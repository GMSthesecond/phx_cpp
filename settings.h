#pragma once
#include <windows.h>

// Control IDs for folder rows in the settings window
#define ID_FOLDER_DMD_LABEL   11
#define ID_FOLDER_STR_LABEL   12
#define ID_FOLDER_DMD_CHANGE  13
#define ID_FOLDER_STR_CHANGE  14
#define ID_FOLDER_CD_LABEL    15
#define ID_FOLDER_CD_CHANGE   16

// Registers the settings window class — call once in WinMain before any window is created
void RegisterSettingsClass(HINSTANCE hInstance);

// Opens the settings window; hwndParent is disabled until settings is closed.
// Safe to call while settings is already open — does nothing in that case.
void OpenSettings(HWND hwndParent);

// Reads saved folder paths from %APPDATA%\PhoenixLandDept\settings.ini.
// Call once in WinMain before any window is created.
// Falls back to compiled-in defaults if the file does not exist yet.
void LoadFolders();
