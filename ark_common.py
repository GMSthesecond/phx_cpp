"""Shared helpers for the launcher's Python scripts: settings.ini lookups, message boxes and error
reporting (notify, run_button, missing_package), and ARK web automation (login, report download,
Data Loader upload).
Imported by close_dates, cost_to_extend, download_report, non_hbp_mi, ppiq, str_verification,
tpp_lhpp, case_matchup, case_unit_names, docket_updates, map_builder, map_uploader and mirror (not launched directly).
Also holds the Mirror result kinds (UPLOADED / REVIEW / NOTHING) and small helpers (plural, parse_date).
Reads %APPDATA%\\PhoenixLandDept\\settings.ini ([Credentials], [EnverusCredentials],
[SlackCredentials], [Folders]);
callers keep a Playwright storage-state file (session.json) next to it via _SESSION.
Standard library only at import, so a script can report a missing package (missing_package);
login() imports Playwright when called (callers own the browser)."""
import configparser
import ctypes
import os
import re
import traceback
from contextlib import contextmanager
from datetime import datetime

_APP_DIR  = os.path.join(os.environ['APPDATA'], 'PhoenixLandDept')  # per-user settings folder shared with the C++ launcher
_INI_PATH = os.path.join(_APP_DIR, 'settings.ini')  # INI written by the launcher's Settings window
_SESSION  = os.path.join(_APP_DIR, 'session.json')  # Playwright storage state (ARK login cookies) that callers load/save directly

_CHEVRON_PATH = 'M2.667 5.333 8 10.668l5.333-5.333H2.667z'  # SVG path of the ARK report dropdown chevron, used to locate its button
UPLOAD_URL = 'https://ark.phoenixenergy.com/data/data-loader/newUpload'  # Ark Data Loader new-upload page, opened by upload()

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
    """Show a message box titled title (info icon unless flags say otherwise, e.g. 0x10 = error).
    Scripts run with no console, so this is the only way to reach the user."""
    ctypes.windll.user32.MessageBoxW(0, message, title, flags)


def run_button(title, main, log_path):
    """Run a button script's main(): on any error write the traceback to log_path, show an error
    box with the error and the log's path, then re-raise. Returns what main() returns."""
    try:
        return main()
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


def trigger_download(page, report_url, generation_wait_ms=10_000):
    """Navigate to report_url, trigger generation, and return the Download object.
    ARK builds the file server-side: this clicks Download in the chevron menu, waits a
    fixed generation_wait_ms, then pulls the file from the notifications panel. Caller
    saves it (e.g. dl.save_as)."""
    page.goto(report_url)
    page.wait_for_url('**/report**', timeout=20_000)
    page.wait_for_load_state('networkidle')

    chevron = page.locator(f'button:has(svg path[d="{_CHEVRON_PATH}"])')
    chevron.click()
    page.get_by_role('button', name=re.compile(r'^\s*Download\s*$')).first.click()

    page.wait_for_timeout(generation_wait_ms)

    page.locator('#notifications-btn').click()

    with page.expect_download(timeout=15_000) as dl_info:
        page.locator('button:has-text("Download File")').first.click()

    dl = dl_info.value
    dl.path()  # blocks until the temp file is fully written
    return dl


def upload(page, csv_path, upload_name, dataset, operation='Update'):
    """Drive the Ark Data Loader wizard to upload csv_path as a dataset/operation job (dataset is
    the listbox option, e.g. 'Landholdings', 'Units' or 'Cases'; matched as the whole name, ignoring
    capitalization, since Ark renames them). Changes live Ark data. Blocks until
    the row counter (UPLOAD_ACCEPTED) shows, up to 2 minutes; Ark finishes processing on its own.
    Used by close_dates, cost_to_extend, non_hbp_mi and case_unit_names."""
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
