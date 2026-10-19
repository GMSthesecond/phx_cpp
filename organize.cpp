// Organize: personal-finance CSV categorizer. Opened by the main window's "Organization" button.
// Entry points: RegisterOrganizeClass, OpenOrganize. Works in the [Folders] Organize folder
// (Settings; default Desktop\Organization): first rebuilds Data.CSV there from the Chase
// exports (*Chase*.csv; skipped if there are none), then reads Data.CSV,
// prompts (classify dialog) for unmatched descriptions, writes Organized.CSV (one row per day).
// Rules and scrub words persist in %APPDATA%\PhoenixLandDept\organize_rules.ini
// ([Rules] SNIPPET=colIndex, [ScrubWords] WORD=1, [Meta] ColumnSchema). If that file doesn't
// exist yet, it is first copied from default_organize_rules.ini next to the exe (in the repo).
#include "organize.h"
#include "settings.h"
#include "csv_text.h"
#include <shlobj.h>
#include <wchar.h>
#include <string>
#include <vector>
#include <map>
#include <regex>
#include <algorithm>

// ─── Column definitions ───────────────────────────────────────────────────────

static const int NUM_COLS  = 15; // exported columns
static const int IGNORE_COL = 15; // stored in rules but never written to output
// Category names, in output order; index = column index stored in rules.
static const wchar_t* const COLS[NUM_COLS] = {
    L"Income", L"Mortgage", L"Bills", L"Health", L"Groceries",
    L"Cats", L"Transport", L"Takeout", L"House", L"Travel",
    L"Wyn", L"Ruby", L"Briar", L"Mutual Aid", L"Savings"
};

// Working folder ([Folders] Organize in Settings): holds the Chase exports (*Chase*.csv) that
// BuildDataCsv merges into DataPath(), and the output.
static std::wstring OrgDir() { return GetSetting(L"Folders", L"Organize"); }
// Data.CSV: the merged Chase exports, rebuilt by BuildDataCsv and read by RunOrganize.
static std::wstring DataPath() { return OrgDir() + L"\\Data.CSV"; }
// Organized.CSV: RunOrganize's output, one row per day.
static std::wstring OutputPath() { return OrgDir() + L"\\Organized.CSV"; }

// ─── Rules (uppercased description → column index) ────────────────────────────

// In-memory copy of [Rules]; filled by LoadRules, added to by SaveRule.
static std::map<std::wstring, int> g_rules;

// default_organize_rules.ini next to phxcpp.exe: the rules committed to the repo, so a fresh
// install starts with them. Copied by SeedRulesIfMissing; the app never writes to it.
static std::wstring DefaultRulesPath() {
    wchar_t exe[MAX_PATH] = {};
    GetModuleFileName(NULL, exe, MAX_PATH);
    wchar_t* slash = wcsrchr(exe, L'\\');
    if (slash) slash[1] = L'\0';
    return std::wstring(exe) + L"default_organize_rules.ini";
}

// Copies seed to rulesPath only if rulesPath doesn't exist yet, so learned rules are never
// overwritten. Does nothing if seed is missing. Called by GetRulesPath.
static void SeedRulesIfMissing(const wchar_t* rulesPath, const std::wstring& seed) {
    CopyFile(seed.c_str(), rulesPath, TRUE);
}

// Writes the organize_rules.ini path into out (MAX_PATH); creates %APPDATA%\PhoenixLandDept if
// missing, and seeds the INI from DefaultRulesPath() on a machine that has none.
static void GetRulesPath(wchar_t* out) {
    wchar_t appData[MAX_PATH];
    SHGetFolderPath(NULL, CSIDL_APPDATA, NULL, 0, appData);
    wchar_t dir[MAX_PATH];
    wsprintf(dir, L"%s\\PhoenixLandDept", appData);
    CreateDirectory(dir, NULL);
    wsprintf(out, L"%s\\organize_rules.ini", dir);
    SeedRulesIfMissing(out, DefaultRulesPath());
}

// Rules are saved as description -> column INDEX, so reordering/inserting
// columns silently repoints old rules at the wrong category unless the
// saved indices are remapped. Maps each pre-Briar column index (0-12, plus
// 13 for "Ignore") to its new index under the current COLS layout.
static const int OLD_TO_NEW_COL_V1[14] = {
    0,  // Income     -> Income
    1,  // Mortgage   -> Mortgage
    2,  // Bills      -> Bills
    3,  // Medical    -> Health
    4,  // Groceries  -> Groceries
    7,  // Takeout    -> Takeout
    6,  // Transport  -> Transport
    8,  // House      -> House
    9,  // Travel     -> Travel
    10, // Wyn        -> Wyn
    11, // Ruby       -> Ruby
    13, // Mutual Aid -> Mutual Aid
    14, // Savings    -> Savings
    15, // Ignore     -> Ignore
};

// One-time migration of rules saved under the pre-Briar column layout.
// If [Meta] ColumnSchema < 2, rewrites every [Rules] value via OLD_TO_NEW_COL_V1
// and sets ColumnSchema=2. Called by LoadRules.
static void MigrateRuleColumnsIfNeeded(const wchar_t* path) {
    wchar_t schema[16] = {};
    GetPrivateProfileString(L"Meta", L"ColumnSchema", L"1", schema, ARRAYSIZE(schema), path);
    if (_wtoi(schema) >= 2) return;

    wchar_t buf[65536] = {};
    GetPrivateProfileSection(L"Rules", buf, ARRAYSIZE(buf), path);
    for (const wchar_t* p = buf; *p; p += wcslen(p) + 1) {
        const wchar_t* eq = wcschr(p, L'=');
        if (!eq) continue;
        std::wstring key(p, eq - p);
        int oldCol = _wtoi(eq + 1);
        if (oldCol < 0 || oldCol >= 14) continue; // unrecognized; leave as-is
        wchar_t val[8];
        wsprintf(val, L"%d", OLD_TO_NEW_COL_V1[oldCol]);
        WritePrivateProfileString(L"Rules", key.c_str(), val, path);
    }
    WritePrivateProfileString(L"Meta", L"ColumnSchema", L"2", path);
}

// Replaces g_rules with the [Rules] section of organize_rules.ini (after migration).
// Keeps indices 0..IGNORE_COL: category rules plus Ignore rules (which RunOrganize skips silently).
static void LoadRules() {
    g_rules.clear();
    wchar_t path[MAX_PATH];
    GetRulesPath(path);
    MigrateRuleColumnsIfNeeded(path);
    // GetPrivateProfileSection returns multi-string: "KEY=val\0KEY=val\0\0"
    wchar_t buf[65536] = {};
    GetPrivateProfileSection(L"Rules", buf, ARRAYSIZE(buf), path);
    for (const wchar_t* p = buf; *p; p += wcslen(p) + 1) {
        const wchar_t* eq = wcschr(p, L'=');
        if (!eq) continue;
        std::wstring key(p, eq - p);
        int col = _wtoi(eq + 1);
        if (col >= 0 && col <= IGNORE_COL)
            g_rules[key] = col;
    }
}

// Saves snippet desc -> col to [Rules] in organize_rules.ini and to g_rules.
static void SaveRule(const std::wstring& desc, int col) {
    wchar_t path[MAX_PATH], val[8];
    GetRulesPath(path);
    wsprintf(val, L"%d", col);
    WritePrivateProfileString(L"Rules", desc.c_str(), val, path);
    g_rules[desc] = col;
}

// ─── Classify dialog ──────────────────────────────────────────────────────────

// Control IDs for the classify dialog.
#define ID_CL_COMBO   501
#define ID_CL_OK      502
#define ID_CL_SKIP    503
#define ID_CL_SNIPPET 504

// State shared between ClassifyTx and ClassifyProc for one transaction prompt.
struct ClassifyParams {
    const wchar_t* date;
    const wchar_t* desc;
    const wchar_t* amount;
    int     result;       // -1 = skip, 0-14 = column index, 15 = Ignore
    bool    done;         // set by ClassifyProc to end ClassifyTx's message loop
    wchar_t snippet[512]; // pattern to save; user edits this down from the full description
};

// Params of the classify dialog currently open (nullptr when none); written by ClassifyProc.
static ClassifyParams* g_cp = nullptr;
// Window class name for the classify dialog.
static const wchar_t CLASSIFY_CLS[] = L"OrgClassifyDlg";

// Window proc for the classify dialog: shows date/description/amount, a snippet edit
// box, a category combo (COLS + "Ignore"), Confirm and Skip. Confirm stores the combo
// index and snippet in g_cp; Skip/close store -1. Either sets g_cp->done and destroys.
static LRESULT CALLBACK ClassifyProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        HINSTANCE hi = ((LPCREATESTRUCT)lp)->hInstance;
        ClassifyParams* cp = (ClassifyParams*)((LPCREATESTRUCT)lp)->lpCreateParams;
        wchar_t buf[1024];

        wsprintf(buf, L"Date:         %s", cp->date);
        CreateWindowEx(0, L"STATIC", buf, WS_CHILD|WS_VISIBLE|SS_LEFT, 10, 12, 570, 18, hwnd, NULL, hi, NULL);

        wsprintf(buf, L"Description:  %s", cp->desc);
        CreateWindowEx(0, L"STATIC", buf, WS_CHILD|WS_VISIBLE|SS_LEFT, 10, 36, 570, 18, hwnd, NULL, hi, NULL);

        wsprintf(buf, L"Amount:       %s", cp->amount);
        CreateWindowEx(0, L"STATIC", buf, WS_CHILD|WS_VISIBLE|SS_LEFT, 10, 60, 570, 18, hwnd, NULL, hi, NULL);

        CreateWindowEx(0, L"STATIC", NULL, WS_CHILD|WS_VISIBLE|SS_ETCHEDHORZ, 10, 88, 570, 2, hwnd, NULL, hi, NULL);

        // Snippet row — user trims the description down to the identifying part.
        CreateWindowEx(0, L"STATIC", L"Match any description containing:",
            WS_CHILD|WS_VISIBLE|SS_LEFT, 10, 100, 300, 18, hwnd, NULL, hi, NULL);
        HWND hEd = CreateWindowEx(WS_EX_CLIENTEDGE, L"EDIT", cp->desc,
            WS_CHILD|WS_VISIBLE|ES_AUTOHSCROLL,
            10, 120, 570, 22, hwnd, (HMENU)ID_CL_SNIPPET, hi, NULL);
        SendMessage(hEd, EM_SETSEL, 0, -1); // select all so typing replaces immediately

        CreateWindowEx(0, L"STATIC", L"Category:", WS_CHILD|WS_VISIBLE|SS_LEFT, 10, 155, 90, 20, hwnd, NULL, hi, NULL);
        HWND hCb = CreateWindowEx(0, L"ComboBox", NULL,
            WS_CHILD|WS_VISIBLE|CBS_DROPDOWNLIST|WS_VSCROLL,
            105, 152, 220, 300, hwnd, (HMENU)ID_CL_COMBO, hi, NULL);
        for (int i = 0; i < NUM_COLS; i++)
            SendMessage(hCb, CB_ADDSTRING, 0, (LPARAM)COLS[i]);
        SendMessage(hCb, CB_ADDSTRING, 0, (LPARAM)L"Ignore");
        SendMessage(hCb, CB_SETCURSEL, 0, 0);

        CreateWindowEx(0, L"BUTTON", L"Confirm", WS_CHILD|WS_VISIBLE|BS_DEFPUSHBUTTON,
            10, 188, 90, 28, hwnd, (HMENU)ID_CL_OK, hi, NULL);
        CreateWindowEx(0, L"BUTTON", L"Skip", WS_CHILD|WS_VISIBLE|BS_PUSHBUTTON,
            110, 188, 90, 28, hwnd, (HMENU)ID_CL_SKIP, hi, NULL);
        return 0;
    }
    case WM_COMMAND:
        if (LOWORD(wp) == ID_CL_OK) {
            int sel = (int)SendMessage(GetDlgItem(hwnd, ID_CL_COMBO), CB_GETCURSEL, 0, 0);
            if (sel >= 0 && sel <= IGNORE_COL) {
                // Capture whatever snippet text the user left in the edit field.
                GetWindowText(GetDlgItem(hwnd, ID_CL_SNIPPET),
                    g_cp->snippet, ARRAYSIZE(g_cp->snippet));
                g_cp->result = sel;
                g_cp->done   = true;
                DestroyWindow(hwnd);
            }
        } else if (LOWORD(wp) == ID_CL_SKIP) {
            g_cp->result = -1;
            g_cp->done   = true;
            DestroyWindow(hwnd);
        }
        return 0;
    case WM_CLOSE:
        g_cp->result = -1;
        g_cp->done   = true;
        DestroyWindow(hwnd);
        return 0;
    }
    return DefWindowProc(hwnd, msg, wp, lp);
}

// Shows the classify dialog modally.
// Returns the chosen column index (0-14, or 15 = Ignore), or -1 to skip.
// On a confirmed choice, snippetOut receives the pattern the user typed.
static int ClassifyTx(HWND hwndParent, const wchar_t* date, const wchar_t* desc,
                      const wchar_t* amount, wchar_t* snippetOut, int snippetMax) {
    ClassifyParams cp{};
    cp.date   = date;
    cp.desc   = desc;
    cp.amount = amount;
    cp.result = -1;
    cp.done   = false;
    // Pre-fill snippet with the full description; the user shortens it in the dialog.
    lstrcpyn(cp.snippet, desc, ARRAYSIZE(cp.snippet));

    g_cp = &cp;
    EnableWindow(hwndParent, FALSE);
    HWND hwnd = CreateWindowEx(
        WS_EX_DLGMODALFRAME, CLASSIFY_CLS, L"Categorize Transaction",
        WS_POPUP | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT, CW_USEDEFAULT, 610, 260,
        hwndParent, NULL, GetModuleHandle(NULL), &cp);
    if (!hwnd) {
        EnableWindow(hwndParent, TRUE);
        g_cp = nullptr;
        return -1;
    }
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);
    // Nested message loop — blocks until the dialog is closed.
    MSG msg;
    while (!cp.done) {
        BOOL r = GetMessage(&msg, NULL, 0, 0);
        if (r == 0) { PostQuitMessage((int)msg.wParam); break; } // re-post WM_QUIT
        if (r < 0) break;
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    EnableWindow(hwndParent, TRUE);
    SetForegroundWindow(hwndParent);
    g_cp = nullptr;
    if (cp.result >= 0)
        lstrcpyn(snippetOut, cp.snippet, snippetMax);
    return cp.result;
}

// ─── String helpers ───────────────────────────────────────────────────────────

// Returns an uppercased copy of s.
static std::wstring ToUpper(std::wstring s) {
    for (auto& c : s) c = (wchar_t)towupper(c);
    return s;
}

// "STARBUCKS COFFEE #1234" -> "Starbucks Coffee" — first letter of each word
// capitalized, the rest lowercased; digits/punctuation just reset the
// word boundary rather than being cased themselves.
static std::wstring TitleCase(std::wstring s) {
    bool startOfWord = true;
    for (auto& c : s) {
        if (iswalpha(c)) {
            c = startOfWord ? (wchar_t)towupper(c) : (wchar_t)towlower(c);
            startOfWord = false;
        } else {
            startOfWord = true;
        }
    }
    return s;
}

// ─── Scrub words (manual list of terms stripped from transaction notes) ──────
// Stored in the same INI as the rules so new words can be added without a
// rebuild. Any default below not already present in the INI is merged in on
// load, so adding a new entry here and rebuilding is enough to pick it up —
// it isn't limited to a one-time seed of a brand-new INI.

// Uppercased scrub words from [ScrubWords]; filled by LoadScrubWords, used by ScrubDesc.
static std::vector<std::wstring> g_scrubWords;

// Loads [ScrubWords] keys into g_scrubWords, then writes any missing built-in
// default word to the INI (as WORD=1) and appends it to the list.
static void LoadScrubWords() {
    g_scrubWords.clear();
    wchar_t path[MAX_PATH];
    GetRulesPath(path);
    wchar_t buf[8192] = {};
    GetPrivateProfileSection(L"ScrubWords", buf, ARRAYSIZE(buf), path);
    for (const wchar_t* p = buf; *p; p += wcslen(p) + 1) {
        std::wstring line(p);
        size_t eq = line.find(L'=');
        std::wstring word = Trim(eq == std::wstring::npos ? line : line.substr(0, eq));
        if (!word.empty()) g_scrubWords.push_back(ToUpper(word));
    }

    static const wchar_t* const defaults[] = { L"CASPER", L"GOOGLE", L"PURCHASE", L"WY", L"O WEB ID: PAYPAL", L"O PAYROLL", L"PPD", L"WEB ID:",
        L"www.", L".c www.ladder", L".COM", L"MKTPL", L"*", L"ONLINE", L"ACHPAY WEB", L"Web", L"BILL", L"POWER",
        L"New York", L"SFH PAD MTG PYMT PPD", L"Thank You-Mobile", L"O PAYROLL PPD ", L"CO ENTRY DESCR:CASHOUT SEC:PPD ORIG", L"ORIG CO NAME:",
        L"ORIG CO NAME:", L"ID:", L"CO ENTRY DESCR:CASHOUT SEC: ORIG", L"SFH PAD MTG PYMT", L"DEPT EDUCATION", L"-"
     };
    for (auto* w : defaults) {
        std::wstring up = ToUpper(Trim(w));
        if (up.empty()) continue;
        bool have = false;
        for (auto& existing : g_scrubWords) if (existing == up) { have = true; break; }
        if (have) continue;
        WritePrivateProfileString(L"ScrubWords", w, L"1", path);
        g_scrubWords.push_back(up);
    }
}

// Escapes regex metacharacters so a scrub word can be dropped into a pattern
// as a literal (the ScrubWords list can contain things like "*", ".", "-").
static std::wstring EscapeRegex(const std::wstring& s) {
    static const std::wstring special = L".^$|()[]{}*+?\\";
    std::wstring out;
    out.reserve(s.size() * 2);
    for (wchar_t c : s) {
        if (special.find(c) != std::wstring::npos) out += L'\\';
        out += c;
    }
    return out;
}

// Strips useless identifying junk from a transaction description before it
// goes into the notes column: label+number IDs ("ID: 5264681992",
// "REF# 12345"), bare "#1234" tags, phone-number-shaped digit runs
// ("307-234-2121", "800-9106463"), bare numeric IDs ("1393"), opaque
// alphanumeric reference codes ("P474095192304", "*532DA1WV1",
// "023860430ACHPAY", "ST-R3I5X0S2M3W5"), and any manually configured scrub
// words (case-insensitive, whole word) — then collapses any resulting runs
// of whitespace down to one space and title-cases the result ("STARBUCKS
// COFFEE" -> "Starbucks Coffee"). Falls back to the original description if
// everything was stripped. Called by RunOrganize for each note entry.
static std::wstring ScrubDesc(const std::wstring& desc) {
    std::wstring s = desc;

    static const std::wregex reLabelId(
        LR"(\b(ID|REF|REFERENCE|CONF|CONFIRMATION|AUTH|TRACE|TXN|TRANS|ACCT|ACCOUNT)\.?\s*[:#]?\s*\d+\b)",
        std::regex_constants::icase);
    s = std::regex_replace(s, reLabelId, L" ");

    static const std::wregex reHashId(LR"(#\s*\d+)");
    s = std::regex_replace(s, reHashId, L" ");

    // Phone numbers and other long dashed/dotted digit runs (7+ digits total).
    static const std::wregex rePhone(LR"(\b\d[\d\-.]{5,}\d\b)");
    s = std::regex_replace(s, rePhone, L" ");

    // Bare numeric tokens (order numbers, confirmation codes, etc.).
    static const std::wregex reBareNum(LR"(\b\d{4,}\b)");
    s = std::regex_replace(s, reBareNum, L" ");

    // Opaque alphanumeric reference codes: a token (optionally prefixed with
    // * or #, optionally hyphen-joined, e.g. "ST-R3I5X0S2M3W5") that mixes
    // letters and digits and has at least 6 characters of alphanumeric
    // content. Real category words don't look like this, so it's a safe net
    // for the POS/ACH/processor reference junk that shows up in descriptions.
    {
        static const std::wregex reToken(LR"([*#]?[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b)");
        std::wstring out;
        out.reserve(s.size());
        size_t last = 0;
        for (auto it = std::wsregex_iterator(s.begin(), s.end(), reToken);
             it != std::wsregex_iterator(); ++it) {
            auto& m = *it;
            std::wstring tok = m.str();
            std::wstring alnum;
            for (wchar_t c : tok) if (iswalnum(c)) alnum += c;
            bool hasDigit = false, hasAlpha = false;
            for (wchar_t c : alnum) {
                if (iswdigit(c)) hasDigit = true;
                if (iswalpha(c)) hasAlpha = true;
            }
            bool qualifies = hasDigit && hasAlpha && alnum.size() >= 6;
            out.append(s, last, (size_t)m.position() - last);
            out += qualifies ? L" " : tok;
            last = (size_t)m.position() + (size_t)m.length();
        }
        out.append(s, last, s.size() - last);
        s = out;
    }

    for (auto& w : g_scrubWords) {
        std::wregex re(L"\\b" + EscapeRegex(w) + L"\\b", std::regex_constants::icase);
        s = std::regex_replace(s, re, L" ");
    }

    static const std::wregex reWs(LR"(\s+)");
    s = std::regex_replace(s, reWs, L" ");
    s = Trim(s);
    return TitleCase(s.empty() ? Trim(desc) : s); // never blank out a note entirely
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

// Calendar date (year, month 1-12, day 1-31).
struct Date { int y, m, d; };

// True if date a is strictly before b.
static bool DateLt(const Date& a, const Date& b) {
    if (a.y != b.y) return a.y < b.y;
    if (a.m != b.m) return a.m < b.m;
    return a.d < b.d;
}
// True if date a is on or before b.
static bool DateLe(const Date& a, const Date& b) { return !DateLt(b, a); }

// Number of days in month m of year y, accounting for leap years.
static int DaysInMonth(int y, int m) {
    static const int t[] = { 0,31,28,31,30,31,30,31,31,30,31,30,31 };
    int d = t[m];
    if (m == 2 && ((y % 4 == 0 && y % 100 != 0) || y % 400 == 0)) d = 29;
    return d;
}

// Returns the calendar day after d.
static Date NextDay(Date d) {
    if (++d.d > DaysInMonth(d.y, d.m)) { d.d = 1; if (++d.m > 12) { d.m = 1; d.y++; } }
    return d;
}

// Accepts "M/D/YYYY", "MM/DD/YYYY", and "YYYY-MM-DD".
// Returns false if the text doesn't parse or fails a basic range check.
static bool ParseDate(const std::wstring& s, Date& out) {
    std::wstring t = Trim(s);
    if (t.size() >= 10 && t[4] == L'-' && t[7] == L'-') {
        out.y = _wtoi(t.c_str());
        out.m = _wtoi(t.c_str() + 5);
        out.d = _wtoi(t.c_str() + 8);
    } else {
        size_t s1 = t.find(L'/');
        if (s1 == std::wstring::npos) return false;
        size_t s2 = t.find(L'/', s1 + 1);
        if (s2 == std::wstring::npos) return false;
        out.m = _wtoi(t.c_str());
        out.d = _wtoi(t.c_str() + s1 + 1);
        out.y = _wtoi(t.c_str() + s2 + 1);
    }
    return out.y > 0 && out.m >= 1 && out.m <= 12 && out.d >= 1 && out.d <= 31;
}

// Sortable "YYYY-MM-DD" key used for the per-day map.
static std::wstring DateKey(const Date& d) {
    wchar_t b[16]; wsprintf(b, L"%04d-%02d-%02d", d.y, d.m, d.d); return b;
}

// "M/D/YYYY" text written to the Date column of Organized.CSV.
static std::wstring DateDisplay(const Date& d) {
    wchar_t b[16]; wsprintf(b, L"%d/%d/%04d", d.m, d.d, d.y); return b;
}

// ─── Amount helpers ───────────────────────────────────────────────────────────

// Parses "$1,234.56", "-1,234.56", "(1,234.56)", etc.
static double ParseAmount(const std::wstring& s) {
    std::wstring t = Trim(s);
    bool neg = false;
    if (!t.empty() && t.front() == L'(') { neg = true; t = t.substr(1); }
    if (!t.empty() && t.back()  == L')') { t.pop_back(); }
    if (!t.empty() && t.front() == L'-') { neg = true; t = t.substr(1); }
    if (!t.empty() && t.front() == L'$') { t = t.substr(1); }
    std::wstring c; for (wchar_t ch : t) if (ch != L',') c += ch;
    double v = _wtof(c.c_str());
    return neg ? -v : v;
}

// Formats v with two decimals ("-12.50").
// Returns empty string for zero (leaves the cell blank in the output).
static std::wstring FmtAmount(double v) {
    if (v == 0.0) return L"";
    wchar_t buf[32];
    _snwprintf(buf, ARRAYSIZE(buf) - 1, L"%.2f", v);
    buf[ARRAYSIZE(buf) - 1] = L'\0';
    return buf;
}

// ─── Rule matching ────────────────────────────────────────────────────────────

// Returns the column index of the saved snippet found in the uppercased description, or -1 if
// none is. When several match, the longest (most specific) wins, e.g. "AMAZON PRIME" over "AMAZON";
// equal lengths go to the first alphabetically.
static int FindRule(const std::wstring& upperDesc) {
    int col = -1;
    size_t bestLen = 0;
    for (auto& kv : g_rules) {
        if (kv.first.size() > bestLen && upperDesc.find(kv.first) != std::wstring::npos) {
            col = kv.second;
            bestLen = kv.first.size();
        }
    }
    return col;
}

// Descriptions (uppercased snippets) of credit-card payments: the card side ("Payment Thank You",
// autopay) and the checking side ("Payment to Chase card ending in 1234"). They only move money
// between accounts, so Organize leaves them out (the card's purchases are counted instead).
static const wchar_t* const CARD_PAYMENT_SNIPPETS[] = {
    L"PAYMENT THANK YOU", L"AUTOMATIC PAYMENT - THANK", L"PAYMENT TO CHASE CARD",
};

// True if the uppercased description is a credit-card payment (CARD_PAYMENT_SNIPPETS).
static bool IsCardPayment(const std::wstring& upperDesc) {
    for (const wchar_t* s : CARD_PAYMENT_SNIPPETS) {
        if (upperDesc.find(s) != std::wstring::npos) return true;
    }
    return false;
}

// ─── File helpers ─────────────────────────────────────────────────────────────

// Reads a UTF-8 text file (BOM optional) into lines split on LF (a trailing CR is left on).
// Returns false if the file can't be opened.
static bool ReadTextLines(const wchar_t* path, std::vector<std::wstring>& lines) {
    lines.clear();
    HANDLE hf = CreateFile(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (hf == INVALID_HANDLE_VALUE) return false;
    DWORD fsz = GetFileSize(hf, NULL);
    std::vector<char> raw(fsz + 4, 0);
    DWORD nr = 0;
    ReadFile(hf, raw.data(), fsz, &nr, NULL);
    CloseHandle(hf);

    // Strip UTF-8 BOM if present, then decode to wide string.
    char* src = raw.data();
    if (nr >= 3 &&
        (unsigned char)src[0] == 0xEF &&
        (unsigned char)src[1] == 0xBB &&
        (unsigned char)src[2] == 0xBF) src += 3;

    int wlen = MultiByteToWideChar(CP_UTF8, 0, src, -1, NULL, 0);
    std::vector<wchar_t> wb(wlen + 1, 0);
    MultiByteToWideChar(CP_UTF8, 0, src, -1, wb.data(), wlen);
    std::wstring content(wb.data());

    size_t pos = 0;
    while (pos <= content.size()) {
        size_t nl = content.find(L'\n', pos);
        if (nl == std::wstring::npos) nl = content.size();
        lines.push_back(content.substr(pos, nl - pos));
        if (nl >= content.size()) break;
        pos = nl + 1;
    }
    return true;
}

// Finds the "Posting Date"/"Post Date", "Description" and "Amount" columns in a CSV header line
// (case-insensitive; "Transaction Date" is not a match). Returns false if any is missing.
static bool FindTxColumns(const std::wstring& headerLine, int& colDate, int& colDesc, int& colAmt) {
    colDate = colDesc = colAmt = -1;
    auto hdr = SplitCSV(headerLine);
    for (int i = 0; i < (int)hdr.size(); ++i) {
        std::wstring h = ToUpper(Trim(hdr[i]));
        if (h == L"POSTING DATE" || h == L"POST DATE") colDate = i;
        else if (h == L"DESCRIPTION")                  colDesc = i;
        else if (h == L"AMOUNT")                       colAmt  = i;
    }
    return colDate >= 0 && colDesc >= 0 && colAmt >= 0;
}

// Writes text to path as UTF-8 with a BOM (so Excel opens it correctly), replacing any old file.
// Returns false if the file can't be created.
static bool WriteUtf8File(const wchar_t* path, const std::wstring& text) {
    HANDLE hOut = CreateFile(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hOut == INVALID_HANDLE_VALUE) return false;
    std::string mb = "\xEF\xBB\xBF";
    int n = WideCharToMultiByte(CP_UTF8, 0, text.c_str(), (int)text.size(), NULL, 0, NULL, NULL);
    if (n > 0) {
        size_t start = mb.size();
        mb.resize(start + n);
        WideCharToMultiByte(CP_UTF8, 0, text.c_str(), (int)text.size(), &mb[start], n, NULL, NULL);
    }
    DWORD nw = 0;
    WriteFile(hOut, mb.data(), (DWORD)mb.size(), &nw, NULL);
    CloseHandle(hOut);
    return true;
}

// ─── Data.CSV from Chase exports ──────────────────────────────────────────────

// Names (not paths) of the .csv files in OrgDir() whose name contains "chase" in any case,
// sorted alphabetically so the merge order is stable.
static std::vector<std::wstring> FindChaseFiles() {
    std::vector<std::wstring> names;
    std::wstring pattern = OrgDir() + L"\\*.csv";
    WIN32_FIND_DATA fd;
    HANDLE h = FindFirstFile(pattern.c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) return names;
    do {
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
        std::wstring upper = ToUpper(fd.cFileName);
        size_t n = upper.size();
        if (n >= 4 && upper.compare(n - 4, 4, L".CSV") == 0 && upper.find(L"CHASE") != std::wstring::npos)
            names.push_back(fd.cFileName);
    } while (FindNextFile(h, &fd));
    FindClose(h);
    std::sort(names.begin(), names.end());
    return names;
}

// Outcome of BuildDataCsv.
enum class BuildResult { NoChaseFiles, Built, Failed };

// Rebuilds DataPath() from every Chase export in OrgDir(). Each export can have its own column
// layout; only Posting Date/Post Date (rewritten as M/D/YYYY), Description and Amount are kept,
// in file-name order, then row order. Rows with no valid date or no description are dropped, and
// so are card payments (a "Type" column saying Payment: money moved, not spent).
// Overlapping exports: a row with the same date, description and amount is kept only as many
// times as the single file that has it most, so an old export left in the folder isn't counted
// twice while real repeat charges within one export are kept.
// On Failed (unreadable file, missing column, Data.CSV not writable) a MessageBox has been shown
// and Data.CSV is unchanged. On Built, fileCount and rowCount say how much went in.
static BuildResult BuildDataCsv(HWND hwndParent, int& fileCount, int& rowCount) {
    fileCount = rowCount = 0;
    std::vector<std::wstring> files = FindChaseFiles();
    if (files.empty()) return BuildResult::NoChaseFiles;

    std::wstring out = L"Post Date,Description,Amount\r\n";
    std::map<std::wstring, int> kept; // date|desc|amount -> rows written so far
    for (auto& name : files) {
        std::wstring path = OrgDir() + L"\\" + name;
        std::vector<std::wstring> lines;
        int colDate, colDesc, colAmt;
        if (!ReadTextLines(path.c_str(), lines)) {
            MessageBox(hwndParent, (L"Could not read the Chase export:\n" + path +
                L"\n\nClose it if it is open in Excel, then try again.").c_str(),
                L"Organize — Error", MB_ICONERROR);
            return BuildResult::Failed;
        }
        if (lines.empty() || !FindTxColumns(lines[0], colDate, colDesc, colAmt)) {
            MessageBox(hwndParent, (L"Could not find the required columns in the Chase export:\n" + path +
                L"\n\nExpected headers: \"Posting Date\" or \"Post Date\", \"Description\", \"Amount\".\n"
                L"Data.CSV was not changed.").c_str(),
                L"Organize — Error", MB_ICONERROR);
            return BuildResult::Failed;
        }
        int need = 1 + max(colDate, max(colDesc, colAmt));
        int colType = -1;  // card exports: Sale / Return / Payment / Adjustment
        auto header = SplitCSV(Trim(lines[0]));
        for (int c = 0; c < (int)header.size(); c++) {
            if (ToUpper(Trim(header[c])) == L"TYPE") colType = c;
        }
        std::map<std::wstring, int> seen; // same key, rows seen in this file
        for (size_t i = 1; i < lines.size(); ++i) {
            std::wstring ln = Trim(lines[i]);
            if (ln.empty()) continue;
            auto f = SplitCSV(ln);
            if ((int)f.size() < need) continue;
            Date d{};
            if (!ParseDate(f[colDate], d)) continue;
            std::wstring desc = Trim(f[colDesc]);
            if (desc.empty()) continue;
            if (colType >= 0 && colType < (int)f.size() && ToUpper(Trim(f[colType])) == L"PAYMENT") continue;
            std::wstring amt = Trim(f[colAmt]);
            std::wstring key = DateKey(d) + L"|" + desc + L"|" + FmtAmount(ParseAmount(amt));
            int n = ++seen[key];
            if (n <= kept[key]) continue; // already written from an overlapping export
            kept[key] = n;
            out += DateDisplay(d) + L"," + EscCSV(desc) + L"," + EscCSV(amt) + L"\r\n";
            rowCount++;
        }
        fileCount++;
    }

    if (!WriteUtf8File(DataPath().c_str(), out)) {
        MessageBox(hwndParent, (std::wstring(L"Could not write Data.CSV:\n") + DataPath() +
            L"\n\nClose it if it is open in Excel, then try again.").c_str(),
            L"Organize — Error", MB_ICONERROR);
        return BuildResult::Failed;
    }
    return BuildResult::Built;
}

// ─── Main organize logic ──────────────────────────────────────────────────────

// Accumulated totals and notes for one calendar day of output.
struct DayRow {
    double       c[NUM_COLS]; // per-column summed amount
    std::wstring notes[NUM_COLS]; // per-column: "Desc $amt; Desc $amt"
    DayRow() { for (int i = 0; i < NUM_COLS; i++) c[i] = 0.0; }
};

// Does the whole Organize job: rebuilds Data.CSV from the Chase exports (BuildDataCsv; keeps
// the existing Data.CSV if there are none), loads rules/scrub words, parses Data.CSV (columns
// found by header: Posting/Post Date, Description, Amount), categorizes each transaction
// (card payments skipped; a positive amount goes to its rule's column, so a refund reduces that
// category, else Income; a negative one to its rule, else ClassifyTx prompt + SaveRule), sums amounts
// and scrubbed notes per day, and writes Organized.CSV (UTF-8 BOM) covering every day
// of the spanned months. Shows MessageBoxes for errors and completion.
static void RunOrganize(HWND hwndParent) {
    int chaseFiles = 0, chaseRows = 0;
    BuildResult built = BuildDataCsv(hwndParent, chaseFiles, chaseRows);
    if (built == BuildResult::Failed) return;

    LoadRules();
    LoadScrubWords();

    // Read Data.CSV
    std::vector<std::wstring> lines;
    if (!ReadTextLines(DataPath().c_str(), lines)) {
        MessageBox(hwndParent, (std::wstring(
            L"Could not open Data.CSV, and there were no Chase exports to build it from.\n\n"
            L"Put the Chase CSV downloads (any .csv with \"Chase\" in its name) in:\n") + OrgDir()).c_str(),
            L"Organize — Error", MB_ICONERROR);
        return;
    }

    // Parse transactions — detect column indices from header row.
    struct Tx {
        Date        date;
        std::wstring dateRaw, desc, amountRaw;
        double      amount;
    };
    std::vector<Tx> txns;
    Date minD{ 9999,12,31 }, maxD{ 1900,1,1 };
    bool hasData = false;

    int colDate = -1, colDesc = -1, colAmt = -1;
    if (lines.empty() || !FindTxColumns(lines[0], colDate, colDesc, colAmt)) {
        MessageBox(hwndParent,
            L"Could not find required columns in Data.CSV.\n\n"
            L"Expected headers: \"Posting Date\" or \"Post Date\", \"Description\", \"Amount\".",
            L"Organize — Error", MB_ICONERROR);
        return;
    }

    for (size_t i = 1; i < lines.size(); ++i) {
        std::wstring ln = Trim(lines[i]);
        if (ln.empty()) continue;
        auto f = SplitCSV(ln);
        int need = 1 + max(colDate, max(colDesc, colAmt));
        if ((int)f.size() < need) continue;
        Date d{};
        if (!ParseDate(f[colDate], d)) continue;
        std::wstring desc = Trim(f[colDesc]);
        if (desc.empty()) continue;
        double amt = ParseAmount(f[colAmt]);
        txns.push_back({ d, Trim(f[colDate]), desc, Trim(f[colAmt]), amt });
        if (!hasData || DateLt(d, minD)) minD = d;
        if (!hasData || DateLt(maxD, d)) maxD = d;
        hasData = true;
    }

    if (!hasData) {
        MessageBox(hwndParent,
            L"No valid transactions were found in Data.CSV.\n\n"
            L"The file should have three columns: Date, Description, Amount.",
            L"Organize", MB_ICONINFORMATION);
        return;
    }

    // Expand the date range to cover complete months.
    Date startD{ minD.y, minD.m, 1 };
    Date endD{ maxD.y, maxD.m, DaysInMonth(maxD.y, maxD.m) };

    // Categorize each transaction and accumulate into the day map.
    std::map<std::wstring, DayRow> dayMap;

    for (auto& tx : txns) {
        std::wstring upper = ToUpper(tx.desc);
        if (IsCardPayment(upper)) continue;  // a transfer between accounts, not income or spending
        int col;
        if (tx.amount > 0.0) {
            // A refund carries its merchant's rule and offsets that category; anything else is Income
            col = FindRule(upper);
            if (col < 0) col = 0;
        } else {
            col = FindRule(upper);
            if (col < 0) {
                wchar_t snippet[512] = {};
                col = ClassifyTx(hwndParent,
                    tx.dateRaw.c_str(), tx.desc.c_str(), tx.amountRaw.c_str(),
                    snippet, ARRAYSIZE(snippet));
                if (col >= 0 && snippet[0])
                    SaveRule(ToUpper(snippet), col);
            }
        }
        if (col >= 0 && col < NUM_COLS) {
            auto& row = dayMap[DateKey(tx.date)];
            row.c[col] += tx.amount;
            if (!row.notes[col].empty()) row.notes[col] += L"; ";
            row.notes[col] += ScrubDesc(tx.desc) + L" " + FmtAmount(tx.amount);
        }
        // col == IGNORE_COL: rule matched "Ignore" — skip silently, no output
    }

    // Header row: Date, Income, Income Notes, Mortgage, Mortgage Notes, ...
    std::wstring out = L"Date";
    for (int c = 0; c < NUM_COLS; c++) {
        out += L','; out += COLS[c];
        out += L','; out += COLS[c]; out += L" Notes";
    }
    out += L"\r\n";

    // One row per calendar day across the full month span.
    for (Date cur = startD; DateLe(cur, endD); cur = NextDay(cur)) {
        out += EscCSV(DateDisplay(cur));
        auto it = dayMap.find(DateKey(cur));
        for (int c = 0; c < NUM_COLS; c++) {
            out += L',';
            if (it != dayMap.end()) out += FmtAmount(it->second.c[c]);
            out += L',';
            if (it != dayMap.end()) out += EscCSV(it->second.notes[c]);
        }
        out += L"\r\n";
    }

    if (!WriteUtf8File(OutputPath().c_str(), out)) {
        MessageBox(hwndParent,
            L"Could not write Organized.CSV.\n\n"
            L"Check that the Organization folder exists, and close the file if it is open in Excel.",
            L"Organize — Error", MB_ICONERROR);
        return;
    }

    std::wstring done = L"Organize complete!\n\n";
    if (built == BuildResult::Built)
        done += L"Data.CSV was built from " + std::to_wstring(chaseFiles) + L" Chase export(s) (" +
                std::to_wstring(chaseRows) + L" transactions).\n\n";
    done += std::wstring(L"Output saved to:\n") + OutputPath();
    MessageBox(hwndParent, done.c_str(), L"Organize — Done", MB_ICONINFORMATION);
}

// ─── Public API ───────────────────────────────────────────────────────────────

// Registers the OrgClassifyDlg class with ClassifyProc. Called once from WinMain.
void RegisterOrganizeClass(HINSTANCE hInstance) {
    WNDCLASS wc      = {};
    wc.lpfnWndProc   = ClassifyProc;
    wc.hInstance     = hInstance;
    wc.lpszClassName = CLASSIFY_CLS;
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    RegisterClass(&wc);
}

// Main-window "Organization" button handler; runs RunOrganize synchronously.
void OpenOrganize(HWND hwndParent) {
    RunOrganize(hwndParent);
}
