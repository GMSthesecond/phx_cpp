import os
import re
import configparser
from playwright.sync_api import TimeoutError as PlaywrightTimeout

_APP_DIR  = os.path.join(os.environ['APPDATA'], 'PhoenixLandDept')
_INI_PATH = os.path.join(_APP_DIR, 'settings.ini')
_SESSION  = os.path.join(_APP_DIR, 'session.json')

_CHEVRON_PATH = 'M2.667 5.333 8 10.668l5.333-5.333H2.667z'


def read_credentials():
    cfg = configparser.ConfigParser()
    cfg.read(_INI_PATH)
    return cfg['Credentials']['username'], cfg['Credentials']['password']


def read_enverus_credentials():
    cfg = configparser.ConfigParser()
    cfg.read(_INI_PATH)
    return cfg['EnverusCredentials']['identifier'], cfg['EnverusCredentials']['password']


def read_folder(key, default):
    cfg = configparser.ConfigParser()
    cfg.read(_INI_PATH)
    return cfg.get('Folders', key, fallback=default)


def login(page, username, password, success_url='https://ark.phoenixenergy.com/**'):
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
    """Navigate to report_url, trigger generation, and return the Download object."""
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
