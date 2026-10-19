"""Stamps today's date on every unit in an Ark report and re-uploads it (Case Update).
Launched by the "Case Update" button. Logs into Ark (ark_common credentials/session),
downloads the report, overwrites column 2 with today's date and appends a "Last updated"
column, writes non_hbp_mi.<mm.dd.yyyy>.csv to the [Folders] NonHBPMI folder, then uploads
it (if it has any rows) through the Ark data loader as a Units Update. Also Mirror's
"Case Update" step (mirror_step). Depends on playwright; errors shown in a message box.
"""
import csv
import os
from datetime import date

import ark_common


_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\Case Update'  # output folder used when [Folders] NonHBPMI is unset


def _notify(message):
    """Show an information message box titled Case Update (the only visible error channel)."""
    ark_common.notify('Case Update', message, 0x40)


_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=391d699d4edefdf6073d9e8f'  # Ark report of units to stamp (non-HBP MI units, per the filename)


def main():
    """Log in, download the report, set each row's date column to today, write the CSV, and
    upload it if it has any rows. Always saves the browser session and closes the browser,
    even on failure. Returns the number of units uploaded."""
    out_dir = ark_common.read_folder('NonHBPMI', _DEFAULT_DIR)
    os.makedirs(out_dir, exist_ok=True)

    today_str = date.today().strftime('%m/%d/%Y')
    today_file_str = date.today().strftime('%m.%d.%Y')

    
    with ark_common.ark_page(_REPORT_URL) as page:
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

        # Nothing to send when there are no rows (an empty upload used to time out)
        if rows:
            ark_common.upload(page, out_path, f'case update {today_file_str}', dataset='Units')
    return len(rows)


def mirror_step():
    """Mirror's Case Update step: run and return (result kind, report line)."""
    updated = main()
    if updated:
        return ark_common.UPLOADED, f"Updated {ark_common.plural(updated, 'unit')} to today's date"
    return ark_common.NOTHING, 'No units to update'


if __name__ == '__main__':
    ark_common.run_button('Case Update', main,
                          os.path.join(ark_common.read_folder('NonHBPMI', _DEFAULT_DIR), 'non_hbp_mi_error.log'))
