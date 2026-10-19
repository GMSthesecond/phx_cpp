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
