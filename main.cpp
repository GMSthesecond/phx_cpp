#include <windows.h>
#include <commctrl.h>
#include <tchar.h>
#include <string>
#include <cstdio>
#include <cstdlib>
#include "settings.h"
#include "project_correlation.h"
#include "organize.h"
#include "rename.h"

// Enable visual styles (modern button rendering) without a separate .manifest file
#pragma comment(lib, "comctl32.lib")
#pragma comment(linker, "/manifestdependency:\"type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")

// Control IDs used only in the main window
#define ID_TITLE                3
#define ID_BUTTON_SETTINGS      6
#define ID_BUTTON_DOWNLOAD      9
#define ID_BUTTON_STR          10
#define ID_BUTTON_CORR         15
#define ID_BUTTON_PPIQ         20
#define ID_BUTTON_INDEX        21
#define ID_BUTTON_TPP_LHPP     22
#define ID_BUTTON_COST         23
// Column 2
#define ID_BUTTON_ELMI         30
#define ID_BUTTON_DNM          31
#define ID_BUTTON_HBPNW        32
#define ID_BUTTON_LE           33
#define ID_BUTTON_LHP          34
#define ID_BUTTON_NHBPW        35
#define ID_BUTTON_SIB          36
#define ID_BUTTON_UNLE         37
#define ID_BUTTON_SL           38
// Column 3
#define ID_BUTTON_DECEASED     40
#define ID_BUTTON_HBP_WELLS    41
#define ID_BUTTON_ORGANIZE     44
#define ID_BUTTON_CASE_MATCHUP 46
#define ID_BUTTON_RENAME       47
// Column 4
#define ID_BUTTON_CLOSE_DATE   43
#define ID_BUTTON_NONHBP_MI    45
// Column 5
#define ID_BUTTON_MAP          48
// Index run status (hidden except while the Index button is running)
#define ID_PROGRESS_INDEX      49
#define ID_LABEL_INDEX_STATUS  50

HFONT  g_hTitleFont   = NULL;
HFONT  g_hButtonFont  = NULL;
HBRUSH g_hBgBrush     = NULL;
HBRUSH g_hYellowBrush = NULL;
HWND   g_hwndMain     = NULL;

// Buttons whose click handler is not implemented yet — drawn light yellow as a visual "not done" cue
static const int g_unwiredButtonIds[] = {
    ID_BUTTON_ELMI, ID_BUTTON_DNM, ID_BUTTON_HBPNW, ID_BUTTON_LE, ID_BUTTON_LHP,
    ID_BUTTON_NHBPW, ID_BUTTON_SIB, ID_BUTTON_UNLE, ID_BUTTON_SL,
    ID_BUTTON_HBP_WELLS,
};

bool IsUnwiredButton(int id) {
    for (int candidate : g_unwiredButtonIds) {
        if (candidate == id) return true;
    }
    return false;
}

// Runs map_builder.py to completion, then map_uploader.py, relabeling the Map button to
// show which phase is running (upload can take about a minute). Off the UI thread so
// waiting on the scripts doesn't freeze the window; each script also shows its own
// completion/error message box.
struct MapUploadThreadArgs {
    HWND hwnd;
    TCHAR exeDir[MAX_PATH];
};

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
        SetWindowText(hButton, TEXT("Map"));
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

    SetWindowText(hButton, TEXT("Map"));
    EnableWindow(hButton, TRUE);
    delete args;
    return 0;
}

// Runs the three doc inventory scripts back to back (Roosevelt, Richland, Divide counties),
// relabeling the Index button to show which county is running. Off the UI thread so waiting
// on the scripts doesn't freeze the window; a message box reports if any script fails to launch.
struct IndexRunThreadArgs {
    HWND hwnd;
    TCHAR exeDir[MAX_PATH];
};

// Reads one doc_inventory_*.py's stdout line by line looking for the machine-readable
// tags it prints alongside its normal human-readable output:
//   "@PROGRESS <done> <total>"  (total is -1 when the script doesn't pre-count files)
//   "@DONE <processed>"
// Updates the progress bar/status label live and returns the final processed count.
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

    SECURITY_ATTRIBUTES sa = { sizeof(sa), NULL, TRUE };
    HANDLE hReadPipe = NULL, hWritePipe = NULL;
    if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0)) {
        TCHAR msg[512] = {};
        wsprintf(msg, TEXT("Could not create a pipe for %s."), script);
        MessageBox(hwndMain, msg, TEXT("Error"), MB_ICONERROR);
        return -1;
    }
    SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0);
    HANDLE hNul = CreateFile(TEXT("NUL"), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              &sa, OPEN_EXISTING, 0, NULL);

    STARTUPINFO si = { sizeof(si) };
    si.dwFlags    = STARTF_USESTDHANDLES;
    si.hStdOutput = hWritePipe;
    si.hStdError  = hWritePipe;
    si.hStdInput  = hNul;

    PROCESS_INFORMATION pi = {};
    BOOL created = CreateProcess(NULL, cmd, NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    CloseHandle(hWritePipe);
    if (hNul != INVALID_HANDLE_VALUE) CloseHandle(hNul);

    if (!created) {
        CloseHandle(hReadPipe);
        TCHAR msg[512] = {};
        wsprintf(msg, TEXT("Could not launch %s.\nEnsure Python is installed and available in your PATH."), script);
        MessageBox(hwndMain, msg, TEXT("Error"), MB_ICONERROR);
        return -1;
    }

    int processed = 0;
    std::string pending;
    char buf[4096];
    DWORD bytesRead = 0;
    while (ReadFile(hReadPipe, buf, sizeof(buf), &bytesRead, NULL) && bytesRead > 0) {
        pending.append(buf, bytesRead);

        size_t pos;
        while ((pos = pending.find_first_of("\r\n")) != std::string::npos) {
            std::string line = pending.substr(0, pos);
            pending.erase(0, pos + 1);
            if (line.empty()) continue;

            if (line.rfind("@PROGRESS ", 0) == 0) {
                int done = 0, total = -1;
                sscanf(line.c_str() + 10, "%d %d", &done, &total);
                if (total > 0) {
                    SendMessage(hProgress, PBM_SETPOS, (int)(((long long)done * 100) / total), 0);
                    wsprintf(statusBuf, TEXT("%s: %d / %d"), county, done, total);
                } else {
                    wsprintf(statusBuf, TEXT("%s: %d processed"), county, done);
                }
                SetWindowText(hStatus, statusBuf);
            } else if (line.rfind("@DONE ", 0) == 0) {
                processed = atoi(line.c_str() + 6);
            }
        }
    }
    CloseHandle(hReadPipe);

    WaitForSingleObject(pi.hProcess, INFINITE);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);

    if (!indeterminate) SendMessage(hProgress, PBM_SETPOS, 100, 0);
    return processed;
}

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

void LayoutControls(HWND hwnd) {
    RECT rc;
    GetClientRect(hwnd, &rc);
    int w = rc.right;

    HWND hTitle = GetDlgItem(hwnd, ID_TITLE);
    MoveWindow(hTitle, 0, 10, w, 50, TRUE);
    InvalidateRect(hTitle, NULL, TRUE);

    int bw = 200, bh = 30, gap = 10, y0 = 70;
    int c1 = 10, c2 = c1 + bw + gap, c3 = c2 + bw + gap, c4 = c3 + bw + gap, c5 = c4 + bw + gap;

    // Column 1
    int y = y0;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_PPIQ),      c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_INDEX),     c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_STR),       c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_TPP_LHPP),  c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_DOWNLOAD),  c1, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_COST),      c1, y, bw, bh, TRUE);

    // Settings pinned to bottom-left
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_SETTINGS),  c1, rc.bottom - bh - gap, 90, bh, TRUE);

    // Index run status pinned to bottom-right (hidden except while Index is running)
    int barW = 220, statusW = 260, rightMargin = 20;
    int barX = rc.right - rightMargin - barW;
    int statusX = barX - gap - statusW;
    MoveWindow(GetDlgItem(hwnd, ID_LABEL_INDEX_STATUS), statusX, rc.bottom - bh - gap + 6, statusW, bh - 6, TRUE);
    MoveWindow(GetDlgItem(hwnd, ID_PROGRESS_INDEX),     barX,    rc.bottom - bh - gap,     barW,    bh,     TRUE);

    // Column 2
    y = y0;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_ELMI),      c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_DNM),       c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_HBPNW),     c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_LE),        c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_LHP),       c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_NHBPW),     c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_SIB),       c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_UNLE),      c2, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_SL),        c2, y, bw, bh, TRUE);

    // Column 3
    y = y0;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_DECEASED),    c3, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_HBP_WELLS),   c3, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_CORR),        c3, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_ORGANIZE),    c3, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_CASE_MATCHUP), c3, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_RENAME),      c3, y, bw, bh, TRUE);

    // Column 4
    y = y0;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_CLOSE_DATE),  c4, y, bw, bh, TRUE); y += bh + gap;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_NONHBP_MI),   c4, y, bw, bh, TRUE);

    // Column 5
    y = y0;
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_MAP),         c5, y, bw, bh, TRUE);
}

// Called by Windows for every event (paint, close, etc.) that happens to the main window
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

            HWND hTitle = CreateWindowEx(
                0, TEXT("STATIC"), TEXT("Phoenix Land Department Reporting"),
                WS_CHILD | WS_VISIBLE | SS_CENTER | SS_NOPREFIX,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_TITLE,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            SendMessage(hTitle, WM_SETFONT, (WPARAM)g_hTitleFont, TRUE);

            // All buttons — LayoutControls handles column placement
            struct { int id; const TCHAR* label; } buttons[] = {
                // Column 1
                { ID_BUTTON_PPIQ,        TEXT("PPIQ")                 },
                { ID_BUTTON_INDEX,       TEXT("Index")                 },
                { ID_BUTTON_STR,         TEXT("STR Verification")      },
                { ID_BUTTON_TPP_LHPP,    TEXT("TPP-LHPP")             },
                { ID_BUTTON_DOWNLOAD,    TEXT("Data Meeting Download")  },
                { ID_BUTTON_COST,        TEXT("Cost to Extend")        },
                { ID_BUTTON_CORR,        TEXT("Project Correlation")   },
                { ID_BUTTON_SETTINGS,    TEXT("Settings")              },
                // Column 2
                { ID_BUTTON_ELMI,        TEXT("ELMI")                  },
                { ID_BUTTON_DNM,         TEXT("DNM")                   },
                { ID_BUTTON_HBPNW,       TEXT("HBPNW")                 },
                { ID_BUTTON_LE,          TEXT("LE")                    },
                { ID_BUTTON_LHP,         TEXT("LHP")                   },
                { ID_BUTTON_NHBPW,       TEXT("NHBPW")                 },
                { ID_BUTTON_SIB,         TEXT("SIB")                   },
                { ID_BUTTON_UNLE,        TEXT("UNLE")                  },
                { ID_BUTTON_SL,          TEXT("SL")                    },
                // Column 3
                { ID_BUTTON_DECEASED,    TEXT("Deceased")              },
                { ID_BUTTON_HBP_WELLS,   TEXT("HBP Wells")             },
                { ID_BUTTON_ORGANIZE,    TEXT("Organize")              },
                { ID_BUTTON_CASE_MATCHUP, TEXT("Case Matchup")         },
                { ID_BUTTON_RENAME,      TEXT("Rename")                },
                // Column 4
                { ID_BUTTON_CLOSE_DATE,  TEXT("Close Date")            },
                { ID_BUTTON_NONHBP_MI,   TEXT("Case Update")           },
                // Column 5
                { ID_BUTTON_MAP,         TEXT("Map")                   },
            };
            for (auto& b : buttons) {
                DWORD style = WS_CHILD | WS_VISIBLE |
                    (IsUnwiredButton(b.id) ? (DWORD)BS_OWNERDRAW : (DWORD)BS_PUSHBUTTON);
                HWND hBtn = CreateWindowEx(
                    0, TEXT("BUTTON"), b.label,
                    style,
                    0, 0, 0, 0,
                    hwnd, (HMENU)(UINT_PTR)b.id,
                    ((LPCREATESTRUCT)lParam)->hInstance, NULL
                );
                SendMessage(hBtn, WM_SETFONT, (WPARAM)g_hButtonFont, FALSE);
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

            bool pressed = (dis->itemState & ODS_SELECTED) != 0;
            FillRect(dis->hDC, &dis->rcItem, g_hYellowBrush);
            FrameRect(dis->hDC, &dis->rcItem, (HBRUSH)GetStockObject(GRAY_BRUSH));

            TCHAR text[256];
            GetWindowText(dis->hwndItem, text, 256);
            SetBkMode(dis->hDC, TRANSPARENT);
            SetTextColor(dis->hDC, RGB(0, 0, 0));
            HFONT hOldFont = (HFONT)SelectObject(dis->hDC, g_hButtonFont);
            RECT textRect = dis->rcItem;
            if (pressed) OffsetRect(&textRect, 1, 1);
            DrawText(dis->hDC, text, -1, &textRect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            SelectObject(dis->hDC, hOldFont);

            if (dis->itemState & ODS_FOCUS) DrawFocusRect(dis->hDC, &dis->rcItem);
            return TRUE;
        }
        case WM_COMMAND: {
            if (LOWORD(wParam) == ID_BUTTON_PPIQ) {
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

                TCHAR cmd[4096] = {};
                wsprintf(cmd, TEXT("py \"%sppiq.py\""), exeDir);

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch ppiq.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
            } else if (LOWORD(wParam) == ID_BUTTON_INDEX) {
                IndexRunThreadArgs* args = new IndexRunThreadArgs();
                args->hwnd = hwnd;
                GetModuleFileName(NULL, args->exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(args->exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

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
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

                TCHAR cmd[4096] = {};
                wsprintf(cmd, TEXT("py \"%stpp_lhpp.py\""), exeDir);

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch tpp_lhpp.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
            } else if (LOWORD(wParam) == ID_BUTTON_COST) {
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

                TCHAR cmd[4096] = {};
                wsprintf(cmd, TEXT("py \"%scost_to_extend.py\""), exeDir);

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch cost_to_extend.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
            } else if (LOWORD(wParam) == ID_BUTTON_SETTINGS) {
                OpenSettings(hwnd);
            } else if (LOWORD(wParam) == ID_BUTTON_DOWNLOAD) {
                // Build the script path from the directory containing the EXE
                // so download_report.py is found regardless of the working directory
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0'); // strip filename, keep trailing backslash

                TCHAR cmd[4096] = {};
                wsprintf(cmd, TEXT("py \"%sdownload_report.py\""), exeDir);

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);   // we don't wait for the script to finish
                    CloseHandle(pi.hProcess);  // browser window acts as the progress indicator
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch download_report.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
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
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

                TCHAR cmd[4096] = {};
                wsprintf(cmd, TEXT("py \"%sdeceased.py\""), exeDir);

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch deceased.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
            } else if (LOWORD(wParam) == ID_BUTTON_HBP_WELLS) {
                // TODO: implement HBP Wells
            } else if (LOWORD(wParam) == ID_BUTTON_CLOSE_DATE) {
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

                TCHAR cmd[4096] = {};
                wsprintf(cmd, TEXT("py \"%sclose_dates.py\""), exeDir);

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch close_dates.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
            } else if (LOWORD(wParam) == ID_BUTTON_NONHBP_MI) {
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

                TCHAR cmd[4096] = {};
                wsprintf(cmd, TEXT("py \"%snon_hbp_mi.py\""), exeDir);

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch non_hbp_mi.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
            } else if (LOWORD(wParam) == ID_BUTTON_ORGANIZE) {
                OpenOrganize(hwnd);
            } else if (LOWORD(wParam) == ID_BUTTON_CASE_MATCHUP) {
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

                TCHAR cmd[4096] = {};
                wsprintf(cmd, TEXT("py \"%scase_matchup.py\""), exeDir);

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch case_matchup.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
            } else if (LOWORD(wParam) == ID_BUTTON_RENAME) {
                OpenRename(hwnd);
            } else if (LOWORD(wParam) == ID_BUTTON_CORR) {
                OpenCorrelation(hwnd);
            } else if (LOWORD(wParam) == ID_BUTTON_MAP) {
                MapUploadThreadArgs* args = new MapUploadThreadArgs();
                args->hwnd = hwnd;
                GetModuleFileName(NULL, args->exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(args->exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

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
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0');

                TCHAR cmd[4096] = {};
                wsprintf(cmd, TEXT("py \"%sstr_verification.py\""), exeDir);

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch str_verification.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
            }
            return 0;
        }
        case WM_DESTROY:
            if (g_hTitleFont)  DeleteObject(g_hTitleFont);
            if (g_hButtonFont) DeleteObject(g_hButtonFont);
            PostQuitMessage(0);
            return 0;
    }
    // Let Windows handle any messages we don't care about
    return DefWindowProc(hwnd, msg, wParam, lParam);
}

// Entry point for a Windows GUI application (equivalent to main())
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR, int nCmdShow) {
    CoInitialize(NULL);

    LoadFolders();
    LoadCompletedTasks();

    g_hBgBrush     = CreateSolidBrush(RGB(240, 240, 240));
    g_hYellowBrush = CreateSolidBrush(RGB(255, 255, 153));

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
    RegisterCorrelationClass(hInstance);  // register the project correlation window class
    RegisterOrganizeClass(hInstance);     // register the classify dialog class used by Organize
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
    return (int)msg.wParam;
}
