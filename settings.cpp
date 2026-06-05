#include "settings.h"
#include <shlobj.h>  // SHGetFolderPath for locating %APPDATA%

// Internal window class name — only settings.cpp needs this string
static const TCHAR SETTINGS_CLASS[] = TEXT("SettingsWindow");

// Binding state — all private to this translation unit except g_bindA/g_bindB
KeyBinding   g_bindA = { 'A', TEXT("A") }; // initial binding for button A
KeyBinding   g_bindB = { 'B', TEXT("B") }; // initial binding for button B

enum ListenTarget { LISTEN_NONE, LISTEN_A, LISTEN_B };
static ListenTarget s_listenTarget = LISTEN_NONE; // which button is being rebound right now; LISTEN_NONE = idle
static HHOOK        s_hKeyHook     = NULL;         // handle for the low-level keyboard hook; NULL when not listening
static HHOOK        s_hMouseHook   = NULL;         // handle for the low-level mouse hook; NULL when not listening
static HWND         s_hwndParent   = NULL;         // main window handle, stored when OpenSettings is called
static HWND         s_hwndSettings = NULL;         // settings window handle; NULL when closed

// Fills 'label' with a readable name for a virtual key code (e.g. VK_LBUTTON → "LMB", 0x41 → "A")
static void GetVKLabel(UINT vk, TCHAR* label, int len) {
    switch (vk) {
        case VK_LBUTTON:  lstrcpyn(label, TEXT("LMB"), len); return; // left mouse button
        case VK_RBUTTON:  lstrcpyn(label, TEXT("RMB"), len); return; // right mouse button
        case VK_MBUTTON:  lstrcpyn(label, TEXT("MMB"), len); return; // middle mouse button
        case VK_XBUTTON1: lstrcpyn(label, TEXT("MB4"), len); return; // first side mouse button
        case VK_XBUTTON2: lstrcpyn(label, TEXT("MB5"), len); return; // second side mouse button
    }
    // For keyboard keys, ask Windows for the name via the scan code
    UINT scan = MapVirtualKey(vk, MAPVK_VK_TO_VSC); // convert VK code to hardware scan code
    if (!GetKeyNameText((LONG)(scan << 16), label, len))
        wsprintf(label, TEXT("VK%02X"), vk); // fallback hex label for any unrecognised key
}

// Removes both hooks and re-enables the bind buttons in the settings window
static void StopListening() {
    if (s_hKeyHook)   { UnhookWindowsHookEx(s_hKeyHook);   s_hKeyHook   = NULL; } // remove keyboard hook
    if (s_hMouseHook) { UnhookWindowsHookEx(s_hMouseHook); s_hMouseHook = NULL; } // remove mouse hook
    s_listenTarget = LISTEN_NONE;

    if (s_hwndSettings) {
        EnableWindow(GetDlgItem(s_hwndSettings, ID_BIND_BTN_A), TRUE); // re-enable A bind button
        EnableWindow(GetDlgItem(s_hwndSettings, ID_BIND_BTN_B), TRUE); // re-enable B bind button
    }
}

// Applies the captured vk as the new binding for whichever slot is currently listening and updates both windows
static void FinishBinding(UINT vk) {
    KeyBinding* slot   = (s_listenTarget == LISTEN_A) ? &g_bindA      : &g_bindB;
    UINT        mainId = (s_listenTarget == LISTEN_A) ? ID_BUTTON_A   : ID_BUTTON_B;   // button in the main window to relabel
    UINT        bindId = (s_listenTarget == LISTEN_A) ? ID_BIND_BTN_A : ID_BIND_BTN_B; // button in settings to relabel

    slot->vk = vk;
    GetVKLabel(vk, slot->label, 32); // build the display label from the new VK code

    if (s_hwndSettings) SetWindowText(GetDlgItem(s_hwndSettings, bindId), slot->label); // update settings bind button
    if (s_hwndParent)   SetWindowText(GetDlgItem(s_hwndParent,   mainId), slot->label); // update main window button

    StopListening();
    SaveBindings(); // persist immediately so the new binding survives a restart
}

// Cancels an in-progress rebind (triggered by Esc) and restores button text without changing the binding
static void CancelBinding() {
    if (s_hwndSettings) {
        SetWindowText(GetDlgItem(s_hwndSettings, ID_BIND_BTN_A), g_bindA.label); // restore A button to its current label
        SetWindowText(GetDlgItem(s_hwndSettings, ID_BIND_BTN_B), g_bindB.label); // restore B button to its current label
    }
    StopListening();
}

// Low-level keyboard hook — fires for every key press system-wide while installed
static LRESULT CALLBACK LLKeyProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode == HC_ACTION && wParam == WM_KEYDOWN && s_listenTarget != LISTEN_NONE) {
        KBDLLHOOKSTRUCT* kb = (KBDLLHOOKSTRUCT*)lParam; // contains the virtual key code of the pressed key
        if (kb->vkCode == VK_ESCAPE)
            CancelBinding();
        else
            FinishBinding(kb->vkCode);
        return 1; // return non-zero to consume the key so it doesn't reach any other window
    }
    return CallNextHookEx(NULL, nCode, wParam, lParam); // pass through anything not being captured
}

// Low-level mouse hook — fires for every mouse event system-wide while installed
static LRESULT CALLBACK LLMouseProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode == HC_ACTION && s_listenTarget != LISTEN_NONE) {
        UINT vk = 0;
        if      (wParam == WM_LBUTTONDOWN) vk = VK_LBUTTON;
        else if (wParam == WM_RBUTTONDOWN) vk = VK_RBUTTON;
        else if (wParam == WM_MBUTTONDOWN) vk = VK_MBUTTON;
        else if (wParam == WM_XBUTTONDOWN) {
            MSLLHOOKSTRUCT* ms = (MSLLHOOKSTRUCT*)lParam; // contains extended mouse data including which X button
            vk = (HIWORD(ms->mouseData) == XBUTTON1) ? VK_XBUTTON1 : VK_XBUTTON2;
        }
        if (vk) {
            FinishBinding(vk);
            return 1; // consume the click so it doesn't also activate whatever was under the cursor
        }
    }
    return CallNextHookEx(NULL, nCode, wParam, lParam);
}

// Called by Windows for every event on the settings popup window
static LRESULT CALLBACK SettingsProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        case WM_CREATE: {
            HINSTANCE hInst = ((LPCREATESTRUCT)lParam)->hInstance; // application instance for child control creation

            CreateWindowEx( // label for the A row
                0, TEXT("STATIC"), TEXT("A button:"),
                WS_CHILD | WS_VISIBLE | SS_LEFT,
                10, 22, 90, 20, hwnd, NULL, hInst, NULL
            );
            CreateWindowEx( // bind button for A — shows current binding; click to start capturing
                0, TEXT("BUTTON"), g_bindA.label,
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                110, 17, 280, 30, hwnd, (HMENU)ID_BIND_BTN_A, hInst, NULL
            );

            CreateWindowEx( // label for the B row
                0, TEXT("STATIC"), TEXT("B button:"),
                WS_CHILD | WS_VISIBLE | SS_LEFT,
                10, 67, 90, 20, hwnd, NULL, hInst, NULL
            );
            CreateWindowEx( // bind button for B
                0, TEXT("BUTTON"), g_bindB.label,
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                110, 62, 280, 30, hwnd, (HMENU)ID_BIND_BTN_B, hInst, NULL
            );
            return 0;
        }
        case WM_COMMAND: {
            UINT id = LOWORD(wParam);
            if ((id == ID_BIND_BTN_A || id == ID_BIND_BTN_B) && s_listenTarget == LISTEN_NONE) {
                s_listenTarget = (id == ID_BIND_BTN_A) ? LISTEN_A : LISTEN_B;

                SetWindowText(GetDlgItem(hwnd, id), TEXT("Press any key or mouse button...  (Esc cancels)")); // show listening state
                EnableWindow(GetDlgItem(hwnd, ID_BIND_BTN_A), FALSE); // disable both buttons to prevent double-bind
                EnableWindow(GetDlgItem(hwnd, ID_BIND_BTN_B), FALSE);

                // Install system-wide hooks — these fire even when other windows have focus
                s_hKeyHook   = SetWindowsHookEx(WH_KEYBOARD_LL, LLKeyProc,   GetModuleHandle(NULL), 0);
                s_hMouseHook = SetWindowsHookEx(WH_MOUSE_LL,    LLMouseProc, GetModuleHandle(NULL), 0);
            }
            return 0;
        }
        case WM_DESTROY:
            if (s_listenTarget != LISTEN_NONE) CancelBinding(); // clean up if closed while in listening mode
            EnableWindow(s_hwndParent, TRUE);    // re-enable the main window now that settings is gone
            SetForegroundWindow(s_hwndParent);   // bring the main window back to the front
            s_hwndSettings = NULL;               // mark settings as closed so it can be reopened
            return 0;
    }
    return DefWindowProc(hwnd, msg, wParam, lParam);
}

// --- Public interface ---

void RegisterSettingsClass(HINSTANCE hInstance) {
    WNDCLASS wcs      = {};
    wcs.lpfnWndProc   = SettingsProc;                  // function that handles settings window events
    wcs.hInstance     = hInstance;
    wcs.lpszClassName = SETTINGS_CLASS;
    wcs.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);   // dialog-style gray background to match system dialogs
    wcs.hCursor       = LoadCursor(NULL, IDC_ARROW);
    RegisterClass(&wcs);
}

void OpenSettings(HWND hwndParent) {
    if (s_hwndSettings != NULL) return; // already open — do nothing

    s_hwndParent = hwndParent;          // store so FinishBinding can update main window button labels
    EnableWindow(hwndParent, FALSE);    // disable main window to prevent interaction while settings is open

    s_hwndSettings = CreateWindowEx(
        WS_EX_DLGMODALFRAME,                     // dialog-style border to visually distinguish it as a popup
        SETTINGS_CLASS, TEXT("Settings"),
        WS_POPUP | WS_CAPTION | WS_SYSMENU,      // popup with title bar and close button, no resize/maximize
        CW_USEDEFAULT, CW_USEDEFAULT, 420, 130,  // fixed size — contents don't need to be resizable
        hwndParent, NULL, GetModuleHandle(NULL), NULL
    );
    ShowWindow(s_hwndSettings, SW_SHOW); // make the settings window visible
}

void HandleBoundInput(HWND hwndMain, UINT vk, bool pressed) {
    WPARAM state = pressed ? TRUE : FALSE; // BM_SETSTATE TRUE = visually depressed, FALSE = released
    if (vk == g_bindA.vk) SendMessage(GetDlgItem(hwndMain, ID_BUTTON_A), BM_SETSTATE, state, 0);
    if (vk == g_bindB.vk) SendMessage(GetDlgItem(hwndMain, ID_BUTTON_B), BM_SETSTATE, state, 0);
}

bool Settings_IsListening() {
    return s_listenTarget != LISTEN_NONE; // true while waiting for the user to press a new binding key
}

bool Settings_IsBoundKey(UINT vk) {
    return vk == g_bindA.vk || vk == g_bindB.vk; // true if this VK is currently assigned to either button
}

// Builds the full path to the INI file and ensures the containing directory exists.
// Returns the path in 'out', which must be at least MAX_PATH characters.
static void GetIniPath(TCHAR* out) {
    TCHAR appData[MAX_PATH];
    SHGetFolderPath(NULL, CSIDL_APPDATA, NULL, 0, appData); // e.g. C:\Users\<name>\AppData\Roaming

    TCHAR dir[MAX_PATH];
    wsprintf(dir, TEXT("%s\\PhoenixLandDept"), appData);
    CreateDirectory(dir, NULL); // no-op and non-fatal if the directory already exists

    wsprintf(out, TEXT("%s\\settings.ini"), dir);
}

void LoadBindings() {
    TCHAR iniPath[MAX_PATH];
    GetIniPath(iniPath);

    // GetPrivateProfileInt returns the default value when the key or file is missing,
    // so the compiled-in defaults (A=65, B=66) are used automatically on first launch.
    UINT vkA = (UINT)GetPrivateProfileInt(TEXT("KeyBindings"), TEXT("BindA"), (int)g_bindA.vk, iniPath);
    UINT vkB = (UINT)GetPrivateProfileInt(TEXT("KeyBindings"), TEXT("BindB"), (int)g_bindB.vk, iniPath);

    g_bindA.vk = vkA;
    GetVKLabel(vkA, g_bindA.label, 32); // rebuild label from the loaded VK so it matches what the user set

    g_bindB.vk = vkB;
    GetVKLabel(vkB, g_bindB.label, 32);
}

void SaveBindings() {
    TCHAR iniPath[MAX_PATH];
    GetIniPath(iniPath);

    // WritePrivateProfileString requires a string, so convert each VK code to decimal text first
    TCHAR buf[16];
    wsprintf(buf, TEXT("%u"), g_bindA.vk);
    WritePrivateProfileString(TEXT("KeyBindings"), TEXT("BindA"), buf, iniPath);

    wsprintf(buf, TEXT("%u"), g_bindB.vk);
    WritePrivateProfileString(TEXT("KeyBindings"), TEXT("BindB"), buf, iniPath);
}
