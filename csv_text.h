// csv_text.h — small text and CSV helpers shared by organize.cpp (Organization button) and rename.cpp
// (Rename button). Header-only (inline), so each file just includes it. Touches no files or INI.
// Tested through tests/cpp/test_organize.cpp (organize_csv_split_and_escape) and test_rename.cpp.
#pragma once
#include <string>
#include <vector>

// Returns s without leading/trailing spaces, tabs, CR, LF.
inline std::wstring Trim(const std::wstring& s) {
    size_t a = s.find_first_not_of(L" \t\r\n");
    if (a == std::wstring::npos) return {};
    size_t b = s.find_last_not_of(L" \t\r\n");
    return s.substr(a, b - a + 1);
}

// Splits one CSV line into fields; handles quoted fields with commas and "" escapes, drops CR.
inline std::vector<std::wstring> SplitCSV(const std::wstring& line) {
    std::vector<std::wstring> out;
    std::wstring field;
    bool inQ = false;
    for (size_t i = 0; i < line.size(); ++i) {
        wchar_t c = line[i];
        if (c == L'"') {
            if (inQ && i + 1 < line.size() && line[i + 1] == L'"') {
                field += L'"'; ++i; // escaped quote inside quoted field
            } else {
                inQ = !inQ;
            }
        } else if (c == L',' && !inQ) {
            out.push_back(field); field.clear();
        } else if (c != L'\r') {
            field += c;
        }
    }
    out.push_back(field);
    return out;
}

// Wraps a field in quotes (doubling inner quotes) if it contains a comma, quote, or newline.
inline std::wstring EscCSV(const std::wstring& s) {
    if (s.find_first_of(L",\"\n\r") == std::wstring::npos) return s;
    std::wstring o = L"\"";
    for (wchar_t c : s) { if (c == L'"') o += L"\"\""; else o += c; }
    return o + L'"';
}
