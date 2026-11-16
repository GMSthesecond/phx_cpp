// merge.cpp — the link window of the Merge button (column 3): asks for links to the two Ark accounts
// to merge, checks them, and hands their record ids back to main.cpp, which launches
// `py merge.py <id> <id>`. Entry points: RegisterMergeClass, AskMergeAccounts.
// Accepts a link to an account page (https://ark.phoenixenergy.com/accounts?recordId=<id>) or a bare
// record id, in either box. Touches no files or settings.
#include "merge.h"
#include <cwctype>

// ─── Link checks ───────────────────────────────────────────────────────────────

// Length of an Ark record id: 24 hex digits, e.g. 298bf830230991db2c6679eb.
static const size_t kRecordIdLength = 24;

// Spaces, tabs and line breaks, trimmed from both ends of a pasted link.
static const wchar_t kBlank[] = L" \t\r\n";

// True if s is an Ark record id: exactly kRecordIdLength hex digits (any case).
static bool IsRecordId(const std::wstring& s) {
    if (s.size() != kRecordIdLength) return false;
    for (wchar_t c : s) {
        if (!iswxdigit(c)) return false;
    }
    return true;
}

// Lowercase copy of s (record ids are compared and passed on in lowercase).
static std::wstring Lower(std::wstring s) {
    for (wchar_t& c : s) c = (wchar_t)towlower(c);
    return s;
}

// Reads the account record id out of one box of the Merge window. text may be a link to an Ark
// account page (other query parts and a #fragment allowed, any Ark domain) or the bare record id;
// blanks around it are ignored. Returns true with the id in lowercase, or false with the reason in
// error (a phrase that follows "Account 1 ").
static bool ParseAccountLink(const std::wstring& text, std::wstring& id, std::wstring& error) {
    size_t first = text.find_first_not_of(kBlank);
    if (first == std::wstring::npos) {
        error = L"is empty: paste a link to an Ark account.";
        return false;
    }
    std::wstring t = text.substr(first, text.find_last_not_of(kBlank) - first + 1);
    if (IsRecordId(t)) {
        id = Lower(t);
        return true;
    }
    if (t.find_first_of(kBlank) != std::wstring::npos) {
        error = L"has more than one thing in it: paste one link per box.";
        return false;
    }

    size_t question = t.find(L'?');
    std::wstring path = Lower(t.substr(0, question));
    while (!path.empty() && path.back() == L'/') path.pop_back();
    const std::wstring accounts = L"/accounts";
    if (question == std::wstring::npos || path.find(L"://") == std::wstring::npos ||
        path.size() < accounts.size() || path.compare(path.size() - accounts.size(), accounts.size(), accounts) != 0) {
        error = L"isn't a link to an Ark account (it should contain /accounts?recordId=).";
        return false;
    }

    std::wstring query = t.substr(question + 1);
    query = query.substr(0, query.find(L'#'));
    size_t start = 0;
    while (start <= query.size()) {
        size_t amp = query.find(L'&', start);
        std::wstring part = query.substr(start, amp == std::wstring::npos ? std::wstring::npos : amp - start);
        size_t eq = part.find(L'=');
        if (eq != std::wstring::npos && Lower(part.substr(0, eq)) == L"recordid") {
            std::wstring value = part.substr(eq + 1);
            if (!IsRecordId(value)) {
                error = L"has a record id that isn't 24 letters and digits: copy the link again.";
                return false;
            }
            id = Lower(value);
            return true;
        }
        if (amp == std::wstring::npos) break;
        start = amp + 1;
    }
    error = L"has no recordId in it: copy the link from the account's page.";
    return false;
}

// Checks both boxes: each must hold an account link (ParseAccountLink) and they must be two
// different accounts. Returns true with args = "<first id> <second id>" (merge.py's arguments,
// in the order typed), or false with a full sentence for the window's error line in error.
static bool CheckMergeLinks(const std::wstring& first, const std::wstring& second,
                            std::wstring& args, std::wstring& error) {
    std::wstring ids[2], why;
    const std::wstring* texts[2] = { &first, &second };
    for (int i = 0; i < 2; i++) {
        if (!ParseAccountLink(*texts[i], ids[i], why)) {
            error = L"Account " + std::to_wstring(i + 1) + L" " + why;
            return false;
        }
    }
    if (ids[0] == ids[1]) {
        error = L"Both links are the same account: paste the other account's link in one box.";
        return false;
    }
    args = ids[0] + L" " + ids[1];
    return true;
}

// ─── Window ────────────────────────────────────────────────────────────────────

// Control ids in the Merge window (Continue and Cancel use IDOK / IDCANCEL, so Enter and Esc work).
#define ID_MG_FIRST   701  // Account 1 link box
#define ID_MG_SECOND  702  // Account 2 link box
#define ID_MG_ERROR   703  // red line under the boxes saying what's wrong with the links

// Window class name of the Merge window (tests/buttons.py uses it to find the window).
static const wchar_t MERGE_CLS[] = L"MergeDlg";
// Client area size of the Merge window, in pixels.
static const int kMergeW = 540, kMergeH = 200;

// Set when the Merge window closes; ends AskMergeAccounts' nested message loop.
static bool g_mergeDone = false;
// True if the window closed through Continue with valid links (false: Cancel / close).
static bool g_mergeAccepted = false;
// merge.py's arguments from the last accepted window ("<id> <id>").
static std::wstring g_mergeArgs;

// Text of control id in hwnd.
static std::wstring ControlText(HWND hwnd, int id) {
    HWND control = GetDlgItem(hwnd, id);
    std::wstring text(GetWindowTextLength(control) + 1, L'\0');
    text.resize(GetWindowText(control, &text[0], (int)text.size()));
    return text;
}

// Closes the Merge window: ends AskMergeAccounts' loop and re-enables the launcher BEFORE destroying
// the window, since Windows gives the focus back to an owner only if it's enabled as its popup goes
// (otherwise another app's window comes to the front).
static void CloseMergeWindow(HWND hwnd) {
    g_mergeDone = true;
    EnableWindow(GetWindow(hwnd, GW_OWNER), TRUE);
    DestroyWindow(hwnd);
}

// Window proc of the Merge window: instructions, two link boxes, the error line, Continue and
// Cancel. Continue checks the links (CheckMergeLinks): valid ones close the window accepted,
// otherwise the error line says what's wrong and the window stays open. Cancel / close / Esc
// close it without launching anything (each close goes through CloseMergeWindow).
static LRESULT CALLBACK MergeProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        HINSTANCE hi = ((LPCREATESTRUCT)lp)->hInstance;
        HFONT font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);
        struct { const wchar_t* cls; const wchar_t* text; DWORD style; int x, y, w, h, id; } controls[] = {
            { L"STATIC", L"Paste links to the two Ark accounts to merge (copy each from the browser's "
                         L"address bar on the account's page). The order doesn't matter.",
              SS_LEFT, 10, 10, 520, 30, 0 },
            { L"STATIC", L"Account 1:", SS_LEFT, 10, 56, 70, 20, 0 },
            { L"EDIT", L"", WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL, 85, 53, 445, 22, ID_MG_FIRST },
            { L"STATIC", L"Account 2:", SS_LEFT, 10, 90, 70, 20, 0 },
            { L"EDIT", L"", WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL, 85, 87, 445, 22, ID_MG_SECOND },
            { L"STATIC", L"", SS_LEFT | SS_NOPREFIX, 10, 120, 520, 30, ID_MG_ERROR },
            { L"BUTTON", L"Continue", WS_TABSTOP | BS_DEFPUSHBUTTON, 320, 160, 100, 28, IDOK },
            { L"BUTTON", L"Cancel", WS_TABSTOP | BS_PUSHBUTTON, 430, 160, 100, 28, IDCANCEL },
        };
        for (auto& c : controls) {
            HWND h = CreateWindowEx(0, c.cls, c.text, WS_CHILD | WS_VISIBLE | c.style, c.x, c.y, c.w, c.h,
                                    hwnd, (HMENU)(UINT_PTR)c.id, hi, NULL);
            SendMessage(h, WM_SETFONT, (WPARAM)font, FALSE);
        }
        return 0;
    }
    case WM_CTLCOLORSTATIC: {
        HDC hdc = (HDC)wp;
        SetBkColor(hdc, GetSysColor(COLOR_BTNFACE));
        SetTextColor(hdc, GetDlgCtrlID((HWND)lp) == ID_MG_ERROR ? RGB(192, 0, 0) : GetSysColor(COLOR_WINDOWTEXT));
        return (LRESULT)GetSysColorBrush(COLOR_BTNFACE);
    }
    case DM_GETDEFID:
        return MAKELRESULT(IDOK, DC_HASDEFID);  // Enter in a link box presses Continue
    case WM_COMMAND:
        if (LOWORD(wp) == IDOK) {
            std::wstring error;
            if (CheckMergeLinks(ControlText(hwnd, ID_MG_FIRST), ControlText(hwnd, ID_MG_SECOND), g_mergeArgs, error)) {
                g_mergeAccepted = true;
                CloseMergeWindow(hwnd);
            } else {
                SetDlgItemText(hwnd, ID_MG_ERROR, error.c_str());
                SetFocus(GetDlgItem(hwnd, error.rfind(L"Account 2", 0) == 0 ? ID_MG_SECOND : ID_MG_FIRST));
            }
        } else if (LOWORD(wp) == IDCANCEL) {
            CloseMergeWindow(hwnd);
        }
        return 0;
    case WM_CLOSE:
        CloseMergeWindow(hwnd);
        return 0;
    }
    return DefWindowProc(hwnd, msg, wp, lp);
}

// Registers the MergeDlg class with MergeProc. Called once from WinMain.
void RegisterMergeClass(HINSTANCE hInstance) {
    WNDCLASS wc      = {};
    wc.lpfnWndProc   = MergeProc;
    wc.hInstance     = hInstance;
    wc.lpszClassName = MERGE_CLS;
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    RegisterClass(&wc);
}

// Shows the Merge window modally: disables hwndParent and runs a nested message loop (with
// IsDialogMessage, so Tab, Enter and Esc work) until the window closes. Returns true with
// args = merge.py's arguments if the user pressed Continue with valid links. Called by the Merge button.
bool AskMergeAccounts(HWND hwndParent, std::wstring& args) {
    g_mergeDone = false;
    g_mergeAccepted = false;
    g_mergeArgs.clear();

    DWORD style = WS_POPUP | WS_CAPTION | WS_SYSMENU, exStyle = WS_EX_DLGMODALFRAME | WS_EX_CONTROLPARENT;
    RECT size = { 0, 0, kMergeW, kMergeH };
    AdjustWindowRectEx(&size, style, FALSE, exStyle);
    RECT owner = {};
    GetWindowRect(hwndParent, &owner);
    int w = size.right - size.left, h = size.bottom - size.top;

    EnableWindow(hwndParent, FALSE);
    HWND hwnd = CreateWindowEx(exStyle, MERGE_CLS, L"Merge Accounts", style,
        owner.left + (owner.right - owner.left - w) / 2, owner.top + (owner.bottom - owner.top - h) / 3, w, h,
        hwndParent, NULL, GetModuleHandle(NULL), NULL);
    if (!hwnd) {
        EnableWindow(hwndParent, TRUE);
        return false;
    }
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);
    SetFocus(GetDlgItem(hwnd, ID_MG_FIRST));
    MSG msg;
    while (!g_mergeDone) {
        BOOL r = GetMessage(&msg, NULL, 0, 0);
        if (r == 0) { PostQuitMessage((int)msg.wParam); break; }
        if (r < 0) break;
        if (IsWindow(hwnd) && IsDialogMessage(hwnd, &msg)) continue;
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    EnableWindow(hwndParent, TRUE);
    SetForegroundWindow(hwndParent);
    if (g_mergeAccepted) args = g_mergeArgs;
    return g_mergeAccepted;
}
