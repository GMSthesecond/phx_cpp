"""ark_common.upload: the Ark Data Loader wizard shared by every script that uploads
(Close Date, Case Update, Cost to Extend, Case Unit Names).

Driven against FakeLoaderPage, which records the page opened, the options and buttons
picked and the text waited for, so nothing reaches Ark.
"""
import pytest

import ark_common
from fakes import LOADER_TEXTS, FakeLoaderPage


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
