#pragma once
#include <windows.h>

// Registers the classify-dialog window class — call once in WinMain.
void RegisterOrganizeClass(HINSTANCE hInstance);

// Reads Data.CSV, prompts the user to categorize any unknown descriptions,
// and writes Organized.CSV to the same folder.
void OpenOrganize(HWND hwndParent);
