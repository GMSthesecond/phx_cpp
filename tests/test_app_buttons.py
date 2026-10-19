"""Clicks every button in a test build of phxcpp.exe and checks it does what tests/buttons.py says.

The app is compiled into a temp folder, and next to it goes a stand-in for every script main.cpp
can launch. A stand-in only records that it ran (and, for Index, prints the progress tags the
real scripts print), so a click proves the button reaches the right script with the right
arguments without running the real thing. Dialog buttons must open their window and disable
the main window until it closes, and TODO buttons must do nothing. Organize is never clicked
because it reads and writes personal files directly; its logic is covered by test_cpp.py.
"""
import ctypes
import json
import pathlib
import subprocess
import tempfile
import time
from ctypes import wintypes

import pytest

import mirror
import msvc
from buttons import BUTTONS, COLUMN_HEADERS, COLUMNS, DIALOG, DISABLED, SCRIPT, TODO, by_label
from test_wiring import _launched_scripts

pytestmark = pytest.mark.app

_user32 = ctypes.WinDLL('user32', use_last_error=True)  # own handle: conftest replaced windll.user32.MessageBoxW
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
for _name, _res, _args in [
    ('EnumWindows', wintypes.BOOL, [_WNDENUMPROC, wintypes.LPARAM]),
    ('EnumChildWindows', wintypes.BOOL, [wintypes.HWND, _WNDENUMPROC, wintypes.LPARAM]),
    ('GetWindowThreadProcessId', wintypes.DWORD, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]),
    ('GetClassNameW', ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
    ('GetWindowTextW', ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
    ('GetDlgItemTextW', wintypes.UINT, [wintypes.HWND, ctypes.c_int, wintypes.LPWSTR, ctypes.c_int]),
    ('GetDlgItem', wintypes.HWND, [wintypes.HWND, ctypes.c_int]),
    ('GetWindowLongW', ctypes.c_long, [wintypes.HWND, ctypes.c_int]),
    ('IsWindow', wintypes.BOOL, [wintypes.HWND]),
    ('IsWindowVisible', wintypes.BOOL, [wintypes.HWND]),
    ('IsWindowEnabled', wintypes.BOOL, [wintypes.HWND]),
    ('GetWindowRect', wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]),
    ('GetClientRect', wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]),
    ('ClientToScreen', wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]),
    ('PostMessageW', wintypes.BOOL, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]),
    ('SendMessageW', ctypes.c_ssize_t, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]),
]:
    getattr(_user32, _name).restype = _res
    getattr(_user32, _name).argtypes = _args

_BM_CLICK = 0x00F5  # simulates a mouse click on a button
_WM_CLOSE = 0x0010
_WM_COMMAND = 0x0111
_IDOK = 1
_PBM_GETPOS = 0x0408  # progress bar position (WM_USER + 8)
_GWL_STYLE = -16
_BS_TYPEMASK, _BS_OWNERDRAW = 0x0F, 0x0B  # button type bits; owner-drawn = painted yellow by main.cpp
_ID_PROGRESS_INDEX, _ID_LABEL_INDEX_STATUS = 49, 50  # Index progress bar / status label ids in main.cpp
_ID_PROGRESS_MIRROR, _ID_LABEL_MIRROR_STATUS = 53, 54  # Mirror progress bar / status label ids in main.cpp
_ID_TITLE = 3  # title label id in main.cpp
_ID_COLUMN_HEADER = 55  # first column-header label id in main.cpp (one per column, consecutive)
_IDYES, _IDNO = 6, 7  # Yes / No in a message box
_ROOSEVELT_HOLD_S = 2.0  # how long the Roosevelt stand-in pauses mid-run so the progress bar can be read
_MIRROR_HOLD_S = 2.0  # how long the mirror.py stand-in pauses mid-run so the progress bar can be read
_MIRROR_CRASH_FLAG = 'mirror_crash'  # if this file is next to the stand-in, mirror.py exits without @FINISHED
_MIRROR_LONG_HOLD_FLAG = 'mirror_long_hold'  # if present, the mirror.py stand-in's first step takes 30 s (unless stopped)
_MIRROR_REPORT_FLAG = 'mirror_report_hold'  # if present, the stand-in stays alive after @FINISHED until it is removed
_MIRROR_REPORT_OPEN = 'mirror_report_open'  # written by the stand-in while it "shows its report box"
_MIRROR_SAW_STOP = 'mirror_saw_stop'  # written by the stand-in when it finds its stop file
_INDEX_COUNTS = {'doc_inventory_roosevelt.py': 3, 'doc_inventory_richland.py': 4, 'doc_inventory_divide.py': 5}
_MIRROR_STEPS = [step.name for step in mirror.STEPS]  # buttons Mirror runs (drawn green)
_LOCKED_DURING_MIRROR = ['PPIQ', 'AOI', 'DMD']  # also share the Ark login, so locked too

# Stand-in for every launched script: records its name and arguments to calls.jsonl next to it.
# The Index stand-ins also print progress tags the way the real scripts do (tag mid-line after \r),
# and the mirror.py stand-in prints Mirror's @STAGE / @PROGRESS / @FINISHED tags, ends its first step
# early when its --stop-file appears, and can stay alive after @FINISHED like the real report box.
_STAND_IN = f'''"""Test stand-in written by tests/test_app_buttons.py; records that the app launched it."""
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
name = os.path.basename(__file__)
flag = lambda f: os.path.exists(os.path.join(here, f))
with open(os.path.join(here, 'calls.jsonl'), 'a') as f:
    f.write(json.dumps({{'script': name, 'args': sys.argv[1:], 'time': time.time()}}) + '\\n')
counts = {_INDEX_COUNTS!r}
if name in counts:
    total = -1 if 'richland' in name else 2
    sys.stdout.write('\\rProcessing: 1/2 (50.0%)')
    print('@PROGRESS 1', total, flush=True)
    if 'roosevelt' in name:
        time.sleep({_ROOSEVELT_HOLD_S})
    print('@DONE', counts[name], flush=True)
if name == 'map_builder.py':
    time.sleep(1.0)
if name == 'mirror.py':
    stop_file = sys.argv[2] if sys.argv[1:2] == ['--stop-file'] else None
    print('@STAGE 0 50 Step 1 of 2: Index', flush=True)
    sys.stdout.write('\\rProcessing: 1/2 (50.0%)')
    print('@PROGRESS 1 2', flush=True)
    end = time.time() + (30 if flag({_MIRROR_LONG_HOLD_FLAG!r}) else {_MIRROR_HOLD_S})
    stopped = False
    while time.time() < end and not stopped:
        stopped = bool(stop_file) and os.path.exists(stop_file)
        time.sleep(0.05)
    if stopped:
        open(os.path.join(here, {_MIRROR_SAW_STOP!r}), 'w').close()
    else:
        print('@STAGE 50 100 Step 2 of 2: Close Date', flush=True)
    if not flag({_MIRROR_CRASH_FLAG!r}):
        report = flag({_MIRROR_REPORT_FLAG!r})
        if report:
            open(os.path.join(here, {_MIRROR_REPORT_OPEN!r}), 'w').close()
        print('@FINISHED', flush=True)
        if report:
            while flag({_MIRROR_REPORT_FLAG!r}):
                time.sleep(0.05)
            os.remove(os.path.join(here, {_MIRROR_REPORT_OPEN!r}))
'''


def _text(hwnd):
    """Window text (button label, window title)."""
    buf = ctypes.create_unicode_buffer(512)
    _user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def _class(hwnd):
    """Window class name."""
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _rect(hwnd):
    """Window rectangle in screen coordinates as (left, top, right, bottom)."""
    r = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _wait_for(condition, timeout, what):
    """Polls condition() until it returns something truthy; fails after timeout seconds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(0.05)
    pytest.fail(f'Timed out after {timeout}s waiting for {what}', pytrace=False)


class App:
    """A running test build of phxcpp.exe."""

    def __init__(self, proc, main, folder):
        """proc: the Popen; main: main window handle; folder: build folder holding the stand-ins."""
        self.proc, self.main, self.folder = proc, main, folder

    def top_windows(self):
        """Visible top-level windows of the app other than the main window."""
        found = []

        def collect(hwnd, _):
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.proc.pid and hwnd != self.main and _user32.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True
        _user32.EnumWindows(_WNDENUMPROC(collect), 0)
        return found

    def popup(self, class_name=None, title=None):
        """First visible popup matching class_name / title, or None."""
        for hwnd in self.top_windows():
            if (class_name is None or _class(hwnd) == class_name) and (title is None or _text(hwnd) == title):
                return hwnd
        return None

    def buttons(self):
        """{label: handle} of every button on the main window."""
        found = {}

        def collect(hwnd, _):
            if _class(hwnd) == 'Button':
                found[_text(hwnd)] = hwnd
            return True
        _user32.EnumChildWindows(self.main, _WNDENUMPROC(collect), 0)
        return found

    def click(self, label):
        """Clicks a button by its label."""
        _user32.PostMessageW(self.buttons()[label], _BM_CLICK, 0, 0)

    def calls(self):
        """Stand-in launches so far: [{'script', 'args', 'time'}]."""
        log = self.folder / 'calls.jsonl'
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]

    def reset(self):
        """Forgets earlier launches and closes any leftover popups."""
        (self.folder / 'calls.jsonl').unlink(missing_ok=True)
        self.close_popups()

    def close_popups(self):
        """Closes every popup and waits for the main window to be enabled again."""
        for hwnd in self.top_windows():
            _user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
        _wait_for(lambda: not self.top_windows() and _user32.IsWindowEnabled(self.main), 5,
                  'popups to close and the main window to be enabled')


@pytest.fixture(scope='module')
def app_build(tmp_path_factory):
    """Builds phxcpp.exe into a temp folder and writes a stand-in for every launched script."""
    if not msvc.available():
        pytest.skip(f'Visual Studio build tools not found at {msvc.VCVARS}')
    folder = tmp_path_factory.mktemp('app_build')
    exe, ok, log = msvc.build_app(folder)
    if not ok:
        pytest.fail(f'phxcpp.exe did not compile:\n{log}', pytrace=False)
    for script in _launched_scripts():
        (folder / script).write_text(_STAND_IN)
    return exe


@pytest.fixture(scope='module')
def app(app_build):
    """Launches the test build once for the whole module; kills it afterwards."""
    folder = app_build.parent
    # Safety: every script the app could launch must be a stand-in in the build folder.
    for script in _launched_scripts():
        assert 'Test stand-in' in (folder / script).read_text(), f'{script} is not a stand-in'
    proc = subprocess.Popen([str(app_build)], cwd=folder)

    def find_main():
        found = []

        def collect(hwnd, _):
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            # Visible only after WM_CREATE has finished creating every button
            if pid.value == proc.pid and _class(hwnd) == 'MainWindow' and _user32.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True
        _user32.EnumWindows(_WNDENUMPROC(collect), 0)
        return found[0] if found else None
    try:
        main = _wait_for(find_main, 15, 'the main window (if this always fails, Device Guard may be '
                                        'blocking exes started from a script)')
        yield App(proc, main, folder)
    finally:
        proc.kill()
        proc.wait(5)


@pytest.fixture
def running_app(app):
    """The running app with no leftover launches or popups; closes popups after the test."""
    app.reset()
    yield app
    app.close_popups()


def test_app_compiles(app_build):
    """phxcpp.exe builds from the current sources."""
    assert app_build.exists()


def test_every_button_is_shown_and_laid_out(running_app):
    """Every spec button exists, is visible, sits inside the window, and overlaps no other button.
    Unfinished buttons (yellow) and the buttons Mirror runs (green) are owner-drawn."""
    buttons = running_app.buttons()
    assert sorted(buttons) == sorted(b.label for b in BUTTONS)

    client = wintypes.RECT()
    _user32.GetClientRect(running_app.main, ctypes.byref(client))
    origin = wintypes.POINT(0, 0)
    _user32.ClientToScreen(running_app.main, ctypes.byref(origin))
    rects = {}
    for label, hwnd in buttons.items():
        assert _user32.IsWindowVisible(hwnd), f'{label} is hidden'
        left, top, right, bottom = _rect(hwnd)
        assert right - left > 20 and bottom - top > 10, f'{label} has no size (missing from LayoutControls?)'
        assert origin.x <= left and right <= origin.x + client.right, f'{label} is outside the window'
        assert origin.y <= top and bottom <= origin.y + client.bottom, f'{label} is outside the window'
        rects[label] = (left, top, right, bottom)
        owner_drawn = (_user32.GetWindowLongW(hwnd, _GWL_STYLE) & _BS_TYPEMASK) == _BS_OWNERDRAW
        assert owner_drawn == (by_label(label).kind == TODO or label in _MIRROR_STEPS), \
            f'{label}: owner-drawn only if not implemented (yellow) or run by Mirror (green)'
    labels = list(rects)
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            ra, rb = rects[a], rects[b]
            overlap = ra[0] < rb[2] and rb[0] < ra[2] and ra[1] < rb[3] and rb[1] < ra[3]
            assert not overlap, f'{a} and {b} overlap'


def test_buttons_sit_in_their_columns(running_app):
    """Each COLUMNS list in buttons.py is one column, top to bottom in the listed order, and
    the columns run left to right in the listed order."""
    buttons = running_app.buttons()
    lefts = []
    for column in COLUMNS:
        rects = [_rect(buttons[label]) for label in column]
        assert len({r[0] for r in rects}) == 1, f'{column} are not lined up in one column'
        tops = [r[1] for r in rects]
        assert tops == sorted(tops), f'column order should be {column}'
        lefts.append(rects[0][0])
    assert lefts == sorted(lefts) and len(set(lefts)) == len(lefts), 'columns are out of order'


def test_each_column_has_its_header(running_app):
    """Each column has a visible COLUMN_HEADERS label right above its first button, within
    the column's width and below the Mirror button and the title."""
    buttons = running_app.buttons()
    mirror_bottom = _rect(buttons['Mirror'])[3]
    title_bottom = _rect(_user32.GetDlgItem(running_app.main, _ID_TITLE))[3]
    for i, (header, column) in enumerate(zip(COLUMN_HEADERS, COLUMNS)):
        hwnd = _user32.GetDlgItem(running_app.main, _ID_COLUMN_HEADER + i)
        assert hwnd and _class(hwnd) == 'Static', f'no header label for column {i + 1}'
        assert _text(hwnd) == header
        assert _user32.IsWindowVisible(hwnd), f'{header} is hidden'
        left, top, right, bottom = _rect(hwnd)
        first = _rect(buttons[column[0]])
        assert first[0] <= left and right <= first[2], f'{header} is not over its column'
        assert bottom <= first[1] and first[1] - bottom <= 10, f'{header} is not right above {column[0]}'
        assert top >= max(mirror_bottom, title_bottom), f'{header} overlaps the Mirror button or the title'


@pytest.mark.parametrize('label', [b.label for b in BUTTONS if b.kind == SCRIPT])
def test_script_button_launches_its_script(running_app, label):
    """The click launches exactly the spec script and arguments, with no error box."""
    script, *args = by_label(label).target
    running_app.click(label)
    calls = _wait_for(running_app.calls, 10, f'{label} to launch {script}')
    time.sleep(0.3)  # catch a second, unexpected launch
    assert [(c['script'], c['args']) for c in running_app.calls()] == [(script, args)]
    assert running_app.top_windows() == [], f'{label} showed a window: {[_text(h) for h in running_app.top_windows()]}'


def test_index_runs_each_county_and_reports_counts(running_app):
    """Index runs the three county scripts in order, moves the progress bar from their
    @PROGRESS tags, and its summary shows each script's @DONE count."""
    app = running_app
    progress = _user32.GetDlgItem(app.main, _ID_PROGRESS_INDEX)
    status = _user32.GetDlgItem(app.main, _ID_LABEL_INDEX_STATUS)
    app.click('Index')

    _wait_for(lambda: _text(status) == 'Roosevelt: 1 / 2', _ROOSEVELT_HOLD_S + 5, 'status "Roosevelt: 1 / 2"')
    assert _user32.IsWindowVisible(progress)
    assert _user32.SendMessageW(progress, _PBM_GETPOS, 0, 0) == 50
    assert not _user32.IsWindowEnabled(app.buttons()['Roosevelt']), 'Index button should be disabled while running'

    box = _wait_for(lambda: app.popup('#32770', 'Index Complete'), 20, 'the Index Complete message box')
    text = ctypes.create_unicode_buffer(512)
    _user32.GetDlgItemTextW(box, 0xFFFF, text, 512)  # 0xFFFF = a message box's text control
    assert 'Roosevelt: 3' in text.value and 'Richland: 4' in text.value and 'Divide: 5' in text.value
    assert [c['script'] for c in app.calls()] == list(by_label('Index').target)
    _user32.PostMessageW(box, _WM_COMMAND, _IDOK, 0)
    _wait_for(lambda: 'Index' in app.buttons() and _user32.IsWindowEnabled(app.buttons()['Index']), 5,
              'the Index button to come back')
    assert not _user32.IsWindowVisible(progress)


def test_map_builds_then_uploads(running_app):
    """Maps runs map_builder.py to completion, then map_uploader.py, relabeling its button meanwhile."""
    app = running_app
    app.click('Maps')
    _wait_for(lambda: 'Building...' in app.buttons(), 5, 'the Maps button to read "Building..."')
    _wait_for(lambda: len(app.calls()) == 2, 10, 'both map scripts to run')
    builder, uploader = app.calls()
    assert (builder['script'], uploader['script']) == tuple(by_label('Maps').target)
    assert uploader['time'] - builder['time'] >= 0.9, 'uploader started before the builder finished'
    _wait_for(lambda: 'Maps' in app.buttons() and _user32.IsWindowEnabled(app.buttons()['Maps']), 10,
              'the Maps button to come back')


@pytest.mark.parametrize('label', [b.label for b in BUTTONS if b.kind == DIALOG])
def test_dialog_button_opens_its_window(running_app, label):
    """The click opens the dialog, the main window is disabled until it closes, and no script runs."""
    app = running_app
    app.click(label)
    dialog = _wait_for(lambda: app.popup(by_label(label).target), 5, f'the {label} window')
    assert not _user32.IsWindowEnabled(app.main), f'main window should be disabled while {label} is open'
    _user32.PostMessageW(dialog, _WM_CLOSE, 0, 0)
    _wait_for(lambda: not _user32.IsWindow(dialog) and _user32.IsWindowEnabled(app.main), 5,
              f'{label} to close and the main window to be enabled')
    assert app.calls() == []


def test_unfinished_buttons_do_nothing(running_app):
    """Clicking a yellow (TODO) button launches nothing and opens nothing."""
    for b in BUTTONS:
        if b.kind == TODO:
            running_app.click(b.label)
    time.sleep(0.5)
    assert running_app.calls() == []
    assert running_app.top_windows() == []


def test_greyed_out_buttons_are_disabled_and_do_nothing(running_app):
    """A DISABLED button (g_disabledButtonIds) is shown greyed out and a click launches nothing."""
    buttons = running_app.buttons()
    disabled = [b.label for b in BUTTONS if b.kind == DISABLED]
    for label in disabled:
        assert not _user32.IsWindowEnabled(buttons[label]), f'{label} should be greyed out'
        assert _user32.IsWindowVisible(buttons[label]), f'{label} should still be shown'
        running_app.click(label)
    time.sleep(0.5)
    assert running_app.calls() == []
    assert running_app.top_windows() == []
    others = [b.label for b in BUTTONS if b.kind != DISABLED and b.label != 'Mirror']
    assert all(_user32.IsWindowEnabled(buttons[label]) for label in others), 'only DISABLED buttons start greyed out'


def _box_text(box):
    """The message text of a message box."""
    text = ctypes.create_unicode_buffer(1024)
    _user32.GetDlgItemTextW(box, 0xFFFF, text, 1024)  # 0xFFFF = a message box's text control
    return text.value


def _mirror_box(app, containing):
    """Waits for a message box titled Mirror whose text contains `containing`."""
    def find():
        box = app.popup('#32770', 'Mirror')
        return box if box and containing in _box_text(box) else None
    return _wait_for(find, 10, f'a Mirror message box saying "{containing}"')


def test_mirror_asks_first_and_no_runs_nothing(running_app):
    """Mirror's confirmation lists the steps and the ones that upload; No launches nothing."""
    app = running_app
    app.click('Mirror')
    box = _mirror_box(app, 'Start now?')
    text = _box_text(box)
    assert ', '.join(_MIRROR_STEPS) in text
    uploaders = ', '.join(step.name for step in mirror.STEPS if step.uploads)
    assert f'These upload to Ark (live data):\n{uploaders}' in text
    _user32.PostMessageW(box, _WM_COMMAND, _IDNO, 0)
    _wait_for(lambda: not app.top_windows(), 5, 'the confirmation to close')
    time.sleep(0.5)
    assert app.calls() == []


def test_mirror_runs_with_progress_and_restores_buttons(running_app):
    """Yes runs mirror.py with a stop file in %TEMP%; the bar and status follow its tags, Mirror reads Stop,
    its steps and the other buttons sharing the Ark login are disabled meanwhile (the rest are not), and
    everything comes back when it ends."""
    app = running_app
    progress = _user32.GetDlgItem(app.main, _ID_PROGRESS_MIRROR)
    status = _user32.GetDlgItem(app.main, _ID_LABEL_MIRROR_STATUS)
    app.click('Mirror')
    _user32.PostMessageW(_mirror_box(app, 'Start now?'), _WM_COMMAND, _IDYES, 0)

    _wait_for(lambda: _text(status).startswith('Step 1 of 2: Index: 1 / 2 - '), _MIRROR_HOLD_S + 5,
              'status "Step 1 of 2: Index: 1 / 2"')
    assert _text(status).endswith(' elapsed')
    assert _user32.IsWindowVisible(progress)
    assert _user32.SendMessageW(progress, _PBM_GETPOS, 0, 0) == 25
    buttons = app.buttons()
    assert 'Mirror' not in buttons and _user32.IsWindowEnabled(buttons['Stop']), 'Mirror should read Stop while running'
    for name in _MIRROR_STEPS + _LOCKED_DURING_MIRROR:
        assert not _user32.IsWindowEnabled(buttons[name]), f'{name} should be disabled while Mirror runs'
    assert _user32.IsWindowEnabled(buttons['Unit Connect to Cases']), 'buttons that don\'t use the Ark login stay usable'

    _wait_for(lambda: 'Mirror' in app.buttons() and _user32.IsWindowEnabled(app.buttons()['Mirror']), 10,
              'the Mirror button to come back')
    assert not _user32.IsWindowVisible(progress)
    assert all(_user32.IsWindowEnabled(app.buttons()[name]) for name in _MIRROR_STEPS + _LOCKED_DURING_MIRROR)
    assert app.top_windows() == [], 'a finished run shows no error box (mirror.py shows the report itself)'
    [call] = app.calls()
    assert call['script'] == 'mirror.py'
    assert call['args'][0] == '--stop-file' and len(call['args']) == 2
    stop_file = pathlib.Path(call['args'][1])
    assert stop_file.parent.resolve() == pathlib.Path(tempfile.gettempdir()).resolve()
    assert stop_file.name.startswith('phx_mirror_stop_') and not stop_file.exists()


def _start_mirror(app):
    """Clicks Mirror, answers Yes, and waits for this run's first @PROGRESS in the status label (an
    earlier run's text stays in the hidden label, but ends on step 2 or starts with "Stopping...")."""
    status = _user32.GetDlgItem(app.main, _ID_LABEL_MIRROR_STATUS)
    app.click('Mirror')
    _user32.PostMessageW(_mirror_box(app, 'Start now?'), _WM_COMMAND, _IDYES, 0)
    _wait_for(lambda: 'Stop' in app.buttons() and _text(status).startswith('Step 1 of 2: Index: 1 / 2 - '), 10,
              'Mirror\'s first step to start')


def _mirror_back(app):
    """True once the Mirror button is back and enabled."""
    return 'Mirror' in app.buttons() and _user32.IsWindowEnabled(app.buttons()['Mirror'])


def test_mirror_stop_asks_then_stops_the_run(running_app):
    """Stop asks first (No keeps it running); Yes creates the stop file, mirror.py sees it and finishes
    early, and the buttons come back without an error box."""
    app = running_app
    hold = app.folder / _MIRROR_LONG_HOLD_FLAG
    hold.write_text('')
    (app.folder / _MIRROR_SAW_STOP).unlink(missing_ok=True)
    try:
        _start_mirror(app)
        started = time.time()
        app.click('Stop')
        box = _mirror_box(app, 'Stop Mirror?')
        assert '(Step 1 of 2: Index)' in _box_text(box)
        _user32.PostMessageW(box, _WM_COMMAND, _IDNO, 0)
        _wait_for(lambda: not app.top_windows(), 5, 'the Stop question to close')
        time.sleep(0.5)
        assert 'Stop' in app.buttons() and not (app.folder / _MIRROR_SAW_STOP).exists(), 'No must not stop it'

        app.click('Stop')
        _user32.PostMessageW(_mirror_box(app, 'Stop Mirror?'), _WM_COMMAND, _IDYES, 0)
        _wait_for(lambda: _mirror_back(app), 10, 'the Mirror button to come back after Stop')
        assert time.time() - started < 20, 'the stand-in ran its full 30 s: the Stop did not reach it'
        assert (app.folder / _MIRROR_SAW_STOP).exists()
        time.sleep(0.5)
        assert app.top_windows() == [], 'a stopped run that reported shows no error box'
    finally:
        hold.unlink()


def test_mirror_buttons_come_back_while_its_report_is_open(running_app):
    """The buttons are restored at @FINISHED, not when mirror.py exits, so a report box left open
    (or hidden behind another window) doesn't keep Mirror and its steps locked."""
    app = running_app
    report = app.folder / _MIRROR_REPORT_FLAG
    report.write_text('')
    try:
        _start_mirror(app)
        _wait_for(lambda: _mirror_back(app), 10, 'the Mirror button to come back')
        assert (app.folder / _MIRROR_REPORT_OPEN).exists(), 'mirror.py should still be showing its report'
        assert all(_user32.IsWindowEnabled(app.buttons()[name]) for name in _MIRROR_STEPS + _LOCKED_DURING_MIRROR)
    finally:
        report.unlink()
    _wait_for(lambda: not (app.folder / _MIRROR_REPORT_OPEN).exists(), 5, 'the stand-in to close its "report"')
    time.sleep(0.3)
    assert app.top_windows() == [], 'mirror.py exiting after @FINISHED shows no error box'


def test_mirror_reports_a_run_that_stops_early(running_app):
    """If mirror.py exits without reaching @FINISHED, Mirror says so (there is no report)."""
    app = running_app
    flag = app.folder / _MIRROR_CRASH_FLAG
    flag.write_text('')
    try:
        app.click('Mirror')
        _user32.PostMessageW(_mirror_box(app, 'Start now?'), _WM_COMMAND, _IDYES, 0)
        box = _mirror_box(app, 'stopped before it finished')
        _user32.PostMessageW(box, _WM_COMMAND, _IDOK, 0)
        _wait_for(lambda: 'Mirror' in app.buttons() and _user32.IsWindowEnabled(app.buttons()['Mirror']), 5,
                  'the Mirror button to come back')
    finally:
        flag.unlink()


def test_mirror_waits_for_a_running_step(running_app):
    """While Index is running on its own, Mirror refuses to start instead of running it twice."""
    app = running_app
    app.click('Index')
    _wait_for(lambda: 'Roosevelt' in app.buttons(), 5, 'Index to start')
    app.click('Mirror')
    box = _mirror_box(app, 'still busy')
    _user32.PostMessageW(box, _WM_COMMAND, _IDOK, 0)
    done = _wait_for(lambda: app.popup('#32770', 'Index Complete'), 20, 'the Index Complete message box')
    _user32.PostMessageW(done, _WM_COMMAND, _IDOK, 0)
    _wait_for(lambda: 'Index' in app.buttons() and _user32.IsWindowEnabled(app.buttons()['Index']), 5,
              'the Index button to come back')
    assert 'mirror.py' not in [c['script'] for c in app.calls()]
