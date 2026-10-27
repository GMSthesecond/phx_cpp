# Code Index

Every function, global, constant and type, grouped by file. Local variables are left out.
Each entry is also commented in the source. Search the name to find it (no line numbers,
since they go stale). For how the pieces fit together, see [ARCHITECTURE.md](ARCHITECTURE.md).

**Contents**
- C++: [main.cpp](#maincpp) · [mirror.cpp](#mirrorcpp--mirrorh) · [settings.cpp](#settingscpp--settingsh) · [organize.cpp](#organizecpp--organizeh) · [rename.cpp](#renamecpp--renameh) · [csv_text.h](#csv_texth)
- Python (shared): [ark_common.py](#ark_commonpy) · [operator_colors.py](#operator_colorspy) · [mirror.py](#mirrorpy)
- Python (Ark): [ppiq.py](#ppiqpy) · [tpp_lhpp.py](#tpp_lhpppy) · [download_report.py](#download_reportpy) · [cost_to_extend.py](#cost_to_extendpy) · [str_verification.py](#str_verificationpy) · [close_dates.py](#close_datespy) · [non_hbp_mi.py](#non_hbp_mipy) · [case_matchup.py](#case_matchuppy) · [case_unit_names.py](#case_unit_namespy) · [section_id_blank.py](#section_id_blankpy)
- Python (other): [deceased.py](#deceasedpy) · [qq_checker.py](#qq_checkerpy) · [docket_updates.py](#docket_updatespy) · [docket_updates_slack.py](#docket_updates_slackpy) · [doc_inventory.py + county scripts](#doc_inventorypy--doc_inventory_roosevelt--richland--dividepy) · [map_builder.py](#map_builderpy) · [map_uploader.py](#map_uploaderpy)
- [Tests](#tests): shared helpers, C++ test support, test files

---

## C++

### main.cpp
Entry point, main window, button dispatch.
**Reads:** settings.ini via `LoadSettings`. **Launches:** every button script (`LaunchScript`, or the Index / Maps threads). Each button is labeled with the Desktop folder its work goes to.

| Name | Kind | Description |
|---|---|---|
| `ID_TITLE`, `ID_BUTTON_*` | macro | Control ids for the title and each button; grouped by column. `ID_BUTTON_AOI` (11) runs `str_verification.py --aoi`; `ID_BUTTON_DOCKET_UPDATES` (51) runs `docket_updates.py`; `ID_BUTTON_DOCKET_UPDATES_SLACK` (59) runs `docket_updates_slack.py` (bottom of column 1); `ID_BUTTON_SIB` (36) runs `section_id_blank.py` (also a Mirror step); `ID_BUTTON_QQ` (60, bottom of column 4) runs `qq_checker.py`. |
| `ID_PROGRESS_INDEX`, `ID_LABEL_INDEX_STATUS` | macro | Index progress bar and status label (hidden unless Index is running). |
| `ID_BUTTON_MIRROR` (52), `ID_PROGRESS_MIRROR` (53), `ID_LABEL_MIRROR_STATUS` (54) | macro | Mirror button (top-left, outside the columns) and its progress bar / status label (hidden unless Mirror is running; same spot as Index's). |
| `ID_COLUMN_HEADER` (55) | macro | First column-header label id; `ID_COLUMN_HEADER + i` (55-58) is the label over column i + 1. |
| `g_columnHeaders` | constant | Column header texts left to right: Daily, Set Date, As Needed, In Progress (must match `COLUMN_HEADERS` in tests/buttons.py). |
| `g_hTitleFont` / `g_hButtonFont` / `g_hHeaderFont` | global | Title (32px bold), button (13px) and column header (15px semibold) Segoe UI fonts; created in WM_CREATE. |
| `g_hBgBrush` / `g_hYellowBrush` / `g_hGreenBrush` | global | Window background gray; fill for unwired buttons (yellow) and for the buttons Mirror runs (faint green). |
| `g_hwndMain` | global | The main window. |
| `g_unwiredButtonIds` | static global | Buttons with no handler yet; drawn yellow. |
| `IsUnwiredButton` | function | True if the id is in `g_unwiredButtonIds`; makes the button owner-drawn. |
| `g_hiddenButtonIds` | static global | Working buttons that are switched off: created hidden and disabled; remove an id to bring it back. Holds only `0` (no control's id) while none are hidden, since C++ has no empty arrays. |
| `IsHiddenButton` | function | True if the id is in `g_hiddenButtonIds`; WM_CREATE creates those buttons hidden and disabled, and WM_COMMAND ignores them (a `BM_CLICK` still reaches a hidden button). |
| `g_mirrorSteps` | static global | `MirrorStep` table: the buttons Mirror runs, in order, and which upload. Must match `STEPS` in mirror.py (test_wiring checks). |
| `g_lockedDuringMirror` | static global | PPIQ, AOI, DMD: not Mirror steps, but disabled while Mirror runs because their scripts share the Ark login (session.json). test_wiring checks every such button is a step or listed here. |
| `IsMirrorButton` | function | True if the id is in `g_mirrorSteps`; makes the button owner-drawn (green). |
| `GetExeDir` | static function | Folder of phxcpp.exe (and the scripts), with trailing backslash. |
| `LaunchScript` | static function | `py "<exeDir><script>" <args>` with no console window, not waited on; error box if Python can't start. Every one-script button calls it. |
| `MapUploadThreadArgs` | struct | `hwnd` + `exeDir` passed to `RunMapThenUpload`; deleted by the thread. |
| `RunMapThenUpload` | function (thread) | Maps button: runs map_builder.py, waits, then map_uploader.py; relabels the button. |
| `IndexRunThreadArgs` | struct | `hwnd` + `exeDir` passed to `RunIndexScripts`. |
| `RunOneIndexScript` | static function | Runs one doc_inventory script through `RunScriptLines`; finds `@PROGRESS` / `@DONE` anywhere in a line; returns processed count or -1. |
| `RunIndexScripts` | function (thread) | Index button: runs the three county scripts in order, then shows a summary. |
| `LayoutControls` | function | Positions Mirror (top-left), the title, the 4 column headers and columns, and the bottom-right progress controls; called on WM_CREATE and WM_SIZE. |
| `WndProc` | wndproc | Main window messages: create controls, layout, colors, owner-draw (yellow / green, gray text when disabled), button clicks, cleanup. |
| `WinMain` | function | CoInitialize, `LoadSettings`, register window classes, create window, message loop. |

### mirror.cpp / mirror.h
Mirror button: confirmation, then runs mirror.py (in a kill-on-close job) on a background thread and shows its progress;
while it runs the button reads Stop. Also holds `RunScriptLines`, which Index uses too. **Launches:** `mirror.py --stop-file <path>`.
**Files:** creates `%TEMP%\phx_mirror_stop_<pid>_<run>.flag` on Stop (deleted when mirror.py exits). No INI keys.

| Name | Kind | Description |
|---|---|---|
| `MirrorStep` | struct (mirror.h) | `buttonId` + `uploads`; one row of main.cpp's `g_mirrorSteps`. |
| `MirrorProgress` | struct (mirror.h) | Parsed progress: stage `lo`/`hi`, `percent`, `stage` label, `detail`, `finished`, `stopping` (set by `StopMirror`). |
| `RunScriptLines` | function | Runs a command with no window, calls back for each stdout/stderr line; polls so a browser left running by the script can't hang it. Optional job: the process starts suspended and is put in it first. False if it could not start. |
| `CreateKillOnCloseJob` | function | Job object that ends all its processes when its last handle closes (also when the app exits); not inheritable. |
| `MirrorCommand` | function | `py "<exeDir><script>" --stop-file "<stopFile>"`. |
| `MirrorStopConfirmText` | function | Yes/No text for Stop, naming the running step. |
| `ApplyMirrorLine` | function | Applies one `@STAGE lo hi label` / `@PROGRESS done total` / `@FINISHED` line (tag anywhere in the line). |
| `MirrorStatusText` | function | Status label: `Stopping... ` when stopping, stage, detail, `m:ss elapsed`. |
| `MirrorConfirmText` | function | Yes/No text: every step, then the ones that upload to Ark. |
| `StartMirror` | function | Mirror click (no run going): refuse if a step button is busy, confirm, make the stop-file path and job, disable the step buttons and the `alsoLock` buttons (main.cpp's `g_lockedDuringMirror`), relabel Mirror "Stop", show progress, start `RunMirror`. |
| `IsMirrorRunning` | function | True from `StartMirror` until the buttons are restored; main.cpp routes Mirror clicks to `StopMirror` meanwhile. |
| `StopMirror` | function | Stop click: Yes/No (No is the default), then creates the stop file and relabels "Stopping..." (disabled). Does nothing if that run ended while the box was open. |
| `kMirrorTimerId` | constant | Once-a-second timer that refreshes the elapsed time. |
| `kMirrorStopGraceMs` | constant | 30 s: after Stop, mirror.py must reach `@FINISHED` by then or the timer ends its job. |
| `g_mirrorLock` / `g_mirror` / `g_mirrorRunning` / `g_mirrorStart` / `g_mirrorStatus` | static global | Shared run state (guarded by the SRW lock), start tick, status label. |
| `g_mirrorRunId` / `g_mirrorButton` / `g_mirrorStopFile` / `g_mirrorStopAt` / `g_mirrorJob` | static global | For Stop: run counter (a late Yes does nothing), Mirror button, the run's stop file, tick Stop was confirmed (0 = not stopping), the run's job (ended by the timer after the grace period). |
| `MirrorRun` | struct | Window handles, buttons to disable (steps + `alsoLock`), command line, stop file, job and `restored` flag for the worker; deleted by `RunMirror`. |
| `WideFromUtf8` / `EmitLines` / `DrainPipe` / `ClampPercent` / `JoinNames` | static function | Helpers: UTF-8 decode, line splitting, non-blocking pipe read, 0–100 clamp, comma join. |
| `RefreshMirrorStatus` | static function | Puts the latest status text in the label (lock released before `SetWindowText`). |
| `MirrorTimerProc` | static function | Timer callback; ends the job if a Stop isn't honored within `kMirrorStopGraceMs`; kills itself once the run ends. |
| `RestoreMirrorUi` | static function | Hides the progress controls, re-enables the buttons, relabels Mirror; called once per run at `@FINISHED` or when mirror.py exits without it. |
| `RunMirror` | static function (thread) | Runs mirror.py in the run's job, applies its lines, restores the buttons at `@FINISHED` (without waiting for the report box); then closes the job (ending leftovers) and deletes the stop file; error box if it couldn't launch or never reached `@FINISHED`. |

### settings.cpp / settings.h
Settings dialog: one row per folder, file and sign-in the scripts and the Organization / Rename dialogs use.
**Opened by:** Settings. **Reads/Writes:** every `s_settings` row in settings.ini: `[Folders]` (19 keys), `[Files] IndexWorkbook` and `HearingDockets`,
`[Credentials]`, `[EnverusCredentials]`, `[SlackCredentials]` (table in [ARCHITECTURE.md](ARCHITECTURE.md#settingsini)).

| Name | Kind | Description |
|---|---|---|
| `ID_SETTING_VALUE_BASE` / `ID_SETTING_BUTTON_BASE` | macro (settings.h) | Row *i*'s value control is 1000 + *i*, its Change / Save button 2000 + *i*. |
| `SETTINGS_CLASS` | constant | Window class name `"SettingsWindow"`. |
| `s_hwndParent` | static global | Main window, disabled while Settings is open. |
| `s_hwndSettings` | static global | Open Settings window or NULL; prevents duplicates. |
| `SettingKind` | enum | `SETTING_FOLDER` / `SETTING_FILE` (picked), `SETTING_TEXT` / `SETTING_SECRET` (typed; secret shows dots). |
| `Setting` | struct | `section`, `key`, `label`, `kind`, `value` (starts as the default the scripts also use). |
| `s_settings` / `kNumSettings` | static global / constant | Every row, top to bottom, and how many. Add a setting here (test_wiring checks it is read and documented). |
| `GetIniPath` | static function | Builds the settings.ini path; creates the PhoenixLandDept folder. |
| `LoadSettings` | function | Called by WinMain; reads every row. Never writes. |
| `SaveSetting` | static function | Writes one row's key (other keys untouched). |
| `FindSetting` | static function | Row for `[section] key` (case-insensitive) or NULL. |
| `GetSetting` / `SetSetting` | function | Current value of a row ("" if unknown) / change it in memory. Organization and Rename read their folders with `GetSetting`. |
| `PickPath` | static function | COM `IFileDialog` picker for a folder or an `.xlsx`; true on OK. |
| `kRowTop` / `kRowPitch` / `kLabelW` / `kValueX` / `kValueW` / `kButtonX` | constant | Row layout in pixels. |
| `SettingsProc` | wndproc | Builds the rows; Change → `PickPath`, Save → text box; then `SaveSetting`. Typing turns "Saved" back into "Save". Re-enables parent on close. |
| `RegisterSettingsClass` | function | Called by WinMain. |
| `OpenSettings` | function | Called by Settings button; disables parent, shows the popup sized to fit every row. |

### organize.cpp / organize.h
Personal finance categorizer: `<[Folders] Organize>\*Chase*.csv` → `Data.CSV` → `Organized.CSV` (folder default `Desktop\Organization`).
**Opened by:** Organization. **Reads/Writes:** `organize_rules.ini` `[Rules]`, `[ScrubWords]`, `[Meta]`.
**Reads:** `default_organize_rules.ini` next to the exe (committed in the repo), copied to `organize_rules.ini` when that doesn't exist yet.

| Name | Kind | Description |
|---|---|---|
| `NUM_COLS` | constant | 15 output categories. |
| `IGNORE_COL` | constant | 15 = "Ignore" (never written to output). |
| `COLS` | constant | Category names in output order (Income … Savings). |
| `OrgDir` | static function | `[Folders] Organize` (`GetSetting`): folder searched for Chase exports. |
| `DataPath` / `OutputPath` | static function | `Data.CSV` / `Organized.CSV` in `OrgDir()`. |
| `g_rules` | static global | Uppercased snippet → column index. |
| `DefaultRulesPath` | static function | `<exe folder>\default_organize_rules.ini`: the rules committed to the repo. |
| `SeedRulesIfMissing` | static function | Copies the default rules to organize_rules.ini only if it doesn't exist (never overwrites). |
| `GetRulesPath` | static function | Path to organize_rules.ini; seeds it from `DefaultRulesPath()` on a machine that has none. |
| `OLD_TO_NEW_COL_V1` | constant | Old (pre-Briar) column indexes → current. |
| `MigrateRuleColumnsIfNeeded` | static function | Remaps `[Rules]` once if `ColumnSchema < 2`. |
| `LoadRules` | static function | Migrate, then load `[Rules]` (categories 0–14 and Ignore 15) into `g_rules`. |
| `SaveRule` | static function | Writes a new snippet rule to INI and `g_rules`. |
| `ID_CL_*` | macro | Classify dialog control ids (501–504). |
| `ClassifyParams` | struct | One prompt's input (date/desc/amount) and output (result, snippet, done). |
| `g_cp` | static global | Active `ClassifyParams` for `ClassifyProc`. |
| `CLASSIFY_CLS` | constant | Window class `"OrgClassifyDlg"`. |
| `ClassifyProc` | wndproc | Classify dialog: snippet box, category combo, Confirm/Skip. |
| `ClassifyTx` | static function | Shows the classify dialog modally; returns column (or -1) + snippet. |
| `ToUpper` / `TitleCase` | static function | String helpers (`Trim` is in csv_text.h). |
| `g_scrubWords` | static global | Words removed from notes. |
| `LoadScrubWords` | static function | Loads `[ScrubWords]`; writes missing defaults. |
| `EscapeRegex` | static function | Makes a scrub word regex-literal. |
| `ScrubDesc` | static function | Cleans a bank description into a short note. |
| `Date` | struct | y/m/d. |
| `DateLt` / `DateLe` / `DaysInMonth` / `NextDay` | static function | Date math for the day-by-day output. |
| `ParseDate` / `DateKey` / `DateDisplay` | static function | Parse M/D/YYYY or ISO; map key; display text. |
| `ParseAmount` / `FmtAmount` | static function | Currency parse / format (0 → blank). |
| `FindRule` | static function | Column of the longest (most specific) `g_rules` snippet in the description, or -1. |
| `CARD_PAYMENT_SNIPPETS` | constant | Card-payment descriptions (card side "Payment Thank You", autopay; checking side "Payment to Chase card"). |
| `IsCardPayment` | static function | True if a description is a card payment; `RunOrganize` leaves those out. |
| `ReadTextLines` | static function | Reads a UTF-8 file (BOM optional) into lines. |
| `FindTxColumns` | static function | Finds Posting/Post Date, Description, Amount in a header line. |
| `WriteUtf8File` | static function | Writes text as UTF-8 with BOM (Data.CSV, Organized.CSV). |
| `FindChaseFiles` | static function | Sorted names of `.csv` files in `OrgDir()` containing "chase" (any case). |
| `BuildResult` | enum | `BuildDataCsv` outcome: NoChaseFiles / Built / Failed. |
| `BuildDataCsv` | static function | Rebuilds Data.CSV from the Chase exports: date (M/D/YYYY), description, amount only; rows of Type "Payment" (card payments) dropped; overlapping exports not double-counted. |
| `DayRow` | struct | Per-day totals `c[15]` and notes `notes[15]`. |
| `RunOrganize` | static function | Whole pipeline: build Data.CSV from Chase exports (if any), read, categorize (card payments skipped; a positive amount goes to its rule's column, so a refund reduces that category, else Income), accumulate, write. |
| `RegisterOrganizeClass` | function | Called by WinMain. |
| `OpenOrganize` | function | Called by Organization button; runs `RunOrganize`. |

### rename.cpp / rename.h
Bulk file renamer + MP3 artist tag editor, driven by `rename.csv` in `[Folders] Rename` (default `Desktop\Rename`).
**Opened by:** Rename.

| Name | Kind | Description |
|---|---|---|
| `RenameFolder` | static function | `[Folders] Rename` (`GetSetting`). |
| `CSV_NAME` | constant | `rename.csv`. |
| `CsvPath` | static function | Full path of rename.csv. |
| `HasExtension` / `SameNameCI` | static function | Case-insensitive extension / name compare. |
| `ReadWholeFile` | static function | Whole-file byte read. |
| `TEMP_SUFFIX` | constant | `.phxtmp`, suffix of the temp file `WriteWholeFile` writes first. |
| `WriteWholeFile` | static function | Safe whole-file replace: write temp file, then `MoveFileEx` over the original (original untouched on failure). |
| `Synchsafe32` / `EncodeSynchsafe32` / `BigEndian32` / `EncodeBigEndian32` | static function | ID3 integer encodings. |
| `Id3Frame` / `Id3v2Tag` | struct | Raw ID3v2 frame; parsed tag. |
| `ParseID3v2` / `BuildID3v2` | static function | Parse / rebuild an ID3v2.3/2.4 tag; tags with flags 0xF0 (unsync, extended header, experimental, footer) are left verbatim. |
| `DecodeID3Text` / `EncodeID3TextUTF16` | static function | ID3 text frame decode / encode. |
| `ID3V1_SIZE` | constant | 128-byte ID3v1 block. |
| `ReadID3v1Artist` / `ReadMp3Artist` / `WriteMp3Artist` | static function | Read artist (v2 then v1); write new artist to v2 + v1. |
| `WriteUtf8` | static function | Write a wide string as UTF-8. |
| `GenerateCSV` | static function | Button 1: list files and artists into rename.csv, open it. |
| `ApplyRenames` | static function | Button 2: apply renames (`MoveFile`) and artist changes. |
| `ID_RN_*` | macro | Dialog button ids (601–603). |
| `g_renameDone` | static global | Ends `OpenRename`'s modal loop. |
| `RENAME_CLS` | constant | Window class `"RenameDlg"`. |
| `RenameProc` | wndproc | Shows the folder (from Settings), Generate / Apply / Close. |
| `RegisterRenameClass` | function | Called by WinMain. |
| `OpenRename` | function | Called by Rename button; modal dialog loop. |

### csv_text.h
Header-only text / CSV helpers shared by organize.cpp and rename.cpp. Touches no files.

| Name | Kind | Description |
|---|---|---|
| `Trim` | inline function | Strip spaces, tabs, CR, LF from both ends. |
| `SplitCSV` | inline function | One CSV line → fields (quoted fields, `""` escapes, CR dropped). |
| `EscCSV` | inline function | Quote a field if it has a comma, quote or newline. |

---

## Python — shared

### ark_common.py
Imported by every script (settings, message boxes, errors) and by the Ark scripts for the browser.
Standard library only at import (Playwright is imported inside `ark_page` / `login`), so a script can report a missing package.

| Name | Kind | Description |
|---|---|---|
| `_APP_DIR` / `_INI_PATH` | constant | `%APPDATA%\PhoenixLandDept` and its settings.ini. |
| `_SESSION` | constant | session.json (Playwright login state); loaded and saved by `ark_page`. |
| `_CHEVRON_PATH` | constant | SVG path used to find Ark's report dropdown. |
| `UPLOAD_URL` | constant | Ark Data Loader new-upload page, opened by `upload`. |
| `_PREPARING` | constant | Regex for Ark's in-progress notification line ("We'll let you know when your file is ready…", "0–99% Complete"); `trigger_download` waits while any shows. |
| `_POLL_MS` / `_GENERATION_TIMEOUT_MS` | constant | `trigger_download` rechecks the notifications every 5 s and gives up after 10 min. |
| `UPLOAD_ACCEPTED` | constant | Regex for the Data Loader row counter ("X of Y", commas allowed); once it shows Ark has the data, so `upload` stops waiting there. |
| `UPLOADED` / `REVIEW` / `NOTHING` | constant | Mirror result kinds returned by each `mirror_step()` ("Uploaded", "Needs review", "No changes"); also the report's headings. |
| `plural` | function | `'1 unit'` / `'3 units'` (irregular plural optional). |
| `parse_date` | function | Ark report date in one of 4 formats; ValueError otherwise. Used by close_dates and tpp_lhpp. |
| `_read_ini` | private function | settings.ini parsed with `interpolation=None`, so a `%` in a password or path is read as typed. |
| `read_credentials` | function | Ark `(username, password)` from `[Credentials]`. |
| `read_enverus_credentials` | function | Enverus `(identifier, password)` from `[EnverusCredentials]`. |
| `read_slack_token` | function | Slack user token from `[SlackCredentials] token`; KeyError if missing. |
| `read_folder` | function | `[Folders]` value for a key, or the default. |
| `read_setting` | function | Any `[section] key` (e.g. `[Files] IndexWorkbook`), or the default. |
| `notify` | function | Message box with a title (info icon, or e.g. 0x10 = error). Each script's `_notify` calls it with its own title. |
| `run_button` | function | Runs a button script's `main()`; on an error writes the traceback to the script's `*_error.log`, shows "<title> failed: <error>" with the log path, re-raises. Every script's `__main__` uses it. |
| `_PIP_NAMES` | constant | Import name → pip package where they differ (`shapefile` → `pyshp`). |
| `missing_package` | function | For an `except ImportError` guard: box naming the `py -m pip install` command, then exit. Used by the map scripts. |
| `login` | function | Microsoft SSO sign-in, then wait for `success_url`. |
| `needs_login` | function | Page is on the Microsoft / Cloudflare sign-in. |
| `ensure_login` | function | `login` with `[Credentials]` if `needs_login` (PPIQ's domain switch). |
| `ark_page` | context manager | Chromium with the saved session → first URL → `ensure_login` → yields the page; always saves the session and closes the browser on the way out (also after an error). Every Ark script uses it. |
| `trigger_download` | function | Open report → Download → wait `generation_wait_ms` → open notifications → wait while any export there is in progress (`_PREPARING`, every `_POLL_MS`, RuntimeError after `_GENERATION_TIMEOUT_MS`) → pull the newest file; returns Playwright Download. Taking the top file without that wait grabbed an older export (2026-10-21). |
| `check_columns` | function | `check_columns(path, columns, report)`: RuntimeError ("Ark sent a different report than …", naming the columns it got) unless the CSV starts with `columns` (`None` = any name). Used by str_verification, cost_to_extend, non_hbp_mi, case_unit_names, section_id_blank. |
| `upload` | function | Drive the Data Loader wizard to upload a CSV as `dataset` (Landholdings, Units, Cases; whole option name, any capitalization) / `operation` (default Update); waits for `UPLOAD_ACCEPTED`. **Changes live data.** Used by close_dates, cost_to_extend, non_hbp_mi, case_unit_names, section_id_blank. |

### operator_colors.py
Imported only by map_uploader. Persists `<Maps>\operator_colors.json`.

| Name | Kind | Description |
|---|---|---|
| `_PALETTE` | constant | 20 distinct non-red colors, assigned in order. |
| `_RED_LOW_DEGREES` / `_RED_HIGH_DEGREES` | constant | Excluded red hue band (15° / 335°). |
| `_color_file` | private function | Path to operator_colors.json. |
| `load_colors` / `save_colors` | function | Read / write `{operator: (r,g,b)}`. |
| `_generate_color` | private function | Golden-angle hue that skips reds; used when the palette runs out. |
| `_pick_unused_color` | private function | Next unused palette or generated color. |
| `color_for_operator` | function | Existing color or assign a new one. |
| `_is_reddish` | private function | Hue in the red band. |
| `scrub_red_colors` | function | Reassign saved reddish colors; returns changed operators. |

### mirror.py
**Button:** Mirror. Runs each `STEPS` entry quietly in its own child process (`mirror.py --step …`) with a 20-minute limit, and keeps going past failures, hangs and crashes. Launched as `mirror.py --stop-file <path>`: when main.cpp's Stop creates that file, the running step is killed and the rest skipped.
**Writes:** `Mirror MM.DD.YYYY.txt` in `[Folders] MirrorArchive` (default `Desktop\Dailies\Archive`; a second run that day is appended), then shows the report in a message box.

| Name | Kind | Description |
|---|---|---|
| `FAILED` | constant | Result kind for a step that raised, hung or crashed. |
| `STOPPED` / `NOT_RUN` | constant | Result kinds after a Stop: the step that was running ("Stopped partway through", plus a Data Loader note for uploading steps) / the steps skipped. |
| `_GROUPS` | constant | Report section order: Uploaded, Needs review, No changes, Failed, Stopped, Not run. |
| `_ARCHIVE_DEFAULT` / `_RUN_SEPARATOR` | constant | Default archive folder; rule between two runs in one day's file. |
| `_MAX_ERROR` | constant | Longest failure reason kept (200 characters). |
| `_MB_ICONINFORMATION` / `_MB_ICONWARNING` / `_MB_TOPMOST` | constant | Message box flags (warning icon when a step failed or the run was stopped). |
| `STEP_TIMEOUT_S` | constant | 20 min: a step still running then is stopped (whole process tree) and reported as failed. |
| `RUN_IN_CHILD` | global | True: each step in a child process. tests/conftest.py sets False so tests never start real steps. |
| `_RESULT_TAG` | constant | `@RESULT ` line a step's child prints once: `<kind>\t<report line>`. |
| `_STOP_POLL_S` / `_STOP_DRAIN_S` | constant | 0.5 s: how often a running child is checked for a Stop / 5 s: after killing a stopped child, how long to read its remaining output (a late `@RESULT` wins). |
| `_INDEX_COUNTIES` | constant | The Index button's three county scripts, in order. |
| `_stage` | global | `(lo, hi, label)` of the running step's slice of the bar. |
| `_stop_file` | global | Path from `--stop-file` (set by `main`); None = no Stop possible. |
| `stop_requested` | function | True once the stop file exists. |
| `Step` | dataclass | `name` (button label), `run` (→ kind, line), `uploads`. |
| `STEPS` | constant | The steps, in order: Index, Close Date, Case Update, STR, TPP-LHPP, C2E, Cases Unit Names, SIB (named after the buttons). Must match main.cpp's `g_mirrorSteps`. |
| `_begin_stage` | private function | Prints `@STAGE lo hi label` for main.cpp and remembers it. |
| `_error_text` | private function | One-line failure reason (first line + type; `sys.exit` message). |
| `_index_step` | private function | Runs the three counties (a failing one doesn't stop the others); "Added N new documents to the Index sheet (…)". |
| `_run_here` | private function | Runs one step in this process; FAILED on an exception. |
| `_step_command` | private function | `[python, mirror.py, --step, n, lo, hi, label]`. |
| `_kill_tree` | private function | `taskkill /T /F` the child and everything it started (Chromium). |
| `_run_in_child` | private function | Runs a command, passes its lines through (the `@` tags reach main.cpp), returns its `@RESULT`; FAILED "Stopped: still running after N min" past the limit, STOPPED on a Stop (process tree killed), or "stopped without a result (…)" with its last line. |
| `_child_main` | private function | Entry point of a step's child: set the progress slice, run `STEPS[n]`, print one `@RESULT` line. |
| `run_steps` | function | Runs every step with an equal slice of the bar, each via `_run_in_child` (or `_run_here` when `RUN_IN_CHILD` is off); after a Stop the rest are NOT_RUN; `[(name, kind, line)]`. |
| `build_report` | function | Header (start time, duration, "stopped early" after a Stop) + one section per result kind. |
| `_archive_path` / `_save` | private function | Day's report file; append the report to it. |
| `_show` | private function | Final message box. |
| `_stop_file_arg` | private function | The path after `--stop-file` in argv, or None. |
| `main` | function | `main(stop_file)`: run → report → save → `@FINISHED` → message box. `mirror.py --step n lo hi label` runs `_child_main` instead. |

---

## Python — Ark scripts

### ppiq.py
**Button:** PPIQ. **Folder:** `[Folders] PPIQ` (default `Desktop\PPIQ`). **Writes:** 4 report CSVs + `Update_Inverted.csv` there, then a box with the issue count (errors: `ppiq_error.log` + a box).

| Name | Kind | Description |
|---|---|---|
| `_PPIQ_FOLDER` | constant | Output folder from `[Folders] PPIQ`. |
| `_PPIQ_URLS` | constant | (report URL, generation wait ms) × 4; the 4th is on the phoenixenergy.com domain. |
| `_download_files` | private function | `ark_page` on phxcapitalgroup.com; download all 4 reports (30s apart); `ensure_login` on the domain switch. |
| `_run_analysis` | private function | Cross-check the 4 CSVs for price-paid / queue issues; write `Update_Inverted.csv`; returns the issue count. |
| `main` | function | Download → analyse → box with the count and report path. |

### tpp_lhpp.py
**Button:** TPP-LHPP (also a Mirror step). **Folder:** `[Folders] TPPLHPP` (default `Desktop\TPP-LHPP`). **Writes:** `PHX_Price_Paid_Export.xlsx` there, then a message box listing exported offers with a Close Date.

| Name | Kind | Description |
|---|---|---|
| `_notify` | private function | Message box (errors and the Close Date summary). |
| `_OUT_DIR` | constant | Folder from `[Folders] TPPLHPP`. |
| `_REPORT_URLS` | constant | Offers report (15s wait), LHT report (120s wait). |
| `_OFFERS_FILENAME` / `_LHT_FILENAME` / `_EXPORT_FILENAME` | constant | Expected download names; output name. |
| `_MAX_LISTED` | constant | Most offers (25) named in the Close Date message box; the rest are counted. |
| `_SOON_DAYS` | constant | 14: Mirror counts mismatches closing from today through this many days out. |
| `_YELLOW_FILL` | constant | Highlight for exported cells. |
| `_download_files` | private function | Log in and download both reports. |
| `_find_file` | private function | Case-insensitive file lookup in `_OUT_DIR`. |
| `_process_offers` | private function | Offers CSV → `{id: TPP, status, close date}`. |
| `_process_lht` | private function | Sum LHT values per offer. |
| `_export` | private function | Offers where LHT and TPP differ by more than $1 → xlsx; returns exported Ids. |
| `_close_date_message` | private function | Summary text: how many exported offers have a Close Date, listing up to `_MAX_LISTED`. |
| `_closing_soon` | private function | `(soon, unreadable)`: exported offers closing today through `_SOON_DAYS` out, and those whose Close Date can't be parsed. |
| `main` | function | Download → process → export → Close Date message box (skipped when `quiet`); returns `(offers, exported)`. |
| `mirror_step` | function | Mirror: quiet run; Needs review "N price mismatches closing in the next two weeks" (plus "and N with a Close Date Mirror couldn't read"), or Needs review for unreadable dates alone, else No changes. |

### download_report.py
**Button:** DMD. **Folder:** `[Folders] DataMeetingDownload`. Shows a box when done (errors: `download_report_error.log` + a box).

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | `Desktop\DMD`, used when `[Folders] DataMeetingDownload` is unset. |
| `_REPORT_URLS` | constant | The two Data Meeting reports. |
| `_out_dir` | private function | The output folder. |
| `_trigger_and_save` | private function | Download one report; save with today's date in the name. |
| `main` | function | `ark_page`, download both, box saying where they went. |

### cost_to_extend.py
**Button:** C2E (also a Mirror step). **Folder:** `[Folders] CostToExtend`. **Uploads to Ark (Landholdings Update).**

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | `Desktop\C2E`, used when `[Folders] CostToExtend` is unset. |
| `_notify` | private function | Message box (`ark_common.notify`). |
| `_REPORT_URL` | constant | Cost-to-extend report. |
| `_COLUMNS` | constant | The 14 report columns, the 5 that `main` reads by position named; checked by `ark_common.check_columns`. |
| `_to_float` | private function | Currency string → float (blank → 0). |
| `main` | function | Download, check `_COLUMNS`, flag rows where NMA × $/acre is off by more than $10, write CSV, upload (`ark_common.upload`, Landholdings); returns the number fixed. |
| `mirror_step` | function | Mirror: Uploaded "Uploaded fixes for N landholdings", else "No cost to extend errors found". |

### str_verification.py
**Buttons:** STR (no args; also a Mirror step), AOI (`--aoi`). **Folders:** `[Folders] STRVerification` (STR), `[Folders] AOI` (AOI). **Writes:** `Error_Report.csv` (STR) or `AOI MM.DD.YYYY.csv` (AOI), each in its own folder.

| Name | Kind | Description |
|---|---|---|
| `_REPORT_URL` | constant | Ark "Check STR" report. |
| `_INPUT_NAME` | constant | Downloaded report's file name, `Check_STR_(EM)_(Full).csv`. |
| `_COLUMNS` | constant | The 8 report columns `_process` reads by position (7th unread); checked on download. |
| `_OUT_DIR` / `_INPUT_PATH` | constant | STR Verification folder (default `Desktop\STR`); its downloaded report. |
| `_AOI_DIR` / `_AOI_INPUT_PATH` | constant | AOI folder (default `Desktop\AOI`); its downloaded report. |
| `_STR_ERROR_PATH` / `_AOI_ERROR_PATH` | constant | STR Verification report (`Error_Report.csv`, in `_OUT_DIR`); AOI report (`AOI MM.DD.YYYY.csv`, run date, in `_AOI_DIR`). |
| `_download_report` | private function | `trigger_download` (60s wait) → `_AOI_INPUT_PATH` if `aoi`, else `_INPUT_PATH` → `check_columns(_COLUMNS)`. |
| `_has_whole` | private function | Text contains a token as a whole number ("4," not inside "14,"; leading zeros may differ). |
| `_process` | private function | `aoi=False`: `_INPUT_PATH`, Section Name vs S-T-R → `_STR_ERROR_PATH`. `aoi=True`: `_AOI_INPUT_PATH`, AOI containment (`_has_whole`) → `_AOI_ERROR_PATH`. Returns the failure count. |
| `main` | function | `ark_page` → download → `_process(aoi)`; `aoi` defaults to whether `--aoi` was passed. Returns the failure count. |
| `_button` | private function | The STR / AOI button: `main()`, then a box with the count and report path. |
| `mirror_step` | function | Mirror (STR check only): Needs review "N Section Name mismatches: review Error_Report.csv", else "No STR errors found". |
| `_LOG_DIR` | global | Running button's folder (`_AOI_DIR` with `--aoi`, else `_OUT_DIR`); `str_verification_error.log` goes there (defined in `__main__`). |

### close_dates.py
**Button:** Close Date (also a Mirror step). **Folder:** `[Folders] CloseDates`. **Uploads to Ark (Landholdings Update).**

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | `Desktop\Close Date`, used when `[Folders] CloseDates` is unset. |
| `_notify` | private function | Message box (`ark_common.notify`). |
| `_REPORT_URL` | constant | Close-date report. |
| `_nth_weekday` | private function | nth (or last) weekday of a month, for floating holidays. |
| `_holidays` | private function | Office holidays for a year: federal + day after Thanksgiving + Christmas Eve, plus weekend-observed dates. |
| `_is_business_day` | private function | Weekday and not a holiday. |
| `_target_dates` | private function | Every day from the last business day before today through yesterday (Fri–Sun on Monday, further back after a holiday). |
| `main` | function | Download, keep rows closed on the target dates (skip Deferred; its message box only when not `quiet`), write CSV, upload if any rows (`ark_common.upload`, Landholdings); returns the count. |
| `mirror_step` | function | Mirror: quiet run; Uploaded "Uploaded close dates for N landholdings", else "No close dates to upload". |

### non_hbp_mi.py
**Button:** Case Update (also a Mirror step). **Folder:** `[Folders] NonHBPMI`. **Uploads to Ark (Units Update).**

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | `Desktop\Case Update`, used when `[Folders] NonHBPMI` is unset. |
| `_notify` | private function | Message box (`ark_common.notify`). |
| `_REPORT_URL` | constant | Units report. |
| `_COLUMNS` | constant | Report's first columns, Record Id and Updated Date (the one stamped); checked on download. |
| `main` | function | Download, check `_COLUMNS`, stamp today's date on every row, write CSV, upload if any rows (`ark_common.upload`, Units); always saves the session; returns the count. |
| `mirror_step` | function | Mirror: Uploaded "Updated N units to today's date", else "No units to update". |

### case_matchup.py
**Button:** Unit Connect to Cases. **Folder:** `[Folders] CaseMatchup`. **Reads:** `All_Cases.csv` and the units docket CSV. **Writes:** `Case_Matchup_Export.<date>.csv`.

| Name | Kind | Description |
|---|---|---|
| `_notify` | private function | Message box. |
| `_IN_DIR` / `_CASES_PATH` / `_UNITS_PATH` | constant | Folder and the two input CSVs. |
| `_OUTPUT_HEADER` | constant | Export column order. |
| `_DATE_FORMATS` / `_BLANK_STATUSES` | constant | Accepted date formats; statuses meaning "no case yet". |
| `_parse_date` / `_split_list` / `_split_strs` / `_dedup_ordered` / `_dedup_ordered_cases` | private function | Parsing helpers. |
| `_read_cases` | private function | Load cases; classify spacing / density / pooling / other. |
| `_read_units` | private function | Load units (skip rows with no Record Id). |
| `_strs_match` / `_strs_overlap` | private function | Exact vs partial STR match. |
| `_is_denied` / `_is_granted` | private function | Order status checks. |
| `_pick_best` | private function | Best non-denied case: Granted → Phoenix applicant → latest hearing. |
| `_compute_status` / `_status_matches` | private function | Expected unit status vs existing. |
| `_mentions_case` / `_mentions_case_denied` | private function | Docket-note text checks; the case number must appear whole ("C-1" isn't found in "C-14"), any case. |
| `_build_notes` | private function | Rule engine: discrepancy notes for one unit. |
| `_process` | private function | Match cases to units; call `_build_notes`. |
| `_write_output` | private function | Write the export CSV. |
| `main` | function | Read → process → write → summary box. |

### case_unit_names.py
**Button:** Cases Unit Names (also a Mirror step). **Uploads to Ark (Case Update).** **Folder:** `[Folders] CaseUnitNames` (default `Desktop\Cases Unit Names`). **Downloads:** `Units_For_Case_Names.csv`, `Phoenix_Cases_Fixes.csv` (overwritten each run). **Writes:** `Case_Unit_Names.<date>.csv` (Record Id, PHX Unit Name; only matched cases whose name is blank or different, i.e. needs fixing), plus `Replaced_Names.<date>.csv` when more replacements than fit in the message box.

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | Folder used when `[Folders] CaseUnitNames` is unset. |
| `_UNITS_URL` / `_CASES_URL` | constant | The units and cases reports. |
| `_UNITS_FILE` / `_CASES_FILE` | constant | Fixed names the two reports are saved as. |
| `_UNITS_COLUMNS` / `_CASES_COLUMNS` | constant | Each report's columns (Record Id, STRs, Unit Name / Record Id, Applicant, PHX Unit Name, Sections); checked on download. |
| `_OUTPUT_HEADER` | constant | Output columns: Record Id, PHX Unit Name. |
| `_MAX_LISTED` | constant | Replaced cases listed in the message box (30); the rest go to Replaced_Names. |
| `_notify` | private function | Message box. |
| `_split_strs` | private function | STR field → uppercase set (order, case and spacing ignored). |
| `_read_units` | private function | STR set → sorted unit names; skips units with no name or STRs. |
| `_read_cases` | private function | Cases with STRs and existing names; blank-Record-Id rows add names to the case above. |
| `_match` | private function | Exact STR-set match; returns output rows (cases needing a fix), replaced names, unmatched ids, already-correct ids. Several names are comma-joined. |
| `_write_csv` | private function | Write a header + rows CSV. |
| `_summary` | private function | Finish message: counts (matched, already right, to fix), output path, uploaded or nothing to upload, replaced cases (old → new). |
| `main` | function | Log in → download both reports (each checked against its columns) → match → write → upload if any rows (`ark_common.upload`, dataset Cases) → summary box (skipped when `quiet`). Always saves the session; returns the number uploaded. Errors go to `case_unit_names_error.log` + a box. |
| `mirror_step` | function | Mirror: quiet run; Uploaded "Uploaded PHX Unit Names for N cases", else "No case unit names to upload" (no match/replace totals). |

### section_id_blank.py
**Button:** SIB (also Mirror's last step). **Uploads to Ark (Landholdings Update).** **Folder:** `[Folders] SIB` (default `Desktop\SIB`). **Downloads:** `Landholdings_Section_Id_Blank_EM.csv` (landholdings with no Section Id) and `Section_ID_Getting.csv` (every section and its Id), overwritten each run. **Writes:** `Section_Id_Upload.<date>.csv` (Id, Section Name, Section Id; one row per landholding whose Section Name is exactly one section).

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | Folder used when `[Folders] SIB` is unset. |
| `_BLANK_URL` / `_SECTIONS_URL` | constant | The Landholdings Section Id Blank EM and Section ID Getting reports. |
| `_BLANK_FILE` / `_SECTIONS_FILE` | constant | Fixed names the two reports are saved as. |
| `_BLANK_COLUMNS` / `_SECTIONS_COLUMNS` | constant | Each report's first columns (Id, Section Name, Section Id / Section: Id, Section Name); checked on download. |
| `_OUTPUT_HEADER` | constant | Output columns: Id, Section Name, Section Id. |
| `_MAX_LISTED` | constant | Ambiguous section names listed in the message box (20). |
| `_notify` | private function | Message box. |
| `_key` | private function | Section Name as compared: uppercase, spaces collapsed. |
| `_read_sections` | private function | Section name → set of section Ids; skips rows with no Id or name. |
| `_read_blank` | private function | (Id, Section Name) of landholdings still missing a Section Id; skips rows with no Id or name, or a Section Id already. |
| `_match` | private function | Returns output rows, unmatched landholding ids (no section of that name) and ambiguous names (more than one section Id; left out). |
| `_write_csv` | private function | Write `_OUTPUT_HEADER` + rows. |
| `_summary` | private function | Finish message: found/total, output path, uploaded or nothing to upload, unmatched count, ambiguous names. |
| `main` | function | Log in → download both reports (each checked against its columns) → match → write → upload if any rows (`ark_common.upload`, dataset Landholdings) → summary box (skipped when `quiet`). Always saves the session; returns (number uploaded, ambiguous names). Errors go to `section_id_blank_error.log` + a box. |
| `mirror_step` | function | Mirror: quiet run; Uploaded "Uploaded Section Ids for N landholdings" (plus the ambiguous count if any), Needs review when there are only ambiguous names, else "No blank Section Ids to fill in". |

---

## Python — other

### docket_updates.py
**Button:** Docket Updates. **Folder:** `[Folders] DocketUpdates` (default `Desktop\Docket Updates`). **Reads:** the ND and
MT sheets of the Hearing Dockets workbook (`[Files] HearingDockets`, default `_DEFAULT_WORKBOOK` in Box) and the Ark RW
cases report (`_REPORT_URL`, saved as `RW_Case_Info.csv`). **Writes:** `Docket_Differences.csv` (`_DIFF_HEADER`: each
workbook case / sub-case next to its RW record, Result = Match / Differs / Not in RW / Not in workbook),
`Docket_Upload.csv` (Record Id + the compared columns the report has, one row per record with a difference the upload
can fix, dates as MM/DD/YYYY, for a Cases Update by hand) and `Not_In_RW.csv` (`_MISSING_HEADER`); all overwritten each run. Read-only on Box and Ark: nothing
is uploaded. Rules: [ARCHITECTURE.md](ARCHITECTURE.md#docket-updates-comparison).

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | `Desktop\Docket Updates`; output folder when `[Folders] DocketUpdates` is unset. |
| `_DEFAULT_WORKBOOK` | constant | The Hearing Dockets workbook in Box; used when `[Files] HearingDockets` is unset. |
| `_SHEETS` | constant | Sheets compared: ND, MT. UT, WY and Sheet2 are left out for now (KNOWN_ISSUES). |
| `_WB_COLUMNS` / `_OPTIONAL_WB` | constant | Field → workbook header (Case No., Case Type, Operator, Proposed Spacing Unit, Hearing Date, State, County, Order Status, Order Number, Date Order Signed) / the ones that may be missing (State, County). |
| `_PHOENIX` | constant | An Operator containing "phoenix" puts a case in scope even when RW lacks it. |
| `_REPORT_URL` / `_REPORT_FILE` | constant | Ark RW cases report and its saved name `RW_Case_Info.csv`. |
| `_FIELDS` / `_DATE_FIELDS` / `_REQUIRED_RW` | constant | Compared fields, named as report columns and Data Loader fields (Case Status, Order Status, Case Type, Sections, Hearing Date, Order Number, Date Order Signed) / the two compared as dates / the columns the run can't do without (Record Id, Case Number). |
| `_UTAH_NUMBER_RE` | constant | Utah case numbers (`2026-027-15`), left out of Not in workbook while UT isn't read. |
| `_DIFF_FILE` / `_DIFF_HEADER` | constant | `Docket_Differences.csv` and its columns (Result, Differences, numbers, Record Id, Sheet, Rows, State, County, Group, Operator / Applicant, Workbook / RW pair of each field, Missing from RW, Extra in RW, Notes). |
| `_MATCH` / `_DIFFERS` / `_NOT_IN_RW` / `_NOT_IN_WORKBOOK` | constant | Result values. |
| `_UPLOAD_FILE` | constant | `Docket_Upload.csv`, the Cases Update file (not uploaded). |
| `_MISSING_FILE` / `_MISSING_HEADER` | constant | `Not_In_RW.csv` and its columns (Case Number, State, Applicant, then `_FIELDS`). |
| `_STATUS_RE` / `_EXPECTED_STATUS` / `_DOCKETED` | constant | Results found in Order Status (GRANTED, PARTIALLY GRANTED, DENIED, DISMISSED, DIMISSED, WITHDRAWN) and the RW Case Status / Order Status each means; Docketed for no result and a hearing still to come. |
| `_FILL_DOWN_CASES` | constant | An Order Number on more cases than this (50) is a fill-down slip and is ignored. |
| `_PREFIX_RE` / `_TYPE_MAP` | constant | "(Continued)" prefix / workbook Case Type (uppercase) → RW Case Type. Edit `_TYPE_MAP` to change the mapping. |
| `_SPACING_TYPES` / `_TYPE_FAMILIES` | constant | RW spacing types / workbook types that also match a family of RW types (Establish Spacing → any spacing type). One way only: RW's generic Establish Spacing against a specific workbook type differs, so the upload makes RW specific (intended). |
| `_WELL_TYPES` | constant | Types whose workbook unit is the well's quarter-quarter (SWD, Commingling, Show Cause, Permit Protest, Recompletion Certification): sections compared whole. |
| `_WB_SECTION_RE` / `_RW_SECTION_RE` / `_PART_RE` / `_QUARTERS` | constant | Workbook section line (`24-160N-90W-ALL`), RW section (`NW-11-156N-91W`), one aliquot step, quarter corners in the 4×4 grid. |
| `InputError` | class | Workbook or report unusable (missing, locked, a sheet or column gone); its text is shown as is. |
| `_notify` / `_write_csv` | private function | Message box titled Docket Updates / CSV as UTF-8 with BOM. |
| `_text` / `_date` / `_fmt_date` / `_order_number` | private function | Cell → trimmed text (non-breaking-space placeholders blank) / date or None / MM/DD/YYYY / Order Number text (a date typed there is blank). |
| `_part_cells` / `_section_key` | private function | Quarter-quarter cells of an aliquot (None if unreadable) / section name as RW writes it. |
| `_workbook_cells` | private function | Cells + unreadable lines of a Proposed Spacing Unit cell (one section per line; no part = ALL; lots unreadable). |
| `_rw_cells` / `_section_order` / `_describe` / `_whole_sections` | private function | Cells of an RW Sections value / sort key / RW-style text for cells / every cell of each section touched. |
| `_status` / `_rw_type` | private function | Result in an Order Status cell / RW type for a workbook type (None = not compared). |
| `_read_sheet` / `_read_workbook` | private function | Rows of one sheet as dicts (case-numbered rows only, Excel row numbers kept) / all `_SHEETS`; raise InputError when something is missing. |
| `_group` / `_groups` / `_fill_down_numbers` | private function | One sub-case from its row(s), with the RW types of their Case Types / one hearing's rows as sub-cases, rows with the same land merged (one case, several reliefs) / Order Numbers on more than `_FILL_DOWN_CASES` cases. |
| `_cases` | private function | One case per sheet + number with the row-choice rules (latest hearing's rows = sub-cases, same land merged, latest type, latest recognized result with its order details, else Docketed / not compared) and notes. |
| `_read_rw` | private function | RW report rows + cells (continuation rows add Sections) and which `_FIELDS` columns exist; InputError without Record Id / Case Number. |
| `_candidates` / `_pair` | private function | RW records for a case number and its sub-cases / groups ↔ records: same land, then `<n>-k`, then a lone group takes the rest. |
| `_wanted` / `_same` / `_is_well` / `_differences` | private function | Values the workbook says RW should have (blank = not compared), plus Other Types and Blank Order Status / one field agrees / either side a `_WELL_TYPES` type / fields that disagree (a type matching any of the group's types agrees; an Order Status that should be blank but isn't differs). |
| `_pair_notes` / `_rw_value` | private function | Notes for one pairing (RW date not read; Order Status to clear by hand) / RW's own value for the upload, readable dates as MM/DD/YYYY. |
| `_compare` | private function | Comparison rows, upload rows (workbook value where different, RW's own elsewhere; none for a record whose only difference is an Order Status to blank), Not in RW rows, counts and cases compared; scope = in RW or Phoenix. |
| `_rw_only` | private function | A Not in workbook row for an RW record. |
| `_summary` | private function | Finish box: counts, records to update, fields the report lacks, file paths. |
| `main` | function | Workbook → download RW report → compare → write the three CSVs → summary; own boxes for an unusable workbook / report and a CSV locked by Excel. `today` is for tests. Other errors go to `docket_updates_error.log` + a box. |

### docket_updates_slack.py
**Button:** Docket Updates Slack (bottom of column 1; the Slack version of Docket Updates, which reads the Hearing Dockets workbook since 2026-10-16).
**Folder:** `[Folders] DocketUpdates` (default `Desktop\Docket Updates`). **Reads:** Slack Web API
(`conversations.history`, `conversations.replies`) with `[SlackCredentials] token`; then, when the messages hold any
case, the Ark RW cases report (`_REPORT_URL`, saved as `Slack_RW_Case_Info.csv`). **Writes:** `Slack_Docket_Updates.csv`
(ID, Date, Time, Message, Reply To, Slack TS, Link; newest first) and `Slack_Docket_Differences.csv` (`_DIFF_HEADER`: each
case / well group next to its RW record(s), Result = Match / Differs / Not in RW / Not in message) and `Slack_Not_In_RW.csv`
(`_MISSING_HEADER`: the Slack side of every Not in RW row); all overwritten each run. The `Slack_` prefix keeps them apart
from Docket Updates' files in the same folder. Read-only on Slack and Ark.

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | `Desktop\Docket Updates`; output folder when `[Folders] DocketUpdates` is unset. |
| `_CHANNEL_ID` / `_USER_ID` | constant | Slack ids of #docket-updates and Cheyanne Winn. |
| `_WORKSPACE_URL` / `_API_URL` | constant | Permalink base (phxenergy.slack.com) and Web API base. |
| `_PAGE_SIZE` | constant | Messages per request (200). |
| `_MAX_RETRIES` | constant | Retries per request after HTTP 429 (5). |
| `_KEPT_SUBTYPES` | constant | Message kinds exported (plain, thread broadcast, file share, /me); joins etc. skipped. |
| `_OUTPUT_FILE` / `_OUTPUT_HEADER` | constant | `Slack_Docket_Updates.csv` and its columns. |
| `_LINK_RE` | constant | Slack link markup `<url\|label>` / `<url>`. |
| `_NO_TOKEN_HELP` | constant | Setup steps shown when there is no token. |
| `_REPORT_URL` / `_REPORT_FILE` | constant | Ark RW cases report (Record Id, Applicant, Case Number, Case Status, Case Type, Sections; Order Status if added) and its saved name `Slack_RW_Case_Info.csv`. |
| `_DIFF_FILE` / `_DIFF_HEADER` | constant | `Slack_Docket_Differences.csv` and its columns (Result, Differences, both sides of each field, Missing from RW, Extra in RW, Notes, Link). |
| `_MATCH` / `_DIFFERS` / `_NOT_IN_RW` / `_NOT_IN_MESSAGE` | constant | Result values. |
| `_MISSING_FILE` / `_MISSING_HEADER` | constant | `Slack_Not_In_RW.csv` and its columns (Case Number, State, Applicant, Case Type, Case Status, Order Status, Sections). |
| `_STATE_CODES` | constant | US state name (title case, as the state heading reads) → postal code (`North Dakota` → `ND`), for `Slack_Not_In_RW.csv`. |
| `_SPACING_TYPES` | constant | The five Establish … Spacing RW types. |
| `_TYPE_RULES` | constant | Slack case type pattern → RW Case Types that match (None = not compared). POOLING and SPACING in either order or joined any way (`and`, `&`, `/`) count as Pooling and Spacing. Edit here to change the mapping. |
| `_STATUS_RE` / `_EXPECTED_STATUS` | constant | Board results found in a Slack status, and the RW Case Status / Order Status each one should show (GRANTED, PARTIALLY GRANTED, DENIED = Ordered; DISMISSED = Dismissed). |
| `_HEADER_RE` / `_STATE_RE` / `_BOARD_RE` / `_WELLS_RE` | constant | Line patterns: case header, state heading (`NORTH DAKOTA:`), message heading, `(4 Wells)` group line. |
| `_SECTION_RE` / `_RW_SECTION_RE` / `_PART_RE` | constant | Slack section line (`11-156N-91W-W2`), RW section (`NW-11-156N-91W`), one aliquot step (`NE`, `W2`). |
| `_QUARTERS` | constant | Quarter names and their corner in the 4×4 quarter-quarter grid. |
| `SlackError` | class | Slack answered `ok: false`. |
| `_notify` | private function | Message box. |
| `_call` | private function | One API GET with the token; waits Retry-After and retries on 429; raises SlackError on `ok: false`. |
| `_paged` | private function | Yields every message of a call, following `next_cursor`. |
| `_is_hers` | private function | Sent by `_USER_ID` and a kept subtype. |
| `_fetch_messages` | private function | Her posts from history plus her replies in every thread; keyed by ts so broadcasts appear once. |
| `_clean_text` | private function | Links → label / url, `&amp;` `&lt;` `&gt;` decoded. |
| `_sent_at` | private function | Local datetime of a ts. |
| `_message_id` | private function | `YYYYMMDD-HHMMSS-ffffff` from local send time + Slack's microseconds. |
| `_permalink` | private function | Message link; replies open in their thread. |
| `_rows` | private function | CSV rows newest first; Reply To = parent's ID. |
| `_write_csv` | private function | Header + rows, UTF-8 with BOM (Excel-friendly). |
| `_part_cells` | private function | Quarter-quarter cells an aliquot covers (ALL, W2, NE, S2SE, E2W2…); None if unreadable. |
| `_section_key` | private function | Section name as RW writes it (`11-156N-91W`). |
| `_slack_section` | private function | Cells + remarks of a Slack section line; a missing range direction is W outside Montana. |
| `_rw_cells` | private function | Cells of an RW Sections value; unreadable entries kept as their own cell. |
| `_section_order` / `_describe` | private function | Sort by township, range, section / RW-style text for cells (whole section, quarter, quarter-quarter). |
| `_status` | private function | GRANTED / PARTIALLY GRANTED / DISMISSED / DENIED in a status; ignores `~struck~` text, reads GARNTED. |
| `_rw_types` | private function | RW types matching a Slack type via `_TYPE_RULES`. |
| `_parse_header` | private function | Number(s), applicant (nested parentheses OK), type, status, status as written (`status_text`) and notes of a `Case …` line. |
| `_group` / `_parse_message` | private function | New well group / cases of one message with state, well groups and notes. A header with no status takes one only from the first non-blank line below it. |
| `_has_info` | private function | A post of a case has a status or sections (a bare mention has neither). |
| `_fill_blanks` | private function | Copies the status, type, applicant and sections a post leaves blank from an older post of the same case; an unrecognized status as written isn't blank. Returns the fields copied. |
| `_cases_from` | private function | Cases of all messages. Posts sharing any case number are one case; the newest post with a status or sections wins (a bare mention never does) and its blanks are filled from the newest older post that has them (noted as "Sections from the … post"); the other posts are noted, and all their numbers are looked up. |
| `_read_rw` | private function | RW report rows + cells; blank-Record-Id rows add Sections to the case above; whether Order Status exists. |
| `_candidates` | private function | RW records for a case number and its sub-cases. |
| `_pair` | private function | Well groups ↔ RW records: same sections, then position (`<n>-k`), then a lone group takes the rest. |
| `_differences` | private function | Status / Order Status / Type / Sections that disagree. |
| `_rw_fields` / `_compare` | private function | RW columns of a row / all comparison rows + Result counts; unpaired plain sub-cases become Not in message (Roman-numeral field-rules ones are skipped). |
| `_missing_rows` | private function | `Slack_Not_In_RW.csv` rows from the comparison rows: Not in RW only, state as postal code (unknown kept as is), Slack result as RW Case Status / Order Status via `_EXPECTED_STATUS` (blank when none), sections as written in Slack. |
| `_summary` / `_compare_summary` | private function | Finish message parts: Slack count, date range, path / comparison counts, differences and Not in RW paths. |
| `main` | function | Token → fetch → write messages → (if any case) download RW report → compare → write differences and Not in RW → summary; own boxes for no token, Slack errors and a CSV locked by Excel. Other errors go to `docket_updates_slack_error.log` + a box (titled Docket Updates Slack). |

### deceased.py
**Button:** Bring out your dead. **Folder:** `[Folders] Deceased` (default `Desktop\Bring out your dead`).
Reads the deceased account CSV and `heir_template.csv`; writes `deceased_upload.csv`, splitting each holding by heir share,
then shows a box with the row count (errors: `deceased_error.log` + a box).

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | Folder used when `[Folders] Deceased` is unset. |
| `_DECEASED_FILE` / `_HEIR_FILE` / `_OUTPUT_FILE` | constant | Input export, heir template, output file names. |
| `_folder` | private function | The working folder. |
| `main` | function | Read both inputs, cross every heir with every holding, write the CSV, box; returns the row count. Its locals `deceased` / `heirs` / `user_heirs` hold the holdings, output rows and heirs. |

### qq_checker.py
**Button:** QQ (bottom of column 4; not a Mirror step). **Folder:** `[Folders] QQ` (default `Desktop\QQ`). **Reads:**
`QQ_Checker.csv` (Ark landholdings export saved there by hand; UTF-8 or Windows-1252). **Writes:** `QQ_Mismatches.<date>.csv`
(UTF-8 with BOM): Id, Tract Description, Quarter Section, State, Title Source, Mismatch, Note, QQs With Values, Values
Outside Tract, Tract QQs Without Values, Expected Quarter Section; one row per landholding failing either check. A
quarter-quarter has a value when its NMA cell is nonzero. Tract Description must name exactly those quarter-quarters (a
partial one such as E2SWNE counts as whole); Quarter Section must cover exactly the quarters holding them, in any wording.
Then a box with the counts (errors: `qq_checker_error.log` + a box). Local files only.

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | Folder used when `[Folders] QQ` is unset. |
| `_INPUT_FILE` | constant | `QQ_Checker.csv`, the export to check. |
| `_QQS` / `_QUARTERS` | constant | The 16 quarter-quarters in the export's column order; quarter order for a written Quarter Section. |
| `_REQUIRED_COLUMNS` / `_OUTPUT_HEADER` | constant | Columns the export must have; columns of the output CSV. |
| `_TERM` / `_ALIQUOT` / `_SINGLE` / `_SEPARATORS` | constant | Regexes: one aliquot step (NE, N2), a whole aliquot, a lone step (joins the next word), tract separators (`, ; &` and AND). |
| `TRACT` / `QUARTER_SECTION` / `BOTH` / `UNREADABLE` | constant | Mismatch column values. Unreadable wins when either field can't be read. |
| `NOTE_*` | constant | Note column texts, one per kind of problem (tract: part of a quarter, other quarter, named with no value, both ways, blank, unreadable; Quarter Section: leaves out, extra, wrong, blank, unreadable; no values at all). Tract and Quarter Section notes are joined with `; `. |
| `_folder` / `_notify` | private function | The working folder; message box titled "QQ Checker". |
| `_normalize` | private function | Uppercase; fraction notation to plain aliquots (N12 → N2, SE14 / SE4 → SE). |
| `aliquot_qqs` | function | Quarter-quarters one aliquot touches (steps applied right to left on a 4×4 grid), or None if it isn't one. |
| `_cell` / `_overlaps` | private function | A quarter-quarter's corner on the grid; whether it overlaps a box. |
| `description_qqs` | function | Quarter-quarters (frozenset) a Tract Description or Quarter Section names, or None if any word isn't an aliquot. Two lone steps side by side join ("NE NW" = NENW); cached per text. |
| `_quarters` | private function | Quarters holding a set of quarter-quarters. |
| `quarter_section` | function | Shortest Quarter Section for a set of quarters (N2/S2 preferred, then E2/W2; `NW,NE,SE,SW` for all four). |
| `_has_value` | private function | NMA cell holds interest: nonzero number or other non-blank text. |
| `_list` | private function | Quarter-quarters as text in column order. |
| `_tract_note` / `_qs_note` | private function | Note for each check, or '' when it passes. |
| `check_row` | function | Check one export row (dict); returns the output row or None. |
| `_read_rows` | private function | Export rows as dicts; RuntimeError naming any missing required column. |
| `_summary` | private function | Box text: rows checked, mismatches by kind, output path. |
| `main` | function | Check every row, write the CSV (header only if nothing fails), box; returns (rows checked, output rows). RuntimeError if the export is missing. |

### doc_inventory.py / doc_inventory_roosevelt / richland / divide.py
**Button:** Index (the three county scripts, in that order; also Mirror's Index step). Each county script is a thin
wrapper (`COUNTY`, `main()`, `__main__` → `run_button`); the work is in doc_inventory.py. Scans Box county folders for
PDFs not yet in the index workbook (`[Files] IndexWorkbook`); writes `<[Folders] Index>\<County>.csv` and appends rows to
the county tab, after backing the workbook up as `<workbook>.<County>.bak`.

| Name | Kind | Description |
|---|---|---|
| `_BOX_IMAGES` | constant | Box Drive root of the county image folders. |
| `_DEFAULT_INDEX_DIR` / `_DEFAULT_WORKBOOK` | constant | Defaults for `[Folders] Index` / `[Files] IndexWorkbook`. |
| `EXCEL_COLUMN_INDEX` / `FOLDER_NAME_MODE` / `PDF_ONLY` | constant | Filename column (A); Folder column source; PDFs only. |
| `County` | dataclass | `name` (tab + CSV), `roots`, `match_stem` (Richland: names without extension), `precount` (percentage bar vs running tally), `csv_bom` (Divide). |
| `ROOSEVELT` / `RICHLAND` / `DIVIDE` | constant | The three counties. Each wrapper's `COUNTY` points at one. |
| `_images` | private function | A folder under `_BOX_IMAGES`. |
| `output_csv` / `workbook_path` | function | The county CSV path; the workbook path. |
| `win_long` | function | Add the `\\?\` long-path prefix. |
| `_key` | private function | Name as compared: trimmed, lower-cased, stem only if `match_stem`. |
| `_stop_if_open_in_excel` | private function | `sys.exit("Close … in Excel")` before the scan if the workbook is locked. |
| `load_indexed_names` | function | Names already in the tab. Missing openpyxl / workbook / tab: `sys.exit(message)`. |
| `iter_files` | function | `os.walk` generator. |
| `_wanted` | private function | A PDF not already indexed. |
| `count_files_to_process` | function | Pre-count for the percentage bar. |
| `Progress` | class | Throttled printer; emits `@PROGRESS done total` (total -1 for a running tally). |
| `get_pdf_page_count` | function | PyPDF2 page count, or a status string. |
| `folder_label_for_path` | function | Folder column value. |
| `backup_path` | function | `<workbook>.<County>.bak`. |
| `append_rows_to_excel` | function | Back up, append rows, save; `sys.exit` saying the rows are in the CSV if Excel opened the workbook mid-run. |
| `run` | function | One county: scan, write CSV, print `@DONE n`, append to Excel; returns n. |
| `run_button` | function | `run` as the Index button runs it: a stop or error shows a box titled "Index (<County>)" (`index_<county>_error.log`). |

### map_builder.py
**Button:** Maps (step 1). **Folder:** `[Folders] Maps`. Reads `Units.csv`; queries BLM PLSS; writes `YYYY.MM.DD. <Operator>.zip` shapefiles. A missing requests / pyshp / shapely shows which to install (`ark_common.missing_package`); errors: `map_builder_error.log` + a box.

| Name | Kind | Description |
|---|---|---|
| `_MAPS_DIR` / `_UNITS_CSV` | constant | Maps folder; input CSV. |
| `_BLM_TOWNSHIP_URL` / `_BLM_SECTION_URL` / `_BLM_INTERSECTED_URL` | constant | BLM PLSS layers 1/2/3. |
| `_QUARTERS` / `_HALF_TO_QUARTERS` / `_VALID_ALIQUOTS` | constant | Aliquot vocab. |
| `_STR_RE` | constant | Regex for one STR token. |
| `_PRJ_WKT` | constant | .prj projection text. |
| `_SERIAL_DATE_EPOCH` / `_INVALID_FILENAME_CHARS` / `_MAX_NEIGHBOR_METERS` | constant | Serial date base; filename sanitizer; 50 km meridian-stitch limit. |
| `_FIELD_SPECS` | constant | DBF field definitions. |
| `_state_meridian_cache` | global | Memo of meridians per state. |
| `_qq_labels_for` | private function | Aliquot → quarter-quarter labels. |
| `_meridians_for_state` | private function | BLM query for a state's meridians. |
| `_notify` | private function | Message box. |
| `_parse_serial_date` / `_parse_int` / `_sanitize_filename` / `_row_label` | private function | Small parsers/helpers. |
| `_frstdivid` | private function | BLM section id from STR + meridian. |
| `_parse_strs` | private function | Unit STRs field → components. |
| `_fetch_by_ids` / `_fetch_aliquot_polygons` / `_fetch_all_section_pieces` | private function | BLM geometry fetchers. |
| `_pieces_in_aliquot` | private function | Assign lot pieces to a half/quarter by centroid. |
| `_fetch_all_meridians` | private function | Resolve every component under every meridian. |
| `_resolve_unit` | private function | Choose meridian(s) for a unit; returns (polys, missing). |
| `_polygon_to_parts` | private function | Shapely polygon → pyshp rings. |
| `_build_shapefile` | private function | Write .shp/.shx/.dbf/.prj/.cpg for one operator. |
| `main` | function | CSV → geometry → one zip per operator → summary. |

### map_uploader.py
**Button:** Maps (step 2). Uploads the dated zips to Enverus, colors each layer, saves the "Phoenix Units" workspace,
then moves the uploaded zips to `Maps\Uploaded`. A missing Playwright shows which to install; errors: `map_uploader_error.log` + a box.

| Name | Kind | Description |
|---|---|---|
| `_MAPS_DIR` | constant | Where map_builder leaves zips. |
| `_UPLOADED_DIR` | constant | `Maps\Uploaded`; successfully uploaded zips are moved here so they aren't re-uploaded. |
| `_APP_URL` | constant | DI map app; opened signed out, it redirects to a fresh Enverus sign-in page. |
| `_LOGIN_HOST` | constant | `login.auth.enverus.com`, the sign-in site `_login` waits to leave. |
| `_NAME_PATTERN` | constant | `YYYY.MM.DD. Operator` zip naming. |
| `_WORKSPACE_NAME` | constant | `"Phoenix Units"`. |
| `_notify` | private function | Message box. |
| `_zip_layer_name` / `_operator_from_layer_name` | private function | Zip → layer name → operator. |
| `_login` | private function | Enverus two-step login, started from `_APP_URL` (no captured sign-in link to expire). |
| `_open_map_layers` | private function | Open DI and the Layer Manager. |
| `_set_fill_color` | private function | Set a layer's RGB fill. |
| `_upload_one` | private function | Upload one zip, color it, enable it. |
| `_save_workspace` | private function | SAVE or SAVE AS the workspace. |
| `main` | function | Colors → login → upload all → save workspace → move to Uploaded → summary. |

---

## Tests

Regression tests in `tests/`, run with `py -m pytest` (see [TESTING.md](TESTING.md)).
Shared helpers are listed in full. Test files are listed by what they cover, not by each test
function, since every test has a docstring.

### Config and entry points

| Name | Kind | Description |
|---|---|---|
| `pytest.ini` | config | `testpaths = tests`, repo root on `sys.path`, `xfail_strict`, markers `cpp` and `app`. |
| `.vscode/settings.json` | config | Turns on pytest in the VS Code Testing panel. |
| `.vscode/tasks.json` | config | Tasks "Run all tests" (default, Ctrl+Shift+B) and "Run quick tests (Python only)". |
| `run_tests.bat` | script | Installs pytest if missing, runs the tests, pauses. |

### tests/conftest.py
Loaded first by pytest. At import it blocks the browser, the network and message boxes, points `ark_common` at a fake settings.ini, and sets `mirror.RUN_IN_CHILD = False` so Mirror never starts real steps in child processes.

| Name | Kind | Description |
|---|---|---|
| `REPO` | constant | Repo root. |
| `SANDBOX` | constant | Session temp folder: fake `%APPDATA%\PhoenixLandDept`, `[Folders]` targets and the `[Files] IndexWorkbook` / `HearingDockets` paths (never the real Box files). |
| `FOLDER_KEYS` | constant | Every `[Folders]` key (must match the Settings rows; test_wiring checks); each gets a sandbox folder in the fake INI (which also holds fake `[Credentials]`, `[EnverusCredentials]`, `[SlackCredentials]` and `[Files] IndexWorkbook` / `HearingDockets`). |
| `_blocked_sync_playwright` / `_blocked_connect` / `_blocked_getaddrinfo` / `_fake_messagebox` | private function | Installed over Playwright, `socket.connect`, `socket.getaddrinfo` (DNS) and `MessageBoxW`. |
| `_MSGBOXES` | global | Recorded message boxes. |
| `msgboxes` | fixture | List of `(title, text)` the script tried to show. |
| `Folders` / `folders` | class / fixture | Replaces `ark_common.read_folder` so each key maps to `tmp_path/<key>`. |
| `fake_ark` | fixture | Installs a `fakes.FakeArk`. |
| `no_real_makedirs` | fixture | Makes `os.makedirs` a no-op (for scripts run as buttons in test_error_reporting). |

### tests/fakes.py

| Name | Kind | Description |
|---|---|---|
| `write_csv` / `read_csv` | function | Write / read a CSV as lists of rows. |
| `FakeArk` | class | Fake Ark + Playwright: `serve(url, rows, filename)`; records `downloads`, `logins`, `sessions_saved`, `waited_ms`; `needs_login` = signed-out domains. Replaces `ark_common.trigger_download` / `login` and `playwright.sync_api.sync_playwright` (which `ark_common.ark_page` uses), plus any script's own `sync_playwright`. |
| `FakePage` / `FakeContext` / `FakeBrowser` / `FakeDownload` | class | The Playwright objects the scripts touch; `FakePage` raises on any call it doesn't model. |
| `LOGIN_PAGE` | constant | URL a signed-out `FakePage` lands on. |
| `Recorder` | class | Callable that records its calls; replaces `ark_common.upload`, `_login`, etc. |
| `LOADER_TEXTS` | constant | Data Loader status texts and whether `ark_common.upload` should stop waiting at each. |
| `FakeLoaderPage` / `_NullLocator` | class | Page `ark_common.upload` can drive with no browser; records `get_by_text` patterns in `text_patterns`, `get_by_role` (role, name) in `roles`, `goto` URLs in `visited`. |
| `FakeReportPage` / `_ReportLocator` / `_PreparingLocator` / `_FakeDownloadInfo` | class | Report page `ark_common.trigger_download` can drive with no browser: `preparing` = in-progress notifications at each check (last repeats); records `clicks` as (element, `waited_ms` then), `checks`, total `waited_ms`. |

### tests/buttons.py

| Name | Kind | Description |
|---|---|---|
| `Button` | dataclass | `label`, `kind`, `target` (script + args / window class), `covered_by` (test files). |
| `BUTTONS` | constant | The spec: every main-window button and what a click must do. |
| `COLUMNS` | constant | Main-window columns left to right, each listed top to bottom; the app test checks the layout matches. |
| `COLUMN_HEADERS` | constant | Label over each of `COLUMNS`; must match `g_columnHeaders` in main.cpp. |
| `CORNER_BUTTONS` | constant | Buttons placed outside the columns (Mirror top-left, Settings bottom-left). |
| `SCRIPT` / `SEQUENCE` / `DIALOG` / `INLINE` / `TODO` / `HIDDEN` | constant | Button kinds (`HIDDEN`: works but hidden by `g_hiddenButtonIds` and left out of `COLUMNS`; target = the script it runs once brought back). |
| `by_label` | function | Spec entry for a label. |

### tests/msvc.py

| Name | Kind | Description |
|---|---|---|
| `VCVARS` | constant | `vcvars64.bat` path (override with `PHX_VCVARS`). |
| `LIBS` | constant | Link libraries, same as build_and_run.bat. |
| `available` | function | True if the build tools exist. |
| `build_app` | function | Builds `phxcpp.exe` (icon + manifest) into a temp folder. |
| `build_cpp_tests` | function | Builds `tests/cpp/*.cpp` into `cpp_tests.exe`. |
| `_run` | private function | Runs commands in a VS developer environment; refuses the repo folder. |

### tests/cpp (C++ test support)

| Name | Kind | Description |
|---|---|---|
| `minitest.h`: `TEST`, `KNOWN_BUG`, `CHECK`, `CHECK_EQ` | macro | Register a test / known-bug test; checks that throw `MiniTestFailure`. |
| `minitest.h`: `MiniTests`, `MiniTestRegistrar`, `MiniShow`, `MiniFail` | function / struct | Registry, registration, value printing, failure. |
| `win_fakes.h` | header | Redefines `SHGetFolderPath`, `MessageBox`, `ShellExecute` to fakes before the tested .cpp is included. Declares the file helpers. |
| `test_main.cpp`: `wmain` | function | Runs every test with a fresh folder; prints `PASS` / `FAIL` / `KNOWN` / `FIXED` lines. |
| `test_main.cpp`: `g_sandbox`, `g_testDir`, `g_messageBoxes`, `g_shellOpened` | global | Run folder, per-test folder, recorded boxes and opened files. |
| `test_main.cpp`: `Fake_SHGetFolderPath`, `Fake_MessageBox`, `Fake_ShellExecute` | function | The fakes. |
| `test_main.cpp`: `ResetDir`, `WriteBytes`, `ReadBytes`, `FileExists`, `Utf8`, `FromUtf8`, `SawMessageBox` | function | File and string helpers for tests. |
| `test_organize.cpp` / `test_rename.cpp` / `test_settings.cpp` / `test_mirror.cpp` | test file | `#include` the matching .cpp to test its static functions (`test_mirror.cpp` also runs `cmd.exe` one-liners through `RunScriptLines`). Organize and Rename tests point their folder setting at the test folder with `SetSetting`. |

### Test files

| File | Covers |
|---|---|
| `test_wiring.py` | Static checks of main.cpp, settings.cpp, scripts and docs: every folder/file a script reads has a Settings row and vice versa, the sandbox covers every folder, every button using the Ark login is locked during Mirror (xfail for the ones using it only through `ark_page`, see KNOWN_ISSUES), `COLUMNS` + `CORNER_BUTTONS` place every shown button once, main.cpp's column headers match `COLUMN_HEADERS`, `g_hiddenButtonIds` is the `HIDDEN` buttons and their handlers and layout lines are still there, every script compiles and imports, `default_organize_rules.ini` has valid `[Rules]` columns and `ColumnSchema=2`. |
| `test_app_buttons.py` | Builds the app with stand-in scripts and clicks every button (a `HIDDEN` one must be hidden, disabled, and launch nothing); checks each button sits in its `COLUMNS` column and order, under its `COLUMN_HEADERS` label. The mirror.py stand-in honors `--stop-file`; flag files next to it make it hold its first step 30 s (`mirror_long_hold`), stay alive after `@FINISHED` like the report box (`mirror_report_hold`), or exit early (`mirror_crash`). |
| `test_cpp.py` | Builds and runs the C++ tests; Python reads the INI that settings.cpp writes. |
| `test_error_reporting.py` | Every button script shows an error box on failure (title, error and log path); the map scripts name a missing package; `ark_common.run_button`. |
| `test_ark_common.py` | `ark_common.upload` (the shared Data Loader wizard): picks the given dataset (whole name, any capitalization), confirms with the operation, stops at the "X of Y" row counter; `trigger_download` waits while Ark's notifications show an export in progress and fails after the time limit instead of taking an older file; `check_columns` accepts the expected header and rejects another report's; settings with `%` read as typed; `ark_page` logs in and keeps the session after an error. |
| `test_mirror.py` | Mirror's runner (fake steps): progress tags, failures carried on, report groups, archive file, message box; the child-process runner and its time limit (harmless `python -c` children); Stop via the stop file (Not run steps, the running child's tree killed); Index step; one full run of the real steps against the fake Ark. An autouse fixture resets `mirror._stop_file` per test. |
| `test_ppiq.py`, `test_index.py`, `test_str_verification.py`, `test_tpp_lhpp.py`, `test_download_report.py`, `test_cost_to_extend.py`, `test_case_matchup.py`, `test_case_unit_names.py`, `test_section_id_blank.py`, `test_docket_updates.py`, `test_docket_updates_slack.py`, `test_deceased.py`, `test_qq_checker.py`, `test_close_dates.py`, `test_case_update.py`, `test_map.py` | One button's script each (see the table in [TESTING.md](TESTING.md#button--tests)). |
