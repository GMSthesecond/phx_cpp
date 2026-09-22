#pragma once
#include <windows.h>

// Registers the rename-dialog window class — call once in WinMain.
void RegisterRenameClass(HINSTANCE hInstance);

// Opens the Rename dialog: generate a CSV of filenames (+ MP3 artist tag)
// in the Rename folder, edit it, then apply renames/tag changes.
void OpenRename(HWND hwndParent);
