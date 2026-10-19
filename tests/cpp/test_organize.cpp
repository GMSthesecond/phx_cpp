// test_organize.cpp — unit tests for organize.cpp (the Organize button).
// Includes organize.cpp directly so its static helpers are visible. win_fakes.h redirects
// organize_rules.ini into the sandbox and records message boxes; the [Folders] Organize setting is
// pointed at the test folder, so the real Desktop\Organization files are never touched.
// The classify dialog's window class is never registered here, so an unmatched transaction
// gets "Skip" instead of opening a dialog.
#include "minitest.h"
#include "win_fakes.h"
#include "../../organize.cpp"

static std::wstring s_orgDir;      // test stand-in for Desktop\Organization
static std::wstring s_dataPath;    // test copy of Data.CSV
static std::wstring s_outputPath;  // test copy of Organized.CSV

// Points the [Folders] Organize setting (so OrgDir / DataPath / OutputPath) at the running test's folder.
static void UseTestPaths() {
    s_orgDir = g_testDir;
    s_dataPath = g_testDir + L"\\Data.CSV";
    s_outputPath = g_testDir + L"\\Organized.CSV";
    SetSetting(L"Folders", L"Organize", s_orgDir.c_str());
}

// Checking-account export layout (Chase "Activity" download for a bank account).
static const char CHECKING_HDR[] = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\r\n";
// Credit-card export layout: Transaction Date comes first and must not be used.
static const char CARD_HDR[] = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\r\n";

// Writes a file into the test's Organization folder.
static void WriteOrgFile(const wchar_t* name, const std::string& bytes) {
    WriteBytes(s_orgDir + L"\\" + name, bytes);
}

// Data.CSV split into lines (BOM stripped, CRLF lines, header included).
static std::vector<std::wstring> ReadDataLines() {
    std::string bytes = ReadBytes(s_dataPath);
    CHECK(bytes.size() >= 3 && bytes.compare(0, 3, "\xEF\xBB\xBF") == 0);
    std::wstring text = FromUtf8(bytes.substr(3));
    std::vector<std::wstring> lines;
    size_t pos = 0, nl;
    while ((nl = text.find(L"\r\n", pos)) != std::wstring::npos) {
        lines.push_back(text.substr(pos, nl - pos));
        pos = nl + 2;
    }
    CHECK_EQ(pos, text.size());  // every line ends in CRLF
    return lines;
}

// Full path of the (sandboxed) organize_rules.ini.
static std::wstring RulesIni() {
    wchar_t path[MAX_PATH];
    GetRulesPath(path);
    return path;
}

// Writes one [Rules] entry: snippet -> column index.
static void AddRule(const wchar_t* snippet, int col) {
    WritePrivateProfileString(L"Rules", snippet, std::to_wstring(col).c_str(), RulesIni().c_str());
}

// Organized.CSV split into rows of fields (BOM stripped, CRLF lines).
static std::vector<std::vector<std::wstring>> ReadOutput() {
    std::string bytes = ReadBytes(s_outputPath);
    CHECK(bytes.size() >= 3 && bytes.compare(0, 3, "\xEF\xBB\xBF") == 0);
    std::wstring text = FromUtf8(bytes.substr(3));
    std::vector<std::vector<std::wstring>> rows;
    size_t pos = 0, nl;
    while ((nl = text.find(L"\r\n", pos)) != std::wstring::npos) {
        rows.push_back(SplitCSV(text.substr(pos, nl - pos)));
        pos = nl + 2;
    }
    return rows;
}

// The output row for one M/D/YYYY date.
static std::vector<std::wstring> RowFor(const std::vector<std::vector<std::wstring>>& rows, const wchar_t* date) {
    for (auto& r : rows) if (!r.empty() && r[0] == date) return r;
    MiniFail(__FILE__, __LINE__, "RowFor", "no output row for " + MiniShow(date));
}

TEST(organize_parse_date_formats) {
    Date d{};
    CHECK(ParseDate(L"9/5/2026", d));
    CHECK_EQ(DateKey(d), std::wstring(L"2026-09-05"));
    CHECK(ParseDate(L" 2026-09-05 ", d));
    CHECK_EQ(DateDisplay(d), std::wstring(L"9/5/2026"));
    CHECK(!ParseDate(L"Sept 5", d));
    CHECK(!ParseDate(L"13/1/2026", d));
}

TEST(organize_date_math) {
    CHECK_EQ(DaysInMonth(2024, 2), 29);
    CHECK_EQ(DaysInMonth(2026, 2), 28);
    CHECK_EQ(DaysInMonth(1900, 2), 28);
    CHECK_EQ(DaysInMonth(2000, 2), 29);
    CHECK_EQ(DateKey(NextDay({ 2026, 12, 31 })), std::wstring(L"2027-01-01"));
    CHECK_EQ(DateKey(NextDay({ 2026, 2, 28 })), std::wstring(L"2026-03-01"));
    CHECK(DateLt({ 2026, 1, 31 }, { 2026, 2, 1 }));
    CHECK(DateLe({ 2026, 2, 1 }, { 2026, 2, 1 }));
}

TEST(organize_parse_and_format_amounts) {
    CHECK_EQ(ParseAmount(L"$1,234.56"), 1234.56);
    CHECK_EQ(ParseAmount(L"-12.5"), -12.5);
    CHECK_EQ(ParseAmount(L"(45.10)"), -45.1);
    CHECK_EQ(FmtAmount(0.0), std::wstring(L""));
    CHECK_EQ(FmtAmount(-12.5), std::wstring(L"-12.50"));
}

TEST(organize_csv_split_and_escape) {
    auto f = SplitCSV(L"a,\"b, c\",\"say \"\"hi\"\"\",\r");
    CHECK_EQ(f.size(), (size_t)4);
    CHECK_EQ(f[1], std::wstring(L"b, c"));
    CHECK_EQ(f[2], std::wstring(L"say \"hi\""));
    CHECK_EQ(f[3], std::wstring(L""));
    CHECK_EQ(EscCSV(L"plain"), std::wstring(L"plain"));
    CHECK_EQ(EscCSV(L"a,b"), std::wstring(L"\"a,b\""));
    CHECK_EQ(EscCSV(L"q\""), std::wstring(L"\"q\"\"\""));
}

TEST(organize_scrub_desc_cleans_notes) {
    LoadScrubWords();
    CHECK_EQ(ScrubDesc(L"KROGER #123 CASPER WY"), std::wstring(L"Kroger"));
    CHECK_EQ(ScrubDesc(L"CALL 307-234-2121 NOW"), std::wstring(L"Call Now"));
    CHECK_EQ(ScrubDesc(L"ST-R3I5X0S2M3W5 COFFEE"), std::wstring(L"Coffee"));
    CHECK_EQ(ScrubDesc(L"PAYROLL ACME CORP PPD ID: 12345"), std::wstring(L"Payroll Acme Corp"));
    CHECK_EQ(ScrubDesc(L"12345"), std::wstring(L"12345"));  // never blanks a note entirely
}

TEST(organize_scrub_words_seed_the_ini) {
    LoadScrubWords();
    wchar_t buf[16] = {};
    GetPrivateProfileString(L"ScrubWords", L"CASPER", L"", buf, ARRAYSIZE(buf), RulesIni().c_str());
    CHECK_EQ(std::wstring(buf), std::wstring(L"1"));
}

TEST(organize_default_rules_live_next_to_the_exe) {
    wchar_t exe[MAX_PATH] = {};
    GetModuleFileName(NULL, exe, MAX_PATH);
    std::wstring dir(exe);
    dir = dir.substr(0, dir.rfind(L'\\') + 1);
    CHECK_EQ(DefaultRulesPath(), dir + L"default_organize_rules.ini");
}

TEST(organize_seeds_missing_rules_from_default) {
    std::wstring seed = g_testDir + L"\\default_organize_rules.ini";
    WriteBytes(seed, "[Rules]\r\nKROGER=4\r\n[ScrubWords]\r\nWYOMING=1\r\n[Meta]\r\nColumnSchema=2\r\n");
    std::wstring rules = g_sandbox + L"\\AppData\\PhoenixLandDept\\organize_rules.ini";
    CreateDirectory((g_sandbox + L"\\AppData\\PhoenixLandDept").c_str(), NULL);
    CHECK(!FileExists(rules));
    SeedRulesIfMissing(rules.c_str(), seed);
    CHECK_EQ(RulesIni(), rules);
    LoadRules();
    LoadScrubWords();
    CHECK_EQ(g_rules[L"KROGER"], 4);
    CHECK(std::find(g_scrubWords.begin(), g_scrubWords.end(), L"WYOMING") != g_scrubWords.end());
}

TEST(organize_seed_never_overwrites_learned_rules) {
    AddRule(L"KROGER", 4);
    std::wstring seed = g_testDir + L"\\default_organize_rules.ini";
    WriteBytes(seed, "[Rules]\r\nKROGER=9\r\nNETFLIX=2\r\n");
    SeedRulesIfMissing(RulesIni().c_str(), seed);
    LoadRules();
    CHECK_EQ(g_rules[L"KROGER"], 4);
    CHECK(g_rules.count(L"NETFLIX") == 0);
}

TEST(organize_missing_default_rules_is_harmless) {
    std::wstring rules = g_sandbox + L"\\AppData\\PhoenixLandDept\\organize_rules.ini";
    CreateDirectory((g_sandbox + L"\\AppData\\PhoenixLandDept").c_str(), NULL);
    SeedRulesIfMissing(rules.c_str(), g_testDir + L"\\no_such_file.ini");
    CHECK(!FileExists(rules));
    LoadRules();
    CHECK(g_rules.empty());
}

TEST(organize_find_rule) {
    g_rules.clear();
    g_rules[L"KROGER"] = 4;
    g_rules[L"NETFLIX"] = 2;
    CHECK_EQ(FindRule(L"KROGER #12 CASPER"), 4);
    CHECK_EQ(FindRule(L"NETFLIX.COM"), 2);
    CHECK_EQ(FindRule(L"SOMETHING ELSE"), -1);
}

TEST(organize_migrates_old_rule_columns_once) {
    AddRule(L"OLDTAKEOUT", 5);   // old Takeout -> 7
    AddRule(L"OLDMUTUAL", 11);   // old Mutual Aid -> 13
    AddRule(L"OLDIGNORE", 13);   // old Ignore -> 15
    LoadRules();
    CHECK_EQ(g_rules[L"OLDTAKEOUT"], 7);
    CHECK_EQ(g_rules[L"OLDMUTUAL"], 13);
    CHECK_EQ(g_rules[L"OLDIGNORE"], 15);
    CHECK_EQ((int)GetPrivateProfileInt(L"Meta", L"ColumnSchema", 0, RulesIni().c_str()), 2);
    LoadRules();  // second load must not remap again
    CHECK_EQ(g_rules[L"OLDTAKEOUT"], 7);
}

TEST(organize_end_to_end) {
    UseTestPaths();
    WritePrivateProfileString(L"Meta", L"ColumnSchema", L"2", RulesIni().c_str());
    AddRule(L"KROGER", 4);     // Groceries
    AddRule(L"NETFLIX", 2);    // Bills
    AddRule(L"TRANSFER", 15);  // Ignore
    WriteBytes(s_dataPath, std::string("\xEF\xBB\xBF") +
        "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\r\n"
        "CREDIT,09/05/2026,PAYROLL ACME CORP PPD ID: 12345,2500.00,ACH_CREDIT,,\r\n"
        "DEBIT,09/05/2026,KROGER #123 CASPER WY,-45.10,DEBIT_CARD,,\r\n"
        "DEBIT,09/05/2026,\"KROGER #456\",-4.90,DEBIT_CARD,,\r\n"
        "DEBIT,09/20/2026,NETFLIX.COM,-15.99,DEBIT_CARD,,\r\n"
        "DEBIT,10/01/2026,ONLINE TRANSFER TO SAV 1234,-100.00,ACH_DEBIT,,\r\n"
        "DEBIT,10/02/2026,MYSTERY SHOP,-9.99,DEBIT_CARD,,\r\n"   // no rule -> skipped
        "DEBIT,not a date,KROGER,-1.00,DEBIT_CARD,,\r\n");

    RunOrganize(NULL);

    CHECK(SawMessageBox(L"Organize complete!"));
    auto rows = ReadOutput();
    CHECK_EQ(rows.size(), (size_t)(1 + 30 + 31));  // header + every day of September and October
    CHECK_EQ(rows[0].size(), (size_t)(1 + 2 * NUM_COLS));
    CHECK_EQ(rows[0][1], std::wstring(L"Income"));
    CHECK_EQ(rows[0][10], std::wstring(L"Groceries Notes"));
    CHECK_EQ(rows[1][0], std::wstring(L"9/1/2026"));
    CHECK_EQ(rows.back()[0], std::wstring(L"10/31/2026"));

    auto sep5 = RowFor(rows, L"9/5/2026");
    CHECK_EQ(sep5[1], std::wstring(L"2500.00"));
    CHECK_EQ(sep5[2], std::wstring(L"Payroll Acme Corp 2500.00"));
    CHECK_EQ(sep5[9], std::wstring(L"-50.00"));
    CHECK_EQ(sep5[10], std::wstring(L"Kroger -45.10; Kroger -4.90"));

    auto sep20 = RowFor(rows, L"9/20/2026");
    CHECK_EQ(sep20[5], std::wstring(L"-15.99"));
    CHECK_EQ(sep20[6], std::wstring(L"Netflix -15.99"));

    for (const wchar_t* day : { L"10/1/2026", L"10/2/2026" }) {  // ignored, skipped
        auto r = RowFor(rows, day);
        for (size_t i = 1; i < r.size(); i++) CHECK_EQ(r[i], std::wstring(L""));
    }
}

TEST(organize_missing_data_file_shows_error) {
    UseTestPaths();
    RunOrganize(NULL);
    CHECK(SawMessageBox(L"Could not open Data.CSV"));
    CHECK(!FileExists(s_outputPath));
}

TEST(organize_missing_columns_shows_error) {
    UseTestPaths();
    WriteBytes(s_dataPath, "Date,Desc,Amt\r\n1/1/2026,x,1\r\n");
    RunOrganize(NULL);
    CHECK(SawMessageBox(L"Could not find required columns"));
}

TEST(organize_without_chase_exports_keeps_existing_data_csv) {
    UseTestPaths();
    std::string data = "Post Date,Description,Amount\r\n9/5/2026,KROGER,-1.00\r\n";
    WriteBytes(s_dataPath, data);
    WriteOrgFile(L"Budget.csv", "Not,A,Chase,File\r\n");
    int files = -1, rows = -1;
    CHECK(BuildDataCsv(NULL, files, rows) == BuildResult::NoChaseFiles);
    CHECK_EQ(ReadBytes(s_dataPath), data);  // untouched
    CHECK(g_messageBoxes.empty());
}

TEST(organize_finds_only_chase_csv_files) {
    UseTestPaths();
    WriteOrgFile(L"Chase2028_Activity_20261006.csv", "x");
    WriteOrgFile(L"Chase0736_Activity_20261006.CSV", "x");
    WriteOrgFile(L"old chase export.csv", "x");          // any case
    WriteOrgFile(L"Chase statement.pdf", "x");           // not a CSV
    WriteOrgFile(L"Data.CSV", "x");                      // no "chase"
    CreateDirectory((s_orgDir + L"\\Chase folder.csv").c_str(), NULL);  // folder, not a file
    auto names = FindChaseFiles();
    CHECK_EQ(names.size(), (size_t)3);
    CHECK_EQ(names[0], std::wstring(L"Chase0736_Activity_20261006.CSV"));
    CHECK_EQ(names[1], std::wstring(L"Chase2028_Activity_20261006.csv"));
    CHECK_EQ(names[2], std::wstring(L"old chase export.csv"));
}

TEST(organize_builds_data_csv_from_chase_exports) {
    UseTestPaths();
    WriteBytes(s_dataPath, "Post Date,Description,Amount\r\nstale,row,1\r\n");  // replaced
    WriteOrgFile(L"Chase0736_Activity_20261006.csv", std::string(CHECKING_HDR) +
        "DEBIT,10/06/2026,\"POS DEBIT   OLIVE GARDEN, CASPER  WY\",-32.28,MISC_DEBIT, ,,\r\n"
        "CREDIT,09/15/2026,\"PHOENIX ENERGY O PAYROLL   PPD ID: 9111111101\",2425.22,ACH_CREDIT,3638.79,,\r\n"
        "\r\n"
        "DEBIT,not a date,DROPPED,-1.00,DEBIT_CARD,,,\r\n"
        "DEBIT,09/14/2026,,-2.00,DEBIT_CARD,,,\r\n"   // no description: dropped
        "DEBIT,09/13/2026\r\n");                      // too few fields: dropped
    WriteOrgFile(L"Chase2028_Activity_20261006.csv", std::string("\xEF\xBB\xBF") + CARD_HDR +
        "10/04/2026,10/05/2026,ALBERTSONS.COM #0060,Groceries,Sale,-93.94,\r\n"
        "09/16/2026,09/16/2026,Payment Thank You-Mobile,,Payment,379.99,\r\n"   // card payment: dropped
        "09/17/2026,09/17/2026,ALBERTSONS.COM REFUND,Groceries,Return,10.00,\r\n");

    int files = 0, rows = 0;
    CHECK(BuildDataCsv(NULL, files, rows) == BuildResult::Built);
    CHECK_EQ(files, 2);
    CHECK_EQ(rows, 4);
    auto lines = ReadDataLines();
    CHECK_EQ(lines.size(), (size_t)5);
    CHECK_EQ(lines[0], std::wstring(L"Post Date,Description,Amount"));
    CHECK_EQ(lines[1], std::wstring(L"10/6/2026,\"POS DEBIT   OLIVE GARDEN, CASPER  WY\",-32.28"));
    CHECK_EQ(lines[2], std::wstring(L"9/15/2026,PHOENIX ENERGY O PAYROLL   PPD ID: 9111111101,2425.22"));
    CHECK_EQ(lines[3], std::wstring(L"10/5/2026,ALBERTSONS.COM #0060,-93.94"));  // Post Date, not Transaction Date
    CHECK_EQ(lines[4], std::wstring(L"9/17/2026,ALBERTSONS.COM REFUND,10.00"));  // a Return is kept
    CHECK(g_messageBoxes.empty());
}

TEST(organize_overlapping_chase_exports_are_not_double_counted) {
    UseTestPaths();
    // Older export left in the folder, then a newer one covering the same days and more.
    // The two identical Sam's Club charges are real and must both be kept, once.
    WriteOrgFile(L"Chase0736_Activity_20260920.csv", std::string(CHECKING_HDR) +
        "DEBIT,09/15/2026,SAMS CLUB,-3.68,DEBIT_CARD,,,\r\n"
        "DEBIT,09/15/2026,SAMS CLUB,-3.68,DEBIT_CARD,,,\r\n"
        "DEBIT,09/14/2026,NETFLIX,-19.99,DEBIT_CARD,,,\r\n");
    WriteOrgFile(L"Chase0736_Activity_20261006.csv", std::string(CHECKING_HDR) +
        "DEBIT,10/01/2026,NEW ONE,-5.00,DEBIT_CARD,,,\r\n"
        "DEBIT,09/15/2026,SAMS CLUB,-3.68,DEBIT_CARD,,,\r\n"
        "DEBIT,09/15/2026,SAMS CLUB,-3.68,DEBIT_CARD,,,\r\n"
        "DEBIT,09/15/2026,SAMS CLUB,-3.68,DEBIT_CARD,,,\r\n"   // a third one only the newer file has
        "DEBIT,09/14/2026,NETFLIX,-19.990,DEBIT_CARD,,,\r\n"); // same amount, written differently

    int files = 0, rows = 0;
    CHECK(BuildDataCsv(NULL, files, rows) == BuildResult::Built);
    CHECK_EQ(rows, 5);
    auto lines = ReadDataLines();
    CHECK_EQ(lines.size(), (size_t)6);
    CHECK_EQ(lines[1], std::wstring(L"9/15/2026,SAMS CLUB,-3.68"));
    CHECK_EQ(lines[2], std::wstring(L"9/15/2026,SAMS CLUB,-3.68"));
    CHECK_EQ(lines[3], std::wstring(L"9/14/2026,NETFLIX,-19.99"));
    CHECK_EQ(lines[4], std::wstring(L"10/1/2026,NEW ONE,-5.00"));
    CHECK_EQ(lines[5], std::wstring(L"9/15/2026,SAMS CLUB,-3.68"));
}

TEST(organize_chase_export_missing_column_shows_error) {
    UseTestPaths();
    std::string data = "Post Date,Description,Amount\r\n9/5/2026,KROGER,-1.00\r\n";
    WriteBytes(s_dataPath, data);
    WriteOrgFile(L"Chase0736_Activity_20261006.csv", std::string(CHECKING_HDR) +
        "DEBIT,10/06/2026,GOOD,-1.00,MISC_DEBIT,,,\r\n");
    WriteOrgFile(L"Chase9999_Activity_20261006.csv",
        "Transaction Date,Description,Amount\r\n10/04/2026,NO POST DATE,-1.00\r\n");

    RunOrganize(NULL);

    CHECK(SawMessageBox(L"Could not find the required columns in the Chase export"));
    CHECK(SawMessageBox(L"Chase9999_Activity_20261006.csv"));
    CHECK(!SawMessageBox(L"Organize complete!"));
    CHECK_EQ(ReadBytes(s_dataPath), data);  // not half-rebuilt
    CHECK(!FileExists(s_outputPath));
}

TEST(organize_end_to_end_from_chase_exports) {
    UseTestPaths();
    WritePrivateProfileString(L"Meta", L"ColumnSchema", L"2", RulesIni().c_str());
    AddRule(L"KROGER", 4);     // Groceries
    AddRule(L"NETFLIX", 2);    // Bills
    WriteOrgFile(L"Chase0736_Activity_20261006.csv", std::string(CHECKING_HDR) +
        "CREDIT,09/05/2026,\"PAYROLL ACME CORP PPD ID: 12345\",2500.00,ACH_CREDIT,,,\r\n"
        "DEBIT,09/05/2026,\"KROGER #123 CASPER WY\",-45.10,DEBIT_CARD,,,\r\n");
    WriteOrgFile(L"Chase2028_Activity_20261006.csv", std::string(CARD_HDR) +
        "09/19/2026,09/20/2026,NETFLIX.COM,Bills & Utilities,Sale,-15.99,\r\n"
        "09/04/2026,09/05/2026,KROGER #456,Groceries,Sale,-4.90,\r\n");

    RunOrganize(NULL);

    CHECK(SawMessageBox(L"Organize complete!"));
    CHECK(SawMessageBox(L"built from 2 Chase export(s) (4 transactions)"));
    CHECK_EQ(ReadDataLines().size(), (size_t)5);
    auto rows = ReadOutput();
    CHECK_EQ(rows.size(), (size_t)(1 + 30));  // header + every day of September
    auto sep5 = RowFor(rows, L"9/5/2026");
    CHECK_EQ(sep5[1], std::wstring(L"2500.00"));
    CHECK_EQ(sep5[9], std::wstring(L"-50.00"));
    CHECK_EQ(sep5[10], std::wstring(L"Kroger -45.10; Kroger -4.90"));
    auto sep20 = RowFor(rows, L"9/20/2026");
    CHECK_EQ(sep20[5], std::wstring(L"-15.99"));
}

TEST(organize_most_specific_rule_wins) {
    g_rules.clear();
    g_rules[L"AMAZON"] = 8;        // House
    g_rules[L"AMAZON PRIME"] = 2;  // Bills
    g_rules[L"PRIME"] = 9;         // Travel (shorter, also matches)
    CHECK_EQ(FindRule(L"AMAZON PRIME VIDEO"), 2);
    CHECK_EQ(FindRule(L"AMAZON MKTPL"), 8);
    g_rules[L"ZZZZZZZZZZZZ"] = 3;  // a longer snippet that doesn't match changes nothing
    CHECK_EQ(FindRule(L"AMAZON PRIME VIDEO"), 2);
}

TEST(organize_card_payments_are_recognized) {
    CHECK(IsCardPayment(L"PAYMENT THANK YOU-MOBILE"));
    CHECK(IsCardPayment(L"AUTOMATIC PAYMENT - THANK"));
    CHECK(IsCardPayment(L"PAYMENT TO CHASE CARD ENDING IN 2028 10/01"));
    CHECK(!IsCardPayment(L"KROGER #123"));
    CHECK(!IsCardPayment(L"PAYMENT RECEIVED - VENMO"));
}

TEST(organize_refunds_offset_their_category_and_card_payments_are_skipped) {
    UseTestPaths();
    WritePrivateProfileString(L"Meta", L"ColumnSchema", L"2", RulesIni().c_str());
    AddRule(L"KROGER", 4);     // Groceries
    AddRule(L"TRANSFER", 15);  // Ignore
    WriteBytes(s_dataPath, std::string("Post Date,Description,Amount\r\n") +
        "9/5/2026,KROGER #123,-45.10\r\n"
        "9/5/2026,KROGER #123 RETURN,12.00\r\n"                     // refund: back into Groceries
        "9/5/2026,PAYROLL ACME,2500.00\r\n"                         // no rule: Income
        "9/6/2026,Payment Thank You-Mobile,379.99\r\n"              // card side of a payment
        "9/6/2026,Payment to Chase card ending in 2028,-379.99\r\n" // checking side of it
        "9/7/2026,ONLINE TRANSFER FROM SAV 1234,200.00\r\n");       // positive but ruled Ignore

    RunOrganize(NULL);

    CHECK(SawMessageBox(L"Organize complete!"));
    auto rows = ReadOutput();
    auto sep5 = RowFor(rows, L"9/5/2026");
    CHECK_EQ(sep5[9], std::wstring(L"-33.10"));
    CHECK_EQ(sep5[10], std::wstring(L"Kroger -45.10; Kroger Return 12.00"));
    CHECK_EQ(sep5[1], std::wstring(L"2500.00"));
    for (const wchar_t* day : { L"9/6/2026", L"9/7/2026" }) {  // payments and the ignored transfer
        auto r = RowFor(rows, day);
        for (size_t i = 1; i < r.size(); i++) CHECK_EQ(r[i], std::wstring(L""));
    }
}
