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
   compile Organization, Rename, Settings and Mirror with MSVC into a temp folder and test their logic with
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
| Mirror | [test_mirror.py](../tests/test_mirror.py): step order, carrying on after a failure, report groups, dated archive (appended on a second run), message box, each step in its own process with the 20-minute limit (a hung child and its own child are killed; a crash is reported with its last line), Index step totals, a full run of the real steps against the fake Ark, Stop (stop file read from `--stop-file`, the running child's process tree killed, the rest Not run, a late `@RESULT` kept, the Data Loader note for an uploading step, report still written); each green button's `mirror_step` in its own test file; [test_cpp.py](../tests/test_cpp.py) (`mirror_*`, `run_script_lines_*`, `kill_on_close_job_*`): progress parsing, status, confirmation and Stop text, the command line, output reading, the job holding what the script started and ending it when closed | yes: confirmation (No runs nothing), progress bar and status, Mirror reads Stop while step buttons and PPIQ / AOI / Data Meeting Download are disabled then restored, Stop asks (No keeps running) then ends the run early, buttons come back while the report box is still open, error box if mirror.py stops early, refuses while Index runs |
| PPIQ | [test_ppiq.py](../tests/test_ppiq.py): downloads, both logins, all 4 issue types, folder from `[Folders] PPIQ`, issue-count box | yes |
| Index | [test_index.py](../tests/test_index.py): all 3 counties, skip already-indexed (Richland by name without extension), page counts, Excel append, a backup per county, Divide's BOM, `@PROGRESS`/`@DONE` tags, re-run adds nothing, `main()` returns the count, paths from Settings, missing workbook / workbook open in Excel (before the scan and mid-run) stop with a readable message, shown in a box as a button | yes, with the progress bar and summary counts |
| STR / AOI | [test_str_verification.py](../tests/test_str_verification.py): both checks, padding, AOI numbers matched whole (4 isn't found in 14), `--aoi` picks the report and folder, each folder from its own `[Folders]` key, Mirror step (STR only, mismatch count) | yes |
| TPP-LHPP | [test_tpp_lhpp.py](../tests/test_tpp_lhpp.py): LHT sums, $1 tolerance, export workbook, Close Date message box, Mirror step (only mismatches closing in the next 14 days, unreadable Close Dates flagged, no box) | yes |
| DMD | [test_download_report.py](../tests/test_download_report.py): dated names, login, done box | yes |
| C2E | [test_cost_to_extend.py](../tests/test_cost_to_extend.py): $10 threshold, notes, upload call (faked, Landholdings), Mirror step | yes |
| Settings | [test_cpp.py](../tests/test_cpp.py) (`settings_*`): every row saves and loads, defaults kept, saving one row leaves the rest alone, get/set by key, secrets hidden; Python reads every value C++ writes (a `%` included); [test_wiring.py](../tests/test_wiring.py): every folder/file a script reads has a row | yes, the dialog opens and closes |
| Unit Connect to Cases | [test_case_matchup.py](../tests/test_case_matchup.py): matching rules, notes (a case number counts only whole: C-1 isn't C-14), export, summary | yes |
| Bring out your dead | [test_deceased.py](../tests/test_deceased.py): heir × holding rows, share scaling, same-section holdings kept apart, two runs in one process stay separate, done box | yes |
| Organization | [test_cpp.py](../tests/test_cpp.py) (`organize_*`): parsing, rules (most specific wins), migration, scrubbing, Chase exports → Data.CSV (both layouts, overlap dedupe, card payments dropped, bad header), card payments skipped and refunds offsetting their category, full Data.CSV → Organized.CSV, default rules seeded on a fresh machine but never over learned ones; [test_wiring.py](../tests/test_wiring.py): the committed `default_organize_rules.ini` is valid | no (uses personal files) |
| Rename | [test_cpp.py](../tests/test_cpp.py) (`rename_*`): ID3 read/write, extended-header tags kept verbatim, failed write leaves the MP3 untouched, CSV generate/apply | yes, the dialog opens and closes |
| Cases Unit Names | [test_case_unit_names.py](../tests/test_case_unit_names.py): both downloads, login, exact STR-set match, already-right cases left out, blank unit names, comma-joined names, continuation rows, replaced-name message box and overflow CSV, upload call (faked, Cases dataset), no upload when nothing to fix, session saved on failure, Mirror step (upload count only, no box) | yes |
| Close Date | [test_close_dates.py](../tests/test_close_dates.py): Monday weekend rule, holidays (incl. observed dates), date formats, Deferred, upload call (faked, Landholdings), no upload when nothing closed, Mirror step (no Deferred box) | yes |
| Case Update | [test_case_update.py](../tests/test_case_update.py): date stamping, upload call (faked, Units), no upload when empty, session saved on failure, Mirror step | yes |
| Docket Updates | [test_docket_updates.py](../tests/test_docket_updates.py): workbooks built with openpyxl, RW report from the fake Ark. Reading: ND and MT only (UT / WY / Sheet2 ignored), rows without a case number skipped, numeric case numbers, non-breaking-space blanks, missing workbook / sheet / column boxes, section lines (no part, AL / All, two parts on a line, spaces, lots and names unreadable). Which row wins: latest hearing's rows = sub-cases (same land = one sub-case with several types, one Not in RW row), latest type, latest result with its order details (noted when re-listed later), fill-down Order Number ignored, Docketed for a hearing to come, no status after a past hearing (CONTINUED noted). Status and type mapping; Order Status left on a Dismissed / Docketed case flagged, not blanked. Comparison: every field, dates in either format (uploaded as MM/DD/YYYY; unreadable RW date noted), blanks never overwrite RW, generic ESTABLISH SPACING (and RW's generic made specific), well types by whole section, unreadable sections skipped, sub-cases by land then position, Phoenix cases Not in RW (sub-cases `-k`) and others ignored, Not in workbook (leftover sub-cases; Utah and Roman-numeral ones skipped), continuation rows, report without the new columns. main(): the three CSVs with BOM, summary text, nothing uploaded, report without Record Id, CSV locked by Excel, defaults equal the Settings dialog's | yes |
| Docket Updates Slack *(greyed out)* | [test_docket_updates_slack.py](../tests/test_docket_updates_slack.py) (the old Docket Updates tests, `Slack_` file names): fake Slack API; only her messages, newest first, time IDs unique within a second, paging, thread replies (hers in anyone's thread, broadcasts once), joins skipped, link/`&amp;` cleanup, 429 retry, Slack error / no token / Excel-locked boxes, BOM, default `Desktop\Docket Updates` folder. Case parsing: header variants (missing colons, nested parentheses, struck-out / misspelled status, two numbers), status on the next line, `(N Wells)` groups, states, notes, every section format (W2, S2SE, E2W2, WALL, missing range direction), newest post wins. RW comparison (fake Ark report): status / Order Status / type mapping, section gaps, W2 = NW+SW, groups to sub-cases by sections and by position, Not in RW / Not in message, duplicates, continuation rows; Slack_Not_In_RW.csv (Not in RW rows only, one per missing group, state codes, status in RW terms, sections as written); no Ark download without cases; locked differences / Not in RW CSV | yes, greyed out: a click launches nothing |
| Maps | [test_map.py](../tests/test_map.py): STR parsing, shapes from a fake BLM, one zip per operator, uploader moves zips, operator colors, Enverus login starts from the app URL | yes, build then upload |
| Yellow (TODO) buttons | — | yes, a click does nothing |
| Greyed-out (DISABLED) buttons | [test_wiring.py](../tests/test_wiring.py): `g_disabledButtonIds` matches the spec and the handler still launches the script | yes, shown greyed out and a click (even a `BM_CLICK`) launches nothing |

[test_error_reporting.py](../tests/test_error_reporting.py) also checks that every button script shows an
error box when it fails, naming the error and its log (the scripts have no console, so otherwise failures are
invisible), and that the map scripts name a missing package.
[test_ark_common.py](../tests/test_ark_common.py) tests the Data Loader upload every uploading button shares
(`ark_common.upload`): it picks the dataset asked for, confirms with the operation, and stops at the "X of Y" row counter.
It also checks settings with `%` are read as typed and that `ark_page` keeps the login after an error.

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
- **No dialogs.** Message boxes are recorded instead of shown (`msgboxes` fixture), so a test can check
  what the user would have seen.
- **Never in the repo.** The C++ builds go to a temp folder ([tests/msvc.py](../tests/msvc.py) refuses
  the repo folder), and nothing is launched except the test build with its stand-ins.

---

## Adding or changing a button

The tests force the first two steps: `test_wiring.py` fails until they're done.

1. Add the button in `main.cpp` as usual (see ARCHITECTURE.md §2, *Adding a new script button*).
2. Add it to `BUTTONS` in [tests/buttons.py](../tests/buttons.py): label, kind (`SCRIPT`, `SEQUENCE`,
   `DIALOG`, `INLINE`, `TODO` or `DISABLED`), the script and arguments, and the test file that covers it.
   Also add its label to `COLUMNS` (the column it sits in, in top-to-bottom order).
   The app test then clicks it automatically.
3. Write `tests/test_<script>.py` for its logic. Copy the closest existing file:
   - Ark download + process: [test_download_report.py](../tests/test_download_report.py) (small) or [test_tpp_lhpp.py](../tests/test_tpp_lhpp.py).
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
side when comparing strings.

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
