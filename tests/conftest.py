"""Shared pytest setup for the regression tests (run `py -m pytest`; see docs/TESTING.md).

pytest loads this before any test module. At import it makes the whole run offline and harmless:
- ark_common's settings.ini / session.json paths point at a throwaway sandbox folder holding a
  fake settings.ini (fake credentials, sandbox [Folders]), so the real %APPDATA% is never read.
- playwright's sync_playwright is replaced by a stub that raises, so no browser opens unless a
  test installs the fake Ark site (fake_ark fixture, see fakes.py).
- Outgoing socket connections and DNS lookups raise, so nothing can reach Ark, Enverus, BLM or Slack.
- Win32 MessageBoxW is replaced by a recorder (msgboxes fixture), so no dialog blocks a test.
- mirror.RUN_IN_CHILD is False, so Mirror runs its steps in the test process (where all of the above
  applies) and never starts a real step in a child process.
Fixtures: msgboxes, folders, fake_ark, no_real_makedirs.
"""
import configparser
import ctypes
import os
import pathlib
import socket
import sys
import tempfile

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent  # repo root: the scripts under test
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # so tests can import fakes / buttons

SANDBOX = pathlib.Path(tempfile.mkdtemp(prefix='phx_tests_'))  # session-wide fake APPDATA and [Folders]

# Every [Folders] key a script reads; the fake settings.ini points each at a sandbox folder.
FOLDER_KEYS = ['DataMeetingDownload', 'STRVerification', 'AOI', 'CloseDates', 'Maps', 'MirrorArchive',
               'CaseMatchup', 'NonHBPMI', 'CostToExtend', 'CaseUnitNames', 'DocketUpdates',
               'PPIQ', 'TPPLHPP', 'Deceased', 'Index', 'Organize', 'Rename']


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

_MSGBOXES = []  # (title, text) of every MessageBoxW call; exposed by the msgboxes fixture


def _fake_messagebox(hwnd, text, title, flags):
    """Stand-in for user32.MessageBoxW: records the box and returns IDOK without showing it."""
    _MSGBOXES.append((title, text))
    return 1


ctypes.windll.user32.MessageBoxW = _fake_messagebox

import ark_common  # noqa: E402  (after the playwright patch, before any script imports it)

ark_common._APP_DIR = str(SANDBOX / 'AppData' / 'PhoenixLandDept')
ark_common._INI_PATH = os.path.join(ark_common._APP_DIR, 'settings.ini')
ark_common._SESSION = os.path.join(ark_common._APP_DIR, 'session.json')
os.makedirs(ark_common._APP_DIR, exist_ok=True)

import mirror  # noqa: E402
mirror.RUN_IN_CHILD = False  # a child process would run the real steps outside this safety net

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
    """List of (title, text) for every message box a script tried to show during the test."""
    _MSGBOXES.clear()
    yield _MSGBOXES
    _MSGBOXES.clear()


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
