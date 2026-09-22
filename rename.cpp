#include "rename.h"
#include <shellapi.h>
#include <string>
#include <vector>

// ─── Paths ─────────────────────────────────────────────────────────────────────

static const wchar_t* FOLDER_PATH = L"C:\\Users\\Ethan Mesecher\\Desktop\\Rename";
static const wchar_t* CSV_NAME    = L"rename.csv";

static std::wstring CsvPath() {
    return std::wstring(FOLDER_PATH) + L"\\" + CSV_NAME;
}

// ─── String / CSV helpers (same conventions as organize.cpp) ─────────────────

static std::wstring Trim(const std::wstring& s) {
    size_t a = s.find_first_not_of(L" \t\r\n");
    if (a == std::wstring::npos) return {};
    size_t b = s.find_last_not_of(L" \t\r\n");
    return s.substr(a, b - a + 1);
}

static std::vector<std::wstring> SplitCSV(const std::wstring& line) {
    std::vector<std::wstring> out;
    std::wstring field;
    bool inQ = false;
    for (size_t i = 0; i < line.size(); ++i) {
        wchar_t c = line[i];
        if (c == L'"') {
            if (inQ && i + 1 < line.size() && line[i + 1] == L'"') { field += L'"'; ++i; }
            else inQ = !inQ;
        } else if (c == L',' && !inQ) {
            out.push_back(field); field.clear();
        } else if (c != L'\r') {
            field += c;
        }
    }
    out.push_back(field);
    return out;
}

static std::wstring EscCSV(const std::wstring& s) {
    if (s.find_first_of(L",\"\n\r") == std::wstring::npos) return s;
    std::wstring o = L"\"";
    for (wchar_t c : s) { if (c == L'"') o += L"\"\""; else o += c; }
    return o + L'"';
}

static bool HasExtension(const std::wstring& name, const wchar_t* ext) {
    size_t extLen = wcslen(ext);
    if (name.size() < extLen) return false;
    std::wstring tail = name.substr(name.size() - extLen);
    for (auto& c : tail) c = (wchar_t)towlower(c);
    std::wstring want = ext;
    for (auto& c : want) c = (wchar_t)towlower(c);
    return tail == want;
}

static bool SameNameCI(const std::wstring& a, const std::wstring& b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); i++)
        if (towlower(a[i]) != towlower(b[i])) return false;
    return true;
}

// ─── Whole-file read/write ─────────────────────────────────────────────────────

static bool ReadWholeFile(const std::wstring& path, std::vector<BYTE>& out) {
    HANDLE hf = CreateFile(path.c_str(), GENERIC_READ, FILE_SHARE_READ,
        NULL, OPEN_EXISTING, 0, NULL);
    if (hf == INVALID_HANDLE_VALUE) return false;
    LARGE_INTEGER sz;
    if (!GetFileSizeEx(hf, &sz)) { CloseHandle(hf); return false; }
    out.resize((size_t)sz.QuadPart);
    DWORD nr = 0;
    BOOL ok = out.empty() ? TRUE : ReadFile(hf, out.data(), (DWORD)out.size(), &nr, NULL);
    CloseHandle(hf);
    return ok && (size_t)nr == out.size();
}

static bool WriteWholeFile(const std::wstring& path, const std::vector<BYTE>& data) {
    HANDLE hf = CreateFile(path.c_str(), GENERIC_WRITE, 0,
        NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hf == INVALID_HANDLE_VALUE) return false;
    DWORD nw = 0;
    BOOL ok = data.empty() ? TRUE : WriteFile(hf, data.data(), (DWORD)data.size(), &nw, NULL);
    CloseHandle(hf);
    return ok && (size_t)nw == data.size();
}

// ─── ID3 tag reading/writing ───────────────────────────────────────────────────
//
// Supports reading the artist from ID3v2.3/2.4 (TPE1) or ID3v1 (last 128 bytes),
// and writing it back the same way. ID3v2 tags using unsynchronisation, an
// extended header, a footer, or the older 3-byte-id v2.2 layout are left
// untouched on write (too easy to corrupt) — only the ID3v1 fallback is
// updated/added for those files.

static DWORD Synchsafe32(const BYTE* p) {
    return ((DWORD)(p[0] & 0x7F) << 21) | ((DWORD)(p[1] & 0x7F) << 14) |
           ((DWORD)(p[2] & 0x7F) << 7)  |  (DWORD)(p[3] & 0x7F);
}
static void EncodeSynchsafe32(DWORD v, BYTE* out) {
    out[0] = (BYTE)((v >> 21) & 0x7F);
    out[1] = (BYTE)((v >> 14) & 0x7F);
    out[2] = (BYTE)((v >> 7)  & 0x7F);
    out[3] = (BYTE)(v & 0x7F);
}
static DWORD BigEndian32(const BYTE* p) {
    return ((DWORD)p[0] << 24) | ((DWORD)p[1] << 16) | ((DWORD)p[2] << 8) | (DWORD)p[3];
}
static void EncodeBigEndian32(DWORD v, BYTE* out) {
    out[0] = (BYTE)(v >> 24); out[1] = (BYTE)(v >> 16);
    out[2] = (BYTE)(v >> 8);  out[3] = (BYTE)v;
}

struct Id3Frame {
    std::string id;
    WORD flags;
    std::vector<BYTE> data;
};

struct Id3v2Tag {
    bool present    = false;
    bool unsupported = false; // true => don't touch on write (still fine for read)
    BYTE version    = 0;      // major version (3 or 4 expected)
    BYTE flags      = 0;
    size_t tagEnd   = 0;      // offset of first byte after the tag
    std::vector<Id3Frame> frames;
};

static Id3v2Tag ParseID3v2(const std::vector<BYTE>& data) {
    Id3v2Tag t;
    if (data.size() < 10 || data[0] != 'I' || data[1] != 'D' || data[2] != '3') return t;
    t.present = true;
    t.version = data[3];
    t.flags   = data[5];
    DWORD size = Synchsafe32(&data[6]);
    t.tagEnd = 10 + (size_t)size;
    if (t.tagEnd > data.size() || t.version < 3 || t.version > 4 || (t.flags & 0xB0) != 0) {
        t.unsupported = true;
        if (t.tagEnd > data.size()) t.tagEnd = data.size(); // clamp so callers stay safe
        return t;
    }
    size_t pos = 10;
    while (pos + 10 <= t.tagEnd) {
        if (data[pos] == 0) break; // padding begins
        Id3Frame f;
        f.id.assign((const char*)&data[pos], 4);
        DWORD fsize = (t.version == 4) ? Synchsafe32(&data[pos + 4]) : BigEndian32(&data[pos + 4]);
        f.flags = ((WORD)data[pos + 8] << 8) | data[pos + 9];
        size_t dataStart = pos + 10;
        if (fsize == 0 || dataStart + fsize > t.tagEnd) break;
        f.data.assign(data.begin() + dataStart, data.begin() + dataStart + fsize);
        t.frames.push_back(f);
        pos = dataStart + fsize;
    }
    return t;
}

static std::vector<BYTE> BuildID3v2(BYTE version, const std::vector<Id3Frame>& frames) {
    std::vector<BYTE> body;
    for (auto& f : frames) {
        body.insert(body.end(), f.id.begin(), f.id.end());
        BYTE sz[4];
        if (version == 4) EncodeSynchsafe32((DWORD)f.data.size(), sz);
        else              EncodeBigEndian32((DWORD)f.data.size(), sz);
        body.insert(body.end(), sz, sz + 4);
        body.push_back((BYTE)(f.flags >> 8));
        body.push_back((BYTE)(f.flags & 0xFF));
        body.insert(body.end(), f.data.begin(), f.data.end());
    }
    std::vector<BYTE> out = { 'I', 'D', '3', version, 0, 0 };
    BYTE sz[4];
    EncodeSynchsafe32((DWORD)body.size(), sz);
    out.insert(out.end(), sz, sz + 4);
    out.insert(out.end(), body.begin(), body.end());
    return out;
}

// Decodes a text-frame payload (encoding byte + text) into a wstring.
static std::wstring DecodeID3Text(const std::vector<BYTE>& d) {
    if (d.empty()) return L"";
    BYTE enc = d[0];
    const BYTE* p = d.data() + 1;
    size_t len = d.size() - 1;
    std::wstring out;
    if (enc == 0 || enc == 3) { // Latin-1 or UTF-8
        std::string s((const char*)p, len);
        while (!s.empty() && s.back() == '\0') s.pop_back();
        int wlen = MultiByteToWideChar(enc == 3 ? CP_UTF8 : 1252, 0, s.c_str(), -1, NULL, 0);
        if (wlen > 0) {
            std::vector<wchar_t> wb(wlen);
            MultiByteToWideChar(enc == 3 ? CP_UTF8 : 1252, 0, s.c_str(), -1, wb.data(), wlen);
            out = wb.data();
        }
    } else { // UTF-16 (with or without BOM)
        size_t start = 0;
        bool bigEndian = false;
        if (len >= 2 && p[0] == 0xFF && p[1] == 0xFE) start = 2;
        else if (len >= 2 && p[0] == 0xFE && p[1] == 0xFF) { start = 2; bigEndian = true; }
        for (size_t i = start; i + 1 < len; i += 2) {
            wchar_t ch = bigEndian ? ((wchar_t)p[i] << 8 | p[i + 1])
                                   : ((wchar_t)p[i + 1] << 8 | p[i]);
            if (ch == 0) break;
            out += ch;
        }
    }
    return Trim(out);
}

static std::vector<BYTE> EncodeID3TextUTF16(const std::wstring& s) {
    std::vector<BYTE> out;
    out.push_back(0x01); // encoding: UTF-16 with BOM
    out.push_back(0xFF); out.push_back(0xFE);
    for (wchar_t c : s) { out.push_back((BYTE)(c & 0xFF)); out.push_back((BYTE)(c >> 8)); }
    return out;
}

static const size_t ID3V1_SIZE = 128;

// Reads the Artist field from a trailing ID3v1 tag, or "" if none present.
static std::wstring ReadID3v1Artist(const std::vector<BYTE>& data) {
    if (data.size() < ID3V1_SIZE) return L"";
    const BYTE* t = data.data() + data.size() - ID3V1_SIZE;
    if (t[0] != 'T' || t[1] != 'A' || t[2] != 'G') return L"";
    std::string s((const char*)t + 33, 30);
    while (!s.empty() && (s.back() == '\0' || s.back() == ' ')) s.pop_back();
    int wlen = MultiByteToWideChar(1252, 0, s.c_str(), -1, NULL, 0);
    if (wlen <= 0) return L"";
    std::vector<wchar_t> wb(wlen);
    MultiByteToWideChar(1252, 0, s.c_str(), -1, wb.data(), wlen);
    return wb.data();
}

// Reads the MP3 artist tag: prefers ID3v2 TPE1, falls back to ID3v1.
static std::wstring ReadMp3Artist(const std::wstring& path) {
    std::vector<BYTE> data;
    if (!ReadWholeFile(path, data)) return L"";
    Id3v2Tag tag = ParseID3v2(data);
    if (tag.present && tag.version >= 3) {
        for (auto& f : tag.frames)
            if (f.id == "TPE1") return DecodeID3Text(f.data);
    }
    return ReadID3v1Artist(data);
}

// Writes a new artist into the MP3's tags. Returns false only on an I/O error;
// tag structures we don't understand are simply left as-is (not an error).
static bool WriteMp3Artist(const std::wstring& path, const std::wstring& newArtist) {
    std::vector<BYTE> data;
    if (!ReadWholeFile(path, data)) return false;

    Id3v2Tag tag = ParseID3v2(data);
    std::vector<BYTE> front;
    size_t audioStart = 0;

    if (tag.present && !tag.unsupported) {
        std::vector<Id3Frame> frames;
        for (auto& f : tag.frames) if (f.id != "TPE1") frames.push_back(f);
        Id3Frame nf; nf.id = "TPE1"; nf.flags = 0; nf.data = EncodeID3TextUTF16(newArtist);
        frames.push_back(nf);
        front = BuildID3v2(tag.version, frames);
        audioStart = tag.tagEnd;
    } else if (tag.present) {
        // Structure we don't safely rewrite (unsynchronised/extended/footer/v2.2) — keep verbatim.
        front.assign(data.begin(), data.begin() + tag.tagEnd);
        audioStart = tag.tagEnd;
    }

    std::vector<BYTE> rest(data.begin() + audioStart, data.end());

    // Patch or append the ID3v1 fallback tag so older players still see the new artist.
    std::string ansi;
    {
        int n = WideCharToMultiByte(1252, 0, newArtist.c_str(), -1, NULL, 0, NULL, NULL);
        std::vector<char> buf(n > 0 ? n : 1, 0);
        if (n > 0) WideCharToMultiByte(1252, 0, newArtist.c_str(), -1, buf.data(), n, NULL, NULL);
        ansi.assign(buf.data());
    }
    if (rest.size() >= ID3V1_SIZE &&
        rest[rest.size() - ID3V1_SIZE] == 'T' &&
        rest[rest.size() - ID3V1_SIZE + 1] == 'A' &&
        rest[rest.size() - ID3V1_SIZE + 2] == 'G') {
        BYTE* artistField = rest.data() + rest.size() - ID3V1_SIZE + 33;
        memset(artistField, 0, 30);
        memcpy(artistField, ansi.data(), min(ansi.size(), (size_t)30));
    } else {
        std::vector<BYTE> v1(ID3V1_SIZE, 0);
        v1[0] = 'T'; v1[1] = 'A'; v1[2] = 'G';
        memcpy(v1.data() + 33, ansi.data(), min(ansi.size(), (size_t)30));
        v1[127] = 255; // genre: unknown
        rest.insert(rest.end(), v1.begin(), v1.end());
    }

    std::vector<BYTE> out;
    out.reserve(front.size() + rest.size());
    out.insert(out.end(), front.begin(), front.end());
    out.insert(out.end(), rest.begin(), rest.end());
    return WriteWholeFile(path, out);
}

// ─── CSV generation ────────────────────────────────────────────────────────────

static void WriteUtf8(HANDLE hOut, const std::wstring& ws) {
    int n = WideCharToMultiByte(CP_UTF8, 0, ws.c_str(), -1, NULL, 0, NULL, NULL);
    if (n <= 1) return;
    std::vector<char> mb(n);
    WideCharToMultiByte(CP_UTF8, 0, ws.c_str(), -1, mb.data(), n, NULL, NULL);
    DWORD nw = 0;
    WriteFile(hOut, mb.data(), n - 1, &nw, NULL);
}

static void GenerateCSV(HWND hwndParent) {
    CreateDirectory(FOLDER_PATH, NULL);

    std::vector<std::wstring> names;
    std::wstring pattern = std::wstring(FOLDER_PATH) + L"\\*.*";
    WIN32_FIND_DATA fd;
    HANDLE hFind = FindFirstFile(pattern.c_str(), &fd);
    if (hFind != INVALID_HANDLE_VALUE) {
        do {
            if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
            if (SameNameCI(fd.cFileName, CSV_NAME)) continue;
            names.push_back(fd.cFileName);
        } while (FindNextFile(hFind, &fd));
        FindClose(hFind);
    }

    HANDLE hOut = CreateFile(CsvPath().c_str(), GENERIC_WRITE, 0,
        NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hOut == INVALID_HANDLE_VALUE) {
        MessageBox(hwndParent, L"Could not write rename.csv.", L"Rename — Error", MB_ICONERROR);
        return;
    }
    const char bom[] = { '\xEF', '\xBB', '\xBF' };
    DWORD nw = 0;
    WriteFile(hOut, bom, 3, &nw, NULL);
    WriteUtf8(hOut, L"Original Filename,New Filename,Artist,New Artist\r\n");

    for (auto& name : names) {
        std::wstring artist;
        if (HasExtension(name, L".mp3"))
            artist = ReadMp3Artist(std::wstring(FOLDER_PATH) + L"\\" + name);
        std::wstring row = EscCSV(name) + L"," + EscCSV(name) + L"," +
                            EscCSV(artist) + L"," + EscCSV(artist) + L"\r\n";
        WriteUtf8(hOut, row);
    }
    CloseHandle(hOut);

    MessageBox(hwndParent,
        L"rename.csv generated.\n\n"
        L"Edit the \"New Filename\" and \"New Artist\" columns (leave a cell "
        L"unchanged to leave that file/tag as-is), save the file, then click "
        L"\"Apply Renames + Tags\".",
        L"Rename", MB_ICONINFORMATION);

    ShellExecute(hwndParent, L"open", CsvPath().c_str(), NULL, NULL, SW_SHOWNORMAL);
}

// ─── Apply renames ──────────────────────────────────────────────────────────────

static void ApplyRenames(HWND hwndParent) {
    std::vector<BYTE> raw;
    if (!ReadWholeFile(CsvPath(), raw)) {
        MessageBox(hwndParent,
            L"Could not open rename.csv.\n\nGenerate it first with \"Generate File List\".",
            L"Rename — Error", MB_ICONERROR);
        return;
    }

    char* src = (char*)raw.data();
    size_t srcLen = raw.size();
    if (srcLen >= 3 && (BYTE)src[0] == 0xEF && (BYTE)src[1] == 0xBB && (BYTE)src[2] == 0xBF) {
        src += 3; srcLen -= 3;
    }
    int wlen = MultiByteToWideChar(CP_UTF8, 0, src, (int)srcLen, NULL, 0);
    std::vector<wchar_t> wb(wlen + 1, 0);
    MultiByteToWideChar(CP_UTF8, 0, src, (int)srcLen, wb.data(), wlen);
    std::wstring content(wb.data());

    std::vector<std::wstring> lines;
    size_t pos = 0;
    while (pos <= content.size()) {
        size_t nl = content.find(L'\n', pos);
        if (nl == std::wstring::npos) nl = content.size();
        lines.push_back(content.substr(pos, nl - pos));
        if (nl >= content.size()) break;
        pos = nl + 1;
    }

    int renamed = 0, tagged = 0, skipped = 0;
    std::wstring errors;

    for (size_t i = 1; i < lines.size(); ++i) {
        std::wstring ln = Trim(lines[i]);
        if (ln.empty()) continue;
        auto f = SplitCSV(ln);
        if (f.size() < 4) continue;

        std::wstring orig      = Trim(f[0]);
        std::wstring newName   = Trim(f[1]);
        std::wstring oldArtist = Trim(f[2]);
        std::wstring newArtist = Trim(f[3]);
        if (orig.empty()) continue;

        std::wstring oldPath = std::wstring(FOLDER_PATH) + L"\\" + orig;
        std::wstring curPath = oldPath;

        if (GetFileAttributes(oldPath.c_str()) == INVALID_FILE_ATTRIBUTES) {
            errors += L"Not found: " + orig + L"\r\n";
            skipped++;
            continue;
        }

        if (!newName.empty() && !SameNameCI(newName, orig)) {
            std::wstring newPath = std::wstring(FOLDER_PATH) + L"\\" + newName;
            if (GetFileAttributes(newPath.c_str()) != INVALID_FILE_ATTRIBUTES) {
                errors += L"Skipped (target exists): " + orig + L" -> " + newName + L"\r\n";
            } else if (MoveFile(oldPath.c_str(), newPath.c_str())) {
                curPath = newPath;
                renamed++;
            } else {
                errors += L"Rename failed: " + orig + L"\r\n";
            }
        }

        if (!newArtist.empty() && newArtist != oldArtist && HasExtension(curPath, L".mp3")) {
            if (WriteMp3Artist(curPath, newArtist)) tagged++;
            else errors += L"Tag update failed: " + orig + L"\r\n";
        }
    }

    std::wstring summary = L"Renamed " + std::to_wstring(renamed) +
        L" file(s), updated " + std::to_wstring(tagged) + L" artist tag(s).";
    if (!errors.empty()) summary += L"\r\n\r\nIssues:\r\n" + errors;
    MessageBox(hwndParent, summary.c_str(), L"Rename — Done",
        errors.empty() ? MB_ICONINFORMATION : MB_ICONWARNING);
}

// ─── Dialog UI ──────────────────────────────────────────────────────────────────

#define ID_RN_GENERATE 601
#define ID_RN_APPLY    602
#define ID_RN_CLOSE    603

static bool g_renameDone = false;
static const wchar_t RENAME_CLS[] = L"RenameDlg";

static LRESULT CALLBACK RenameProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        HINSTANCE hi = ((LPCREATESTRUCT)lp)->hInstance;
        CreateWindowEx(0, L"STATIC",
            L"Folder: C:\\Users\\Ethan Mesecher\\Desktop\\Rename\r\n\r\n"
            L"1. Generate a CSV listing the files in that folder.\r\n"
            L"2. Edit \"New Filename\" / \"New Artist\" in the CSV, then save it.\r\n"
            L"3. Click Apply to rename files and update MP3 artist tags.",
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            10, 10, 470, 90, hwnd, NULL, hi, NULL);

        CreateWindowEx(0, L"BUTTON", L"1. Generate File List (CSV)",
            WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            10, 110, 230, 30, hwnd, (HMENU)ID_RN_GENERATE, hi, NULL);
        CreateWindowEx(0, L"BUTTON", L"2. Apply Renames + Tags",
            WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            250, 110, 230, 30, hwnd, (HMENU)ID_RN_APPLY, hi, NULL);
        CreateWindowEx(0, L"BUTTON", L"Close",
            WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            190, 155, 110, 28, hwnd, (HMENU)ID_RN_CLOSE, hi, NULL);
        return 0;
    }
    case WM_COMMAND:
        if (LOWORD(wp) == ID_RN_GENERATE) {
            GenerateCSV(hwnd);
        } else if (LOWORD(wp) == ID_RN_APPLY) {
            ApplyRenames(hwnd);
        } else if (LOWORD(wp) == ID_RN_CLOSE) {
            g_renameDone = true;
            DestroyWindow(hwnd);
        }
        return 0;
    case WM_CLOSE:
        g_renameDone = true;
        DestroyWindow(hwnd);
        return 0;
    }
    return DefWindowProc(hwnd, msg, wp, lp);
}

void RegisterRenameClass(HINSTANCE hInstance) {
    WNDCLASS wc      = {};
    wc.lpfnWndProc   = RenameProc;
    wc.hInstance     = hInstance;
    wc.lpszClassName = RENAME_CLS;
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    RegisterClass(&wc);
}

void OpenRename(HWND hwndParent) {
    g_renameDone = false;
    EnableWindow(hwndParent, FALSE);
    HWND hwnd = CreateWindowEx(
        WS_EX_DLGMODALFRAME, RENAME_CLS, L"Rename Files",
        WS_POPUP | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT, CW_USEDEFAULT, 510, 230,
        hwndParent, NULL, GetModuleHandle(NULL), NULL);
    if (!hwnd) {
        EnableWindow(hwndParent, TRUE);
        return;
    }
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);
    MSG msg;
    while (!g_renameDone) {
        BOOL r = GetMessage(&msg, NULL, 0, 0);
        if (r == 0) { PostQuitMessage((int)msg.wParam); break; }
        if (r < 0) break;
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    EnableWindow(hwndParent, TRUE);
    SetForegroundWindow(hwndParent);
}
