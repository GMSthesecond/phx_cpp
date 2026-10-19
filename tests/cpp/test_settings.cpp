// test_settings.cpp — unit tests for settings.cpp (the Settings button's folders, files and sign-ins).
// Includes settings.cpp directly so its s_settings table and SaveSetting are visible.
// win_fakes.h redirects %APPDATA% into the sandbox, so the real settings.ini is never touched.
// settings_save_then_load_round_trips leaves a copy of the INI at <sandbox>\settings_for_python.ini;
// tests/test_cpp.py reads it back with the Python scripts' ark_common functions.
#include "minitest.h"
#include "win_fakes.h"
#include "../../settings.cpp"

// Full path of the (sandboxed) settings.ini.
static std::wstring IniPath() {
    TCHAR path[MAX_PATH];
    GetIniPath(path);
    return path;
}

// The value the round-trip test saves for row s: D:\Test\<key>, or for sign-ins a value with
// characters an INI reader could mangle (% is special to Python's configparser).
static std::wstring TestValue(const Setting& s) {
    if (s.kind == SETTING_FOLDER || s.kind == SETTING_FILE) return std::wstring(L"D:\\Test\\") + s.key;
    return std::wstring(s.key) + L" 100% = ok; #1";
}

TEST(settings_ini_is_in_phoenix_folder) {
    CHECK_EQ(IniPath(), g_sandbox + L"\\AppData\\PhoenixLandDept\\settings.ini");
}

TEST(settings_save_then_load_round_trips) {
    for (Setting& s : s_settings) {
        lstrcpyn(s.value, TestValue(s).c_str(), MAX_PATH);
        SaveSetting(s);
        lstrcpyn(s.value, L"junk", MAX_PATH);
    }

    LoadSettings();

    for (const Setting& s : s_settings) CHECK_EQ(std::wstring(s.value), TestValue(s));
    CHECK(CopyFile(IniPath().c_str(), (g_sandbox + L"\\settings_for_python.ini").c_str(), FALSE));
}

TEST(settings_missing_ini_keeps_defaults) {
    SetSetting(L"Folders", L"AOI", L"C:\\Default\\AOI");
    SetSetting(L"Folders", L"Organize", L"C:\\Default\\Organization");
    LoadSettings();
    CHECK_EQ(std::wstring(GetSetting(L"Folders", L"AOI")), std::wstring(L"C:\\Default\\AOI"));
    CHECK_EQ(std::wstring(GetSetting(L"Folders", L"Organize")), std::wstring(L"C:\\Default\\Organization"));
    CHECK(!FileExists(IniPath()));  // loading never writes
}

TEST(settings_saving_one_row_leaves_other_keys_alone) {
    WritePrivateProfileString(L"Folders", L"SomethingElse", L"E:\\Other", IniPath().c_str());
    WritePrivateProfileString(L"Credentials", L"username", L"someone", IniPath().c_str());
    SetSetting(L"Folders", L"Maps", L"D:\\Maps");
    SaveSetting(*FindSetting(L"Folders", L"Maps"));
    wchar_t buf[MAX_PATH] = {};
    GetPrivateProfileString(L"Folders", L"SomethingElse", L"", buf, MAX_PATH, IniPath().c_str());
    CHECK_EQ(std::wstring(buf), std::wstring(L"E:\\Other"));
    GetPrivateProfileString(L"Credentials", L"username", L"", buf, MAX_PATH, IniPath().c_str());
    CHECK_EQ(std::wstring(buf), std::wstring(L"someone"));
    GetPrivateProfileString(L"Folders", L"AOI", L"(unset)", buf, MAX_PATH, IniPath().c_str());
    CHECK_EQ(std::wstring(buf), std::wstring(L"(unset)"));  // a row nobody changed isn't written
}

TEST(settings_get_and_set_by_section_and_key) {
    CHECK(SetSetting(L"folders", L"rename", L"D:\\Music"));  // INI names are case-insensitive
    CHECK_EQ(std::wstring(GetSetting(L"Folders", L"Rename")), std::wstring(L"D:\\Music"));
    CHECK(!SetSetting(L"Folders", L"NoSuchKey", L"x"));
    CHECK_EQ(std::wstring(GetSetting(L"Folders", L"NoSuchKey")), std::wstring(L""));
}

TEST(settings_every_row_is_unique_and_secrets_are_hidden) {
    for (int i = 0; i < kNumSettings; i++) {
        for (int j = i + 1; j < kNumSettings; j++) {
            bool same = lstrcmpi(s_settings[i].section, s_settings[j].section) == 0 &&
                        lstrcmpi(s_settings[i].key, s_settings[j].key) == 0;
            CHECK(!same);
        }
        bool secret = lstrcmpi(s_settings[i].key, L"password") == 0 || lstrcmpi(s_settings[i].key, L"token") == 0;
        CHECK_EQ(secret, s_settings[i].kind == SETTING_SECRET);
    }
}
