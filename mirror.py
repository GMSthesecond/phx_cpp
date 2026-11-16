"""Mirror: runs several buttons' work back to back and reports what each one did.

Launched by the "Mirror" button (main.cpp, after a Yes/No confirmation), which reads this
script's stdout on a background thread. Runs each step in STEPS in order, each in its own child
process (`mirror.py --step <n> ...`, see _child_main) with the steps' own message boxes turned off,
and keeps going when a step fails. A step still running after STEP_TIMEOUT_S is stopped (its whole
process tree, browser included) and reported as failed, so one hung page can't hold up the rest.
main.cpp's Stop button creates the file named by `--stop-file <path>`: Mirror then stops the running
step's process tree, skips the rest, and still writes and shows the report.
Prints "@STAGE <lo> <hi> <label>" before each step (and each Index county) so main.cpp can
move its progress bar; the child's output, e.g. the Index scripts' "@PROGRESS" lines, passes
straight through, except its one "@RESULT <kind>\t<line>" line, which Mirror keeps for the report.
A step that needs a large Ark report waits for the user's Yes/No (ark_common.confirm_download): its child prints
@WAITING / @RESUMED around the box, and Mirror pauses that step's time limit and says so on the progress
label meanwhile. A No fails the step ("Large download cancelled: ...") and the run goes on.
At the end writes the report to "Mirror MM.DD.YYYY.txt" in [Folders] MirrorArchive
(default Desktop\\Dailies\\Archive; a second run that day is appended), prints "@FINISHED"
and shows the report in a task dialog whose web links (e.g. a cancelled report's) and archive path can be
clicked, or a plain message box if that can't open (main.cpp unlocks its buttons at @FINISHED, without
waiting for the box). Adding a step: see docs/ARCHITECTURE.md (Mirror).
"""
import ctypes
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import ark_common
import case_unit_names
import close_dates
import cost_to_extend
import docket_updates_slack
import doc_inventory_divide
import doc_inventory_richland
import doc_inventory_roosevelt
import non_hbp_mi
import section_id_blank
import str_verification
import tpp_lhpp

FAILED = 'Failed'  # result kind for a step that raised, hung or crashed
STOPPED = 'Stopped'  # result kind for the step that was running when the user clicked Stop
NOT_RUN = 'Not run'  # result kind for the steps skipped after a Stop
_GROUPS = [ark_common.UPLOADED, ark_common.REVIEW, ark_common.NOTHING, FAILED, STOPPED, NOT_RUN]  # report section order

_ARCHIVE_DEFAULT = r'C:\Users\Ethan Mesecher\Desktop\Dailies\Archive'  # used when [Folders] MirrorArchive is unset
_RUN_SEPARATOR = '\n' + '-' * 40 + '\n\n'  # between two runs appended to the same day's file
_MAX_ERROR = 200  # longest failure reason kept in the report (Playwright errors run to pages)

_MB_ICONINFORMATION = 0x40  # message box icon when every step worked
_MB_ICONWARNING = 0x30  # message box icon when a step failed or the run was stopped
_MB_TOPMOST = 0x40000  # keeps the report above the browser windows the steps opened (fallback message box)

# The report is shown in a task dialog (_task_dialog) so its links can be clicked; Win32 values from commctrl.h
_URL_RE = re.compile(r'https?://[^\s;,<>"]+')  # web links in the report, made clickable (_with_links)
_URL_TRAILING = '.)'  # characters dropped from the end of a URL found in the report (sentence punctuation)
_TDF_ENABLE_HYPERLINKS = 0x0001  # task dialog flag: <a href> in the content is a link
_TDF_ALLOW_DIALOG_CANCELLATION = 0x0008  # task dialog flag: Esc and the close box work
_TDCBF_OK_BUTTON = 0x0001  # the task dialog's one button
_TDN_CREATED = 0  # callback notification: the dialog window exists
_TDN_HYPERLINK_CLICKED = 3  # callback notification: a link was clicked (lparam = its href)
_TD_ICONS = {_MB_ICONINFORMATION: 0xFFFD, _MB_ICONWARNING: 0xFFFF}  # message-box icon flag -> TD_INFORMATION_ICON / TD_WARNING_ICON
_HWND_TOPMOST = -1  # SetWindowPos: keep the report above other windows
_SWP_NOSIZE, _SWP_NOMOVE = 0x0001, 0x0002  # SetWindowPos: only change the z-order
_INVALID_HANDLE = wintypes.HANDLE(-1).value  # CreateActCtxW's failure value
_MANIFEST_NAME = 'phx_mirror_comctl6.manifest'  # temp-folder file _task_dialog builds its activation context from
# Asks for Common Controls 6, which has task dialogs (python.exe's own manifest doesn't)
_COMCTL6_MANIFEST = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <dependency>
    <dependentAssembly>
      <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0"
                        processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/>
    </dependentAssembly>
  </dependency>
</assembly>
"""

# PFTASKDIALOGCALLBACK: (hwnd, notification, wParam, lParam, callback data) -> HRESULT
_TaskDialogCallback = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                         wintypes.LPARAM, ctypes.c_ssize_t)


class _TaskDialogConfig(ctypes.Structure):
    """TASKDIALOGCONFIG (commctrl.h, byte-packed: 160 bytes on 64-bit, checked by test_mirror)."""
    _pack_ = 1
    _fields_ = [('cbSize', wintypes.UINT), ('hwndParent', wintypes.HWND), ('hInstance', wintypes.HINSTANCE),
                ('dwFlags', wintypes.DWORD), ('dwCommonButtons', wintypes.DWORD),
                ('pszWindowTitle', wintypes.LPCWSTR), ('pszMainIcon', ctypes.c_void_p),
                ('pszMainInstruction', wintypes.LPCWSTR), ('pszContent', wintypes.LPCWSTR),
                ('cButtons', wintypes.UINT), ('pButtons', ctypes.c_void_p), ('nDefaultButton', ctypes.c_int),
                ('cRadioButtons', wintypes.UINT), ('pRadioButtons', ctypes.c_void_p),
                ('nDefaultRadioButton', ctypes.c_int), ('pszVerificationText', wintypes.LPCWSTR),
                ('pszExpandedInformation', wintypes.LPCWSTR), ('pszExpandedControlText', wintypes.LPCWSTR),
                ('pszCollapsedControlText', wintypes.LPCWSTR), ('hFooterIcon', ctypes.c_void_p),
                ('pszFooter', wintypes.LPCWSTR), ('pfCallback', _TaskDialogCallback),
                ('lpCallbackData', ctypes.c_ssize_t), ('cxWidth', wintypes.UINT)]


class _ActCtx(ctypes.Structure):
    """ACTCTXW (winbase.h): the manifest an activation context is made from."""
    _fields_ = [('cbSize', wintypes.ULONG), ('dwFlags', wintypes.DWORD), ('lpSource', wintypes.LPCWSTR),
                ('wProcessorArchitecture', wintypes.USHORT), ('wLangId', wintypes.LANGID),
                ('lpAssemblyDirectory', wintypes.LPCWSTR), ('lpResourceName', wintypes.LPCWSTR),
                ('lpApplicationName', wintypes.LPCWSTR), ('hModule', wintypes.HMODULE)]

STEP_TIMEOUT_S = 20 * 60  # a step still running after this long (not counting time waiting on a large-download box) is stopped and reported as failed
_WAITING_LABEL = ': waiting for your answer (large download)'  # added to the progress label while a step's large-download box is open
RUN_IN_CHILD = True  # run each step in its own process (so it can be stopped); tests/conftest.py sets False
_RESULT_TAG = '@RESULT '  # child -> Mirror: "@RESULT <kind>\t<report line>", printed once by _child_main
_STOP_POLL_S = 0.5  # how often a running step's child is checked for a Stop
_STOP_DRAIN_S = 5  # after killing a stopped step, how long to wait for the rest of its output (a late @RESULT)

_INDEX_COUNTIES = [doc_inventory_roosevelt, doc_inventory_richland, doc_inventory_divide]  # Index button's scripts, in its order

_stage = (0, 0, '')  # (lo, hi, label) of the running step's slice of the progress bar; set by _begin_stage
_stop_file = None  # main.cpp creates this file when the user clicks Stop (`--stop-file`); None = can't be stopped


@dataclass
class Step:
    """One button whose work Mirror runs. run() returns (result kind, report line) or raises."""
    name: str  # the button's label; main.cpp's g_mirrorSteps lists the same buttons in the same order
    run: Callable
    uploads: bool  # changes live Ark data (main.cpp names these in the confirmation box)
    report_last: bool = False  # its line goes at the very end of the report, after the result groups


def _begin_stage(lo, hi, label):
    """Tell main.cpp a new stage started: the bar moves to lo, and @PROGRESS lines fill up to hi."""
    global _stage
    _stage = (lo, hi, label)
    print(f'@STAGE {lo} {hi} {label}', flush=True)


def stop_requested():
    """True once main.cpp has created the stop file (the user clicked Stop and confirmed)."""
    return bool(_stop_file) and os.path.exists(_stop_file)


def _error_text(e):
    """One short line describing a failure: the first line of the error, with its type (a cancelled
    large download's text alone, which says what it is)."""
    if isinstance(e, ark_common.DownloadCancelled):
        text = str(e)
    elif isinstance(e, SystemExit):
        text = str(e.code) if isinstance(e.code, str) else f'stopped (exit code {e.code})'
    else:
        first = str(e).strip().splitlines()[0] if str(e).strip() else ''
        text = f'{type(e).__name__}: {first}' if first else type(e).__name__
    return text if len(text) <= _MAX_ERROR else text[:_MAX_ERROR - 1] + '…'


def _index_step():
    """Mirror's Index step: run each county script (one failing doesn't stop the others) and
    return (result kind, report line) with the number of documents added to the Index sheet."""
    lo, hi, label = _stage
    added, errors = [], []
    for k, mod in enumerate(_INDEX_COUNTIES):
        n = len(_INDEX_COUNTIES)
        _begin_stage(lo + (hi - lo) * k // n, lo + (hi - lo) * (k + 1) // n, f'{label} ({mod.COUNTY.name})')
        try:
            added.append((mod.COUNTY.name, mod.main()))
        except (Exception, SystemExit) as e:
            errors.append(f'{mod.COUNTY.name}: {_error_text(e)}')
    total = sum(count for _, count in added)
    breakdown = ', '.join(f'{county} {count}' for county, count in added)
    if errors:
        done = f'. Added {ark_common.plural(total, "new document")} ({breakdown})' if added else ''
        return FAILED, '; '.join(errors) + done
    if total:
        return ark_common.UPLOADED, f'Added {ark_common.plural(total, "new document")} to the Index sheet ({breakdown})'
    return ark_common.NOTHING, 'No new documents'


# The buttons Mirror runs, in order. main.cpp's g_mirrorSteps must list the same buttons
# (test_wiring checks), and those buttons are drawn green.
STEPS = [
    Step('Index', _index_step, uploads=False),
    Step('Close Date', close_dates.mirror_step, uploads=True),
    Step('Case Update', non_hbp_mi.mirror_step, uploads=True),
    Step('STR', str_verification.mirror_step, uploads=False),
    Step('TPP-LHPP', tpp_lhpp.mirror_step, uploads=False),
    Step('C2E', cost_to_extend.mirror_step, uploads=True),
    Step('Cases Unit Names', case_unit_names.mirror_step, uploads=True),
    Step('SIB', section_id_blank.mirror_step, uploads=True),
    Step('Docket Updates Slack', docket_updates_slack.mirror_step, uploads=False),
    Step('AOI', str_verification.aoi_mirror_step, uploads=False, report_last=True),
]


def _run_here(step):
    """Run one step in this process: (result kind, report line); a step that raises (including a
    large download the user said No to) is FAILED."""
    try:
        return step.run()
    except (Exception, SystemExit) as e:
        return FAILED, _error_text(e)


def _step_command(index, lo, hi, label):
    """The command that runs STEPS[index] in a child process (see _child_main)."""
    return [sys.executable, os.path.abspath(__file__), '--step', str(index), str(lo), str(hi), label]


def _kill_tree(proc):
    """Stop proc and everything it started (Chromium windows included)."""
    subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    proc.kill()


def _run_in_child(cmd, timeout_s):
    """Run cmd, printing its output lines on (main.cpp reads the @ tags) except the @RESULT line,
    which is returned as (kind, report line). Stops the process tree after timeout_s and returns
    FAILED, or as soon as stop_requested() and returns STOPPED; a child that ends without @RESULT
    is FAILED with its last line of output as the reason. Between the child's WAITING_TAG and
    RESUMED_TAG (a large-download Yes/No box is open) the time limit is paused and the progress
    label (_stage) gets _WAITING_LABEL; those two lines aren't passed on."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            encoding='utf-8', errors='replace', env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    lines = queue.Queue()

    def pump():
        for line in proc.stdout:
            lines.put(line.rstrip('\r\n'))
        lines.put(None)  # end of output
    threading.Thread(target=pump, daemon=True).start()

    result, last, stopping = None, '', False
    paused_at = None  # time.monotonic() when the child's large-download box opened; None = not waiting on one
    lo, hi, label = _stage
    deadline = time.monotonic() + timeout_s
    while True:
        if not stopping and stop_requested():
            _kill_tree(proc)  # then read what it printed before dying, in case it had already reported
            stopping, deadline = True, time.monotonic() + _STOP_DRAIN_S
        waiting = paused_at is not None and not stopping
        try:
            line = lines.get(timeout=_STOP_POLL_S if waiting else
                             max(0.0, min(_STOP_POLL_S, deadline - time.monotonic())))
        except queue.Empty:
            if waiting or time.monotonic() < deadline:
                continue
            if stopping:
                break
            _kill_tree(proc)
            return FAILED, f'Stopped: still running after {timeout_s // 60} min'
        if line is None:
            break
        if line.startswith(_RESULT_TAG):
            kind, _, message = line[len(_RESULT_TAG):].partition('\t')
            result = (kind, message)
        elif line.strip() == ark_common.WAITING_TAG:
            paused_at = paused_at or time.monotonic()
            print(f'@STAGE {lo} {hi} {label}{_WAITING_LABEL}', flush=True)
        elif line.strip() == ark_common.RESUMED_TAG:
            if paused_at is not None:
                deadline += time.monotonic() - paused_at
                paused_at = None
            print(f'@STAGE {lo} {hi} {label}', flush=True)
        else:
            print(line, flush=True)
            if line.strip() and not line.startswith('@'):
                last = line.strip()
    if stopping:
        return result or (STOPPED, 'Stopped partway through')
    code = proc.wait()
    if result:
        return result
    reason = last or f'exit code {code}'
    return FAILED, f'stopped without a result ({reason})'[:_MAX_ERROR]


def _child_main(index, lo, hi, label):
    """Entry point of a step's child process: run STEPS[index] with the parent's progress slice
    and print its result as one @RESULT line."""
    global _stage
    _stage = (lo, hi, label)
    kind, message = _run_here(STEPS[index])
    print(f'{_RESULT_TAG}{kind}\t{" ".join(message.splitlines())}', flush=True)


def run_steps(steps):
    """Run every step in order, giving each an equal slice of the progress bar, each in its own
    process with STEP_TIMEOUT_S (in this process when RUN_IN_CHILD is False; steps must then be STEPS
    for the child to find them). Returns [(step name, result kind, report line)]; a step that
    raises, hangs or crashes is FAILED. After a Stop the running step is STOPPED and the rest NOT_RUN."""
    results = []
    for i, step in enumerate(steps):
        if stop_requested():
            results.append((step.name, NOT_RUN, 'Skipped because Mirror was stopped'))
            continue
        lo, hi = 100 * i // len(steps), 100 * (i + 1) // len(steps)
        label = f'Step {i + 1} of {len(steps)}: {step.name}'
        _begin_stage(lo, hi, label)
        if RUN_IN_CHILD:
            kind, message = _run_in_child(_step_command(i, lo, hi, label), STEP_TIMEOUT_S)
        else:
            kind, message = _run_here(step)
        if kind == STOPPED and step.uploads:
            message += ': an upload it had started may still finish in Ark (check the Data Loader history)'
        results.append((step.name, kind, message))
    return results


def build_report(results, started, finished, last=()):
    """The report text: a header line (noting a Stop), then one section per result kind that has any
    steps, then the steps named in last, each on its own "<name>: <line>" line ("<name>: <kind>: <line>"
    if it failed, stopped or didn't run)."""
    seconds = int((finished - started).total_seconds())
    took = f'{seconds // 60} min' if seconds >= 60 else f'{seconds} s'
    if any(kind in (STOPPED, NOT_RUN) for _, kind, _ in results):
        took += ', stopped early'
    hour = started.hour % 12 or 12
    lines = [f'Mirror run {started:%m/%d/%Y} {hour}:{started:%M %p} (took {took})']
    for group in _GROUPS:
        rows = [f'  {name}: {message}' for name, kind, message in results if kind == group and name not in last]
        if rows:
            lines += ['', group] + rows
    for name, kind, message in results:
        if name in last:
            problem = f'{kind}: ' if kind in (FAILED, STOPPED, NOT_RUN) else ''
            lines += ['', f'{name}: {problem}{message}']
    return '\n'.join(lines)


def _archive_path(started):
    """The day's report file in [Folders] MirrorArchive."""
    folder = ark_common.read_folder('MirrorArchive', _ARCHIVE_DEFAULT)
    return os.path.join(folder, f'Mirror {started:%m.%d.%Y}.txt')


def _save(report, started):
    """Append the report to the day's archive file (creating the folder); returns its path."""
    path = _archive_path(started)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    earlier = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, 'a', encoding='utf-8') as f:
        f.write((_RUN_SEPARATOR if earlier else '') + report + '\n')
    return path


def _with_links(text, links=()):
    """text with every web link (_URL_RE) and every one of links (e.g. the archive path) where it
    appears wrapped as a task-dialog hyperlink, <a href="target">target</a>. Punctuation ending a
    sentence after a URL (_URL_TRAILING) is left outside it."""
    patterns = [re.escape(link) for link in sorted(set(filter(None, links)), key=len, reverse=True)]
    pattern = re.compile('|'.join(patterns + [_URL_RE.pattern]))

    def wrap(m):
        """One link's markup, with any trailing punctuation after it."""
        target = m.group(0) if m.group(0) in links else m.group(0).rstrip(_URL_TRAILING)
        return f'<a href="{target}">{target}</a>{m.group(0)[len(target):]}'
    return pattern.sub(wrap, text)


def _open_link(target):
    """Open a clicked report link: a web page in the default browser, a file in its program."""
    try:
        os.startfile(target)
    except OSError:
        pass  # nothing to report it in; the link text is still there to copy


def _on_dialog_event(hwnd, msg, wparam, lparam, data):
    """Task dialog callback: keep the report above the steps' browser windows when it opens
    (like MB_TOPMOST), and open a link when one is clicked (lparam is its href)."""
    try:
        if msg == _TDN_CREATED:
            user32 = ctypes.WinDLL('user32')
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE)
        elif msg == _TDN_HYPERLINK_CLICKED:
            _open_link(ctypes.wstring_at(lparam))
    except Exception:  # noqa: BLE001  (an error can't leave a ctypes callback; the dialog just carries on)
        pass
    return 0


def _task_dialog(title, content, icon):
    """Show content (plain text with <a href> links) in a Windows task dialog with an OK button and
    the icon matching the message-box icon flag. Task dialogs need Common Controls 6, which
    python.exe doesn't ask for, so this runs inside an activation context made from
    _COMCTL6_MANIFEST (written to the temp folder). Raises OSError (or AttributeError on an old
    comctl32) if Windows refuses; tests/conftest.py replaces it."""
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateActCtxW.restype = wintypes.HANDLE
    kernel32.CreateActCtxW.argtypes = [ctypes.POINTER(_ActCtx)]
    kernel32.ActivateActCtx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.DeactivateActCtx.argtypes = [wintypes.DWORD, ctypes.c_size_t]
    kernel32.ReleaseActCtx.argtypes = [wintypes.HANDLE]

    manifest = os.path.join(tempfile.gettempdir(), _MANIFEST_NAME)
    with open(manifest, 'w', encoding='utf-8') as f:
        f.write(_COMCTL6_MANIFEST)
    ctx = _ActCtx(cbSize=ctypes.sizeof(_ActCtx), lpSource=manifest)
    handle = kernel32.CreateActCtxW(ctypes.byref(ctx))
    if handle is None or handle == _INVALID_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        cookie = ctypes.c_size_t()
        if not kernel32.ActivateActCtx(handle, ctypes.byref(cookie)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            show = ctypes.WinDLL('comctl32').TaskDialogIndirect  # Common Controls 6 inside the context
            show.restype = ctypes.c_long
            show.argtypes = [ctypes.POINTER(_TaskDialogConfig), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            callback = _TaskDialogCallback(_on_dialog_event)  # kept alive until the dialog closes
            config = _TaskDialogConfig(
                cbSize=ctypes.sizeof(_TaskDialogConfig), dwFlags=_TDF_ENABLE_HYPERLINKS | _TDF_ALLOW_DIALOG_CANCELLATION,
                dwCommonButtons=_TDCBF_OK_BUTTON, pszWindowTitle=title,
                pszMainIcon=_TD_ICONS.get(icon, _TD_ICONS[_MB_ICONINFORMATION]), pszContent=content,
                pfCallback=callback)
            result = show(ctypes.byref(config), None, None, None)
            if result != 0:
                raise OSError(f'TaskDialogIndirect failed: 0x{result & 0xFFFFFFFF:08X}')
        finally:
            kernel32.DeactivateActCtx(0, cookie.value)
    finally:
        kernel32.ReleaseActCtx(handle)


def _show(text, icon, links=()):
    """Show the final report titled Mirror in a task dialog where web links and links (e.g. the
    archive path) can be clicked (_with_links); a plain message box if the task dialog can't open."""
    try:
        _task_dialog('Mirror', _with_links(text, links), icon)
    except (OSError, AttributeError):
        ctypes.windll.user32.MessageBoxW(0, text, 'Mirror', icon | _MB_TOPMOST)


def _stop_file_arg(argv):
    """The path after `--stop-file` in argv (main.cpp always passes one), or None."""
    return argv[2] if argv[1:2] == ['--stop-file'] and len(argv) > 2 else None


def main(stop_file=None):
    """Run every step (until stop_file appears), archive the report, print @FINISHED for main.cpp,
    then show the report (_show: its web links and the archive path can be clicked)."""
    global _stop_file
    _stop_file = stop_file
    started = datetime.now()
    results = run_steps(STEPS)
    report = build_report(results, started, datetime.now(), last={s.name for s in STEPS if s.report_last})
    saved = None
    try:
        saved = _save(report, started)
        footer = f'Saved to {saved}'
    except OSError as e:
        footer = f'Could not save the report: {e}'
    _begin_stage(100, 100, 'Finished')
    print('@FINISHED', flush=True)
    failed = any(kind in (FAILED, STOPPED, NOT_RUN) for _, kind, _ in results)
    _show(f'{report}\n\n{footer}', _MB_ICONWARNING if failed else _MB_ICONINFORMATION, links=[saved])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # main.cpp decodes the stage labels as UTF-8
    if sys.argv[1:2] == ['--step']:
        _child_main(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
    else:
        main(_stop_file_arg(sys.argv))
