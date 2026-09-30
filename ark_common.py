"""Shared helpers for the launcher's Python scripts: settings.ini lookups and ARK web automation.
Imported by close_dates, cost_to_extend, download_report, non_hbp_mi, ppiq, str_verification,
tpp_lhpp, case_matchup, map_builder and map_uploader (not launched directly).
Reads %APPDATA%\\PhoenixLandDept\\settings.ini ([Credentials], [EnverusCredentials], [Folders]);
callers keep a Playwright storage-state file (session.json) next to it via _SESSION.
Depends on Playwright (only for its TimeoutError here; callers own the browser)."""
import os
import re
import configparser
from playwright.sync_api import TimeoutError as PlaywrightTimeout

_APP_DIR  = os.path.join(os.environ['APPDATA'], 'PhoenixLandDept')  # per-user settings folder shared with the C++ launcher
_INI_PATH = os.path.join(_APP_DIR, 'settings.ini')  # INI written by the launcher's Settings window
_SESSION  = os.path.join(_APP_DIR, 'session.json')  # Playwright storage state (ARK login cookies) that callers load/save directly

_CHEVRON_PATH = 'M2.667 5.333 8 10.668l5.333-5.333H2.667z'  # SVG path of the ARK report dropdown chevron, used to locate its button


def read_credentials():
    """Returns (username, password) for ARK's Microsoft login from [Credentials]; KeyError if missing."""
    cfg = configparser.ConfigParser()
    cfg.read(_INI_PATH)
    return cfg['Credentials']['username'], cfg['Credentials']['password']


def read_enverus_credentials():
    """Returns (identifier, password) for the Enverus/drillinginfo login from [EnverusCredentials]."""
    cfg = configparser.ConfigParser()
    cfg.read(_INI_PATH)
    return cfg['EnverusCredentials']['identifier'], cfg['EnverusCredentials']['password']


def read_folder(key, default):
    """Returns the [Folders] path for key from settings.ini, or default if unset."""
    cfg = configparser.ConfigParser()
    cfg.read(_INI_PATH)
    return cfg.get('Folders', key, fallback=default)


def login(page, username, password, success_url='https://ark.phoenixenergy.com/**'):
    """Fills in a Microsoft sign-in page already showing on page (email, then password),
    accepts the optional "Stay signed in?" prompt, and waits up to 90s for success_url
    (allowing time for MFA approval)."""
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
