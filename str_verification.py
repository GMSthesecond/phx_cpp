import os
import csv
import ark_common
from collections import defaultdict
from playwright.sync_api import sync_playwright

_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=4d424303b039c7d617785bde'

_OUT_DIR    = ark_common.read_folder('STRVerification', r'C:\Users\Ethan Mesecher\Desktop\AOI-STR')
_INPUT_PATH = os.path.join(_OUT_DIR, 'Check_STR_(EM)_(Full).csv')
_ERROR_PATH = os.path.join(_OUT_DIR, 'Error_Report.csv')


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_report(page):
    dl = ark_common.trigger_download(page, _REPORT_URL, generation_wait_ms=60_000)
    os.makedirs(_OUT_DIR, exist_ok=True)
    dl.save_as(_INPUT_PATH)
    print(f'Saved: {_INPUT_PATH}', flush=True)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def _process():
    errors = defaultdict(lambda: {"id": 0, "section_name": "", "area_of_interest": "", "combined_str": "", "issue": ""})

    with open(_INPUT_PATH, "r", encoding="utf-8-sig") as file:
        csv_reader = csv.reader(file)
        for i, row in enumerate(csv_reader):
            if i == 0:
                continue
            id               = row[0]
            section          = row[1]
            township         = row[2]
            range_           = row[3]
            section_name     = row[4]
            if section_name == "":
                continue
            township_name    = row[5]
            area_of_interest = row[7]

            section0      = section
            section_name0 = section_name
            if len(section) == 1 and section.isdigit() and section[0] != "0":
                section = '0' + section
            if len(section_name) > 1 and section_name[0] in "123456789" and section_name[1] == '-':
                section_name = '0' + section_name

            if township == "" or range_ == "":
                combined_str = f"{section}-{township_name}"
            else:
                combined_str = f"{section}-{township}-{range_}"

            if section_name != combined_str:
                errors[id]["id"]           = id
                errors[id]["section_name"] = section_name
                errors[id]["combined_str"] = combined_str
                errors[id]["issue"]        = "Combined STR doesn't match Section Name"

            if area_of_interest not in ("Non-Ops", ""):
                if (section0 + ",") in area_of_interest and (township + "-" + range_) in area_of_interest:
                    pass
                elif section_name0 in area_of_interest:
                    pass
                else:
                    errors[id]["id"]               = id
                    errors[id]["section_name"]     = section_name0
                    errors[id]["area_of_interest"] = area_of_interest
                    errors[id]["combined_str"]     = combined_str
                    errors[id]["issue"]            = "area of interest cannot be verified automatically"

    with open(_ERROR_PATH, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['ID', 'Section Name', 'Combined STR', 'Area of Interest', 'Issue'])
        for id in errors:
            writer.writerow([id, errors[id]['section_name'], errors[id]['combined_str'], errors[id]['area_of_interest'], errors[id]['issue']])

    print(f'Error report: {_ERROR_PATH}', flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    username, password = ark_common.read_credentials()

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

        _download_report(page)

        ctx.storage_state(path=ark_common._SESSION)
        browser.close()

    _process()


if __name__ == '__main__':
    import traceback
    _LOG_PATH = os.path.join(_OUT_DIR, 'str_verification_error.log')
    try:
        main()
    except Exception:
        os.makedirs(_OUT_DIR, exist_ok=True)
        with open(_LOG_PATH, 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
        raise
