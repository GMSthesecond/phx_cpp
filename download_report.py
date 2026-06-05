import os
import re
import configparser
from datetime import date  # used to stamp downloaded filenames with today's date
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# All app data lives in %APPDATA%\PhoenixLandDept\ alongside settings.ini
_APP_DIR  = os.path.join(os.environ['APPDATA'], 'PhoenixLandDept')
_INI_PATH = os.path.join(_APP_DIR, 'settings.ini')
_SESSION  = os.path.join(_APP_DIR, 'session.json')  # persisted login cookies

# Both reports are downloaded on every Data Meeting Download run
_REPORT_URLS = [
    'https://ark.phoenixenergy.com/report?recordId=6789387edb62d9fbb70d6b8b',
    'https://ark.phoenixenergy.com/report?recordId=67bf95077dd3a6a940c3fe13',
]

# Unique SVG path data for the chevron-down dropdown trigger on the report page
_CHEVRON_PATH = 'M2.667 5.333 8 10.668l5.333-5.333H2.667z'

# How long to wait for the server to finish generating the report before
# opening the bell panel
_GENERATION_WAIT_MS = 10_000


def _read_credentials():
    # configparser lowercases all keys, so 'Username' in the INI is read as 'username'
    cfg = configparser.ConfigParser()
    cfg.read(_INI_PATH)
    return cfg['Credentials']['username'], cfg['Credentials']['password']


def _login(page, username, password):
    # Microsoft OAuth flow: email -> Next -> password -> Sign in -> Stay signed in
    page.fill('input[type="email"]', username)
    page.click('input[type="submit"]')  # "Next" button

    page.wait_for_selector('input[type="password"]', timeout=15_000)
    page.fill('input[type="password"]', password)
    page.click('input[type="submit"]')  # "Sign in" button

    # "Stay signed in?" prompt — clicking Yes maximises the session lifetime so
    # the saved session.json stays valid longer between runs
    try:
        page.wait_for_selector('#idSIButton9', timeout=8_000)
        page.click('#idSIButton9')
    except PlaywrightTimeout:
        pass  # prompt absent when MFA handles session extension instead

    # Wait until the browser is redirected back to the Phoenix app
    # 90 s timeout leaves room for manual MFA approval in the browser window
    page.wait_for_url('https://ark.phoenixenergy.com/**', timeout=90_000)


def _trigger_and_save(page, out_dir, report_url):
    # Navigate to this report's page and wait for it to fully load
    page.goto(report_url)
    page.wait_for_url('**/report**', timeout=20_000)
    page.wait_for_load_state('networkidle')

    # --- Step 1: open chevron dropdown and trigger report generation ---
    # The chevron button is identified by its unique SVG path; no text or id to rely on
    chevron = page.locator(f'button:has(svg path[d="{_CHEVRON_PATH}"])')
    chevron.click()

    # "Download" is the exact label of the generate-report option inside the dropdown.
    # The regex anchor avoids matching "Download File" in the bell panel.
    page.get_by_role('button', name=re.compile(r'^\s*Download\s*$')).first.click()

    # --- Step 2: wait for the server to build the report ---
    page.wait_for_timeout(_GENERATION_WAIT_MS)

    # --- Step 3: open bell panel and save the completed report ---
    # Bell button has a stable id so we can target it directly
    page.locator('#notifications-btn').click()

    # expect_download() intercepts the browser's file-save dialog automatically
    with page.expect_download(timeout=15_000) as dl_info:
        # .first picks the newest notification entry at the top of the list
        page.locator('button:has-text("Download File")').first.click()

    download = dl_info.value
    download.path()  # blocks until the temp file is fully written before we copy or close

    # The server doesn't send a Content-Disposition filename, so suggested_filename
    # is just a UUID. Strip any existing extension, append today's date as
    # month.day.year, then force a .csv extension so the file is usable immediately.
    filename = download.suggested_filename or 'report'
    base = filename[:-4] if filename.endswith('.csv') else filename
    today = date.today().strftime('%m.%d.%Y')  # e.g. 06.03.2026
    filename = f'{base}.{today}.csv'
    dest = os.path.join(out_dir, filename)
    download.save_as(dest)
    print(f'Saved: {dest}', flush=True)


def main():
    # Fixed destination for Data Meeting Downloads — always saves here regardless of argv[1].
    # makedirs with exist_ok=True creates the folder on first run without raising if it already exists.
    out_dir = r'C:\Users\Ethan Mesecher\Desktop\DMD'
    os.makedirs(out_dir, exist_ok=True)

    username, password = _read_credentials()

    with sync_playwright() as pw:
        # headless=False keeps the browser window visible so MFA prompts are accessible
        browser = pw.chromium.launch(headless=False)

        # Load saved session cookies to skip login when they are still valid.
        # accept_downloads=True tells Playwright to intercept downloads automatically
        # instead of letting Chrome show its native "Save As" dialog.
        ctx = browser.new_context(
            storage_state=_SESSION if os.path.exists(_SESSION) else None,
            accept_downloads=True
        )
        page = ctx.new_page()

        # Navigate to the first report to trigger any login redirect
        page.goto(_REPORT_URLS[0])
        if 'microsoftonline.com' in page.url or 'cloudflareaccess.com' in page.url:
            _login(page, username, password)

        # Download each report in sequence using the same authenticated session
        for url in _REPORT_URLS:
            _trigger_and_save(page, out_dir, url)

        # Write session cookies back so the next run can skip the login step
        ctx.storage_state(path=_SESSION)
        browser.close()


if __name__ == '__main__':
    main()
