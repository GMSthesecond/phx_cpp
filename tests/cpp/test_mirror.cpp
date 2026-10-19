// test_mirror.cpp — unit tests for mirror.cpp (the Mirror button's progress parsing, status and
// confirmation text, and RunScriptLines, which Index uses too).
// Includes mirror.cpp directly so its helpers are visible. RunScriptLines (with and without the
// kill-on-close job Mirror runs in) is tested with cmd.exe one-liners only; nothing else is launched.
#include "minitest.h"
#include "win_fakes.h"
#include "../../mirror.cpp"

// Ids of the processes in job right now.
static std::vector<DWORD> JobPids(HANDLE job) {
    struct { JOBOBJECT_BASIC_PROCESS_ID_LIST list; ULONG_PTR more[63]; } buf = {};
    std::vector<DWORD> pids;
    if (QueryInformationJobObject(job, JobObjectBasicProcessIdList, &buf, sizeof(buf), NULL))
        for (DWORD i = 0; i < buf.list.NumberOfProcessIdsInList; i++) pids.push_back((DWORD)buf.list.ProcessIdList[i]);
    return pids;
}

// True if every process in pids has exited within timeoutMs.
static bool AllExit(const std::vector<DWORD>& pids, DWORD timeoutMs) {
    for (DWORD pid : pids) {
        HANDLE h = OpenProcess(SYNCHRONIZE, FALSE, pid);
        if (!h) continue;  // already gone
        DWORD waited = WaitForSingleObject(h, timeoutMs);
        CloseHandle(h);
        if (waited != WAIT_OBJECT_0) return false;
    }
    return true;
}

// Every line RunScriptLines reports for cmd.
static std::vector<std::string> LinesOf(const std::wstring& cmd) {
    std::vector<std::string> lines;
    CHECK(RunScriptLines(cmd, [&](const std::string& line) { lines.push_back(line); }));
    return lines;
}

TEST(mirror_stage_sets_label_and_bar_start) {
    MirrorProgress p;
    CHECK(ApplyMirrorLine("@STAGE 16 33 Step 2 of 6: Close Date", p));
    CHECK_EQ(p.stage, std::wstring(L"Step 2 of 6: Close Date"));
    CHECK_EQ(p.percent, 16);
    CHECK_EQ(p.lo, 16);
    CHECK_EQ(p.hi, 33);
    CHECK(!p.finished);
}

TEST(mirror_progress_fills_the_current_stage) {
    MirrorProgress p;
    ApplyMirrorLine("@STAGE 0 50 Step 1 of 2: Index (Roosevelt)", p);
    CHECK(ApplyMirrorLine("@PROGRESS 1 2", p));
    CHECK_EQ(p.percent, 25);
    CHECK_EQ(p.detail, std::wstring(L": 1 / 2"));
    ApplyMirrorLine("@PROGRESS 9 2", p);  // more done than total: stays inside the stage
    CHECK_EQ(p.percent, 50);
}

TEST(mirror_progress_tag_found_mid_line) {
    // The Index scripts print "\rProcessing: ..." with no newline right before the tag
    MirrorProgress p;
    ApplyMirrorLine("@STAGE 0 100 Index", p);
    CHECK(ApplyMirrorLine("Processing: 3/4 (75.0%)@PROGRESS 3 4", p));
    CHECK_EQ(p.percent, 75);
}

TEST(mirror_progress_without_total_shows_a_count) {
    // Richland doesn't pre-count (total -1): the bar stays put and the label shows the tally
    MirrorProgress p;
    ApplyMirrorLine("@STAGE 10 20 Step 1 of 6: Index (Richland)", p);
    CHECK(ApplyMirrorLine("@PROGRESS 40 -1", p));
    CHECK_EQ(p.percent, 10);
    CHECK_EQ(p.detail, std::wstring(L": 40 processed"));
}

TEST(mirror_new_stage_clears_the_detail) {
    MirrorProgress p;
    ApplyMirrorLine("@STAGE 0 50 A", p);
    ApplyMirrorLine("@PROGRESS 1 2", p);
    ApplyMirrorLine("@STAGE 50 100 B", p);
    CHECK_EQ(p.detail, std::wstring());
    CHECK_EQ(p.percent, 50);
}

TEST(mirror_finished_fills_the_bar) {
    MirrorProgress p;
    CHECK(ApplyMirrorLine("@FINISHED", p));
    CHECK(p.finished);
    CHECK_EQ(p.percent, 100);
}

TEST(mirror_ignores_other_output) {
    MirrorProgress p;
    CHECK(!ApplyMirrorLine("Saved: C:\\Users\\x\\report.csv", p));
    CHECK(!ApplyMirrorLine("@STAGE nonsense", p));
    CHECK_EQ(p.stage, std::wstring());
}

TEST(mirror_stage_label_is_utf8) {
    MirrorProgress p;
    ApplyMirrorLine("@STAGE 0 10 Caf\xc3\xa9 \xe2\x80\x94 step", p);
    CHECK_EQ(p.stage, std::wstring(L"Caf\u00e9 \u2014 step"));
}

TEST(mirror_status_text_shows_elapsed_time) {
    MirrorProgress p;
    CHECK_EQ(MirrorStatusText(p, 0), std::wstring(L"Starting... - 0:00 elapsed"));
    ApplyMirrorLine("@STAGE 0 50 Step 1 of 6: Index (Roosevelt)", p);
    ApplyMirrorLine("@PROGRESS 12 40", p);
    CHECK_EQ(MirrorStatusText(p, 65 * 1000 + 400),
             std::wstring(L"Step 1 of 6: Index (Roosevelt): 12 / 40 - 1:05 elapsed"));
    CHECK_EQ(MirrorStatusText(p, 75 * 60 * 1000), std::wstring(L"Step 1 of 6: Index (Roosevelt): 12 / 40 - 75:00 elapsed"));
}

TEST(mirror_status_text_says_when_stopping) {
    MirrorProgress p;
    ApplyMirrorLine("@STAGE 16 33 Step 2 of 6: Close Date", p);
    p.stopping = true;
    CHECK_EQ(MirrorStatusText(p, 5000), std::wstring(L"Stopping... Step 2 of 6: Close Date - 0:05 elapsed"));
}

TEST(mirror_command_passes_the_stop_file) {
    CHECK_EQ(MirrorCommand(L"C:\\My Apps\\", L"mirror.py", L"C:\\Temp Dir\\phx_mirror_stop_1_2.flag"),
             std::wstring(L"py \"C:\\My Apps\\mirror.py\" --stop-file \"C:\\Temp Dir\\phx_mirror_stop_1_2.flag\""));
}

TEST(mirror_stop_confirm_text_names_the_running_step) {
    std::wstring text = MirrorStopConfirmText(L"Step 3 of 7: Case Update");
    CHECK_EQ(text, std::wstring(
        L"Stop Mirror?\n\nThe step running now (Step 3 of 7: Case Update) stops right away, and the steps "
        L"after it are skipped.\nSteps that already finished stay done, including their uploads to Ark.\n\n"
        L"You'll still get the report of what ran."));
    CHECK(MirrorStopConfirmText(L"").find(L"The step running now stops right away") != std::wstring::npos);
}

TEST(mirror_confirm_text_lists_steps_and_uploads) {
    std::wstring text = MirrorConfirmText({ L"Index", L"Close Date", L"Cost to Extend" },
                                          { L"Close Date", L"Cost to Extend" });
    CHECK_EQ(text, std::wstring(
        L"Mirror will run these buttons, one after another:\n"
        L"Index, Close Date, Cost to Extend\n\n"
        L"These upload to Ark (live data):\n"
        L"Close Date, Cost to Extend\n\n"
        L"A sign-in may be needed when the first browser opens. Start now?"));
}

TEST(mirror_confirm_text_without_uploads) {
    std::wstring text = MirrorConfirmText({ L"Index" }, {});
    CHECK(text.find(L"upload") == std::wstring::npos);
    CHECK(text.find(L"Index\n\n") != std::wstring::npos);
}

TEST(run_script_lines_splits_output_into_lines) {
    std::vector<std::string> lines = LinesOf(L"cmd /c \"echo first& echo @PROGRESS 2 3& echo last\"");
    CHECK_EQ(lines.size(), (size_t)3);
    CHECK_EQ(lines[0], std::string("first"));
    CHECK_EQ(lines[1], std::string("@PROGRESS 2 3"));
    CHECK_EQ(lines[2], std::string("last"));
}

TEST(run_script_lines_reports_a_launch_failure) {
    CHECK(!RunScriptLines(L"no_such_program_phx_test.exe", [](const std::string&) {}));
}

TEST(run_script_lines_returns_when_the_script_exits_even_if_a_child_keeps_running) {
    // A browser left running by a script still holds the output pipe; Mirror must not wait on it.
    DWORD start = GetTickCount();
    std::vector<std::string> lines = LinesOf(L"cmd /c \"start /b ping -n 6 127.0.0.1 >nul & echo done\"");
    DWORD took = GetTickCount() - start;
    CHECK(took < 3000);
    CHECK_EQ(lines.back(), std::string("done"));
}

TEST(run_script_lines_in_a_job_keeps_what_the_script_started_in_it) {
    // Mirror's Stop and closing the app end the job, which must hold the browser a step left behind
    HANDLE job = CreateKillOnCloseJob();
    CHECK(job != NULL);
    std::vector<std::string> lines;
    CHECK(RunScriptLines(L"cmd /c \"start /b ping -n 30 127.0.0.1 >nul & echo done\"",
                         [&](const std::string& line) { lines.push_back(line); }, job));
    CHECK_EQ(lines.back(), std::string("done"));
    std::vector<DWORD> left = JobPids(job);
    CHECK(!left.empty());  // ping outlived cmd, inside the job
    CHECK(TerminateJobObject(job, 1));
    CHECK(AllExit(left, 5000));
    CloseHandle(job);
}

TEST(kill_on_close_job_ends_its_processes_when_closed) {
    // What happens to a running Mirror when the app exits (its job handle closes)
    HANDLE job = CreateKillOnCloseJob();
    CHECK(job != NULL);
    CHECK(RunScriptLines(L"cmd /c \"start /b ping -n 30 127.0.0.1 >nul\"", [](const std::string&) {}, job));
    std::vector<DWORD> left = JobPids(job);
    CHECK(!left.empty());
    CloseHandle(job);
    CHECK(AllExit(left, 5000));
}
