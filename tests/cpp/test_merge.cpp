// test_merge.cpp — unit tests for merge.cpp (the Merge button's link window): which pasted links
// and record ids it accepts, the reasons it gives for the rest, and the arguments it builds for merge.py.
// Includes merge.cpp directly so its static helpers are visible. No window is opened.
#include "minitest.h"
#include "win_fakes.h"
#include "../../merge.cpp"

// Record ids of the Dummy 1 / Dummy 2 test accounts made for Merge.
static const std::wstring kId1 = L"298bf830230991db2c6679eb", kId2 = L"2176a2baecb3919109798abe";
// Dummy 1's link as copied from the browser's address bar.
static const std::wstring kLink1 = L"https://ark.phoenixenergy.com/accounts?recordId=" + kId1;

// The id ParseAccountLink reads from text, or "error: <reason>".
static std::wstring Parsed(const std::wstring& text) {
    std::wstring id, error;
    return ParseAccountLink(text, id, error) ? id : L"error: " + error;
}

TEST(merge_reads_the_id_from_an_account_link) {
    CHECK_EQ(Parsed(kLink1), kId1);
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts?recordId=" + kId2), kId2);
}

TEST(merge_accepts_a_bare_record_id) {
    CHECK_EQ(Parsed(kId1), kId1);
    CHECK_EQ(Parsed(L"298BF830230991DB2C6679EB"), kId1);  // lowercased for merge.py
}

TEST(merge_ignores_blanks_around_a_paste) {
    CHECK_EQ(Parsed(L"  " + kLink1 + L"\r\n"), kId1);
    CHECK_EQ(Parsed(L"\t" + kId1 + L" "), kId1);
}

TEST(merge_accepts_link_variations) {
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts/?recordId=" + kId1), kId1);  // trailing slash
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts?tab=history&recordId=" + kId1 + L"&x=1#top"), kId1);
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts?recordId=" + kId1 + L"#history"), kId1);
    CHECK_EQ(Parsed(L"https://ark.phxcapitalgroup.com/accounts?recordId=" + kId1), kId1);  // Ark's other domain
    CHECK_EQ(Parsed(L"HTTPS://ARK.PHOENIXENERGY.COM/ACCOUNTS?RECORDID=298BF830230991DB2C6679EB"), kId1);
}

TEST(merge_rejects_an_empty_box) {
    CHECK_EQ(Parsed(L""), std::wstring(L"error: is empty: paste a link to an Ark account."));
    CHECK_EQ(Parsed(L" \r\n "), std::wstring(L"error: is empty: paste a link to an Ark account."));
}

TEST(merge_rejects_links_to_other_pages) {
    const std::wstring notAccount = L"error: isn't a link to an Ark account (it should contain /accounts?recordId=).";
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/landholdings?recordId=" + kId1), notAccount);
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/report?recordId=" + kId1), notAccount);
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts"), notAccount);
    CHECK_EQ(Parsed(L"ark.phoenixenergy.com/accounts?recordId=" + kId1), notAccount);  // no https://
    CHECK_EQ(Parsed(L"Dummy1"), notAccount);
}

TEST(merge_rejects_two_things_in_one_box) {
    CHECK_EQ(Parsed(kLink1 + L" " + kId2), std::wstring(L"error: has more than one thing in it: paste one link per box."));
    CHECK_EQ(Parsed(L"Dummy 1"), std::wstring(L"error: has more than one thing in it: paste one link per box."));
}

TEST(merge_rejects_a_damaged_record_id) {
    const std::wstring damaged = L"error: has a record id that isn't 24 letters and digits: copy the link again.";
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts?recordId=298bf830230991db2c6679e"), damaged);   // short
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts?recordId=298bf830230991db2c6679ebb"), damaged); // long
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts?recordId=298bf830230991db2c6679ez"), damaged);  // not hex
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts?recordId="), damaged);
}

TEST(merge_rejects_an_account_link_without_a_record_id) {
    CHECK_EQ(Parsed(L"https://ark.phoenixenergy.com/accounts?tab=history"),
             std::wstring(L"error: has no recordId in it: copy the link from the account's page."));
}

TEST(merge_args_are_both_ids_in_the_order_typed) {
    std::wstring args, error;
    CHECK(CheckMergeLinks(kLink1, L"https://ark.phoenixenergy.com/accounts?recordId=" + kId2, args, error));
    CHECK_EQ(args, kId1 + L" " + kId2);
    CHECK(CheckMergeLinks(kId2, kLink1, args, error));
    CHECK_EQ(args, kId2 + L" " + kId1);
}

TEST(merge_error_names_the_box_with_the_problem) {
    std::wstring args = L"unchanged", error;
    CHECK(!CheckMergeLinks(L"", kId2, args, error));
    CHECK_EQ(error, std::wstring(L"Account 1 is empty: paste a link to an Ark account."));
    CHECK(!CheckMergeLinks(kId1, L"https://ark.phoenixenergy.com/landholdings?recordId=" + kId2, args, error));
    CHECK_EQ(error, std::wstring(L"Account 2 isn't a link to an Ark account (it should contain /accounts?recordId=)."));
    CHECK_EQ(args, std::wstring(L"unchanged"));
}

TEST(merge_rejects_the_same_account_twice) {
    std::wstring args, error;
    CHECK(!CheckMergeLinks(kLink1, L"298BF830230991DB2C6679EB", args, error));
    CHECK_EQ(error, std::wstring(L"Both links are the same account: paste the other account's link in one box."));
}

// Fills both link boxes with valid links and presses Continue.
static void ContinueWithValidLinks(HWND popup, HWND) {
    SetDlgItemText(popup, ID_MG_FIRST, kLink1.c_str());
    SetDlgItemText(popup, ID_MG_SECOND, kId2.c_str());
    SendMessage(popup, WM_COMMAND, IDOK, 0);
}

TEST(merge_window_reenables_the_launcher_before_it_closes) {
    RegisterMergeClass(GetModuleHandle(NULL));
    CHECK(OwnerEnabledWhenPopupCloses(MERGE_CLS, [](HWND popup, HWND) { SendMessage(popup, WM_COMMAND, IDCANCEL, 0); }));
    RegisterMergeClass(GetModuleHandle(NULL));
    CHECK(OwnerEnabledWhenPopupCloses(MERGE_CLS, [](HWND popup, HWND) { SendMessage(popup, WM_CLOSE, 0, 0); }));
    RegisterMergeClass(GetModuleHandle(NULL));
    CHECK(OwnerEnabledWhenPopupCloses(MERGE_CLS, ContinueWithValidLinks));
    CHECK(g_mergeAccepted);
}
