// mirror.cpp — the Mirror button (top-left of the main window). After a Yes/No confirmation it
// runs mirror.py, which runs the work of several other buttons in a row (the g_mirrorSteps table in
// main.cpp) and ends with a report message box. This file reads mirror.py's stdout on a background
// thread and moves the progress bar / status label from its @STAGE, @PROGRESS and @FINISHED lines.
// While it runs the button reads "Stop": clicking it (after a Yes/No) creates a stop file in %TEMP%
// that mirror.py watches. mirror.py runs in a kill-on-close job, so closing the app stops it too.
// Also holds RunScriptLines, which the Index button uses to read its scripts' progress the same way.
// Touches no INI keys; mirror.py writes the report to [Folders] MirrorArchive.
#include "mirror.h"
#include <commctrl.h>
#include <tchar.h>
#include <cstdio>

static const UINT_PTR kMirrorTimerId = 0x4D52;  // main-window timer that refreshes the elapsed time once a second
static const DWORD kMirrorStopGraceMs = 30 * 1000;  // after Stop, mirror.py has this long to reach @FINISHED before its job is ended

static SRWLOCK g_mirrorLock = SRWLOCK_INIT;  // guards every g_mirror* below (worker thread vs. UI thread and timer)
static MirrorProgress g_mirror;              // latest progress read from mirror.py
static bool  g_mirrorRunning = false;        // true from the click until @FINISHED (or mirror.py exits)
static DWORD g_mirrorRunId = 0;              // counts runs, so a Stop confirmed after its run ended does nothing
static DWORD g_mirrorStart = 0;              // GetTickCount() when the run started
static HWND  g_mirrorStatus = NULL;          // the status label being updated
static HWND  g_mirrorButton = NULL;          // the Mirror button ("Stop" while running)
static std::wstring g_mirrorStopFile;        // the running run's stop file (mirror.py --stop-file); StopMirror creates it
static DWORD  g_mirrorStopAt = 0;            // GetTickCount() when Stop was confirmed; 0 = not stopping
static HANDLE g_mirrorJob = NULL;            // the running run's job; the timer ends it if a Stop isn't honored in time

// Everything the worker thread needs; allocated by StartMirror, deleted by RunMirror.
struct MirrorRun {
    HWND hwnd;                  // main window (owner of error boxes)
    HWND hMirror;               // the Mirror button, relabeled "Stop" meanwhile
    HWND hProgress;             // progress bar
    HWND hStatus;               // status label
    std::vector<HWND> buttons;  // step buttons and the alsoLock buttons, disabled during the run
    std::wstring cmd;           // MirrorCommand(...)
    std::wstring stopFile;      // %TEMP%\phx_mirror_stop_<pid>_<run>.flag; deleted when mirror.py exits
    HANDLE job = NULL;          // CreateKillOnCloseJob(); closed (ending any leftovers) when mirror.py exits
    bool restored = false;      // buttons already restored (at @FINISHED); later output is ignored
};

// Wide string from UTF-8 bytes (mirror.py writes its labels as UTF-8).
static std::wstring WideFromUtf8(const std::string& s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), NULL, 0);
    std::wstring out(n, L'\0');
    if (n > 0) MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), &out[0], n);
    return out;
}

// Splits complete lines off the front of pending and passes each non-empty one to onLine.
static void EmitLines(std::string& pending, const std::function<void(const std::string&)>& onLine) {
    size_t pos;
    while ((pos = pending.find_first_of("\r\n")) != std::string::npos) {
        std::string line = pending.substr(0, pos);
        pending.erase(0, pos + 1);
        if (!line.empty()) onLine(line);
    }
}

// Reads whatever is waiting in the pipe without blocking.
static void DrainPipe(HANDLE hRead, std::string& pending, const std::function<void(const std::string&)>& onLine) {
    char buf[4096];
    DWORD avail = 0;
    while (PeekNamedPipe(hRead, NULL, 0, NULL, &avail, NULL) && avail > 0) {
        DWORD got = 0;
        if (!ReadFile(hRead, buf, avail < sizeof(buf) ? avail : (DWORD)sizeof(buf), &got, NULL) || got == 0) return;
        pending.append(buf, got);
        EmitLines(pending, onLine);
    }
}

// Polls the pipe instead of reading to end-of-file: a browser a script leaves running can keep
// the pipe open after the script itself has exited, and that must not hang the caller.
// With a job, the process starts suspended so it is in the job before it can start anything itself.
bool RunScriptLines(const std::wstring& cmd, const std::function<void(const std::string&)>& onLine, HANDLE job) {
    SECURITY_ATTRIBUTES sa = { sizeof(sa), NULL, TRUE };
    HANDLE hRead = NULL, hWrite = NULL;
    if (!CreatePipe(&hRead, &hWrite, &sa, 0)) return false;
    SetHandleInformation(hRead, HANDLE_FLAG_INHERIT, 0);
    HANDLE hNul = CreateFile(TEXT("NUL"), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                             &sa, OPEN_EXISTING, 0, NULL);

    STARTUPINFO si = { sizeof(si) };
    si.dwFlags    = STARTF_USESTDHANDLES;
    si.hStdOutput = hWrite;
    si.hStdError  = hWrite;
    si.hStdInput  = hNul;

    std::vector<wchar_t> cmdLine(cmd.begin(), cmd.end());
    cmdLine.push_back(L'\0');
    PROCESS_INFORMATION pi = {};
    DWORD flags = CREATE_NO_WINDOW | (job ? CREATE_SUSPENDED : 0);
    BOOL created = CreateProcess(NULL, cmdLine.data(), NULL, NULL, TRUE, flags, NULL, NULL, &si, &pi);
    CloseHandle(hWrite);
    if (hNul != INVALID_HANDLE_VALUE) CloseHandle(hNul);
    if (!created) {
        CloseHandle(hRead);
        return false;
    }
    if (job) {
        AssignProcessToJobObject(job, pi.hProcess);  // if this fails it still runs, just outside the job
        ResumeThread(pi.hThread);
    }

    std::string pending;
    for (;;) {
        DrainPipe(hRead, pending, onLine);
        if (WaitForSingleObject(pi.hProcess, 50) == WAIT_OBJECT_0) {
            DrainPipe(hRead, pending, onLine);
            break;
        }
    }
    if (!pending.empty()) onLine(pending);

    CloseHandle(hRead);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return true;
}

// Not inheritable, so mirror.py's own processes can't keep the job (and themselves) alive.
HANDLE CreateKillOnCloseJob() {
    HANDLE job = CreateJobObject(NULL, NULL);
    if (!job) return NULL;
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = {};
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, &info, sizeof(info))) {
        CloseHandle(job);
        return NULL;
    }
    return job;
}

// Both paths are quoted (they may contain spaces).
std::wstring MirrorCommand(const std::wstring& exeDir, const std::wstring& script, const std::wstring& stopFile) {
    return L"py \"" + exeDir + script + L"\" --stop-file \"" + stopFile + L"\"";
}

// Names the running step when known.
std::wstring MirrorStopConfirmText(const std::wstring& stage) {
    return L"Stop Mirror?\n\nThe step running now" + (stage.empty() ? std::wstring() : L" (" + stage + L")") +
           L" stops right away, and the steps after it are skipped.\n"
           L"Steps that already finished stay done, including their uploads to Ark.\n\n"
           L"You'll still get the report of what ran.";
}

// Keeps v within 0..100.
static int ClampPercent(int v) {
    return v < 0 ? 0 : (v > 100 ? 100 : v);
}

// Tags may appear anywhere in a line (the Index scripts print "\rProcessing: ..." just before theirs).
bool ApplyMirrorLine(const std::string& line, MirrorProgress& p) {
    size_t at = line.find("@STAGE ");
    if (at != std::string::npos) {
        int lo = 0, hi = 0, used = 0;
        if (sscanf(line.c_str() + at + 7, "%d %d %n", &lo, &hi, &used) < 2) return false;
        p.lo = ClampPercent(lo);
        p.hi = ClampPercent(hi < lo ? lo : hi);
        p.percent = p.lo;
        p.stage = WideFromUtf8(line.substr(at + 7 + used));
        p.detail.clear();
        return true;
    }
    at = line.find("@PROGRESS ");
    if (at != std::string::npos) {
        int done = 0, total = -1;
        if (sscanf(line.c_str() + at + 10, "%d %d", &done, &total) < 1) return false;
        if (total > 0) {
            if (done > total) done = total;
            if (done < 0) done = 0;
            p.percent = p.lo + (int)(((long long)(p.hi - p.lo) * done) / total);
            p.detail = L": " + std::to_wstring(done) + L" / " + std::to_wstring(total);
        } else {
            p.detail = L": " + std::to_wstring(done) + L" processed";
        }
        return true;
    }
    if (line.find("@FINISHED") != std::string::npos) {
        p.finished = true;
        p.percent = 100;
        return true;
    }
    return false;
}

// Status label text; the elapsed time counts the whole run, not the step.
std::wstring MirrorStatusText(const MirrorProgress& p, DWORD elapsedMs) {
    DWORD seconds = elapsedMs / 1000;
    wchar_t clock[32];
    swprintf(clock, 32, L"%lu:%02lu", seconds / 60, seconds % 60);
    return (p.stopping ? L"Stopping... " : L"") + (p.stage.empty() ? std::wstring(L"Starting...") : p.stage) +
           p.detail + L" - " + clock + L" elapsed";
}

// Joins names with ", ".
static std::wstring JoinNames(const std::vector<std::wstring>& names) {
    std::wstring out;
    for (size_t i = 0; i < names.size(); i++) out += (i ? L", " : L"") + names[i];
    return out;
}

// Confirmation text; the upload line is left out when no step uploads.
std::wstring MirrorConfirmText(const std::vector<std::wstring>& steps, const std::vector<std::wstring>& uploaders) {
    std::wstring text = L"Mirror will run these buttons, one after another:\n" + JoinNames(steps) + L"\n\n";
    if (!uploaders.empty())
        text += L"These upload to Ark (live data):\n" + JoinNames(uploaders) + L"\n\n";
    return text + L"A sign-in may be needed when the first browser opens. Start now?";
}

// Puts the latest stage and elapsed time in the status label. Called by the worker thread and
// the timer; the lock is released before SetWindowText so neither can block the other.
static void RefreshMirrorStatus() {
    AcquireSRWLockExclusive(&g_mirrorLock);
    std::wstring text = MirrorStatusText(g_mirror, GetTickCount() - g_mirrorStart);
    ReleaseSRWLockExclusive(&g_mirrorLock);
    SetWindowText(g_mirrorStatus, text.c_str());
}

// Once-a-second main-window timer: keeps the elapsed time moving during long Ark waits, ends the
// job if a Stop wasn't honored within kMirrorStopGraceMs, and stops itself after the run ends.
static VOID CALLBACK MirrorTimerProc(HWND hwnd, UINT, UINT_PTR id, DWORD) {
    AcquireSRWLockExclusive(&g_mirrorLock);
    bool running = g_mirrorRunning;
    if (running && g_mirrorStopAt && g_mirrorJob && GetTickCount() - g_mirrorStopAt > kMirrorStopGraceMs) {
        TerminateJobObject(g_mirrorJob, 1);  // mirror.py then exits without @FINISHED: RunMirror says so
        g_mirrorStopAt = 0;
    }
    ReleaseSRWLockExclusive(&g_mirrorLock);
    if (!running) {
        KillTimer(hwnd, id);
        return;
    }
    RefreshMirrorStatus();
}

// Ends the run on screen: hides the progress controls, re-enables the buttons and turns Stop back
// into Mirror. Called once per run, from the worker thread: at @FINISHED (mirror.py's report box
// may still be open) or when mirror.py exits without it.
static void RestoreMirrorUi(MirrorRun* run) {
    AcquireSRWLockExclusive(&g_mirrorLock);
    g_mirrorRunning = false;
    g_mirrorStopFile.clear();
    g_mirrorStopAt = 0;
    g_mirrorJob = NULL;  // the worker still owns run->job and closes it when mirror.py exits
    ReleaseSRWLockExclusive(&g_mirrorLock);
    run->restored = true;

    ShowWindow(run->hProgress, SW_HIDE);
    ShowWindow(run->hStatus, SW_HIDE);
    for (HWND b : run->buttons) EnableWindow(b, TRUE);
    SetWindowText(run->hMirror, TEXT("Mirror"));
    EnableWindow(run->hMirror, TRUE);
}

// Worker thread: runs mirror.py in the run's job, applies each output line, restores the buttons at
// @FINISHED, and reports a launch failure or a run that ended without @FINISHED (mirror.py shows the
// normal report itself). Closing the job afterwards ends anything mirror.py left running.
static DWORD WINAPI RunMirror(LPVOID param) {
    MirrorRun* run = (MirrorRun*)param;
    bool launched = RunScriptLines(run->cmd, [&](const std::string& line) {
        if (run->restored) return;  // after @FINISHED only the report box is left
        AcquireSRWLockExclusive(&g_mirrorLock);
        bool changed = ApplyMirrorLine(line, g_mirror);
        int percent = g_mirror.percent;
        bool finished = g_mirror.finished;
        ReleaseSRWLockExclusive(&g_mirrorLock);
        if (finished) {
            RestoreMirrorUi(run);
        } else if (changed) {
            SendMessage(run->hProgress, PBM_SETPOS, percent, 0);
            RefreshMirrorStatus();
        }
    }, run->job);

    bool finished = run->restored;
    if (!finished) RestoreMirrorUi(run);
    if (run->job) CloseHandle(run->job);
    DeleteFile(run->stopFile.c_str());

    if (!launched) {
        MessageBox(run->hwnd,
            TEXT("Could not launch mirror.py.\nEnsure Python is installed and available in your PATH."),
            TEXT("Error"), MB_ICONERROR);
    } else if (!finished) {
        MessageBox(run->hwnd,
            TEXT("Mirror stopped before it finished, so there is no report.\n")
            TEXT("Steps that ran before it stopped may already have uploaded to Ark."),
            TEXT("Mirror"), MB_ICONERROR);
    }
    delete run;
    return 0;
}

// Click handler (UI thread). Refuses to start while a step button is disabled (still running on its own).
void StartMirror(HWND hwnd, const TCHAR* script, int mirrorId, int progressId, int statusId,
                 const MirrorStep* steps, int count, const int* alsoLock, int alsoLockCount) {
    MirrorRun* run = new MirrorRun();
    run->hwnd      = hwnd;
    run->hMirror   = GetDlgItem(hwnd, mirrorId);
    run->hProgress = GetDlgItem(hwnd, progressId);
    run->hStatus   = GetDlgItem(hwnd, statusId);

    std::vector<std::wstring> names, uploaders;
    bool busy = false;
    for (int i = 0; i < count; i++) {
        HWND b = GetDlgItem(hwnd, steps[i].buttonId);
        if (!IsWindowEnabled(b)) busy = true;  // e.g. Index is still running on its own
        TCHAR label[128] = {};
        GetWindowText(b, label, 128);
        names.push_back(label);
        if (steps[i].uploads) uploaders.push_back(label);
        run->buttons.push_back(b);
    }
    for (int i = 0; i < alsoLockCount; i++) run->buttons.push_back(GetDlgItem(hwnd, alsoLock[i]));
    if (busy) {
        MessageBox(hwnd, TEXT("A button Mirror runs is still busy. Try again when it finishes."),
                   TEXT("Mirror"), MB_ICONINFORMATION);
        delete run;
        return;
    }
    if (MessageBox(hwnd, MirrorConfirmText(names, uploaders).c_str(), TEXT("Mirror"),
                   MB_YESNO | MB_ICONQUESTION) != IDYES) {
        delete run;
        return;
    }

    TCHAR exeDir[MAX_PATH] = {};
    GetModuleFileName(NULL, exeDir, MAX_PATH);
    TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
    if (slash) *(slash + 1) = TEXT('\0');
    TCHAR tempDir[MAX_PATH] = {};
    GetTempPath(MAX_PATH, tempDir);
    AcquireSRWLockExclusive(&g_mirrorLock);
    DWORD runId = ++g_mirrorRunId;
    ReleaseSRWLockExclusive(&g_mirrorLock);
    run->stopFile = std::wstring(tempDir) + L"phx_mirror_stop_" + std::to_wstring(GetCurrentProcessId()) +
                    L"_" + std::to_wstring(runId) + L".flag";
    DeleteFile(run->stopFile.c_str());  // in case an earlier app with this process id left one
    run->cmd = MirrorCommand(exeDir, script, run->stopFile);
    run->job = CreateKillOnCloseJob();  // NULL: runs anyway, it just can't be force-ended

    for (HWND b : run->buttons) EnableWindow(b, FALSE);
    SetWindowText(run->hMirror, TEXT("Stop"));

    AcquireSRWLockExclusive(&g_mirrorLock);
    g_mirror = MirrorProgress();
    g_mirrorRunning = true;
    g_mirrorStart = GetTickCount();
    g_mirrorStatus = run->hStatus;
    g_mirrorButton = run->hMirror;
    g_mirrorStopFile = run->stopFile;
    g_mirrorStopAt = 0;
    g_mirrorJob = run->job;
    ReleaseSRWLockExclusive(&g_mirrorLock);

    SendMessage(run->hProgress, PBM_SETRANGE32, 0, 100);
    SendMessage(run->hProgress, PBM_SETPOS, 0, 0);
    ShowWindow(run->hProgress, SW_SHOW);
    ShowWindow(run->hStatus, SW_SHOW);
    RefreshMirrorStatus();
    SetTimer(hwnd, kMirrorTimerId, 1000, MirrorTimerProc);

    HANDLE hThread = CreateThread(NULL, 0, RunMirror, run, 0, NULL);
    if (hThread) {
        CloseHandle(hThread);
        return;
    }
    RestoreMirrorUi(run);
    if (run->job) CloseHandle(run->job);
    MessageBox(hwnd, TEXT("Could not start Mirror."), TEXT("Error"), MB_ICONERROR);
    delete run;
}

// Read by main.cpp on every Mirror click.
bool IsMirrorRunning() {
    AcquireSRWLockExclusive(&g_mirrorLock);
    bool running = g_mirrorRunning;
    ReleaseSRWLockExclusive(&g_mirrorLock);
    return running;
}

// Click handler (UI thread) while a run is going. The run may end while the Yes/No box is open;
// then Yes does nothing (g_mirrorRunId tells the runs apart). If the stop file can't be created,
// the timer still ends the job after the grace period.
void StopMirror(HWND hwnd) {
    AcquireSRWLockExclusive(&g_mirrorLock);
    bool running = g_mirrorRunning;
    DWORD runId = g_mirrorRunId;
    std::wstring stage = g_mirror.stage;
    ReleaseSRWLockExclusive(&g_mirrorLock);
    if (!running) return;
    if (MessageBox(hwnd, MirrorStopConfirmText(stage).c_str(), TEXT("Mirror"),
                   MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2) != IDYES)
        return;

    AcquireSRWLockExclusive(&g_mirrorLock);
    bool sameRun = g_mirrorRunning && g_mirrorRunId == runId;
    HWND button = g_mirrorButton;
    if (sameRun) {
        HANDLE f = CreateFile(g_mirrorStopFile.c_str(), GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL, NULL);
        if (f != INVALID_HANDLE_VALUE) CloseHandle(f);
        g_mirrorStopAt = GetTickCount() | 1;  // never 0, which means "not stopping"
        g_mirror.stopping = true;
    }
    ReleaseSRWLockExclusive(&g_mirrorLock);
    if (!sameRun) return;
    SetWindowText(button, TEXT("Stopping..."));
    EnableWindow(button, FALSE);
    RefreshMirrorStatus();
}
