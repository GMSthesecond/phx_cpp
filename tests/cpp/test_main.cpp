// test_main.cpp — entry point of cpp_tests.exe, the C++ unit tests (built by tests/test_cpp.py).
// Usage: cpp_tests.exe <sandbox folder>. Runs every TEST / KNOWN_BUG registered by the
// test_*.cpp files and prints one result line per test (format in minitest.h).
// Also defines the fakes and file helpers declared in win_fakes.h.
#include "minitest.h"
#include "win_fakes.h"
#include <cstdio>
#include <filesystem>

std::wstring g_sandbox;  // temp folder for this run (argv[1])
std::wstring g_testDir;  // <sandbox>\<name of the running test>, emptied before each test
std::vector<std::pair<std::wstring, std::wstring>> g_messageBoxes;  // recorded MessageBox calls
std::vector<std::wstring> g_shellOpened;  // recorded ShellExecute files

// Fake SHGetFolderPath: <sandbox>\AppData for any folder id.
HRESULT Fake_SHGetFolderPath(HWND, int, HANDLE, DWORD, LPWSTR out) {
    std::wstring dir = g_sandbox + L"\\AppData";
    CreateDirectory(dir.c_str(), NULL);
    lstrcpyn(out, dir.c_str(), MAX_PATH);
    return S_OK;
}

// Fake MessageBox: records (caption, text), returns IDOK.
int Fake_MessageBox(HWND, LPCWSTR text, LPCWSTR caption, UINT) {
    g_messageBoxes.push_back({ caption ? caption : L"", text ? text : L"" });
    return IDOK;
}

// Fake ShellExecute: records the file, returns a success code (> 32).
HINSTANCE Fake_ShellExecute(HWND, LPCWSTR, LPCWSTR file, LPCWSTR, LPCWSTR, INT) {
    g_shellOpened.push_back(file ? file : L"");
    return (HINSTANCE)33;
}

// Deletes path and everything under it, then recreates it empty.
void ResetDir(const std::wstring& path) {
    std::error_code ec;
    std::filesystem::remove_all(path, ec);
    std::filesystem::create_directories(path, ec);
}

// Writes bytes to path (overwrites).
void WriteBytes(const std::wstring& path, const std::string& bytes) {
    FILE* f = _wfopen(path.c_str(), L"wb");
    if (!f) MiniFail(__FILE__, __LINE__, "WriteBytes", "could not create " + Utf8(path));
    fwrite(bytes.data(), 1, bytes.size(), f);
    fclose(f);
}

// Reads a whole file as bytes ("" if missing).
std::string ReadBytes(const std::wstring& path) {
    FILE* f = _wfopen(path.c_str(), L"rb");
    if (!f) return "";
    std::string out;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0) out.append(buf, n);
    fclose(f);
    return out;
}

// True if path exists.
bool FileExists(const std::wstring& path) {
    return GetFileAttributes(path.c_str()) != INVALID_FILE_ATTRIBUTES;
}

// UTF-8 bytes of a wide string.
std::string Utf8(const std::wstring& s) {
    int n = WideCharToMultiByte(CP_UTF8, 0, s.c_str(), (int)s.size(), NULL, 0, NULL, NULL);
    std::string out(n, '\0');
    if (n > 0) WideCharToMultiByte(CP_UTF8, 0, s.c_str(), (int)s.size(), &out[0], n, NULL, NULL);
    return out;
}

// Wide string from UTF-8 bytes.
std::wstring FromUtf8(const std::string& s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), NULL, 0);
    std::wstring out(n, L'\0');
    if (n > 0) MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), &out[0], n);
    return out;
}

// True if any recorded MessageBox text contains needle.
bool SawMessageBox(const std::wstring& needle) {
    for (auto& box : g_messageBoxes)
        if (box.second.find(needle) != std::wstring::npos) return true;
    return false;
}

// Owner of the popup OwnerEnabledWhenPopupCloses is watching.
static HWND s_watchedOwner = NULL;
// Whether s_watchedOwner was enabled when the watched popup got WM_DESTROY.
static bool s_ownerEnabledAtDestroy = false;
// The watched popup's own window proc, which WatchPopupProc passes every message on to.
static WNDPROC s_popupProc = NULL;

// Window proc put in front of the watched popup's: notes whether its owner is enabled at WM_DESTROY
// (before the popup's own proc runs), then passes the message on.
static LRESULT CALLBACK WatchPopupProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_DESTROY) s_ownerEnabledAtDestroy = IsWindowEnabled(s_watchedOwner) != FALSE;
    return CallWindowProc(s_popupProc, hwnd, msg, wp, lp);
}

// See win_fakes.h.
bool OwnerEnabledWhenPopupCloses(const wchar_t* cls, void (*close)(HWND popup, HWND owner), void* createParam) {
    static const wchar_t kOwnerCls[] = L"TestPopupOwner";
    HINSTANCE hi = GetModuleHandle(NULL);
    WNDCLASS wc = {};
    wc.lpfnWndProc   = DefWindowProc;
    wc.hInstance     = hi;
    wc.lpszClassName = kOwnerCls;
    RegisterClass(&wc);  // fails harmlessly once registered
    HWND owner = CreateWindowEx(0, kOwnerCls, L"", WS_OVERLAPPEDWINDOW, 0, 0, 100, 100, NULL, NULL, hi, NULL);
    EnableWindow(owner, FALSE);
    HWND popup = owner ? CreateWindowEx(WS_EX_DLGMODALFRAME, cls, L"", WS_POPUP | WS_CAPTION | WS_SYSMENU,
                                        0, 0, 300, 200, owner, NULL, hi, createParam) : NULL;
    bool enabled = false, closed = false;
    if (popup) {
        s_watchedOwner = owner;
        s_ownerEnabledAtDestroy = false;
        s_popupProc = (WNDPROC)SetWindowLongPtr(popup, GWLP_WNDPROC, (LONG_PTR)WatchPopupProc);
        close(popup, owner);
        enabled = s_ownerEnabledAtDestroy;
        closed = !IsWindow(popup);
        if (!closed) DestroyWindow(popup);
    }
    if (owner) DestroyWindow(owner);
    UnregisterClass(cls, hi);
    if (!popup) MiniFail(__FILE__, __LINE__, "OwnerEnabledWhenPopupCloses", "couldn't open the popup (class registered?)");
    if (!closed) MiniFail(__FILE__, __LINE__, "OwnerEnabledWhenPopupCloses", "the popup is still open after close");
    return enabled;
}

// Runs every registered test with a fresh sandbox and the fake recorders cleared.
int wmain(int argc, wchar_t** argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: cpp_tests.exe <sandbox folder>\n");
        return 2;
    }
    g_sandbox = argv[1];
    int failures = 0;
    for (auto& t : MiniTests()) {
        g_testDir = g_sandbox + L"\\" + FromUtf8(t.name);
        ResetDir(g_testDir);
        ResetDir(g_sandbox + L"\\AppData");
        g_messageBoxes.clear();
        g_shellOpened.clear();

        std::string error;
        try {
            t.fn();
        } catch (MiniTestFailure& f) {
            error = f.message;
        } catch (std::exception& e) {
            error = std::string("exception: ") + e.what();
        } catch (...) {
            error = "unknown exception";
        }

        if (t.knownBug) {
            if (error.empty()) { printf("FIXED %s\n", t.name); failures++; }
            else printf("KNOWN %s :: %s (%s)\n", t.name, error.c_str(), t.issue);
        } else if (error.empty()) {
            printf("PASS %s\n", t.name);
        } else {
            printf("FAIL %s :: %s\n", t.name, error.c_str());
            failures++;
        }
        fflush(stdout);
    }
    return failures ? 1 : 0;
}
