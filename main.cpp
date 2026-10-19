// main.cpp — entry point and main window for Phoenix Land Department Reporting (phxcpp.exe).
// Builds the grid of buttons; each button either launches a Python script that sits next to
// the exe (LaunchScript: `py "<exeDir>\script.py"`, no console window) or opens a C++ dialog
// (Settings -> settings.cpp, Organization -> organize.cpp, Rename -> rename.cpp).
// Each button is labeled with the Desktop folder its work goes to (C2E, DMD, STR, ...).
// Index and Maps run their scripts on a background thread so the window stays responsive.
// Mirror (top-left, mirror.cpp) runs several buttons' work in a row; those buttons are drawn green.
// While Mirror runs its button reads "Stop" and clicks go to StopMirror.
// See docs/ARCHITECTURE.md for the full button -> script map.
#include <windows.h>
#include <commctrl.h>
#include <tchar.h>
#include <string>
#include <cstdio>
#include <cstdlib>
#include "settings.h"
#include "organize.h"
#include "rename.h"
#include "mirror.h"

// Enable visual styles (modern button rendering) without a separate .manifest file
#pragma comment(lib, "comctl32.lib")
#pragma comment(linker, "/manifestdependency:\"type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")

// Control IDs used only in the main window
#define ID_TITLE                3
#define ID_BUTTON_SETTINGS      6
// Column 1
#define ID_BUTTON_CLOSE_DATE   43
#define ID_BUTTON_NONHBP_MI    45
#define ID_BUTTON_INDEX        21
#define ID_BUTTON_CASE_UNIT_NAMES 42  // runs case_unit_names.py
#define ID_BUTTON_STR          10
#define ID_BUTTON_TPP_LHPP     22
#define ID_BUTTON_COST         23
#define ID_BUTTON_DOCKET_UPDATES 51  // runs docket_updates.py (Hearing Dockets workbook vs RW)
#define ID_BUTTON_DOCKET_UPDATES_SLACK 59  // runs docket_updates_slack.py; disabled (g_disabledButtonIds)
// Column 2
#define ID_BUTTON_PPIQ         20
#define ID_BUTTON_AOI          11
#define ID_BUTTON_DOWNLOAD      9
#define ID_BUTTON_ORGANIZE     44
// Column 3
#define ID_BUTTON_CASE_MATCHUP 46
#define ID_BUTTON_DECEASED     40
#define ID_BUTTON_RENAME       47
#define ID_BUTTON_MAP          48
// Column 4
#define ID_BUTTON_ELMI         30
#define ID_BUTTON_DNM          31
#define ID_BUTTON_HBPNW        32
#define ID_BUTTON_LE           33
#define ID_BUTTON_LHP          34
#define ID_BUTTON_NHBPW        35
#define ID_BUTTON_SIB          36
#define ID_BUTTON_UNLE         37
#define ID_BUTTON_SL           38
#define ID_BUTTON_HBP_WELLS    41
// Index run status (hidden except while the Index button is running)
#define ID_PROGRESS_INDEX      49
#define ID_LABEL_INDEX_STATUS  50
// Mirror (top-left, outside the columns) and its run status (hidden except while it runs)
#define ID_BUTTON_MIRROR       52
#define ID_PROGRESS_MIRROR     53
#define ID_LABEL_MIRROR_STATUS 54
// Column header labels: ID_COLUMN_HEADER + i is the label over column i + 1 (55-58)
#define ID_COLUMN_HEADER       55

HFONT  g_hTitleFont   = NULL;  // 32px bold Segoe UI for the window title; created in WM_CREATE, freed in WM_DESTROY
HFONT  g_hButtonFont  = NULL;  // 13px Segoe UI for buttons and the Index status label
HFONT  g_hHeaderFont  = NULL;  // 15px semibold Segoe UI for the column headers
HBRUSH g_hBgBrush     = NULL;  // light gray window background; also returned for static controls in WM_CTLCOLORSTATIC
HBRUSH g_hYellowBrush = NULL;  // fill for unwired (owner-drawn) buttons in WM_DRAWITEM
HBRUSH g_hGreenBrush  = NULL;  // faint green fill for the buttons Mirror runs (owner-drawn) in WM_DRAWITEM
HWND   g_hwndMain     = NULL;  // the main window, created in WinMain

// Labels over the button columns, left to right (tests/buttons.py COLUMN_HEADERS must match)
static const TCHAR* const g_columnHeaders[] = {
    TEXT("Daily"), TEXT("Set Date"), TEXT("As Needed"), TEXT("In Progress"),
};

// Buttons whose click handler is not implemented yet — drawn light yellow as a visual "not done" cue
static const int g_unwiredButtonIds[] = {
    ID_BUTTON_ELMI, ID_BUTTON_DNM, ID_BUTTON_HBPNW, ID_BUTTON_LE, ID_BUTTON_LHP,
    ID_BUTTON_NHBPW, ID_BUTTON_SIB, ID_BUTTON_UNLE, ID_BUTTON_SL,
    ID_BUTTON_HBP_WELLS,
};

// True if id is in g_unwiredButtonIds. WM_CREATE uses this to make those buttons owner-drawn
// so WM_DRAWITEM can paint them yellow. Remove an id from the list once its button is implemented.
bool IsUnwiredButton(int id) {
    for (int candidate : g_unwiredButtonIds) {
        if (candidate == id) return true;
    }
    return false;
}

// Working buttons shown greyed out (disabled) so they can't be clicked; WM_COMMAND also ignores them.
// Their click handler still launches their script, so removing an id from this list is all it
// takes to reactivate one.
static const int g_disabledButtonIds[] = {
    ID_BUTTON_DOCKET_UPDATES_SLACK,
};

// True if id is in g_disabledButtonIds. WM_CREATE disables those buttons after creating them.
bool IsDisabledButton(int id) {
    for (int candidate : g_disabledButtonIds) {
        if (candidate == id) return true;
    }
    return false;
}

// Buttons whose work the Mirror button runs, in order. Must list the same buttons as STEPS in
// mirror.py (test_wiring checks). Drawn faint green. uploads = changes live Ark data (named in
// Mirror's confirmation box). To add a step, see docs/ARCHITECTURE.md (Mirror).
static const MirrorStep g_mirrorSteps[] = {
    { ID_BUTTON_INDEX,           false },
    { ID_BUTTON_CLOSE_DATE,      true  },
    { ID_BUTTON_NONHBP_MI,       true  },
    { ID_BUTTON_STR,             false },
    { ID_BUTTON_TPP_LHPP,        false },
    { ID_BUTTON_COST,            true  },
    { ID_BUTTON_CASE_UNIT_NAMES, true  },
};

// Buttons Mirror doesn't run but disables while it runs, because their scripts share the Ark
// login (session.json) with Mirror's steps (test_wiring checks every such script is covered).
static const int g_lockedDuringMirror[] = {
    ID_BUTTON_PPIQ, ID_BUTTON_AOI, ID_BUTTON_DOWNLOAD,
};

// True if id is one of g_mirrorSteps. WM_CREATE makes those buttons owner-drawn so WM_DRAWITEM can paint them green.
bool IsMirrorButton(int id) {
    for (const MirrorStep& step : g_mirrorSteps) {
        if (step.buttonId == id) return true;
    }
    return false;
}

// Writes the folder holding phxcpp.exe (and the scripts next to it), with a trailing backslash,
// into out (MAX_PATH), so scripts are found whatever the working directory.
static void GetExeDir(TCHAR* out) {
    GetModuleFileName(NULL, out, MAX_PATH);
    TCHAR* slash = _tcsrchr(out, TEXT('\\'));
    if (slash) *(slash + 1) = TEXT('\0');
}

// Starts `py "<exeDir><script>" <args>` with no console window and returns at once: the script
// shows its own message boxes (and its browser window, if any, is the progress indicator).
// Shows an error box if Python can't be started. Used by every one-script button.
static void LaunchScript(HWND hwnd, const TCHAR* script, const TCHAR* args = TEXT("")) {
    TCHAR exeDir[MAX_PATH] = {};
    GetExeDir(exeDir);
    TCHAR cmd[4096] = {};
    wsprintf(cmd, TEXT("py \"%s%s\"%s%s"), exeDir, script, args[0] ? TEXT(" ") : TEXT(""), args);

    STARTUPINFO si = { sizeof(si) };
    PROCESS_INFORMATION pi = {};
    if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    } else {
        TCHAR msg[512] = {};
        wsprintf(msg, TEXT("Could not launch %s%s%s.\nEnsure Python is installed and available in your PATH."),
                 script, args[0] ? TEXT(" ") : TEXT(""), args);
        MessageBox(hwnd, msg, TEXT("Error"), MB_ICONERROR);
    }
}

// Runs map_builder.py to completion, then map_uploader.py, relabeling the Maps button to
// show which phase is running (upload can take about a minute). Off the UI thread so
// waiting on the scripts doesn't freeze the window; each script also shows its own
// completion/error message box.
// Heap-allocated by the Maps click handler and deleted by RunMapThenUpload when it finishes.
struct MapUploadThreadArgs {
    HWND hwnd;               // main window (owner for message boxes; parent of the Maps button)
    TCHAR exeDir[MAX_PATH];  // folder containing phxcpp.exe, with trailing backslash
};

// Thread entry point started by the Maps button. Disables the button while running.
DWORD WINAPI RunMapThenUpload(LPVOID param) {
    MapUploadThreadArgs* args = (MapUploadThreadArgs*)param;
    HWND hButton = GetDlgItem(args->hwnd, ID_BUTTON_MAP);

    EnableWindow(hButton, FALSE);
    SetWindowText(hButton, TEXT("Building..."));

    TCHAR buildCmd[4096] = {};
    wsprintf(buildCmd, TEXT("py \"%smap_builder.py\""), args->exeDir);

    STARTUPINFO si = { sizeof(si) };
    PROCESS_INFORMATION pi = {};
    if (CreateProcess(NULL, buildCmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, INFINITE);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    } else {
        MessageBox(args->hwnd,
            TEXT("Could not launch map_builder.py.\n")
            TEXT("Ensure Python is installed and available in your PATH."),
            TEXT("Error"), MB_ICONERROR);
        SetWindowText(hButton, TEXT("Maps"));
        EnableWindow(hButton, TRUE);
        delete args;
        return 0;
    }

    SetWindowText(hButton, TEXT("Uploading..."));

    TCHAR uploadCmd[4096] = {};
    wsprintf(uploadCmd, TEXT("py \"%smap_uploader.py\""), args->exeDir);

    STARTUPINFO si2 = { sizeof(si2) };
    PROCESS_INFORMATION pi2 = {};
    if (CreateProcess(NULL, uploadCmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si2, &pi2)) {
        WaitForSingleObject(pi2.hProcess, INFINITE);
        CloseHandle(pi2.hThread);
        CloseHandle(pi2.hProcess);
    } else {
        MessageBox(args->hwnd,
            TEXT("Could not launch map_uploader.py.\n")
            TEXT("Ensure Python is installed and available in your PATH."),
            TEXT("Error"), MB_ICONERROR);
    }

    SetWindowText(hButton, TEXT("Maps"));
    EnableWindow(hButton, TRUE);
    delete args;
    return 0;
}

// Runs the three doc inventory scripts back to back (Roosevelt, Richland, Divide counties),
// relabeling the Index button to show which county is running. Off the UI thread so waiting
// on the scripts doesn't freeze the window; a message box reports if any script fails to launch.
// Heap-allocated by the Index click handler and deleted by RunIndexScripts when it finishes.
struct IndexRunThreadArgs {
    HWND hwnd;               // main window (owner of the button, progress bar and status label)
    TCHAR exeDir[MAX_PATH];  // folder containing phxcpp.exe, with trailing backslash
};

// Reads one doc_inventory_*.py's stdout line by line (RunScriptLines, mirror.cpp) looking for the machine-readable
// tags it prints alongside its normal human-readable output:
//   "@PROGRESS <done> <total>"  (total is -1 when the script doesn't pre-count files)
//   "@DONE <processed>"
// Tags are matched anywhere in a line, because the scripts print a "\rProcessing: ..."
// line with no newline just before each @PROGRESS, so the tag lands mid-line.
// Updates the progress bar/status label live and returns the final processed count,
// or -1 if the script could not be launched (an error box has already been shown).
// indeterminate = show a marquee bar instead of a percentage (used for Richland).
static int RunOneIndexScript(HWND hwndMain, HWND hProgress, HWND hStatus,
                              const TCHAR* exeDir, const TCHAR* script,
                              const TCHAR* county, bool indeterminate) {
    LONG_PTR style = GetWindowLongPtr(hProgress, GWL_STYLE);
    if (indeterminate) {
        SetWindowLongPtr(hProgress, GWL_STYLE, style | PBS_MARQUEE);
        SendMessage(hProgress, PBM_SETMARQUEE, TRUE, 30);
    } else {
        SendMessage(hProgress, PBM_SETMARQUEE, FALSE, 0);
        SetWindowLongPtr(hProgress, GWL_STYLE, style & ~PBS_MARQUEE);
        SendMessage(hProgress, PBM_SETPOS, 0, 0);
    }

    TCHAR statusBuf[256] = {};
    wsprintf(statusBuf, TEXT("%s: starting..."), county);
    SetWindowText(hStatus, statusBuf);

    TCHAR cmd[4096] = {};
    wsprintf(cmd, TEXT("py \"%s%s\""), exeDir, script);

    int processed = 0;
    bool launched = RunScriptLines(cmd, [&](const std::string& line) {
        size_t progressAt = line.find("@PROGRESS ");
        size_t doneAt     = line.find("@DONE ");
        if (progressAt != std::string::npos) {
            int done = 0, total = -1;
            sscanf(line.c_str() + progressAt + 10, "%d %d", &done, &total);
            if (total > 0) {
                SendMessage(hProgress, PBM_SETPOS, (int)(((long long)done * 100) / total), 0);
                wsprintf(statusBuf, TEXT("%s: %d / %d"), county, done, total);
            } else {
                wsprintf(statusBuf, TEXT("%s: %d processed"), county, done);
            }
            SetWindowText(hStatus, statusBuf);
        } else if (doneAt != std::string::npos) {
            processed = atoi(line.c_str() + doneAt + 6);
        }
    });
    if (!launched) {
        TCHAR msg[512] = {};
        wsprintf(msg, TEXT("Could not launch %s.\nEnsure Python is installed and available in your PATH."), script);
        MessageBox(hwndMain, msg, TEXT("Error"), MB_ICONERROR);
        return -1;
    }

    if (!indeterminate) SendMessage(hProgress, PBM_SETPOS, 100, 0);
    return processed;
}

// Thread entry point started by the Index button. Shows the progress bar/status label,
// calls RunOneIndexScript once per county (stopping early if a launch fails), then hides
// them and shows a "New documents added" summary.
DWORD WINAPI RunIndexScripts(LPVOID param) {
    IndexRunThreadArgs* args = (IndexRunThreadArgs*)param;
    HWND hButton   = GetDlgItem(args->hwnd, ID_BUTTON_INDEX);
    HWND hProgress = GetDlgItem(args->hwnd, ID_PROGRESS_INDEX);
    HWND hStatus   = GetDlgItem(args->hwnd, ID_LABEL_INDEX_STATUS);

    struct { const TCHAR* script; const TCHAR* county; bool indeterminate; } steps[] = {
        { TEXT("doc_inventory_roosevelt.py"), TEXT("Roosevelt"), false },
        { TEXT("doc_inventory_richland.py"),  TEXT("Richland"),  true  },
        { TEXT("doc_inventory_divide.py"),    TEXT("Divide"),    false },
    };
    const int kNumSteps = 3;
    int added[kNumSteps] = { 0, 0, 0 };

    EnableWindow(hButton, FALSE);
    SendMessage(hProgress, PBM_SETRANGE32, 0, 100);
    ShowWindow(hProgress, SW_SHOW);
    ShowWindow(hStatus, SW_SHOW);

    for (int i = 0; i < kNumSteps; i++) {
        SetWindowText(hButton, steps[i].county);
        int processed = RunOneIndexScript(args->hwnd, hProgress, hStatus, args->exeDir,
                                           steps[i].script, steps[i].county, steps[i].indeterminate);
        if (processed < 0) break;  // launch failed; error already shown
        added[i] = processed;
    }

    SendMessage(hProgress, PBM_SETMARQUEE, FALSE, 0);
    ShowWindow(hProgress, SW_HIDE);
    ShowWindow(hStatus, SW_HIDE);
    SetWindowText(hButton, TEXT("Index"));
    EnableWindow(hButton, TRUE);

    TCHAR summary[512] = {};
    wsprintf(summary, TEXT("New documents added:\n\nRoosevelt: %d\nRichland: %d\nDivide: %d"),
              added[0], added[1], added[2]);
    MessageBox(args->hwnd, summary, TEXT("Index Complete"), MB_ICONINFORMATION);

    delete args;
    return 0;
}

// Positions every control in the main window: Mirror in the top-left corner, title across the
// top, a header label over each of the four 200px button columns, Settings pinned bottom-left, and the Index / Mirror progress
// bar and status pinned bottom-right (same spot: the two never run at once).
// Called from WM_CREATE and on every WM_SIZE. A new button needs a line here AND an
// entry in the buttons[] table in WM_CREATE.
void LayoutControls(HWND hwnd) {
    RECT rc;
    GetClientRect(hwnd, &rc);
    int w = rc.right;

    // Mirror sits in the top-left corner, outside the columns; the title keeps clear of it on
    // both sides so it stays centered
    int mirrorW = 120, titleMargin = 10 + mirrorW + 10;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_MIRROR), 10, 15, mirrorW, 40, TRUE);

    HWND hTitle = GetDlgItem(hwnd, ID_TITLE);
    MoveWindow(hTitle, titleMargin, 10, w > 2 * titleMargin ? w - 2 * titleMargin : 0, 50, TRUE);
    InvalidateRect(hTitle, NULL, TRUE);

    int bw = 200, bh = 30, gap = 10, headerY = 70, headerH = 22, y0 = headerY + headerH + 6;
    int c1 = 10, c2 = c1 + bw + gap, c3 = c2 + bw + gap, c4 = c3 + bw + gap;

    // Column headers, one over each column
    int columnX[] = { c1, c2, c3, c4 };
    for (int i = 0; i < 4; i++) {
        MoveWindow(GetDlgItem(hwnd, ID_COLUMN_HEADER + i), columnX[i], headerY, bw, headerH, TRUE);
    }

    // Column 1
    int y = y0;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_CLOSE_DATE), c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_NONHBP_MI), c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_INDEX),    c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_CASE_UNIT_NAMES), c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_STR),      c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_TPP_LHPP), c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_COST),     c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_DOCKET_UPDATES), c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_DOCKET_UPDATES_SLACK), c1, y, bw, bh, TRUE);

    // Settings pinned to bottom-left
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_SETTINGS),  c1, rc.bottom - bh - gap, 90, bh, TRUE);

    // Index run status pinned to bottom-right (hidden except while Index is running)
    int barW = 220, statusW = 260, rightMargin = 20;
    int barX = rc.right - rightMargin - barW;
    int statusX = barX - gap - statusW;
    MoveWindow(GetDlgItem(hwnd, ID_LABEL_INDEX_STATUS), statusX, rc.bottom - bh - gap + 6, statusW, bh - 6, TRUE);
    MoveWindow(GetDlgItem(hwnd, ID_PROGRESS_INDEX),     barX,    rc.bottom - bh - gap,     barW,    bh,     TRUE);

    // Mirror run status: same spot, wider label (stage name + elapsed time)
    int mirrorStatusW = 440;
    MoveWindow(GetDlgItem(hwnd, ID_LABEL_MIRROR_STATUS), barX - gap - mirrorStatusW, rc.bottom - bh - gap + 6,
               mirrorStatusW, bh - 6, TRUE);
    MoveWindow(GetDlgItem(hwnd, ID_PROGRESS_MIRROR), barX, rc.bottom - bh - gap, barW, bh, TRUE);

    // Column 2
    y = y0;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_PPIQ),     c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_AOI),      c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_DOWNLOAD), c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_ORGANIZE), c2, y, bw, bh, TRUE);

    // Column 3
    y = y0;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_CASE_MATCHUP), c3, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_DECEASED), c3, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_RENAME),   c3, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_MAP),      c3, y, bw, bh, TRUE);

    // Column 4
    y = y0;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_ELMI),     c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_DNM),      c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_HBPNW),    c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_LE),       c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_LHP),      c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_NHBPW),    c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_SIB),      c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_UNLE),     c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_SL),       c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_HBP_WELLS), c4, y, bw, bh, TRUE);
}

// Called by Windows for every event (paint, close, etc.) that happens to the main window.
//   WM_CREATE         create fonts, title, column headers, all buttons (g_disabledButtonIds greyed out), and the
//                     hidden Index / Mirror progress controls
//   WM_SIZE           re-run LayoutControls
//   WM_CTLCOLORSTATIC give static labels the gray background
//   WM_DRAWITEM       paint owner-drawn buttons: unwired yellow, Mirror steps faint green
//   WM_COMMAND        button click dispatch: one branch per button id (Mirror: Start or Stop)
//   WM_DESTROY        free fonts and quit the message loop
LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        case WM_CREATE: {
            INITCOMMONCONTROLSEX icc = { sizeof(icc), ICC_PROGRESS_CLASS };
            InitCommonControlsEx(&icc);

            g_hTitleFont = CreateFont(
                -32, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE,
                DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_SWISS, TEXT("Segoe UI")
            );
            g_hButtonFont = CreateFont(
                -13, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_SWISS, TEXT("Segoe UI")
            );

            g_hHeaderFont = CreateFont(
                -15, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE,
                DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_SWISS, TEXT("Segoe UI")
            );

            HWND hTitle = CreateWindowEx(
                0, TEXT("STATIC"), TEXT("Phoenix Land Department Reporting"),
                WS_CHILD | WS_VISIBLE | SS_CENTER | SS_NOPREFIX,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_TITLE,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            SendMessage(hTitle, WM_SETFONT, (WPARAM)g_hTitleFont, TRUE);

            // Column headers — LayoutControls places each over its column
            for (int i = 0; i < 4; i++) {
                HWND hHeader = CreateWindowEx(
                    0, TEXT("STATIC"), g_columnHeaders[i],
                    WS_CHILD | WS_VISIBLE | SS_CENTER | SS_NOPREFIX,
                    0, 0, 0, 0,
                    hwnd, (HMENU)(UINT_PTR)(ID_COLUMN_HEADER + i),
                    ((LPCREATESTRUCT)lParam)->hInstance, NULL
                );
                SendMessage(hHeader, WM_SETFONT, (WPARAM)g_hHeaderFont, FALSE);
            }

            // All buttons — LayoutControls handles column placement
            struct { int id; const TCHAR* label; } buttons[] = {
                // Top-left corner
                { ID_BUTTON_MIRROR,      TEXT("Mirror")                },
                // Column 1
                { ID_BUTTON_CLOSE_DATE,  TEXT("Close Date")            },
                { ID_BUTTON_NONHBP_MI,   TEXT("Case Update")           },
                { ID_BUTTON_INDEX,       TEXT("Index")                 },
                { ID_BUTTON_CASE_UNIT_NAMES, TEXT("Cases Unit Names")  },
                { ID_BUTTON_STR,         TEXT("STR")                   },
                { ID_BUTTON_TPP_LHPP,    TEXT("TPP-LHPP")             },
                { ID_BUTTON_COST,        TEXT("C2E")                   },
                { ID_BUTTON_DOCKET_UPDATES, TEXT("Docket Updates")     },
                { ID_BUTTON_DOCKET_UPDATES_SLACK, TEXT("Docket Updates Slack") },
                { ID_BUTTON_SETTINGS,    TEXT("Settings")              },
                // Column 2
                { ID_BUTTON_PPIQ,        TEXT("PPIQ")                 },
                { ID_BUTTON_AOI,         TEXT("AOI")                   },
                { ID_BUTTON_DOWNLOAD,    TEXT("DMD")                   },
                { ID_BUTTON_ORGANIZE,    TEXT("Organization")          },
                // Column 3
                { ID_BUTTON_CASE_MATCHUP, TEXT("Unit Connect to Cases") },
                { ID_BUTTON_DECEASED,    TEXT("Bring out your dead")   },
                { ID_BUTTON_RENAME,      TEXT("Rename")                },
                { ID_BUTTON_MAP,         TEXT("Maps")                  },
                // Column 4
                { ID_BUTTON_ELMI,        TEXT("ELMI")                  },
                { ID_BUTTON_DNM,         TEXT("DNM")                   },
                { ID_BUTTON_HBPNW,       TEXT("HBPNW")                 },
                { ID_BUTTON_LE,          TEXT("LE")                    },
                { ID_BUTTON_LHP,         TEXT("LHP")                   },
                { ID_BUTTON_NHBPW,       TEXT("NHBPW")                 },
                { ID_BUTTON_SIB,         TEXT("SIB")                   },
                { ID_BUTTON_UNLE,        TEXT("UNLE")                  },
                { ID_BUTTON_SL,          TEXT("SL")                    },
                { ID_BUTTON_HBP_WELLS,   TEXT("HBP Wells")             },
            };
            for (auto& b : buttons) {
                DWORD style = WS_CHILD | WS_VISIBLE |
                    (IsUnwiredButton(b.id) || IsMirrorButton(b.id) ? (DWORD)BS_OWNERDRAW : (DWORD)BS_PUSHBUTTON);
                HWND hBtn = CreateWindowEx(
                    0, TEXT("BUTTON"), b.label,
                    style,
                    0, 0, 0, 0,
                    hwnd, (HMENU)(UINT_PTR)b.id,
                    ((LPCREATESTRUCT)lParam)->hInstance, NULL
                );
                SendMessage(hBtn, WM_SETFONT, (WPARAM)g_hButtonFont, FALSE);
                if (IsDisabledButton(b.id)) EnableWindow(hBtn, FALSE);
            }

            // Index run status — created hidden, shown only while the Index button is running
            HWND hIndexStatus = CreateWindowEx(
                0, TEXT("STATIC"), TEXT(""),
                WS_CHILD | SS_LEFT | SS_NOPREFIX,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_LABEL_INDEX_STATUS,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            SendMessage(hIndexStatus, WM_SETFONT, (WPARAM)g_hButtonFont, FALSE);

            CreateWindowEx(
                0, PROGRESS_CLASS, NULL,
                WS_CHILD | PBS_SMOOTH,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_PROGRESS_INDEX,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );

            // Mirror run status — created hidden, shown only while Mirror is running
            HWND hMirrorStatus = CreateWindowEx(
                0, TEXT("STATIC"), TEXT(""),
                WS_CHILD | SS_LEFT | SS_NOPREFIX,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_LABEL_MIRROR_STATUS,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            SendMessage(hMirrorStatus, WM_SETFONT, (WPARAM)g_hButtonFont, FALSE);

            CreateWindowEx(
                0, PROGRESS_CLASS, NULL,
                WS_CHILD | PBS_SMOOTH,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_PROGRESS_MIRROR,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );

            LayoutControls(hwnd);
            return 0;
        }
        case WM_SIZE:
            LayoutControls(hwnd);
            return 0;
        case WM_CTLCOLORSTATIC: {
            HDC hdc = (HDC)wParam;
            SetBkColor(hdc, RGB(240, 240, 240));
            SetTextColor(hdc, RGB(0, 0, 0));
            return (LRESULT)g_hBgBrush;
        }
        case WM_DRAWITEM: {
            LPDRAWITEMSTRUCT dis = (LPDRAWITEMSTRUCT)lParam;
            if (dis->CtlType != ODT_BUTTON) break;

            bool pressed  = (dis->itemState & ODS_SELECTED) != 0;
            bool disabled = (dis->itemState & ODS_DISABLED) != 0;  // e.g. a Mirror step while Mirror runs
            FillRect(dis->hDC, &dis->rcItem, IsUnwiredButton((int)dis->CtlID) ? g_hYellowBrush : g_hGreenBrush);
            FrameRect(dis->hDC, &dis->rcItem, (HBRUSH)GetStockObject(GRAY_BRUSH));

            TCHAR text[256];
            GetWindowText(dis->hwndItem, text, 256);
            SetBkMode(dis->hDC, TRANSPARENT);
            SetTextColor(dis->hDC, disabled ? GetSysColor(COLOR_GRAYTEXT) : RGB(0, 0, 0));
            HFONT hOldFont = (HFONT)SelectObject(dis->hDC, g_hButtonFont);
            RECT textRect = dis->rcItem;
            if (pressed) OffsetRect(&textRect, 1, 1);
            DrawText(dis->hDC, text, -1, &textRect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            SelectObject(dis->hDC, hOldFont);

            if (dis->itemState & ODS_FOCUS) DrawFocusRect(dis->hDC, &dis->rcItem);
            return TRUE;
        }
        case WM_COMMAND: {
            // A greyed-out button ignores mouse clicks, but a BM_CLICK sent to it still arrives here
            if (IsDisabledButton(LOWORD(wParam))) return 0;
            if (LOWORD(wParam) == ID_BUTTON_MIRROR && IsMirrorRunning()) {
                StopMirror(hwnd);  // the button reads "Stop" while Mirror runs
            } else if (LOWORD(wParam) == ID_BUTTON_MIRROR) {
                StartMirror(hwnd, TEXT("mirror.py"), ID_BUTTON_MIRROR, ID_PROGRESS_MIRROR, ID_LABEL_MIRROR_STATUS,
                            g_mirrorSteps, (int)(sizeof(g_mirrorSteps) / sizeof(g_mirrorSteps[0])),
                            g_lockedDuringMirror, (int)(sizeof(g_lockedDuringMirror) / sizeof(g_lockedDuringMirror[0])));
            } else if (LOWORD(wParam) == ID_BUTTON_PPIQ) {
                LaunchScript(hwnd, TEXT("ppiq.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_INDEX) {
                IndexRunThreadArgs* args = new IndexRunThreadArgs();
                args->hwnd = hwnd;
                GetExeDir(args->exeDir);

                HANDLE hThread = CreateThread(NULL, 0, RunIndexScripts, args, 0, NULL);
                if (hThread) {
                    CloseHandle(hThread);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not start the Index scripts."),
                        TEXT("Error"), MB_ICONERROR);
                    delete args;
                }
            } else if (LOWORD(wParam) == ID_BUTTON_TPP_LHPP) {
                LaunchScript(hwnd, TEXT("tpp_lhpp.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_COST) {
                LaunchScript(hwnd, TEXT("cost_to_extend.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_SETTINGS) {
                OpenSettings(hwnd);
            } else if (LOWORD(wParam) == ID_BUTTON_DOWNLOAD) {
                LaunchScript(hwnd, TEXT("download_report.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_ELMI) {
                // TODO: implement ELMI
            } else if (LOWORD(wParam) == ID_BUTTON_DNM) {
                // TODO: implement DNM
            } else if (LOWORD(wParam) == ID_BUTTON_HBPNW) {
                // TODO: implement HBPNW
            } else if (LOWORD(wParam) == ID_BUTTON_LE) {
                // TODO: implement LE
            } else if (LOWORD(wParam) == ID_BUTTON_LHP) {
                // TODO: implement LHP
            } else if (LOWORD(wParam) == ID_BUTTON_NHBPW) {
                // TODO: implement NHBPW
            } else if (LOWORD(wParam) == ID_BUTTON_SIB) {
                // TODO: implement SIB
            } else if (LOWORD(wParam) == ID_BUTTON_UNLE) {
                // TODO: implement UNLE
            } else if (LOWORD(wParam) == ID_BUTTON_SL) {
                // TODO: implement SL
            } else if (LOWORD(wParam) == ID_BUTTON_DECEASED) {
                LaunchScript(hwnd, TEXT("deceased.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_HBP_WELLS) {
                // TODO: implement HBP Wells
            } else if (LOWORD(wParam) == ID_BUTTON_CLOSE_DATE) {
                LaunchScript(hwnd, TEXT("close_dates.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_NONHBP_MI) {
                LaunchScript(hwnd, TEXT("non_hbp_mi.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_DOCKET_UPDATES) {
                LaunchScript(hwnd, TEXT("docket_updates.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_DOCKET_UPDATES_SLACK) {
                // Only reachable once the button is taken out of g_disabledButtonIds
                LaunchScript(hwnd, TEXT("docket_updates_slack.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_ORGANIZE) {
                OpenOrganize(hwnd);
            } else if (LOWORD(wParam) == ID_BUTTON_CASE_MATCHUP) {
                LaunchScript(hwnd, TEXT("case_matchup.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_RENAME) {
                OpenRename(hwnd);
            } else if (LOWORD(wParam) == ID_BUTTON_CASE_UNIT_NAMES) {
                LaunchScript(hwnd, TEXT("case_unit_names.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_MAP) {
                MapUploadThreadArgs* args = new MapUploadThreadArgs();
                args->hwnd = hwnd;
                GetExeDir(args->exeDir);

                HANDLE hThread = CreateThread(NULL, 0, RunMapThenUpload, args, 0, NULL);
                if (hThread) {
                    CloseHandle(hThread);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not start the map build/upload process."),
                        TEXT("Error"), MB_ICONERROR);
                    delete args;
                }
            } else if (LOWORD(wParam) == ID_BUTTON_STR) {
                LaunchScript(hwnd, TEXT("str_verification.py"));
            } else if (LOWORD(wParam) == ID_BUTTON_AOI) {
                // Same script as STR; --aoi makes it write only the Area of Interest report
                LaunchScript(hwnd, TEXT("str_verification.py"), TEXT("--aoi"));
            }
            return 0;
        }
        case WM_DESTROY:
            if (g_hTitleFont)  DeleteObject(g_hTitleFont);
            if (g_hButtonFont) DeleteObject(g_hButtonFont);
            if (g_hHeaderFont) DeleteObject(g_hHeaderFont);
            PostQuitMessage(0);
            return 0;
    }
    // Let Windows handle any messages we don't care about
    return DefWindowProc(hwnd, msg, wParam, lParam);
}

// Entry point for a Windows GUI application (equivalent to main()).
// Initializes COM (needed by the Settings folder picker), loads saved settings from
// settings.ini, registers the main and dialog window classes, then runs the message loop.
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR, int nCmdShow) {
    CoInitialize(NULL);

    LoadSettings();

    g_hBgBrush     = CreateSolidBrush(RGB(240, 240, 240));
    g_hYellowBrush = CreateSolidBrush(RGB(255, 255, 153));
    g_hGreenBrush  = CreateSolidBrush(RGB(214, 240, 214));

    const TCHAR CLASS_NAME[] = TEXT("MainWindow");

    WNDCLASSEX wc    = { sizeof(WNDCLASSEX) };
    wc.lpfnWndProc   = WndProc;
    wc.hInstance     = hInstance;
    wc.lpszClassName = CLASS_NAME;
    wc.hbrBackground = g_hBgBrush;
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    wc.hIcon         = LoadIcon(hInstance, MAKEINTRESOURCE(1));
    wc.hIconSm       = LoadIcon(hInstance, MAKEINTRESOURCE(1));
    RegisterClassEx(&wc);

    RegisterSettingsClass(hInstance);     // register the settings window class defined in settings.cpp
    RegisterOrganizeClass(hInstance);     // register the classify dialog class used by Organization
    RegisterRenameClass(hInstance);       // register the dialog class used by Rename

    g_hwndMain = CreateWindowEx(
        0, CLASS_NAME, TEXT("Phoenix Land Department Reporting"),
        WS_OVERLAPPEDWINDOW,                           // standard resizable window style
        CW_USEDEFAULT, CW_USEDEFAULT, 1500, 900,       // position and size
        NULL, NULL, hInstance, NULL
    );

    ShowWindow(g_hwndMain, nCmdShow);  // make the window visible using the show state passed by Windows (e.g. normal, maximized)
    UpdateWindow(g_hwndMain);          // force an immediate paint

    MSG msg = {};
    while (GetMessage(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    CoUninitialize();
    if (g_hBgBrush) DeleteObject(g_hBgBrush);
    if (g_hYellowBrush) DeleteObject(g_hYellowBrush);
    if (g_hGreenBrush) DeleteObject(g_hGreenBrush);
    return (int)msg.wParam;
}
