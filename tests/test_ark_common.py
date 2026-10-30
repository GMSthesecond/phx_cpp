"""ark_common: the Ark Data Loader wizard shared by every script that uploads (Close Date,
Case Update, Cost to Extend, Case Unit Names), the report download every Ark script uses
(trigger_download), the downloaded-report column check (check_columns) and settings lookups.

upload is driven against FakeLoaderPage and trigger_download against FakeReportPage, which
record what was clicked, picked and waited for, so nothing reaches Ark.
"""
import pytest

import ark_common
from fakes import LOADER_TEXTS, FakeLoaderPage, FakeReportPage, write_csv


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
    ('New=D:\\new\nOld=D:\\old\n', 'D:\\new'),  # the new key wins
    ('Old=D:\\old\n', 'D:\\old'),               # a folder saved under the old name is kept
    ('', 'default'),                            # neither set: the default
])
def test_read_folder_falls_back_to_a_renamed_key(tmp_path, monkeypatch, folders, expected):
    """read_folder(key, default, old_key=...) reads the key's old name when the new one is unset,
    so renaming a [Folders] key (e.g. DataMeetingDownload -> NewlyAcquiredInterest) doesn't lose it."""
    ini = tmp_path / 'settings.ini'
    ini.write_text('[Folders]\n' + folders, encoding='utf-8')
    monkeypatch.setattr(ark_common, '_INI_PATH', str(ini))
    assert ark_common.read_folder('New', 'default', old_key='Old') == expected


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


def test_download_waits_until_ark_finishes_the_report():
    """While the notifications panel shows an export in progress, trigger_download keeps waiting,
    then takes the file. Taking the top file at once grabbed an older export (Mirror's STR step
    got yesterday's units report on 10/21/2026)."""
    page = FakeReportPage(preparing=[1, 1, 0])
    dl = ark_common.trigger_download(page, _URL, generation_wait_ms=60_000)
    assert dl is page.download
    assert page.checks == 3
    assert page.clicks[-1] == ('Download File', 60_000 + 2 * ark_common._POLL_MS)


def test_download_finished_in_time_is_taken_after_the_first_wait():
    """A report Ark finished within generation_wait_ms is taken without extra waiting."""
    page = FakeReportPage(preparing=[0])
    ark_common.trigger_download(page, _URL, generation_wait_ms=10_000)
    assert page.waited_ms == 10_000
    assert [what for what, _ in page.clicks][-2:] == ['#notifications-btn', 'Download File']


def test_download_still_preparing_fails_instead_of_taking_an_older_file():
    """A report still building after _GENERATION_TIMEOUT_MS raises, and no file is taken."""
    page = FakeReportPage(preparing=[1])
    with pytest.raises(RuntimeError, match='still preparing'):
        ark_common.trigger_download(page, _URL, generation_wait_ms=60_000)
    assert 'Download File' not in [what for what, _ in page.clicks]
    assert page.waited_ms >= ark_common._GENERATION_TIMEOUT_MS


@pytest.mark.parametrize('text, preparing', [
    ("We'll let you know when your file is ready for download", True),   # just started
    ('We’ll let you know when your file is ready for download', True),  # curly apostrophe
    ('4% Complete', True),
    ('99% Complete', True),
    ('100% Complete', False),        # done
    ('Download File', False),
    ('Preparing download for report LandHoldings Upload Template EM', False),  # the title alone may stay
])
def test_preparing_text_matches_only_exports_in_progress(text, preparing):
    """_PREPARING matches the notification lines Ark shows while it builds an export."""
    assert bool(ark_common._PREPARING.search(text)) == preparing


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
