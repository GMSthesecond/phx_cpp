"""NAI button (nai_download.py, Newly Acquired Interest): saves both reports with today's date.
"""
from datetime import date

import ark_common
import nai_download


def test_saves_both_reports_with_todays_date(fake_ark, folders, msgboxes):
    """Each report lands in [Folders] NewlyAcquiredInterest as <name>.MM.DD.YYYY.csv."""
    url1, url2 = nai_download._REPORT_URLS
    fake_ark.serve(url1, [['a'], ['1']], filename='5f3e-uuid-name')   # Ark often sends no extension
    fake_ark.serve(url2, [['b'], ['2']], filename='Units Report.csv')

    nai_download.main()

    today = date.today().strftime('%m.%d.%Y')
    out = folders['NewlyAcquiredInterest']
    assert sorted(p.name for p in out.iterdir()) == [f'5f3e-uuid-name.{today}.csv', f'Units Report.{today}.csv']
    assert fake_ark.downloads == [url1, url2]
    assert fake_ark.sessions_saved == 1
    assert msgboxes == [('Newly Acquired Interest', f'Saved 2 reports to:\n{out}')]


def test_logs_in_when_signed_out(fake_ark, folders):
    """A signed-out session goes through ark_common.login before downloading."""
    for url in nai_download._REPORT_URLS:
        fake_ark.serve(url, [['a']])
    fake_ark.needs_login = {'ark.phoenixenergy.com'}

    nai_download.main()

    assert fake_ark.logins == ['https://ark.phoenixenergy.com/**']
    assert len(fake_ark.downloads) == 2


def test_folder_set_before_the_rename_is_still_used(tmp_path, monkeypatch):
    """A settings.ini from the DMD days (only [Folders] DataMeetingDownload) keeps its folder;
    once NewlyAcquiredInterest is set it wins; with neither, the default is Desktop\\NAI."""
    ini = tmp_path / 'settings.ini'
    monkeypatch.setattr(ark_common, '_INI_PATH', str(ini))

    ini.write_text('[Folders]\nDataMeetingDownload=D:\\old DMD\n', encoding='utf-8')
    assert nai_download._out_dir() == 'D:\\old DMD'

    ini.write_text('[Folders]\nDataMeetingDownload=D:\\old DMD\nNewlyAcquiredInterest=D:\\NAI\n', encoding='utf-8')
    assert nai_download._out_dir() == 'D:\\NAI'

    ini.write_text('[Folders]\n', encoding='utf-8')
    assert nai_download._out_dir() == nai_download._DEFAULT_DIR
    assert nai_download._DEFAULT_DIR.endswith('\\Desktop\\NAI')
