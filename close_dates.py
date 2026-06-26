import csv
import os
import re
from datetime import date, datetime, timedelta
from playwright.sync_api import sync_playwright
import ark_common

_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=c348d047aeebd9028494bf6c'
_UPLOAD_URL = 'https://ark.phoenixenergy.com/data/data-loader/newUpload'


def _target_date():
    today = date.today()
    if today.weekday() == 0:  # Monday — use previous Friday
        return today - timedelta(days=3)
    return today - timedelta(days=1)


def _parse_date(s):
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Unrecognized date format: {s!r}')


def _upload(page, csv_path, upload_name, dataset='Landholdings', operation='Update'):
    page.goto(_UPLOAD_URL)
    page.wait_for_load_state('networkidle')

    # 1 — select the operation card (Update, Insert, etc.)
    card_label = page.locator('p.font-semibold', has_text=operation)
    card_label.wait_for(timeout=15_000)
    page.wait_for_timeout(1500)
    card_label.click()
    page.wait_for_load_state('networkidle')

    # 2 — select the dataset from the listbox
    page.locator('[aria-haspopup="listbox"]').click(timeout=10_000)
    page.get_by_role('option', name=dataset, exact=True).click(timeout=10_000)

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

    # Wait for "X of X" completion indicator (up to 2 minutes)
    page.get_by_text(re.compile(r'\d+ of \d+')).first.wait_for(timeout=120_000)
    print('Upload complete.', flush=True)


def main():
    out_dir = ark_common.read_folder('CloseDates', r'C:\Users\Ethan Mesecher\Desktop\Close Date')
    os.makedirs(out_dir, exist_ok=True)

    username, password = ark_common.read_credentials()
    target = _target_date()
    today_str = date.today().strftime('%m.%d.%Y')
    rows = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(
            storage_state=ark_common._SESSION if os.path.exists(ark_common._SESSION) else None,
            accept_downloads=True
        )
        page = ctx.new_page()

        page.goto(_REPORT_URL)
        if 'microsoftonline.com' in page.url or 'cloudflareaccess.com' in page.url:
            ark_common.login(page, username, password)

        dl = ark_common.trigger_download(page, _REPORT_URL)

        # Read the temp file while the browser still holds it open
        with open(dl.path(), newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header row
            for row in reader:
                if len(row) < 3:
                    continue
                record_id = row[1].strip()
                close_date_str = row[2].strip()
                try:
                    close_date = _parse_date(close_date_str)
                except ValueError:
                    continue
                if close_date == target:
                    rows.append((record_id, close_date_str))

        # Write filtered CSV before upload (path needed by _upload)
        out_path = os.path.join(out_dir, f'close_dates.{today_str}.csv')
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Id', 'Close Date'])
            writer.writerows(rows)
        print(f'Saved {len(rows)} row(s) to: {out_path}', flush=True)

        _upload(page, out_path, f'close date {today_str}')

        ctx.storage_state(path=ark_common._SESSION)
        browser.close()


if __name__ == '__main__':
    main()
