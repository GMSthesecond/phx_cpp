import ctypes
import csv
import os
import ark_common
from playwright.sync_api import sync_playwright
from openpyxl import Workbook
from openpyxl.styles import PatternFill
from openpyxl.cell import WriteOnlyCell


def _notify(message):
    ctypes.windll.user32.MessageBoxW(0, message, 'TPP-LHPP', 0x40)


_OUT_DIR = r"C:\Users\Ethan Mesecher\Desktop\TPP-LHPP"

# (url, generation_wait_ms) — the LandHoldingTransactions report has ~350k+ rows and can take
# well over the 10s default to finish generating server-side; grabbing the download too early
# silently returns a stale previously-generated copy instead of erroring, which was causing
# offers with recently-added LandHoldingTransactions to show up as having 0 LHT total.
_REPORT_URLS = [
    ('https://ark.phoenixenergy.com/report?recordId=688d3dfda95ef3a2a6ba14f9', 15_000),   # Offers report
    ('https://ark.phoenixenergy.com/report?recordId=689257e3d2b183ad4f221902', 120_000),  # LandHoldingTransactions — large, slow to generate
]

_OFFERS_FILENAME = 'Offers_Report_For_Price_Comparison_EM.csv'
_LHT_FILENAME = 'LandHoldingTransactions_For_Price_Comparison_EM.csv'
_EXPORT_FILENAME = 'PHX_Price_Paid_Export.xlsx'

_YELLOW_FILL = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')


def _download_files():
    os.makedirs(_OUT_DIR, exist_ok=True)
    username, password = ark_common.read_credentials()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(
            storage_state=ark_common._SESSION if os.path.exists(ark_common._SESSION) else None,
            accept_downloads=True,
        )
        try:
            page = ctx.new_page()

            page.goto(_REPORT_URLS[0][0])
            if 'microsoftonline.com' in page.url or 'cloudflareaccess.com' in page.url:
                ark_common.login(page, username, password)

            for i, (url, generation_wait_ms) in enumerate(_REPORT_URLS):
                if i > 0:
                    page.wait_for_timeout(30_000)  # 30-second delay between downloads

                dl = ark_common.trigger_download(page, url, generation_wait_ms=generation_wait_ms)
                dest = os.path.join(_OUT_DIR, dl.suggested_filename)
                dl.save_as(dest)
                print(f'Saved: {dest}', flush=True)

            page.wait_for_timeout(10_000)  # let the last download finish writing before closing
        finally:
            ctx.storage_state(path=ark_common._SESSION)
            browser.close()


def _find_file(filename):
    for name in os.listdir(_OUT_DIR):
        if name.lower() == filename.lower():
            return os.path.join(_OUT_DIR, name)
    return None


def _process_offers(offers):
    path = _find_file(_OFFERS_FILENAME)
    if not path:
        return

    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            offer_id = row['Id'].strip()
            offer = offers.setdefault(offer_id, {
                'offer_tpp': 0.0, 'lht_tpp': 0.0, 'status': '', 'close_date': '',
            })

            tpp = row['Total Purchase Price'].strip()
            if tpp:
                try:
                    offer['offer_tpp'] = float(tpp)
                except ValueError:
                    print(f'Error parsing {offer_id}')

            status = row['Status'].strip()
            if status:
                offer['status'] = status

            close_date = row['Close Date'].strip()
            if close_date:
                offer['close_date'] = close_date


def _process_lht(offers):
    path = _find_file(_LHT_FILENAME)
    if not path:
        return

    # Multiple LandHoldingTransaction rows can share the same offer id — sum their values.
    totals = {}
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            offer_id = row['LandHoldingTransaction: Offer Id'].strip()
            value = row['LandHoldingTransaction: Total LandHolding Value'].strip()
            if not value:
                continue
            try:
                totals[offer_id] = totals.get(offer_id, 0.0) + float(value)
            except ValueError:
                print(f'Error parsing {offer_id}')

    # Only apply LHT totals to offers that actually appear in the Offers report —
    # LandHoldingTransactions with no matching offer aren't a real comparison and
    # would otherwise flood the export as trivial "mismatches" (0 vs. some value).
    for offer_id, lht_tpp in totals.items():
        if offer_id in offers:
            offers[offer_id]['lht_tpp'] = lht_tpp


def _export(offers):
    export_path = os.path.join(_OUT_DIR, _EXPORT_FILENAME)

    # write_only mode streams rows instead of building an in-memory cell grid —
    # required here since a mismatched offer highlights all 5 cells in its row,
    # and normal openpyxl cell styling is far too slow at 100k+ styled rows.
    wb = Workbook(write_only=True)
    ws = wb.create_sheet('Export Data')

    ws.append(['Offer ID', 'Total Purchase Price', 'LHT Price Total', 'Close Date', 'Status'])

    for offer_id, offer in offers.items():
        diff = offer['lht_tpp'] - offer['offer_tpp']
        # A >$1 tolerance filters out float-rounding noise from summing many small
        # LHT values (e.g. off by a few cents) that isn't a real price mismatch.
        if -1 <= diff <= 1:
            continue

        values = [offer_id, offer['offer_tpp'], offer['lht_tpp'], offer['close_date'], offer['status']]
        row = []
        for value in values:
            cell = WriteOnlyCell(ws, value=value)
            cell.fill = _YELLOW_FILL
            row.append(cell)
        ws.append(row)

    wb.save(export_path)
    print(f'Data successfully exported to: {export_path}', flush=True)


def main():
    _download_files()

    offers = {}
    _process_offers(offers)
    _process_lht(offers)
    _export(offers)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        _notify(f'TPP-LHPP failed:\n{e}')
