#include "project_correlation.h"
#include <shlobj.h>
#include <tchar.h>

// --- Control IDs (all 200+ to avoid collisions with other windows) ---
#define ID_CORR_LIST          201
#define ID_CORR_ADD_C1        202
#define ID_CORR_ADD_C2        203
#define ID_CORR_BTN_ADD       204
#define ID_CORR_BTN_DEL       205
#define ID_CORR_POT_C1_BASE   206  // 206-211: C1 for potential projects 0-5
#define ID_CORR_POT_C2_BASE   212  // 212-217: C2 for potential projects 0-5
#define ID_CORR_CALC          218
#define ID_CORR_BEST_LIST     219

#define NUM_POT 6

static const TCHAR CORR_CLASS[] = TEXT("CorrelationWindow");
static HWND s_hwndParent = NULL;
static HWND s_hwndCorr   = NULL;

// --- Completed task storage ---
#define MAX_TASKS 64
static int s_c1[MAX_TASKS];  // component index 0-17
static int s_c2[MAX_TASKS];  // component index 0-17, or -1 for none
static int s_count = 0;

// --- Component definitions ---
// Indices: Fi=0, W=1, Gh=2, Da=3, Fa=4, Ps=5, S=6, R=7, Gra=8, Fl=9,
//          N=10, B=11, Gro=12, E=13, Po=14, I=15, Dr=16, Fg=17
static const TCHAR* k_abbrevs[] = {
    TEXT("Fi"),  TEXT("W"),   TEXT("Gh"),  TEXT("Da"),  TEXT("Fa"),  TEXT("Ps"),
    TEXT("S"),   TEXT("R"),   TEXT("Gra"), TEXT("Fl"),  TEXT("N"),   TEXT("B"),
    TEXT("Gro"), TEXT("E"),   TEXT("Po"),  TEXT("I"),   TEXT("Dr"),  TEXT("Fg"),
};

static const TCHAR* k_names[] = {
    TEXT("Fileable (Fi)"),
    TEXT("Writable (W)"),
    TEXT("Gross File Size Req. (Gh)"),
    TEXT("Data Complexity (Da)"),
    TEXT("Far-reaching Affects (Fa)"),
    TEXT("Protected Files (Ps)"),
    TEXT("Scalable (S)"),
    TEXT("Rigid Structure (R)"),
    TEXT("Gradient of Files (Gra)"),
    TEXT("Floating Point (Fl)"),
    TEXT("Nascent (N)"),
    TEXT("Buggy (B)"),
    TEXT("Grounded in Ark Systems (Gro)"),
    TEXT("Elementary (E)"),
    TEXT("Potentially Intensive (Po)"),
    TEXT("Isolated (I)"),
    TEXT("Draining Resources (Dr)"),
    TEXT("Friction w/ Existing (Fg)"),
};

// k_effects[completed_component][potential_component]
// Values: -2 (--), -1 (-), 0 (none), +1 (+), +2 (++)
// Sources: spec in project_correlation file; typos corrected per user (Fi's +R->+B, Fa's +D->+Da)
static const int k_effects[18][18] = {
    //     Fi   W  Gh  Da  Fa  Ps   S   R Gra  Fl   N   B Gro   E  Po   I  Dr  Fg
    /* Fi*/{ -1, -1,  0,  0,  0,  0, +1, -1, +1,  0,  0, +1,  0,  0,  0, +1, -1,  0 },
    /*  W*/{ +1, -1,  0,  0,  0,  0,  0, +1, -1,  0,  0,  0, +1,  0,  0,  0, -1,  0 },
    /* Gh*/{  0,  0, +1, -1,  0, +1,  0,  0,  0,  0, -2,  0,  0,  0,  0,  0,  0,  0 },
    /* Da*/{  0,  0, +1, -1, -1, +1,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, -1 },
    /* Fa*/{ -1,  0,  0, +1,  0, -1, -1,  0,  0,  0,  0,  0,  0,  0,  0,  0, +1, +1 },
    /* Ps*/{  0,  0, -2,  0,  0, -1, -1,  0,  0,  0,  0,  0,  0,  0, +1,  0,  0, +1 },
    /*  S*/{ -1, -1,  0,  0, +1,  0, -1, +1,  0,  0,  0,  0,  0, -1,  0, +1,  0,  0 },
    /*  R*/{ +1,  0,  0,  0,  0,  0, -1,  0,  0, +1,  0, +1, -1,  0,  0, +1,  0, -1 },
    /*Gra*/{ -1, +1,  0,  0,  0, -1, -1, +1, -1, -1,  0, -1, +1,  0,  0,  0, -1,  0 },
    /* Fl*/{  0,  0,  0,  0,  0,  0, -1, -1, +1,  0,  0, +1,  0, -1,  0,  0,  0, +1 },
    /*  N*/{  0,  0, -2,  0,  0,  0, -1, -1,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0 },
    /*  B*/{ -1,  0, -1, +1, -1, +1, -1,  0, +1, -1,  0,  0,  0,  0,  0,  0,  0, -1 },
    /*Gro*/{ +1,  0,  0,  0,  0, +1, +1, +1, -1, -2,  0, -1,  0, +1,  0,  0,  0,  0 },
    /*  E*/{  0, +1,  0,  0,  0,  0,  0,  0, -1, +1,  0,  0, -2, -1,  0,  0, -1,  0 },
    /* Po*/{  0,  0, -1,  0, +1, -1, -2, -1, +1,  0,  0,  0, -1,  0,  0,  0,  0,  0 },
    /*  I*/{ -1, -1,  0,  0,  0,  0, -1,  0, +1, +1,  0,  0, +1,  0,  0, -1, +1,  0 },
    /* Dr*/{  0,  0,  0,  0, -1,  0, -1,  0,  0,  0,  0,  0,  0,  0,  0,  0, +1,  0 },
    /* Fg*/{  0,  0, -2, +1, -1, -1, +1, +1,  0, -1, +1, -1,  0,  0,  0, +1,  0,  0 },
};

// --- INI helpers ---

static void GetIniPath(TCHAR* out) {
    TCHAR appData[MAX_PATH];
    SHGetFolderPath(NULL, CSIDL_APPDATA, NULL, 0, appData);
    TCHAR dir[MAX_PATH];
    wsprintf(dir, TEXT("%s\\PhoenixLandDept"), appData);
    CreateDirectory(dir, NULL);
    wsprintf(out, TEXT("%s\\settings.ini"), dir);
}

void LoadCompletedTasks() {
    TCHAR ini[MAX_PATH];
    GetIniPath(ini);
    int n = (int)GetPrivateProfileInt(TEXT("CompletedTasks"), TEXT("count"), 0, ini);
    if (n > MAX_TASKS) n = MAX_TASKS;
    s_count = 0;
    for (int i = 0; i < n; ++i) {
        TCHAR key[32], val[32];
        wsprintf(key, TEXT("task_%d"), i);
        GetPrivateProfileString(TEXT("CompletedTasks"), key, TEXT("0,-1"), val, 32, ini);
        TCHAR* comma = _tcschr(val, TEXT(','));
        if (!comma) continue;
        *comma = TEXT('\0');
        int c1 = _ttoi(val);
        int c2 = _ttoi(comma + 1);
        if (c1 < 0 || c1 >= 18) continue;
        if (c2 != -1 && (c2 < 0 || c2 >= 18)) c2 = -1;
        s_c1[s_count] = c1;
        s_c2[s_count] = c2;
        ++s_count;
    }
}

static void SaveTasks() {
    TCHAR ini[MAX_PATH];
    GetIniPath(ini);
    TCHAR buf[16];
    wsprintf(buf, TEXT("%d"), s_count);
    WritePrivateProfileString(TEXT("CompletedTasks"), TEXT("count"), buf, ini);
    for (int i = 0; i < s_count; ++i) {
        TCHAR key[32], val[32];
        wsprintf(key, TEXT("task_%d"), i);
        wsprintf(val, TEXT("%d,%d"), s_c1[i], s_c2[i]);
        WritePrivateProfileString(TEXT("CompletedTasks"), key, val, ini);
    }
}

// --- Compatibility logic ---

static int ScoreComp(int doneComp, int potC1, int potC2) {
    int score = k_effects[doneComp][potC1];
    if (potC2 >= 0) score += k_effects[doneComp][potC2];
    return score;
}

// Returns the best score a completed task (doneC1/doneC2) achieves against a potential project.
// The best score across doneC1 and doneC2 is used because either component can drive the relationship.
static int GetScore(int doneC1, int doneC2, int potC1, int potC2) {
    int score = ScoreComp(doneC1, potC1, potC2);
    if (doneC2 >= 0) {
        int s2 = ScoreComp(doneC2, potC1, potC2);
        if (s2 > score) score = s2;
    }
    return score;
}

// Short label for display in the narrow per-project columns.
static const TCHAR* ScoreToShort(int score) {
    if (score <= -2) return TEXT("Imp");
    if (score == -1) return TEXT("Rsn");
    if (score ==  0) return TEXT("Avg");
    if (score ==  1) return TEXT("Smp");
    return TEXT("Easy");
}

// --- Best-4 selection ---
//
// Goal: find the 4 existing tasks that together give every potential project at least
// one "Simple" (score >= 1) match.  When full coverage is impossible, maximize the
// number of potential projects covered.  Ties are broken by the highest combined
// score sum across all potential projects.
//
// Algorithm:
//   1. For each existing task i, build covers[i]: a bitmask of which active potential
//      project slots it scores >= 1 on.  Also accumulate totalScore[i] for tiebreaking.
//   2. Try every C(n,4) combination of 4 existing tasks.  For each combo, OR the four
//      coverage masks and count set bits.  Track the combo with the most bits set
//      (then highest score sum).
//   3. If fewer than 4 tasks exist, use all of them.
//
// C(64,4) = 635,376 iterations — fast enough to run synchronously on button click.

struct BestResult {
    int idx[4];   // indices into s_c1/s_c2; -1 for unused slots
    int numIdx;   // number of valid slots: min(s_count, 4)
};

static BestResult FindBestFour(int potC1[NUM_POT], int potC2[NUM_POT]) {
    BestResult result;
    result.numIdx = (s_count < 4) ? s_count : 4;
    for (int i = 0; i < 4; ++i) result.idx[i] = -1;

    if (s_count == 0) return result;

    // Step 1: precompute coverage bitmask and total score per existing task
    int covers[MAX_TASKS]    = {};
    int totalScore[MAX_TASKS] = {};
    int allActive = 0;
    for (int p = 0; p < NUM_POT; ++p)
        if (potC1[p] >= 0) allActive |= (1 << p);

    for (int i = 0; i < s_count; ++i) {
        for (int p = 0; p < NUM_POT; ++p) {
            if (potC1[p] < 0) continue;
            int score = GetScore(s_c1[i], s_c2[i], potC1[p], potC2[p]);
            if (score >= 1) covers[i] |= (1 << p);
            totalScore[i] += score;
        }
    }

    // Fewer than 4 tasks: use them all, no search needed
    if (s_count < 4) {
        for (int i = 0; i < s_count; ++i) result.idx[i] = i;
        return result;
    }

    // Step 2: brute-force all C(n,4) combinations
    int bestCoverage = -1;
    int bestScoreSum = -1;
    int n = s_count;

    for (int a = 0; a < n - 3; ++a)
    for (int b = a + 1; b < n - 2; ++b)
    for (int c = b + 1; c < n - 1; ++c)
    for (int d = c + 1; d < n;     ++d) {
        int combined = (covers[a] | covers[b] | covers[c] | covers[d]) & allActive;

        // Count set bits (Brian Kernighan)
        int cnt = 0;
        for (int tmp = combined; tmp; tmp &= tmp - 1) ++cnt;

        int scoreSum = totalScore[a] + totalScore[b] + totalScore[c] + totalScore[d];

        if (cnt > bestCoverage || (cnt == bestCoverage && scoreSum > bestScoreSum)) {
            bestCoverage = cnt;
            bestScoreSum = scoreSum;
            result.idx[0] = a; result.idx[1] = b;
            result.idx[2] = c; result.idx[3] = d;
        }
    }

    return result;
}

// --- UI helpers ---

static void PopulateCombo(HWND hCombo, bool includeNone) {
    if (includeNone)
        SendMessage(hCombo, CB_ADDSTRING, 0, (LPARAM)TEXT("(none)"));
    for (int i = 0; i < 18; ++i)
        SendMessage(hCombo, CB_ADDSTRING, 0, (LPARAM)k_names[i]);
    SendMessage(hCombo, CB_SETCURSEL, 0, 0);
}

// Returns component index (0-17), or -1 for "none"/no selection.
static int GetComboComp(HWND hCombo, bool includeNone) {
    int idx = (int)SendMessage(hCombo, CB_GETCURSEL, 0, 0);
    if (idx == CB_ERR) return -1;
    if (includeNone) return (idx == 0) ? -1 : idx - 1;
    return idx;
}

// Formats a task abbreviation string without spaces to fit the narrow task column.
static void FormatTask(int c1, int c2, TCHAR* out) {
    if (c2 < 0)
        lstrcpy(out, k_abbrevs[c1]);
    else
        wsprintf(out, TEXT("%s+%s"), k_abbrevs[c1], k_abbrevs[c2]);
}

// Rebuilds the task list with "-" placeholders in all six potential-project columns.
// Called after Add/Delete so results are clearly stale until Calculate is clicked.
static void RebuildList(HWND hwnd) {
    HWND hList = GetDlgItem(hwnd, ID_CORR_LIST);
    SendMessage(hList, LB_RESETCONTENT, 0, 0);
    for (int i = 0; i < s_count; ++i) {
        TCHAR task[32], display[64];
        FormatTask(s_c1[i], s_c2[i], task);
        wsprintf(display, TEXT("%s\t-\t-\t-\t-\t-\t-"), task);
        SendMessage(hList, LB_ADDSTRING, 0, (LPARAM)display);
    }
}

// Recalculates compatibility for all completed tasks against each of the six potential projects.
// Potential project slots with potC1[p] < 0 are unused and shown as "-".
static void UpdateResults(HWND hwnd, int potC1[NUM_POT], int potC2[NUM_POT]) {
    HWND hList = GetDlgItem(hwnd, ID_CORR_LIST);
    SendMessage(hList, LB_RESETCONTENT, 0, 0);
    for (int i = 0; i < s_count; ++i) {
        TCHAR task[32], display[128];
        FormatTask(s_c1[i], s_c2[i], task);
        lstrcpy(display, task);
        for (int p = 0; p < NUM_POT; ++p) {
            TCHAR col[8];
            if (potC1[p] < 0)
                wsprintf(col, TEXT("\t-"));
            else {
                int score = GetScore(s_c1[i], s_c2[i], potC1[p], potC2[p]);
                wsprintf(col, TEXT("\t%s"), ScoreToShort(score));
            }
            lstrcat(display, col);
        }
        SendMessage(hList, LB_ADDSTRING, 0, (LPARAM)display);
    }
}

// Runs FindBestFour and populates the best-4 listbox.
// Each line shows the task abbreviation and which potential projects it covers (score >= 1).
static void UpdateBestFour(HWND hwnd, int potC1[NUM_POT], int potC2[NUM_POT]) {
    HWND hBest = GetDlgItem(hwnd, ID_CORR_BEST_LIST);
    SendMessage(hBest, LB_RESETCONTENT, 0, 0);

    BestResult best = FindBestFour(potC1, potC2);

    // Count total active potential project slots for the summary
    int numActive = 0;
    for (int p = 0; p < NUM_POT; ++p)
        if (potC1[p] >= 0) ++numActive;

    // Track which potential projects are covered by the recommended set
    int combinedCoverage = 0;

    for (int k = 0; k < best.numIdx; ++k) {
        int idx = best.idx[k];
        TCHAR task[32];
        FormatTask(s_c1[idx], s_c2[idx], task);

        // Build "P1,P3,P5" string for all potential projects this task covers
        TCHAR covered[32] = TEXT("");
        bool any = false;
        for (int p = 0; p < NUM_POT; ++p) {
            if (potC1[p] < 0) continue;
            int score = GetScore(s_c1[idx], s_c2[idx], potC1[p], potC2[p]);
            if (score >= 1) {
                TCHAR lbl[8];
                wsprintf(lbl, any ? TEXT(",P%d") : TEXT("P%d"), p + 1);
                lstrcat(covered, lbl);
                combinedCoverage |= (1 << p);
                any = true;
            }
        }
        if (!any) lstrcpy(covered, TEXT("none"));

        TCHAR line[96];
        wsprintf(line, TEXT("%d. %s  [covers %s]"), k + 1, task, covered);
        SendMessage(hBest, LB_ADDSTRING, 0, (LPARAM)line);
    }

    // Summary line: how many of the active potential projects are covered
    int coveredCount = 0;
    for (int tmp = combinedCoverage; tmp; tmp &= tmp - 1) ++coveredCount;

    TCHAR summary[64];
    wsprintf(summary, TEXT("   Coverage: %d / %d potential projects"), coveredCount, numActive);
    SendMessage(hBest, LB_ADDSTRING, 0, (LPARAM)summary);
}

// --- Window procedure ---

static LRESULT CALLBACK CorrProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
    case WM_CREATE: {
        HINSTANCE hInst = ((LPCREATESTRUCT)lParam)->hInstance;

        // Left panel column headers: "Task" then "P1"-"P6" aligned to tab stops
        // Tab stops at pixel positions 100, 150, 200, 250, 300, 350
        static const int k_tabPx[NUM_POT] = { 100, 150, 200, 250, 300, 350 };
        CreateWindowEx(0, TEXT("STATIC"), TEXT("Task"),
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            10, 10, 88, 18, hwnd, NULL, hInst, NULL);
        for (int p = 0; p < NUM_POT; ++p) {
            TCHAR hdr[4];
            wsprintf(hdr, TEXT("P%d"), p + 1);
            CreateWindowEx(0, TEXT("STATIC"), hdr,
                WS_CHILD | WS_VISIBLE | SS_LEFT,
                10 + k_tabPx[p] + 2, 10, 44, 18, hwnd, NULL, hInst, NULL);
        }

        HWND hList = CreateWindowEx(WS_EX_CLIENTEDGE, TEXT("LISTBOX"), NULL,
            WS_CHILD | WS_VISIBLE | LBS_NOTIFY | LBS_USETABSTOPS | WS_VSCROLL,
            10, 32, 405, 195, hwnd, (HMENU)ID_CORR_LIST, hInst, NULL);
        DWORD baseUnit = LOWORD(GetDialogBaseUnits());
        DWORD du = (baseUnit > 0 ? baseUnit : 6);
        DWORD tabStops[NUM_POT];
        for (int p = 0; p < NUM_POT; ++p)
            tabStops[p] = k_tabPx[p] * 4 / du;
        SendMessage(hList, LB_SETTABSTOPS, NUM_POT, (LPARAM)tabStops);

        // Add-task controls (left panel, below listbox)
        CreateWindowEx(0, TEXT("STATIC"), TEXT("Add New Task:"),
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            10, 238, 310, 18, hwnd, NULL, hInst, NULL);
        CreateWindowEx(0, TEXT("STATIC"), TEXT("Component 1:"),
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            10, 262, 100, 18, hwnd, NULL, hInst, NULL);
        CreateWindowEx(0, TEXT("COMBOBOX"), NULL,
            WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
            115, 258, 205, 300, hwnd, (HMENU)ID_CORR_ADD_C1, hInst, NULL);
        CreateWindowEx(0, TEXT("STATIC"), TEXT("Component 2:"),
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            10, 295, 100, 18, hwnd, NULL, hInst, NULL);
        CreateWindowEx(0, TEXT("COMBOBOX"), NULL,
            WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
            115, 291, 205, 300, hwnd, (HMENU)ID_CORR_ADD_C2, hInst, NULL);
        CreateWindowEx(0, TEXT("BUTTON"), TEXT("Add Task"),
            WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            10, 328, 100, 28, hwnd, (HMENU)ID_CORR_BTN_ADD, hInst, NULL);
        CreateWindowEx(0, TEXT("BUTTON"), TEXT("Delete Selected"),
            WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            120, 328, 135, 28, hwnd, (HMENU)ID_CORR_BTN_DEL, hInst, NULL);

        // Vertical separator between left panel and potential-projects panel
        CreateWindowEx(0, TEXT("STATIC"), NULL,
            WS_CHILD | WS_VISIBLE | SS_ETCHEDVERT,
            428, 5, 2, 410, hwnd, NULL, hInst, NULL);

        // Right panel: six potential project rows
        // Each row: number label + C1 combo + C2 (optional) combo.
        // Both combos include "(none)" so slots can be left unused.
        CreateWindowEx(0, TEXT("STATIC"), TEXT("Potential Projects:"),
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            440, 8, 200, 18, hwnd, NULL, hInst, NULL);
        CreateWindowEx(0, TEXT("STATIC"), TEXT("Component 1"),
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            466, 28, 175, 16, hwnd, NULL, hInst, NULL);
        CreateWindowEx(0, TEXT("STATIC"), TEXT("Component 2 (opt.)"),
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            656, 28, 175, 16, hwnd, NULL, hInst, NULL);

        for (int p = 0; p < NUM_POT; ++p) {
            int yLbl   = 54 + p * 38;
            int yCombo = 50 + p * 38;
            TCHAR rowLbl[4];
            wsprintf(rowLbl, TEXT("%d:"), p + 1);
            CreateWindowEx(0, TEXT("STATIC"), rowLbl,
                WS_CHILD | WS_VISIBLE | SS_LEFT,
                440, yLbl, 20, 18, hwnd, NULL, hInst, NULL);
            CreateWindowEx(0, TEXT("COMBOBOX"), NULL,
                WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
                464, yCombo, 183, 300, hwnd,
                (HMENU)(UINT_PTR)(ID_CORR_POT_C1_BASE + p), hInst, NULL);
            CreateWindowEx(0, TEXT("COMBOBOX"), NULL,
                WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
                652, yCombo, 183, 300, hwnd,
                (HMENU)(UINT_PTR)(ID_CORR_POT_C2_BASE + p), hInst, NULL);
        }

        // Best-4 section (right panel, below potential project rows)
        // Shows the four existing tasks that together give the most "Simple" coverage.
        CreateWindowEx(0, TEXT("STATIC"), NULL,
            WS_CHILD | WS_VISIBLE | SS_ETCHEDHORZ,
            440, 276, 400, 1, hwnd, NULL, hInst, NULL);
        CreateWindowEx(0, TEXT("STATIC"), TEXT("Best 4 for Coverage:"),
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            440, 283, 200, 18, hwnd, NULL, hInst, NULL);
        HWND hBest = CreateWindowEx(WS_EX_CLIENTEDGE, TEXT("LISTBOX"), NULL,
            WS_CHILD | WS_VISIBLE | LBS_NOSEL,
            440, 304, 400, 108, hwnd, (HMENU)ID_CORR_BEST_LIST, hInst, NULL);
        SendMessage(hBest, LB_ADDSTRING, 0, (LPARAM)TEXT("(click Calculate)"));

        // Horizontal separator and Calculate button spanning full width
        CreateWindowEx(0, TEXT("STATIC"), NULL,
            WS_CHILD | WS_VISIBLE | SS_ETCHEDHORZ,
            10, 422, 830, 2, hwnd, NULL, hInst, NULL);
        CreateWindowEx(0, TEXT("BUTTON"), TEXT("Calculate Compatibility"),
            WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            280, 436, 290, 35, hwnd, (HMENU)ID_CORR_CALC, hInst, NULL);

        // Populate dropdowns
        PopulateCombo(GetDlgItem(hwnd, ID_CORR_ADD_C1), false);
        PopulateCombo(GetDlgItem(hwnd, ID_CORR_ADD_C2), true);
        for (int p = 0; p < NUM_POT; ++p) {
            PopulateCombo(GetDlgItem(hwnd, ID_CORR_POT_C1_BASE + p), true);
            PopulateCombo(GetDlgItem(hwnd, ID_CORR_POT_C2_BASE + p), true);
        }

        RebuildList(hwnd);
        return 0;
    }
    case WM_COMMAND: {
        UINT id = LOWORD(wParam);
        if (id == ID_CORR_BTN_ADD) {
            if (s_count >= MAX_TASKS) {
                MessageBox(hwnd, TEXT("Maximum number of tasks reached."), TEXT("Error"), MB_ICONERROR);
                return 0;
            }
            int c1 = GetComboComp(GetDlgItem(hwnd, ID_CORR_ADD_C1), false);
            int c2 = GetComboComp(GetDlgItem(hwnd, ID_CORR_ADD_C2), true);
            if (c1 < 0) {
                MessageBox(hwnd, TEXT("Please select Component 1."), TEXT("Error"), MB_ICONERROR);
                return 0;
            }
            if (c2 == c1) {
                MessageBox(hwnd, TEXT("Component 2 must differ from Component 1."), TEXT("Warning"), MB_ICONWARNING);
                return 0;
            }
            s_c1[s_count] = c1;
            s_c2[s_count] = c2;
            ++s_count;
            SaveTasks();
            RebuildList(hwnd);
        } else if (id == ID_CORR_BTN_DEL) {
            HWND hList = GetDlgItem(hwnd, ID_CORR_LIST);
            int sel = (int)SendMessage(hList, LB_GETCURSEL, 0, 0);
            if (sel == LB_ERR) {
                MessageBox(hwnd, TEXT("Select a task to delete."), TEXT("Info"), MB_ICONINFORMATION);
                return 0;
            }
            for (int i = sel; i < s_count - 1; ++i) {
                s_c1[i] = s_c1[i + 1];
                s_c2[i] = s_c2[i + 1];
            }
            --s_count;
            SaveTasks();
            RebuildList(hwnd);
        } else if (id == ID_CORR_CALC) {
            if (s_count == 0) {
                MessageBox(hwnd, TEXT("Add at least one completed task first."), TEXT("Info"), MB_ICONINFORMATION);
                return 0;
            }
            // Read all six potential project pairs; potC1[p] < 0 means the slot is unused.
            int potC1[NUM_POT], potC2[NUM_POT];
            bool anySet = false;
            for (int p = 0; p < NUM_POT; ++p) {
                potC1[p] = GetComboComp(GetDlgItem(hwnd, ID_CORR_POT_C1_BASE + p), true);
                potC2[p] = GetComboComp(GetDlgItem(hwnd, ID_CORR_POT_C2_BASE + p), true);
                if (potC1[p] >= 0) {
                    anySet = true;
                    if (potC2[p] == potC1[p]) {
                        TCHAR err[80];
                        wsprintf(err, TEXT("Potential Project %d: Component 2 must differ from Component 1."), p + 1);
                        MessageBox(hwnd, err, TEXT("Warning"), MB_ICONWARNING);
                        return 0;
                    }
                }
            }
            if (!anySet) {
                MessageBox(hwnd, TEXT("Enter at least one potential project."), TEXT("Info"), MB_ICONINFORMATION);
                return 0;
            }
            UpdateResults(hwnd, potC1, potC2);
            UpdateBestFour(hwnd, potC1, potC2);
        }
        return 0;
    }
    case WM_DESTROY:
        EnableWindow(s_hwndParent, TRUE);
        SetForegroundWindow(s_hwndParent);
        s_hwndCorr = NULL;
        return 0;
    }
    return DefWindowProc(hwnd, msg, wParam, lParam);
}

// --- Public API ---

void RegisterCorrelationClass(HINSTANCE hInstance) {
    WNDCLASS wc      = {};
    wc.lpfnWndProc   = CorrProc;
    wc.hInstance     = hInstance;
    wc.lpszClassName = CORR_CLASS;
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    RegisterClass(&wc);
}

void OpenCorrelation(HWND hwndParent) {
    if (s_hwndCorr != NULL) {
        SetForegroundWindow(s_hwndCorr);
        return;
    }
    s_hwndParent = hwndParent;
    EnableWindow(hwndParent, FALSE);
    s_hwndCorr = CreateWindowEx(
        WS_EX_DLGMODALFRAME,
        CORR_CLASS, TEXT("Project Correlation"),
        WS_POPUP | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT, CW_USEDEFAULT, 880, 530,
        hwndParent, NULL, GetModuleHandle(NULL), NULL
    );
    ShowWindow(s_hwndCorr, SW_SHOW);
}
