# Testing

Regression tests that check every button still works after a change. They run in about
30 seconds and are **completely offline**: nothing logs into Ark or Enverus, nothing uploads,
and no real file on your Desktop, in Box or in `%APPDATA%` is read or changed.

Companion docs: [ARCHITECTURE.md](ARCHITECTURE.md) · [INDEX.md](INDEX.md#tests) · [KNOWN_ISSUES.md](KNOWN_ISSUES.md)

---

## Running the tests

One-time setup: `py -m pip install pytest` (`run_tests.bat` does this for you if it's missing).

| Where | How |
|---|---|
| **VS Code Testing panel** | Click the beaker icon in the left sidebar. Press ▷ at the top to run everything, or ▷ next to one file or test. Failures show inline with the reason. If the panel is empty, run **Python: Configure Tests** from the command palette (Ctrl+Shift+P) and pick *pytest* → *tests*. |
| **VS Code task** | Ctrl+Shift+B runs **Run all tests**. *Terminal → Run Task… → Run quick tests (Python only)* skips the C++ builds (about 2 seconds). |
| **Terminal** | `py -m pytest` (everything), `py -m pytest tests/test_map.py` (one file), `py -m pytest -k aoi` (tests whose name contains "aoi"), `py -m pytest -m "not app"` (skip clicking the app). |
| **Explorer** | Double-click `run_tests.bat`. |

Run them **after every change, before you commit**. A run ends with a line like
`353 passed` (plus `N xfailed` while a known bug has a test). Anything `failed` means a button no longer does what it used to.

### Reading the results

| Result | Meaning |
|---|---|
| `passed` | Works as expected. |
| `failed` | Something broke. The message says what was expected and what happened. |
| `xfailed` | A **known bug** from [KNOWN_ISSUES.md](KNOWN_ISSUES.md). The test describes the correct behavior and is expected to fail until the bug is fixed. |
| `XPASS(strict)` / "marked KNOWN_BUG but now passes" | You fixed a known bug. Remove the `xfail` mark (Python) or change `KNOWN_BUG` to `TEST` (C++), and delete the KNOWN_ISSUES entry. |
| `skipped` | Visual Studio wasn't found, so the C++ tests couldn't build. |

---

## What is tested

Four layers, from fastest to most realistic:

1. **Wiring checks** ([tests/test_wiring.py](../tests/test_wiring.py)) read `main.cpp`, `settings.cpp`,
   the scripts and the docs as text. They catch the usual mistakes when adding a button: duplicate
   control ids, a button with no `MoveWindow` line or no click handler, a script name typo, a
   button missing from the docs or from the tests, mismatched settings.ini keys, and any script
   that no longer compiles or imports.
2. **Script tests** (one file per button) run the real Python code on small sample CSVs and check
   the output files. Ark, Enverus and BLM are replaced with fakes (see *Safety net* below).
3. **C++ unit tests** ([tests/cpp/](../tests/cpp/), run by [tests/test_cpp.py](../tests/test_cpp.py))
   compile Organization, Rename, Settings, Mirror and Merge with MSVC into a temp folder and test their logic with
   sample files.
4. **Click every button** ([tests/test_app_buttons.py](../tests/test_app_buttons.py)) builds a test copy
   of `phxcpp.exe` in a temp folder, puts a harmless *stand-in* next to it for every script it
   can launch, starts it and clicks each button. A stand-in only records that it ran, so this
   proves each button launches the right script with the right arguments. It also checks the
   layout (every button visible, inside the window, no overlaps, each in its `COLUMNS` column and order under its header;
   yellow and green buttons owner-drawn),
   the Index and Mirror progress bars, the Maps build → upload order, that dialogs open and close,
   and that yellow buttons do nothing. Organization is not clicked because it reads your real Chase exports and `Data.CSV`.

### Button → tests

| Button | Logic tested in | Clicked in the app test |
|---|---|---|
| Mirror | [test_mirror.py](../tests/test_mirror.py): step order, carrying on after a failure, report groups, dated archive (appended on a second run), report box (task dialog with clickable links and archive path, message-box fallback, link clicks, struct layout), each step in its own process with the 20-minute limit (a hung child and its own child are killed; a crash is reported with its last line), Index step totals, a full run of the real steps against the fake Ark (Docket Updates Slack with its Slack messages stubbed), Stop (stop file read from `--stop-file`, the running child's process tree killed, the rest Not run, a late `@RESULT` kept, the Data Loader note for an uploading step, report still written); each green button's `mirror_step` in its own test file; [test_cpp.py](../tests/test_cpp.py) (`mirror_*`, `run_script_lines_*`, `kill_on_close_job_*`): progress parsing, status, confirmation and Stop text, the command line, output reading, the job holding what the script started and ending it when closed | yes: confirmation (No runs nothing), progress bar and status, Mirror reads Stop while step buttons and PPIQ / AOI / NAI are disabled then restored, Stop asks (No keeps running) then ends the run early, buttons come back while the report box is still open, error box if mirror.py stops early, refuses while Index runs |
| PPIQ | [test_ppiq.py](../tests/test_ppiq.py) (real report headers): downloads saved under fixed names, no fixed waits, both logins, a different report stops the run, all 4 issue types, LHT mismatch rows with both amounts, details from Landholdings In Queue (EM) first (filled with EM All Landholdings cut down, and winning when both list a landholding), from EM All Landholdings for a queued landholding with no price paid, a paid report missing a detail column stops the run, a landholding missing from EM All Landholdings or with two issues, blank amounts, BOM for Excel, folder from `[Folders] PPIQ`, issue-count box, the queue report refused as the (trimmed) Inverse report, column names in other capitals, a file open in Excel stops before downloading (`fakes.locked_like_excel`), the output opened mid-run gets the same box; xfail: blank Ids skipped, an unreadable amount names its report | yes |
| Index | [test_index.py](../tests/test_index.py): all 3 counties, skip already-indexed (Richland by name without extension), page counts, Excel append, a backup per county, Divide's BOM, `@PROGRESS`/`@DONE` tags, re-run adds nothing, `main()` returns the count, paths from Settings, missing workbook / workbook open in Excel (before the scan and mid-run) stop with a readable message, shown in a box as a button | yes, with the progress bar and summary counts |
| STR / AOI | [test_str_verification.py](../tests/test_str_verification.py): both checks, padding, every AOI name format in the real report parsed into sections (two townships, no name, spacing; unreadable names flagged), a section counted only under its own township-range, 4 not covered by 14 nor 53N by 153N, a row's section from Section Name then S-T-R fields (Township without N, blank Section Name), the Issue text, `--aoi` picks the report and folder, each folder from its own `[Folders]` key, Mirror steps (STR: mismatch count; AOI: rows in the error report or none, AOI folder only); [test_mirror.py](../tests/test_mirror.py): AOI is the last step and its line ends the report (review, none, Failed, Not run after a Stop) | yes |
| TPP-LHPP | [test_tpp_lhpp.py](../tests/test_tpp_lhpp.py): LHT sums, $1 tolerance, export workbook, Close Date message box, Mirror step (only mismatches closing in the next 14 days, unreadable Close Dates flagged, no box; No changes when the export has the last one's rows in any order, Needs review on any difference or a missing/damaged last export) | yes |
| NAI | [test_nai_download.py](../tests/test_nai_download.py): dated names, login, done box, folder from `[Folders] NewlyAcquiredInterest`, never the old `DataMeetingDownload` (DMD) key; [test_cpp.py](../tests/test_cpp.py) (`settings_old_dmd_key_is_ignored`): the Settings row ignores the old key too | yes |
| C2E | [test_cost_to_extend.py](../tests/test_cost_to_extend.py): $10 threshold, notes, upload call (faked, Landholdings), Mirror step | yes |
| Settings | [test_cpp.py](../tests/test_cpp.py) (`settings_*`): every row saves and loads, defaults kept, saving one row leaves the rest alone, get/set by key, secrets hidden, closing the window re-enables the launcher first; Python reads every value C++ writes (a `%` included); [test_wiring.py](../tests/test_wiring.py): every folder/file a script reads has a row | yes, the dialog opens and closes |
| Unit Connect to Cases | [test_case_matchup.py](../tests/test_case_matchup.py): matching rules, notes (a case number counts only whole: C-1 isn't C-14), export, summary | yes |
| Bring out your dead | [test_deceased.py](../tests/test_deceased.py): heir × holding rows, share scaling, same-section holdings kept apart, two runs in one process stay separate, done box | yes |
| QQ | [test_qq_checker.py](../tests/test_qq_checker.py): aliquot reading (halves, quarters, nested, partial quarter-quarters as whole, fraction notation N12 / SE14 / NW4, typos rejected), description lists (`, ; &` AND), space rules ("NE NW" = NENW, "S2NE W2" = two tracts), free text unreadable, suggested Quarter Section wording; row checks: spec example passes (0 = blank, equivalent Quarter Section wording), each Note kind, Mismatch Tract / Quarter Section / Both / Unreadable, no values, blank fields; main(): only failing rows written, Title Source and State carried, counts box, header-only output, Windows-1252 export, missing export or column | yes |
| Organization | [test_cpp.py](../tests/test_cpp.py) (`organize_*`): parsing, rules (most specific wins), migration, scrubbing, Chase exports → Data.CSV (both layouts, overlap dedupe, card payments dropped, bad header), card payments skipped and refunds offsetting their category, full Data.CSV → Organized.CSV, default rules seeded on a fresh machine but never over learned ones, closing the classify dialog re-enables the launcher first; [test_wiring.py](../tests/test_wiring.py): the committed `default_organize_rules.ini` is valid | no (uses personal files) |
| Rename | [test_cpp.py](../tests/test_cpp.py) (`rename_*`): ID3 read/write, extended-header tags kept verbatim, failed write leaves the MP3 untouched, CSV generate/apply, closing the dialog re-enables the launcher first | yes, the dialog opens and closes |
| Cases Unit Names | [test_case_unit_names.py](../tests/test_case_unit_names.py): both downloads, login, exact STR-set match, already-right cases left out, blank unit names, comma-joined names, continuation rows, replaced-name message box and overflow CSV, upload call (faked, Cases dataset), no upload when nothing to fix, session saved on failure, Mirror step (upload count only, no box) | yes |
| SIB | [test_section_id_blank.py](../tests/test_section_id_blank.py): the index: sections from earlier downloads still match, new sections appended (dated), a name with a new Id takes it, the download deleted after the merge, a name with two Ids in one download stops (index untouched, download kept), a missing index stops before Ark opens, a name twice in the index stops, `--seed` (builds, keeps the download, never overwrites, stops on two Ids); match by Section Name (case and spaces ignored), several landholdings on one section, unmatched left alone, rows with a Section Id already or missing fields skipped, upload call (faked, Landholdings), no upload when nothing matches, wrong report from either URL (index untouched), Mirror step (Uploaded / nothing, replaced Ids named, no box) | yes |
| Close Date | [test_close_dates.py](../tests/test_close_dates.py): Monday weekend rule, holidays (incl. observed dates), date formats, Deferred (real 4-column report), wrong report fails with nothing written or uploaded, upload call (faked, Landholdings), no upload when nothing closed, Mirror step (no Deferred box) | yes |
| Case Update | [test_case_update.py](../tests/test_case_update.py): date stamping, upload call (faked, Units), no upload when empty, session saved on failure, Mirror step | yes |
| Docket Updates Sheet | [test_docket_updates.py](../tests/test_docket_updates.py): workbooks built with openpyxl, RW report from the fake Ark. Reading: ND and MT only (UT / WY / Sheet2 ignored), rows without a case number skipped, numeric case numbers, non-breaking-space blanks, missing workbook / sheet / column boxes, section lines (no part, AL / All, two parts on a line, spaces, lots and names unreadable). Which row wins: latest hearing's rows = sub-cases (same land = one sub-case with several types, one Not in RW row), latest type, latest result with its order details (noted when re-listed later), fill-down Order Number ignored, Docketed for a hearing to come, no status after a past hearing (CONTINUED noted). Status and type mapping; Order Status left on a Dismissed / Docketed case flagged, not blanked. Comparison: every field, dates in either format (uploaded as MM/DD/YYYY; unreadable RW date noted), blanks never overwrite RW, generic ESTABLISH SPACING (and RW's generic made specific), well types by whole section, unreadable sections skipped, sub-cases by land then position, Phoenix cases Not in RW (sub-cases `-k`) and others ignored, Not in workbook (leftover sub-cases; Utah and Roman-numeral ones skipped), continuation rows, report without the new columns. main(): the three CSVs with BOM, summary text, nothing uploaded, report without Record Id, CSV locked by Excel, defaults equal the Settings dialog's | yes |
| Docket Updates Slack | [test_docket_updates_slack.py](../tests/test_docket_updates_slack.py) (the old Docket Updates tests, `Slack_` file names): fake Slack API; only the last 7 days (`oldest` sent, an older post and its case left out, window ends at the current time by default; a reply in the window to an older post is xfail), only her messages, newest first, time IDs unique within a second, paging, thread replies (hers in anyone's thread, broadcasts once), joins skipped, link/`&amp;` cleanup, 429 retry, Slack error / no token / Excel-locked boxes (each with the stale-files warning), any other error raised as `RunFailed` with the warning in run_button's box, BOM, default `Desktop\Docket Updates` folder. Case parsing: header variants (missing colons, also before the status (`Pooling GRANTED`, none at all, a dash, struck-out text), nested parentheses, struck-out / misspelled status, two numbers), status on the next line, sections / state headings skipped, well count summed from `(N Wells)` lines (unit names, singular, no parentheses, remarks ignored, only the case above, both blocks of a repeated case, filled from older posts), newest post with info wins, blanks filled from older posts. RW comparison (fake Ark report): status / Order Status mapping, type mapping (`_rw_types`, no longer compared), type / applicant / sections not compared, RW Case Notes attached (column found ignoring case, never compared), well count vs RW Number of Wells (decimal, blank, text, no Slack count, column found ignoring case, total over several sub-cases with a note, not compared without the column), one row per `<number>` / `<number>-k` record (Roman-numeral sub-cases only when there are none), every number of a case looked up, Not in RW, duplicates, continuation rows skipped; order date from the `Board Order Updates from` heading (singular, two-digit year, any case; the post's date without a readable one; used for the upload; RW already holding it matches); blank or earlier Date Order Signed differs when Slack has a result (GRANTED, DENIED, DISMISSED; not when on or after the order date, unreadable or no result; not compared without the column; Slack Order Date + RW Date Order Signed highlighted); Slack_Not_In_RW.csv (Not in RW rows only, one per case, no state or sections, status in RW terms, well count as Number of Wells); Slack_Docket_Differences.xlsx (Differs rows only, Slack and RW cells of each difference highlighted, bold frozen filterable header, clickable Link); Slack_Docket_Upload.csv (column names, Slack values, RW values carried forward, RW well count kept, DISMISSED blank Order Status, DISMISSED takes Slack's well count and the post date, Date Order Signed only moved forward / time stripped / unreadable kept + noted, link not added twice, differing records only, sub-cases / duplicates / two numbers held back with a note, columns the report lacks left out, header-only without cases); Parsed_Slack_Messages.csv name; finish box names report columns not compared; no Ark download without cases; locked differences workbook / upload / Not in RW CSV; main() returns the counts. Mirror step: no box, Needs review / No changes line naming the files (differs, not in RW, both, no cases, no differences), no token / Slack error / locked file raised as `RunFailed` (warning first, then the error) instead of shown, Mirror's Failed line keeps the warning after a long error | yes |
| Merge | [test_merge.py](../tests/test_merge.py): links and bare ids read (blanks, trailing slash, other query parts, other Ark domain, any case), anything else refused (other record types, damaged ids, two links in one box); both accounts read from the fake Ark in the order given and shown in the review window (recorded; no message box); each account's details (Created Date, disposition, address, phone, emails), Quick Reference counts (thousands separators) and notes (trimmed, several lines; an unrelated "Notes" field ignored), items and fields a page doesn't show (None, not 0 or blank), the tables sharing the Quick Reference id and the second copy of each section ignored, values taken only once two reads agree, a page that never fills fails after 30 s; each linked land holding read once, after its account (Legal Entity, Section Name, Title Information, signers in number order with Last Name / Capacity, blank ones left out), land holdings counted but not linked reported, "Land Holding Not Found" fails; review rows (one text per account, "blank" / "none" / "not on this page"), land holding lines, the window itself (built hidden: each value in its account's column, land holdings under their account, the red not-read line, links open the browser, Keep Account 1 / 2 and Cancel answer and close it); the merge step: (keep) / (merge) added and replacing an earlier tag, the note block (date + RM, a differing mailing address on one line, only phone numbers / emails the kept account lacks, the same values typed differently left out, notes between quote lines, nothing when there's nothing to add), the kept account's blanks filled from the merge account (`blank_fills`: phone and email each on its own, the address only when wholly blank, trimmed, fields not on the page and blank merge values skipped, what's copied left out of the note; through the fake: listed in the Yes/No box, saved, checked after the reload, said in the Done box; a box no longer blank stops before the kept account is saved; `_check_saved` compares them), notes combined above the old ones, the Call Notes block (no address lines); through the fake edit windows: both renamed, both blocks saved and the merge account's records moved for either account kept (several of each kind, kind by kind; only Call Notes to add; nothing to add or move), the Yes/No box text and Done box, closing the window or answering No changes nothing, an already-tagged merge account isn't saved again, a kept account without Account Notes stops before anything changes, Merge waits for Ark's save answer before reloading (a reload sooner cancels the save, as in Ark), no answer / an error answer / a rename Ark didn't keep / a window that never fills in / a missing or doubled box each stop with an error; records that can't be moved are noted in a warning Done box while the rest move (Ark refuses the save, another account with the kept name, the search never lists it, the pick doesn't take, no Account lookup, the record's Account no longer the merge account, more counted than the drawer ever lists), with Ark's count of what's left given once, as why it wasn't deleted; Quick Reference entries clicked by their exact label (not an expanded table containing it); notes tabs clicked by their exact name (not a label containing it), else the first text containing it; records the drawer lists only later moved in another pass, a long list scrolled until all show; parent account (field, else the "Parent - " entry) and its note line only when it differs; land holdings: the drawer read for ones the page doesn't link, the window's options (Legal Entities, signer lists, capacities, each once even when one land holding has a capacity twice), `clean_signers`, `holding_plans` (merge account's all move, kept ones only when changed, case and spacing aside), the Yes/No box's land holding lines, each moved / changed and checked (Account, Legal Entity, the signer boxes Ark has: Signer 1–9, Last Name 1–2, Capacity 1–3, later signers emptied; the Signer Information tab found when its text isn't exactly its name), a signer part Ark has no box for stops that land holding (`missing_signer_boxes`), closing the window changes nothing, no window without land holdings, one failing is noted and the rest go on, a change Ark doesn't show is noted, one left on the merge account blocks the delete; the land holdings window (starts from what each has, typed values trimmed, Copy signers from, Apply to all, Add signer stops at 9, Last Name / Capacity boxes Ark lacks greyed out, Cancel); documents copied (download, rename with an extension from the listed name / Ark's download name / the contents, Windows-safe names, upload, folder emptied, the merge account keeps its copies), file types from contents (PDF, PNG, JPG, GIF, TIF, RTF, docx / xlsx / pptx / zip, doc / xls / msg), an unknown type not copied, documents never listed, an upload listed without its extension, an upload Ark doesn't list kept in the folder; a document failing with no error message noted by the error's kind; the upload check stops after 30 s even when each look is slow; deleting the merge account: both accounts opened for review, Yes deletes (Delete, the confirmation's Delete, Ark's answer, Account Not Found), No keeps it (and the kept account's "(keep)"), Yes then renames the kept account without "(keep)" (`untag_kept`; a failed rename is a warning box with the link), a stale Land Holdings count doesn't block it (the drawer lists none), land holdings / records left / documents not copied / problems block it (warning, no question), rechecked right before deleting (name, counts), a confirmation box without one Delete button deletes nothing, a delete Ark refuses / doesn't answer / doesn't carry out stops with an error, an earlier answer naming the account doesn't cut the delete short (checked in another tab); the first account reopened after a login, names with dashes / the same name twice; "Account Not Found" fails at once, a page that never loads after 30 s; wrong argument counts and the same account twice stop before a browser opens; error box + `merge_error.log` in `%APPDATA%`. [test_cpp.py](../tests/test_cpp.py) (`merge_*`): the link window's parsing, each error reason, the arguments built, the same account twice, closing the window re-enables the launcher first | yes: the window opens and closes; valid links run `merge.py <id> <id>`; an empty box, a landholding link or the same account twice keep it open with the reason and run nothing |
| Maps | [test_map.py](../tests/test_map.py): STR parsing, shapes from a fake BLM, one zip per operator, uploader moves zips, operator colors, Enverus login starts from the app URL | yes, build then upload |
| Yellow (TODO) buttons | — | yes, a click does nothing |
| Hidden (HIDDEN) buttons (none at present) | [test_wiring.py](../tests/test_wiring.py): `g_hiddenButtonIds` matches the spec, and the handler still launches the script and the layout line is still there | yes, not shown, disabled, and a `BM_CLICK` launches nothing |

[test_error_reporting.py](../tests/test_error_reporting.py) also checks that every button script shows an
error box when it fails, naming the error and its log (the scripts have no console, so otherwise failures are
invisible), and that the map scripts name a missing package.
[test_ark_common.py](../tests/test_ark_common.py) tests the Data Loader upload every uploading button shares
(`ark_common.upload`): it picks the dataset asked for, confirms with the operation, and stops at the "X of Y" row counter.
It also checks the report download every Ark button shares (`ark_common.trigger_download`, against a `FakeReportPage`):
it waits until Ark's notifications list the new file and takes that one (not an older export, and not held up
by Data Loader notifications stuck at "0% Complete"), and fails after 10 minutes rather than take an older file
(a large export gets at least 2 minutes to start downloading), and `check_columns` rejects a report with other columns.
Large downloads: `record_count` reads the page's Total Record Count (a `FakeReportPage(count_texts=[...])`), and
a report of 10,000 records or more (`LARGE_DOWNLOAD_ROWS`; exactly 10,000 counts) or with an unreadable count
gets a Yes/No box before Ark is asked for anything. No raises `DownloadCancelled` with nothing requested, Yes downloads,
and smaller reports get no box. `run_button` shows a cancel as "stopped" (no log). test_mirror checks a No fails only
that step and that the step's time limit is paused while the box waits. To test a script's own large report, serve it
with `fake_ark.serve(url, rows, records=12_345)` and answer the box with `msgboxes.answers = [7]` (No) or `[6]` (Yes).
It also checks settings with `%`
are read as typed, that `read_folder` reads only its own key, and that `ark_page` keeps the login after an error.

---

## Safety net

[tests/conftest.py](../tests/conftest.py) loads before any test and makes the whole run harmless:

- **No browser.** Playwright is replaced by a stub that refuses to launch. Tests that need Ark use
  the `fake_ark` fixture ([tests/fakes.py](../tests/fakes.py)): the test *serves* a CSV for a report
  URL and the script "downloads" it from disk. Waits aren't slept, so runs are instant.
- **No uploads.** `ark_common.upload` (Data Loader) and the Enverus steps are replaced with recorders, so the
  test can check what *would* be uploaded. Tests that run `ark_common.upload` itself hand it a `FakeLoaderPage`,
  which has no browser behind it.
- **No network.** Any outgoing connection or DNS lookup raises an error. Docket Updates Slack's calls go to
  `FakeSlack` in [test_docket_updates_slack.py](../tests/test_docket_updates_slack.py) instead.
- **No real settings.** `ark_common` points at a fake `settings.ini` (fake Ark, Enverus and Slack credentials, temp folders).
  The C++ tests redirect `%APPDATA%` the same way.
- **No real files.** Every script's folder (and the index workbook) is pointed at a per-test or sandbox temp
  folder; `test_wiring` checks the sandbox covers every `[Folders]` setting. The C++ tests point the Organize
  and Rename folder settings at temp folders (`SetSetting`).
- **No real Mirror steps.** `mirror.RUN_IN_CHILD` is off, so Mirror runs its steps inside the test process
  (where all of the above applies) instead of starting real ones in child processes.
- **No dialogs.** Message boxes are recorded instead of shown (`msgboxes` fixture), and so are Mirror's report
  task dialog (`task_dialogs`, also in `msgboxes` without its link markup) and Merge's review window (`reviews`; it answers
  `reviews.keep`), so a test can check what the user would have seen. Yes/No boxes answer Yes unless the test
  queues `msgboxes.answers` (e.g. `[7]` = No). test_merge builds the review window itself, hidden, and
  never waits on it.
- **No browser tabs.** `webbrowser.open` only records the URL (`browser_tabs` fixture; Merge opens both accounts
  for review before asking to delete one).
- **Never in the repo.** The C++ builds go to a temp folder ([tests/msvc.py](../tests/msvc.py) refuses
  the repo folder), and nothing is launched except the test build with its stand-ins.

---

## Adding or changing a button

The tests force the first two steps: `test_wiring.py` fails until they're done.

1. Add the button in `main.cpp` as usual (see ARCHITECTURE.md §2, *Adding a new script button*).
2. Add it to `BUTTONS` in [tests/buttons.py](../tests/buttons.py): label, kind (`SCRIPT`, `SEQUENCE`,
   `DIALOG`, `INLINE`, `TODO` or `HIDDEN`), the script and arguments, and the test file that covers it.
   Also add its label to `COLUMNS` (the column it sits in, in top-to-bottom order; not for a `HIDDEN` one).
   The app test then clicks it automatically.
3. Write `tests/test_<script>.py` for its logic. Copy the closest existing file:
   - Ark download + process: [test_nai_download.py](../tests/test_nai_download.py) (small) or [test_tpp_lhpp.py](../tests/test_tpp_lhpp.py).
   - Ark with Data Loader upload: [test_cost_to_extend.py](../tests/test_cost_to_extend.py).
   - Offline CSV in / CSV out: [test_case_matchup.py](../tests/test_case_matchup.py).
   - Web API (JSON over HTTP): [test_docket_updates_slack.py](../tests/test_docket_updates_slack.py) (fake server replaces `urlopen`).
4. Run `py -m pytest`.

A typical Ark script test:

```python
def test_writes_the_report(fake_ark, folders):
    fake_ark.serve(my_script._REPORT_URL, [['Id', 'Value'], ['LH-1', '5']])  # what "Ark" returns
    my_script.main()
    rows = read_csv(folders['MyFolderKey'] / 'output.csv')                  # what the script wrote
    assert rows == [['Id', 'Value'], ['LH-1', '5']]
```

**Fixing a bug:** first write a test that fails because of the bug, then fix the code until it passes.
The test then keeps the bug from coming back.

**C++ tests:** add `TEST(name) { CHECK(...); CHECK_EQ(actual, expected); }` to the matching
`tests/cpp/test_*.cpp`. It is picked up automatically. `CHECK_EQ` needs `std::wstring(L"...")` on one
side when comparing strings. A dialog's window can be opened hidden with `OwnerEnabledWhenPopupCloses`
(test_main.cpp): it shows the popup under a disabled stand-in for the launcher, runs your close callback and
returns whether the launcher was enabled again before the popup was destroyed. It unregisters the class
afterwards, since Organize's tests rely on the classify dialog's class not being registered.

**When a test fails after an intentional change** (you changed what a button does on purpose),
update the test's expected values to the new behavior in the same change.

---

## Troubleshooting

- **C++ tests skipped:** Visual Studio isn't at `C:\Program Files\Microsoft Visual Studio\18\Community`.
  Set the `PHX_VCVARS` environment variable to your `vcvars64.bat`.
- **"did not compile":** the message includes the compiler output. A C++ change broke the build.
- **App test times out waiting for the main window:** something blocked the test build from starting
  (for example a Device Guard policy change). Run `py -m pytest -m "not app"` meanwhile.
- **A test left a window open:** the app test kills its test build when it finishes. If you stop a run
  midway, close any leftover `phxcpp.exe` from Task Manager.
