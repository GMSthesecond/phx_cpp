#include "settings.h"
#include <shlobj.h>

static const TCHAR SETTINGS_CLASS[] = TEXT("SettingsWindow");

static HWND  s_hwndParent   = NULL;
static HWND  s_hwndSettings = NULL;

// Defaults match the hardcoded paths the Python scripts previously used
static TCHAR s_folderDMD[MAX_PATH] = TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\DMD");
static TCHAR s_folderSTR[MAX_PATH] = TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\AOI-STR");
static TCHAR s_folderCD[MAX_PATH]  = TEXT("C:\\Users\\Ethan Mesecher\\Desktop\\Close Date");

static void GetIniPath(TCHAR* out) {
    TCHAR appData[MAX_PATH];
    SHGetFolderPath(NULL, CSIDL_APPDATA, NULL, 0, appData);
    TCHAR dir[MAX_PATH];
    wsprintf(dir, TEXT("%s\\PhoenixLandDept"), appData);
    CreateDirectory(dir, NULL);
    wsprintf(out, TEXT("%s\\settings.ini"), dir);
}

void LoadFolders() {
    TCHAR iniPath[MAX_PATH];
    GetIniPath(iniPath);
    // GetPrivateProfileString writes the default into the buffer if the key is absent,
    // so s_folderDMD/STR keep their compiled-in values on first launch.
    GetPrivateProfileString(TEXT("Folders"), TEXT("DataMeetingDownload"),
        s_folderDMD, s_folderDMD, MAX_PATH, iniPath);
    GetPrivateProfileString(TEXT("Folders"), TEXT("STRVerification"),
        s_folderSTR, s_folderSTR, MAX_PATH, iniPath);
    GetPrivateProfileString(TEXT("Folders"), TEXT("CloseDates"),
        s_folderCD, s_folderCD, MAX_PATH, iniPath);
}

static void SaveFolders() {
    TCHAR iniPath[MAX_PATH];
    GetIniPath(iniPath);
    WritePrivateProfileString(TEXT("Folders"), TEXT("DataMeetingDownload"), s_folderDMD, iniPath);
    WritePrivateProfileString(TEXT("Folders"), TEXT("STRVerification"),     s_folderSTR, iniPath);
    WritePrivateProfileString(TEXT("Folders"), TEXT("CloseDates"),          s_folderCD,  iniPath);
}

// Opens a Vista-style folder picker and writes the chosen path into pathOut.
// Returns true if the user confirmed a selection, false if they cancelled.
static bool PickFolder(HWND hwndOwner, TCHAR* pathOut) {
    IFileDialog* pfd = nullptr;
    if (FAILED(CoCreateInstance(CLSID_FileOpenDialog, NULL, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&pfd))))
        return false;
    DWORD options;
    pfd->GetOptions(&options);
    pfd->SetOptions(options | FOS_PICKFOLDERS);
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

static LRESULT CALLBACK SettingsProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        case WM_CREATE: {
            HINSTANCE hInst = ((LPCREATESTRUCT)lParam)->hInstance;

            // Row 1: Data Meeting Download
            CreateWindowEx(0, TEXT("STATIC"), TEXT("Data Meeting Download:"),
                WS_CHILD | WS_VISIBLE | SS_LEFT,
                10, 22, 200, 20, hwnd, NULL, hInst, NULL);
            CreateWindowEx(0, TEXT("STATIC"), s_folderDMD,
                WS_CHILD | WS_VISIBLE | SS_LEFT | SS_NOPREFIX,
                215, 22, 450, 20, hwnd, (HMENU)ID_FOLDER_DMD_LABEL, hInst, NULL);
            CreateWindowEx(0, TEXT("BUTTON"), TEXT("Change"),
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                670, 17, 80, 30, hwnd, (HMENU)ID_FOLDER_DMD_CHANGE, hInst, NULL);

            // Row 2: STR Verification
            CreateWindowEx(0, TEXT("STATIC"), TEXT("STR Verification:"),
                WS_CHILD | WS_VISIBLE | SS_LEFT,
                10, 62, 200, 20, hwnd, NULL, hInst, NULL);
            CreateWindowEx(0, TEXT("STATIC"), s_folderSTR,
                WS_CHILD | WS_VISIBLE | SS_LEFT | SS_NOPREFIX,
                215, 62, 450, 20, hwnd, (HMENU)ID_FOLDER_STR_LABEL, hInst, NULL);
            CreateWindowEx(0, TEXT("BUTTON"), TEXT("Change"),
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                670, 57, 80, 30, hwnd, (HMENU)ID_FOLDER_STR_CHANGE, hInst, NULL);

            // Row 3: Close Dates
            CreateWindowEx(0, TEXT("STATIC"), TEXT("Close Dates:"),
                WS_CHILD | WS_VISIBLE | SS_LEFT,
                10, 102, 200, 20, hwnd, NULL, hInst, NULL);
            CreateWindowEx(0, TEXT("STATIC"), s_folderCD,
                WS_CHILD | WS_VISIBLE | SS_LEFT | SS_NOPREFIX,
                215, 102, 450, 20, hwnd, (HMENU)ID_FOLDER_CD_LABEL, hInst, NULL);
            CreateWindowEx(0, TEXT("BUTTON"), TEXT("Change"),
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                670, 97, 80, 30, hwnd, (HMENU)ID_FOLDER_CD_CHANGE, hInst, NULL);

            return 0;
        }
        case WM_COMMAND: {
            UINT id = LOWORD(wParam);
            if (id == ID_FOLDER_DMD_CHANGE || id == ID_FOLDER_STR_CHANGE || id == ID_FOLDER_CD_CHANGE) {
                TCHAR* folder  = (id == ID_FOLDER_DMD_CHANGE) ? s_folderDMD
                               : (id == ID_FOLDER_STR_CHANGE) ? s_folderSTR
                               :                                s_folderCD;
                UINT   labelId = (id == ID_FOLDER_DMD_CHANGE) ? ID_FOLDER_DMD_LABEL
                               : (id == ID_FOLDER_STR_CHANGE) ? ID_FOLDER_STR_LABEL
                               :                                ID_FOLDER_CD_LABEL;
                if (PickFolder(hwnd, folder)) {
                    SetWindowText(GetDlgItem(hwnd, labelId), folder);
                    SaveFolders();
                }
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

void RegisterSettingsClass(HINSTANCE hInstance) {
    WNDCLASS wcs      = {};
    wcs.lpfnWndProc   = SettingsProc;
    wcs.hInstance     = hInstance;
    wcs.lpszClassName = SETTINGS_CLASS;
    wcs.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wcs.hCursor       = LoadCursor(NULL, IDC_ARROW);
    RegisterClass(&wcs);
}

void OpenSettings(HWND hwndParent) {
    if (s_hwndSettings != NULL) return;

    s_hwndParent = hwndParent;
    EnableWindow(hwndParent, FALSE);

    s_hwndSettings = CreateWindowEx(
        WS_EX_DLGMODALFRAME,
        SETTINGS_CLASS, TEXT("Settings"),
        WS_POPUP | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT, CW_USEDEFAULT, 770, 170,
        hwndParent, NULL, GetModuleHandle(NULL), NULL
    );
    ShowWindow(s_hwndSettings, SW_SHOW);
}
