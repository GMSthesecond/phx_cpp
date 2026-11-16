"""ark_common: the Ark Data Loader wizard shared by every script that uploads (Close Date,
Case Update, Cost to Extend, Case Unit Names), the report download every Ark script uses
(trigger_download), the downloaded-report column check (check_columns) and settings lookups.
Also the large-download check: before asking Ark for an export, trigger_download reads the report
page's Total Record Count (record_count) and, at LARGE_DOWNLOAD_ROWS or more or when unreadable,
only goes on after a Yes in confirm_download's box; a No stops the script (run_button's warning).

upload is driven against FakeLoaderPage and trigger_download against FakeReportPage, which
record what was clicked, picked and waited for, so nothing reaches Ark.
"""
from datetime import datetime, timedelta

import pytest

import ark_common
from fakes import LOADER_TEXTS, STUCK_UPLOADS, FakeLoaderPage, FakeReportPage, ready_card, write_csv


@pytest.mark.parametrize('text, stops', LOADER_TEXTS)
def test_upload_waits_only_for_the_row_counter(text, stops):
    """upload stops waiting at the first "X of Y" row counter (Ark already has the data), commas allowed."""
    page = FakeLoaderPage()
    ark_common.upload(page, 'upload.csv', 'upload name', dataset='Landholdings')
    assert bool(page.text_patterns[-1].search(text)) == stops


@pytest.mark.parametrize('dataset', ['Landholdings', 'Units', 'Cases'])
def test_upload_picks_the_given_dataset(dataset):
    """The listbox option clicked is the whole dataset name in any capitalization (Ark renamed
    "Case" to "cases"), never a longer or shorter name, on the Data Loader page."""
    page = FakeLoaderPage()
    ark_common.upload(page, 'upload.csv', 'upload name', dataset=dataset)
    assert page.visited == [ark_common.UPLOAD_URL]
    [option] = [name for role, name in page.roles if role == 'option']
    for shown in (dataset, dataset.lower(), dataset.upper(), f' {dataset} '):
        assert option.search(shown), shown
    for other in (dataset[:-1], f'{dataset} Archive', f'Old {dataset}'):
        assert not option.search(other), other


def test_upload_confirms_with_the_operation_button():
    """The final confirm button matches the operation (Update by default), and only that word."""
    page = FakeLoaderPage()
    ark_common.upload(page, 'upload.csv', 'upload name', dataset='Cases')
    confirm = page.roles[-1]
    assert confirm[0] == 'button'
    assert confirm[1].match('Update') and not confirm[1].match('Update all')


def test_settings_with_percent_signs_read_back_unchanged(tmp_path, monkeypatch):
    """A password, token or folder with % in it is read as typed (configparser would otherwise
    treat % as a variable and fail, stopping every Ark script)."""
    ini = tmp_path / 'settings.ini'
    ini.write_text('[Credentials]\nusername=me@example.com\npassword=50%off%\n'
                   '[EnverusCredentials]\nidentifier=me\npassword=%(x)s\n'
                   '[SlackCredentials]\ntoken=xoxp-1%2\n'
                   '[Folders]\nMaps=C:\100% done\n', encoding='utf-8')
    monkeypatch.setattr(ark_common, '_INI_PATH', str(ini))
    assert ark_common.read_credentials() == ('me@example.com', '50%off%')
    assert ark_common.read_enverus_credentials() == ('me', '%(x)s')
    assert ark_common.read_slack_token() == 'xoxp-1%2'
    assert ark_common.read_folder('Maps', 'default') == 'C:\100% done'


@pytest.mark.parametrize('folders, expected', [
    ('New=D:\\new\nOld=D:\\old\n', 'D:\\new'),  # the key is set: its value
    ('Old=D:\\old\n', 'default'),               # only another key set (e.g. a key's pre-rename name): the default
    ('', 'default'),                            # nothing set: the default
])
def test_read_folder_reads_only_its_own_key(tmp_path, monkeypatch, folders, expected):
    """read_folder(key, default) returns [Folders] key or default, never another key's folder (the
    DataMeetingDownload -> NewlyAcquiredInterest fallback sent NAI reports to the old DMD folder)."""
    ini = tmp_path / 'settings.ini'
    ini.write_text('[Folders]\n' + folders, encoding='utf-8')
    monkeypatch.setattr(ark_common, '_INI_PATH', str(ini))
    assert ark_common.read_folder('New', 'default') == expected


def test_ark_page_logs_in_and_keeps_the_login_when_a_step_fails(fake_ark):
    """ark_page logs in if Ark asks, and saves the session and closes the browser even when the
    work inside fails, so the next run doesn't redo 2FA."""
    url = 'https://ark.phoenixenergy.com/report?recordId=test'
    fake_ark.serve(url, [['Id']])
    fake_ark.needs_login = {'ark.phoenixenergy.com'}
    with pytest.raises(RuntimeError):
        with ark_common.ark_page(url):
            raise RuntimeError('a step failed')
    assert fake_ark.logins == ['https://ark.phoenixenergy.com/**']
    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed


_URL = 'https://ark.phoenixenergy.com/report?recordId=test'  # report URL the download tests open
_YESTERDAY = datetime.now() - timedelta(days=1)  # when the old exports in the panel were made
_OLD_FILES = [ready_card('RW Case Info', _YESTERDAY), ready_card('Land Holding Closings EM', _YESTERDAY)]  # already listed
_COUNT_MS = ark_common._COUNT_SETTLE_MS  # waited reading the Total Record Count (two readings that agree)


def test_download_is_not_held_up_by_stuck_upload_notifications():
    """Ark's Data Loader notifications stuck at "0% Complete" since 10/20/2026 don't count as an export in
    progress: the new file is taken as soon as it's listed. Waiting on them made every Ark download
    sit for 10 minutes and fail (Close Date, 11/3/2026)."""
    page = FakeReportPage(old_files=_OLD_FILES, others=STUCK_UPLOADS)
    dl = ark_common.trigger_download(page, _URL, generation_wait_ms=10_000)
    assert dl is page.download
    assert page.clicked_file == page.new_file
    assert page.waited_ms == _COUNT_MS + ark_common._PANEL_MS + 10_000


def test_download_waits_until_ark_lists_the_new_file():
    """Until the requested export is listed, trigger_download keeps checking, then takes that file,
    not the top one already there. Taking the top file at once grabbed an older export (Mirror's
    STR step got yesterday's units report on 10/21/2026)."""
    page = FakeReportPage(old_files=_OLD_FILES, ready_after=2)
    dl = ark_common.trigger_download(page, _URL, generation_wait_ms=60_000)
    assert dl is page.download and page.clicked_file == page.new_file
    assert page.checks == 3
    assert page.clicks[-1] == ('Download File', _COUNT_MS + ark_common._PANEL_MS + 60_000 + 2 * ark_common._POLL_MS)


def test_download_finished_in_time_is_taken_after_the_first_wait():
    """A report Ark finished within generation_wait_ms is taken without extra waiting."""
    page = FakeReportPage()
    ark_common.trigger_download(page, _URL, generation_wait_ms=10_000)
    assert page.waited_ms == _COUNT_MS + ark_common._PANEL_MS + 10_000
    assert [what for what, _ in page.clicks][-2:] == ['#notifications-btn', 'Download File']


def test_large_download_gets_minutes_to_start():
    """After Download File is clicked, the browser gets at least 2 minutes for the download to start.
    The 15 s it gets now ran out on PPIQ's 125 MB Inverse report on 11/10/2026."""
    page = FakeReportPage()
    ark_common.trigger_download(page, _URL)
    assert page.download_timeout >= 120_000


def test_download_never_listed_fails_instead_of_taking_an_older_file():
    """No new file after _GENERATION_TIMEOUT_MS raises, and no file is taken."""
    page = FakeReportPage(old_files=_OLD_FILES, new_file=None)
    with pytest.raises(RuntimeError, match='no new file'):
        ark_common.trigger_download(page, _URL, generation_wait_ms=60_000)
    assert page.clicked_file is None
    assert page.waited_ms >= ark_common._GENERATION_TIMEOUT_MS


def test_download_reopens_the_panel_while_waiting():
    """Every _REOPEN_POLLS checks without the file the panel is closed and opened again, in case it
    doesn't refresh while open; it is left open for the Download File click."""
    page = FakeReportPage(ready_after=ark_common._REOPEN_POLLS + 1)
    ark_common.trigger_download(page, _URL)
    bell = [what for what, _ in page.clicks].count('#notifications-btn')
    assert bell == 2 + 1 + 2  # look before Download (open, close), open after, one reopen
    assert page.panel_open and page.clicked_file == page.new_file


def test_download_ignores_an_old_file_the_panel_hadnt_listed_yet():
    """If the panel hadn't filled in when the files already there were noted, an older export that
    shows up later still isn't taken: a file stamped before the Download click is skipped."""
    page = FakeReportPage(old_files=_OLD_FILES, slow_panel=True, ready_after=1)
    ark_common.trigger_download(page, _URL)
    assert page.clicked_file == page.new_file


def test_download_ignores_an_identical_file_already_listed():
    """A file with the same report, minute and date as one listed before Download (a run started
    twice within a minute) isn't the new one."""
    same = ready_card('Report', datetime.now())
    page = FakeReportPage(old_files=[same], new_file=same, ready_after=1)
    ark_common.trigger_download(page, _URL)
    assert page.checks == 2  # the copy already there wasn't taken at the first check


@pytest.mark.parametrize('text, when', [
    ('Your file is ready for download! For Land Holding Closings EM Download File 10:22 AM 11/3/2026',
     datetime(2026, 11, 3, 10, 22)),
    ('Your file is ready for download! For RW Case Info Download File 01:17 PM 10/20/2026',
     datetime(2026, 10, 20, 13, 17)),
    ('For X 12:05 AM 1/2/2027', datetime(2027, 1, 2, 0, 5)),    # just after midnight
    ('For X 12:30 PM 12/31/2026', datetime(2026, 12, 31, 12, 30)),  # noon
    ('For X 10:22 AM 10:22 AM 11/3/2026 11/3/2026', datetime(2026, 11, 3, 10, 22)),  # time shown twice (mobile + desktop)
    # Run together, as an element's textContent gave them on the live run of 11/3/2026
    ('Your file is ready for download!For Land Holding Closings EM10:30 AM11/3/2026 Download File',
     datetime(2026, 11, 3, 10, 30)),
    ('Your file is ready for download!For Phoenix Cases Fixes09:34 AM10/20/2026 Download File',
     datetime(2026, 10, 20, 9, 34)),
    ('Your file is ready for download! For X', None),           # no time or date
    ('For X 10:22 AM 13/45/2026', None),                        # not a real date
])
def test_card_time_reads_the_notification_stamp(text, when):
    """_card_time reads the time and date Ark prints on a notification (the PC's local time)."""
    assert ark_common._card_time(text) == when


_STR_COLUMNS = ['Id', 'Section', None, 'Range']  # columns a test script reads; None = not read


def test_check_columns_accepts_the_expected_report(tmp_path):
    """Matching names pass; None accepts any name; extra columns after them are fine."""
    path = write_csv(str(tmp_path / 'r.csv'), [['Id', 'Section', 'Township', 'Range', 'More'], ['1', '2', '3', '4', '5']],
                     encoding='utf-8-sig')
    ark_common.check_columns(path, _STR_COLUMNS, 'Check STR')


@pytest.mark.parametrize('header', [
    ['Record Id', 'STRs', 'Unit Name'],          # Mirror's STR step got the units report on 10/21/2026
    ['Id', 'Section', 'Township'],               # too few columns
    ['Id', 'Range', 'Township', 'Section'],      # reordered
    [],                                          # empty file
])
def test_check_columns_rejects_a_different_report(tmp_path, header):
    """A report without the expected columns, in order, raises naming the report and what came back."""
    path = write_csv(str(tmp_path / 'r.csv'), [header] if header else [])
    with pytest.raises(RuntimeError, match='Check STR') as err:
        ark_common.check_columns(path, _STR_COLUMNS, 'Check STR')
    assert ', '.join(header) in str(err.value)


# ---- Large downloads: Total Record Count checked before the export is asked for ----

_YES, _NO = 6, 7  # MessageBoxW answers, queued in msgboxes.answers


def _asked_for_export(page):
    """Whether trigger_download got as far as asking Ark for the export (chevron menu's Download)."""
    return 'Download' in [what for what, _ in page.clicks]


@pytest.mark.parametrize('text, count', [
    ('Total Record Count 13', 13),                  # as on the report page (screenshot 11/12/2026)
    ('Total Record Count 286,722', 286_722),        # thousands separators
    ('Total Record Count: 10,000', 10_000),
    ('total record count\n9999', 9_999),
    ('Total Record Count 12.3K', None),             # rounded: not trusted as a count
    ('Total Record Count 1M', None),
    ('Total Record Count', None),                   # label with no number (still loading)
    (None, None),                                   # page has no Total Record Count card
])
def test_record_count_reads_the_total_record_count_card(text, count):
    """record_count reads the number under the report page's Total Record Count label; anything it
    can't read as a whole count gives None (after _COUNT_WAIT_MS)."""
    page = FakeReportPage(count_texts=[text])
    assert ark_common.record_count(page) == count
    if count is None:
        assert page.waited_ms >= ark_common._COUNT_WAIT_MS


def test_record_count_waits_for_the_count_to_settle():
    """A count still changing as the page fills in isn't trusted until two readings in a row agree."""
    page = FakeReportPage(count_texts=['Total Record Count 0', 'Total Record Count 40',
                                       'Total Record Count 52,000', 'Total Record Count 52,000'])
    assert ark_common.record_count(page) == 52_000
    assert page.count_reads == 4


@pytest.mark.parametrize('count', [0, 13, 9_999])
def test_small_report_downloads_without_asking(msgboxes, count):
    """Under LARGE_DOWNLOAD_ROWS records the download goes ahead with no box."""
    page = FakeReportPage(count_texts=[f'Total Record Count {count:,}'])
    assert ark_common.trigger_download(page, _URL) is page.download
    assert msgboxes == []


@pytest.mark.parametrize('count', [10_000, 286_722])
def test_large_report_is_not_requested_when_the_user_says_no(msgboxes, count):
    """At LARGE_DOWNLOAD_ROWS records or more (10,000 itself included) a Yes/No box names the count and
    report; No raises DownloadCancelled before Ark is even asked for the export, so nothing is downloaded."""
    page = FakeReportPage(count_texts=[f'Total Record Count {count:,}'])
    msgboxes.answers = [_NO]
    with pytest.raises(ark_common.DownloadCancelled) as err:
        ark_common.trigger_download(page, _URL)
    assert str(err.value) == f'Large download cancelled: {count:,} records, {_URL}'
    assert not _asked_for_export(page) and page.clicked_file is None
    [(title, text)] = msgboxes
    assert title == 'Large Ark download'
    assert text == (f'This Ark report has {count:,} records:\n{_URL}\n\nReports of 10,000 records or more '
                    f"need your OK before they're downloaded.\n\nDownload it?")


def test_large_report_downloads_when_the_user_says_yes(msgboxes):
    """Yes in the box lets the download go ahead as usual."""
    page = FakeReportPage(count_texts=['Total Record Count 810,608'])
    msgboxes.answers = [_YES]
    assert ark_common.trigger_download(page, _URL) is page.download
    assert len(msgboxes) == 1 and page.clicked_file == page.new_file


@pytest.mark.parametrize('answer, downloads', [(_NO, False), (_YES, True)])
def test_unreadable_count_asks_too(msgboxes, answer, downloads):
    """A page with no readable Total Record Count (e.g. Ark renamed the label) asks rather than risk a
    large download; the box says the count couldn't be read."""
    page = FakeReportPage(count_texts=[None])
    msgboxes.answers = [answer]
    if downloads:
        ark_common.trigger_download(page, _URL)
    else:
        with pytest.raises(ark_common.DownloadCancelled, match='record count unreadable'):
            ark_common.trigger_download(page, _URL)
    assert _asked_for_export(page) == downloads
    [(_, text)] = msgboxes
    assert text.startswith("This Ark report's record count couldn't be read (no Total Record Count on its page):\n")


def test_large_download_box_is_topmost_with_no_as_default(monkeypatch, capsys):
    """The box is a Yes/No warning kept above the browser, with No as the default button (Enter
    doesn't download), and @WAITING / @RESUMED go round it for Mirror; closing it counts as No."""
    shown = []
    monkeypatch.setattr(ark_common, 'notify', lambda title, text, flags: shown.append(flags) or 2)  # 2 = IDCANCEL
    with pytest.raises(ark_common.DownloadCancelled):
        ark_common.confirm_download(_URL, 50_000)
    [flags] = shown
    assert flags & 0xF == 0x4          # MB_YESNO
    assert flags & 0xF0 == 0x30        # MB_ICONWARNING
    assert flags & 0xF00 == 0x100      # MB_DEFBUTTON2: No
    assert flags & 0x40000             # MB_TOPMOST
    assert capsys.readouterr().out.splitlines() == ['@WAITING', '@RESUMED']


def test_run_button_reports_a_cancelled_download_as_stopped(fake_ark, msgboxes, tmp_path):
    """A script whose large download was refused stops with a warning naming the report (no error log),
    and nothing after that download runs."""
    url = 'https://ark.phoenixenergy.com/report?recordId=big'
    fake_ark.serve(url, [['Id'], ['1']], records=12_345)
    msgboxes.answers = [_NO]
    after = []

    def main():
        with ark_common.ark_page(url) as page:
            ark_common.trigger_download(page, url)
            after.append('ran')
    log = tmp_path / 'x_error.log'
    assert ark_common.run_button('X', main, str(log)) is None
    assert after == [] and fake_ark.downloads == [] and not log.exists()
    assert msgboxes[-1] == ('X', f'X stopped. Large download cancelled: 12,345 records, {url}')
