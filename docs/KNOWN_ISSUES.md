# Known Issues

Found while documenting the code (2026-09-30). Most impactful first. Delete an entry once it's resolved.

Fixed 2026-09-30:
- Index progress bar never moved (tags were mid-line).
- Organize forgot Ignore rules.
- Map re-uploaded old zips (they now move to `Maps\Uploaded`).
- Close Date skipped weekend closes.

## Bugs

1. **Rename can damage MP3s.** `ParseID3v2` doesn't treat the extended-header flag (0x40)
   as unsupported, so such tags are mis-parsed and `WriteMp3Artist` can drop frames
   (cover art, title). The rewrite is also in place with no backup.
2. **Data Loader "done" check can fire early.** `_upload` in close_dates / non_hbp_mi /
   cost_to_extend waits for `\d+ of \d+`, which also matches "0 of 5", and then closes the browser.
3. **Close Date ignores holidays.** After a Monday holiday, Tuesday's run pulls only Monday,
   so Friday–Sunday closes are missed.
4. **Deceased can silently lose holdings.** `deceased` is keyed only by Legal Entity + Section
   Name, so holdings that differ only by type or title source overwrite each other.

## Silent failures

Scripts run with no console, so these give no feedback at all:
- `ppiq.py`, `download_report.py`, `non_hbp_mi.py`, `deceased.py`: no error message box.
- `str_verification.py`: errors only go to a log file; success only `print`s.
- map_builder / map_uploader: a missing package (shapely, pyshp, playwright) crashes before any message box.

## Settings gaps

- `[Folders] CaseMatchup`, `NonHBPMI`, `CostToExtend` are read by scripts but the Settings
  dialog has no row for them.
- PPIQ, TPP-LHPP, Deceased, Organize, Rename and Index use hardcoded `C:\Users\Ethan Mesecher\...`
  paths with no setting, so they won't work for another user.
- `map_uploader._LOGIN_URL` embeds a captured Auth0 `state=` token that will likely expire.

## Duplication (refactor candidates)

- main.cpp: about 11 copies of the "build path, CreateProcess, error box" block. They could be one `LaunchScript(hwnd, L"x.py")` helper.
- The three `doc_inventory_*.py` are about 90% identical. They could be one module with county settings.
- `_upload` (3 copies), `_notify` (6 copies), and the browser/session/login setup in each Ark script. These could move to ark_common.
- `Trim`, `SplitCSV` and `EscCSV` are copied in organize.cpp and rename.cpp.

## Minor

- organize: `FindRule` picks the first matching snippet alphabetically, not the most specific one. All positive amounts go to Income, so refunds do too.
- case_matchup `_mentions_case` and str_verification's AOI check use substring matching ("4," matches "14,").
- doc_inventory: the single `.bak` is overwritten by each county in turn. Saving fails if the workbook is open in Excel (after the CSV is written).
- `box_copy_deals.py` is launched by nothing; it's a one-off script.
