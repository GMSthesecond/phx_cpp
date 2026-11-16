"""Shared helpers for the launcher's Python scripts: settings.ini lookups, message boxes and error
reporting (notify, run_button, missing_package), and ARK web automation (login, report download,
Data Loader upload). A report whose Total Record Count is LARGE_DOWNLOAD_ROWS or more (or can't be
read) is only downloaded after the user clicks Yes in a warning box (confirm_download).
Imported by close_dates, cost_to_extend, nai_download, non_hbp_mi, ppiq, str_verification,
tpp_lhpp, case_matchup, case_unit_names, docket_updates, map_builder, map_uploader, merge and mirror (not launched directly).
Also holds the Mirror result kinds (UPLOADED / REVIEW / NOTHING) and small helpers (plural, parse_date).
Reads %APPDATA%\\PhoenixLandDept\\settings.ini ([Credentials], [EnverusCredentials],
[SlackCredentials], [Folders]);
callers keep a Playwright storage-state file (session.json) next to it via _SESSION.
Standard library only at import, so a script can report a missing package (missing_package);
login() imports Playwright when called (callers own the browser)."""
import configparser
import csv
import ctypes
import os
import re
import traceback
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta

_APP_DIR  = os.path.join(os.environ['APPDATA'], 'PhoenixLandDept')  # per-user settings folder shared with the C++ launcher
_INI_PATH = os.path.join(_APP_DIR, 'settings.ini')  # INI written by the launcher's Settings window
_SESSION  = os.path.join(_APP_DIR, 'session.json')  # Playwright storage state (ARK login cookies) that callers load/save directly

_CHEVRON_PATH = 'M2.667 5.333 8 10.668l5.333-5.333H2.667z'  # SVG path of the ARK report dropdown chevron, used to locate its button
UPLOAD_URL = 'https://ark.phoenixenergy.com/data/data-loader/newUpload'  # Ark Data Loader new-upload page, opened by upload()

_DOWNLOAD_FILE = 'button:has-text("Download File")'  # a finished export's button in Ark's notifications panel
# JS for locator.evaluate_all: the text of the notification around each Download File button (up to the
# element holding its h3 title), its text pieces joined by spaces:
# "Your file is ready for download! For <report> 10:22 AM 11/3/2026 Download File"
_FILE_TEXTS_JS = ("buttons => buttons.map(b => { let n = b; while (n.parentElement && !n.querySelector('h3')) "
                  "n = n.parentElement; const w = document.createTreeWalker(n, NodeFilter.SHOW_TEXT), parts = []; "
                  "while (w.nextNode()) parts.push(w.currentNode.nodeValue); "
                  "return parts.join(' ').replace(/\\s+/g, ' ').trim(); })")
# Time and date printed on a notification ("01:17 PM", "11/3/2026"); digit lookarounds instead of \b so
# run-together text ("Fixes09:34 AM10/20/2026", what textContent gives) still reads
_CARD_TIME = re.compile(r'(?<!\d)(\d{1,2}):(\d{2})\s*([AP]M)', re.I)
_CARD_DATE = re.compile(r'(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)')
_PANEL_MS = 2_000  # time for the notifications panel to fill after opening, before trigger_download notes the files listed
_POLL_MS = 5_000  # how often trigger_download rechecks the notifications panel
_REOPEN_POLLS = 6  # every this many checks without the new file, trigger_download closes and reopens the panel
_GENERATION_TIMEOUT_MS = 10 * 60_000  # trigger_download gives up on a report with no new file after this long
_DOWNLOAD_START_MS = 3 * 60_000  # time a clicked Download File gets to start downloading; 15 s ran out on PPIQ's 125 MB Inverse report (11/10/2026)

LARGE_DOWNLOAD_ROWS = 10_000  # a report with this many records or more is downloaded only after the user says Yes (confirm_download)
# JS for page.evaluate: the text of the card around the report page's "Total Record Count" label
# ("Total Record Count 12,345"), or null if the page has no such label
_COUNT_CARD_JS = ("() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); "
                  "while (w.nextNode()) { if (w.currentNode.nodeValue.trim().toLowerCase() !== 'total record count') "
                  "continue; let n = w.currentNode.parentElement; "
                  "for (let i = 0; n && i < 4; i++, n = n.parentElement) { "
                  "const t = (n.innerText || '').replace(/\\s+/g, ' ').trim(); "
                  "if (t.toLowerCase() !== 'total record count') return t; } } return null; }")
# The number after the label; a rounded one ("12.3K") doesn't match, so it counts as unreadable
_RECORD_COUNT = re.compile(r'total record count\s*:?\s*(\d[\d,]*)(?![\d.]|\s*[KkMm]\b)', re.I)
_COUNT_SETTLE_MS = 1_000  # record_count reads the count again after this long; two equal readings are trusted
_COUNT_WAIT_MS = 20_000  # record_count gives up (count unreadable) after this long without two equal readings
_LARGE_TITLE = 'Large Ark download'  # title of confirm_download's Yes/No box
_MB_LARGE_DOWNLOAD = 0x4 | 0x30 | 0x100 | 0x10000 | 0x40000  # Yes/No, warning icon, No as default, foreground, topmost
_IDYES = 6  # MessageBoxW's answer for Yes
WAITING_TAG = '@WAITING'  # printed just before confirm_download's box opens; Mirror pauses the step's time limit
RESUMED_TAG = '@RESUMED'  # printed once the box is answered; Mirror restarts the step's time limit


class DownloadCancelled(Exception):
    """The user clicked No (or closed the box) when asked to download a large report (confirm_download).
    run_button shows it as a warning, not an error; Mirror fails the step with its text."""

# Data Loader row counter ("0 of 1,400", "5 of 5"): once it shows, Ark has the data and keeps processing
# it after the browser closes. upload() stops waiting there.
UPLOAD_ACCEPTED = re.compile(r'\b\d[\d,]* of \d[\d,]*')

# Kinds of result a script's mirror_step() returns; mirror.py groups its report under these headings.
UPLOADED = 'Uploaded'    # changed live data (an Ark upload, or rows added to the Index sheet)
REVIEW = 'Needs review'  # wrote a report someone should look at
NOTHING = 'No changes'   # ran fine and found nothing to do


def plural(n, word, plural_word=None):
    """'1 unit' / '3 units' (plural_word for irregular plurals like 'mismatches')."""
    return f'{n} {word if n == 1 else plural_word or word + "s"}'


def parse_date(s):
    """Parse an Ark report date in one of several formats; raises ValueError if none match."""
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Unrecognized date format: {s!r}')


def _read_ini():
    """settings.ini, parsed with values taken literally (a % in a password is just a %)."""
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(_INI_PATH)
    return cfg


def read_credentials():
    """Returns (username, password) for ARK's Microsoft login from [Credentials]; KeyError if missing."""
    cfg = _read_ini()
    return cfg['Credentials']['username'], cfg['Credentials']['password']


def read_enverus_credentials():
    """Returns (identifier, password) for the Enverus/drillinginfo login from [EnverusCredentials]."""
    cfg = _read_ini()
    return cfg['EnverusCredentials']['identifier'], cfg['EnverusCredentials']['password']


def read_slack_token():
    """Returns the Slack user token (xoxp-...) from [SlackCredentials] token; KeyError if missing."""
    cfg = _read_ini()
    return cfg['SlackCredentials']['token']


def read_folder(key, default):
    """Returns the [Folders] path for key from settings.ini, or default if unset."""
    return read_setting('Folders', key, default)


def read_setting(section, key, default):
    """Returns settings.ini [section] key (e.g. [Files] IndexWorkbook), or default if unset."""
    cfg = _read_ini()
    return cfg.get(section, key, fallback=default)


def notify(title, message, flags=0x40):
    """Show a message box titled title (info icon unless flags say otherwise, e.g. 0x10 = error) and
    return the button clicked (e.g. 6 = Yes for a Yes/No box). Scripts run with no console, so this is
    the only way to reach the user."""
    return ctypes.windll.user32.MessageBoxW(0, message, title, flags)


def run_button(title, main, log_path):
    """Run a button script's main(): on any error write the traceback to log_path, show an error
    box with the error and the log's path, then re-raise. Returns what main() returns.
    A large download the user said No to (DownloadCancelled) gets a warning box saying the script
    stopped, no log, and returns None."""
    try:
        return main()
    except DownloadCancelled as e:
        notify(title, f'{title} stopped. {e}', 0x30)
        return None
    except Exception as e:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, 'w', encoding='utf-8') as f:
                traceback.print_exc(file=f)
            details = f'\n\nDetails: {log_path}'
        except OSError:
            details = ''  # the folder itself may be the problem; the box still shows the error
        notify(title, f'{title} failed:\n{e}{details}', 0x10)
        raise


_PIP_NAMES = {'shapefile': 'pyshp'}  # import name -> pip package name, where they differ


def missing_package(title, err):
    """For a script's import guard (except ImportError as err): show which package to install, then exit."""
    name = (err.name or 'unknown').split('.')[0]
    package = _PIP_NAMES.get(name, name)
    notify(title, f'{title} can\'t start: the Python package "{package}" isn\'t installed.\n\n'
                  f'Install it from a command prompt with:\npy -m pip install {package}', 0x10)
    raise SystemExit(1)


def login(page, username, password, success_url='https://ark.phoenixenergy.com/**'):
    """Fills in a Microsoft sign-in page already showing on page (email, then password),
    accepts the optional "Stay signed in?" prompt, and waits up to 90s for success_url
    (allowing time for MFA approval)."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    page.fill('input[type="email"]', username)
    page.click('input[type="submit"]')

    page.wait_for_selector('input[type="password"]', timeout=15_000)
    page.fill('input[type="password"]', password)
    page.click('input[type="submit"]')

    try:
        page.wait_for_selector('#idSIButton9', timeout=8_000)
        page.click('#idSIButton9')
    except PlaywrightTimeout:
        pass

    page.wait_for_url(success_url, timeout=90_000)


def needs_login(page):
    """Whether page is on the Microsoft / Cloudflare sign-in instead of Ark."""
    return 'microsoftonline.com' in page.url or 'cloudflareaccess.com' in page.url


def ensure_login(page, success_url='https://ark.phoenixenergy.com/**'):
    """Log in with [Credentials] if page landed on a sign-in page (e.g. after switching Ark domains)."""
    if needs_login(page):
        username, password = read_credentials()
        login(page, username, password, success_url)


@contextmanager
def ark_page(first_url, success_url='https://ark.phoenixenergy.com/**'):
    """Open Chromium (visible) with the saved Ark login (_SESSION), go to first_url, log in if Ark
    asks (ensure_login), and yield the page. On the way out, also after an error, save the session
    so a fresh login/2FA isn't lost, and close the browser. Used by every Ark script."""
    from playwright.sync_api import sync_playwright  # here, so importing ark_common needs no Playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(storage_state=_SESSION if os.path.exists(_SESSION) else None,
                                  accept_downloads=True)
        try:
            page = ctx.new_page()
            page.goto(first_url)
            ensure_login(page, success_url)
            yield page
        finally:
            ctx.storage_state(path=_SESSION)
            browser.close()


def _file_texts(page):
    """Text of each finished export listed in the open notifications panel, top (newest) first."""
    return page.locator(_DOWNLOAD_FILE).evaluate_all(_FILE_TEXTS_JS)


def _card_time(text):
    """The time and date a notification's text says it was made (to the minute, the PC's local
    time), or None if it shows no valid time and date."""
    t, d = _CARD_TIME.search(text), _CARD_DATE.search(text)
    if not (t and d):
        return None
    hour = int(t[1]) % 12 + (12 if t[3].upper() == 'PM' else 0)
    try:
        return datetime(int(d[3]), int(d[1]), int(d[2]), hour, int(t[2]))
    except ValueError:
        return None


def _new_file(texts, before, since):
    """Index in texts (top first) of the first file that wasn't listed before the download was asked
    for (before, counting repeats) and isn't stamped earlier than since; None if there's none yet."""
    already = Counter(before)
    for i, text in enumerate(texts):
        if already[text]:
            already[text] -= 1
            continue
        made = _card_time(text)
        if made is None or made >= since:
            return i
    return None


def trigger_download(page, report_url, generation_wait_ms=10_000):
    """Navigate to report_url, trigger generation, and return the Download object.
    ARK builds the file server-side and lists it in the notifications panel when done. This notes
    the files the panel already lists, clicks Download in the chevron menu, waits
    generation_wait_ms, opens the panel and rechecks every _POLL_MS (reopening it every
    _REOPEN_POLLS checks) until a new file stamped no earlier than the click shows (_new_file), then
    downloads that one. Other notifications are ignored (Data Loader ones stuck at "0% Complete" held
    every download for 10 minutes until 11/3/2026). Raises if no new file shows within
    _GENERATION_TIMEOUT_MS, or if the clicked file doesn't start downloading within
    _DOWNLOAD_START_MS. Before asking Ark for the export, reads the page's Total Record Count
    (record_count): a large or unreadable one needs the user's Yes (confirm_download, which raises
    DownloadCancelled on No), so nothing large is generated or downloaded unasked.
    Caller saves it (e.g. dl.save_as)."""
    page.goto(report_url)
    page.wait_for_url('**/report**', timeout=20_000)
    page.wait_for_load_state('networkidle')
    confirm_download(report_url, record_count(page))

    bell = page.locator('#notifications-btn')
    bell.click()  # open the panel to note the files already listed, then close it
    page.wait_for_timeout(_PANEL_MS)
    before = _file_texts(page)
    bell.click()
    since = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=1)  # a minute's slack for Ark's clock

    chevron = page.locator(f'button:has(svg path[d="{_CHEVRON_PATH}"])')
    chevron.click()
    page.get_by_role('button', name=re.compile(r'^\s*Download\s*$')).first.click()

    page.wait_for_timeout(generation_wait_ms)
    waited = generation_wait_ms

    bell.click()
    checks = 1
    while (new := _new_file(_file_texts(page), before, since)) is None:
        if waited >= _GENERATION_TIMEOUT_MS:
            raise RuntimeError(f'Ark listed no new file for the report after {waited // 60_000} min '
                               f'(see its notifications): {report_url}')
        page.wait_for_timeout(_POLL_MS)
        waited += _POLL_MS
        if checks % _REOPEN_POLLS == 0:
            bell.click()
            bell.click()
        checks += 1

    with page.expect_download(timeout=_DOWNLOAD_START_MS) as dl_info:
        page.locator(_DOWNLOAD_FILE).nth(new).click()

    return dl_info.value


def record_count(page):
    """The report's Total Record Count as its Ark report page shows it, once two readings
    _COUNT_SETTLE_MS apart agree (the page may still be filling it in); None if no readable count
    shows within _COUNT_WAIT_MS. Called by trigger_download before it asks for the export."""
    last, waited = None, 0
    while waited < _COUNT_WAIT_MS:
        found = _RECORD_COUNT.search(page.evaluate(_COUNT_CARD_JS) or '')
        count = int(found[1].replace(',', '')) if found else None
        if count is not None and count == last:
            return count
        last = count
        page.wait_for_timeout(_COUNT_SETTLE_MS)
        waited += _COUNT_SETTLE_MS
    return None


def confirm_download(report_url, records):
    """Let a report of fewer than LARGE_DOWNLOAD_ROWS records through; for a larger one, or one whose
    count couldn't be read (records None), ask in a topmost Yes/No box (No by default) with the count
    and link, and raise DownloadCancelled unless the user clicks Yes. Prints WAITING_TAG / RESUMED_TAG
    around the box so Mirror doesn't count the wait against the step's time limit."""
    if records is not None and records < LARGE_DOWNLOAD_ROWS:
        return
    if records is None:
        size, short = "This Ark report's record count couldn't be read (no Total Record Count on its page)", \
                      'record count unreadable'
    else:
        size, short = f'This Ark report has {records:,} records', f'{records:,} records'
    print(WAITING_TAG, flush=True)
    try:
        answer = notify(_LARGE_TITLE, f'{size}:\n{report_url}\n\nReports of {LARGE_DOWNLOAD_ROWS:,} records or more '
                                      f"need your OK before they're downloaded.\n\nDownload it?", _MB_LARGE_DOWNLOAD)
    finally:
        print(RESUMED_TAG, flush=True)
    if answer != _IDYES:
        raise DownloadCancelled(f'Large download cancelled: {short}, {report_url}')


def check_columns(path, columns, report):
    """Raise if the CSV at path doesn't start with these columns (None = any name), so a script
    never reads or uploads a different report Ark handed back. report names it in the error."""
    with open(path, newline='', encoding='utf-8-sig') as f:
        header = next(csv.reader(f), [])
    if len(header) < len(columns) or any(want is not None and got.strip() != want
                                         for want, got in zip(columns, header)):
        raise RuntimeError(f'Ark sent a different report than {report} '
                           f'(columns: {", ".join(header) or "none"}); run it again')


def upload(page, csv_path, upload_name, dataset, operation='Update'):
    """Drive the Ark Data Loader wizard to upload csv_path as a dataset/operation job (dataset is
    the listbox option, e.g. 'Landholdings', 'Units' or 'Cases'; matched as the whole name, ignoring
    capitalization, since Ark renames them). Changes live Ark data. Blocks until
    the row counter (UPLOAD_ACCEPTED) shows, up to 2 minutes; Ark finishes processing on its own.
    Used by close_dates, cost_to_extend, non_hbp_mi, case_unit_names and section_id_blank."""
    page.goto(UPLOAD_URL)
    page.wait_for_load_state('networkidle')

    # 1 — select the operation card (Update, Insert, etc.)
    card_label = page.locator('p.font-semibold', has_text=operation)
    card_label.wait_for(timeout=15_000)
    page.wait_for_timeout(1500)
    card_label.click()
    page.wait_for_load_state('networkidle')

    # 2 — select the dataset from the listbox
    page.locator('[aria-haspopup="listbox"]').click(timeout=10_000)
    option_name = re.compile(rf'^\s*{re.escape(dataset)}\s*$', re.I)
    page.get_by_role('option', name=option_name).click(timeout=10_000)

    # 3 — fill the upload name (close the listbox dropdown first with Escape)
    page.keyboard.press('Escape')
    name_input = page.locator('input.bg-neutral-gray-1')
    name_input.wait_for(timeout=10_000)
    name_input.click()
    name_input.press_sequentially(upload_name)

    # 4 — attach the CSV
    page.locator('input[type="file"]').set_input_files(csv_path)

    # 5 — continue to the next page
    page.get_by_role('button', name=re.compile(r'continue', re.I)).click()
    page.wait_for_load_state('networkidle')

    # 6 — submit
    page.get_by_role('button', name=re.compile(r'save and upload', re.I)).click()

    # 7 — confirm in the popup/modal
    confirm_btn = page.get_by_role('button', name=re.compile(rf'^{operation}$', re.I))
    confirm_btn.wait_for(timeout=15_000)
    confirm_btn.click()

    # Wait for the row counter ("X of Y", up to 2 minutes): Ark has the data then and finishes on its own
    page.get_by_text(UPLOAD_ACCEPTED).first.wait_for(timeout=120_000)
    print('Upload complete.', flush=True)
