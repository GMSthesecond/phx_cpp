// win_fakes.h — redirects the Windows calls that would make the C++ code under test touch
// real files or block on UI. Each test_*.cpp includes this BEFORE including the .cpp it
// tests (organize.cpp, rename.cpp, settings.cpp), so their calls bind to the fakes:
//   SHGetFolderPath(CSIDL_APPDATA) -> <sandbox>\AppData   (organize_rules.ini, settings.ini)
//   MessageBox                     -> recorded in g_messageBoxes, returns IDOK
//   ShellExecute                   -> recorded in g_shellOpened, opens nothing
// Defined in test_main.cpp. The sandbox folder is passed on the command line by tests/test_cpp.py.
#pragma once
#include <windows.h>
#include <shlobj.h>
#include <shellapi.h>
#include <string>
#include <utility>
#include <vector>

// Temp folder for this run (argv[1]); every test file lives under it.
extern std::wstring g_sandbox;
// Empty folder for the test that is running: <sandbox>\<test name>.
extern std::wstring g_testDir;
// (caption, text) of every MessageBox the code under test showed.
extern std::vector<std::pair<std::wstring, std::wstring>> g_messageBoxes;
// Every file the code under test asked ShellExecute to open.
extern std::vector<std::wstring> g_shellOpened;

// Fake SHGetFolderPath: writes <sandbox>\AppData into out for any folder id.
HRESULT Fake_SHGetFolderPath(HWND hwnd, int csidl, HANDLE token, DWORD flags, LPWSTR out);
// Fake MessageBox: records the box and returns IDOK.
int Fake_MessageBox(HWND hwnd, LPCWSTR text, LPCWSTR caption, UINT type);
// Fake ShellExecute: records the file and reports success.
HINSTANCE Fake_ShellExecute(HWND hwnd, LPCWSTR op, LPCWSTR file, LPCWSTR params, LPCWSTR dir, INT show);

#undef SHGetFolderPath
#define SHGetFolderPath Fake_SHGetFolderPath
#undef MessageBox
#define MessageBox Fake_MessageBox
#undef ShellExecute
#define ShellExecute Fake_ShellExecute

// ─── File helpers for tests ──────────────────────────────────────────────────

// Deletes path and everything under it, then recreates it empty.
void ResetDir(const std::wstring& path);
// Writes bytes to path (overwrites).
void WriteBytes(const std::wstring& path, const std::string& bytes);
// Reads a whole file as bytes ("" if missing).
std::string ReadBytes(const std::wstring& path);
// True if path exists.
bool FileExists(const std::wstring& path);
// UTF-8 bytes of a wide string.
std::string Utf8(const std::wstring& s);
// Wide string from UTF-8 bytes.
std::wstring FromUtf8(const std::string& s);
// True if any recorded MessageBox text contains needle.
bool SawMessageBox(const std::wstring& needle);

// ─── Popup window helper ─────────────────────────────────────────────────────

// Opens a hidden popup of window class cls (registered by the caller; createParam goes to its
// WM_CREATE), owned by a hidden owner window that is disabled, as the launcher is while a popup is
// open; calls close(popup, owner); returns whether the owner was enabled again by the time the
// popup got WM_DESTROY. It must be: Windows gives the focus back to the owner only if it's enabled
// as the popup goes, otherwise another app's window comes to the front. Fails the test if close
// leaves the popup open. Unregisters cls afterwards (Organize's tests rely on its dialog class
// not being registered).
bool OwnerEnabledWhenPopupCloses(const wchar_t* cls, void (*close)(HWND popup, HWND owner),
                                 void* createParam = nullptr);
