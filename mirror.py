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
At the end writes the report to "Mirror MM.DD.YYYY.txt" in [Folders] MirrorArchive
(default Desktop\\Dailies\\Archive; a second run that day is appended), prints "@FINISHED"
and shows the report in a message box (main.cpp unlocks its buttons at @FINISHED, without waiting for
the box). Adding a step: see docs/ARCHITECTURE.md (Mirror).
"""
import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import ark_common
import case_unit_names
import close_dates
import cost_to_extend
import doc_inventory_divide
import doc_inventory_richland
import doc_inventory_roosevelt
import non_hbp_mi
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
_MB_TOPMOST = 0x40000  # keeps the report above the browser windows the steps opened

STEP_TIMEOUT_S = 20 * 60  # a step still running after this long is stopped and reported as failed
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


def _begin_stage(lo, hi, label):
    """Tell main.cpp a new stage started: the bar moves to lo, and @PROGRESS lines fill up to hi."""
    global _stage
    _stage = (lo, hi, label)
    print(f'@STAGE {lo} {hi} {label}', flush=True)


def stop_requested():
    """True once main.cpp has created the stop file (the user clicked Stop and confirmed)."""
    return bool(_stop_file) and os.path.exists(_stop_file)


def _error_text(e):
    """One short line describing a failure: the first line of the error, with its type."""
    if isinstance(e, SystemExit):
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
]


def _run_here(step):
    """Run one step in this process: (result kind, report line); a step that raises is FAILED."""
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
    is FAILED with its last line of output as the reason."""
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
    deadline = time.monotonic() + timeout_s
    while True:
        if not stopping and stop_requested():
            _kill_tree(proc)  # then read what it printed before dying, in case it had already reported
            stopping, deadline = True, time.monotonic() + _STOP_DRAIN_S
        try:
            line = lines.get(timeout=max(0.0, min(_STOP_POLL_S, deadline - time.monotonic())))
        except queue.Empty:
            if time.monotonic() < deadline:
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


def build_report(results, started, finished):
    """The report text: a header line (noting a Stop), then one section per result kind that has any steps."""
    seconds = int((finished - started).total_seconds())
    took = f'{seconds // 60} min' if seconds >= 60 else f'{seconds} s'
    if any(kind in (STOPPED, NOT_RUN) for _, kind, _ in results):
        took += ', stopped early'
    hour = started.hour % 12 or 12
    lines = [f'Mirror run {started:%m/%d/%Y} {hour}:{started:%M %p} (took {took})']
    for group in _GROUPS:
        rows = [f'  {name}: {message}' for name, kind, message in results if kind == group]
        if rows:
            lines += ['', group] + rows
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


def _show(text, icon):
    """Show the final report in a message box titled Mirror."""
    ctypes.windll.user32.MessageBoxW(0, text, 'Mirror', icon | _MB_TOPMOST)


def _stop_file_arg(argv):
    """The path after `--stop-file` in argv (main.cpp always passes one), or None."""
    return argv[2] if argv[1:2] == ['--stop-file'] and len(argv) > 2 else None


def main(stop_file=None):
    """Run every step (until stop_file appears), archive the report, print @FINISHED for main.cpp,
    then show the report."""
    global _stop_file
    _stop_file = stop_file
    started = datetime.now()
    results = run_steps(STEPS)
    report = build_report(results, started, datetime.now())
    try:
        footer = f'Saved to {_save(report, started)}'
    except OSError as e:
        footer = f'Could not save the report: {e}'
    _begin_stage(100, 100, 'Finished')
    print('@FINISHED', flush=True)
    failed = any(kind in (FAILED, STOPPED, NOT_RUN) for _, kind, _ in results)
    _show(f'{report}\n\n{footer}', _MB_ICONWARNING if failed else _MB_ICONINFORMATION)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # main.cpp decodes the stage labels as UTF-8
    if sys.argv[1:2] == ['--step']:
        _child_main(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
    else:
        main(_stop_file_arg(sys.argv))
