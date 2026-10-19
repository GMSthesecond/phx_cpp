// minitest.h — tiny test framework for the C++ unit tests in tests/cpp (no dependencies).
// Built and run by tests/test_cpp.py; see docs/TESTING.md.
//   TEST(name) { CHECK(cond); CHECK_EQ(actual, expected); }   registers a test
//   KNOWN_BUG(name, "where it is documented") { ... }         a test for a bug listed in
//     docs/KNOWN_ISSUES.md: expected to fail until the bug is fixed. pytest reports it as
//     xfail, and as a failure once it starts passing so the marker and the entry get removed.
// test_main.cpp runs every registered test and prints one line each:
//   PASS <name> | FAIL <name> :: <detail> | KNOWN <name> :: <detail> | FIXED <name>
#pragma once
#include <windows.h>
#include <sstream>
#include <string>
#include <vector>

// One registered test.
struct MiniTest {
    const char* name;
    void (*fn)();
    bool knownBug;      // true for KNOWN_BUG tests
    const char* issue;  // where a known bug is documented
};

// Every registered test, in registration order (one translation unit at a time).
inline std::vector<MiniTest>& MiniTests() {
    static std::vector<MiniTest> tests;
    return tests;
}

// Thrown by a failed CHECK; carries "file:line check — detail".
struct MiniTestFailure { std::string message; };

// Adds a test to MiniTests() at static-initialization time (used by the TEST macros).
struct MiniTestRegistrar {
    MiniTestRegistrar(const char* name, void (*fn)(), bool knownBug, const char* issue) {
        MiniTests().push_back({ name, fn, knownBug, issue });
    }
};

// Printable forms of values for CHECK_EQ messages; wide strings are converted to UTF-8.
inline std::string MiniShow(const std::wstring& s) {
    int n = WideCharToMultiByte(CP_UTF8, 0, s.c_str(), -1, NULL, 0, NULL, NULL);
    std::string out(n > 0 ? n - 1 : 0, '\0');
    if (n > 1) WideCharToMultiByte(CP_UTF8, 0, s.c_str(), -1, &out[0], n, NULL, NULL);
    return "L\"" + out + "\"";
}
inline std::string MiniShow(const wchar_t* s) { return MiniShow(std::wstring(s ? s : L"(null)")); }
inline std::string MiniShow(const std::string& s) { return "\"" + s + "\""; }
inline std::string MiniShow(const char* s) { return MiniShow(std::string(s ? s : "(null)")); }
inline std::string MiniShow(bool v) { return v ? "true" : "false"; }
template <class T> std::string MiniShow(const T& v) { std::ostringstream o; o << v; return o.str(); }

// Throws a MiniTestFailure describing a failed check.
[[noreturn]] inline void MiniFail(const char* file, int line, const char* check, const std::string& detail) {
    std::string f = file;
    size_t slash = f.find_last_of("\\/");
    if (slash != std::string::npos) f = f.substr(slash + 1);
    throw MiniTestFailure{ f + ":" + std::to_string(line) + " " + check + (detail.empty() ? "" : " -- " + detail) };
}

#define MINITEST_REGISTER(name, known, issue) \
    static void name(); \
    static MiniTestRegistrar name##_registrar(#name, name, known, issue); \
    static void name()

#define TEST(name) MINITEST_REGISTER(name, false, "")
#define KNOWN_BUG(name, issue) MINITEST_REGISTER(name, true, issue)

#define CHECK(cond) \
    do { if (!(cond)) MiniFail(__FILE__, __LINE__, "CHECK(" #cond ")", ""); } while (0)

#define CHECK_EQ(actual, expected) \
    do { \
        auto&& minitest_a = (actual); auto&& minitest_e = (expected); \
        if (!(minitest_a == minitest_e)) \
            MiniFail(__FILE__, __LINE__, "CHECK_EQ(" #actual ", " #expected ")", \
                     "got " + MiniShow(minitest_a) + ", expected " + MiniShow(minitest_e)); \
    } while (0)
