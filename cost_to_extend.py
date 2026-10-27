"""Cost to Extend correction, launched by the "C2E" button.

Downloads the cost-to-extend landholding report from ark.phoenixenergy.com, finds rows
where NMA x $/acre differs from Total Cost to Extend by more than $10, writes the fixes
to cost_to_extend.MM.DD.YYYY.csv in the [Folders] CostToExtend folder, and uploads that
CSV back to Ark through the Data Loader as a Landholdings Update (changes live data).
Also Mirror's "C2E" step (mirror_step). Uses ark_common and Playwright; errors are shown in a message box.
"""
import csv
import os
from datetime import date

import ark_common


_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\C2E'  # output folder used when [Folders] CostToExtend is unset


def _notify(message):
    """Show an information message box titled Cost to Extend (the only visible error channel)."""
    ark_common.notify('Cost to Extend', message, 0x40)


_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=67f413a4878d0fb2c4cf3411'  # cost-to-extend landholdings report
_COLUMNS = (['Id', None, 'Total Cost to Extend', 'Land Holding NMA', '$/Acre for Extension'] + [None] * 8
            + ['Lease Notes & Additional Documentation'])  # report columns main reads by position (None = not read); checked on download


def _to_float(s):
    """Parse a currency/number string (commas and $ allowed); blank becomes 0.0."""
    s = s.strip().replace(',', '').replace('$', '')
    return float(s) if s else 0.0


def main():
    """Download the report, build the correction CSV, and upload it if any rows need fixing.
    Raises before reading it if the report lacks _COLUMNS.

    Always saves session.json and closes the browser, even on failure.
    Returns the number of landholdings fixed and uploaded (0 = nothing to fix).
    """
    out_dir = ark_common.read_folder('CostToExtend', _DEFAULT_DIR)
    os.makedirs(out_dir, exist_ok=True)

    today_str = date.today().strftime('%m/%d/%Y')
    today_file_str = date.today().strftime('%m.%d.%Y')

    
    with ark_common.ark_page(_REPORT_URL) as page:
        dl = ark_common.trigger_download(page, _REPORT_URL)

        # Move the downloaded report into the C2E folder
        src_path = os.path.join(out_dir, dl.suggested_filename)
        dl.save_as(src_path)
        print(f'Downloaded: {src_path}', flush=True)
        ark_common.check_columns(src_path, _COLUMNS, 'Cost to Extend')

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

            ark_common.upload(page, out_path, f'cost to extend {today_file_str}', dataset='Landholdings')
    return len(rows)


def mirror_step():
    """Mirror's C2E step: run and return (result kind, report line)."""
    fixed = main()
    if fixed:
        return ark_common.UPLOADED, f'Uploaded fixes for {ark_common.plural(fixed, "landholding")}'
    return ark_common.NOTHING, 'No cost to extend errors found'


if __name__ == '__main__':
    ark_common.run_button('Cost to Extend', main,
                          os.path.join(ark_common.read_folder('CostToExtend', _DEFAULT_DIR), 'cost_to_extend_error.log'))
