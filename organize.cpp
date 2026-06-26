#include "organize.h"
#include <shlobj.h>
#include <wchar.h>
#include <string>
#include <vector>
#include <map>

// ─── Column definitions ───────────────────────────────────────────────────────

static const int NUM_COLS  = 13; // exported columns
static const int IGNORE_COL = 13; // stored in rules but never written to output
static const wchar_t* const COLS[NUM_COLS] = {
    L"Income", L"Mortgage", L"Bills", L"Medical", L"Groceries",
    L"Takeout", L"Transport", L"House", L"Travel", L"Wyn",
    L"Ruby", L"Mutual Aid", L"Savings"
};

static const wchar_t* DATA_PATH   = L"C:\\Users\\Ethan Mesecher\\Desktop\\Organization\\Data.CSV";
static const wchar_t* OUTPUT_PATH = L"C:\\Users\\Ethan Mesecher\\Desktop\\Organization\\Organized.CSV";

// ─── Rules (uppercased description → column index) ────────────────────────────

static std::map<std::wstring, int> g_rules;

static void GetRulesPath(wchar_t* out) {
    wchar_t appData[MAX_PATH];
    SHGetFolderPath(NULL, CSIDL_APPDATA, NULL, 0, appData);
    wchar_t dir[MAX_PATH];
    wsprintf(dir, L"%s\\PhoenixLandDept", appData);
    CreateDirectory(dir, NULL);
    wsprintf(out, L"%s\\organize_rules.ini", dir);
}

static void LoadRules() {
    g_rules.clear();
    wchar_t path[MAX_PATH];
    GetRulesPath(path);
    // GetPrivateProfileSection returns multi-string: "KEY=val\0KEY=val\0\0"
    wchar_t buf[65536] = {};
    GetPrivateProfileSection(L"Rules", buf, ARRAYSIZE(buf), path);
    for (const wchar_t* p = buf; *p; p += wcslen(p) + 1) {
        const wchar_t* eq = wcschr(p, L'=');
        if (!eq) continue;
        std::wstring key(p, eq - p);
        int col = _wtoi(eq + 1);
        if (col >= 0 && col < NUM_COLS)
            g_rules[key] = col;
    }
}

static void SaveRule(const std::wstring& desc, int col) {
    wchar_t path[MAX_PATH], val[8];
    GetRulesPath(path);
    wsprintf(val, L"%d", col);
    WritePrivateProfileString(L"Rules", desc.c_str(), val, path);
    g_rules[desc] = col;
}

// ─── Classify dialog ──────────────────────────────────────────────────────────

#define ID_CL_COMBO   501
#define ID_CL_OK      502
#define ID_CL_SKIP    503
#define ID_CL_SNIPPET 504

struct ClassifyParams {
    const wchar_t* date;
    const wchar_t* desc;
    const wchar_t* amount;
    int     result;       // -1 = skip, 0-12 = column index
    bool    done;
    wchar_t snippet[512]; // pattern to save; user edits this down from the full description
};

static ClassifyParams* g_cp = nullptr;
static const wchar_t CLASSIFY_CLS[] = L"OrgClassifyDlg";

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
// Returns the chosen column index (0-12), or -1 to skip.
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

static std::wstring Trim(const std::wstring& s) {
    size_t a = s.find_first_not_of(L" \t\r\n");
    if (a == std::wstring::npos) return {};
    size_t b = s.find_last_not_of(L" \t\r\n");
    return s.substr(a, b - a + 1);
}

static std::wstring ToUpper(std::wstring s) {
    for (auto& c : s) c = (wchar_t)towupper(c);
    return s;
}

// Minimal CSV tokenizer — handles double-quoted fields with embedded commas/quotes.
static std::vector<std::wstring> SplitCSV(const std::wstring& line) {
    std::vector<std::wstring> out;
    std::wstring field;
    bool inQ = false;
    for (size_t i = 0; i < line.size(); ++i) {
        wchar_t c = line[i];
        if (c == L'"') {
            if (inQ && i + 1 < line.size() && line[i + 1] == L'"') {
                field += L'"'; ++i; // escaped quote inside quoted field
            } else {
                inQ = !inQ;
            }
        } else if (c == L',' && !inQ) {
            out.push_back(field); field.clear();
        } else if (c != L'\r') {
            field += c;
        }
    }
    out.push_back(field);
    return out;
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

struct Date { int y, m, d; };

static bool DateLt(const Date& a, const Date& b) {
    if (a.y != b.y) return a.y < b.y;
    if (a.m != b.m) return a.m < b.m;
    return a.d < b.d;
}
static bool DateLe(const Date& a, const Date& b) { return !DateLt(b, a); }

static int DaysInMonth(int y, int m) {
    static const int t[] = { 0,31,28,31,30,31,30,31,31,30,31,30,31 };
    int d = t[m];
    if (m == 2 && ((y % 4 == 0 && y % 100 != 0) || y % 400 == 0)) d = 29;
    return d;
}

static Date NextDay(Date d) {
    if (++d.d > DaysInMonth(d.y, d.m)) { d.d = 1; if (++d.m > 12) { d.m = 1; d.y++; } }
    return d;
}

// Accepts "M/D/YYYY", "MM/DD/YYYY", and "YYYY-MM-DD".
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

static std::wstring DateKey(const Date& d) {
    wchar_t b[16]; wsprintf(b, L"%04d-%02d-%02d", d.y, d.m, d.d); return b;
}

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

// Returns empty string for zero (leaves the cell blank in the output).
static std::wstring FmtAmount(double v) {
    if (v == 0.0) return L"";
    wchar_t buf[32];
    _snwprintf(buf, ARRAYSIZE(buf) - 1, L"%.2f", v);
    buf[ARRAYSIZE(buf) - 1] = L'\0';
    return buf;
}

// Wraps a field in quotes if it contains a comma, quote, or newline.
static std::wstring EscCSV(const std::wstring& s) {
    if (s.find_first_of(L",\"\n\r") == std::wstring::npos) return s;
    std::wstring o = L"\"";
    for (wchar_t c : s) { if (c == L'"') o += L"\"\""; else o += c; }
    return o + L'"';
}

// ─── Rule matching ────────────────────────────────────────────────────────────

// Returns the column index if any saved snippet is a substring of the uppercased
// description, or -1 if no rule matches.
static int FindRule(const std::wstring& upperDesc) {
    for (auto& kv : g_rules) {
        if (!kv.first.empty() && upperDesc.find(kv.first) != std::wstring::npos)
            return kv.second;
    }
    return -1;
}

// ─── Main organize logic ──────────────────────────────────────────────────────

struct DayRow {
    double       c[13];
    std::wstring details; // semicolon-separated descriptions of categorized transactions
    DayRow() { for (int i = 0; i < 13; i++) c[i] = 0.0; }
};

static void RunOrganize(HWND hwndParent) {
    LoadRules();

    // Read Data.CSV
    HANDLE hf = CreateFile(DATA_PATH, GENERIC_READ, FILE_SHARE_READ,
        NULL, OPEN_EXISTING, 0, NULL);
    if (hf == INVALID_HANDLE_VALUE) {
        MessageBox(hwndParent,
            L"Could not open Data.CSV.\n\n"
            L"Expected location:\n"
            L"C:\\Users\\Ethan Mesecher\\Desktop\\Organization\\Data.CSV",
            L"Organize — Error", MB_ICONERROR);
        return;
    }
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

    // Split into lines.
    std::vector<std::wstring> lines;
    {
        size_t pos = 0;
        while (pos <= content.size()) {
            size_t nl = content.find(L'\n', pos);
            if (nl == std::wstring::npos) nl = content.size();
            lines.push_back(content.substr(pos, nl - pos));
            if (nl >= content.size()) break;
            pos = nl + 1;
        }
    }

    // Parse transactions (row 0 is the header — skip it).
    struct Tx {
        Date        date;
        std::wstring dateRaw, desc, amountRaw;
        double      amount;
    };
    std::vector<Tx> txns;
    Date minD{ 9999,12,31 }, maxD{ 1900,1,1 };
    bool hasData = false;

    for (size_t i = 1; i < lines.size(); ++i) {
        std::wstring ln = Trim(lines[i]);
        if (ln.empty()) continue;
        auto f = SplitCSV(ln);
        if (f.size() < 3) continue;
        Date d{};
        if (!ParseDate(f[0], d)) continue;
        std::wstring desc = Trim(f[1]);
        if (desc.empty()) continue;
        double amt = ParseAmount(f[2]);
        txns.push_back({ d, Trim(f[0]), desc, Trim(f[2]), amt });
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
        int col = FindRule(upper);
        if (col < 0) {
            wchar_t snippet[512] = {};
            col = ClassifyTx(hwndParent,
                tx.dateRaw.c_str(), tx.desc.c_str(), tx.amountRaw.c_str(),
                snippet, ARRAYSIZE(snippet));
            if (col >= 0 && snippet[0])
                SaveRule(ToUpper(snippet), col);
        }
        if (col >= 0 && col < NUM_COLS) {
            auto& row = dayMap[DateKey(tx.date)];
            row.c[col] += tx.amount;
            if (!row.details.empty()) row.details += L"; ";
            row.details += tx.desc;
        }
        // col == IGNORE_COL: rule matched "Ignore" — skip silently, no output
    }

    // Write Organized.CSV with a UTF-8 BOM so Excel opens it correctly.
    HANDLE hOut = CreateFile(OUTPUT_PATH, GENERIC_WRITE, 0,
        NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hOut == INVALID_HANDLE_VALUE) {
        MessageBox(hwndParent,
            L"Could not write Organized.CSV.\n\n"
            L"Check that the Organization folder exists and is not read-only.",
            L"Organize — Error", MB_ICONERROR);
        return;
    }

    auto WriteW = [&](const std::wstring& ws) {
        int n = WideCharToMultiByte(CP_UTF8, 0, ws.c_str(), -1, NULL, 0, NULL, NULL);
        if (n <= 1) return;
        std::vector<char> mb(n);
        WideCharToMultiByte(CP_UTF8, 0, ws.c_str(), -1, mb.data(), n, NULL, NULL);
        DWORD nw = 0;
        WriteFile(hOut, mb.data(), n - 1, &nw, NULL); // n-1: skip null terminator
    };

    const char bom[] = { '\xEF', '\xBB', '\xBF' };
    DWORD nw = 0;
    WriteFile(hOut, bom, 3, &nw, NULL);

    // Header row
    std::wstring hdr = L"Date";
    for (int c = 0; c < NUM_COLS; c++) { hdr += L','; hdr += COLS[c]; }
    hdr += L",Details\r\n";
    WriteW(hdr);

    // One row per calendar day across the full month span.
    for (Date cur = startD; DateLe(cur, endD); cur = NextDay(cur)) {
        std::wstring row = EscCSV(DateDisplay(cur));
        auto it = dayMap.find(DateKey(cur));
        for (int c = 0; c < NUM_COLS; c++) {
            row += L',';
            if (it != dayMap.end()) row += FmtAmount(it->second.c[c]);
        }
        row += L',';
        if (it != dayMap.end()) row += EscCSV(it->second.details);
        row += L"\r\n";
        WriteW(row);
    }

    CloseHandle(hOut);

    MessageBox(hwndParent,
        L"Organize complete!\n\n"
        L"Output saved to:\n"
        L"C:\\Users\\Ethan Mesecher\\Desktop\\Organization\\Organized.CSV",
        L"Organize — Done", MB_ICONINFORMATION);
}

// ─── Public API ───────────────────────────────────────────────────────────────

void RegisterOrganizeClass(HINSTANCE hInstance) {
    WNDCLASS wc      = {};
    wc.lpfnWndProc   = ClassifyProc;
    wc.hInstance     = hInstance;
    wc.lpszClassName = CLASSIFY_CLS;
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    RegisterClass(&wc);
}

void OpenOrganize(HWND hwndParent) {
    RunOrganize(hwndParent);
}
