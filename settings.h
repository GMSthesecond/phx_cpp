#pragma once
#include <windows.h>

// IDs shared between main.cpp and settings.cpp — settings.cpp uses these to update main window button labels
#define ID_BUTTON_A   4
#define ID_BUTTON_B   5

// IDs used only inside the settings window
#define ID_BIND_BTN_A 7
#define ID_BIND_BTN_B 8

// Holds everything needed to describe one key or mouse button binding
struct KeyBinding {
    UINT  vk;        // virtual key code — letters use their ASCII value; mouse uses VK_LBUTTON etc.
    TCHAR label[32]; // human-readable label shown on the button and in settings
};

extern KeyBinding g_bindA; // exposed so main.cpp can read the initial label when creating button A
extern KeyBinding g_bindB; // exposed so main.cpp can read the initial label when creating button B

// Registers the settings window class — call once in WinMain before any window is created
void RegisterSettingsClass(HINSTANCE hInstance);

// Opens the settings window; hwndParent is disabled until settings is closed.
// Safe to call while settings is already open — does nothing in that case.
void OpenSettings(HWND hwndParent);

// Checks an incoming VK against both bindings and presses or releases the matching main window button.
// Call from WndProc for WM_KEYDOWN, WM_KEYUP, and all mouse button messages.
void HandleBoundInput(HWND hwndMain, UINT vk, bool pressed);

// Returns true while the user is in the middle of pressing a new key to rebind.
// Use in the message loop to avoid intercepting keys during an active capture.
bool Settings_IsListening();

// Returns true if vk matches either the A or B binding's current virtual key code.
// Use in the message loop to decide whether to route a key directly to WndProc.
bool Settings_IsBoundKey(UINT vk);

// Reads saved bindings from %APPDATA%\PhoenixLandDept\settings.ini and applies them to g_bindA/g_bindB.
// Call once in WinMain before any window is created so initial button labels are correct.
// Falls back to the compiled-in defaults (A/B) if the file does not exist yet.
void LoadBindings();

// Writes the current g_bindA and g_bindB VK codes to %APPDATA%\PhoenixLandDept\settings.ini.
// Call after every successful rebind so changes survive a restart.
void SaveBindings();
