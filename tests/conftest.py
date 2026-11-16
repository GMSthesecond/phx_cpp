"""Shared pytest setup for the regression tests (run `py -m pytest`; see docs/TESTING.md).

pytest loads this before any test module. At import it makes the whole run offline and harmless:
- ark_common's settings.ini / session.json paths point at a throwaway sandbox folder holding a
  fake settings.ini (fake credentials, sandbox [Folders]), so the real %APPDATA% is never read.
- playwright's sync_playwright is replaced by a stub that raises, so no browser opens unless a
  test installs the fake Ark site (fake_ark fixture, see fakes.py).
- Outgoing socket connections and DNS lookups raise, so nothing can reach Ark, Enverus, BLM or Slack.
- webbrowser.open only records the URL (browser_tabs fixture), so no real browser tab opens.
- Win32 MessageBoxW is replaced by a recorder (msgboxes fixture; Yes/No boxes answer Yes unless the
  test queues msgboxes.answers), so no dialog blocks a test; so is
  Mirror's report task dialog (mirror._task_dialog; task_dialogs fixture, also recorded in msgboxes).
- mirror.RUN_IN_CHILD is False, so Mirror runs its steps in the test process (where all of the above
  applies) and never starts a real step in a child process.
- merge._show_review is replaced by a recorder (reviews fixture), so Merge's review window never opens
  and waits for a click; it answers "closed without picking" unless the test sets reviews.keep. So is
  merge._show_holdings (holdings fixture), the land holdings window: it answers "leave every land
  holding as it is" unless the test sets holdings.choose.
Fixtures: msgboxes, task_dialogs, browser_tabs, reviews, holdings, folders, fake_ark, no_real_makedirs.
A large report's Yes/No box (ark_common.confirm_download) is a message box too: it answers Yes unless the
test queues msgboxes.answers = [7], and fake_ark only hands over a report after that box lets it through.
"""
import configparser
import ctypes
import os
import pathlib
import re
import socket
import sys
import tempfile

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent  # repo root: the scripts under test
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # so tests can import fakes / buttons

SANDBOX = pathlib.Path(tempfile.mkdtemp(prefix='phx_tests_'))  # session-wide fake APPDATA and [Folders]

# Every [Folders] key a script reads; the fake settings.ini points each at a sandbox folder.
FOLDER_KEYS = ['NewlyAcquiredInterest','STRVerification', 'AOI', 'CloseDates', 'Maps', 'MirrorArchive',
               'CaseMatchup', 'NonHBPMI', 'CostToExtend', 'CaseUnitNames', 'DocketUpdates',
               'PPIQ', 'TPPLHPP', 'Deceased', 'Index', 'Organize', 'Rename', 'SIB', 'QQ', 'Merges']


# ---- Safety net, installed at import so it is active even while test modules import ----

def _blocked_sync_playwright(*args, **kwargs):
    """Stand-in for playwright's sync_playwright: refuses to open a real browser."""
    raise RuntimeError('Real browser blocked in tests (use the fake_ark fixture)')


import playwright.sync_api  # noqa: E402
playwright.sync_api.sync_playwright = _blocked_sync_playwright


def _blocked_connect(self, address, *args):
    """Stand-in for socket.connect: refuses every outgoing connection."""
    raise RuntimeError(f'Network blocked in tests: tried to connect to {address!r}')


socket.socket.connect = _blocked_connect
socket.socket.connect_ex = _blocked_connect


def _blocked_getaddrinfo(host, *args, **kwargs):
    """Stand-in for socket.getaddrinfo: refuses DNS lookups, so a blocked request doesn't even resolve the host."""
    raise RuntimeError(f'Network blocked in tests: tried to look up {host!r}')


socket.getaddrinfo = _blocked_getaddrinfo

_BROWSER_TABS = []  # URLs scripts tried to open in the default browser (webbrowser.open); browser_tabs fixture


def _fake_webbrowser_open(url, *args, **kwargs):
    """Stand-in for webbrowser.open: records the URL instead of opening the real browser."""
    _BROWSER_TABS.append(url)
    return True


import webbrowser  # noqa: E402
webbrowser.open = _fake_webbrowser_open

class _MsgBoxes(list):
    """(title, text) of every MessageBoxW call; exposed by the msgboxes fixture. answers: what the
    Yes/No boxes return, in turn (6 = Yes, 7 = No); once used up, Yes."""
    answers = []


_MSGBOXES = _MsgBoxes()  # every message box shown; msgboxes fixture
_YESNO = 0x4  # MB_YESNO in a message box's flags


def _fake_messagebox(hwnd, text, title, flags):
    """Stand-in for user32.MessageBoxW: records the box and returns IDOK without showing it (a Yes/No
    box returns the next of msgboxes.answers, else IDYES)."""
    _MSGBOXES.append((title, text))
    if flags & 0xF == _YESNO:
        return _MSGBOXES.answers.pop(0) if _MSGBOXES.answers else 6
    return 1


ctypes.windll.user32.MessageBoxW = _fake_messagebox

import ark_common  # noqa: E402  (after the playwright patch, before any script imports it)

ark_common._APP_DIR = str(SANDBOX / 'AppData' / 'PhoenixLandDept')
ark_common._INI_PATH = os.path.join(ark_common._APP_DIR, 'settings.ini')
ark_common._SESSION = os.path.join(ark_common._APP_DIR, 'session.json')
os.makedirs(ark_common._APP_DIR, exist_ok=True)

import mirror  # noqa: E402
mirror.RUN_IN_CHILD = False  # a child process would run the real steps outside this safety net

_TASK_DIALOGS = []  # (title, content with its <a href> links, icon) of every Mirror report task dialog; task_dialogs fixture


def _fake_task_dialog(title, content, icon):
    """Stand-in for mirror._task_dialog: records the dialog, and its text with the link markup taken
    out as a message box (so msgboxes sees the report either way), without showing anything."""
    _TASK_DIALOGS.append((title, content, icon))
    _MSGBOXES.append((title, re.sub(r'<a href="[^"]*">(.*?)</a>', r'\1', content)))


mirror._task_dialog = _fake_task_dialog

import merge  # noqa: E402

class _Reviews(list):
    """The accounts passed to every Merge review window; keep: what the stand-in window answers (the
    index of the account kept, or None = closed without picking)."""
    keep = None


_REVIEWS = _Reviews()  # every Merge review window shown; reviews fixture


def _fake_show_review(accounts):
    """Stand-in for merge._show_review: records the accounts and returns reviews.keep instead of opening
    the window and waiting for a click (tests build the window themselves with merge._review_window)."""
    _REVIEWS.append(accounts)
    return _REVIEWS.keep


merge._show_review = _fake_show_review


class _Holdings(list):
    """(accounts, keep) passed to every Merge land holdings window; choose(accounts, keep): what the
    stand-in window answers (choices as merge.holding_choices, or None = closed). Default: every land
    holding as it is now."""
    choose = None


_HOLDINGS = _Holdings()  # every Merge land holdings window shown; holdings fixture


def _fake_show_holdings(accounts, keep):
    """Stand-in for merge._show_holdings: records the call and answers holdings.choose(accounts, keep)
    (default: nothing changed) instead of opening the window."""
    _HOLDINGS.append((accounts, keep))
    return (_HOLDINGS.choose or (lambda a, k: merge.holding_choices(a)))(accounts, keep)


merge._show_holdings = _fake_show_holdings

_ini = configparser.ConfigParser()
_ini.optionxform = str  # keep key case, like the C++ side writes it
_ini['Credentials'] = {'username': 'test.user@example.com', 'password': 'not-a-real-password'}
_ini['EnverusCredentials'] = {'identifier': 'test.user@example.com', 'password': 'not-a-real-password'}
_ini['SlackCredentials'] = {'token': 'xoxp-not-a-real-token'}
_ini['Folders'] = {key: str(SANDBOX / 'Folders' / key) for key in FOLDER_KEYS}
_ini['Files'] = {'IndexWorkbook': str(SANDBOX / 'Files' / 'Index of Scanned Docs.xlsx'),  # never the real Box workbooks
                 'HearingDockets': str(SANDBOX / 'Files' / 'Hearing Dockets.xlsx')}
with open(ark_common._INI_PATH, 'w') as _f:
    _ini.write(_f)
for _key in FOLDER_KEYS:
    (SANDBOX / 'Folders' / _key).mkdir(parents=True, exist_ok=True)


# ---- Fixtures ----

@pytest.fixture
def msgboxes():
    """List of (title, text) for every message box a script tried to show during the test. Set
    msgboxes.answers = [7] to answer the next Yes/No box No (Yes otherwise)."""
    _MSGBOXES.clear()
    _MSGBOXES.answers = []
    yield _MSGBOXES
    _MSGBOXES.clear()
    _MSGBOXES.answers = []


@pytest.fixture
def browser_tabs():
    """List of the URLs a script opened in the default browser during the test (webbrowser.open)."""
    _BROWSER_TABS.clear()
    yield _BROWSER_TABS
    _BROWSER_TABS.clear()


@pytest.fixture
def task_dialogs():
    """List of (title, content with <a href> links, icon) for every Mirror report task dialog during the test."""
    _TASK_DIALOGS.clear()
    yield _TASK_DIALOGS
    _TASK_DIALOGS.clear()


@pytest.fixture
def reviews():
    """List of the accounts shown in each Merge review window during the test (merge._show_review).
    Set reviews.keep = 0 / 1 to pick that account to keep (default None: closed without picking)."""
    _REVIEWS.clear()
    _REVIEWS.keep = None
    yield _REVIEWS
    _REVIEWS.clear()
    _REVIEWS.keep = None


@pytest.fixture
def holdings():
    """List of (accounts, keep) of each Merge land holdings window during the test (merge._show_holdings).
    Set holdings.choose = function(accounts, keep) -> choices (or None = closed) to answer it; default:
    every land holding left as it is."""
    _HOLDINGS.clear()
    _HOLDINGS.choose = None
    yield _HOLDINGS
    _HOLDINGS.clear()
    _HOLDINGS.choose = None


class Folders:
    """Maps a [Folders] key to a per-test folder; installed over ark_common.read_folder."""

    def __init__(self, root):
        """root is the test's tmp_path; each key gets root/<key>."""
        self.root = root

    def __getitem__(self, key):
        """Path of the folder a script gets for read_folder(key)."""
        path = self.root / key
        path.mkdir(exist_ok=True)
        return path

    def read_folder(self, key, default):
        """Replacement for ark_common.read_folder (ignores the hardcoded default)."""
        return str(self[key])


@pytest.fixture
def folders(tmp_path, monkeypatch):
    """Points every ark_common.read_folder() lookup at tmp_path/<key> for this test."""
    f = Folders(tmp_path)
    monkeypatch.setattr(ark_common, 'read_folder', f.read_folder)
    return f


@pytest.fixture
def fake_ark(tmp_path_factory, monkeypatch, msgboxes):
    """A fake Ark site and Playwright browser (see fakes.FakeArk). Serve reports with
    fake_ark.serve(url, rows, filename) before calling the script."""
    from fakes import FakeArk
    ark = FakeArk(tmp_path_factory.mktemp('served'))
    ark.install(monkeypatch)
    return ark


@pytest.fixture
def no_real_makedirs(monkeypatch):
    """Makes os.makedirs a no-op, for tests that run a script with its hardcoded Desktop paths."""
    monkeypatch.setattr(os, 'makedirs', lambda *a, **k: None)
