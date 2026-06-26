import os
import ark_common
from datetime import date
from playwright.sync_api import sync_playwright

# Both reports are downloaded on every Data Meeting Download run
_REPORT_URLS = [
    'https://ark.phoenixenergy.com/report?recordId=6789387edb62d9fbb70d6b8b',
    'https://ark.phoenixenergy.com/report?recordId=67bf95077dd3a6a940c3fe13',
]


def _trigger_and_save(page, out_dir, report_url):
    dl = ark_common.trigger_download(page, report_url)

    # The server doesn't send a Content-Disposition filename, so suggested_filename
    # is just a UUID. Strip any existing extension, append today's date as
    # month.day.year, then force a .csv extension so the file is usable immediately.
    filename = dl.suggested_filename or 'report'
    base = filename[:-4] if filename.endswith('.csv') else filename
    today = date.today().strftime('%m.%d.%Y')  # e.g. 06.03.2026
    dest = os.path.join(out_dir, f'{base}.{today}.csv')
    dl.save_as(dest)
    print(f'Saved: {dest}', flush=True)


def main():
    out_dir = ark_common.read_folder('DataMeetingDownload', r'C:\Users\Ethan Mesecher\Desktop\DMD')
    os.makedirs(out_dir, exist_ok=True)

    username, password = ark_common.read_credentials()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(
            storage_state=ark_common._SESSION if os.path.exists(ark_common._SESSION) else None,
            accept_downloads=True
        )
        page = ctx.new_page()

        page.goto(_REPORT_URLS[0])
        if 'microsoftonline.com' in page.url or 'cloudflareaccess.com' in page.url:
            ark_common.login(page, username, password)

        for url in _REPORT_URLS:
            _trigger_and_save(page, out_dir, url)

        ctx.storage_state(path=ark_common._SESSION)
        browser.close()


if __name__ == '__main__':
    main()
