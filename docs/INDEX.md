# Code Index

Every function, global, constant and type, grouped by file. Local variables are left out.
Each entry is also commented in the source. Search the name to find it (no line numbers,
since they go stale). For how the pieces fit together, see [ARCHITECTURE.md](ARCHITECTURE.md).

**Contents**
- C++: [main.cpp](#maincpp) · [mirror.cpp](#mirrorcpp--mirrorh) · [settings.cpp](#settingscpp--settingsh) · [organize.cpp](#organizecpp--organizeh) · [rename.cpp](#renamecpp--renameh) · [merge.cpp](#mergecpp--mergeh) · [csv_text.h](#csv_texth)
- Python (shared): [ark_common.py](#ark_commonpy) · [operator_colors.py](#operator_colorspy) · [mirror.py](#mirrorpy)
- Python (Ark): [ppiq.py](#ppiqpy) · [tpp_lhpp.py](#tpp_lhpppy) · [nai_download.py](#nai_downloadpy) · [cost_to_extend.py](#cost_to_extendpy) · [str_verification.py](#str_verificationpy) · [close_dates.py](#close_datespy) · [non_hbp_mi.py](#non_hbp_mipy) · [case_matchup.py](#case_matchuppy) · [case_unit_names.py](#case_unit_namespy) · [section_id_blank.py](#section_id_blankpy)
- Python (other): [merge.py](#mergepy) · [deceased.py](#deceasedpy) · [qq_checker.py](#qq_checkerpy) · [docket_updates.py](#docket_updatespy) · [docket_updates_slack.py](#docket_updates_slackpy) · [doc_inventory.py + county scripts](#doc_inventorypy--doc_inventory_roosevelt--richland--dividepy) · [map_builder.py](#map_builderpy) · [map_uploader.py](#map_uploaderpy)
- [Tests](#tests): shared helpers, C++ test support, test files

---

## C++

### main.cpp
Entry point, main window, button dispatch.
**Reads:** settings.ini via `LoadSettings`. **Launches:** every button script (`LaunchScript`, or the Index / Maps threads). Each button is labeled with the Desktop folder its work goes to.

| Name | Kind | Description |
|---|---|---|
| `ID_TITLE`, `ID_BUTTON_*` | macro | Control ids for the title and each button; grouped by column. `ID_BUTTON_AOI` (11) runs `str_verification.py --aoi` (column 1 below STR; also Mirror's last step); `ID_BUTTON_NAI` (9, was `ID_BUTTON_DOWNLOAD`) runs `nai_download.py`; `ID_BUTTON_DOCKET_UPDATES` (51) is **Docket Updates Sheet** (below SIB) and runs `docket_updates.py`; `ID_BUTTON_DOCKET_UPDATES_SLACK` (59) runs `docket_updates_slack.py` (bottom of column 1; also a Mirror step); `ID_BUTTON_SIB` (36) runs `section_id_blank.py` (also a Mirror step); `ID_BUTTON_QQ` (60, bottom of column 4) runs `qq_checker.py`; `ID_BUTTON_MERGE` (61, bottom of column 3) opens the Merge link window (`AskMergeAccounts`), then runs `merge.py <id> <id>`. |
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
| `g_lockedDuringMirror` | static global | PPIQ, NAI, Docket Updates Sheet, Merge: not Mirror steps, but disabled while Mirror runs because their scripts share the Ark login (session.json). test_wiring checks every such button is a step or listed here. |
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
| `WinMain` | function | CoInitialize, `LoadSettings`, register window classes (Settings, Organize, Rename, Merge), create window, message loop. |

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
| `LoadSettings` | function | Called by WinMain; reads every row's own key (the old `DataMeetingDownload` key is ignored). Never writes. |
| `SaveSetting` | static function | Writes one row's key (other keys untouched). |
| `FindSetting` | static function | Row for `[section] key` (case-insensitive) or NULL. |
| `GetSetting` / `SetSetting` | function | Current value of a row ("" if unknown) / change it in memory. Organization and Rename read their folders with `GetSetting`. |
| `PickPath` | static function | COM `IFileDialog` picker for a folder or an `.xlsx`; true on OK. |
| `kRowTop` / `kRowPitch` / `kLabelW` / `kValueX` / `kValueW` / `kButtonX` | constant | Row layout in pixels. |
| `SettingsProc` | wndproc | Builds the rows; Change → `PickPath`, Save → text box; then `SaveSetting`. Typing turns "Saved" back into "Save". `WM_CLOSE` re-enables the parent before destroying the window (else Windows brings another app to the front); `WM_DESTROY` re-enables it too. |
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
| `CloseClassifyWindow` | static function | Sets `g_cp`'s result and done, re-enables the launcher, then destroys the dialog (enabling first keeps the focus off other apps). |
| `ClassifyProc` | wndproc | Classify dialog: snippet box, category combo, Confirm/Skip; each close through `CloseClassifyWindow`. |
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
| `CloseRenameWindow` | static function | Sets `g_renameDone`, re-enables the launcher, then destroys the dialog (enabling first keeps the focus off other apps). |
| `RenameProc` | wndproc | Shows the folder (from Settings), Generate / Apply / Close; Close and the X go through `CloseRenameWindow`. |
| `RegisterRenameClass` | function | Called by WinMain. |
| `OpenRename` | function | Called by Rename button; modal dialog loop. |

### merge.cpp / merge.h
The Merge button's link window: two boxes for links to the Ark accounts to merge; hands their record ids back to main.cpp, which runs `merge.py`. Touches no files or settings.
**Opened by:** Merge.

| Name | Kind | Description |
|---|---|---|
| `kRecordIdLength` | constant | 24, the length of an Ark record id (hex digits). |
| `kBlank` | constant | Spaces, tabs, CR, LF: trimmed from a pasted link. |
| `IsRecordId` | static function | True if a string is exactly 24 hex digits. |
| `Lower` | static function | Lowercase copy (ids are compared and passed on in lowercase). |
| `ParseAccountLink` | static function | One box → record id: an Ark `/accounts?recordId=` link (any domain, other query parts / `#` allowed) or the bare id, blanks trimmed; otherwise false with the reason (empty, not an account link, two things in one box, damaged id, no recordId). |
| `CheckMergeLinks` | static function | Both boxes: each `ParseAccountLink`, and two different accounts. True with merge.py's arguments `"<id> <id>"` (order typed), else the error line ("Account 2 …", "Both links are the same account …"). |
| `ID_MG_FIRST` / `ID_MG_SECOND` / `ID_MG_ERROR` | macro | Link boxes and red error line (701–703); Continue / Cancel are `IDOK` / `IDCANCEL`. |
| `MERGE_CLS` | constant | Window class `"MergeDlg"`. |
| `kMergeW` / `kMergeH` | constant | Client size of the window (540 × 200). |
| `g_mergeDone` / `g_mergeAccepted` / `g_mergeArgs` | static global | End of the modal loop; closed through Continue with valid links; the arguments it built. |
| `ControlText` | static function | Text of a control. |
| `CloseMergeWindow` | static function | Sets `g_mergeDone`, re-enables the launcher, then destroys the window (enabling first keeps the focus off other apps). |
| `MergeProc` | wndproc | Creates the controls; Continue runs `CheckMergeLinks` (close if OK, else show the error and focus the bad box); Cancel / close / Esc close; every close through `CloseMergeWindow`; error line drawn red; `DM_GETDEFID` makes Enter press Continue. |
| `RegisterMergeClass` | function | Called by WinMain. |
| `AskMergeAccounts` | function | Called by the Merge button: modal loop with `IsDialogMessage` (Tab / Enter / Esc); true + arguments on Continue. |

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
| `_DOWNLOAD_FILE` | constant | Selector of a finished export's "Download File" button in the notifications panel. |
| `_FILE_TEXTS_JS` | constant | JS that returns the text of the notification around each Download File button (report, time, date), pieces joined by spaces. |
| `_CARD_TIME` / `_CARD_DATE` | constant | Regexes for the time ("01:17 PM") and date ("11/3/2026") on a notification; digit lookarounds, so run-together text still reads. |
| `_PANEL_MS` | constant | 2 s for the notifications panel to fill before `trigger_download` notes the files already listed. |
| `_POLL_MS` / `_REOPEN_POLLS` / `_GENERATION_TIMEOUT_MS` | constant | `trigger_download` rechecks the panel every 5 s, closes and reopens it every 6 checks, and gives up after 10 min. |
| `_DOWNLOAD_START_MS` | constant | 3 min for a clicked Download File to start downloading (`expect_download`); 15 s ran out on PPIQ's 125 MB Inverse report on 2026-11-10. |
| `LARGE_DOWNLOAD_ROWS` | constant | 10,000: a report whose Total Record Count is this or more is downloaded only after the user clicks Yes (`confirm_download`). |
| `_COUNT_CARD_JS` | constant | JS that returns the text of the card around the report page's "Total Record Count" label ("Total Record Count 12,345"), or null. |
| `_RECORD_COUNT` | constant | Regex for the number after the label (commas allowed); a rounded "12.3K" doesn't match (counts as unreadable). |
| `_COUNT_SETTLE_MS` / `_COUNT_WAIT_MS` | constant | `record_count` reads the count every 1 s until two readings agree, giving up (unreadable) after 20 s. |
| `_LARGE_TITLE` / `_MB_LARGE_DOWNLOAD` / `_IDYES` | constant | `confirm_download`'s box: title "Large Ark download"; Yes/No, warning icon, No as the default button, foreground, topmost; Yes = 6. |
| `WAITING_TAG` / `RESUMED_TAG` | constant | `@WAITING` / `@RESUMED`, printed around `confirm_download`'s box; Mirror pauses the step's time limit between them. |
| `DownloadCancelled` | exception | The user said No to (or closed) a large-download box. `run_button` shows "<title> stopped. Large download cancelled: …" as a warning (no log); Mirror fails the step with that text. |
| `UPLOAD_ACCEPTED` | constant | Regex for the Data Loader row counter ("X of Y", commas allowed); once it shows Ark has the data, so `upload` stops waiting there. |
| `UPLOADED` / `REVIEW` / `NOTHING` | constant | Mirror result kinds returned by each `mirror_step()` ("Uploaded", "Needs review", "No changes"); also the report's headings. |
| `plural` | function | `'1 unit'` / `'3 units'` (irregular plural optional). |
| `parse_date` | function | Ark report date in one of 4 formats; ValueError otherwise. Used by close_dates and tpp_lhpp. |
| `_read_ini` | private function | settings.ini parsed with `interpolation=None`, so a `%` in a password or path is read as typed. |
| `read_credentials` | function | Ark `(username, password)` from `[Credentials]`. |
| `read_enverus_credentials` | function | Enverus `(identifier, password)` from `[EnverusCredentials]`. |
| `read_slack_token` | function | Slack user token from `[SlackCredentials] token`; KeyError if missing. |
| `read_folder` | function | `[Folders]` value for a key, else the default. Reads no other key (a renamed key's old name is ignored). |
| `read_setting` | function | Any `[section] key` (e.g. `[Files] IndexWorkbook`), or the default. |
| `notify` | function | Message box with a title (info icon, or e.g. 0x10 = error); returns the button clicked (6 = Yes in a Yes/No box, used by Merge). Each script's `_notify` calls it with its own title. |
| `run_button` | function | Runs a button script's `main()`; on an error writes the traceback to the script's `*_error.log`, shows "<title> failed: <error>" with the log path, re-raises. A `DownloadCancelled` instead gets a warning box "<title> stopped. Large download cancelled: <count> records, <report URL>", no log, and returns None. Every script's `__main__` uses it. |
| `_PIP_NAMES` | constant | Import name → pip package where they differ (`shapefile` → `pyshp`). |
| `missing_package` | function | For an `except ImportError` guard: box naming the `py -m pip install` command, then exit. Used by the map scripts. |
| `login` | function | Microsoft SSO sign-in, then wait for `success_url`. |
| `needs_login` | function | Page is on the Microsoft / Cloudflare sign-in. |
| `ensure_login` | function | `login` with `[Credentials]` if `needs_login` (PPIQ's domain switch). |
| `ark_page` | context manager | Chromium with the saved session → first URL → `ensure_login` → yields the page; always saves the session and closes the browser on the way out (also after an error). Every Ark script uses it. |
| `_file_texts` | private function | Text of each finished export in the open notifications panel, top first (`_FILE_TEXTS_JS`). |
| `_card_time` | private function | The minute a notification's text says it was made (`_CARD_TIME`, `_CARD_DATE`); None if it has no valid time and date. |
| `_new_file` | private function | Index of the first listed file that wasn't there before the Download click (repeats counted) and isn't stamped earlier than it; None if none yet. |
| `trigger_download` | function | Open report → `confirm_download(record_count(page))` (a large or unreadable count needs the user's Yes before Ark is asked for anything; No raises `DownloadCancelled`) → note the files the notifications panel lists → Download → wait `generation_wait_ms` → open the panel and recheck every `_POLL_MS` (reopening every `_REOPEN_POLLS`) until `_new_file` finds the new file → download that one; returns Playwright Download. RuntimeError after `_GENERATION_TIMEOUT_MS`, or if the download doesn't start within `_DOWNLOAD_START_MS`. Other notifications are ignored: Data Loader ones stuck at "0% Complete" held every download 10 min (until 2026-11-03), and taking the top file grabbed an older export (2026-10-21). |
| `record_count` | function | The report page's Total Record Count (`_COUNT_CARD_JS`, `_RECORD_COUNT`) once two readings `_COUNT_SETTLE_MS` apart agree; None if none readable within `_COUNT_WAIT_MS`. Called by `trigger_download`. |
| `confirm_download` | function | `confirm_download(report_url, records)`: returns at once under `LARGE_DOWNLOAD_ROWS`; otherwise (or records None) prints `WAITING_TAG`, shows the Yes/No box with the count and link, prints `RESUMED_TAG`, and raises `DownloadCancelled` unless Yes. Called by `trigger_download` (and the test FakeArk). |
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
**Writes:** `Mirror MM.DD.YYYY.txt` in `[Folders] MirrorArchive` (default `Desktop\Dailies\Archive`; a second run that day is appended), then shows the report in a task dialog where web links and the archive path can be clicked (a plain message box if it can't open).

| Name | Kind | Description |
|---|---|---|
| `FAILED` | constant | Result kind for a step that raised, hung or crashed. |
| `STOPPED` / `NOT_RUN` | constant | Result kinds after a Stop: the step that was running ("Stopped partway through", plus a Data Loader note for uploading steps) / the steps skipped. |
| `_GROUPS` | constant | Report section order: Uploaded, Needs review, No changes, Failed, Stopped, Not run. |
| `_ARCHIVE_DEFAULT` / `_RUN_SEPARATOR` | constant | Default archive folder; rule between two runs in one day's file. |
| `_MAX_ERROR` | constant | Longest failure reason kept (200 characters). |
| `_MB_ICONINFORMATION` / `_MB_ICONWARNING` / `_MB_TOPMOST` | constant | Message box flags (warning icon when a step failed or the run was stopped); the icon flag also picks the task dialog's icon. |
| `_URL_RE` / `_URL_TRAILING` | constant | Web links in the report, and the sentence punctuation left outside one. |
| `_TDF_*` / `_TDCBF_OK_BUTTON` / `_TDN_CREATED` / `_TDN_HYPERLINK_CLICKED` / `_TD_ICONS` | constant | Task dialog flags, button, callback notifications and icons (commctrl.h). |
| `_HWND_TOPMOST` / `_SWP_NOSIZE` / `_SWP_NOMOVE` | constant | `SetWindowPos` values that keep the report on top. |
| `_INVALID_HANDLE` / `_MANIFEST_NAME` / `_COMCTL6_MANIFEST` | constant | The Common Controls 6 manifest written to the temp folder for `_task_dialog`'s activation context, and `CreateActCtxW`'s failure value. |
| `_TaskDialogCallback` / `_TaskDialogConfig` / `_ActCtx` | ctypes type | `PFTASKDIALOGCALLBACK`, `TASKDIALOGCONFIG` (byte-packed, 160 bytes on 64-bit) and `ACTCTXW`. |
| `STEP_TIMEOUT_S` | constant | 20 min: a step still running then (time spent waiting on a large-download box not counted) is stopped (whole process tree) and reported as failed. |
| `_WAITING_LABEL` | constant | ": waiting for your answer (large download)", added to the progress label while a step's large-download box is open. |
| `RUN_IN_CHILD` | global | True: each step in a child process. tests/conftest.py sets False so tests never start real steps. |
| `_RESULT_TAG` | constant | `@RESULT ` line a step's child prints once: `<kind>\t<report line>`. |
| `_STOP_POLL_S` / `_STOP_DRAIN_S` | constant | 0.5 s: how often a running child is checked for a Stop / 5 s: after killing a stopped child, how long to read its remaining output (a late `@RESULT` wins). |
| `_INDEX_COUNTIES` | constant | The Index button's three county scripts, in order. |
| `_stage` | global | `(lo, hi, label)` of the running step's slice of the bar. |
| `_stop_file` | global | Path from `--stop-file` (set by `main`); None = no Stop possible. |
| `stop_requested` | function | True once the stop file exists. |
| `Step` | dataclass | `name` (button label), `run` (→ kind, line), `uploads`, `report_last` (its line ends the report instead of going in a result group). |
| `STEPS` | constant | The steps, in order: Index, Close Date, Case Update, STR, TPP-LHPP, C2E, Cases Unit Names, SIB, Docket Updates Slack, AOI (`report_last`) (named after the buttons). Must match main.cpp's `g_mirrorSteps`. |
| `_begin_stage` | private function | Prints `@STAGE lo hi label` for main.cpp and remembers it. |
| `_error_text` | private function | One-line failure reason (first line + type; `sys.exit` message; a `DownloadCancelled`'s text alone). |
| `_index_step` | private function | Runs the three counties (a failing one doesn't stop the others); "Added N new documents to the Index sheet (…)". |
| `_run_here` | private function | Runs one step in this process; FAILED on an exception (a refused large download: "Large download cancelled: <count> records, <report URL>"). |
| `_step_command` | private function | `[python, mirror.py, --step, n, lo, hi, label]`. |
| `_kill_tree` | private function | `taskkill /T /F` the child and everything it started (Chromium). |
| `_run_in_child` | private function | Runs a command, passes its lines through (the `@` tags reach main.cpp), returns its `@RESULT`; FAILED "Stopped: still running after N min" past the limit, STOPPED on a Stop (process tree killed), or "stopped without a result (…)" with its last line. Between the child's `@WAITING` and `@RESUMED` (a large-download box is open) the time limit is paused and the label gets `_WAITING_LABEL` (re-sent as `@STAGE`); those two tags aren't passed on. |
| `_child_main` | private function | Entry point of a step's child: set the progress slice, run `STEPS[n]`, print one `@RESULT` line. |
| `run_steps` | function | Runs every step with an equal slice of the bar, each via `_run_in_child` (or `_run_here` when `RUN_IN_CHILD` is off); after a Stop the rest are NOT_RUN; `[(name, kind, line)]`. |
| `build_report` | function | Header (start time, duration, "stopped early" after a Stop) + one section per result kind, then each step named in `last` (`main` passes the `report_last` steps) on its own closing line, "AOI: …" ("AOI: Failed: …" for a failure, stop or skip). |
| `_archive_path` / `_save` | private function | Day's report file; append the report to it. |
| `_with_links` | private function | Report text with each web link and each given path (the archive file) wrapped as `<a href>` links. |
| `_open_link` | private function | Opens a clicked link (`os.startfile`: browser or the file's program). |
| `_on_dialog_event` | private function | Task dialog callback: topmost on `TDN_CREATED`, `_open_link` on `TDN_HYPERLINK_CLICKED`. |
| `_task_dialog` | private function | Shows the report in a Windows task dialog (OK button, hyperlinks) inside a Common Controls 6 activation context; raises OSError if Windows refuses. Replaced by tests/conftest.py. |
| `_show` | private function | Final report: `_task_dialog` with `_with_links`; the old topmost message box if that fails. |
| `_stop_file_arg` | private function | The path after `--stop-file` in argv, or None. |
| `main` | function | `main(stop_file)`: run → report → save → `@FINISHED` → `_show` (archive path clickable). `mirror.py --step n lo hi label` runs `_child_main` instead. |

---

## Python — Ark scripts

### ppiq.py
**Button:** PPIQ. **Folder:** `[Folders] PPIQ` (default `Desktop\PPIQ`). **Writes:** 4 report CSVs (fixed names) + `Update_Inverted.csv` (UTF-8 with BOM) there, then a box with the issue count (a "close it" box instead if one of those files is open in Excel; errors: `ppiq_error.log` + a box).

| Name | Kind | Description |
|---|---|---|
| `_PPIQ_FOLDER` | constant | Output folder from `[Folders] PPIQ`. |
| `_Report` | class | One report: Ark name, URL, generation wait ms, the file name it's saved as, the columns read from it (by header name, any capitals), and `excludes`: columns it never has (one there means another report came). |
| `_LH_ID` / `_LH_NAME` / `_STATUS` / `_LHT_VALUE` | constant | Column names in the two queue reports. |
| `_REPORTS` | constant | `paid` (Landholdings In Queue (EM): Id, Price Paid, Account Name, Land Holding Name, Type), `all` (EM All Landholdings: Id, Account Name, Price Paid, Land Holding Name, Land Holding Type; for the PHX check and details of issues `paid` doesn't list), `queue` (All LHs In Queue (EM)), `inverse` (… (Inverse), on phoenixenergy.com: LH Id, Offer Status; trimmed in Ark 2026-11-13 to Offer Name, LH Id, Status, and excludes the LHT value so the queue report can't pass for it), in download order. |
| `_OUTPUT_FILE` / `_OUTPUT_HEADER` | constant | `Update_Inverted.csv`: ID, Price Paid, LHT Value, Type, Account Name, LH Name, Issue, Status. |
| `_PHX_ACCOUNT` / `_MAX_DIFF` | constant | The account whose landholdings must have a price paid; LHT vs price paid tolerance ($1). |
| `_NOT_IN_QUEUE` / `_PHX_NO_PRICE` / `_QUEUE_NO_PRICE` / `_LHT_MISMATCH` | constant | The Issue column values. |
| `_download_files` | private function | `ark_page` on the first report's domain; download each report back to back, save it as its `filename`, `_check_columns`; `ensure_login` when the domain changes. |
| `_column_indexes` / `_check_columns` | private function | Positions of a report's columns in its header, ignoring capitals; RuntimeError "Ark sent a different report than …" (naming the columns it got) if one is missing or one of its `excludes` is there. |
| `_read` | private function | Yields a saved report's rows as {column: value} for its columns only. |
| `_money` | private function | Amount text → float; blank = 0. |
| `_run_analysis` | private function | The 4 checks (price paid not in queue; PHX account with no price paid; queued with no price paid; LHT value more than $1 off); one row per issue (a landholding can have two); Price Paid / Type / Account / LH Name from Landholdings In Queue (EM) when it lists the landholding, else EM All Landholdings (`details`), LH Name from the queue report if neither has it; returns the issue count. |
| `_locked_files` | private function | The report CSVs and `Update_Inverted.csv` that exist but can't be written (open in Excel). |
| `_close_it` | private function | Warning box: "<path> is open in another program (probably Excel). Close it and click PPIQ again." |
| `main` | function | `_locked_files` (any → `_close_it`, nothing downloaded) → download → analyse (`Update_Inverted.csv` locked by then → `_close_it`) → box with the count and report path. |

### tpp_lhpp.py
**Button:** TPP-LHPP (also a Mirror step). **Folder:** `[Folders] TPPLHPP` (default `Desktop\TPP-LHPP`). **Writes:** `PHX_Price_Paid_Export.xlsx` there, then a message box listing exported offers with a Close Date.

| Name | Kind | Description |
|---|---|---|
| `_notify` | private function | Message box (errors and the Close Date summary). |
| `_OUT_DIR` | constant | Folder from `[Folders] TPPLHPP`. |
| `_REPORT_URLS` | constant | Offers report (15s wait), LHT report (120s wait). |
| `_OFFERS_FILENAME` / `_LHT_FILENAME` / `_EXPORT_FILENAME` | constant | Expected download names; output name. |
| `_EXPORT_SHEET` / `_EXPORT_HEADER` | constant | The export's sheet name and header row. |
| `_MAX_LISTED` | constant | Most offers (25) named in the Close Date message box; the rest are counted. |
| `_SOON_DAYS` | constant | 14: Mirror counts mismatches closing from today through this many days out. |
| `_YELLOW_FILL` | constant | Highlight for exported cells. |
| `_download_files` | private function | Log in and download both reports. |
| `_find_file` | private function | Case-insensitive file lookup in `_OUT_DIR`. |
| `_process_offers` | private function | Offers CSV → `{id: TPP, status, close date}`. |
| `_process_lht` | private function | Sum LHT values per offer. |
| `_row_key` | private function | A workbook row as a tuple, blanks as `''` (a written `''` reads back as None). |
| `_export_rows` | private function | Counter of the rows (header included) of an export workbook, any order; None if missing or unreadable. |
| `_export` | private function | Offers where LHT and TPP differ by more than $1 → xlsx, replacing the last one; returns `(exported Ids, unchanged)`, unchanged when the new rows equal the old file's (`_export_rows`). |
| `_close_date_message` | private function | Summary text: how many exported offers have a Close Date, listing up to `_MAX_LISTED`. |
| `_closing_soon` | private function | `(soon, unreadable)`: exported offers closing today through `_SOON_DAYS` out, and those whose Close Date can't be parsed. |
| `main` | function | Download → process → export → Close Date message box (skipped when `quiet`); returns `(offers, exported, unchanged)`. |
| `mirror_step` | function | Mirror: quiet run; Needs review "N price mismatches closing in the next two weeks" (plus "and N with a Close Date Mirror couldn't read"), or Needs review for unreadable dates alone, else No changes. Either Needs review becomes No changes "PHX_Price_Paid_Export.xlsx unchanged since the last run (…)" when the export is unchanged. |

### nai_download.py
**Button:** NAI (Newly Acquired Interest; was DMD / Data Meeting Download, `download_report.py`, before 2026-10-28). **Folder:** `[Folders] NewlyAcquiredInterest`, else `Desktop\NAI` (the old `DataMeetingDownload` key, which pointed at `Desktop\DMD`, is ignored). Shows a box when done (errors: `nai_download_error.log` + a box).

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | `Desktop\NAI`, used when `[Folders] NewlyAcquiredInterest` is unset. |
| `_REPORT_URLS` | constant | The two NAI reports. |
| `_out_dir` | private function | The output folder (`read_folder('NewlyAcquiredInterest', _DEFAULT_DIR)`). |
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
**Buttons:** STR (no args; also a Mirror step), AOI (`--aoi`; also Mirror's last step). **Folders:** `[Folders] STRVerification` (STR), `[Folders] AOI` (AOI). **Writes:** `Error_Report.csv` (STR) or `AOI MM.DD.YYYY.csv` (AOI), each in its own folder.

| Name | Kind | Description |
|---|---|---|
| `_REPORT_URL` | constant | Ark "Check STR" report. |
| `_INPUT_NAME` | constant | Downloaded report's file name, `Check_STR_(EM)_(Full).csv`. |
| `_COLUMNS` | constant | The 8 report columns `_process` reads by position (7th unread); checked on download. |
| `_OUT_DIR` / `_INPUT_PATH` | constant | STR Verification folder (default `Desktop\STR`); its downloaded report. |
| `_AOI_DIR` / `_AOI_INPUT_PATH` | constant | AOI folder (default `Desktop\AOI`); its downloaded report. |
| `_STR_ERROR_PATH` / `_AOI_ERROR_PATH` | constant | STR Verification report (`Error_Report.csv`, in `_OUT_DIR`); AOI report (`AOI MM.DD.YYYY.csv`, run date, in `_AOI_DIR`). |
| `_AOI_SKIP` | constant | Area of Interest values the AOI check skips (blank, `Non-Ops`). |
| `_SECTIONS_TR` / `_SECTIONS_TR_RE` / `_AOI_BODY` | constant | Regexes for one section group (`1, 12, 13-150N-100W`) and an AOI name's part before `_` (one or more groups, comma-separated). |
| `_AOI_FORMAT` | constant | Example AOI name quoted in the "can't be read" issue. |
| `_download_report` | private function | `trigger_download` (60s wait) → `_AOI_INPUT_PATH` if `aoi`, else `_INPUT_PATH` → `check_columns(_COLUMNS)`. |
| `_aoi_sections` | private function | AOI name → set of `(section, (township, N/S), (range, E/W))` it covers, each section tied to its own township-range; `None` if the name doesn't follow `1, 12-150N-100W[, 25, 36-151N-100W] _ Name`. |
| `_row_section` | private function | A row's `(section, township, range)`: from Section Name, else Section + Township + Range, else Section + Township Name; `None` if none parse. |
| `_aoi_issue` | private function | `''` if the row's section is in the AOI, else the Issue text: AOI can't be read / section can't be read / section not in that township-range's sections / township-range not in the AOI. |
| `_process` | private function | `aoi=False`: `_INPUT_PATH`, Section Name vs S-T-R (blank Section Names skipped) → `_STR_ERROR_PATH`. `aoi=True`: `_AOI_INPUT_PATH`, every row with an AOI (not `_AOI_SKIP`) through `_aoi_issue` → `_AOI_ERROR_PATH`. Returns the failure count. |
| `main` | function | `ark_page` → download → `_process(aoi)`; `aoi` defaults to whether `--aoi` was passed. Returns the failure count. |
| `_button` | private function | The STR / AOI button: `main()`, then a box with the count and report path. |
| `mirror_step` | function | Mirror (STR check only): Needs review "N Section Name mismatches: review Error_Report.csv", else "No STR errors found". |
| `aoi_mirror_step` | function | Mirror's AOI step (AOI check only; `report_last`, so it ends the report): Needs review "N rows in the error report: review AOI MM.DD.YYYY.csv", else No changes "No rows in the error report (AOI MM.DD.YYYY.csv)". |
| `_LOG_DIR` | global | Running button's folder (`_AOI_DIR` with `--aoi`, else `_OUT_DIR`); `str_verification_error.log` goes there (defined in `__main__`). |

### close_dates.py
**Button:** Close Date (also a Mirror step). **Folder:** `[Folders] CloseDates`. **Uploads to Ark (Landholdings Update).**

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | `Desktop\Close Date`, used when `[Folders] CloseDates` is unset. |
| `_notify` | private function | Message box (`ark_common.notify`). |
| `_REPORT_URL` / `_REPORT_NAME` | constant | The Ark report "Land Holding Closings EM" and its name for the wrong-report error. |
| `_COLUMNS` | constant | Its columns, read by position: (any), `LandHoldingTransaction: LandHolding Id`, `Offer: Close Date`, `Offer: Status`; checked with `ark_common.check_columns`. |
| `_nth_weekday` | private function | nth (or last) weekday of a month, for floating holidays. |
| `_holidays` | private function | Office holidays for a year: federal + day after Thanksgiving + Christmas Eve, plus weekend-observed dates. |
| `_is_business_day` | private function | Weekday and not a holiday. |
| `_target_dates` | private function | Every day from the last business day before today through yesterday (Fri–Sun on Monday, further back after a holiday). |
| `main` | function | Download, check `_COLUMNS` (RuntimeError, nothing written or uploaded, if another report came back), keep rows closed on the target dates (skip Deferred in the 4th column; its message box only when not `quiet`), write CSV, upload if any rows (`ark_common.upload`, Landholdings); returns the count. |
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
**Button:** SIB (also Mirror's last step). **Uploads to Ark (Landholdings Update).** **Folder:** `[Folders] SIB` (default `Desktop\SIB`). **Downloads:** `Landholdings_Section_Id_Blank_EM.csv` (landholdings with no Section Id, overwritten each run) and `Section_ID_Getting.csv` (sections created in Ark in the last week; deleted once merged). **Keeps:** `Section_ID_Index.csv` (Section Name, Section Id, Updated: every section, one Id per name; grows each run, never re-downloaded; seeded 2026-11-03 with 59,122 sections). **Writes:** `Section_Id_Upload.<date>.csv` (Id, Section Name, Section Id; one row per landholding whose Section Name is in the index). **Command line:** `py section_id_blank.py --seed` builds a missing index from a full download saved as `Section_ID_Getting.csv`.

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | Folder used when `[Folders] SIB` is unset. |
| `_BLANK_URL` / `_SECTIONS_URL` | constant | The Landholdings Section Id Blank EM and Section ID Getting reports. |
| `_BLANK_FILE` / `_SECTIONS_FILE` | constant | Fixed names the two reports are saved as (the sections one is deleted after the merge). |
| `_INDEX_FILE` / `_INDEX_HEADER` | constant | `Section_ID_Index.csv` and its columns: Section Name, Section Id, Updated (when the name got its current Id). |
| `_BLANK_COLUMNS` / `_SECTIONS_COLUMNS` | constant | Each report's first columns (Id, Section Name, Section Id / Section: Id, Section Name); checked on download. |
| `_OUTPUT_HEADER` | constant | Output columns: Id, Section Name, Section Id. |
| `_MAX_LISTED` | constant | Section names listed in a message box or error (20). |
| `_SEED_ARG` | constant | `--seed`: run `seed` instead of `main`. |
| `_notify` | private function | Message box. |
| `_key` | private function | Section Name as compared: uppercase, spaces collapsed. |
| `_listed` | private function | Up to `_MAX_LISTED` names, comma-joined, "...and N more". |
| `_read_download` | private function | Section ID Getting → `{name key: (name, Id)}`; skips rows with no Id or name; RuntimeError naming each name listed with two different Ids (and the Ids), for a manual check. |
| `_read_index` | private function | `Section_ID_Index.csv` → `{name key: [name, Id, Updated]}`; RuntimeError if missing (says how to `--seed`) or a name is listed twice. |
| `_merge` | private function | Adds new names (dated today) and gives an indexed name that came with a new Id that Id; returns (names added, names replaced). |
| `_write_index` | private function | Writes the index through a `.tmp` file + `os.replace`, so a failed write can't leave half an index. |
| `_read_blank` | private function | (Id, Section Name) of landholdings still missing a Section Id; skips rows with no Id or name, or a Section Id already. |
| `_match` | private function | Returns output rows (the indexed Id of each landholding's Section Name) and unmatched landholding ids (no indexed section of that name). |
| `_write_csv` | private function | Write `_OUTPUT_HEADER` + rows. |
| `_summary` | private function | Finish message: found/total, output path, uploaded or nothing to upload, unmatched count, sections added to the index, names that got a new Id. |
| `main` | function | Read the index (before the browser) → log in → download both reports (each checked against its columns) → merge the sections into the index, write it, delete the download → match → write → upload if any rows (`ark_common.upload`, dataset Landholdings) → summary box (skipped when `quiet`). Always saves the session; returns (number uploaded, names added, names replaced). Errors go to `section_id_blank_error.log` + a box. |
| `seed` | function | `--seed`: builds a missing index from a full `Section_ID_Getting.csv` in the folder (kept); refuses if the index exists. |
| `mirror_step` | function | Mirror: quiet run; Uploaded "Uploaded Section Ids for N landholdings", else No changes "No blank Section Ids to fill in"; either adds "; N section names got a new Section Id". |

---

## Python — other

### merge.py
**Button:** Merge (after its link window, merge.cpp): `py merge.py <id or link> <id or link>`. **Folder:** `[Folders] Merges` (default `Desktop\Merges`), documents between download and upload; errors go to `merge_error.log` in `%APPDATA%\PhoenixLandDept` + a box. Reads both accounts and each of their land holdings and shows them side by side in a review window. When the user picks the account to keep and says Yes, **changes live Ark data**: renames the other account "<name> (merge)" and the kept one "<name> (keep)", puts note blocks above the kept account's Account Notes and Call Notes, moves the merge account's contacts, offers, title requests and calls & texts to the kept account (a record Ark won't move is listed in the closing box), moves its land holdings there and gives every land holding the Legal Entity and signers picked in the land holdings window, and copies its documents there. If nothing is left on the merge account, both accounts open in the browser and a second Yes **deletes the merge account**. Tasks aren't moved.

| Name | Kind | Description |
|---|---|---|
| `ACCOUNT_URL` | constant | `https://ark.phoenixenergy.com/accounts?recordId={}`, an account's page. |
| `_RECORD_ID` | constant | Regex: an Ark record id (24 hex digits). |
| `_ACCOUNT_LINK` | constant | Regex: an account page link (any Ark domain, other query parts / `#` allowed); group 1 = record id. |
| `_TITLE_PREFIX` / `_HOLDING_PREFIX` | constant | `"Account - "` / `"Land Holding - "`: a loaded page's title starts with it, then the record's name. |
| `_NOT_FOUND` / `_HOLDING_NOT_FOUND` | constant | `"Account Not Found"` (Ark's message for a missing account, in about a second) / `"Land Holding Not Found"` (a guess; not seen live). |
| `_OPEN_TIMEOUT_MS` / `_POLL_MS` | constant | Give up on a page after 30 s; recheck the title every 250 ms. |
| `_SETTLE_MS` | constant | 1 s: `_read_page` reads again after this long and takes the page once two reads agree. |
| `CHECKED` | constant | Quick Reference counts read on each account: Documents, Contacts, Offers, Title Requests, Tasks, Calls & Texts, Land Holdings. |
| `DETAILS` | constant | Account fields shown for review (section, label): Created Date (System Information), Account Disposition, Mailing Street / City / State / Zip Code, Confirmed Phone Number, Confirmed Email Addresses (Details). |
| `NOTES` | constant | Account text fields: (`Account Notes`, `Notes`), (`Call Notes`, `Call Notes`) as (section, label). |
| `HOLDING_FIELDS` | constant | Land holding fields: Legal Entity (Details), Section Name (Location Info), Title Information (Title Info). |
| `_SIGNER_SECTION` / `_SIGNER` | constant | `Signer Information`, the land holding section with Signer 1–9; regex for a signer's own label (`Signer N`). |
| `_SIGNER_PARTS` / `_MAX_SIGNERS` | constant | A signer's parts and their field label after "Signer N": Signer (`""`), Last Name, Capacity; 9 signers per land holding. |
| `_SIGNER_BOX_LIMITS` | constant | Highest Signer number Ark has each part's box for: Signer 9, Last Name 2, Capacity 3 (seen 2026-11-11). |
| `_LEGAL_ENTITY` / `_HOLDINGS_LABEL` / `_HOLDING_PATH` | constant | `"Legal Entity"`; the Land Holdings Quick Reference label; `/land-holdings?recordId=` in a land holding link. |
| `_QUICK_ENTRY` | constant | Selector of the Quick Reference entries (and the expanded tables that reuse their id), in the order `_READ_JS` reads them; `_open_drawer` clicks `.nth(_quick_index)`. |
| `_HOLDING_BOX` / `_HOLDING_TABS` | constant | A land holding edit window's box for a field label (`label:text-is("…") + :is(input, textarea)`); the tab each is on (Legal Entity: Details; signers: Signer Information, clicked `loose` since Ark's tab text isn't exactly its name). |
| `_PARENT` / `_PARENT_ENTRY` | constant | `"Parent Account"` (in an account's `details`, compared by `merge_differences`); `"Parent - "`, Ark's Quick Reference hierarchy entry naming the parent. |
| `_COUNT` | constant | Regex: a Quick Reference count, "(12)" / "(1,234)". |
| `_NOT_SHOWN` | constant | `"not on this page"`: how the window shows an item or field the page doesn't have. |
| `_READ_JS` | constant | JS for `page.evaluate`, on account and land holding pages: Quick Reference entries `[label, count text]`, every detail field `[section, label, value]` (value = the element after the label) and the `/land-holdings?recordId=` links `[href, text]`. |
| `_TAG` | constant | Regex: a `(keep)` / `(merge)` already at the end of a name (any case), replaced by `tagged_name`. |
| `_INITIALS` | constant | `"RM"`, in the note block's first line. |
| `_DETAIL_BOX` | constant | An Edit Account window's box for a Details field label (`label:text-is("…") + :is(input, textarea)`, Details tab; seen for the phone and email, mailing boxes assumed the same). |
| `_MAILING` / `_PHONE` / `_EMAIL` | constant | The account fields `merge_differences` compares and `blank_fills` copies: Mailing Street / City / State / Zip Code (one address), Confirmed Phone Number, Confirmed Email Addresses. |
| `_LIST_SPLIT` | constant | Regex: what separates several phone numbers or emails in one field (`,` `;` `/` new line). |
| `_EDIT_BUTTON` / `_NAME_FIELD` / `_SAVE_BUTTON` | constant | A record page's Edit button (accounts, contacts, offers, title requests, calls), the Edit Account window's Account Name box (`label:has-text("Account Name") + input`, Details tab), an edit window's Save. |
| `_NOTE_BOXES` | constant | The Edit Account window's notes boxes by section (= the tab holding it): Account Notes `label:text-is("Notes") + textarea`, Call Notes `label:text-is("Call Notes") + textarea`. |
| `_UPDATE_URL` | constant | `api-ark.phoenixenergy.com/update-sb`, Ark's call that stores an edited record (accounts and the records moved). The window closes before it's sent, so `_save` waits for its answer (reloading sooner cancels the save). |
| `MOVED` | constant | Records moved to the kept account: (Quick Reference label, link path, word for one, for several) for Contacts (`/contacts`), Offers (`/offers`), Title Requests (`/title-requests`), Calls & Texts (`/activities`). |
| `_DRAWER_JS` | constant | JS for `page.evaluate(part)`: the links containing `part` in the side drawer (`#side-drawer`) a Quick Reference entry opens, i.e. the account's full list of that kind. |
| `_ACCOUNT_BOX` | constant | A record's Account lookup in its edit window: the `div` whose label is "Account" or "Account Name *" (not "Account Owner Name"). Its `<p>` is the account shown, its first `<svg>` the x that turns it into a search box. |
| `_KEY_DELAY_MS` | constant | 50 ms between keys when typing the account search (a value filled in at once doesn't search). |
| `_RECORD_LINK` | constant | Regex: the record id in a record page link. |
| `_ASK_FLAGS` / `_IDYES` | constant | Yes/No question box with No as the default (0x124); its Yes answer (6). |
| `_DEFAULT_DIR` | constant | `Desktop\Merges`, used when `[Folders] Merges` is unset. |
| `_DOCUMENTS` / `_DOC_ROWS_JS` / `_DOC_ROW` / `_DOWNLOAD_BUTTON` | constant | The Documents Quick Reference label; JS for the file name (first cell) of each row of the side drawer's table; a row; its download button (the tray-and-arrow icon; never the row's other buttons). |
| `_ADD_BUTTON` / `_FILE_INPUT` / `_UPLOAD_BUTTON` / `_READY` / `_UPLOAD_URL` | constant | The Documents drawer's **Add**, the upload window's file picker, **Confirm and Upload**, the "Ready to Upload" shown under each file taken in, and Ark's `related-bulk-document-upload` call. |
| `_TRANSFER_TIMEOUT_MS` | constant | 2 minutes: give up on one download, or on the upload window closing. |
| `_SCROLL_JS` / `_STILL_READS` / `_LIST_TIMEOUT_MS` | constant | JS scrolling every scrollable box in the side drawer to its bottom (Ark loads long lists as they're scrolled); `_listed` stops after 3 reads in a row add nothing, or after 2 minutes. |
| `_DOWNLOAD_PART` | constant | `_merge_download.part`: a document's name in the folder until `_file_name` names it. |
| `_BAD_NAME_CHARS` | constant | Regex: characters Windows doesn't allow in a file name (`< > : " / \ \| ? *`, control characters), replaced by `_`. |
| `_KNOWN_EXTENSIONS` | constant | Extensions taken from a document's listed name (pdf, docx, xlsx, jpg, tif, msg, ...); anything else after a dot there is part of the name. |
| `_SUGGESTED_EXTENSION` | constant | Regex: an extension on Ark's download name (1–5 letters / digits, at least one a letter). |
| `_MAGIC` / `_ZIP_MAGIC` / `_ZIP_KINDS` / `_OLE_MAGIC` / `_OLE_KINDS` | constant | `_sniff_extension`'s tables: first bytes → .pdf / .png / .jpg / .gif / .tif / .rtf; a zip and its folder → .docx / .xlsx / .pptx (else .zip); an old Office file and its stream name → .doc / .xls / .msg. |
| `_DELETE_BUTTON` | constant | `"Delete"`: the account page's button (top right) and the one in Ark's confirmation box. |
| `_API` / `_CHANGE_METHODS` | constant | `api-ark.phoenixenergy.com`; POST / PUT / PATCH / DELETE. `delete_account` takes the delete as done when such a call naming the account answers. |
| `record_id` | function | Pasted link or bare id → lowercase record id; `ValueError` otherwise. |
| `_Stopwatch` | private class | Time a wait loop has gone on: its own pauses (`sleep`) or the real time since it started, whichever is more (`elapsed_ms`), so a loop whose every look is slow still stops on time. Used by `_listed`, `upload_documents` and `delete_account`. |
| `_reason` | private function | First line of an error's message without a trailing ":", or the error's kind ("OSError") if it has none: what a closing-box note says went wrong. |
| `_open_record` | private function | Open an account or land holding page (log in and reopen it if Ark asks), wait for its name in the title; raises on its Not Found message or after 30 s. |
| `_counts` | private function | `{label: n}` of the "(N)" Quick Reference counts (drops the tables that reuse its id). |
| `_quick_index` | private function | Index in a read of the Quick Reference entry `_counts` takes for a label (exactly that label, with a count), so the entry clicked is the one counted; `None` if none. |
| `_fields` | private function | `{(section, label): value}`: first copy of each field, trimmed, "-" → `''`. |
| `_holding_links` | private function | The land holding URLs linked on an account page, each once. |
| `_read_page` | private function | A `_READ_JS` read once it's ready and two reads `_SETTLE_MS` apart agree; raises if never ready in 30 s. |
| `_signers` | private function | `[{'Signer', 'Last Name', 'Capacity'}]` from Signer Information, in number order, blank signers left out. |
| `_read_holding` | private function | One land holding: `{'name', 'url', 'fields': HOLDING_FIELDS values, 'signers'}`. |
| `_parent` | private function | An account's parent: a "Parent Account" field in any section, else the first line of the "Parent - <name>" Quick Reference entry, else `''`. |
| `_read_account` | private function | One account: `{'name', 'url', 'counts', 'details' (plus Parent Account), 'notes', 'holdings', 'holdings_missing'}` (None = not on the page, `''` = blank). Land holdings: the ones linked on the page, plus the Land Holdings side drawer's (`_related_links`) when the count is higher; `holdings_missing` = counted but found in neither. |
| `untagged_name` | function | The name without a trailing " (keep)" / " (merge)". |
| `tagged_name` | function | `"<name> (keep)"` / `"<name> (merge)"`, replacing a tag already there (so a second try doesn't tag twice). |
| `_plain` | private function | Text lowercased with whitespace collapsed, for comparisons. |
| `_mailing` / `_phones` / `_emails` | private function | An account's mailing address on one line ("street, city, state zip") / the phone numbers in a field as their last 10 digits / the emails in a field, lowercased. |
| `_blank` | private function | A field on the page with nothing in it (`None`, not on the page, isn't blank). |
| `blank_fills` | function | `{label: value}` the kept account gets where its own is blank: phone and email each on its own, the mailing address only when every part is blank (only the parts the merge account has). DETAILS order. |
| `merge_differences` | function | Note lines for the merge account's mailing address, phone, email and parent account, each only if it has one the kept account doesn't / that differs ("Mailing Address: …", "Phone: …", "Email: …", "Parent Account: …"); what `blank_fills` copies isn't listed. |
| `merge_note` | function | The note block: `"<mm/dd/yyyy> RM - Notes from merge:"`, `merge_differences`, then the merge account's Account Notes between `"` lines; `''` if there's nothing to add. |
| `merge_call_note` | function | The Call Notes block: the same date line, then the merge account's Call Notes between `"` lines; `''` if it has none. |
| `note_blocks` | function | `{'Account Notes': merge_note, 'Call Notes': merge_call_note}`. |
| `combined_notes` | function | The kept account's new notes: block, blank line, the notes it had. |
| `_to_move` | private function | An account's `MOVED` records as text ("1 offer, 2 calls & texts"), from its counts. |
| `_confirm_text` | private function | The Yes/No box text: both renames, the blank fields filled (`blank_fills`), each note block (or "Nothing to add to the …"), what will move, each land holding's changes (`_plan_text`, under "Land holdings:"), the documents to copy, and that Merge asks again before deleting the merge account and then renames the kept one without "(keep)". |
| `_field` | private function | The one box matching a selector in an edit window (waits for it); raises if there isn't exactly one. |
| `_save` | private function | Save; if something changed, wait for Ark's `_UPDATE_URL` answer for the record (raises if none in 30 s or an error), then for the window to close. |
| `_loaded_name_box` | private function | The Account Name box once it shows the account's name, so the notes aren't read before the window has the account's data; raises after 30 s. |
| `_edit_account` | private function | Opens the account's Edit Account window, sets the name, fills each of `fills` (`_DETAIL_BOX`; raises before saving if the box isn't blank any more), puts each non-blank block above its section's notes (on that tab: `_open_tab`, its exact name, else the first text containing it as seen live), `_save`. Returns `{section: notes saved}`. |
| `_check_saved` | private function | Reloads the account; raises unless it shows the new name, each new notes text and each field filled (whitespace and case aside). |
| `_open_drawer` | private function | Opens the account and, if its Quick Reference counts any of a label (or `even_empty`), clicks that entry (`_QUICK_ENTRY` `.nth(_quick_index)`: the one counted, not another whose text contains the label) to open its side drawer. Returns the count; raises if `even_empty` and there's no such entry. |
| `_listed` | private function | A list read from the open side drawer, scrolling it (`_SCROLL_JS`) between reads until it has the count, 3 reads in a row add nothing (2 minutes at most), or it stays empty for 30 s (`_Stopwatch` time). |
| `_related_links` | private function | `_open_drawer` for a `MOVED` label, then the drawer's links (`_DRAWER_JS`) through `_listed`. Returns (links, count). |
| `_account_counts` | private function | Opens the account and returns its Quick Reference counts. |
| `_with_listed_holdings` | private function | Counts with Land Holdings replaced by how many the account's Land Holdings drawer lists, when Ark counts some (its count can lag after a move, seen 2026-11-11; an empty drawer under a stale count takes 30 s). Leaves the drawer open. |
| `_move_record` | private function | Opens a contact / offer / title request / call, `_open_edit`, `_account_lookup` (its Account shows the merge account's name), `_pick_account` (the kept account), `_save`. Raises (unsaved) if any step doesn't work out. |
| `_open_edit` | private function | Clicks a record page's Edit (once it shows) and returns the edit window. |
| `_account_lookup` | private function | The edit window's Account lookup once its tag shows the owner's name (the window has loaded); raises after 30 s showing another. |
| `_pick_account` | private function | x on the lookup's account, types the new name key by key, picks the one exact match, checks the tag took it; raises otherwise. |
| `move_records` | function | Every `MOVED` record of the merge account through `_move_record`, rereading the drawer after each pass until it lists nothing new (each record tried once); a failure is noted (`_reason`) and the rest go on; notes records counted but never listed. Returns (`{label: moved}`, problems). What's left is counted once, by `apply_merge`. |
| `_document_names` | private function | `_open_drawer` on Documents (`even_empty` passed on), then the rows' names (`_DOC_ROWS_JS`) through `_listed`; the drawer stays open. Returns (names, count). |
| `_free_path` | private function | `folder\name`, or `name (2).ext`, `(3)`, ... if taken. |
| `_known_extension` | private function | A name's extension in lowercase if it's one of `_KNOWN_EXTENSIONS`, else `''`. |
| `_sniff_extension` | private function | The extension a file's contents show (`_MAGIC`, zip folders, old Office streams), else `''`. |
| `_file_name` | private function | A downloaded document's name: its listed name (else its download name) with `_BAD_NAME_CHARS` → `_`, plus an extension if it has no known one (the download name's, else `_sniff_extension`); raises if neither tells the type. |
| `_document_key` | private function | A document name lowercased, trimmed, without a known extension, for checking an upload is listed. |
| `download_documents` | function | Each listed document of the merge account: its download button → `_DOWNLOAD_PART` → renamed `_file_name` in the folder. Notes documents counted but not listed and each that fails (`_reason`; removing its part file). Returns (paths, problems). |
| `upload_documents` | function | All the paths through the kept account's Documents drawer (left open by `_document_names(even_empty=True)`, which also reads what's there before; Add, file picker, wait for "Ready to Upload" under each, Confirm and Upload, wait for `_UPLOAD_URL` and the window to close), then waits until its list shows them (`_document_key`), up to 30 s of `_Stopwatch` time. Returns (paths listed, problems). |
| `move_documents` | function | `download_documents` then `upload_documents`; deletes from the folder each one Ark lists. Returns (number copied, problems). |
| `_signer_key` / `clean_signers` | private function / function | Signers as compared (each part lowercased, spacing collapsed); signers as saved (trimmed, blank ones dropped, at most 9). |
| `missing_signer_boxes` | function | The `Signer N <part>` labels signers fill that Ark has no box for (`_SIGNER_BOX_LIMITS`). |
| `holding_choices` | function | `{land holding url: {'Legal Entity', 'signers'}}` for every land holding of both accounts as it is now: the land holdings window's starting point and answer form. |
| `holding_options` | function | What the land holdings window offers: (Legal Entities, `[(label, signers)]` signer lists labelled "… (from <land holding>)", capacities), from both accounts, each once (also a capacity two signers of one land holding share). |
| `holding_plans` | function | From the window's choices: `{'url', 'name', 'move', 'owner', 'legal_entity', 'signers'}` per merge account land holding (all move) and per kept one whose Legal Entity or signers change; unchanged values None. |
| `_plan_text` | private function | A plan as a line: `"<name>: move to "<keep>", Legal Entity "…", signers …"`. |
| `_holding_box` / `_open_tab` | private function | The one `_HOLDING_BOX` for a field label (raises if not exactly one); clicks an edit window tab by its exact name if it's there (`loose`: else the first text containing the name, used for the notes and Signer Information tabs). |
| `_update_holding` | private function | One plan: open the land holding, `_open_edit`, `_account_lookup` (owner's name), `_pick_account` if it moves, Legal Entity box, the signer boxes Ark has (`_SIGNER_BOX_LIMITS`; each filled only if different; past the last signer emptied; raises before opening it if `missing_signer_boxes`), `_save`, reload and check the Legal Entity and signers (raises if not shown). |
| `update_holdings` | function | Every plan through `_update_holding` (the owner's current name from `names`); a failure is noted (`_reason`) and the rest go on. Returns (`{'updated', 'moved'}`, problems). |
| `delete_blockers` | function | Why an account with these counts can't be deleted: `MOVED` records or land holdings Ark still counts on it ("Ark still counts N … on it"; callers put in the land holdings listed, `_with_listed_holdings`). `[]` = nothing left. |
| `apply_merge` | function | Renames the merge account and checks it, renames the kept one, fills its blank fields (`blank_fills`), adds the note blocks and checks it, `move_records`, `update_holdings(plans)`, `move_documents`, then recounts the merge account for `blockers` (`delete_blockers` with `_with_listed_holdings`, "N documents on it, M copied", "the problems above need a look first"). Returns `{'merge_name', 'keep_name', 'filled', 'moved', 'holdings', 'documents', 'problems', 'blockers'}`. |
| `delete_account` | function | Reopens the merge account, checks its name and `delete_blockers` again (land holdings as `_with_listed_holdings` lists them, then the account is reopened to close the drawer; raises, deleting nothing, if either is off), clicks Delete and the confirmation box's one Delete, waits for Ark's answer naming the account, then opens the link in another tab (`page.context.new_page`, closed after; reloaded while it still shows the account) until it shows "Account Not Found". The page itself isn't left, so a delete still on its way (if that answer was another call naming the account) isn't cancelled. Raises if Ark refuses, doesn't answer in 30 s, or still shows it after 30 s. |
| `untag_kept` | function | After the delete: renames the kept account to `untagged_name` in a new tab (the deleting page left alone), `_check_saved`, closes the tab. Returns the new name. |
| `_done_text` | private function | The closing box: renames, blank fields filled, notes added, records moved, land holdings changed (and moved), documents copied, "Needs a look (not done):" with each problem, then why the merge account wasn't deleted (blockers) or the question whether to delete it now (and that the kept account is then renamed without "(keep)"). |
| `_shown` / `_shown_count` | private function | A value / count as the window shows it: text or "blank" / number or "none"; `_NOT_SHOWN` for None. |
| `_signer_text` | private function | One signer as "Name (Last Name: …, Capacity: …)", blank parts left out. |
| `_holding_lines` | private function | A land holding's lines: Legal Entity, Section Name, Signers, Title Information. |
| `review_rows` | function | The window's rows: `('heading', text)` and `('row', label, [text per account])` for name, link, `DETAILS`, Parent Account, `CHECKED`, `NOTES`. |
| `_review_window` | private function | Builds (doesn't run) the tkinter window: scrolling grid, a column per account, then each account's land holdings; links open in the browser; "Keep Account N" buttons and Cancel (the window's `.keep` = index picked, else None). Returns a new Tk root, or a Toplevel of `master` (the tests share one hidden Tk, since starting Tk over and over in one process sometimes fails to load its files). |
| `_show_review` | private function | Shows the window in front and waits until it's closed; returns the index of the account to keep, or None (replaced by a recorder in tests). |
| `_SignerRows` | private class | One land holding's signer boxes in the land holdings window: a Signer / Last Name / Capacity row per signer (Capacity lists capacities seen; boxes past `_SIGNER_BOX_LIMITS` disabled), `.boxes` (each row's widgets), `add` (up to 9), `set` (fill, adding rows, blank the rest), `get` (`clean_signers`). |
| `_holdings_window` | private function | Builds (doesn't run) the land holdings window: each land holding of both accounts with its Legal Entity box (existing ones listed, or typed), `_SignerRows`, Copy signers from, Add signer; a "Set every land holding to" row with Apply to all; Continue (`.choices`) / Cancel. Exposes `.editors`, `.all_entity`, `.all_signers`, `.apply_all` for tests. |
| `_show_holdings` | private function | Shows the land holdings window in front and waits; returns its choices, or None if closed (replaced by a recorder in tests). |
| `main` | function | Two arguments (else `ValueError`, also for the same account twice), `ark_page`, `_read_account` both, `_show_review`. If an account was picked: `note_blocks`; stops if a block's section isn't on the kept account; if either account has land holdings, `_show_holdings` (closed: stop) and `holding_plans`; Yes/No box (`_confirm_text`); on Yes a new `ark_page`, `apply_merge`, then `_done_text`: a warning box if anything blocks the delete; otherwise both accounts open in the browser (`webbrowser.open`) and it's a Yes/No box (No by default), and Yes runs `delete_account` in a new `ark_page`, then `untag_kept`, and a box says it's deleted and renamed (a warning box with the link if the rename failed). Returns the accounts. |

### docket_updates.py
**Button:** Docket Updates Sheet (column 1, below SIB). **Folder:** `[Folders] DocketUpdates` (default `Desktop\Docket Updates`). **Reads:** the ND and
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
| `_notify` / `_write_csv` | private function | Message box titled Docket Updates Sheet / CSV as UTF-8 with BOM. |
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
| `main` | function | Workbook → download RW report → compare → write the three CSVs → summary; own boxes for an unusable workbook / report and a CSV locked by Excel. `today` is for tests. Other errors go to `docket_updates_error.log` + a box (titled Docket Updates Sheet). |

### docket_updates_slack.py
**Button:** Docket Updates Slack (bottom of column 1, green; the Slack version of Docket Updates Sheet, which reads the Hearing Dockets workbook). Also Mirror's last step (`mirror_step`).
**Folder:** `[Folders] DocketUpdates` (default `Desktop\Docket Updates`). **Reads:** Slack Web API
(`conversations.history`, `conversations.replies`) with `[SlackCredentials] token`, only the last `_DAYS` (7) days; then, when the messages hold any
case, the Ark RW cases report (`_REPORT_URL`, saved as `Slack_RW_Case_Info.csv`). **Writes:** `Parsed_Slack_Messages.csv`
(ID, Date, Time, Message, Reply To, Slack TS, Link; newest first), `Slack_Docket_Differences.xlsx` (`_DIFF_HEADER`: each
RW record that differs from its Slack case, differing cells highlighted yellow; matches and Not in RW left out) and
`Slack_Docket_Upload.csv` (`_UPLOAD_HEADER`: best-guess Cases Update for each differing record of a case without
sub-cases; **not uploaded**) and `Slack_Not_In_RW.csv` (`_MISSING_HEADER`: the Slack side of every Not in RW case); all overwritten each run. Only the
`Case …` header lines and `(N Wells)` lines (summed into a well count, compared with RW's Number of Wells) are read:
sections and state headings in the messages are skipped. The `Slack_` prefix keeps the files apart
from Docket Updates Sheet's files in the same folder. Read-only on Slack and Ark.

| Name | Kind | Description |
|---|---|---|
| `_DEFAULT_DIR` | constant | `Desktop\Docket Updates`; output folder when `[Folders] DocketUpdates` is unset. |
| `_CHANNEL_ID` / `_USER_ID` | constant | Slack ids of #docket-updates and Cheyanne Winn. |
| `_WORKSPACE_URL` / `_API_URL` | constant | Permalink base (phxenergy.slack.com) and Web API base. |
| `_DAYS` | constant | Days of messages downloaded and compared (7), counted back from the run as `_DAYS` × 24 hours (so a daylight-saving change doesn't shift it); sent to Slack as `oldest`. |
| `_PAGE_SIZE` | constant | Messages per request (200). |
| `_MAX_RETRIES` | constant | Retries per request after HTTP 429 (5). |
| `_KEPT_SUBTYPES` | constant | Message kinds exported (plain, thread broadcast, file share, /me); joins etc. skipped. |
| `_OUTPUT_FILE` / `_OUTPUT_HEADER` | constant | `Parsed_Slack_Messages.csv` and its columns. |
| `_LINK_RE` | constant | Slack link markup `<url\|label>` / `<url>`. |
| `_NO_TOKEN_HELP` | constant | Setup steps shown when there is no token. |
| `_REPORT_URL` / `_REPORT_FILE` | constant | Ark RW cases report (uses Record Id, Case Number, Case Status; Order Status, Number of Wells, Case Notes if there) and its saved name `Slack_RW_Case_Info.csv`. |
| `_RW_WELLS` | constant | `Number of Wells`, the RW report's well count column (found ignoring case and spaces). |
| `_RW_CASE_NOTES` | constant | `Case Notes`, the RW report's notes column (found ignoring case and spaces); shown as RW Case Notes, never compared. |
| `_RW_DATE_SIGNED` | constant | `Date Order Signed`, the RW report column the upload fills (only ever moved forward); a blank one, or one earlier than the order date, differs when Slack has a result. |
| `_UPLOAD_FILE` / `_UPLOAD_HEADER` | constant | `Slack_Docket_Upload.csv` and its columns, named as in the RW report: Record Id, Case Status, Order Status, Number of Wells, Date Order Signed, Case Notes (one the report lacks is left out). |
| `_OPTIONAL_RW` | constant | Report columns compared only when present (Order Status, Number of Wells, Date Order Signed); missing ones are named in the finish box. |
| `_DIFF_FILE` / `_DIFF_HEADER` | constant | `Slack_Docket_Differences.xlsx` and its columns (Differences, case numbers, Record Id, Posted, both sides of status / well count / order date (Slack Order Date, RW Date Order Signed), RW Case Notes, Notes, Link; no applicant or type). |
| `_HIGHLIGHT` / `_YELLOW_FILL` | constant | Difference → the differences columns highlighted for it (Slack side and RW side; Date Order Signed → Slack Order Date + RW Date Order Signed), and the yellow fill used. |
| `_MATCH` / `_DIFFERS` / `_NOT_IN_RW` | constant | Result values. |
| `_MISSING_FILE` / `_MISSING_HEADER` | constant | `Slack_Not_In_RW.csv` and its columns (Case Number, Applicant, Case Type, Case Status, Order Status, Number of Wells). |
| `_SPACING_TYPES` | constant | The five Establish … Spacing RW types. |
| `_TYPE_RULES` | constant | Slack case type pattern → RW Case Types that match (None = no RW type). POOLING and SPACING in either order or joined any way (`and`, `&`, `/`) count as Pooling and Spacing. Not compared with RW since 2026-10-27 and not used by `_parse_header` since 2026-11-04; kept as the Slack type → RW Case Type mapping. |
| `_STATUS_RE` / `_EXPECTED_STATUS` | constant | Board results found in a Slack status, and the RW Case Status / Order Status each one should show (GRANTED, PARTIALLY GRANTED, DENIED = Ordered; DISMISSED = Dismissed). |
| `_STATUS_START_RE` | constant | Where a result word starts (struck-out text included), to split `Pooling GRANTED` (no colon before the status) into type and status. |
| `_ORDER_DATE_RE` | constant | `Board Order Updates from 11/2/2026` heading (singular too, any case); captures the orders' date. |
| `_HEADER_RE` | constant | Case header line pattern (`Case <number> (<applicant>): <type>: <status>`). |
| `_WELLS_RE` | constant | Well group line (`(4 Wells)`, `(5 Wells)-(CHEETAH UNIT)`, `2 wells`); captures the count. |
| `_STALE_NOTE` / `_STALE_SHORT` | constant | Warning that the three comparison files may be from an earlier run, so `Slack_Docket_Upload.csv` shouldn't be loaded: ends every failure box / starts Mirror's Failed line. |
| `SlackError` | class | Slack answered `ok: false`; also raised for a missing token when quiet (Mirror). |
| `RunFailed` | class | Raised by `main` for any error (the original is its cause), with `_STALE_NOTE` (or `_STALE_SHORT` first, quiet). |
| `_notify` | private function | Message box. |
| `_call` | private function | One API GET with the token; waits Retry-After and retries on 429; raises SlackError on `ok: false`. |
| `_paged` | private function | Yields every message of a call, following `next_cursor`. |
| `_is_hers` | private function | Sent by `_USER_ID` and a kept subtype. |
| `_fetch_messages` | private function | Her posts from history after `oldest` (a ts) plus her replies in those posts' threads; keyed by ts so broadcasts appear once. A reply to an older post isn't found. |
| `_clean_text` | private function | Links → label / url, `&amp;` `&lt;` `&gt;` decoded. |
| `_sent_at` | private function | Local datetime of a ts. |
| `_message_id` | private function | `YYYYMMDD-HHMMSS-ffffff` from local send time + Slack's microseconds. |
| `_permalink` | private function | Message link; replies open in their thread. |
| `_rows` | private function | CSV rows newest first; Reply To = parent's ID. |
| `_write_csv` | private function | Header + rows, UTF-8 with BOM (Excel-friendly). |
| `_status` | private function | GRANTED / PARTIALLY GRANTED / DISMISSED / DENIED in a status; ignores `~struck~` text, reads GARNTED. |
| `_rw_types` | private function | RW types matching a Slack type via `_TYPE_RULES` (None when none); not used by the script since 2026-11-04, kept for the type mapping. |
| `_parse_header` | private function | Number(s), applicant (nested parentheses OK), type, status, status as written (`status_text`) and notes of a `Case …` line. Missing colons are fine, also the one before the status (`Pooling GRANTED` splits at `_STATUS_START_RE`). |
| `_parse_message` | private function | Cases of one message: the fields of each `Case …` header line plus `wells`, the sum of the `(N Wells)` lines below it (None if none). Other lines (states, sections, remarks) are skipped, except that a header with no status takes one from the first non-blank line below it. |
| `_order_date` | private function | A message's orders' date as MM/DD/YYYY: its `Board Order Updates from` heading's date, else the message's own date (also when the heading's date can't be read). |
| `_has_info` | private function | A post of a case says more than its number: a status (also an unrecognized one), type, applicant or well count (a bare mention has none). |
| `_fill_blanks` | private function | Copies the status, type, applicant and well count a post leaves blank from an older post of the same case; an unrecognized status as written isn't blank. Returns the fields copied. |
| `_cases_from` | private function | Cases of all messages, each with `posted`, `order_date` (`_order_date`) and link. Posts sharing any case number are one case; the newest post with info (`_has_info`) wins and its blanks are filled from the newest older post that has them (noted as "Status from the … post"); the other posts are noted, and all their numbers are looked up. |
| `_read_rw` | private function | RW report rows with a Record Id (blank-Record-Id continuation rows skipped), column names trimmed and the `_UPLOAD_HEADER` columns found ignoring case; the set of the report's column names. |
| `_well_number` | private function | An RW Number of Wells value as an int (`4`, `4.0`), None when blank or not a whole number. |
| `_rw_date` | private function | An RW date (`10/05/2026`, `2026-10-05`, a time after it is ignored) as a date, None when blank or unreadable. |
| `_candidates` | private function | RW records a case is compared with: each number and its plain `<n>-k` sub-cases, sorted by number; Roman-numeral field-rules sub-cases only when RW has none of those. |
| `_differences` | private function | Status / Order Status / Well Count / Date Order Signed that disagree (all but Status only when the report has the column; Well Count against the case's RW total; Date Order Signed when Slack has a result, DISMISSED too, and RW's is blank or earlier than the case's order date; an unreadable one isn't a difference). Type and applicant aren't compared. |
| `_upload_columns` | private function | The `_UPLOAD_HEADER` columns written: Record Id plus each one the RW report has. |
| `_upload_row` | private function | One upload row + notes: Slack's Case / Order Status (DISMISSED writes a blank Order Status on purpose), well count, and the order date (the `Board Order Updates from` heading's, else the post's) as Date Order Signed when Slack has a result (only moved forward; an unreadable RW date is kept and noted); RW's own value everywhere else; the post's link + space in front of RW's Case Notes unless already there. |
| `_rw_fields` / `_compare` | private function | RW columns of a row (well count as a number when readable, Date Order Signed and Case Notes as given) / all comparison rows as dicts with Result, Upload (the record's upload row or None) and Slack Applicant / Type for `_missing_rows`, + Result counts: one row per candidate record, or Not in RW. Slack's well count is compared with the total of the case's records; a note gives the total when several differ. A differing record of a case with sub-cases or several records gets no upload row and a "review by hand" note. |
| `_write_differences` | private function | Differs rows to `Slack_Docket_Differences.xlsx`: bold frozen filterable header, `_HIGHLIGHT` cells yellow, clickable Link, column widths fitted. |
| `_missing_rows` | private function | `Slack_Not_In_RW.csv` rows from the comparison rows: Not in RW only, Slack result as RW Case Status / Order Status via `_EXPECTED_STATUS` (blank when none), Slack well count. |
| `_summary` / `_compare_summary` | private function | Finish message parts: Slack count, the 7-day window, date range, path / comparison counts, upload rows and held-back records, report columns not compared or left out of the upload, differences / upload / Not in RW paths. |
| `main` | function | `main(now=None, quiet=False)`: runs `_run`; any error is raised again as `RunFailed` with the stale-files warning (`_STALE_NOTE` after the error for `run_button`'s box; one line starting with `_STALE_SHORT` when quiet, for Mirror's report). |
| `_run` | private function | `_run(now, quiet)`: token → fetch the last `_DAYS` days (window ends at `now`, for tests; default the current time) → write messages → (if any case) download RW report → compare → write differences workbook, upload CSV (not uploaded) and Not in RW → summary; own boxes (ending in `_STALE_NOTE`) for no token, Slack errors and a file locked by Excel; when `quiet` (Mirror) no boxes, and those three raise. Returns (cases, differing RW records, upload rows, cases not in RW), or None after a problem box. Other errors go to `docket_updates_slack_error.log` + a box (titled Docket Updates Slack). |
| `mirror_step` | function | Mirror's step: `main(quiet=True)` → Needs review ("N RW records to fix (M in Slack_Docket_Upload.csv, not uploaded), K cases not in RW: review …", naming the files) or No changes (no cases / no differences in the last 7 days). |

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
| `_blocked_sync_playwright` / `_blocked_connect` / `_blocked_getaddrinfo` / `_fake_messagebox` / `_fake_task_dialog` | private function | Installed over Playwright, `socket.connect`, `socket.getaddrinfo` (DNS), `MessageBoxW` and `mirror._task_dialog` (records the dialog, and its text without link markup as a message box). |
| `_MSGBOXES` | global | Recorded message boxes. |
| `msgboxes` / `_MsgBoxes` / `_fake_messagebox` | fixture / class / private function | List of `(title, text)` the script tried to show; Yes/No boxes answer Yes, or the next of `msgboxes.answers` (e.g. `[7]` = No). |
| `_TASK_DIALOGS` / `task_dialogs` | global / fixture | Recorded Mirror report task dialogs: `(title, content with <a href> links, icon)`. |
| `_fake_webbrowser_open` / `_BROWSER_TABS` / `browser_tabs` | private function / global / fixture | Installed over `webbrowser.open`: records each URL a script opens in the browser (Merge's review before deleting), so no real tab opens. |
| `_fake_show_review` / `_Reviews` / `_REVIEWS` / `reviews` | private function / class / global / fixture | Installed over `merge._show_review`: records the accounts each Merge review window would show, so no window opens and waits, and answers `reviews.keep` (the account picked to keep; default None = closed). |
| `_fake_show_holdings` / `_Holdings` / `_HOLDINGS` / `holdings` | private function / class / global / fixture | Installed over `merge._show_holdings`: records `(accounts, keep)` of each land holdings window and answers `holdings.choose(accounts, keep)` (default: every land holding as it is now; `None` = closed). |
| `Folders` / `folders` | class / fixture | Replaces `ark_common.read_folder` so each key maps to `tmp_path/<key>`. |
| `fake_ark` | fixture | Installs a `fakes.FakeArk`. |
| `no_real_makedirs` | fixture | Makes `os.makedirs` a no-op (for scripts run as buttons in test_error_reporting). |

### tests/fakes.py

| Name | Kind | Description |
|---|---|---|
| `write_csv` / `read_csv` | function | Write / read a CSV as lists of rows. |
| `locked_like_excel` | function | Context manager: holds a file open the way Excel does (read allowed, write refused), for "close it in Excel" tests (PPIQ, Index). |
| `FakeArk` | class | Fake Ark + Playwright: `serve(url, rows, filename, records=…)` (`records`: the Total Record Count its page shows, kept in `record_counts`; default its data rows, None = unreadable); records `downloads`, `logins`, `sessions_saved`, `waited_ms`; `needs_login` = signed-out domains. Replaces `ark_common.trigger_download` (still asking about a large report via `ark_common.confirm_download` first; a No downloads nothing) / `login` and `playwright.sync_api.sync_playwright` (which `ark_common.ark_page` uses), plus any script's own `sync_playwright`. |
| `FakePage` / `FakeContext` / `FakeBrowser` / `FakeDownload` | class | The Playwright objects the scripts touch; `FakePage` raises on any call it doesn't model. `FakePage.title()` / `get_by_text("… Not Found")` / `evaluate(merge._READ_JS)` model account and land holding pages (below). |
| `FakeArk.serve_account` / `serve_holding` / `records` / `pages` / `evaluated` | method / attribute | Serve an account (with `related`: the contacts, offers, title requests and calls it holds) / land holding page: name in its title ("Account - " / "Land Holding - ") and what `merge._READ_JS` reads (`pages[record id]`: a list of reads in turn, the last repeating, for a page still loading); `None` name = a page that never loads; an id not served shows "Account Not Found" / "Land Holding Not Found". `evaluated` records each read. Used by test_merge. |
| `account_page` / `holding_page` | function | One `_READ_JS` read laid out like Ark's page. Account: Quick Reference counts (plus History, Webinars and the tables Ark gives the same id), `DETAILS` and notes fields twice with an unrelated "Notes" field, land holding links twice. Land holding: its fields twice, the `SIGNER_LABELS` fields (asserts a signer part Ark has no field for is blank). |
| `record_at` / `_CountLocator` | function / class | (kind, record id) of an account or land holding URL; a locator with only `count()`. |
| `HOLDING_URL` / `CHECKED_DEFAULT` / `_TITLE` / `_NOT_FOUND` / `_PATHS` | constant | Land holding page URL; `merge.CHECKED`; title prefix, Not Found message and URL path of each record kind. |
| `FakePage.get_by_role` / `locator` / `reload` / `close` / `context` / `expect_response` / `drawer` | method / attribute | An account, contact, offer, title request or call page's Edit button and edit window; the Quick Reference entries in page order (`_QuickEntries`: `.nth(i)`, or with `has_text` the first whose label contains it, any case, as Playwright matches; click opens the side drawer on its label, `drawer`; `evaluate(merge._DRAWER_JS)` lists its links); reload (cancels a save still on its way); `goto` / `reload` / `close` cancel a delete still on its way from that page; `context` is the `FakeContext` that opened it (`new_page` opens another tab); Playwright's `expect_response` over `FakeArk.responses`. |
| `_EditButton` / `_EditDialog` / `_EditTab` / `_EditBox` / `_SaveButton` / `_QuickEntries` / `_QuickEntry` | class | Edit opens the window (`FakeArk.editing`): an account's name, both notes and its `ACCOUNT_DETAIL_BOXES` (Details tab), or a record's Account; tabs switch (with `FakeArk.tab_text_elsewhere`, a non-exact text match is a label that switches nothing); the Account Name / notes / detail boxes (`_NAME_FIELD` / `_NOTE_BOXES` / `_HOLDING_BOX` pattern, merge's selectors) fill; Save closes it and, if something changed, answers `UPDATE_URL` and leaves the change pending like Ark. |
| `_AccountBox` / `_LookupPart` / `_LookupTag` / `_LookupX` / `_LookupSearch` / `_LookupOptions` | class | A record's Account lookup (`_ACCOUNT_BOX`): the tag shows the account's name; the x empties it; typed text lists the served accounts with exactly that name; a pick sets the record's Account. |
| `_RELATED_PATHS` / `RELATED_URL` / `_ACCOUNT_BOX` / `_NOTE_BOXES` | constant | Page path of each `merge.MOVED` kind (its kind in `record_at`); a record page URL; merge's selectors. |
| `_ResponseInfo` / `_FakeResponse` / `_FakeRequest` / `UPDATE_URL` | class / constant | What `expect_response` yields; an Ark API answer (url, status, ok, request body); Ark's update call. |
| `FakeArk.editing` / `saves` / `moves` / `owned` / `responses` / `reloads` / `pending` / `cancelled` / `store_pending` | attribute / method | The open window; each account save stored `(record id, name, Account Notes, Call Notes)`; each record moved `(record id, from, to)`; which account holds each record (`serve_account(related=…)`); API answers; reloads; a save sent but not stored yet (stored when the page waits, cancelled by a reload); `store_pending` stores it (account: page fields; record: owner and both accounts' Quick Reference counts). |
| `FakeArk.save_stuck` / `save_ignored` / `save_status` / `edit_boxes` / `edit_never_loads` / `refuse_moves` / `search_lag` / `pick_ignored` / `drawer_limit` / `drawer_page` | attribute | Break things: Save never answers / answers OK but changes nothing / answers with this status; how many Account Name / notes / Account lookup boxes a window shows; account boxes stay empty; records whose save gets 403; the lookup never lists the typed account; a pick doesn't take; the drawer lists at most this many (however far it's scrolled); the drawer lists this many more per scroll (`merge._SCROLL_JS`, `FakePage.scrolls`). |
| `FakeArk.documents` / `add_document` / `downloaded_documents` / `uploads` / `served_dir` | attribute / method | Each account's documents (`serve_account(documents=…)`: a name, or (listed name, Ark's download name, bytes)); listing one, as an upload does; names downloaded; `(account, file name, bytes)` uploaded; where download contents are written. |
| `FakeArk.download_buttons` / `ready_limit` / `upload_status` / `listed_as` | attribute | Download buttons per document row; "Ready to Upload" shown under at most this many files; the upload's HTTP status; file name → name Ark lists the upload under (`None` = not listed). |
| `FakeArk.deleted` / `confirming` / `confirm_buttons` / `delete_status` / `delete_ignored` / `delete_silent` / `delete_slow` / `pending_delete` / `cancelled_deletes` / `delete_now` / `store_pending_delete` / `tab_text_elsewhere` / `tabs_not_exact` / `pages_closed` | attribute / method | Accounts deleted; the account whose confirmation box is open; Delete buttons in that box; the delete's HTTP status; Ark answers OK but keeps the account; the box's Delete sends nothing; a `READ_URL` call naming the account answers first and the delete waits until a page waits (`pending_delete`, carried out by `store_pending_delete`; cancelled into `cancelled_deletes` if its page leaves first); `delete_now` carries one out; edit windows have other text holding each tab's name (`tab_text_elsewhere`); no tab's text is exactly its name (`tabs_not_exact`); pages the script closed. |
| `FakePage.expect_download` / `clicked_document` / `_Drawer` / `_AddButton` / `_DocRows` / `_DownloadButton` / `_FileInput` / `_UploadButton` / `_DeleteButton` / `_ConfirmDelete` | method / attribute / class | The Documents drawer (`evaluate(merge._DOC_ROWS_JS)` lists its names), each row's download button and the download it starts; Add, the upload window's file picker, "Ready to Upload" and Confirm and Upload (`UPLOAD_URL`); an account page's Delete and the confirmation box's Delete (`DELETE_URL`, a stand-in for Ark's call). |
| `_DOC_ROW` / `_DOWNLOAD_BUTTON` / `UPLOAD_URL` / `DELETE_URL` / `READ_URL` | constant | merge's document row and download button selectors; Ark's upload call; the fake's delete call; a fake call that names the account but only reads it (`FakeArk.delete_slow`). |
| `SIGNER_LABELS` | constant | A land holding's signer fields as Ark has them: Signer 1–9, Signer 1–2 Last Name, Signer 1–3 Capacity. |
| `_DRAWER_PATHS` / `_HOLDING_BOX` / `_HOLDING_EDIT_TABS` | constant | Page path of what each side drawer lists (the `MOVED` kinds and Land Holdings); merge's land holding box selector (regex, group 1 = label); the land holding edit window's fields (Legal Entity, `SIGNER_LABELS`) and the tab each is on. |
| `FakeArk.holding_saves` | attribute | `(land holding id, its account, {field label: value})` of each land holding Save stored. A land holding's edit window (`_EditButton` on a land holding page) has its Account lookup, Legal Entity and `SIGNER_LABELS` boxes (`edit_boxes` by label breaks one); its Save moves it (both accounts' Land Holdings counts) and updates its page. `serve_account(holdings=…)` also puts its land holdings in `owned` (the Land Holdings drawer). |
| `ACCOUNT_DETAIL_BOXES` | constant | The Edit Account window's Details boxes a merge can fill: Mailing Street / City / State / Zip Code, Confirmed Phone Number, Confirmed Email Addresses. |
| `FakeArk.detail_saves` / `stale_counts` | attribute | `(account id, {label: new value})` of each account Save that changed `ACCOUNT_DETAIL_BOXES` (its page shows them after); Quick Reference labels whose count doesn't change when records move (as Ark's Land Holdings count lags). |
| `LOGIN_PAGE` | constant | URL a signed-out `FakePage` lands on. |
| `Recorder` | class | Callable that records its calls; replaces `ark_common.upload`, `_login`, etc. |
| `LOADER_TEXTS` | constant | Data Loader status texts and whether `ark_common.upload` should stop waiting at each. |
| `FakeLoaderPage` / `_NullLocator` | class | Page `ark_common.upload` can drive with no browser; records `get_by_text` patterns in `text_patterns`, `get_by_role` (role, name) in `roles`, `goto` URLs in `visited`. |
| `FakeReportPage` / `_ReportLocator` / `_FileButtons` / `_TextLocator` / `_FakeDownloadInfo` | class | Report page and notifications panel `ark_common.trigger_download` can drive with no browser: `old_files` (finished exports already listed), `others` (e.g. `STUCK_UPLOADS`), `new_file` listed at the top after `ready_after` checks (None: never), `slow_panel` (empty at the first look), `count_texts` (what the Total Record Count card reads at each `evaluate`, the last repeating; None = no card; default a 13-record report; `count_reads` counts them). Records `clicks` as (element, `waited_ms` then), `checks` after Download, `clicked_file`, total `waited_ms`, `download_timeout` (the ms `expect_download` was given). |
| `ready_card` | function | Text of Ark's "Your file is ready for download!" notification for a report at a time, as `trigger_download` reads it. |
| `STUCK_UPLOADS` | constant | The three Data Loader notifications stuck at "0% Complete" in the real panel since 2026-10-20. |

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
| `win_fakes.h` | header | Redefines `SHGetFolderPath`, `MessageBox`, `ShellExecute` to fakes before the tested .cpp is included. Declares the file helpers and `OwnerEnabledWhenPopupCloses`. |
| `test_main.cpp`: `wmain` | function | Runs every test with a fresh folder; prints `PASS` / `FAIL` / `KNOWN` / `FIXED` lines. |
| `test_main.cpp`: `g_sandbox`, `g_testDir`, `g_messageBoxes`, `g_shellOpened` | global | Run folder, per-test folder, recorded boxes and opened files. |
| `test_main.cpp`: `Fake_SHGetFolderPath`, `Fake_MessageBox`, `Fake_ShellExecute` | function | The fakes. |
| `test_main.cpp`: `ResetDir`, `WriteBytes`, `ReadBytes`, `FileExists`, `Utf8`, `FromUtf8`, `SawMessageBox` | function | File and string helpers for tests. |
| `test_main.cpp`: `OwnerEnabledWhenPopupCloses` (with `WatchPopupProc`, `s_watchedOwner`, `s_ownerEnabledAtDestroy`, `s_popupProc`) | function | Opens a hidden popup of a class under a hidden, disabled owner, runs a close callback, and returns whether the owner was enabled again when the popup got `WM_DESTROY` (else Windows brings another app to the front). Unregisters the class afterwards. Used by each dialog's `*_window_reenables_the_launcher_before_it_closes` test. |
| `test_organize.cpp` / `test_rename.cpp` / `test_settings.cpp` / `test_mirror.cpp` / `test_merge.cpp` | test file | `#include` the matching .cpp to test its static functions (`test_mirror.cpp` also runs `cmd.exe` one-liners through `RunScriptLines`; `test_merge.cpp` checks the Merge link parsing). Each also has a `*_window_reenables_the_launcher_before_it_closes` test that opens its dialog hidden (`OwnerEnabledWhenPopupCloses`). Organize and Rename tests point their folder setting at the test folder with `SetSetting`. |

### Test files

| File | Covers |
|---|---|
| `test_wiring.py` | Static checks of main.cpp, settings.cpp, scripts and docs: every folder/file a script reads has a Settings row and vice versa, the sandbox covers every folder, every button using the Ark login is locked during Mirror (xfail for the ones using it only through `ark_page`, see KNOWN_ISSUES), `COLUMNS` + `CORNER_BUTTONS` place every shown button once, main.cpp's column headers match `COLUMN_HEADERS`, `g_hiddenButtonIds` is the `HIDDEN` buttons and their handlers and layout lines are still there, every script compiles and imports, `default_organize_rules.ini` has valid `[Rules]` columns and `ColumnSchema=2`. |
| `test_app_buttons.py` | Builds the app with stand-in scripts and clicks every button (a `HIDDEN` one must be hidden, disabled, and launch nothing); fills in the Merge window (`_fill_merge_window`, `_dlg_text`): valid links run merge.py with both ids, bad ones keep it open with the reason; checks each button sits in its `COLUMNS` column and order, under its `COLUMN_HEADERS` label. The mirror.py stand-in honors `--stop-file`; flag files next to it make it hold its first step 30 s (`mirror_long_hold`), stay alive after `@FINISHED` like the report box (`mirror_report_hold`), or exit early (`mirror_crash`). |
| `test_cpp.py` | Builds and runs the C++ tests; Python reads the INI that settings.cpp writes. |
| `test_error_reporting.py` | Every button script shows an error box on failure (title, error and log path); the map scripts name a missing package; `ark_common.run_button`. |
| `test_ark_common.py` | `ark_common.upload` (the shared Data Loader wizard): picks the given dataset (whole name, any capitalization), confirms with the operation, stops at the "X of Y" row counter; `trigger_download` takes the new file once Ark lists it (not an older one or one listed before the click), isn't held up by stuck "0% Complete" notifications, reopens the panel while waiting and fails after the time limit; `_card_time` reads notification stamps (also run-together text); `check_columns` accepts the expected header and rejects another report's; large downloads: `record_count` reads the Total Record Count card (commas; a rounded or missing count is unreadable; waits for two equal readings), `trigger_download` asks before Ark is asked for a report of `LARGE_DOWNLOAD_ROWS` or more or with an unreadable count (No: `DownloadCancelled`, nothing requested; Yes: downloads; under the limit: no box), the box is a topmost Yes/No with No as default and `@WAITING` / `@RESUMED` around it, and `run_button` shows a cancel as "stopped" with no log; settings with `%` read as typed; `read_folder` reads only its own key; `ark_page` logs in and keeps the session after an error. |
| `test_mirror.py` | Mirror's runner (fake steps): progress tags, failures carried on, report groups, archive file, report box (task dialog with clickable links and archive path, message-box fallback, link clicks, struct layout vs. the Windows headers), a refused large download failing only its step; the child-process runner and its time limit, paused while a large-download box waits (harmless `python -c` children); Stop via the stop file (Not run steps, the running child's tree killed); Index step; one full run of the real steps against the fake Ark. An autouse fixture resets `mirror._stop_file` per test. |
| `test_ppiq.py`, `test_index.py`, `test_str_verification.py`, `test_tpp_lhpp.py`, `test_nai_download.py`, `test_cost_to_extend.py`, `test_case_matchup.py`, `test_case_unit_names.py`, `test_section_id_blank.py`, `test_docket_updates.py`, `test_docket_updates_slack.py`, `test_deceased.py`, `test_qq_checker.py`, `test_close_dates.py`, `test_case_update.py`, `test_map.py`, `test_merge.py` | One button's script each (see the table in [TESTING.md](TESTING.md#button--tests)). |
