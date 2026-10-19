"""Data Meeting Download button (download_report.py): saves both reports with today's date.
"""
from datetime import date

import download_report


def test_saves_both_reports_with_todays_date(fake_ark, folders, msgboxes):
    """Each report lands in [Folders] DataMeetingDownload as <name>.MM.DD.YYYY.csv."""
    url1, url2 = download_report._REPORT_URLS
    fake_ark.serve(url1, [['a'], ['1']], filename='5f3e-uuid-name')   # Ark often sends no extension
    fake_ark.serve(url2, [['b'], ['2']], filename='Units Report.csv')

    download_report.main()

    today = date.today().strftime('%m.%d.%Y')
    out = folders['DataMeetingDownload']
    assert sorted(p.name for p in out.iterdir()) == [f'5f3e-uuid-name.{today}.csv', f'Units Report.{today}.csv']
    assert fake_ark.downloads == [url1, url2]
    assert fake_ark.sessions_saved == 1
    assert msgboxes == [('Data Meeting Download', f'Saved 2 reports to:\n{out}')]


def test_logs_in_when_signed_out(fake_ark, folders):
    """A signed-out session goes through ark_common.login before downloading."""
    for url in download_report._REPORT_URLS:
        fake_ark.serve(url, [['a']])
    fake_ark.needs_login = {'ark.phoenixenergy.com'}

    download_report.main()

    assert fake_ark.logins == ['https://ark.phoenixenergy.com/**']
    assert len(fake_ark.downloads) == 2
