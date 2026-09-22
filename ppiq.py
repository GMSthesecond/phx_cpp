import csv
import os
import ark_common
from collections import defaultdict
from playwright.sync_api import sync_playwright

_PPIQ_FOLDER = r"C:\Users\Ethan Mesecher\Desktop\PPIQ"

# (url, generation_wait_ms) — time between triggering generation and checking the notification panel
_PPIQ_URLS = [
    ('https://ark.phxcapitalgroup.com/report?recordId=679290fbcd9e6c677fc1cb5d', 30_000),  # Landholdings In Queue (EM) — slow to prepare
    ('https://ark.phxcapitalgroup.com/report?recordId=6734f573e60ff45d13cc57a0', 60_000),  # EM All Landholdings
    ('https://ark.phxcapitalgroup.com/report?recordId=6792a720ccb927b757c7a6be', 10_000),  # All LHs In Queue (EM)
    ('https://ark.phoenixenergy.com/report?recordId=67f99dc7ca970119b2f06532',   80_000),  # All LHs In Queue (EM) (Inverse)
]


def _download_files():
    os.makedirs(_PPIQ_FOLDER, exist_ok=True)
    username, password = ark_common.read_credentials()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(
            storage_state=ark_common._SESSION if os.path.exists(ark_common._SESSION) else None,
            accept_downloads=True,
        )
        page = ctx.new_page()

        # Prime session / login for phxcapitalgroup.com
        first_url = _PPIQ_URLS[0][0]
        page.goto(first_url)
        if 'microsoftonline.com' in page.url or 'cloudflareaccess.com' in page.url:
            ark_common.login(page, username, password, success_url='https://ark.phxcapitalgroup.com/**')

        for i, (url, generation_wait_ms) in enumerate(_PPIQ_URLS):
            if i > 0:
                page.wait_for_timeout(30_000)  # 30-second delay between downloads

            # Domain switch on the last URL — check login for phoenixenergy.com
            if i == 3:
                page.goto(url)
                if 'microsoftonline.com' in page.url or 'cloudflareaccess.com' in page.url:
                    ark_common.login(page, username, password, success_url='https://ark.phoenixenergy.com/**')

            dl = ark_common.trigger_download(page, url, generation_wait_ms=generation_wait_ms)
            dest = os.path.join(_PPIQ_FOLDER, dl.suggested_filename)
            dl.save_as(dest)
            print(f'Saved: {dest}', flush=True)

        page.wait_for_timeout(10_000)  # let the last download finish writing before closing
        ctx.storage_state(path=ark_common._SESSION)
        browser.close()


def _run_analysis():
    paid = defaultdict(lambda: {"id": 0, "name": "", "price_paid": 0})
    queue = defaultdict(lambda: {"id": 0, "name": "", "price_paid": 0, "status": 0})
    all_lh = defaultdict(lambda: {"id": 0, "name": "", "statuses": []})
    all = defaultdict(lambda: {"id": 0, "name": "", "price_paid": 0, "LHtype": "", "LHname": ""})
    error = defaultdict(lambda: {"id": 0, "name": "", "price_paid": 0, "LHtype": "", "LHname": "", "Issue": "", "status": 0})

    paid_path       = os.path.join(_PPIQ_FOLDER, "Landholdings_In_Queue_(EM).csv")
    queue_path      = os.path.join(_PPIQ_FOLDER, "All_LHs_In_Queue_(EM).csv")
    all_path        = os.path.join(_PPIQ_FOLDER, "EM_All_Landholdings.csv")
    all_lh_path     = os.path.join(_PPIQ_FOLDER, "All_LHs_In_Queue_(EM)_(Inverse).csv")
    output_csv_path = os.path.join(_PPIQ_FOLDER, "Update_Inverted.csv")

    with open(all_path, "r", encoding="utf-8-sig") as file:
        csv_reader = csv.reader(file)
        for i, row in enumerate(csv_reader):
            if i == 0:
                continue
            id = row[0].strip()
            name = row[1]
            LHname = row[3]
            LHtype = row[4]
            price_paid = 0 if row[2] == "" else float(row[2])
            all[id]["name"] = name
            all[id]["price_paid"] = price_paid
            all[id]["LHname"] = LHname
            all[id]["LHtype"] = LHtype

    with open(paid_path, "r", encoding="utf-8-sig") as file:
        csv_reader = csv.reader(file)
        for i, row in enumerate(csv_reader):
            if i == 0:
                continue
            id = row[1].strip()
            name = row[3]
            price_paid = float(row[8])
            paid[id]["name"] = name
            paid[id]["price_paid"] = price_paid

    with open(all_lh_path, "r", encoding="utf-8-sig") as file:
        csv_reader = csv.reader(file)
        for i, row in enumerate(csv_reader):
            if i == 0:
                continue
            id = row[4].strip()
            name = row[3]
            status = row[2]
            all_lh[id]["name"] = name
            if status not in all_lh[id]["statuses"]:
                all_lh[id]["statuses"].append(status)

    with open(queue_path, "r", encoding="utf-8-sig") as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            id = row["LandHoldingTransaction: LandHolding Id"].strip()
            name = row["LandHoldingTransaction: LandHolding Name"].strip()
            status = row["Offer: Status"].strip()
            price_paid = float(row["LandHoldingTransaction: Total LandHolding Value"])
            if id == "":
                print(f"Skipping row with blank ID: {row}")
                continue
            queue[id]["name"] = name
            queue[id]["status"] = status
            queue[id]["price_paid"] = price_paid

    for id, data in paid.items():
        if id not in queue:
            error[id]["id"] = id
            error[id]["name"] = all[id]["name"]
            error[id]["price_paid"] = all[id]["price_paid"]
            error[id]["LHtype"] = all[id]["LHtype"]
            error[id]["LHname"] = all[id]["LHname"]
            error[id]["Issue"] = "Has price paid but not in queue"
            error[id]["status"] = ", ".join(all_lh[id]["statuses"])

    for id, data in all.items():
        if data["name"] == "Phoenix Capital Group Holdings, LLC" and data["price_paid"] == 0:
            error[id]["id"] = id
            error[id]["name"] = all[id]["name"]
            error[id]["price_paid"] = all[id]["price_paid"]
            error[id]["LHtype"] = all[id]["LHtype"]
            error[id]["LHname"] = all[id]["LHname"]
            error[id]["status"] = ", ".join(all_lh[id]["statuses"])
            error[id]["Issue"] = "Landholdings in PHX account need price paid"

    for id, data in queue.items():
        if id not in paid:
            error[id]["id"] = id
            error[id]["name"] = all[id]["name"]
            error[id]["price_paid"] = all[id]["price_paid"]
            error[id]["LHtype"] = all[id]["LHtype"]
            error[id]["LHname"] = all[id]["LHname"]
            error[id]["status"] = data["status"]
            error[id]["Issue"] = "Curative offers should have price paid"

    for id, paid_data in paid.items():
        if id in queue:
            queue_data = queue[id]
            diff = paid_data["price_paid"] - float(queue_data["price_paid"])
            if paid_data["price_paid"] != float(queue_data["price_paid"]) and (diff > 1 or diff < -1):
                error[id]["id"] = id
                error[id]["name"] = queue[id]["name"]
                error[id]["price_paid"] = queue[id]["price_paid"]
                error[id]["status"] = queue[id]["status"]
                error[id]["Issue"] = "LHT Doesn't match LH Price Paid"

    with open(output_csv_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["ID", "Price Paid", "Type", "Account Name", "LH Name", "Issue", "Status"])
        for id in error:
            if error[id]["name"] != "":
                writer.writerow([
                    id,
                    error[id]["price_paid"],
                    error[id]["LHtype"],
                    error[id]["name"],
                    error[id]["LHname"],
                    error[id]["Issue"],
                    error[id]["status"],
                ])

    print(f"Done. {len(error)} issues written to {output_csv_path}")


if __name__ == '__main__':
    _download_files()
    _run_analysis()
