"""Mirror button (mirror.py): runs several buttons' work in a row and reports what each did.

Most tests swap mirror.STEPS for small fake steps, so they check the runner itself: the
@STAGE progress tags main.cpp reads, carrying on after a failure, the report's grouping, the
dated archive file, the final message box and a step failed by a refused large download. conftest keeps the steps in
this process (mirror.RUN_IN_CHILD = False); the child-process runner and its time limit (paused while a
large-download box waits) are tested with
harmless `python -c` children, and so is the Stop button's stop file (remaining steps Not run, the
running child's process tree killed). The Index step is tested with the county scripts' main() replaced.
One test runs the real Ark steps end to end against the fake Ark site.
"""
import re
import subprocess
import sys
import threading
import time
from datetime import date, datetime

import pytest

import ark_common
import case_unit_names
import close_dates
import cost_to_extend
import docket_updates_slack
import mirror
import non_hbp_mi
import section_id_blank
import str_verification
import tpp_lhpp
from buttons import by_label
from fakes import Recorder


@pytest.fixture(autouse=True)
def no_stop_file(monkeypatch):
    """Each test starts with no Stop file, and one a test's main() set doesn't leak into the next."""
    monkeypatch.setattr(mirror, '_stop_file', None)


def _step(name, result=None, error=None, log=None):
    """A fake Mirror step that records its run in log, then returns result or raises error."""
    def run():
        if log is not None:
            log.append(name)
        if error is not None:
            raise error
        return result
    return mirror.Step(name, run, uploads=False)


def _stages(stdout):
    """[(lo, hi, label)] from the @STAGE lines, parsed the way main.cpp's ApplyMirrorLine does."""
    return [(int(m[1]), int(m[2]), m[3]) for m in re.finditer(r'@STAGE (\d+) (\d+) (.*)', stdout)]


def _report_path(folders, day=None):
    """Where Mirror archives a run started on day (default today)."""
    return folders['MirrorArchive'] / f'Mirror {(day or date.today()):%m.%d.%Y}.txt'


def test_runs_steps_in_order_and_reports_each(folders, monkeypatch, msgboxes, capsys):
    """Each step runs once, in order; the report groups them Uploaded, Needs review, No changes; it is
    archived and shown in one message box."""
    log = []
    monkeypatch.setattr(mirror, 'STEPS', [
        _step('Close Date', (ark_common.UPLOADED, 'Uploaded close dates for 4 landholdings'), log=log),
        _step('STR', (ark_common.NOTHING, 'No STR errors found'), log=log),
        _step('TPP-LHPP', (ark_common.REVIEW, '2 price mismatches closing in the next two weeks'), log=log),
        _step('C2E', (ark_common.UPLOADED, 'Uploaded fixes for 1 landholding'), log=log),
    ])

    mirror.main()

    assert log == ['Close Date', 'STR', 'TPP-LHPP', 'C2E']
    report = _report_path(folders).read_text(encoding='utf-8')
    assert report.splitlines()[1:] == [
        '',
        'Uploaded',
        '  Close Date: Uploaded close dates for 4 landholdings',
        '  C2E: Uploaded fixes for 1 landholding',
        '',
        'Needs review',
        '  TPP-LHPP: 2 price mismatches closing in the next two weeks',
        '',
        'No changes',
        '  STR: No STR errors found',
    ]
    assert report.startswith('Mirror run ')
    [(title, text)] = msgboxes
    assert title == 'Mirror'
    assert text == report.rstrip('\n') + f'\n\nSaved to {_report_path(folders)}'


@pytest.mark.parametrize('result, error, last_line', [
    ((ark_common.REVIEW, '3 rows in the error report: review AOI 11.10.2026.csv'), None,
     'AOI: 3 rows in the error report: review AOI 11.10.2026.csv'),
    ((ark_common.NOTHING, 'No rows in the error report (AOI 11.10.2026.csv)'), None,
     'AOI: No rows in the error report (AOI 11.10.2026.csv)'),
    (None, RuntimeError('Timeout'), 'AOI: Failed: RuntimeError: Timeout'),
])
def test_a_report_last_step_ends_the_report(folders, monkeypatch, msgboxes, capsys, result, error, last_line):
    """A report_last step (AOI) is left out of the result groups and gets the report's last line,
    whatever its result; a failure still says Failed and turns the box's icon to a warning."""
    monkeypatch.setattr(mirror, 'STEPS', [
        _step('STR', (ark_common.REVIEW, '1 Section Name mismatch: review Error_Report.csv')),
        mirror.Step('AOI', _step('AOI', result, error).run, uploads=False, report_last=True),
        _step('C2E', (ark_common.NOTHING, 'Nothing to fix')),
    ])
    flags = []
    monkeypatch.setattr(mirror, '_show', lambda text, icon, links=(): flags.append(icon))

    mirror.main()

    lines = _report_path(folders).read_text(encoding='utf-8').splitlines()
    assert lines[1:] == [
        '', 'Needs review', '  STR: 1 Section Name mismatch: review Error_Report.csv',
        '', 'No changes', '  C2E: Nothing to fix',
        '', last_line,
    ]
    assert flags == [mirror._MB_ICONWARNING if error else mirror._MB_ICONINFORMATION]


def test_a_report_last_step_skipped_by_stop_says_not_run(folders, monkeypatch, msgboxes, capsys, tmp_path):
    """After a Stop, the AOI line at the end says it didn't run."""
    stop = tmp_path / 'stop.flag'

    def first():
        """Clicks Stop while the first step runs."""
        stop.write_text('')
        return ark_common.NOTHING, 'done'
    monkeypatch.setattr(mirror, 'STEPS', [mirror.Step('STR', first, uploads=False),
                                          mirror.Step('AOI', lambda: None, uploads=False, report_last=True)])

    mirror.main(str(stop))

    lines = _report_path(folders).read_text(encoding='utf-8').splitlines()
    assert lines[-1] == 'AOI: Not run: Skipped because Mirror was stopped'
    assert '  AOI: Skipped because Mirror was stopped' not in lines


def test_progress_tags_split_the_bar_between_steps(folders, monkeypatch, msgboxes, capsys):
    """Each step gets an equal share of the bar, then "@FINISHED" comes before the message box."""
    monkeypatch.setattr(mirror, 'STEPS', [_step(n, (ark_common.NOTHING, 'ok')) for n in ('A', 'B', 'C')])

    mirror.main()

    out = capsys.readouterr().out
    assert _stages(out) == [(0, 33, 'Step 1 of 3: A'), (33, 66, 'Step 2 of 3: B'), (66, 100, 'Step 3 of 3: C'),
                            (100, 100, 'Finished')]
    assert out.rstrip().endswith('@FINISHED')


def test_a_failed_step_is_reported_last_and_the_rest_still_run(folders, monkeypatch, msgboxes, capsys):
    """An error or a sys.exit in one step doesn't stop the run; failures are listed at the end with their
    reason, and the message box uses the warning icon."""
    log = []
    monkeypatch.setattr(mirror, 'STEPS', [
        _step('Index', error=SystemExit('Excel file not found: x.xlsx'), log=log),
        _step('Close Date', error=RuntimeError('Timeout 120000ms exceeded.\nCall log:\n  - waiting'), log=log),
        _step('Case Update', (ark_common.UPLOADED, "Updated 3 units to today's date"), log=log),
    ])
    flags = []
    monkeypatch.setattr(mirror, '_show', lambda text, icon, links=(): flags.append(icon))

    mirror.main()

    assert log == ['Index', 'Close Date', 'Case Update']
    lines = _report_path(folders).read_text(encoding='utf-8').splitlines()
    assert lines[-4:] == [
        '',
        'Failed',
        '  Index: Excel file not found: x.xlsx',
        '  Close Date: RuntimeError: Timeout 120000ms exceeded.',
    ]
    assert flags == [mirror._MB_ICONWARNING]


def test_a_large_download_said_no_to_fails_only_that_step(folders, monkeypatch, fake_ark, msgboxes, capsys):
    """A step whose large report the user refused in the Yes/No box is Failed with the count and link
    (and downloads nothing); a step whose large report was allowed downloads it; the rest still run."""
    big, bigger = ('https://ark.phoenixenergy.com/report?recordId=big',
                   'https://ark.phoenixenergy.com/report?recordId=bigger')
    fake_ark.serve(big, [['Id'], ['1']], records=10_500)
    fake_ark.serve(bigger, [['Id'], ['1']], records=286_722)

    def downloads(url):
        """A step run() that downloads url."""
        def run():
            with ark_common.ark_page(url) as page:
                ark_common.trigger_download(page, url)
            return ark_common.NOTHING, 'ok'
        return run
    monkeypatch.setattr(mirror, 'STEPS', [
        mirror.Step('TPP-LHPP', downloads(big), uploads=False),
        _step('STR', (ark_common.NOTHING, 'No STR errors found')),
        mirror.Step('C2E', downloads(bigger), uploads=True),
    ])
    msgboxes.answers = [6, 7]  # Yes for TPP-LHPP's report, No for C2E's

    mirror.main()

    lines = _report_path(folders).read_text(encoding='utf-8').splitlines()
    assert '  TPP-LHPP: ok' in lines and '  STR: No STR errors found' in lines
    assert lines[-2:] == ['Failed', f'  C2E: Large download cancelled: 286,722 records, {bigger}']
    assert fake_ark.downloads == [big]
    assert [title for title, _ in msgboxes] == ['Large Ark download', 'Large Ark download', 'Mirror']


def _link(target):
    """Task-dialog markup for a clickable link to target."""
    return f'<a href="{target}">{target}</a>'


def test_report_links_and_archive_path_are_clickable(folders, monkeypatch, msgboxes, task_dialogs, capsys, tmp_path):
    """The report opens in a task dialog where each web link in a step's line (e.g. a cancelled large
    report's) and the archive path are links; the text is otherwise the report (and the archive still
    has plain text)."""
    urls = ['https://ark.phoenixenergy.com/report?recordId=big', 'https://ark.phxcapitalgroup.com/report?recordId=b2']

    def run():
        """A step whose line names two reports."""
        return ark_common.REVIEW, f'Check 10,500 records, {urls[0]}; 10,500 records, {urls[1]}'
    monkeypatch.setattr(mirror, 'STEPS', [mirror.Step('PPIQ', run, uploads=False)])

    mirror.main()

    [(title, content, icon)] = task_dialogs
    archive = str(_report_path(folders))
    assert (title, icon) == ('Mirror', mirror._MB_ICONINFORMATION)
    assert (f'10,500 records, {_link(urls[0])}; 10,500 records, {_link(urls[1])}' in content)
    assert content.endswith(f'Saved to {_link(archive)}')
    assert '<a ' not in _report_path(folders).read_text(encoding='utf-8')
    assert msgboxes[0][1].endswith(f'Saved to {archive}')  # same text once the links are taken out


@pytest.mark.parametrize('text, expected', [
    ('see https://x.com/r?recordId=1.', f'see {_link("https://x.com/r?recordId=1")}.'),       # sentence end
    ('(https://x.com/a)', f'({_link("https://x.com/a")})'),                                   # in brackets
    ('a https://x.com/a, b http://y.com/b;', f'a {_link("https://x.com/a")}, b {_link("http://y.com/b")};'),
    ('No links here: C2E ok', 'No links here: C2E ok'),
])
def test_with_links_wraps_urls_without_their_punctuation(text, expected):
    """Each web link becomes a link; punctuation after it stays text."""
    assert mirror._with_links(text) == expected


def test_with_links_wraps_a_given_path_with_spaces_and_dots():
    """A path passed in links is linked whole (spaces, dots and all); None (archive not saved) is ignored."""
    path = r'C:\Users\Me\Desktop\Dailies\Archive\Mirror 11.03.2026.txt'
    assert mirror._with_links(f'Saved to {path}', [path, None]) == f'Saved to {_link(path)}'


def test_report_falls_back_to_a_message_box_when_the_task_dialog_cannot_open(monkeypatch, msgboxes):
    """If Windows won't show the task dialog, the plain report goes in the old topmost message box."""
    def refuse(title, content, icon):
        raise OSError('no Common Controls 6')
    monkeypatch.setattr(mirror, '_task_dialog', refuse)
    shown = []
    monkeypatch.setattr(mirror.ctypes.windll.user32, 'MessageBoxW',
                        lambda hwnd, text, title, flags: shown.append((text, title, flags)))

    mirror._show('Report https://x.com/a', mirror._MB_ICONWARNING, links=['C:\\a.txt'])

    assert shown == [('Report https://x.com/a', 'Mirror', mirror._MB_ICONWARNING | mirror._MB_TOPMOST)]


def test_clicking_a_link_opens_it(monkeypatch):
    """The dialog's link-click notification opens that link (browser or file); other notifications
    don't, and a link that won't open doesn't break the dialog."""
    opened = []
    monkeypatch.setattr(mirror.os, 'startfile', opened.append)
    href = mirror.ctypes.create_unicode_buffer('https://ark.phoenixenergy.com/report?recordId=big')
    address = mirror.ctypes.addressof(href)

    assert mirror._on_dialog_event(None, mirror._TDN_HYPERLINK_CLICKED, 0, address, 0) == 0
    assert mirror._on_dialog_event(None, 2, 0, address, 0) == 0  # TDN_BUTTON_CLICKED: nothing to open
    assert opened == ['https://ark.phoenixenergy.com/report?recordId=big']

    def fail(target):
        raise OSError('no program for it')
    monkeypatch.setattr(mirror.os, 'startfile', fail)
    assert mirror._on_dialog_event(None, mirror._TDN_HYPERLINK_CLICKED, 0, address, 0) == 0


@pytest.mark.skipif(sys.maxsize <= 2**32, reason='offsets measured for 64-bit Python')
def test_task_dialog_structs_match_the_windows_headers():
    """TASKDIALOGCONFIG is byte-packed in commctrl.h; a wrong layout crashes the dialog. Sizes and
    offsets as MSVC's headers give them on 64-bit (measured 11/3/2026)."""
    cfg, ctx = mirror._TaskDialogConfig, mirror._ActCtx
    assert mirror.ctypes.sizeof(cfg) == 160
    assert {name: getattr(cfg, name).offset for name in (
        'hwndParent', 'dwFlags', 'pszWindowTitle', 'pszContent', 'cButtons', 'pButtons', 'nDefaultButton',
        'pszFooter', 'pfCallback', 'lpCallbackData', 'cxWidth')} == {
        'hwndParent': 4, 'dwFlags': 20, 'pszWindowTitle': 28, 'pszContent': 52, 'cButtons': 60, 'pButtons': 64,
        'nDefaultButton': 72, 'pszFooter': 132, 'pfCallback': 140, 'lpCallbackData': 148, 'cxWidth': 156}
    assert (mirror.ctypes.sizeof(ctx), ctx.lpSource.offset, ctx.hModule.offset) == (56, 8, 48)


@pytest.mark.parametrize('error, expected', [
    (RuntimeError('first line\nsecond line'), 'RuntimeError: first line'),
    (KeyError('Credentials'), "KeyError: 'Credentials'"),
    (TimeoutError(), 'TimeoutError'),
    (SystemExit(1), 'stopped (exit code 1)'),
    (SystemExit('Sheet missing'), 'Sheet missing'),
    (ValueError('x' * 500), 'ValueError: ' + 'x' * (mirror._MAX_ERROR - 13) + '…'),
])
def test_error_text(error, expected):
    """A failure is summed up in one short line."""
    assert mirror._error_text(error) == expected


def test_a_second_run_the_same_day_is_appended(folders, monkeypatch, msgboxes, capsys):
    """Both runs stay in the day's file, separated by a rule."""
    monkeypatch.setattr(mirror, 'STEPS', [_step('A', (ark_common.NOTHING, 'first'))])
    mirror.main()
    monkeypatch.setattr(mirror, 'STEPS', [_step('A', (ark_common.NOTHING, 'second'))])
    mirror.main()

    text = _report_path(folders).read_text(encoding='utf-8')
    assert text.count('Mirror run ') == 2
    assert text.index('A: first') < text.index(mirror._RUN_SEPARATOR) < text.index('A: second')


def test_report_still_shows_when_the_archive_cannot_be_written(folders, monkeypatch, msgboxes, capsys):
    """If the archive folder can't be created, the message box says so instead of crashing."""
    blocker = folders.root / 'not_a_folder'
    blocker.write_text('a file where the folder should be')
    monkeypatch.setattr(ark_common, 'read_folder', lambda key, default: str(blocker / 'Archive'))
    monkeypatch.setattr(mirror, 'STEPS', [_step('A', (ark_common.NOTHING, 'ok'))])

    mirror.main()

    [(_, text)] = msgboxes
    assert 'A: ok' in text and 'Could not save the report' in text


def test_archive_defaults_to_desktop_dailies_archive(monkeypatch):
    """With no [Folders] MirrorArchive setting the report goes to Desktop\\Dailies\\Archive."""
    asked = []
    monkeypatch.setattr(ark_common, 'read_folder', lambda key, default: asked.append((key, default)) or default)
    assert mirror._archive_path(datetime(2026, 10, 8, 7, 30)) == \
        r'C:\Users\Ethan Mesecher\Desktop\Dailies\Archive\Mirror 10.08.2026.txt'
    assert asked == [('MirrorArchive', r'C:\Users\Ethan Mesecher\Desktop\Dailies\Archive')]


def test_report_header_has_start_time_and_duration():
    """The first line says when the run started and how long it took."""
    report = mirror.build_report([('A', ark_common.NOTHING, 'ok')],
                                 datetime(2026, 10, 8, 7, 5), datetime(2026, 10, 8, 7, 23, 40))
    assert report.splitlines()[0] == 'Mirror run 10/08/2026 7:05 AM (took 18 min)'
    short = mirror.build_report([], datetime(2026, 10, 8, 13, 0), datetime(2026, 10, 8, 13, 0, 42))
    assert short.splitlines()[0] == 'Mirror run 10/08/2026 1:00 PM (took 42 s)'


# ---- Child processes and the time limit ----

def _py(code):
    """A command running a small, harmless Python snippet in a child process."""
    return [sys.executable, '-c', code]


def test_child_result_is_returned_and_its_other_lines_pass_through(capsys):
    """The child's @RESULT line becomes the step's result; every other line (e.g. @PROGRESS for
    main.cpp's bar) is printed on by Mirror."""
    code = "print('@PROGRESS 1 2'); print('working'); print('@RESULT Uploaded\\tUploaded 3 things')"
    assert mirror._run_in_child(_py(code), 30) == (ark_common.UPLOADED, 'Uploaded 3 things')
    assert capsys.readouterr().out.splitlines() == ['@PROGRESS 1 2', 'working']


def test_a_step_past_the_time_limit_is_stopped_with_its_children(tmp_path, capsys):
    """A hung step is stopped at the limit, including processes it started (like Chromium), and
    reported as failed; Mirror then carries on."""
    pid_file = tmp_path / 'grandchild.pid'
    code = ("import subprocess, sys, time; "
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            f"open(r'{pid_file}', 'w').write(str(p.pid)); print('started', flush=True); time.sleep(60)")
    started = time.monotonic()
    kind, message = mirror._run_in_child(_py(code), 3)
    assert time.monotonic() - started < 20
    assert (kind, message) == (mirror.FAILED, 'Stopped: still running after 0 min')
    grandchild = int(pid_file.read_text())
    alive = subprocess.run(['tasklist', '/FI', f'PID eq {grandchild}', '/NH'], capture_output=True, text=True).stdout
    assert str(grandchild) not in alive, 'the hung step\'s own child process was left running'


def test_time_spent_on_a_large_download_box_does_not_count(monkeypatch, capsys):
    """While the child waits on a large-download Yes/No box (between @WAITING and @RESUMED) its time
    limit is paused, so a slow answer doesn't get the step killed; the progress label says it's waiting
    meanwhile, and the two tags themselves aren't passed on to main.cpp."""
    monkeypatch.setattr(mirror, '_stage', (10, 20, 'Step 2 of 9: PPIQ'))
    code = ("import time; print('@WAITING', flush=True); time.sleep(4); print('@RESUMED', flush=True); "
            "print('@RESULT No changes\\tok', flush=True)")
    assert mirror._run_in_child(_py(code), 2) == (ark_common.NOTHING, 'ok')
    assert capsys.readouterr().out.splitlines() == [
        '@STAGE 10 20 Step 2 of 9: PPIQ: waiting for your answer (large download)',
        '@STAGE 10 20 Step 2 of 9: PPIQ']


def test_the_time_limit_runs_again_after_the_box_is_answered(capsys):
    """Once the box is answered the step's time limit applies again (only the wait was taken off)."""
    code = ("import time; print('@WAITING', flush=True); print('@RESUMED', flush=True); time.sleep(60)")
    started = time.monotonic()
    assert mirror._run_in_child(_py(code), 2) == (mirror.FAILED, 'Stopped: still running after 0 min')
    assert time.monotonic() - started < 20


def test_a_child_that_crashes_is_failed_with_its_last_words(capsys):
    """A child that ends without @RESULT (e.g. a missing package at import) fails with its last output line."""
    kind, message = mirror._run_in_child(_py("import no_such_package_xyz"), 30)
    assert kind == mirror.FAILED
    assert message.startswith('stopped without a result (') and 'no_such_package_xyz' in message


def test_child_main_runs_the_step_and_prints_one_result_line(monkeypatch, capsys):
    """What a step's child process prints: its own output, then "@RESULT <kind>\t<line>" (one line,
    even if the step's message had several)."""
    monkeypatch.setattr(mirror, 'STEPS', [_step('A', (ark_common.REVIEW, 'two\nlines'))])
    mirror._child_main(0, 0, 50, 'Step 1 of 2: A')
    assert capsys.readouterr().out == '@RESULT Needs review\ttwo lines\n'
    assert mirror._stage == (0, 50, 'Step 1 of 2: A')  # Index counties split this slice


def test_child_main_reports_a_failed_step(monkeypatch, capsys):
    """A step that raises in the child reports FAILED with the usual one-line reason."""
    monkeypatch.setattr(mirror, 'STEPS', [_step('A', error=SystemExit('Sheet missing'))])
    mirror._child_main(0, 0, 100, 'Step 1 of 1: A')
    assert capsys.readouterr().out == '@RESULT Failed\tSheet missing\n'


def test_run_steps_uses_one_child_per_step_with_the_time_limit(monkeypatch, capsys):
    """With RUN_IN_CHILD on, each step runs as `mirror.py --step <n> <lo> <hi> <label>` with STEP_TIMEOUT_S."""
    monkeypatch.setattr(mirror, 'RUN_IN_CHILD', True)
    calls = []
    monkeypatch.setattr(mirror, '_run_in_child', lambda cmd, timeout: calls.append((cmd, timeout)) or ('No changes', 'ok'))
    steps = [_step('A'), _step('B')]

    results = mirror.run_steps(steps)

    assert results == [('A', 'No changes', 'ok'), ('B', 'No changes', 'ok')]
    script = mirror.os.path.abspath(mirror.__file__)
    assert calls == [([sys.executable, script, '--step', '0', '0', '50', 'Step 1 of 2: A'], 20 * 60),
                     ([sys.executable, script, '--step', '1', '50', '100', 'Step 2 of 2: B'], 20 * 60)]


# ---- Stop button ----

def test_stop_skips_the_remaining_steps_and_still_reports(folders, monkeypatch, msgboxes, capsys, tmp_path):
    """Once main.cpp creates the stop file, the steps not started yet are listed as Not run, and the report
    is still archived, @FINISHED printed and the box shown (warning icon, header says it stopped early)."""
    stop = tmp_path / 'stop.flag'
    log = []

    def first():
        log.append('A')
        stop.write_text('')  # the user clicks Stop while A runs
        return ark_common.NOTHING, 'ok'
    monkeypatch.setattr(mirror, 'STEPS', [mirror.Step('A', first, uploads=False),
                                          _step('B', (ark_common.NOTHING, 'ok'), log=log),
                                          _step('C', (ark_common.NOTHING, 'ok'), log=log)])
    flags = []
    monkeypatch.setattr(mirror, '_show', lambda text, icon, links=(): flags.append(icon))

    mirror.main(str(stop))

    assert log == ['A']
    lines = _report_path(folders).read_text(encoding='utf-8').splitlines()
    assert lines[0].endswith(', stopped early)')
    assert lines[-4:] == ['', 'Not run', '  B: Skipped because Mirror was stopped',
                          '  C: Skipped because Mirror was stopped']
    out = capsys.readouterr().out
    assert _stages(out)[-1] == (100, 100, 'Finished') and out.rstrip().endswith('@FINISHED')
    assert flags == [mirror._MB_ICONWARNING]


def test_no_stop_without_the_stop_file(monkeypatch, tmp_path):
    """Nothing stops when there is no stop file, or it hasn't been created yet."""
    assert not mirror.stop_requested()
    monkeypatch.setattr(mirror, '_stop_file', str(tmp_path / 'stop.flag'))
    assert not mirror.stop_requested()
    (tmp_path / 'stop.flag').write_text('')
    assert mirror.stop_requested()


def test_stop_file_comes_from_the_command_line():
    """main.cpp runs `mirror.py --stop-file <path>`; with no flag there is no Stop."""
    assert mirror._stop_file_arg(['mirror.py', '--stop-file', r'C:\Temp\x.flag']) == r'C:\Temp\x.flag'
    assert mirror._stop_file_arg(['mirror.py']) is None
    assert mirror._stop_file_arg(['mirror.py', '--stop-file']) is None


def test_stop_ends_the_running_child_and_what_it_started(monkeypatch, tmp_path, capsys):
    """A Stop while a step runs kills the step's process tree (browser included) within a second or two
    and reports it as Stopped."""
    stop = tmp_path / 'stop.flag'
    monkeypatch.setattr(mirror, '_stop_file', str(stop))
    pid_file = tmp_path / 'grandchild.pid'
    code = ("import subprocess, sys, time; "
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            f"open(r'{pid_file}', 'w').write(str(p.pid)); print('started', flush=True); time.sleep(60)")
    clicker = threading.Timer(1.5, lambda: stop.write_text(''))  # the user clicks Stop 1.5 s in
    clicker.start()
    started = time.monotonic()
    try:
        kind, message = mirror._run_in_child(_py(code), 60)
    finally:
        clicker.cancel()
    assert time.monotonic() - started < 15
    assert (kind, message) == (mirror.STOPPED, 'Stopped partway through')
    grandchild = int(pid_file.read_text())
    alive = subprocess.run(['tasklist', '/FI', f'PID eq {grandchild}', '/NH'], capture_output=True, text=True).stdout
    assert str(grandchild) not in alive, 'the stopped step\'s own child process was left running'


def test_a_step_that_already_reported_keeps_its_result_when_stopped(monkeypatch, tmp_path, capsys):
    """If Stop comes right after the child printed its @RESULT (before Mirror read it), the step's
    real result is kept."""
    stop = tmp_path / 'stop.flag'
    monkeypatch.setattr(mirror, '_stop_file', str(stop))
    code = (f"import time; print('@RESULT Uploaded\\tUploaded 2 things', flush=True); "
            f"open(r'{stop}', 'w').close(); time.sleep(30)")
    assert mirror._run_in_child(_py(code), 60) == (ark_common.UPLOADED, 'Uploaded 2 things')


def test_a_stopped_upload_step_warns_its_upload_may_finish(monkeypatch, tmp_path, capsys):
    """The report line for an uploading step that was stopped says to check the Data Loader history;
    the steps after it are Not run."""
    stop = tmp_path / 'stop.flag'
    monkeypatch.setattr(mirror, '_stop_file', str(stop))
    monkeypatch.setattr(mirror, 'RUN_IN_CHILD', True)

    def fake_child(cmd, timeout):
        stop.write_text('')
        return mirror.STOPPED, 'Stopped partway through'
    monkeypatch.setattr(mirror, '_run_in_child', fake_child)
    steps = [mirror.Step('Close Date', None, uploads=True), _step('TPP-LHPP')]

    assert mirror.run_steps(steps) == [
        ('Close Date', mirror.STOPPED, 'Stopped partway through: an upload it had started may still finish '
                                       'in Ark (check the Data Loader history)'),
        ('TPP-LHPP', mirror.NOT_RUN, 'Skipped because Mirror was stopped'),
    ]


def test_report_lists_stopped_then_not_run_last():
    """Stopped and Not run come after the other groups."""
    report = mirror.build_report([('B', mirror.NOT_RUN, 'Skipped because Mirror was stopped'),
                                  ('A', mirror.STOPPED, 'Stopped partway through'),
                                  ('Z', ark_common.UPLOADED, 'Uploaded 1 thing')],
                                 datetime(2026, 10, 8, 7, 5), datetime(2026, 10, 8, 7, 6))
    assert report.splitlines() == ['Mirror run 10/08/2026 7:05 AM (took 1 min, stopped early)',
                                   '', 'Uploaded', '  Z: Uploaded 1 thing',
                                   '', 'Stopped', '  A: Stopped partway through',
                                   '', 'Not run', '  B: Skipped because Mirror was stopped']


def test_tests_never_start_real_step_processes():
    """The safety switch is on for the whole test run (conftest)."""
    assert mirror.RUN_IN_CHILD is False


# ---- Index step ----

def _fake_counties(monkeypatch, outcomes):
    """Replaces each county script's main() with one returning (or raising) its outcome."""
    for mod, outcome in zip(mirror._INDEX_COUNTIES, outcomes):
        def fake_main(outcome=outcome):
            print('@PROGRESS 1 2', flush=True)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        monkeypatch.setattr(mod, 'main', fake_main)


def test_index_step_adds_up_the_counties(monkeypatch, capsys):
    """New documents from all three counties are summed, with a per-county breakdown."""
    _fake_counties(monkeypatch, [2, 0, 3])
    mirror._begin_stage(0, 30, 'Step 1 of 6: Index')

    result = mirror._index_step()

    assert result == (ark_common.UPLOADED,
                      'Added 5 new documents to the Index sheet (Roosevelt 2, Richland 0, Divide 3)')
    assert _stages(capsys.readouterr().out) == [
        (0, 30, 'Step 1 of 6: Index'),
        (0, 10, 'Step 1 of 6: Index (Roosevelt)'),
        (10, 20, 'Step 1 of 6: Index (Richland)'),
        (20, 30, 'Step 1 of 6: Index (Divide)'),
    ]


def test_index_step_with_no_new_documents(monkeypatch, capsys):
    """Nothing new anywhere: no changes."""
    _fake_counties(monkeypatch, [0, 0, 0])
    assert mirror._index_step() == (ark_common.NOTHING, 'No new documents')


def test_index_step_keeps_going_when_a_county_fails(monkeypatch, capsys):
    """A county that stops (e.g. the workbook is open in Excel) fails the step, but the other
    counties still run and their counts are in the message."""
    _fake_counties(monkeypatch, [1, PermissionError('Index of Scanned Docs.xlsx is open'), 4])

    kind, message = mirror._index_step()

    assert kind == mirror.FAILED
    assert message == ('Richland: PermissionError: Index of Scanned Docs.xlsx is open. '
                       'Added 5 new documents (Roosevelt 1, Divide 4)')


# ---- The real steps ----

def test_steps_are_the_mirror_buttons_in_order():
    """STEPS names real buttons (main.cpp's g_mirrorSteps must match; see test_wiring)."""
    names = [s.name for s in mirror.STEPS]
    assert names == ['Index', 'Close Date', 'Case Update', 'STR', 'TPP-LHPP', 'C2E',
                     'Cases Unit Names', 'SIB', 'Docket Updates Slack', 'AOI']
    for name in names:
        by_label(name)
    assert [s.name for s in mirror.STEPS if s.uploads] == ['Close Date', 'Case Update', 'C2E',
                                                           'Cases Unit Names', 'SIB']
    assert [s.name for s in mirror.STEPS if s.report_last] == ['AOI']
    assert mirror.STEPS[-1].run is str_verification.aoi_mirror_step


def test_full_run_against_the_fake_ark(fake_ark, folders, monkeypatch, msgboxes, capsys, tmp_path):
    """Every real step runs quietly (only Mirror's own box appears) and reports its result."""
    _fake_counties(monkeypatch, [0, 0, 0])
    monkeypatch.setattr(close_dates, '_target_dates', lambda: {date(2026, 9, 25)})
    upload = Recorder()
    monkeypatch.setattr(ark_common, 'upload', upload)
    monkeypatch.setattr(str_verification, '_INPUT_PATH', str(tmp_path / 'Check_STR.csv'))
    monkeypatch.setattr(str_verification, '_STR_ERROR_PATH', str(tmp_path / 'Error_Report.csv'))
    monkeypatch.setattr(str_verification, '_AOI_INPUT_PATH', str(tmp_path / 'AOI' / 'Check_STR.csv'))
    monkeypatch.setattr(str_verification, '_AOI_ERROR_PATH', str(tmp_path / 'AOI' / 'AOI 11.10.2026.csv'))
    monkeypatch.setattr(tpp_lhpp, '_OUT_DIR', str(tmp_path))

    fake_ark.serve(close_dates._REPORT_URL, [['Offer: Offer Name', 'LandHoldingTransaction: LandHolding Id',
                                              'Offer: Close Date', 'Offer: Status'],
                                             ['a', 'LH-1', '09/25/2026', 'Paid'],
                                             ['d', 'LH-2', '09/25/2026', 'Deferred']])
    fake_ark.serve(non_hbp_mi._REPORT_URL, [['Record Id', 'Updated Date'], ['U-1', ''], ['U-2', '']])
    fake_ark.serve(str_verification._REPORT_URL, [
        ['Id', 'Section', 'Township', 'Range', 'Section Name', 'Township Name', 'Section Id', 'Area of Interest'],
        ['LH-3', '12', '153N', '97W', '12-153N-98W', '', '', ''],
        ['LH-6', '4', '153N', '97W', '04-153N-97W', '', '', '9, 16-153N-97W _ Alpha']])  # outside its AOI
    soon = f'{date.today():%Y-%m-%d}'
    fake_ark.serve(tpp_lhpp._REPORT_URLS[0][0], [['Id', 'Total Purchase Price', 'Status', 'Close Date'],
                                                 ['OF-1', '100', 'Open', soon]], filename=tpp_lhpp._OFFERS_FILENAME)
    fake_ark.serve(tpp_lhpp._REPORT_URLS[1][0], [['LandHoldingTransaction: Offer Id',
                                                  'LandHoldingTransaction: Total LandHolding Value']],
                   filename=tpp_lhpp._LHT_FILENAME)
    row = [''] * 14
    row[0], row[2], row[3], row[4] = 'LH-4', '1', '10', '150'
    c2e_header = ['Id', 'Land Holding Name', 'Total Cost to Extend', 'Land Holding NMA', '$/Acre for Extension',
                  'Account Name', 'Optional Extension', 'Land Holding Type', 'Primary Term Expiration',
                  'Extension Expiration', 'Original Lessee', 'HBP', 'Title Information',
                  'Lease Notes & Additional Documentation']
    fake_ark.serve(cost_to_extend._REPORT_URL, [c2e_header, row], filename='c2e.csv')
    fake_ark.serve(case_unit_names._UNITS_URL, [['Record Id', 'STRs', 'Unit Name'], ['U-9', '1-150N-100W', 'ARCHES']])
    fake_ark.serve(case_unit_names._CASES_URL, [['Record Id', 'Applicant', 'PHX Unit Name', 'Sections'],
                                                ['C-1', 'Phoenix Operating LLC', 'OLD', '1-150N-100W']])
    fake_ark.serve(section_id_blank._BLANK_URL, [['Id', 'Section Name', 'Section Id', 'State'],
                                                 ['LH-5', '1-150N-100W', '', 'ND']])
    fake_ark.serve(section_id_blank._SECTIONS_URL, [['Section: Id', 'Section Name'], ['S-1', '1-150N-100W']])
    (folders['SIB'] / section_id_blank._INDEX_FILE).write_text('Section Name,Section Id,Updated\n', encoding='utf-8')
    post = {'type': 'message', 'user': docket_updates_slack._USER_ID, 'ts': f'{time.time():.6f}',
            'text': 'Case 33068 (X): Pooling: GRANTED'}  # one #docket-updates post (Slack itself is tested elsewhere)
    monkeypatch.setattr(docket_updates_slack, '_fetch_messages', lambda token, oldest: {post['ts']: post})
    fake_ark.serve(docket_updates_slack._REPORT_URL, [['Record Id', 'Case Number', 'Case Status'],
                                                      ['REC-1', '33068', 'Docketed']])

    mirror.main()

    [(title, text)] = msgboxes
    assert title == 'Mirror'
    for line in ['  Close Date: Uploaded close dates for 1 landholding',
                 "  Case Update: Updated 2 units to today's date",
                 '  C2E: Uploaded fixes for 1 landholding',
                 '  STR: 1 Section Name mismatch: review Error_Report.csv',
                 '  TPP-LHPP: 1 price mismatch closing in the next two weeks: review PHX_Price_Paid_Export.xlsx',
                 '  Index: No new documents',
                 '  Cases Unit Names: Uploaded PHX Unit Names for 1 case',
                 '  SIB: Uploaded Section Ids for 1 landholding',
                 '  Docket Updates Slack: 1 RW record to fix (1 in Slack_Docket_Upload.csv, not uploaded): '
                 'review Slack_Docket_Differences.xlsx']:
        assert line in text.splitlines()
    assert 'Failed' not in text
    report = text.split('\n\nSaved to ')[0]
    assert report.endswith('\n\nAOI: 1 row in the error report: review AOI 11.10.2026.csv')
    assert (tmp_path / 'AOI' / 'AOI 11.10.2026.csv').exists()
    assert [kw['dataset'] for _, kw in upload.calls] == ['Landholdings', 'Units', 'Landholdings', 'Cases',
                                                               'Landholdings']
