"""Pulls deals that closed on the previous business day from Ark and uploads their Close Dates.
Launched by the "Close Date" button. Logs into Ark (ark_common credentials/session), downloads
the close-date report, keeps rows that closed since the last business day (Friday-Sunday on
Mondays, and further back after a holiday; see _holidays), writes
close_dates.<mm.dd.yyyy>.csv to the [Folders] CloseDates folder, then uploads it (if it has any
rows) through the Ark data loader as a Landholdings Update. Also Mirror's "Close Date" step
(mirror_step). Depends on playwright; errors shown in a message box.
"""
import csv
import os
from datetime import date, timedelta
import ark_common


_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\Close Date'  # output folder used when [Folders] CloseDates is unset


def _notify(message):
    """Show an info message box titled "Close Dates"."""
    ark_common.notify('Close Dates', message, 0x40)

_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=c348d047aeebd9028494bf6c'  # Ark report listing record Id and Close Date


def _nth_weekday(year, month, weekday, n):
    """The nth (1-based; -1 = last) given weekday (0 = Monday) of a month."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _holidays(year):
    """Office holidays in a year: US federal holidays plus the day after Thanksgiving and
    Christmas Eve. A fixed-date holiday on a weekend also adds its observed weekday (Saturday ->
    Friday, Sunday -> Monday), which for New Year's can be December 31 of the year before.
    Generous on purpose: an extra holiday only re-pulls a day, a missing one loses closes."""
    fixed = [date(year, 1, 1), date(year, 6, 19), date(year, 7, 4), date(year, 11, 11),
             date(year, 12, 24), date(year, 12, 25)]
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    days = set(fixed) | {
        _nth_weekday(year, 1, 0, 3),    # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),    # Presidents' Day
        _nth_weekday(year, 5, 0, -1),   # Memorial Day
        _nth_weekday(year, 9, 0, 1),    # Labor Day
        _nth_weekday(year, 10, 0, 2),   # Columbus Day
        thanksgiving, thanksgiving + timedelta(days=1),
    }
    for d in fixed:
        if d.weekday() == 5:
            days.add(d - timedelta(days=1))
        elif d.weekday() == 6:
            days.add(d + timedelta(days=1))
    return days


def _is_business_day(d):
    """True for a weekday that isn't an office holiday."""
    return d.weekday() < 5 and d not in _holidays(d.year) | _holidays(d.year + 1)


def _target_dates():
    """Return the set of close dates to pull: every day from the last business day before today
    through yesterday. A normal day pulls yesterday, Monday pulls Friday through Sunday, and after
    a holiday the window reaches back past it (Tuesday after Labor Day pulls Friday through Monday)."""
    today = date.today()
    start = today - timedelta(days=1)
    while not _is_business_day(start) and (today - start).days < 14:
        start -= timedelta(days=1)
    return {start + timedelta(days=n) for n in range((today - start).days)}


def main(quiet=False):
    """Log in, download the report, filter to the target close dates (skipping Deferred
    deals), write the CSV, and upload it if it has any rows. Always saves the browser session
    afterward. Returns the number of close dates uploaded. quiet=True (Mirror) shows no message boxes."""
    out_dir = ark_common.read_folder('CloseDates', _DEFAULT_DIR)
    os.makedirs(out_dir, exist_ok=True)

    targets = _target_dates()
    today_str = date.today().strftime('%m.%d.%Y')
    rows = []

    with ark_common.ark_page(_REPORT_URL) as page:
        dl = ark_common.trigger_download(page, _REPORT_URL)

        # Read the temp file while the browser still holds it open
        with open(dl.path(), newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header row
            for row in reader:
                if len(row) < 3:
                    continue
                if len(row) >= 5 and row[3].strip() == 'Deferred':
                    if not quiet:
                        _notify('A deferred deal was skipped')
                    continue
                record_id = row[1].strip()
                close_date_str = row[2].strip()
                try:
                    close_date = ark_common.parse_date(close_date_str)
                except ValueError:
                    continue
                if close_date in targets:
                    rows.append((record_id, close_date_str))

        # Write filtered CSV before upload (path needed by ark_common.upload)
        out_path = os.path.join(out_dir, f'close_dates.{today_str}.csv')
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Id', 'Close Date'])
            writer.writerows(rows)
        print(f'Saved {len(rows)} row(s) to: {out_path}', flush=True)

        # Nothing to send when there are no rows (an empty upload used to time out)
        if rows:
            ark_common.upload(page, out_path, f'close date {today_str}', dataset='Landholdings')
    return len(rows)


def mirror_step():
    """Mirror's Close Date step: run quietly and return (result kind, report line)."""
    uploaded = main(quiet=True)
    if uploaded:
        return ark_common.UPLOADED, f'Uploaded close dates for {ark_common.plural(uploaded, "landholding")}'
    return ark_common.NOTHING, 'No close dates to upload'


if __name__ == '__main__':
    ark_common.run_button('Close Dates', main,
                          os.path.join(ark_common.read_folder('CloseDates', _DEFAULT_DIR), 'close_dates_error.log'))
