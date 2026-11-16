#pragma once
#include <windows.h>
#include <string>

// Registers the Merge link window's class — call once in WinMain.
void RegisterMergeClass(HINSTANCE hInstance);

// Opens the Merge link window: two boxes for links to the Ark accounts to merge. Returns true
// once both hold valid, different account links, setting args to merge.py's arguments
// ("<record id> <record id>"); false if the user cancels or closes it.
bool AskMergeAccounts(HWND hwndParent, std::wstring& args);
