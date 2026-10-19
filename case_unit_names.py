"""Case Unit Names, launched by the "Cases Unit Names" button.

Logs in to ark.phoenixenergy.com with Playwright and downloads two reports into the
[Folders] CaseUnitNames folder (settings.ini): Units_For_Case_Names.csv (Record Id, STRs,
Unit Name) and Phoenix_Cases_Fixes.csv (Record Id, Applicant, PHX Unit Name, Sections).
Each case whose Sections are the exact same STR set as a named unit gets that unit's name
(several differently named units are comma-joined). Writes Case_Unit_Names.MM.DD.YYYY.csv
(Record Id, PHX Unit Name) to the same folder with only the matched cases whose PHX Unit Name
needs fixing (blank or different); cases that already have the matched name are left out.
If that CSV has any rows, uploads it through the Ark Data Loader as a Case Update (changes live
data). Then shows a message box that lists every case whose existing PHX Unit Name the upload
replaced. Also Mirror's last step (mirror_step: no message box, reports only the upload).
Uses ark_common for credentials, login, session.json, downloads and the upload.
"""
import csv
import os
from datetime import date

import ark_common

_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\Cases Unit Names'  # folder used when [Folders] CaseUnitNames is unset
_UNITS_URL = 'https://ark.phoenixenergy.com/report?recordId=2794f7e6d4a18cb904f6ea73'  # units whose names go on cases
_CASES_URL = 'https://ark.phoenixenergy.com/report?recordId=76241e3dc6c652a5bff8f0b3'  # cases to name
_UNITS_FILE = 'Units_For_Case_Names.csv'  # saved name of the units report (overwritten each run)
_CASES_FILE = 'Phoenix_Cases_Fixes.csv'   # saved name of the cases report (overwritten each run)
_OUTPUT_HEADER = ['Record Id', 'PHX Unit Name']  # columns of the Case_Unit_Names CSV
_MAX_LISTED = 30  # replaced cases listed in the message box; the rest go to a Replaced_Names CSV


def _notify(message, flags=0x40):
    """Show a message box titled "Case Unit Names" (info icon unless flags say otherwise)."""
    ark_common.notify('Case Unit Names', message, flags)


def _split_strs(value):
    """Split a comma-separated STR field into an uppercase set for order-insensitive comparison."""
    return frozenset(' '.join(part.split()).upper() for part in (value or '').split(',') if part.strip())


def _read_units(path):
    """Map each unit STR set to its unit names, sorted with duplicates removed.
    Units with no Unit Name or no STRs are skipped."""
    names_by_strs = {}
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name = (row.get('Unit Name') or '').strip()
            strs = _split_strs(row.get('STRs'))
            if name and strs:
                names_by_strs.setdefault(strs, set()).add(name)
    return {strs: sorted(names, key=str.upper) for strs, names in names_by_strs.items()}


def _read_cases(path):
    """Load cases as dicts with record_id, strs and existing (current PHX Unit Name values).
    Ark puts a case's extra list values on following rows with a blank Record Id. Those rows
    add to the case's existing names; their Sections are ignored."""
    cases = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            record_id = (row.get('Record Id') or '').strip()
            name = (row.get('PHX Unit Name') or '').strip()
            if record_id:
                cases.append({'record_id': record_id, 'strs': _split_strs(row.get('Sections')), 'existing': []})
            elif not cases:
                continue  # stray continuation row before any case
            if name and name not in cases[-1]['existing']:
                cases[-1]['existing'].append(name)
    return cases


def _match(cases, units):
    """Name each case after the units with exactly its STR set.
    Returns (rows, replaced, unmatched, correct): rows are [Record Id, PHX Unit Name] for matched
    cases that need fixing, replaced are (Record Id, old names, new names) where a different name
    was already set, unmatched are the Record Ids with no unit, and correct are the Record Ids
    that already have the matched names (left out of rows)."""
    rows, replaced, unmatched, correct = [], [], [], []
    for case in cases:
        names = units.get(case['strs'])
        if not names:
            unmatched.append(case['record_id'])
            continue
        if set(case['existing']) == set(names):
            correct.append(case['record_id'])
            continue
        new = ', '.join(names)
        rows.append([case['record_id'], new])
        if case['existing']:
            replaced.append((case['record_id'], ', '.join(case['existing']), new))
    return rows, replaced, unmatched, correct


def _write_csv(path, header, rows):
    """Write header and rows to path as UTF-8 CSV."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def _summary(case_count, rows, replaced, unmatched, correct, out_path, replaced_path):
    """Text of the finish message box: counts, the output path, whether it was uploaded and the replaced cases."""
    lines = [f'Matched {len(rows) + len(correct)} of {case_count} case(s) to a unit by STRs.']
    if correct:
        lines.append(f'{len(correct)} case(s) already had the right PHX Unit Name and were left out of the CSV.')
    lines.append(f'Saved {len(rows)} case(s) to fix: {out_path}')
    lines.append('Uploaded them to Ark as a Case Update.' if rows else 'Nothing to upload.')
    if unmatched:
        lines.append(f'{len(unmatched)} case(s) had no unit with the same STRs and were left out of the CSV.')
    if replaced:
        lines.append(f'{len(replaced)} case(s) already had a different PHX Unit Name. '
                     'The upload replaced it (Record Id: old -> new):')
        lines.append('\n'.join(f'{rid}: {old} -> {new}' for rid, old, new in replaced[:_MAX_LISTED]))
        if len(replaced) > _MAX_LISTED:
            lines.append(f'...and {len(replaced) - _MAX_LISTED} more. Full list: {replaced_path}')
    return '\n\n'.join(lines)


def main(quiet=False):
    """Log in, download both reports, match cases to units, write the dated CSV of cases to fix and
    upload it if it has any rows, then show the summary (not when quiet, for Mirror). Always saves
    the browser session and closes the browser, even on failure. Returns the number of cases uploaded."""
    out_dir = ark_common.read_folder('CaseUnitNames', _DEFAULT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    today = date.today().strftime('%m.%d.%Y')
    out_path = os.path.join(out_dir, f'Case_Unit_Names.{today}.csv')
    replaced_path = os.path.join(out_dir, f'Replaced_Names.{today}.csv')

    with ark_common.ark_page(_UNITS_URL) as page:
        for url, filename in ((_UNITS_URL, _UNITS_FILE), (_CASES_URL, _CASES_FILE)):
            ark_common.trigger_download(page, url).save_as(os.path.join(out_dir, filename))

        cases = _read_cases(os.path.join(out_dir, _CASES_FILE))
        units = _read_units(os.path.join(out_dir, _UNITS_FILE))
        rows, replaced, unmatched, correct = _match(cases, units)

        _write_csv(out_path, _OUTPUT_HEADER, rows)
        if len(replaced) > _MAX_LISTED:
            _write_csv(replaced_path, ['Record Id', 'Old PHX Unit Name', 'New PHX Unit Name'], replaced)

        # Nothing to send when every case is already right (an empty upload times out)
        if rows:
            ark_common.upload(page, out_path, f'case unit names {today}', dataset='Cases')

    if not quiet:
        _notify(_summary(len(cases), rows, replaced, unmatched, correct, out_path, replaced_path))
    return len(rows)


def mirror_step():
    """Mirror's Cases Unit Names step: run quietly and return (result kind, report line) saying only
    whether anything was uploaded."""
    uploaded = main(quiet=True)
    if uploaded:
        return ark_common.UPLOADED, f'Uploaded PHX Unit Names for {ark_common.plural(uploaded, "case")}'
    return ark_common.NOTHING, 'No case unit names to upload'


if __name__ == '__main__':
    ark_common.run_button('Case Unit Names', main,
                          os.path.join(ark_common.read_folder('CaseUnitNames', _DEFAULT_DIR), 'case_unit_names_error.log'))
