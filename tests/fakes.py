"""Fake Ark site and Playwright browser for the Ark script tests (installed by the fake_ark fixture).

The real scripts drive Chromium through Playwright and pull reports with
ark_common.trigger_download. The fake replaces both: a test serves CSV reports by URL,
the script "downloads" them from local files, and the fake records what happened
(downloads, logins, session saves, total time the script asked to wait). Waits are not
slept, so a run that would take minutes against Ark finishes instantly.
"""
import csv
import os
import shutil
import sys
from contextlib import contextmanager
from urllib.parse import urlparse

import ark_common
import playwright.sync_api

LOGIN_PAGE = 'https://login.microsoftonline.com/common/oauth2/authorize'  # where the fake redirects a signed-out page


def write_csv(path, rows, encoding='utf-8'):
    """Writes rows (lists of strings, header first) to path as CSV and returns path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='', encoding=encoding) as f:
        csv.writer(f).writerows(rows)
    return path


def read_csv(path, encoding='utf-8-sig'):
    """Returns every row of a CSV file as a list of lists."""
    with open(path, newline='', encoding=encoding) as f:
        return list(csv.reader(f))


class FakeDownload:
    """Stands in for a Playwright Download: a served local file plus Ark's suggested name."""

    def __init__(self, path, suggested_filename):
        """path is the served file; suggested_filename is what Ark would call it."""
        self._path = path
        self.suggested_filename = suggested_filename

    def path(self):
        """Local path of the downloaded file (Playwright's temp file)."""
        return self._path

    def save_as(self, dest):
        """Copies the download to dest."""
        shutil.copyfile(self._path, dest)


class FakePage:
    """Stands in for a Playwright Page. Supports only what the scripts call outside of
    login/trigger_download/upload (which tests replace); anything else raises."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark
        self.url = 'about:blank'

    def goto(self, url, **kwargs):
        """Navigates; lands on the Microsoft login page if that domain still needs a login."""
        self._ark.visited.append(url)
        domain = urlparse(url).netloc
        self.url = LOGIN_PAGE if domain in self._ark.needs_login else url

    def wait_for_timeout(self, ms):
        """Records the wait instead of sleeping."""
        self._ark.waited_ms += ms

    def __getattr__(self, name):
        """Fails loudly on any Playwright call the fake doesn't model."""
        raise AttributeError(f'FakePage has no {name!r}: the script used a Playwright call '
                             'this test does not fake (replace that function in the test)')


class FakeContext:
    """Stands in for a Playwright BrowserContext."""

    def __init__(self, ark, storage_state):
        """storage_state is the session file the script asked to load (or None)."""
        self._ark = ark
        ark.loaded_session = storage_state

    def new_page(self, **kwargs):
        """Opens a FakePage."""
        return FakePage(self._ark)

    def storage_state(self, path=None):
        """Records a session save and writes an empty session file."""
        self._ark.sessions_saved += 1
        if path:
            with open(path, 'w') as f:
                f.write('{}')


class FakeBrowser:
    """Stands in for a Playwright Browser."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark

    def new_context(self, storage_state=None, **kwargs):
        """Opens a FakeContext."""
        return FakeContext(self._ark, storage_state)

    def new_page(self, **kwargs):
        """Opens a FakePage directly (map_uploader does this)."""
        return FakePage(self._ark)

    def close(self):
        """Records that the browser was closed."""
        self._ark.browser_closed = True


class _FakeChromium:
    """Stands in for playwright.chromium."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark

    def launch(self, **kwargs):
        """Launches a FakeBrowser and records the launch options (e.g. headless)."""
        self._ark.launch_options = kwargs
        return FakeBrowser(self._ark)


class FakeArk:
    """Fake Ark site + Playwright. Attributes record what the script did:
    downloads (URLs pulled), logins (success_url of each login), visited (page.goto URLs),
    sessions_saved, browser_closed, waited_ms. needs_login: domains still signed out."""

    def __init__(self, served_dir):
        """served_dir holds the CSVs that serve() writes."""
        self._served_dir = served_dir
        self._reports = {}
        self.downloads = []
        self.logins = []
        self.visited = []
        self.needs_login = set()
        self.sessions_saved = 0
        self.browser_closed = False
        self.waited_ms = 0
        self.loaded_session = None
        self.launch_options = None

    def serve(self, url, rows, filename='report.csv'):
        """Makes trigger_download(url) return a CSV of rows named filename."""
        path = os.path.join(self._served_dir, str(len(self._reports)), filename)
        write_csv(path, rows)
        self._reports[url] = (path, filename)

    def trigger_download(self, page, report_url, generation_wait_ms=10_000):
        """Replacement for ark_common.trigger_download: returns the served report."""
        if report_url not in self._reports:
            raise AssertionError(f'Script downloaded a report the test did not serve: {report_url}')
        self.downloads.append(report_url)
        self.waited_ms += generation_wait_ms
        return FakeDownload(*self._reports[report_url])

    def login(self, page, username, password, success_url='https://ark.phoenixenergy.com/**'):
        """Replacement for ark_common.login: signs the page's target domain in."""
        assert username and password, 'login called without credentials'
        self.logins.append(success_url)
        domain = urlparse(success_url.replace('**', '')).netloc
        self.needs_login.discard(domain)
        page.url = success_url.replace('**', '')

    @contextmanager
    def sync_playwright(self):
        """Replacement for playwright.sync_api.sync_playwright."""
        class _PW:
            chromium = _FakeChromium(self)
        yield _PW()

    def install(self, monkeypatch):
        """Patches ark_common and every loaded module that bound sync_playwright at import."""
        monkeypatch.setattr(ark_common, 'trigger_download', self.trigger_download)
        monkeypatch.setattr(ark_common, 'login', self.login)
        monkeypatch.setattr(playwright.sync_api, 'sync_playwright', self.sync_playwright)
        for module in list(sys.modules.values()):
            if getattr(module, 'sync_playwright', None) is not None and module is not playwright.sync_api:
                if getattr(module, '__file__', '') and os.path.dirname(os.path.abspath(module.__file__)) \
                        == os.path.dirname(os.path.abspath(ark_common.__file__)):
                    monkeypatch.setattr(module, 'sync_playwright', self.sync_playwright)


class Recorder:
    """Callable that records its calls; used to replace functions like ark_common.upload."""

    def __init__(self, result=None):
        """result is returned from every call."""
        self.calls = []
        self._result = result

    def __call__(self, *args, **kwargs):
        """Records (args, kwargs) and returns result."""
        self.calls.append((args, kwargs))
        return self._result


# (Data Loader status text, whether ark_common.upload should stop waiting). Any "X of Y" row counter means
# Ark has the data and keeps processing it after the browser closes.
LOADER_TEXTS = [
    ('0 of 5', True),            # the counter's first state: already enough
    ('3 of 5', True),
    ('5 of 5', True),
    ('Processed 12 of 12 records', True),
    ('0 of 1,400', True),        # thousands separators
    ('1,400 of 1,400', True),
    ('Uploading...', False),
    ('Save and Upload', False),
    ('Step 1 of', False),        # no second number
]


class _NullLocator:
    """Stand-in for any Playwright locator: every action succeeds and does nothing."""

    def __init__(self):
        """.first returns the same stand-in."""
        self.first = self

    def __getattr__(self, name):
        """Any method (click, wait_for, press_sequentially, ...) is a no-op."""
        return lambda *args, **kwargs: None


class FakeLoaderPage:
    """Stand-in for the Ark Data Loader page ark_common.upload drives. Every click, fill and
    wait succeeds at once; the patterns passed to get_by_text are recorded in text_patterns,
    the (role, name) of each get_by_role in roles, and each page.goto URL in visited."""

    def __init__(self):
        """Starts with nothing recorded."""
        self.text_patterns = []
        self.roles = []
        self.visited = []
        self.keyboard = _NullLocator()

    def goto(self, url, **kwargs):
        """Records the URL opened."""
        self.visited.append(url)

    def locator(self, *args, **kwargs):
        """Any CSS locator."""
        return _NullLocator()

    def get_by_role(self, role, name=None, **kwargs):
        """Records (role, name) of a role locator, e.g. ('option', <pattern for 'Cases'>)."""
        self.roles.append((role, name))
        return _NullLocator()

    def get_by_text(self, pattern, **kwargs):
        """Records the text pattern being waited for."""
        self.text_patterns.append(pattern)
        return _NullLocator()

    def __getattr__(self, name):
        """wait_for_load_state, wait_for_timeout, ... are no-ops."""
        return lambda *args, **kwargs: None


class _FakeDownloadInfo:
    """What page.expect_download yields: .value is the download."""

    def __init__(self, page):
        """page is the FakeReportPage whose click supplies the download."""
        self._page = page

    @property
    def value(self):
        """The download the "Download File" click started."""
        return self._page.download


class _ReportLocator(_NullLocator):
    """A FakeReportPage locator: records clicks on it as (what, page time waited so far)."""

    def __init__(self, page, what):
        """what names the element, e.g. '#notifications-btn' or 'Download File'."""
        super().__init__()
        self._page = page
        self._what = what

    def click(self, *args, **kwargs):
        """Records the click and when it happened."""
        self._page.clicks.append((self._what, self._page.waited_ms))


class _PreparingLocator(_NullLocator):
    """The notifications still in progress: count() plays back FakeReportPage.preparing, one per check."""

    def __init__(self, page):
        """page is the owning FakeReportPage."""
        super().__init__()
        self._page = page

    def filter(self, **kwargs):
        """filter(visible=True) narrows nothing in the fake."""
        return self

    def count(self):
        """How many exports the panel shows in progress at this check (the last value repeats)."""
        self._page.checks += 1
        return self._page.preparing.pop(0) if len(self._page.preparing) > 1 else self._page.preparing[0]


class FakeReportPage:
    """Stand-in for an Ark report page as ark_common.trigger_download drives it. preparing lists how
    many exports the notifications panel shows in progress at each check (the last repeats).
    Records clicks as (element, waited_ms at the time), total waited_ms, checks made and the
    get_by_text patterns used. Waits are not slept."""

    def __init__(self, preparing=(0,)):
        """preparing: in-progress counts for successive checks of the panel."""
        self.preparing = list(preparing)
        self.clicks = []
        self.checks = 0
        self.waited_ms = 0
        self.text_patterns = []
        self.download = FakeDownload('report.csv', 'report.csv')

    def locator(self, selector, **kwargs):
        """The chevron, #notifications-btn or the "Download File" button."""
        return _ReportLocator(self, 'Download File' if 'Download File' in selector else selector)

    def get_by_role(self, role, name=None, **kwargs):
        """The chevron menu's Download button."""
        return _ReportLocator(self, 'Download')

    def get_by_text(self, pattern, **kwargs):
        """The in-progress notification text trigger_download watches for."""
        self.text_patterns.append(pattern)
        return _PreparingLocator(self)

    def wait_for_timeout(self, ms):
        """Adds to waited_ms instead of sleeping."""
        self.waited_ms += ms

    @contextmanager
    def expect_download(self, **kwargs):
        """Yields the download that the "Download File" click inside the block starts."""
        yield _FakeDownloadInfo(self)

    def __getattr__(self, name):
        """goto, wait_for_url, wait_for_load_state, ... are no-ops."""
        return lambda *args, **kwargs: None
