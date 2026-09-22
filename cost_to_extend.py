import ctypes
import csv
import os
import re
from datetime import date

import ark_common


def _notify(message):
    ctypes.windll.user32.MessageBoxW(0, message, 'Cost to Extend', 0x40)


_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=67f413a4878d0fb2c4cf3411'
_UPLOAD_URL = 'https://ark.phoenixenergy.com/data/data-loader/newUpload'


def _to_float(s):
    s = s.strip().replace(',', '').replace('$', '')
    return float(s) if s else 0.0


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
    out_dir = ark_common.read_folder('CostToExtend', r'C:\Users\Ethan Mesecher\Desktop\C2E')
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
        try:
            page = ctx.new_page()

            page.goto(_REPORT_URL)
            if 'microsoftonline.com' in page.url or 'cloudflareaccess.com' in page.url:
                ark_common.login(page, username, password)

            dl = ark_common.trigger_download(page, _REPORT_URL)

            # Move the downloaded report into the C2E folder
            src_path = os.path.join(out_dir, dl.suggested_filename)
            dl.save_as(src_path)
            print(f'Downloaded: {src_path}', flush=True)

            rows = []
            with open(src_path, newline='', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header row
                for row in reader:
                    # A=Id, C=Total Cost to Extend, D=Land Holding NMA, E=$/Acre for Extension, N=Lease Notes & Additional Documentation
                    if len(row) < 14 or not row[0].strip():
                        continue
                    record_id = row[0].strip()
                    try:
                        total_cost = _to_float(row[2])
                        nma = _to_float(row[3])
                        per_acre = _to_float(row[4])
                    except ValueError:
                        continue
                    notes = row[13]

                    calculated = nma * per_acre
                    if abs(calculated - total_cost) > 10:
                        new_notes = f'{today_str} EM - Updated to match calculated cost to extend.\n\n{notes}'
                        rows.append((record_id, calculated, new_notes))

            if not rows:
                print('No rows exceeded the threshold — skipping export and upload.', flush=True)
            else:
                out_path = os.path.join(out_dir, f'cost_to_extend.{today_file_str}.csv')
                with open(out_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Id', 'Total Cost to Extend', 'Lease Notes & Additional Documentation'])
                    writer.writerows(rows)
                print(f'Saved {len(rows)} row(s) to: {out_path}', flush=True)

                _upload(page, out_path, f'cost to extend {today_file_str}')
        finally:
            # Persist whatever session now exists — including a freshly completed manual
            # login/2FA — even if a step above failed, so a crash doesn't force the user
            # to log in and redo 2FA again on the next run.
            ctx.storage_state(path=ark_common._SESSION)
            browser.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        _notify(f'Cost to Extend failed:\n{e}')
