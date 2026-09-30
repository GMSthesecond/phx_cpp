# Code Index

Every function, global, constant and type, grouped by file. Local variables are left out.
Each entry is also commented in the source. Search the name to find it (no line numbers,
since they go stale). For how the pieces fit together, see [ARCHITECTURE.md](ARCHITECTURE.md).

**Contents**
- C++: [main.cpp](#maincpp) · [settings.cpp](#settingscpp--settingsh) · [organize.cpp](#organizecpp--organizeh) · [rename.cpp](#renamecpp--renameh)
- Python (shared): [ark_common.py](#ark_commonpy) · [operator_colors.py](#operator_colorspy)
- Python (Ark): [ppiq.py](#ppiqpy) · [tpp_lhpp.py](#tpp_lhpppy) · [download_report.py](#download_reportpy) · [cost_to_extend.py](#cost_to_extendpy) · [str_verification.py](#str_verificationpy) · [close_dates.py](#close_datespy) · [non_hbp_mi.py](#non_hbp_mipy) · [case_matchup.py](#case_matchuppy)
- Python (other): [deceased.py](#deceasedpy) · [doc_inventory_*.py](#doc_inventory_roosevelt--richland--dividepy) · [map_builder.py](#map_builderpy) · [map_uploader.py](#map_uploaderpy) · [box_copy_deals.py](#box_copy_dealspy)

---

## C++

### main.cpp
Entry point, main window, button dispatch.
**Reads:** settings.ini via `LoadFolders`. **Launches:** every button script.

| Name | Kind | Description |
|---|---|---|
| `ID_TITLE`, `ID_BUTTON_*` | macro | Control ids for the title and each button; grouped by column. |
| `ID_PROGRESS_INDEX`, `ID_LABEL_INDEX_STATUS` | macro | Index progress bar and status label (hidden unless Index is running). |
| `g_hTitleFont` / `g_hButtonFont` | global | Title (32px bold) and button (13px) Segoe UI fonts; created in WM_CREATE. |
| `g_hBgBrush` / `g_hYellowBrush` | global | Window background gray; fill for unwired buttons. |
| `g_hwndMain` | global | The main window. |
| `g_unwiredButtonIds` | static global | Buttons with no handler yet; drawn yellow. |
| `IsUnwiredButton` | function | True if the id is in `g_unwiredButtonIds`; makes the button owner-drawn. |
| `MapUploadThreadArgs` | struct | `hwnd` + `exeDir` passed to `RunMapThenUpload`; deleted by the thread. |
| `RunMapThenUpload` | function (thread) | Map button: runs map_builder.py, waits, then map_uploader.py; relabels the button. |
| `IndexRunThreadArgs` | struct | `hwnd` + `exeDir` passed to `RunIndexScripts`. |
| `RunOneIndexScript` | static function | Runs one doc_inventory script with stdout piped; finds `@PROGRESS` / `@DONE` anywhere in a line; returns processed count or -1. |
| `RunIndexScripts` | function (thread) | Index button: runs the three county scripts in order, then shows a summary. |
| `LayoutControls` | function | Positions all controls in 5 columns; called on WM_CREATE and WM_SIZE. |
| `WndProc` | wndproc | Main window messages: create controls, layout, colors, owner-draw, button clicks, cleanup. |
| `WinMain` | function | CoInitialize, `LoadFolders`, register window classes, create window, message loop. |

### settings.cpp / settings.h
Settings dialog for the folders the Python scripts use.
**Opened by:** Settings. **Reads/Writes:** settings.ini `[Folders]` DataMeetingDownload, STRVerification, CloseDates, Maps.

| Name | Kind | Description |
|---|---|---|
| `ID_FOLDER_*_LABEL` / `ID_FOLDER_*_CHANGE` | macro (settings.h) | Path label and Change button id for each folder row. |
| `SETTINGS_CLASS` | constant | Window class name `"SettingsWindow"`. |
| `s_hwndParent` | static global | Main window, disabled while Settings is open. |
| `s_hwndSettings` | static global | Open Settings window or NULL; prevents duplicates. |
| `s_folderDMD` / `s_folderSTR` / `s_folderCD` / `s_folderMaps` | static global | Current folder paths; defaults are hardcoded Desktop paths. |
| `GetIniPath` | static function | Builds the settings.ini path; creates the PhoenixLandDept folder. |
| `LoadFolders` | function | Called by WinMain; reads the four `[Folders]` keys. Never writes. |
| `SaveFolders` | static function | Writes all four `[Folders]` keys after a change. |
| `PickFolder` | static function | COM `IFileDialog` folder picker; true on OK. |
| `SettingsProc` | wndproc | Builds four rows; Change → `PickFolder` → `SaveFolders`; re-enables parent on close. |
| `RegisterSettingsClass` | function | Called by WinMain. |
| `OpenSettings` | function | Called by Settings button; disables parent, shows the popup. |

### organize.cpp / organize.h
Personal finance categorizer: `Desktop\Organization\Data.CSV` → `Organized.CSV`.
**Opened by:** Organize. **Reads/Writes:** `organize_rules.ini` `[Rules]`, `[ScrubWords]`, `[Meta]`.

| Name | Kind | Description |
|---|---|---|
| `NUM_COLS` | constant | 15 output categories. |
| `IGNORE_COL` | constant | 15 = "Ignore" (never written to output). |
| `COLS` | constant | Category names in output order (Income … Savings). |
| `DATA_PATH` / `OUTPUT_PATH` | constant | Hardcoded input/output CSV paths. |
| `g_rules` | static global | Uppercased snippet → column index. |
| `GetRulesPath` | static function | Path to organize_rules.ini. |
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
| `Trim` / `ToUpper` / `TitleCase` | static function | String helpers. |
| `g_scrubWords` | static global | Words removed from notes. |
| `LoadScrubWords` | static function | Loads `[ScrubWords]`; writes missing defaults. |
| `EscapeRegex` | static function | Makes a scrub word regex-literal. |
| `ScrubDesc` | static function | Cleans a bank description into a short note. |
| `SplitCSV` / `EscCSV` | static function | CSV split / quote. |
| `Date` | struct | y/m/d. |
| `DateLt` / `DateLe` / `DaysInMonth` / `NextDay` | static function | Date math for the day-by-day output. |
| `ParseDate` / `DateKey` / `DateDisplay` | static function | Parse M/D/YYYY or ISO; map key; display text. |
| `ParseAmount` / `FmtAmount` | static function | Currency parse / format (0 → blank). |
| `FindRule` | static function | First `g_rules` snippet contained in the description, or -1. |
| `DayRow` | struct | Per-day totals `c[15]` and notes `notes[15]`. |
| `RunOrganize` | static function | Whole pipeline: read, categorize, accumulate, write. |
| `RegisterOrganizeClass` | function | Called by WinMain. |
| `OpenOrganize` | function | Called by Organize button; runs `RunOrganize`. |

### rename.cpp / rename.h
Bulk file renamer + MP3 artist tag editor, driven by `Desktop\Rename\rename.csv`.
**Opened by:** Rename.

| Name | Kind | Description |
|---|---|---|
| `FOLDER_PATH` / `CSV_NAME` | constant | Hardcoded working folder; `rename.csv`. |
| `CsvPath` | static function | Full path of rename.csv. |
| `Trim` / `SplitCSV` / `EscCSV` | static function | Copies of organize.cpp helpers. |
| `HasExtension` / `SameNameCI` | static function | Case-insensitive extension / name compare. |
| `ReadWholeFile` / `WriteWholeFile` | static function | Whole-file byte I/O. |
| `Synchsafe32` / `EncodeSynchsafe32` / `BigEndian32` / `EncodeBigEndian32` | static function | ID3 integer encodings. |
| `Id3Frame` / `Id3v2Tag` | struct | Raw ID3v2 frame; parsed tag. |
| `ParseID3v2` / `BuildID3v2` | static function | Parse / rebuild an ID3v2.3/2.4 tag. |
| `DecodeID3Text` / `EncodeID3TextUTF16` | static function | ID3 text frame decode / encode. |
| `ID3V1_SIZE` | constant | 128-byte ID3v1 block. |
| `ReadID3v1Artist` / `ReadMp3Artist` / `WriteMp3Artist` | static function | Read artist (v2 then v1); write new artist to v2 + v1. |
| `WriteUtf8` | static function | Write a wide string as UTF-8. |
| `GenerateCSV` | static function | Button 1: list files and artists into rename.csv, open it. |
| `ApplyRenames` | static function | Button 2: apply renames (`MoveFile`) and artist changes. |
| `ID_RN_*` | macro | Dialog button ids (601–603). |
| `g_renameDone` | static global | Ends `OpenRename`'s modal loop. |
| `RENAME_CLS` | constant | Window class `"RenameDlg"`. |
| `RenameProc` | wndproc | Generate / Apply / Close. |
| `RegisterRenameClass` | function | Called by WinMain. |
| `OpenRename` | function | Called by Rename button; modal dialog loop. |

---

## Python — shared

### ark_common.py
Imported by every Ark script, case_matchup and the map scripts.

| Name | Kind | Description |
|---|---|---|
| `_APP_DIR` / `_INI_PATH` | constant | `%APPDATA%\PhoenixLandDept` and its settings.ini. |
| `_SESSION` | constant | session.json (Playwright login state); used directly by 7 scripts. |
| `_CHEVRON_PATH` | constant | SVG path used to find Ark's report dropdown. |
| `read_credentials` | function | Ark `(username, password)` from `[Credentials]`. |
| `read_enverus_credentials` | function | Enverus `(identifier, password)` from `[EnverusCredentials]`. |
| `read_folder` | function | `[Folders]` value for a key, or the default. |
| `login` | function | Microsoft SSO sign-in, then wait for `success_url`. |
| `trigger_download` | function | Open report → Download → wait → pull file from notifications; returns Playwright Download. |

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

---

## Python — Ark scripts

### ppiq.py
**Button:** PPIQ. **Writes:** 4 report CSVs + `Update_Inverted.csv` in `Desktop\PPIQ`.

| Name | Kind | Description |
|---|---|---|
| `_PPIQ_FOLDER` | constant | Hardcoded output folder. |
| `_PPIQ_URLS` | constant | (report URL, generation wait ms) × 4; the 4th is on the phoenixenergy.com domain. |
| `_download_files` | private function | Log in and download all 4 reports (30s apart); re-login on the domain switch. |
| `_run_analysis` | private function | Cross-check the 4 CSVs for price-paid / queue issues; write `Update_Inverted.csv`. |

### tpp_lhpp.py
**Button:** TPP-LHPP. **Writes:** `PHX_Price_Paid_Export.xlsx` in `Desktop\TPP-LHPP`.

| Name | Kind | Description |
|---|---|---|
| `_notify` | private function | Message box (error channel). |
| `_OUT_DIR` | constant | Hardcoded folder. |
| `_REPORT_URLS` | constant | Offers report (15s wait), LHT report (120s wait). |
| `_OFFERS_FILENAME` / `_LHT_FILENAME` / `_EXPORT_FILENAME` | constant | Expected download names; output name. |
| `_YELLOW_FILL` | constant | Highlight for exported cells. |
| `_download_files` | private function | Log in and download both reports. |
| `_find_file` | private function | Case-insensitive file lookup in `_OUT_DIR`. |
| `_process_offers` | private function | Offers CSV → `{id: TPP, status, close date}`. |
| `_process_lht` | private function | Sum LHT values per offer. |
| `_export` | private function | Offers where LHT and TPP differ by more than $1 → xlsx. |
| `main` | function | Download → process → export. |

### download_report.py
**Button:** Data Meeting Download. **Folder:** `[Folders] DataMeetingDownload`.

| Name | Kind | Description |
|---|---|---|
| `_REPORT_URLS` | constant | The two Data Meeting reports. |
| `_trigger_and_save` | private function | Download one report; save with today's date in the name. |
| `main` | function | Log in if needed, download both, save session. |

### cost_to_extend.py
**Button:** Cost to Extend. **Folder:** `[Folders] CostToExtend`. **Uploads to Ark (Landholdings Update).**

| Name | Kind | Description |
|---|---|---|
| `_notify` | private function | Message box (error channel). |
| `_REPORT_URL` / `_UPLOAD_URL` | constant | Cost-to-extend report; Data Loader page. |
| `_to_float` | private function | Currency string → float (blank → 0). |
| `_upload` | private function | Drive the Data Loader wizard; wait for "X of X". |
| `main` | function | Download, flag rows where NMA × $/acre is off by more than $10, write CSV, upload. |

### str_verification.py
**Button:** STR Verification. **Folder:** `[Folders] STRVerification`. **Writes:** `Error_Report.csv`.

| Name | Kind | Description |
|---|---|---|
| `_REPORT_URL` | constant | Ark "Check STR" report. |
| `_OUT_DIR` / `_INPUT_PATH` / `_ERROR_PATH` | constant | Working folder; downloaded report; error report. |
| `_download_report` | private function | `trigger_download` (60s wait) → `_INPUT_PATH`. |
| `_process` | private function | Check Section Name vs S-T-R and AOI containment; write error report. |
| `main` | function | Log in → download → `_process`. |
| `_LOG_PATH` | global | Traceback log (defined in `__main__`). |

### close_dates.py
**Button:** Close Date. **Folder:** `[Folders] CloseDates`. **Uploads to Ark (Landholdings Update).**

| Name | Kind | Description |
|---|---|---|
| `_notify` | private function | Message box. |
| `_REPORT_URL` / `_UPLOAD_URL` | constant | Close-date report; Data Loader. |
| `_target_dates` | private function | Set of close dates: yesterday, or Fri–Sun when run on Monday. |
| `_parse_date` | private function | Tries 4 date formats. |
| `_upload` | private function | Data Loader wizard (copy of non_hbp_mi's). |
| `main` | function | Download, keep rows closed on the target dates (skip Deferred), write CSV, upload. |

### non_hbp_mi.py
**Button:** Case Update. **Folder:** `[Folders] NonHBPMI`. **Uploads to Ark (Units Update).**

| Name | Kind | Description |
|---|---|---|
| `_REPORT_URL` / `_UPLOAD_URL` | constant | Units report; Data Loader. |
| `_upload` | private function | Data Loader wizard (dataset "Units"). |
| `main` | function | Download, stamp today's date on every row, write CSV, upload. |

### case_matchup.py
**Button:** Case Matchup. **Folder:** `[Folders] CaseMatchup`. **Reads:** `All_Cases.csv` and the units docket CSV. **Writes:** `Case_Matchup_Export.<date>.csv`.

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
| `_mentions_case` / `_mentions_case_denied` | private function | Docket-note text checks. |
| `_build_notes` | private function | Rule engine: discrepancy notes for one unit. |
| `_process` | private function | Match cases to units; call `_build_notes`. |
| `_write_output` | private function | Write the export CSV. |
| `main` | function | Read → process → write → summary box. |

---

## Python — other

### deceased.py
**Button:** Deceased. **Folder:** hardcoded `Desktop\Bring out your dead`. No functions: runs top to bottom.
Reads the deceased account CSV and `heir_template.csv`; writes `deceased_upload.csv`, splitting each holding by heir share.

| Name | Kind | Description |
|---|---|---|
| `deceased` | global | Deceased holdings keyed by Legal Entity + Section Name. |
| `heirs` | global | Output rows keyed by heir + section + type + source + deceased. |
| `user_heirs` | global | Heirs from the template; "percentage ownership" is a fraction. |
| `deceased_path` / `heir_csv_path` / `output_csv_path` | constant | Hardcoded file paths. |

### doc_inventory_roosevelt / richland / divide.py
**Button:** Index (in that order). Scans Box county folders for PDFs not yet in
`Index of Scanned Docs.xlsx`; writes `Desktop\Steph Suko\<County>.csv` and appends rows to the county tab.
The three files are near-copies (see KNOWN_ISSUES).

| Name | Kind | Description |
|---|---|---|
| `ROOTS` | constant | Box folders to scan. |
| `OUTPUT_CSV` / `EXCEL_PATH` / `EXCEL_SHEET` / `EXCEL_COLUMN_INDEX` | constant | Output CSV; index workbook, tab, filename column. |
| `FOLDER_NAME_MODE` / `PDF_ONLY` | constant | Folder column source; PDFs only. |
| `win_long` / `win_strip_long` | function | Add / remove the `\\?\` long-path prefix. |
| `clean_name` | function | Divide only; unused. |
| `load_indexed_names` | function | Names already in the tab (Richland: without extension). |
| `iter_files` | function | `os.walk` generator. |
| `count_files_to_process` | function | Pre-count for the progress total (unused in Richland). |
| `Progress` | class | Throttled printer; emits `@PROGRESS done total` (Richland: total -1). |
| `get_pdf_page_count` | function | PyPDF2 page count, or a status string. |
| `folder_label_for_path` | function | Folder column value. |
| `append_rows_to_excel` | function | Back up to `.bak`, append rows, save. |
| `main` | function | Scan, write CSV, print `@DONE n`, append to Excel. |

### map_builder.py
**Button:** Map (step 1). **Folder:** `[Folders] Maps`. Reads `Units.csv`; queries BLM PLSS; writes `YYYY.MM.DD. <Operator>.zip` shapefiles.

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
**Button:** Map (step 2). Uploads the dated zips to Enverus, colors each layer, saves the "Phoenix Units" workspace,
then moves the uploaded zips to `Maps\Uploaded`.

| Name | Kind | Description |
|---|---|---|
| `_MAPS_DIR` | constant | Where map_builder leaves zips. |
| `_UPLOADED_DIR` | constant | `Maps\Uploaded`; successfully uploaded zips are moved here so they aren't re-uploaded. |
| `_LOGIN_URL` / `_APP_URL` | constant | Enverus login; DI map app. |
| `_NAME_PATTERN` | constant | `YYYY.MM.DD. Operator` zip naming. |
| `_WORKSPACE_NAME` | constant | `"Phoenix Units"`. |
| `_notify` | private function | Message box. |
| `_zip_layer_name` / `_operator_from_layer_name` | private function | Zip → layer name → operator. |
| `_login` | private function | Enverus two-step login. |
| `_open_map_layers` | private function | Open DI and the Layer Manager. |
| `_set_fill_color` | private function | Set a layer's RGB fill. |
| `_upload_one` | private function | Upload one zip, color it, enable it. |
| `_save_workspace` | private function | SAVE or SAVE AS the workspace. |
| `main` | function | Colors → login → upload all → save workspace → move to Uploaded → summary. |

### box_copy_deals.py
Not launched by the app; one-off manual script. Copies closed-deal folders from Box, renamed with their Base OGLs.

| Name | Kind | Description |
|---|---|---|
| `_CSV_PATH` / `_SOURCE_DIR` / `_DEST_DIR` | constant | Hardcoded input CSV, Box source, destination. |
| `read_deal_data` | function | Deal number → OGLs. |
| `find_matching_folders` | function | Match deals to folders; returns (matches, duplicates). |
| `make_dest_name` | function | `"OGL1, OGL2 - original"`. |
| `main` | function | Report gaps, robocopy each match. |
