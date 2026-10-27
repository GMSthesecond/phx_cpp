// Settings window: lets the user set every folder, file and sign-in the Python scripts and the
// Organization / Rename dialogs use. Opened by the main window's "Settings" button. Entry points:
// LoadSettings, RegisterSettingsClass, OpenSettings, GetSetting, SetSetting.
// Reads/writes %APPDATA%\PhoenixLandDept\settings.ini: every row of s_settings ([Folders] keys,
// [Files] IndexWorkbook and HearingDockets, [Credentials], [EnverusCredentials], [SlackCredentials]). The Python
// scripts read the same keys via ark_common.read_folder / read_setting / read_credentials.
#include "settings.h"
#include <shlobj.h>

// Window class name for the settings popup.
static const TCHAR SETTINGS_CLASS[] = TEXT("SettingsWindow");

// Main window that was disabled while settings is open; re-enabled on close.
static HWND  s_hwndParent   = NULL;
// The open settings window, or NULL when closed (guards against opening twice).
static HWND  s_hwndSettings = NULL;

// How a row is edited: a folder or file picked with the Windows picker, or typed text
// (SETTING_SECRET is typed text shown as dots: passwords and tokens).
enum SettingKind { SETTING_FOLDER, SETTING_FILE, SETTING_TEXT, SETTING_SECRET };

// One row of the settings window and the settings.ini value behind it.
struct Setting {
    const TCHAR* section;   // settings.ini section, e.g. Folders
    const TCHAR* key;       // key in that section; the Python scripts read the same name
    const TCHAR* label;     // shown at the left of the row
    SettingKind kind;       // how the value is edited
    TCHAR value[MAX_PATH];  // current value; starts as the default the scripts also use
};

// Every row of the settings window, top to bottom. Defaults match the scripts' fallbacks.
// To add a setting: add a row here, read it in the script (ark_common.read_folder for [Folders]),
// and add it to the settings.ini table in docs/ARCHITECTURE.md (tests/test_wiring.py checks).
static Setting s_settings[] = {
    { TEXT("Folders"), TEXT("DataMeetingDownload"), TEXT("Data Meeting Download:"), SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\DMD") },
    { TEXT("Folders"), TEXT("STRVerification"), TEXT("STR Verification:"),   SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\STR") },
    { TEXT("Folders"), TEXT("AOI"),             TEXT("AOI:"),                SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\AOI") },
    { TEXT("Folders"), TEXT("CloseDates"),      TEXT("Close Date:"),         SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Close Date") },
    { TEXT("Folders"), TEXT("Maps"),            TEXT("Map:"),                SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Maps") },
    { TEXT("Folders"), TEXT("PPIQ"),            TEXT("PPIQ:"),               SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\PPIQ") },
    { TEXT("Folders"), TEXT("TPPLHPP"),         TEXT("TPP-LHPP:"),           SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\TPP-LHPP") },
    { TEXT("Folders"), TEXT("CostToExtend"),    TEXT("Cost to Extend:"),     SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\C2E") },
    { TEXT("Folders"), TEXT("CaseMatchup"),     TEXT("Case Matchup:"),       SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Unit Connect to Cases") },
    { TEXT("Folders"), TEXT("CaseUnitNames"),   TEXT("Case Unit Names:"),    SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Cases Unit Names") },
    { TEXT("Folders"), TEXT("NonHBPMI"),        TEXT("Case Update:"),        SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Case Update") },
    { TEXT("Folders"), TEXT("DocketUpdates"),   TEXT("Docket Updates:"),     SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Docket Updates") },
    { TEXT("Files"),   TEXT("HearingDockets"),  TEXT("Hearing Dockets:"),    SETTING_FILE,   TEXT("C:\\Cloud\\Box\\Land\\01. Permit & Hearing Tracking\\02. State Permits & Hearings\\ND,MT,UT,WY - Hearing Dockets.xlsx") },
    { TEXT("Folders"), TEXT("SIB"),             TEXT("Section Id Blank:"),   SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\SIB") },
    { TEXT("Folders"), TEXT("QQ"),              TEXT("QQ Checker:"),         SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\QQ") },
    { TEXT("Folders"), TEXT("Deceased"),        TEXT("Deceased:"),           SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Bring out your dead") },
    { TEXT("Folders"), TEXT("Index"),           TEXT("Index CSVs:"),         SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Index") },
    { TEXT("Files"),   TEXT("IndexWorkbook"),   TEXT("Index workbook:"),     SETTING_FILE,   TEXT("C:\\Cloud\\Box\\Ethan Mesecher\\Index of Scanned Docs.xlsx") },
    { TEXT("Folders"), TEXT("Organize"),        TEXT("Organize:"),           SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Organization") },
    { TEXT("Folders"), TEXT("Rename"),          TEXT("Rename:"),             SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Rename") },
    { TEXT("Folders"), TEXT("MirrorArchive"),   TEXT("Mirror archive:"),     SETTING_FOLDER, TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Dailies\\Archive") },
    { TEXT("Credentials"),        TEXT("username"),   TEXT("Ark email:"),        SETTING_TEXT,   TEXT("") },
    { TEXT("Credentials"),        TEXT("password"),   TEXT("Ark password:"),     SETTING_SECRET, TEXT("") },
    { TEXT("EnverusCredentials"), TEXT("identifier"), TEXT("Enverus email:"),    SETTING_TEXT,   TEXT("") },
    { TEXT("EnverusCredentials"), TEXT("password"),   TEXT("Enverus password:"), SETTING_SECRET, TEXT("") },
    { TEXT("SlackCredentials"),   TEXT("token"),      TEXT("Slack token:"),      SETTING_SECRET, TEXT("") },
};
// Number of rows in s_settings.
static const int kNumSettings = (int)(sizeof(s_settings) / sizeof(s_settings[0]));

// Writes the settings.ini path into out (MAX_PATH); creates %APPDATA%\PhoenixLandDept if missing.
static void GetIniPath(TCHAR* out) {
    TCHAR appData[MAX_PATH];
    SHGetFolderPath(NULL, CSIDL_APPDATA, NULL, 0, appData);
    TCHAR dir[MAX_PATH];
    wsprintf(dir, TEXT("%s\\PhoenixLandDept"), appData);
    CreateDirectory(dir, NULL);
    wsprintf(out, TEXT("%s\\settings.ini"), dir);
}

// Loads every s_settings row from settings.ini. Called once from WinMain; does not write the INI.
void LoadSettings() {
    TCHAR iniPath[MAX_PATH];
    GetIniPath(iniPath);
    // GetPrivateProfileString writes the default into the buffer if the key is absent,
    // so each row keeps its compiled-in value on first launch.
    for (Setting& s : s_settings) {
        GetPrivateProfileString(s.section, s.key, s.value, s.value, MAX_PATH, iniPath);
    }
}

// Writes one row to settings.ini (only that key, so a row never saves a default it wasn't changed from).
static void SaveSetting(const Setting& s) {
    TCHAR iniPath[MAX_PATH];
    GetIniPath(iniPath);
    WritePrivateProfileString(s.section, s.key, s.value, iniPath);
}

// The s_settings row for [section] key (case-insensitive, like the INI), or NULL.
static Setting* FindSetting(const TCHAR* section, const TCHAR* key) {
    for (Setting& s : s_settings) {
        if (lstrcmpi(s.section, section) == 0 && lstrcmpi(s.key, key) == 0) return &s;
    }
    return NULL;
}

// Current value of [section] key, or "" if it isn't a row. See settings.h.
const TCHAR* GetSetting(const TCHAR* section, const TCHAR* key) {
    Setting* s = FindSetting(section, key);
    return s ? s->value : TEXT("");
}

// Changes [section] key in memory only. See settings.h.
bool SetSetting(const TCHAR* section, const TCHAR* key, const TCHAR* value) {
    Setting* s = FindSetting(section, key);
    if (!s) return false;
    lstrcpyn(s->value, value, MAX_PATH);
    return true;
}

// Opens the Windows picker for a folder (pickFolder) or an Excel file, starting from pathOut's
// current value, and writes the choice into pathOut. Returns false if the user cancelled.
static bool PickPath(HWND hwndOwner, TCHAR* pathOut, bool pickFolder) {
    IFileDialog* pfd = nullptr;
    if (FAILED(CoCreateInstance(CLSID_FileOpenDialog, NULL, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&pfd))))
        return false;
    DWORD options;
    pfd->GetOptions(&options);
    if (pickFolder) {
        pfd->SetOptions(options | FOS_PICKFOLDERS);
    } else {
        COMDLG_FILTERSPEC types[] = { { L"Excel workbook", L"*.xlsx" }, { L"All files", L"*.*" } };
        pfd->SetFileTypes(2, types);
        pfd->SetOptions(options | FOS_FILEMUSTEXIST);
    }
    bool ok = false;
    if (SUCCEEDED(pfd->Show(hwndOwner))) {
        IShellItem* psi = nullptr;
        if (SUCCEEDED(pfd->GetResult(&psi))) {
            PWSTR path = nullptr;
            if (SUCCEEDED(psi->GetDisplayName(SIGDN_FILESYSPATH, &path))) {
                lstrcpyn(pathOut, path, MAX_PATH);
                CoTaskMemFree(path);
                ok = true;
            }
            psi->Release();
        }
    }
    pfd->Release();
    return ok;
}

// Row geometry of the settings window, in pixels.
static const int kRowTop = 12, kRowPitch = 30, kLabelW = 160, kValueX = 175, kValueW = 490, kButtonX = 675;

// Window proc for the settings popup. WM_CREATE builds one row per s_settings entry: a label,
// the value (a path label for folders/files, a text box for typed values) and a Change / Save button.
// Change runs PickPath; Save takes the text box. Either updates the row and calls SaveSetting.
// WM_DESTROY re-enables the parent and clears s_hwndSettings.
static LRESULT CALLBACK SettingsProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        case WM_CREATE: {
            HINSTANCE hInst = ((LPCREATESTRUCT)lParam)->hInstance;
            HFONT font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);
            for (int i = 0; i < kNumSettings; i++) {
                const Setting& s = s_settings[i];
                int y = kRowTop + i * kRowPitch;
                HWND label = CreateWindowEx(0, TEXT("STATIC"), s.label, WS_CHILD | WS_VISIBLE | SS_LEFT,
                    10, y + 4, kLabelW, 20, hwnd, NULL, hInst, NULL);
                bool typed = s.kind == SETTING_TEXT || s.kind == SETTING_SECRET;
                HWND value;
                if (typed) {
                    DWORD style = WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL |
                                  (s.kind == SETTING_SECRET ? ES_PASSWORD : 0);
                    value = CreateWindowEx(WS_EX_CLIENTEDGE, TEXT("EDIT"), s.value, style,
                        kValueX, y + 1, kValueW, 23, hwnd, (HMENU)(UINT_PTR)(ID_SETTING_VALUE_BASE + i), hInst, NULL);
                } else {
                    value = CreateWindowEx(0, TEXT("STATIC"), s.value,
                        WS_CHILD | WS_VISIBLE | SS_LEFT | SS_NOPREFIX | SS_PATHELLIPSIS,
                        kValueX, y + 4, kValueW, 20, hwnd, (HMENU)(UINT_PTR)(ID_SETTING_VALUE_BASE + i), hInst, NULL);
                }
                HWND button = CreateWindowEx(0, TEXT("BUTTON"), typed ? TEXT("Save") : TEXT("Change"),
                    WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                    kButtonX, y, 80, 25, hwnd, (HMENU)(UINT_PTR)(ID_SETTING_BUTTON_BASE + i), hInst, NULL);
                SendMessage(label, WM_SETFONT, (WPARAM)font, FALSE);
                SendMessage(value, WM_SETFONT, (WPARAM)font, FALSE);
                SendMessage(button, WM_SETFONT, (WPARAM)font, FALSE);
            }
            return 0;
        }
        case WM_COMMAND: {
            // Typing in a text box after a save turns its "Saved" button back into "Save"
            int typedRow = (int)LOWORD(wParam) - ID_SETTING_VALUE_BASE;
            if (HIWORD(wParam) == EN_CHANGE && typedRow >= 0 && typedRow < kNumSettings) {
                SetWindowText(GetDlgItem(hwnd, ID_SETTING_BUTTON_BASE + typedRow), TEXT("Save"));
                return 0;
            }
            int i = (int)LOWORD(wParam) - ID_SETTING_BUTTON_BASE;
            if (i < 0 || i >= kNumSettings || HIWORD(wParam) != BN_CLICKED) return 0;
            Setting& s = s_settings[i];
            HWND value = GetDlgItem(hwnd, ID_SETTING_VALUE_BASE + i);
            if (s.kind == SETTING_TEXT || s.kind == SETTING_SECRET) {
                GetWindowText(value, s.value, MAX_PATH);
                SaveSetting(s);
                SetWindowText(GetDlgItem(hwnd, ID_SETTING_BUTTON_BASE + i), TEXT("Saved"));
            } else if (PickPath(hwnd, s.value, s.kind == SETTING_FOLDER)) {
                SetWindowText(value, s.value);
                SaveSetting(s);
            }
            return 0;
        }
        case WM_DESTROY:
            EnableWindow(s_hwndParent, TRUE);
            SetForegroundWindow(s_hwndParent);
            s_hwndSettings = NULL;
            return 0;
    }
    return DefWindowProc(hwnd, msg, wParam, lParam);
}

// Registers the SettingsWindow class with SettingsProc. Called once from WinMain.
void RegisterSettingsClass(HINSTANCE hInstance) {
    WNDCLASS wcs      = {};
    wcs.lpfnWndProc   = SettingsProc;
    wcs.hInstance     = hInstance;
    wcs.lpszClassName = SETTINGS_CLASS;
    wcs.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wcs.hCursor       = LoadCursor(NULL, IDC_ARROW);
    RegisterClass(&wcs);
}

// Shows the settings popup modelessly but disables hwndParent until it closes, sized to fit
// every row. No-op if already open. Called by the main window's Settings button.
void OpenSettings(HWND hwndParent) {
    if (s_hwndSettings != NULL) return;

    s_hwndParent = hwndParent;
    EnableWindow(hwndParent, FALSE);

    RECT rc = { 0, 0, kButtonX + 80 + 15, kRowTop + kNumSettings * kRowPitch + 10 };
    AdjustWindowRectEx(&rc, WS_POPUP | WS_CAPTION | WS_SYSMENU, FALSE, WS_EX_DLGMODALFRAME);
    s_hwndSettings = CreateWindowEx(
        WS_EX_DLGMODALFRAME,
        SETTINGS_CLASS, TEXT("Settings"),
        WS_POPUP | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT, CW_USEDEFAULT, rc.right - rc.left, rc.bottom - rc.top,
        hwndParent, NULL, GetModuleHandle(NULL), NULL
    );
    ShowWindow(s_hwndSettings, SW_SHOW);
}
