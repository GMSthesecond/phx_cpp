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
  (`ark_common.run_button`); PPIQ, NAI, STR Verification, AOI and Deceased show a box when
  done; the map scripts say which package to install if one is missing; Index stops (workbook missing or
  open in Excel) appear in a box too.
- Settings has a row for every folder (17), the index workbook, and the Ark / Enverus / Slack sign-ins.
  PPIQ, TPP-LHPP, Deceased, Index, Organize and Rename read their folders from it instead of hardcoded paths.
- A `%` in a password, token or folder setting crashed every script (configparser interpolation); it is now read as typed.
- Mirror: each step runs in its own process and is stopped after 20 minutes, so a hung page no longer holds up
  the rest. PPIQ, AOI and NAI are disabled while it runs (they share the Ark login).
- TPP-LHPP's Mirror line now flags Close Dates it can't read instead of leaving them out silently.
- Organize: the most specific rule wins ("AMAZON PRIME" over "AMAZON"); credit-card payments are left out
  (both sides); a refund offsets its category instead of counting as Income.
- Substring matching: Case Matchup's docket-note check and STR Verification's AOI check now match whole
  numbers ("4," no longer matches "14,"). (AOI now parses the name into sections instead, 2026-11-10.)
- Index: each county backs the workbook up to its own `<workbook>.<County>.bak`; a workbook open in Excel is
  caught before the scan. The three county scripts now share doc_inventory.py.
- Duplication: main.cpp's launch blocks are one `LaunchScript`; `Trim` / `SplitCSV` / `EscCSV` live in csv_text.h;
  every Ark script opens the browser through `ark_common.ark_page` (which also saves the login after an error,
  now including NAI and STR Verification); message boxes go through `ark_common.notify`.
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
  yesterday's units report. It now waits while any export there is in progress (`_PREPARING`; replaced on
  2026-11-03 by waiting for the new file, below) and fails after
  10 minutes instead. STR/AOI, Cost to Extend, Case Update and Cases Unit Names also check the downloaded
  columns (`ark_common.check_columns`), so a wrong report fails clearly instead of being read or uploaded.

Fixed 2026-10-30:
- Docket Updates (now Docket Updates Sheet) and Docket Updates Slack could be started during a Mirror run and
  share session.json with its steps. Docket Updates Slack is now a Mirror step and Docket Updates Sheet is in
  `g_lockedDuringMirror`.

Fixed 2026-11-02:
- Docket Updates Slack's 7-day window was an hour off for a week after a daylight-saving change (7 local days
  back from now). It now asks Slack for exactly 7 × 24 hours back.
- PPIQ: LHT-mismatch rows had the LH name under Account Name, no Type / LH Name, and only the LHT value; they now
  show Price Paid and LHT Value side by side with the holding's details. Reports are saved under fixed names (a
  report renamed in Ark used to leave last week's file to be analyzed) and checked for their columns (read by header
  name, not position). An issue for a landholding missing from EM All Landholdings is no longer dropped (one on
  10/26/2026), and a landholding with two issues gets both rows. Blank amounts count as $0 instead of crashing; the
  CSV has a BOM so Excel shows accented names; the 100 s of fixed waits between downloads are gone.

Fixed 2026-11-03:
- Every Ark download (Close Date, STR, ...) sat on the open notifications panel for 10 minutes and failed. Three
  Data Loader notifications from 10/20/2026 stay at "Processing N records... 0% Complete", and `trigger_download`
  waited while any "% Complete" line showed. It now notes the files the panel lists before clicking Download, waits
  for a new one stamped no earlier than the click and downloads that one, ignoring every other notification.
- Close Date skipped Deferred deals only in a 5-column report; the real one has 4 (Status last), so Deferred deals
  were uploaded. It also checks the report's columns now (`_COLUMNS`, header seen on 11/3/2026).
- Mirror's report box listed large-download links as plain text; it is now a task dialog where they and the
  archive path can be clicked.
- TPP-LHPP was Needs review on every Mirror run with mismatches closing soon, even when nothing had changed. It is
  No changes when the export has exactly the last one's rows.
- SIB downloaded all ~59,000 sections every run (a large download each time). It now keeps them in
  `Section_ID_Index.csv` and merges in the Section ID Getting download, which is to cover only the last week.

Fixed 2026-11-10:
- AOI passed sections outside a two-township Area of Interest: it looked for the section number and the
  township-range anywhere in the name, so 26-146N-102W passed "2, 11-146N-102W, 26, 35-147N-102W". It now parses
  the name into its sections (`_aoi_sections`), each tied to its own township-range, and says why a row fails.
- AOI flagged 25-162N-92W in Sandor because its Township field reads "162" (no N); the section now comes from the
  Section Name first (`_row_section`). The STR check still reports that Township field. Rows with a blank Section
  Name are now checked from Section/Township/Range instead of skipped.

Fixed 2026-11-13:
- A large export got only 15 s to start downloading once its Download File button was clicked; PPIQ failed this
  way on 11/10/2026 on the 125 MB Inverse report. Every Ark download now gets 3 minutes (`_DOWNLOAD_START_MS`).
- PPIQ failed after all its downloads (several minutes) if `Update_Inverted.csv` or a report CSV was open in
  Excel. It now checks first and says which file to close; the output opened mid-run gets the same box.
- PPIQ's Inverse report had the same columns as All LHs In Queue (EM), so one could pass for the other. The
  Inverse report was trimmed in Ark to Offer Name, LandHolding Id and Status, and PPIQ refuses it if it has the
  queue report's LHT value. PPIQ's column names are matched ignoring capitals ("ID", "OFFER: STATUS").

## Possible bugs

- PPIQ keeps one All LHs In Queue (EM) row per landholding (the last), so a landholding with two queue
  transactions is checked against one LHT value: $100 then $40 is flagged against a $100 price paid, $40 then
  $100 isn't, and a $60 + $40 split is flagged. Whether a landholding can have several queued transactions, and
  whether they should be summed, is still to be confirmed.
- PPIQ: a Landholdings In Queue (EM) row with Price Paid 0 counts as paid, so a queued one shows as an LHT
  mismatch, not "Curative offers should have price paid". Only matters if that Ark report can list unpaid rows.
- Clicking PPIQ twice runs two copies at once, sharing its files, session.json and the notifications panel
  (`LaunchScript` doesn't check for a running copy).

## Bugs

- PPIQ: a Landholdings In Queue (EM) or EM All Landholdings row with a blank Id becomes an issue row with a blank
  ID (the queue reports skip them). *(test: `test_rows_with_a_blank_id_are_skipped`)*
- PPIQ: an amount that isn't a number (e.g. "(100.00)") stops the run after the downloads with only "could not
  convert string to float", not which report or row. *(test: `test_an_amount_that_isnt_a_number_names_the_report`)*

## Large downloads (Yes/No box since 2026-11-12)

- Not yet run live. `record_count` finds the report page's count by the label text "Total Record Count" and reads
  the number in the card around it (`_COUNT_CARD_JS`), going by a screenshot from 11/12/2026. If Ark renames the
  label or shows a rounded count ("12.3K"), every download asks with "record count couldn't be read" rather than
  risk a large one. If Ark's count ever differs from what the export holds (e.g. a filter the export ignores), the
  box can be skipped for a report that turns out to be large.
- Reports that are always 10,000+ records ask on every run: PPIQ's EM All Landholdings (286,722) and All LHs In
  Queue (EM) (Inverse) (810,608), two boxes per PPIQ run, and probably TPP-LHPP's LandHoldingTransactions. In Mirror,
  every step with such a report waits for an answer each run (the step's 20-minute limit is paused, but the run
  doesn't finish until someone answers). SIB's Section ID Getting report asks every run until it is filtered to recent
  sections (see Mirror below).
- Reading the count adds about 1 s to every download (two readings 1 s apart must agree).

## Mirror

- The buttons Mirror locks can't be *started* during a run, but one started just before Mirror (e.g. PPIQ
  still downloading) can still overlap a step and share session.json with it.
- A step stopped at the 20-minute limit, or by the Stop button, may already have uploaded part of its work
  (Ark finishes an upload on its own once it has the rows). The report says it was stopped; check the
  Data Loader history.
- Stop kills the running step at once. If that is the Index step in the moment it saves the index workbook,
  the save can be cut off; the county's `<workbook>.<County>.bak` (made just before) has the previous version.
  If it is an Ark step during a fresh sign-in, that sign-in isn't saved to session.json and is asked for again.
- The 30-second Stop fallback (job ended when mirror.py doesn't report in time) and closing the app mid-run
  are tested at the C++ level (`run_script_lines_in_a_job_*`, `kill_on_close_job_*`), not by clicking the app.
- `trigger_download` finds the new file by Ark's notification layout as seen on 2026-11-03: a "Download File"
  button inside a card with an h3 title and a "10:22 AM" / "11/3/2026" stamp (`_FILE_TEXTS_JS`, `_card_time`). If Ark
  changes the button text, every download fails after 10 minutes; if it drops the stamp, only the files-listed-before
  check keeps an older export from being taken.
- Notifications are per Ark account, so an export started by hand in Ark during a run that finishes before the
  step's own can be taken as the new file. The column check catches that for STR/AOI,
  Cost to Extend, Case Update, Cases Unit Names, SIB and PPIQ (its Inverse report also refuses the queue report's
  LHT value, since its other columns are all in the queue report). Close Date checks its columns since 2026-11-03.
  TPP-LHPP, NAI and Docket Updates Slack have no column check, and Docket
  Updates Sheet checks only Record Id and Case Number.
- Mirror's report task dialog was checked on 11/3/2026 by showing it (links drawn, OK closes it); clicking a link
  is tested only by calling the callback. If the dialog can't open, the old message box (no links) is shown.
- SIB's index (since 2026-11-03):
  - Until the Section ID Getting report in Ark is filtered to sections created in the last week, SIB still downloads
    every section (merging changes nothing then, but the download stays large).
  - With no full refresh, a section created while SIB doesn't run for more than a week is never indexed; its
    landholdings stay unmatched. Rebuild with `--seed` from a full download if that happens.
  - Sections deleted in Ark stay in the index, so a landholding naming one gets its old Id uploaded.
  - If `Section_ID_Index.csv` is lost, SIB stops until it's rebuilt: download the full report (filter off) into the
    SIB folder as `Section_ID_Getting.csv` and run `py section_id_blank.py --seed`.
- TPP-LHPP's "unchanged" compares with whatever `PHX_Price_Paid_Export.xlsx` holds, so a run from the button
  between two Mirror runs is "the last run". Editing the file (e.g. adding notes) makes the next run Needs review.

## Settings gaps

- Defaults still point at `C:\Users\Ethan Mesecher\...` (and the Box image folders in doc_inventory.py are
  fixed), so another user has to set their folders in Settings once.
- Organize's committed `default_organize_rules.ini` is only a snapshot. Rules learned afterwards stay in
  `%APPDATA%\PhoenixLandDept\organize_rules.ini` until copied back into the repo, and a machine that already
  has an `organize_rules.ini` never picks up the repo copy again.
- NAI was DMD ("Data Meeting Download") before 2026-10-28. A settings.ini from then may still hold an unused
  `[Folders] DataMeetingDownload` line; nothing reads or deletes it (harmless). A machine that had set a custom DMD
  folder gets the default `Desktop\NAI` until NAI's folder is set in Settings.

## Minor

- PPIQ downloads two huge reports it barely uses (sizes from 11/10/2026). EM All Landholdings (286,722 rows) is
  read for the PHX-account check (about 24,000 rows) and for the details of queued landholdings with no price
  paid, which Landholdings In Queue (EM) doesn't list. The Inverse report (810,608 rows; trimmed to 3 columns on
  11/13/2026, so the file is smaller but the row count and its Yes/No box are the same) only fills the Status
  column of the "not in queue" and "PHX need price paid" rows (23 rows used). Since 11/10/2026 the issue rows
  for landholdings the paid report lists take their details from it. Cutting EM All Landholdings down in Ark to
  PHX landholdings with no price paid would still blank Price Paid / Type / Account Name on the "Curative offers
  should have price paid" rows (8 on 11/10/2026), because All LHs In Queue (EM) has no landholding Type and
  its account is the offer's. Filtering the Inverse report on "Docs Sent" would blank real statuses.
- Merge (added 2026-11-06) has been run live only on the Dummy 1 / Dummy 2 test accounts (2 land holdings each;
  the rename / notes / move steps keeping each account in turn, which moved their practice contact, offer, title
  request and call both ways, one of each). Moving records is untested with many records: the side drawer loads a
  long list as it's scrolled, so Merge scrolls it (`merge._SCROLL_JS`, every scrollable box in `#side-drawer` to
  its bottom; unchecked live, but the list is also read again after each pass, so records missed at first move
  in a later pass), and each record takes a few seconds, so an account with hundreds of calls & texts takes many
  minutes. A record that won't move is only noted in the closing box, not in Ark.
  Not yet run live (added 2026-11-10): copying documents (the Documents drawer's rows, download button and upload
  window: `_DOC_ROWS_JS`, `_DOWNLOAD_BUTTON`, `_ADD_BUTTON`, `_FILE_INPUT`, `_UPLOAD_BUTTON`, `_READY`,
  `_UPLOAD_URL`; scrolling it relies on `_SCROLL_JS` too, since documents stay on the merge account and its list
  never shrinks) and deleting the merge account (`delete_account`: the top-right **Delete** and the confirmation
  box's **Delete** are found by their names; Ark's answer is taken from the first `api-ark` call naming the
  account, then the link, opened in a second tab of the same browser so a delete still on its way isn't
  cancelled, must show "Account Not Found" within 30 s; that second tab is expected to share the sign-in). If
  the confirmation box isn't a `dialog` with
  one Delete button, Merge stops before deleting. Running Merge again after a partial run uploads the documents
  to the kept account again. Tasks aren't moved, so deleting the merge account loses its tasks (accepted).
  The land holdings step (`update_holdings`) was first run live on the dummies on 2026-11-11: moving a land
  holding worked (same Account lookup as contacts), but every signer change stopped with "0 Signer 1 boxes".
  Seen then: Legal Entity and the signer fields are plain text boxes right after their labels (`_HOLDING_BOX`),
  but Ark has Last Name only for Signer 1–2 and Capacity only for Signer 1–3 (`_SIGNER_BOX_LIMITS`). Fixed by
  filling only those and clicking the *Signer Information* tab by the first text containing its name (as for the
  notes tabs; taken to be the cause, since the boxes match the selector). Still to confirm on the dummies: a
  signer change now saves, and a Legal Entity change saves (it's on *Details*, the tab the window opens on).
  Added 2026-11-11, not yet run live: (a) filling the kept account's blank fields (`blank_fills`) assumes the
  Mailing Street / City / State / Zip Code boxes are plain text boxes after their labels on the Edit Account
  window's *Details* tab, like the phone and email boxes seen that day (`_DETAIL_BOX`); if one isn't (say Mailing
  State is a dropdown), the kept account's save stops with "shows 0 … boxes instead of 1" after the merge account
  was already renamed. (b) Ark's Land Holdings count can stay at the old number for a while after land holdings
  move (seen 2026-11-11), so when it counts some, the merge account's Land Holdings drawer is read instead
  (`_with_listed_holdings`); an empty drawer under a stale count waits 30 s (`_OPEN_TIMEOUT_MS`) before it's taken
  as empty, after the merge step and again before deleting. The other counts are trusted; if they lag too, the
  delete is blocked with "Ark still counts …" and the account can be deleted by hand. (c) Taking "(keep)" off
  the kept account happens only after the delete is confirmed, in a new tab; if it fails, the last box is a
  warning with the link. The parent account is read from a "Parent Account"
  field, else from the "Parent - <name>" Quick Reference entry seen on the dummies, whose first line may include
  the owner in brackets ("Dummy Parent (Ruby Mesecher)"); that goes into the note as shown. The merge step edits accounts through Ark's Edit Account window
  (`merge._NAME_FIELD`, `_NOTE_BOXES`, `_ACCOUNT_BOX`) and waits for Ark's `update-sb` call (`merge._UPDATE_URL`); if Ark renames
  either, the step stops with an error instead of saving. A step that fails after the merge account was renamed
  leaves it renamed (running Merge again replaces the tags; the note block is only written in the last save, so
  it isn't doubled unless that save went through). The note block's initials are fixed as "RM" (`merge._INITIALS`),
  not taken from whoever is signed in. The notes tabs are clicked by their exact name, else (as when the rename /
  notes steps were run live) the first text containing it. Two things are unchecked on real accounts: (1) it reads
  the land holdings linked in the account page's Land Holdings panel, which may list only the first few on an
  account with many; when the Quick Reference counts more than are linked, it reads the rest from the Land
  Holdings side drawer (`_related_links`, scrolled like the other drawers; not yet seen live on an account with
  more than the panel links), and the review window says how many still weren't found (`holdings_missing`).
  (2) A land holding Ark can't find is expected to say "Land Holding Not Found"
  (`merge._HOLDING_NOT_FOUND`, a guess from the account page's message); if it says something else, the run fails
  after 30 s instead of at once. It reads the page's layout (`merge._READ_JS`: the `quick-ref-rel-list` entries,
  the `font-medium text-lighter` field labels, the `/land-holdings?recordId=` links), so an Ark redesign can make
  it fail with "didn't finish showing the page" or show fields as "not on this page".
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
- Docket Updates Sheet reads only the ND and MT sheets of the Hearing Dockets workbook (`_SHEETS`). Still to do:
  - **UT**: 102 of 128 rows have no case number, units are written with lots ("8-2S-2E-Lots 2, 3, 4, W2SW") that
    the section grid can't read, and RW numbers Utah cases `2026-027-15`. Until it's read, RW's Utah cases are left
    out of *Not in workbook* (`_UTAH_NUMBER_RE`).
  - **WY**: no Case Type or Order Status columns, so only sections and hearing dates could be compared. RW's two WY
    cases show as *Not in workbook* meanwhile (their `NNNN-YYYY` numbers look like MT's).
  - **Sheet2**: state website links, nothing to compare.
- Docket Updates Sheet (Hearing Dockets version, added 2026-10-16) has only run against the fake Ark and an older
  `RW_Case_Info.csv` without the new columns. On the first real run check that the report's added columns are named
  `Order Status`, `Hearing Date`, `Order Number` and `Date Order Signed` (the finish box lists any `_FIELDS` column it
  didn't find), and that the Data Loader accepts `Docket_Upload.csv` as a Cases Update (column names, MM/DD/YYYY
  dates, comma-separated Sections). Load a few rows first.
- Docket Updates Sheet takes a case's status from the latest row with a result, even when a later hearing re-lists the
  case (agreed 2026-10-16; Notes says "… is from the … hearing; listed again for …"). Such a case is uploaded as
  Ordered while it may still be on a docket. Filter Notes for "listed again" before uploading.
- The Hearing Dockets ND sheet has Order Number 35278 / Date Order Signed 10/05/2026 on about 2,600 rows (mostly
  2022–2025 hearings), almost certainly filled down by mistake. Docket Updates Sheet ignores any Order Number shared by more
  than 50 cases (`_FILL_DOWN_CASES`); the Order Status beside it is still used. Fix the sheet to get those orders back.
- Docket Updates Sheet's Case Type mapping (`_TYPE_MAP`) is a first draft from the types in the sheet on 2026-10-16. In
  particular MT's ADDITIONAL / AUTHORIZE WELLS → Increased Density disagrees with RW's Permit to Drill on ~20 cases,
  and Revoke … → Show Cause is a guess. Types not in the map (Define Field Limits, Amendment-…, Extend Field, Create
  Drilling Unit, …) aren't compared.
- RW has no state column, so Docket Updates Sheet looks ND and MT numbers up in one index. A 3-digit ND number (none since
  2021) would also match MT's `NNN-YYYY` cases.
- Docket Updates Slack reads only the last 7 days of messages (`_DAYS`, since 2026-10-30):
  - A reply she sends in the window to a post from before it isn't found, because only the threads of posts in the
    window are opened (xfail `test_recent_reply_to_an_older_post_is_exported`). A correction made in an old thread
    is missed.
  - A case last posted before the window isn't compared again, so a later change to its RW record isn't reported.
  - A case's blanks (status, well count, ...) are filled only from posts in the window, so a newer post that leaves
    the status out has no status when the post that gave it is older than 7 days.
- Docket Updates Slack exports message text only: attached files aren't downloaded, so a file-only post has a blank Message. An edited message shows its
  latest text. Date, Time and ID use the PC's time zone, so the same message gets a different ID on a PC in another zone.
- Docket Updates Slack's comparison finds RW records by case number only. A mistyped number in Slack gives *Not in RW*
  (or the wrong record), so it also lands in `Slack_Not_In_RW.csv`; check a row there against RW before adding it. RW records with no
  number aren't found. Case Type isn't compared (since 2026-10-27), so a wrong type in RW isn't reported. RW has
  some duplicate records (two 32744s, one with applicant "Phoneix Operating LLC"); each gets its own row.
- Docket Updates Slack doesn't read sections (dropped 2026-10-27 to cut scope) and only adds up the `(N Wells)` lines
  into one well count, so it can't tell which sub-case a post is about. A well count written anywhere else (in the
  header, or in a remark like "3 wells approved") isn't read, and that case's Well Count is blank.
- Docket Updates Slack's well count is compared with the RW report's `Number of Wells` (any case; it ran against
  the live report on 2026-11-03). Slack's count is the whole case's, so it's compared with the total over the RW
  records the case is compared with; a duplicate RW record (two 32744s) is counted twice and makes the case differ.
- Docket Updates Slack counts a blank RW `Date Order Signed`, or one earlier than the order date, as a difference
  whenever Slack has a result (since 2026-11-04). RW had it blank on every case in the 2026-11-03 run, so until
  those are loaded nearly every case differs and Mirror reports Needs review. The order date is the message's
  `Board Order Updates from …` heading date, which is the board's update date, not necessarily the day each order
  was signed. A message without that heading (a thread reply, a correction) uses its own post date. A later RW date
  is never moved back.
- After a failed Docket Updates Slack run, the comparison files from the last run that finished stay in the
  folder. They aren't deleted: the failure box (or Mirror's Failed line) says not to load `Slack_Docket_Upload.csv`.
- Docket Updates Slack's `Slack_Docket_Upload.csv` (added 2026-10-27) hasn't been loaded into Ark yet, and isn't
  uploaded automatically until it has been. On the first real load check that the Data Loader accepts the column
  names, MM/DD/YYYY dates and the link-plus-notes Case Notes, and that DISMISSED's blank Order Status clears the
  field. If the RW report loses a column (`Date Order Signed`, `Number of Wells`, ...), that column is left out of
  the upload and not compared (the finish box says so). Cases with sub-cases or several RW records are never in the upload:
  review their rows in the differences workbook by hand.
- Files from before 2026-10-27 (`Slack_Docket_Updates.csv`, `Slack_Docket_Differences.csv`) stay in the Docket Updates
  folder; Docket Updates Slack now writes `Parsed_Slack_Messages.csv` and `Slack_Docket_Differences.xlsx` and never
  touches the old ones. Delete them by hand. Every `<number>` / `<number>-k` record is compared with the case's one status and type,
  so an order covering only some sub-cases shows the others as *Differs*, and a well group RW has no sub-case for
  isn't reported. A field-rules case RW only has as Roman-numeral sub-cases (`32665-V-1`) is compared with all of them.
- `_TYPE_RULES` is a judgment call agreed on 2026-10-12. For example, an AMENDMENT whose RW record is Commingling
  or Permit to Drill shows as a Type difference.
