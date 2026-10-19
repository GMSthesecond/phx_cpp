// test_rename.cpp — unit tests for rename.cpp (the Rename button).
// Includes rename.cpp directly so its static helpers are visible. The [Folders] Rename setting is
// pointed at the test folder, so the real Desktop\Rename is never touched; ShellExecute and message
// boxes are recorded by win_fakes.h. MP3 files are built byte by byte with ID3 tags.
#include "minitest.h"
#include "win_fakes.h"
#include "../../rename.cpp"

static std::wstring s_folder;  // test copy of the Rename folder

// Points the [Folders] Rename setting at the running test's folder.
static void UseTestFolder() {
    s_folder = g_testDir;
    SetSetting(L"Folders", L"Rename", s_folder.c_str());
}

// Fake MPEG audio that must survive every tag rewrite unchanged.
static const std::string kAudio = std::string("\xFF\xFB\x90\x00", 4) + std::string(200, 'A');

// One ID3v2.3 / 2.4 frame: 4-char id, size, two flag bytes, payload.
static std::string Frame(const char* id, const std::string& payload, int version = 3) {
    BYTE sz[4];
    if (version == 4) EncodeSynchsafe32((DWORD)payload.size(), sz);
    else EncodeBigEndian32((DWORD)payload.size(), sz);
    return std::string(id, 4) + std::string((char*)sz, 4) + std::string(2, '\0') + payload;
}

// Text-frame payload with encoding byte enc (0 = Latin-1, 3 = UTF-8).
static std::string Text(const std::string& s, char enc = 0) { return std::string(1, enc) + s; }

// 128-byte ID3v1 tag with the given artist.
static std::string Id3v1(const std::string& artist) {
    std::string t(128, '\0');
    t.replace(0, 3, "TAG");
    t.replace(33, artist.size(), artist);
    t[127] = (char)255;
    return t;
}

// A whole MP3: ID3v2 tag (header + body + padding), the fake audio, then optional trailer.
static std::string Mp3(const std::string& tagBody, int version = 3, BYTE flags = 0,
                       const std::string& trailer = "") {
    std::string body = tagBody + std::string(16, '\0');
    BYTE sz[4];
    EncodeSynchsafe32((DWORD)body.size(), sz);
    std::string header = std::string("ID3") + (char)version + '\0' + (char)flags + std::string((char*)sz, 4);
    return header + body + kAudio + trailer;
}

// The raw payload of frame id in file bytes, or "(missing)".
static std::string FramePayload(const std::string& file, const char* id) {
    std::vector<BYTE> data(file.begin(), file.end());
    Id3v2Tag tag = ParseID3v2(data);
    for (auto& f : tag.frames)
        if (f.id == id) return std::string(f.data.begin(), f.data.end());
    return "(missing)";
}

// Path of name inside the test folder.
static std::wstring In(const wchar_t* name) { return s_folder + L"\\" + name; }

TEST(rename_reads_artist_from_v23_v24_and_v1) {
    UseTestFolder();
    WriteBytes(In(L"v23.mp3"), Mp3(Frame("TPE1", Text("Old Artist"))));
    WriteBytes(In(L"v24.mp3"), Mp3(Frame("TPE1", Text("Bj\xC3\xB6rk", 3), 4), 4));
    WriteBytes(In(L"v1.mp3"), kAudio + Id3v1("Tape Artist"));
    CHECK_EQ(ReadMp3Artist(In(L"v23.mp3")), std::wstring(L"Old Artist"));
    CHECK_EQ(ReadMp3Artist(In(L"v24.mp3")), std::wstring(L"Bj") + (wchar_t)0x00F6 + L"rk");  // o-umlaut; source stays ASCII
    CHECK_EQ(ReadMp3Artist(In(L"v1.mp3")), std::wstring(L"Tape Artist"));
}

TEST(rename_write_artist_keeps_other_frames_and_audio) {
    UseTestFolder();
    std::string art(300, '\x89');
    WriteBytes(In(L"song.mp3"), Mp3(Frame("TIT2", Text("Song Title")) + Frame("APIC", art) +
                                    Frame("TPE1", Text("Old")), 3, 0, Id3v1("Old")));

    CHECK(WriteMp3Artist(In(L"song.mp3"), L"New Artist"));

    std::string after = ReadBytes(In(L"song.mp3"));
    CHECK_EQ(ReadMp3Artist(In(L"song.mp3")), std::wstring(L"New Artist"));
    CHECK_EQ(FramePayload(after, "TIT2"), Text("Song Title"));
    CHECK(FramePayload(after, "APIC") == art);
    CHECK(after.find(kAudio) != std::string::npos);
    CHECK_EQ(after.size() >= 128 ? after.substr(after.size() - 128, 3) : std::string(), std::string("TAG"));
    CHECK_EQ(after.substr(after.size() - 128 + 33, 10), std::string("New Artist"));
}

TEST(rename_write_artist_adds_id3v1_when_missing) {
    UseTestFolder();
    WriteBytes(In(L"song.mp3"), Mp3(Frame("TPE1", Text("Old"))));
    CHECK(WriteMp3Artist(In(L"song.mp3"), L"New"));
    std::string after = ReadBytes(In(L"song.mp3"));
    CHECK_EQ(after.substr(after.size() - 128, 3), std::string("TAG"));
    CHECK_EQ(ReadID3v1Artist(std::vector<BYTE>(after.begin(), after.end())), std::wstring(L"New"));
}

TEST(rename_unsupported_v22_tag_is_kept_verbatim) {
    UseTestFolder();
    // ID3v2.2 uses 3-char ids and 3-byte sizes, which WriteMp3Artist must not rewrite.
    std::string v22Frame = std::string("TT2\0\0\x05\0Song", 11);
    std::string original = Mp3(v22Frame, 2);
    size_t tagLen = original.size() - kAudio.size();
    WriteBytes(In(L"old.mp3"), original);

    CHECK(WriteMp3Artist(In(L"old.mp3"), L"New"));

    std::string after = ReadBytes(In(L"old.mp3"));
    CHECK(after.compare(0, tagLen + kAudio.size(), original) == 0);  // tag and audio untouched
    CHECK_EQ(ReadID3v1Artist(std::vector<BYTE>(after.begin(), after.end())), std::wstring(L"New"));
}

TEST(rename_generate_csv_lists_files_and_artists) {
    UseTestFolder();
    WriteBytes(In(L"a.mp3"), Mp3(Frame("TPE1", Text("Old"))));
    WriteBytes(In(L"b, with comma.txt"), "hello");
    WriteBytes(In(L"rename.csv"), "stale");

    GenerateCSV(NULL);

    std::string csv = ReadBytes(In(L"rename.csv"));
    CHECK(csv.compare(0, 3, "\xEF\xBB\xBF") == 0);
    CHECK(csv.find("Original Filename,New Filename,Artist,New Artist\r\n") != std::string::npos);
    CHECK(csv.find("a.mp3,a.mp3,Old,Old\r\n") != std::string::npos);
    CHECK(csv.find("\"b, with comma.txt\",\"b, with comma.txt\",,\r\n") != std::string::npos);
    CHECK(csv.find("stale") == std::string::npos);
    CHECK(csv.find("rename.csv,") == std::string::npos);
    CHECK_EQ(g_shellOpened.size(), (size_t)1);
    CHECK_EQ(g_shellOpened[0], CsvPath());
    CHECK(SawMessageBox(L"rename.csv generated"));
}

TEST(rename_apply_renames_and_retags) {
    UseTestFolder();
    WriteBytes(In(L"a.mp3"), Mp3(Frame("TPE1", Text("Old"))));
    WriteBytes(In(L"b.txt"), "b");
    WriteBytes(In(L"x.txt"), "x");
    WriteBytes(In(L"rename.csv"), "\xEF\xBB\xBF"
        "Original Filename,New Filename,Artist,New Artist\r\n"
        "a.mp3,c.mp3,Old,New\r\n"        // rename + retag
        "b.txt,x.txt,,\r\n"              // target exists -> skipped
        "gone.txt,new.txt,,\r\n"         // source missing
        "x.txt,x.txt,,\r\n");            // unchanged

    ApplyRenames(NULL);

    CHECK(!FileExists(In(L"a.mp3")));
    CHECK_EQ(ReadMp3Artist(In(L"c.mp3")), std::wstring(L"New"));
    CHECK_EQ(ReadBytes(In(L"b.txt")), std::string("b"));
    CHECK_EQ(ReadBytes(In(L"x.txt")), std::string("x"));
    CHECK(SawMessageBox(L"Renamed 1 file(s), updated 1 artist tag(s)."));
    CHECK(SawMessageBox(L"Skipped (target exists): b.txt -> x.txt"));
    CHECK(SawMessageBox(L"Not found: gone.txt"));
}

TEST(rename_apply_without_csv_shows_error) {
    UseTestFolder();
    ApplyRenames(NULL);
    CHECK(SawMessageBox(L"Could not open rename.csv"));
}

TEST(rename_extended_header_tag_keeps_frames) {
    UseTestFolder();
    // v2.3 tag with the extended-header flag (0x40): 10-byte extended header, then the frames.
    std::string extHeader = std::string("\0\0\0\x06", 4) + std::string(6, '\0');
    std::string tagged = Mp3(extHeader + Frame("TIT2", Text("Song Title")) + Frame("TPE1", Text("Old")), 3, 0x40);
    WriteBytes(In(L"song.mp3"), tagged);

    CHECK(WriteMp3Artist(In(L"song.mp3"), L"New"));

    std::string after = ReadBytes(In(L"song.mp3"));
    CHECK_EQ(after.substr(0, tagged.size()), tagged);           // ID3v2 tag and audio kept byte for byte
    CHECK_EQ(after.size(), tagged.size() + ID3V1_SIZE);          // only an ID3v1 tag appended
    CHECK_EQ(ReadMp3Artist(In(L"song.mp3")), std::wstring(L"New"));  // read back from ID3v1
}

TEST(rename_failed_tag_write_leaves_mp3_untouched) {
    UseTestFolder();
    std::string original = Mp3(Frame("TIT2", Text("Song Title")) + Frame("TPE1", Text("Old")));
    WriteBytes(In(L"song.mp3"), original);
    // A folder where the temp file would go makes the write fail before the MP3 is touched.
    CreateDirectory((In(L"song.mp3") + TEMP_SUFFIX).c_str(), NULL);

    CHECK(!WriteMp3Artist(In(L"song.mp3"), L"New"));

    CHECK_EQ(ReadBytes(In(L"song.mp3")), original);
}

TEST(rename_tag_write_leaves_no_temp_file) {
    UseTestFolder();
    WriteBytes(In(L"song.mp3"), Mp3(Frame("TPE1", Text("Old"))));
    CHECK(WriteMp3Artist(In(L"song.mp3"), L"New"));
    CHECK_EQ(ReadMp3Artist(In(L"song.mp3")), std::wstring(L"New"));
    CHECK(!FileExists(In(L"song.mp3") + TEMP_SUFFIX));
}
