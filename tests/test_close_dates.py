"""Close Date button (close_dates.py): pulls yesterday's closes (Fri-Sun on Mondays) and uploads them.

The Ark Data Loader step (ark_common.upload) is replaced by a recorder, and "today" is pinned.
"""
from datetime import date, timedelta

import pytest

import ark_common
import close_dates
from fakes import Recorder, read_csv

_MONDAY = date(2026, 9, 28)  # a Monday, so the weekend rule applies
_TUESDAY = date(2026, 9, 29)


def _pin_today(monkeypatch, day):
    """Makes close_dates think today is day."""
    class _Date(date):
        @classmethod
        def today(cls):
            return cls(day.year, day.month, day.day)
    monkeypatch.setattr(close_dates, 'date', _Date)


def _days(first, last):
    """Every date from first through last."""
    return {first + timedelta(days=n) for n in range((last - first).days + 1)}


@pytest.mark.parametrize('today, expected', [
    (_MONDAY, {date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27)}),
    (_TUESDAY, {date(2026, 9, 28)}),
    # After a holiday: from the last business day before it through yesterday.
    (date(2026, 9, 8), _days(date(2026, 9, 4), date(2026, 9, 7))),        # Tuesday after Labor Day
    (date(2026, 11, 30), _days(date(2026, 11, 25), date(2026, 11, 29))),  # Monday after Thanksgiving + Friday
    (date(2026, 12, 28), _days(date(2026, 12, 23), date(2026, 12, 27))),  # Monday after Christmas Eve/Day
    (date(2026, 7, 6), _days(date(2026, 7, 2), date(2026, 7, 5))),        # July 4 on Saturday, observed Friday
    (date(2027, 1, 4), _days(date(2026, 12, 31), date(2027, 1, 3))),      # New Year's on Friday
    (date(2028, 1, 3), _days(date(2027, 12, 30), date(2028, 1, 2))),      # Jan 1 Saturday, observed Dec 31 the year before
    (date(2026, 1, 20), _days(date(2026, 1, 16), date(2026, 1, 19))),     # Tuesday after MLK Day
    (date(2026, 6, 22), _days(date(2026, 6, 18), date(2026, 6, 21))),     # Monday after Juneteenth (Friday)
])
def test_target_dates(monkeypatch, today, expected):
    """Pulls every day from the last business day before today through yesterday: Monday pulls
    Friday through Sunday, a normal day pulls yesterday, and holidays stretch the window back."""
    _pin_today(monkeypatch, today)
    assert close_dates._target_dates() == expected


def test_holidays_2026():
    """The office holidays for 2026, including weekend-observed dates (July 4 is a Saturday)."""
    assert close_dates._holidays(2026) == {
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 5, 25), date(2026, 6, 19),
        date(2026, 7, 3), date(2026, 7, 4), date(2026, 9, 7), date(2026, 10, 12), date(2026, 11, 11),
        date(2026, 11, 26), date(2026, 11, 27), date(2026, 12, 24), date(2026, 12, 25),
    }


@pytest.mark.parametrize('text', ['2026-09-25', '09/25/2026', '9/25/26', '2026/09/25'])
def test_parse_date_formats(text):
    """Every date format Ark has used parses to the same day (ark_common.parse_date, used by close_dates)."""
    assert ark_common.parse_date(text) == date(2026, 9, 25)


def test_parse_date_rejects_garbage():
    """An unrecognized date raises ValueError (the row is then skipped)."""
    with pytest.raises(ValueError):
        ark_common.parse_date('Sept 25')


def test_monday_run_writes_weekend_closes_and_uploads(fake_ark, folders, monkeypatch, msgboxes):
    """Rows closed Fri-Sun are kept, Deferred deals are skipped with a message, others are dropped."""
    _pin_today(monkeypatch, _MONDAY)
    upload = Recorder()
    monkeypatch.setattr(ark_common, 'upload', upload)
    fake_ark.serve(close_dates._REPORT_URL, [
        ['Name', 'Id', 'Close Date', 'Status', 'x'],
        ['a', 'LH-FRI', '09/25/2026', 'Closed', ''],
        ['b', 'LH-SUN', '2026-09-27', 'Closed', ''],
        ['c', 'LH-THU', '09/24/2026', 'Closed', ''],   # before the window
        ['d', 'LH-DEF', '09/26/2026', 'Deferred', ''],
        ['e', 'LH-BAD', 'not a date', 'Closed', ''],
        ['short'],
    ])

    close_dates.main()

    out_path = folders['CloseDates'] / 'close_dates.09.28.2026.csv'
    assert read_csv(out_path) == [['Id', 'Close Date'], ['LH-FRI', '09/25/2026'], ['LH-SUN', '2026-09-27']]
    assert ('Close Dates', 'A deferred deal was skipped') in msgboxes
    (_page, csv_path, upload_name), kwargs = upload.calls[0]
    assert (csv_path, upload_name) == (str(out_path), 'close date 09.28.2026')
    assert kwargs == {'dataset': 'Landholdings'}
    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed


def _serve_monday_report(fake_ark):
    """Serves a report with two Friday-Sunday closes, a Deferred one and one outside the window."""
    fake_ark.serve(close_dates._REPORT_URL, [
        ['Name', 'Id', 'Close Date', 'Status', 'x'],
        ['a', 'LH-FRI', '09/25/2026', 'Closed', ''],
        ['b', 'LH-SUN', '2026-09-27', 'Closed', ''],
        ['c', 'LH-THU', '09/24/2026', 'Closed', ''],
        ['d', 'LH-DEF', '09/26/2026', 'Deferred', ''],
    ])


def test_no_closes_skips_the_upload(fake_ark, folders, monkeypatch):
    """With nothing in the window there is no upload (there is nothing to send; an empty upload
    used to fail after a 2-minute wait)."""
    _pin_today(monkeypatch, _TUESDAY)
    upload = Recorder()
    monkeypatch.setattr(ark_common, 'upload', upload)
    fake_ark.serve(close_dates._REPORT_URL, [['Name', 'Id', 'Close Date', 'Status', 'x'],
                                             ['a', 'LH-OLD', '09/01/2026', 'Closed', '']])

    assert close_dates.main() == 0

    assert upload.calls == []
    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed


def test_mirror_step_reports_the_upload_without_popups(fake_ark, folders, monkeypatch, msgboxes):
    """Mirror gets the uploaded count, and the Deferred message box is not shown."""
    _pin_today(monkeypatch, _MONDAY)
    upload = Recorder()
    monkeypatch.setattr(ark_common, 'upload', upload)
    _serve_monday_report(fake_ark)

    assert close_dates.mirror_step() == (ark_common.UPLOADED, 'Uploaded close dates for 2 landholdings')
    assert len(upload.calls) == 1
    assert msgboxes == []


def test_mirror_step_with_no_closes(fake_ark, folders, monkeypatch):
    """Nothing in the window: Mirror reports no changes and nothing is uploaded."""
    _pin_today(monkeypatch, _TUESDAY)
    upload = Recorder()
    monkeypatch.setattr(ark_common, 'upload', upload)
    _serve_monday_report(fake_ark)

    assert close_dates.mirror_step() == (ark_common.NOTHING, 'No close dates to upload')
    assert upload.calls == []

