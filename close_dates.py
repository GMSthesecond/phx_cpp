"""Pulls deals that closed on the previous business day from Ark and uploads their Close Dates.
Launched by the "Close Date" button. Logs into Ark (ark_common credentials/session), downloads
the close-date report, keeps rows that closed yesterday (Friday-Sunday on Mondays), writes
close_dates.<mm.dd.yyyy>.csv to the [Folders] CloseDates folder, then uploads it through the
Ark data loader as a Landholdings Update. Depends on playwright; errors shown in a message box.
"""
import ctypes
import csv
import os
import re
from datetime import date, datetime, timedelta
from playwright.sync_api import sync_playwright
import ark_common


def _notify(message):
    """Show an info message box titled "Close Dates"."""
    ctypes.windll.user32.MessageBoxW(0, message, 'Close Dates', 0x40)

_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=c348d047aeebd9028494bf6c'  # Ark report listing record Id and Close Date
_UPLOAD_URL = 'https://ark.phoenixenergy.com/data/data-loader/newUpload'  # Ark data-loader new-upload page


def _target_dates():
    """Return the set of close dates to pull: yesterday, or Friday through Sunday when run
    on a Monday (so weekend closes aren't missed). Holidays are not handled."""
    today = date.today()
    if today.weekday() == 0:  # Monday — previous Friday, Saturday and Sunday
        return {today - timedelta(days=n) for n in (1, 2, 3)}
    return {today - timedelta(days=1)}


def _parse_date(s):
    """Parse a report date in one of several formats; raises ValueError if none match."""
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Unrecognized date format: {s!r}')


def _upload(page, csv_path, upload_name, dataset='Landholdings', operation='Update'):
    """Drive the Ark data loader to upload csv_path as the given dataset/operation.
    Blocks until the "X of X" completion text appears (up to 2 minutes).
    Duplicated in non_hbp_mi.py."""
    page.goto(_UPLOAD_URL)
    page.wait_for_load_state('networkidle')

    # 1 — select the operation card (Update, Insert, etc.)
    card_label = page.locator('p.font-semibold', has_text=operation)
    card_label.wait_for(timeout=15_000)
    page.wait_for_timeout(1500)
    card_label.click()
    page.wait_for_load_state('networkidle')

    # 2 — select the dataset from the listbox
    page.locator('[aria-haspopup="listbox"]').click(timeout=10_000)
    page.get_by_role('option', name=dataset, exact=True).click(timeout=10_000)

    # 3 — fill the upload name (close the listbox dropdown first with Escape)
    page.keyboard.press('Escape')
    name_input = page.locator('input.bg-neutral-gray-1')
    name_input.wait_for(timeout=10_000)
    name_input.click()
    name_input.press_sequentially(upload_name)

    # 4 — attach the CSV
    page.locator('input[type="file"]').set_input_files(csv_path)

    # 5 — continue to the next page
    page.get_by_role('button', name=re.compile(r'continue', re.I)).click()
    page.wait_for_load_state('networkidle')

    # 6 — submit
    page.get_by_role('button', name=re.compile(r'save and upload', re.I)).click()

    # 7 — confirm in the popup/modal
    confirm_btn = page.get_by_role('button', name=re.compile(rf'^{operation}$', re.I))
    confirm_btn.wait_for(timeout=15_000)
    confirm_btn.click()

    # Wait for "X of X" completion indicator (up to 2 minutes)
    page.get_by_text(re.compile(r'\d+ of \d+')).first.wait_for(timeout=120_000)
    print('Upload complete.', flush=True)


def main():
    """Log in, download the report, filter to the target close dates (skipping Deferred
    deals), write the CSV, and upload it. Always saves the browser session afterward."""
    out_dir = ark_common.read_folder('CloseDates', r'C:\Users\Ethan Mesecher\Desktop\Close Date')
    os.makedirs(out_dir, exist_ok=True)

    username, password = ark_common.read_credentials()
    targets = _target_dates()
    today_str = date.today().strftime('%m.%d.%Y')
    rows = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(
            storage_state=ark_common._SESSION if os.path.exists(ark_common._SESSION) else None,
            accept_downloads=True
        )
        try:
            page = ctx.new_page()

            page.goto(_REPORT_URL)
            if 'microsoftonline.com' in page.url or 'cloudflareaccess.com' in page.url:
                ark_common.login(page, username, password)

            dl = ark_common.trigger_download(page, _REPORT_URL)

            # Read the temp file while the browser still holds it open
            with open(dl.path(), newline='', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header row
                for row in reader:
                    if len(row) < 3:
                        continue
                    if len(row) >= 5 and row[3].strip() == 'Deferred':
                        _notify('A deferred deal was skipped')
                        continue
                    record_id = row[1].strip()
                    close_date_str = row[2].strip()
                    try:
                        close_date = _parse_date(close_date_str)
                    except ValueError:
                        continue
                    if close_date in targets:
                        rows.append((record_id, close_date_str))

            # Write filtered CSV before upload (path needed by _upload)
            out_path = os.path.join(out_dir, f'close_dates.{today_str}.csv')
            with open(out_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Id', 'Close Date'])
                writer.writerows(rows)
            print(f'Saved {len(rows)} row(s) to: {out_path}', flush=True)

            _upload(page, out_path, f'close date {today_str}')
        finally:
            # Persist whatever session now exists — including a freshly completed manual
            # login/2FA — even if a step above failed, so a crash doesn't force the user
            # to log in and redo 2FA again on the next run.
            ctx.storage_state(path=ark_common._SESSION)
            browser.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        _notify(f'Close Dates failed:\n{e}')
