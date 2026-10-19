// mirror.h — the Mirror button (mirror.cpp): runs mirror.py on a background thread and shows
// its progress, plus RunScriptLines, the "run a script and read its output" helper Index uses too.
#pragma once
#include <windows.h>
#include <functional>
#include <string>
#include <vector>

// One button whose work Mirror runs. main.cpp's g_mirrorSteps lists them (drawn faint green).
struct MirrorStep {
    int  buttonId;  // the button's control id in main.cpp
    bool uploads;   // changes live Ark data; named in the confirmation box
};

// Progress read from mirror.py's stdout by ApplyMirrorLine.
struct MirrorProgress {
    int lo = 0;             // bar position (percent) where the current stage starts
    int hi = 0;             // bar position where the current stage ends
    int percent = 0;        // bar position now
    std::wstring stage;     // e.g. "Step 2 of 6: Close Date"
    std::wstring detail;    // ": 12 / 40" or ": 12 processed" from the last @PROGRESS; empty otherwise
    bool finished = false;  // saw @FINISHED (mirror.py got as far as its report)
    bool stopping = false;  // the user clicked Stop; the status label says so until the run ends
};

// Runs cmd with no console window and calls onLine for every line it prints (stdout and stderr,
// split on \r or \n, blank lines skipped) until the process exits. Returns false if it could not start.
// With a job, the process (and everything it starts) runs inside it, so ending the job ends them all.
bool RunScriptLines(const std::wstring& cmd, const std::function<void(const std::string&)>& onLine,
                    HANDLE job = NULL);

// A job object that ends every process in it when its last handle closes (also when the app exits).
// NULL if it could not be created.
HANDLE CreateKillOnCloseJob();

// mirror.py's command line: py "<exeDir><script>" --stop-file "<stopFile>".
std::wstring MirrorCommand(const std::wstring& exeDir, const std::wstring& script, const std::wstring& stopFile);

// Text of the Yes/No box shown when Stop is clicked; stage is the running step's label (may be empty).
std::wstring MirrorStopConfirmText(const std::wstring& stage);

// Applies one line of mirror.py output (@STAGE / @PROGRESS / @FINISHED) to p. True if p changed.
bool ApplyMirrorLine(const std::string& line, MirrorProgress& p);

// Status label text: the stage, its detail and the elapsed time, e.g. "Step 2 of 6: Close Date - 1:05 elapsed".
std::wstring MirrorStatusText(const MirrorProgress& p, DWORD elapsedMs);

// Text of the Yes/No box shown before a run: every step, then the ones that upload to Ark.
std::wstring MirrorConfirmText(const std::vector<std::wstring>& steps, const std::vector<std::wstring>& uploaders);

// Mirror button click when no run is going: confirms, disables the step buttons plus the alsoLock
// buttons (others that share the Ark login, main.cpp's g_lockedDuringMirror), turns Mirror into
// Stop, shows the progress bar and status label, and runs MirrorCommand in a kill-on-close job on a
// background thread. Everything is restored at @FINISHED (mirror.py's report box may still be
// open); an error box appears if mirror.py exits without reaching it.
void StartMirror(HWND hwnd, const TCHAR* script, int mirrorId, int progressId, int statusId,
                 const MirrorStep* steps, int count, const int* alsoLock, int alsoLockCount);

// True from StartMirror until the run's buttons are restored; main.cpp then sends clicks to StopMirror.
bool IsMirrorRunning();

// Stop click: confirms, then creates the run's stop file so mirror.py stops the running step, skips
// the rest and reports. If mirror.py hasn't reached @FINISHED kMirrorStopGraceMs later, its job is ended.
void StopMirror(HWND hwnd);
