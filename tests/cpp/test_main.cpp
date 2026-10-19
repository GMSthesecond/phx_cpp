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
