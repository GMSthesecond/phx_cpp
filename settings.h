#pragma once
#include <windows.h>

// Control ids in the settings window: row i's value (path label or text box) is
// ID_SETTING_VALUE_BASE + i and its Change / Save button is ID_SETTING_BUTTON_BASE + i.
#define ID_SETTING_VALUE_BASE  1000
#define ID_SETTING_BUTTON_BASE 2000

// Registers the settings window class — call once in WinMain before any window is created
void RegisterSettingsClass(HINSTANCE hInstance);

// Opens the settings window; hwndParent is disabled until settings is closed.
// Safe to call while settings is already open — does nothing in that case.
void OpenSettings(HWND hwndParent);

// Reads every setting from %APPDATA%\PhoenixLandDept\settings.ini.
// Call once in WinMain before any window is created. Settings missing from the file
// keep their compiled-in defaults.
void LoadSettings();

// Current value of settings.ini [section] key (as loaded or last changed in the dialog),
// or an empty string if the key isn't one of the settings window's rows.
// Used by Organization ([Folders] Organize) and Rename ([Folders] Rename).
const TCHAR* GetSetting(const TCHAR* section, const TCHAR* key);

// Changes a setting in memory (not saved; the dialog calls SaveSettings after a change).
// Returns false if [section] key isn't one of the rows.
bool SetSetting(const TCHAR* section, const TCHAR* key, const TCHAR* value);
