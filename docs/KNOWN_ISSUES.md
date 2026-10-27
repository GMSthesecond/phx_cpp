# Known Issues

Found while documenting the code (2026-09-30). Most impactful first. Delete an entry once it's resolved.

Entries marked *(test: …)* have an expected-failure test describing the correct behavior
([TESTING.md](TESTING.md#reading-the-results)). Fixing the bug makes that test report that it
now passes. Then remove its xfail / `KNOWN_BUG` marker and this entry.

Fixed 2026-09-30:
- Index progress bar never moved (tags were mid-line).
- Organize forgot Ignore rules.
- Map re-uploaded old zips (they now move to `Maps\Uploaded`).
- Close Date skipped weekend closes.

Fixed 2026-10-06:
- Rename damaged MP3s with an ID3 extended header; tag rewrites now go through a temp file.
- Close Date ignored holidays.
- Deceased lost holdings that shared legal entity + section.

Fixed 2026-10-08:
- Close Date and Case Update uploaded an empty CSV when there was nothing to upload, which failed
  after a 2-minute wait. They now skip the upload.
- Uploads of 1,000+ rows (Case Update) waited 2 minutes, then reported a timeout although the upload worked:
  the "N of N" check didn't allow "1,400 of 1,400". `_upload` now stops at the first "X of Y" row counter
  (`ark_common.UPLOAD_ACCEPTED`, commas allowed), since Ark has the data by then and finishes on its own.
- Case Update failed silently and lost a fresh login on failure; it now shows an error box and always saves the session.

Fixed 2026-10-09:
- Case Unit Names couldn't upload: Ark renamed the Data Loader dataset "Case" to "cases". It now asks for
  "Cases", and `ark_common.upload` matches the option's whole name in any capitalization.
- Silent failures: every button script now shows an error box naming the error and its `*_error.log`
  (`ark_common.run_button`); PPIQ, Data Meeting Download, STR Verification, AOI and Deceased show a box when
  done; the map scripts say which package to install if one is missing; Index stops (workbook missing or
  open in Excel) appear in a box too.
- Settings has a row for every folder (17), the index workbook, and the Ark / Enverus / Slack sign-ins.
  PPIQ, TPP-LHPP, Deceased, Index, Organize and Rename read their folders from it instead of hardcoded paths.
- A `%` in a password, token or folder setting crashed every script (configparser interpolation); it is now read as typed.
- Mirror: each step runs in its own process and is stopped after 20 minutes, so a hung page no longer holds up
  the rest. PPIQ, AOI and Data Meeting Download are disabled while it runs (they share the Ark login).
- TPP-LHPP's Mirror line now flags Close Dates it can't read instead of leaving them out silently.
- Organize: the most specific rule wins ("AMAZON PRIME" over "AMAZON"); credit-card payments are left out
  (both sides); a refund offsets its category instead of counting as Income.
- Substring matching: Case Matchup's docket-note check and STR Verification's AOI check now match whole
  numbers ("4," no longer matches "14,").
- Index: each county backs the workbook up to its own `<workbook>.<County>.bak`; a workbook open in Excel is
  caught before the scan. The three county scripts now share doc_inventory.py.
- Duplication: main.cpp's launch blocks are one `LaunchScript`; `Trim` / `SplitCSV` / `EscCSV` live in csv_text.h;
  every Ark script opens the browser through `ark_common.ark_page` (which also saves the login after an error,
  now including Data Meeting Download and STR Verification); message boxes go through `ark_common.notify`.
- box_copy_deals.py (one-off, launched by nothing) was deleted; it's in git history.
- Map Uploader signed in through a captured Enverus link whose `state=` token would expire. It now opens the
  app, which sends a signed-out browser to a fresh sign-in page (confirmed by hand 2026-10-09).

Fixed 2026-10-12:
- Mirror's report box locked the app: the buttons stayed disabled ("Running...") until it was closed, so a box
  hidden behind another window looked like a hang. The buttons now come back at `@FINISHED`.
- Mirror couldn't be cancelled: closing the app left mirror.py and the running step going unseen (no report).
  Mirror now has a Stop button, and closing the app ends the run (kill-on-close job).

Fixed 2026-10-21:
- Mirror's STR step failed with "IndexError: list index out of range": Ark hadn't finished the 33 MB Check STR
  report after the fixed 60 s wait, so `trigger_download` took the top file in the notifications panel,
  yesterday's units report. It now waits while any export there is in progress (`_PREPARING`) and fails after
  10 minutes instead. STR/AOI, Cost to Extend, Case Update and Cases Unit Names also check the downloaded
  columns (`ark_common.check_columns`), so a wrong report fails clearly instead of being read or uploaded.

## Bugs

None open.

## Mirror

- The buttons Mirror locks can't be *started* during a run, but one started just before Mirror (e.g. PPIQ
  still downloading) can still overlap a step and share session.json with it.
- Docket Updates and Docket Updates Slack sign in to Ark through `ark_common.ark_page` (session.json) but aren't in
  `g_lockedDuringMirror`, so they can be started during a Mirror run (xfail
  `test_buttons_using_ark_page_are_locked_during_mirror`).
- A step stopped at the 20-minute limit, or by the Stop button, may already have uploaded part of its work
  (Ark finishes an upload on its own once it has the rows). The report says it was stopped; check the
  Data Loader history.
- Stop kills the running step at once. If that is the Index step in the moment it saves the index workbook,
  the save can be cut off; the county's `<workbook>.<County>.bak` (made just before) has the previous version.
  If it is an Ark step during a fresh sign-in, that sign-in isn't saved to session.json and is asked for again.
- The 30-second Stop fallback (job ended when mirror.py doesn't report in time) and closing the app mid-run
  are tested at the C++ level (`run_script_lines_in_a_job_*`, `kill_on_close_job_*`), not by clicking the app.
- `trigger_download`'s in-progress check reads Ark's notification wording ("We'll let you know when your file is
  ready…", "N% Complete"), taken from screenshots on 2026-10-21 and not yet seen on a live run. If Ark rewords it,
  a slow report is again taken too early. If a finished export keeps one of those lines, every download waits
  10 minutes and fails.
- Notifications are per Ark account, so an export started by hand in Ark during a run makes the step wait for it
  too, and if it finishes first it can be taken as the newest file. The column check catches that for STR/AOI,
  Cost to Extend, Case Update, Cases Unit Names and SIB. Close Date, TPP-LHPP, PPIQ, Docket Updates and Data Meeting
  Download have no column check (Close Date's real report header isn't known; its raw download isn't saved).

## Settings gaps

- Defaults still point at `C:\Users\Ethan Mesecher\...` (and the Box image folders in doc_inventory.py are
  fixed), so another user has to set their folders in Settings once.
- Organize's committed `default_organize_rules.ini` is only a snapshot. Rules learned afterwards stay in
  `%APPDATA%\PhoenixLandDept\organize_rules.ini` until copied back into the repo, and a machine that already
  has an `organize_rules.ini` never picks up the repo copy again.

## Minor

- Case Unit Names' Case Update upload (added 2026-10-09) has only run against the fake Ark, not live. Two things to
  check on the first real run: the CSV's first column is `Record Id` (the other uploads use `Id`), and a case
  matching several units gets one comma-joined PHX Unit Name ("Klondike, Klondike E"), which the Data Loader may
  store as one value instead of two list entries. The Data Loader history in Ark shows how it was read.
- SIB's Landholdings Update upload (added 2026-10-21) has only run against the fake Ark, not live. Its CSV has
  `Id, Section Name, Section Id`; Section Name is the landholding's own value, so it should change nothing, but if
  the Data Loader rejects that column, upload only `Id, Section Id` (as the older uploads in `Desktop\SIB\Archive`
  did). Check the Data Loader history after the first real run.
- QQ (added 2026-10-22) reads `QQ_Checker.csv` saved by hand in `[Folders] QQ`; it doesn't download it from Ark
  yet. Its Tract Description reading is a heuristic: two lone terms separated by a space join ("NE NW" = NENW), so
  a description meaning two separate quarters written that way ("NE SW" for NE plus SW) is read as one
  quarter-quarter. Any non-aliquot word (lots, "Part", "except", acreage, typos like `SWNE9`) marks the row
  Unreadable rather than guessing, so `Part NWNW` or `S2SE except 1 acre` need a look by hand.
- Data Loader: `ark_common.upload` closes the browser as soon as the row counter shows, so rows Ark rejects while
  processing are never reported (an "Uploaded N" line in Mirror means N rows were sent, not N accepted).
  Check the Data Loader history in Ark if something looks off.
- Organize recognizes card payments by description (`CARD_PAYMENT_SNIPPETS`: "Payment Thank You", "Automatic
  Payment - Thank", "Payment to Chase card") or a card export's Type = Payment. A payment worded differently
  is still counted; add its wording to the list.
- Docket Updates reads only the ND and MT sheets of the Hearing Dockets workbook (`_SHEETS`). Still to do:
  - **UT**: 102 of 128 rows have no case number, units are written with lots ("8-2S-2E-Lots 2, 3, 4, W2SW") that
    the section grid can't read, and RW numbers Utah cases `2026-027-15`. Until it's read, RW's Utah cases are left
    out of *Not in workbook* (`_UTAH_NUMBER_RE`).
  - **WY**: no Case Type or Order Status columns, so only sections and hearing dates could be compared. RW's two WY
    cases show as *Not in workbook* meanwhile (their `NNNN-YYYY` numbers look like MT's).
  - **Sheet2**: state website links, nothing to compare.
- Docket Updates (Hearing Dockets version, added 2026-10-16) has only run against the fake Ark and an older
  `RW_Case_Info.csv` without the new columns. On the first real run check that the report's added columns are named
  `Order Status`, `Hearing Date`, `Order Number` and `Date Order Signed` (the finish box lists any `_FIELDS` column it
  didn't find), and that the Data Loader accepts `Docket_Upload.csv` as a Cases Update (column names, MM/DD/YYYY
  dates, comma-separated Sections). Load a few rows first.
- Docket Updates takes a case's status from the latest row with a result, even when a later hearing re-lists the
  case (agreed 2026-10-16; Notes says "… is from the … hearing; listed again for …"). Such a case is uploaded as
  Ordered while it may still be on a docket. Filter Notes for "listed again" before uploading.
- The Hearing Dockets ND sheet has Order Number 35278 / Date Order Signed 10/05/2026 on about 2,600 rows (mostly
  2022–2025 hearings), almost certainly filled down by mistake. Docket Updates ignores any Order Number shared by more
  than 50 cases (`_FILL_DOWN_CASES`); the Order Status beside it is still used. Fix the sheet to get those orders back.
- Docket Updates' Case Type mapping (`_TYPE_MAP`) is a first draft from the types in the sheet on 2026-10-16. In
  particular MT's ADDITIONAL / AUTHORIZE WELLS → Increased Density disagrees with RW's Permit to Drill on ~20 cases,
  and Revoke … → Show Cause is a guess. Types not in the map (Define Field Limits, Amendment-…, Extend Field, Create
  Drilling Unit, …) aren't compared.
- RW has no state column, so Docket Updates looks ND and MT numbers up in one index. A 3-digit ND number (none since
  2021) would also match MT's `NNN-YYYY` cases.
- Docket Updates Slack re-reads the whole channel every run (no incremental update). It exports message
  text only: attached files aren't downloaded, so a file-only post has a blank Message. An edited message shows its
  latest text. Date, Time and ID use the PC's time zone, so the same message gets a different ID on a PC in another zone.
- Docket Updates Slack's comparison finds RW records by case number only. A mistyped number in Slack gives *Not in RW*
  (or a wrong pairing), so it also lands in `Slack_Not_In_RW.csv`; check a row there against RW before adding it. RW records with no
  number aren't found. Slack has some data slips the CSV surfaces but can't fix:
  the same case listed twice in one message with different sections (32742, 32744 on 9/23/2026), and Montana
  types like "AMENDMENT – CONTESTED" that map to no RW type (shown, not compared). RW has some duplicate
  records (two 32744s, one with applicant "Phoneix Operating LLC"); each gets its own row.
- `_TYPE_RULES` is a judgment call agreed on 2026-10-12. For example, an AMENDMENT whose RW record is Commingling
  or Permit to Drill shows as a Type difference.
