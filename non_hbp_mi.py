import csv
import os
import re
from datetime import date

import ark_common

_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=391d699d4edefdf6073d9e8f'
_UPLOAD_URL = 'https://ark.phoenixenergy.com/data/data-loader/newUpload'


def _upload(page, csv_path, upload_name, dataset='Units', operation='Update'):
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
    out_dir = ark_common.read_folder(
        'NonHBPMI', r'C:\Users\Ethan Mesecher\Desktop\Case Update'
    )
    os.makedirs(out_dir, exist_ok=True)

    username, password = ark_common.read_credentials()
    today_str = date.today().strftime('%m/%d/%Y')
    today_file_str = date.today().strftime('%m.%d.%Y')

    from playwright.sync_api import sync_playwright

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

        with open(dl.path(), newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            rows = []
            for row in reader:
                if len(row) < 2 or not row[0].strip():
                    continue
                row[1] = today_str
                row.append(today_str)
                rows.append(row)

        out_path = os.path.join(out_dir, f'non_hbp_mi.{today_file_str}.csv')
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if header is not None:
                writer.writerow(header + ['Last updated'])
            writer.writerows(rows)
        print(f'Saved {len(rows)} row(s) to: {out_path}', flush=True)

        _upload(page, out_path, f'case update {today_file_str}')

        ctx.storage_state(path=ark_common._SESSION)
        browser.close()


if __name__ == '__main__':
    main()
