"""Section Id Blank, launched by the "SIB" button.

Logs in to ark.phoenixenergy.com with Playwright and downloads two reports into the [Folders] SIB
folder (settings.ini): Landholdings_Section_Id_Blank_EM.csv (Id, Section Name, Section Id, State:
landholdings with no Section Id) and Section_ID_Getting.csv (Section: Id, Section Name: every
section in Ark). Each landholding whose Section Name matches a section's name (ignoring case and
extra spaces) gets that section's Id. Writes Section_Id_Upload.MM.DD.YYYY.csv (Id, Section Name,
Section Id) to the same folder and, if it has any rows, uploads it through the Ark Data Loader as a
Landholdings Update (changes live data). Landholdings with no matching section are left alone (the
section usually isn't in Ark yet), and so are names that match more than one section. Then shows a
message box with the counts. Also Mirror's "SIB" step (mirror_step: no message box).
Uses ark_common for credentials, login, session.json, downloads and the upload.
"""
import csv
import os
from datetime import date

import ark_common

_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\SIB'  # folder used when [Folders] SIB is unset
_BLANK_URL = 'https://ark.phoenixenergy.com/report?recordId=63aa6abbf62cdd98fdf125b4'  # landholdings with a blank Section Id
_SECTIONS_URL = 'https://ark.phoenixenergy.com/report?recordId=a61b7fb4109328528bc92353'  # every section and its Id
_BLANK_FILE = 'Landholdings_Section_Id_Blank_EM.csv'  # saved name of the landholdings report (overwritten each run)
_SECTIONS_FILE = 'Section_ID_Getting.csv'  # saved name of the sections report (overwritten each run)
_BLANK_COLUMNS = ['Id', 'Section Name', 'Section Id']  # landholdings report's first columns; checked on download
_SECTIONS_COLUMNS = ['Section: Id', 'Section Name']  # sections report's first columns; checked on download
_OUTPUT_HEADER = ['Id', 'Section Name', 'Section Id']  # columns of the Section_Id_Upload CSV
_MAX_LISTED = 20  # section names matching more than one section listed in the message box


def _notify(message, flags=0x40):
    """Show a message box titled "Section Id Blank" (info icon unless flags say otherwise)."""
    ark_common.notify('Section Id Blank', message, flags)


def _key(name):
    """Section Name as compared between the reports: uppercase, spaces collapsed."""
    return ' '.join((name or '').split()).upper()


def _read_sections(path):
    """Map each section name (_key) to the set of section Ids with that name. Rows with no Id or
    no name are skipped."""
    ids_by_name = {}
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            section_id = (row.get('Section: Id') or '').strip()
            name = _key(row.get('Section Name'))
            if section_id and name:
                ids_by_name.setdefault(name, set()).add(section_id)
    return ids_by_name


def _read_blank(path):
    """Landholdings still missing a Section Id, as (Id, Section Name) in report order. Rows with no
    Id or no Section Name are skipped, and so are rows that already have a Section Id."""
    landholdings = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            record_id = (row.get('Id') or '').strip()
            name = (row.get('Section Name') or '').strip()
            if record_id and name and not (row.get('Section Id') or '').strip():
                landholdings.append((record_id, name))
    return landholdings


def _match(landholdings, sections):
    """Give each landholding the Id of the section with its name.
    Returns (rows, unmatched, ambiguous): rows are [Id, Section Name, Section Id] to upload,
    unmatched are the landholdings with no section of that name, and ambiguous are the
    sorted Section Names that match more than one section (their landholdings are left out)."""
    rows, unmatched, ambiguous = [], [], set()
    for record_id, name in landholdings:
        ids = sections.get(_key(name))
        if not ids:
            unmatched.append(record_id)
        elif len(ids) > 1:
            ambiguous.add(name)
        else:
            rows.append([record_id, name, next(iter(ids))])
    return rows, unmatched, sorted(ambiguous)


def _write_csv(path, rows):
    """Write _OUTPUT_HEADER and rows to path as UTF-8 CSV."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(_OUTPUT_HEADER)
        writer.writerows(rows)


def _summary(count, rows, unmatched, ambiguous, out_path):
    """Text of the finish message box: counts, the output path, whether it was uploaded and the
    ambiguous section names."""
    lines = [f'Found a Section Id for {len(rows)} of {count} landholding(s) with a blank Section Id.',
             f'Saved them to: {out_path}',
             'Uploaded them to Ark as a Landholdings Update.' if rows else 'Nothing to upload.']
    if unmatched:
        lines.append(f'{len(unmatched)} landholding(s) have a Section Name that isn\'t a section in Ark yet '
                     'and were left alone.')
    if ambiguous:
        lines.append(f'{len(ambiguous)} Section Name(s) match more than one section, so their landholdings '
                     'were left out:')
        lines.append(', '.join(ambiguous[:_MAX_LISTED])
                     + (f' ...and {len(ambiguous) - _MAX_LISTED} more' if len(ambiguous) > _MAX_LISTED else ''))
    return '\n\n'.join(lines)


def main(quiet=False):
    """Log in, download both reports, match landholdings to sections by name, write the dated CSV and
    upload it if it has any rows, then show the summary (not when quiet, for Mirror). Raises if either
    report lacks its columns (_BLANK_COLUMNS, _SECTIONS_COLUMNS). Always saves the browser session and
    closes the browser, even on failure. Returns (landholdings uploaded, ambiguous section names)."""
    out_dir = ark_common.read_folder('SIB', _DEFAULT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    today = date.today().strftime('%m.%d.%Y')
    out_path = os.path.join(out_dir, f'Section_Id_Upload.{today}.csv')

    with ark_common.ark_page(_BLANK_URL) as page:
        for url, filename, columns, report in (
                (_BLANK_URL, _BLANK_FILE, _BLANK_COLUMNS, 'Landholdings Section Id Blank EM'),
                (_SECTIONS_URL, _SECTIONS_FILE, _SECTIONS_COLUMNS, 'Section ID Getting')):
            ark_common.trigger_download(page, url).save_as(os.path.join(out_dir, filename))
            ark_common.check_columns(os.path.join(out_dir, filename), columns, report)

        landholdings = _read_blank(os.path.join(out_dir, _BLANK_FILE))
        sections = _read_sections(os.path.join(out_dir, _SECTIONS_FILE))
        rows, unmatched, ambiguous = _match(landholdings, sections)
        _write_csv(out_path, rows)

        # Nothing to send when no landholding matched (an empty upload times out)
        if rows:
            ark_common.upload(page, out_path, f'section id {today}', dataset='Landholdings')

    if not quiet:
        _notify(_summary(len(landholdings), rows, unmatched, ambiguous, out_path))
    return len(rows), ambiguous


def mirror_step():
    """Mirror's SIB step: run quietly and return (result kind, report line) with the number of
    landholdings uploaded, plus any section names that matched more than one section (REVIEW when
    those are all there is)."""
    uploaded, ambiguous = main(quiet=True)
    parts = []
    if uploaded:
        parts.append(f'Uploaded Section Ids for {ark_common.plural(uploaded, "landholding")}')
    if ambiguous:
        parts.append(f'{ark_common.plural(len(ambiguous), "Section Name")} matched more than one section: '
                     'run SIB to see them')
    if uploaded:
        return ark_common.UPLOADED, '; '.join(parts)
    if ambiguous:
        return ark_common.REVIEW, parts[0]
    return ark_common.NOTHING, 'No blank Section Ids to fill in'


if __name__ == '__main__':
    ark_common.run_button('Section Id Blank', main,
                          os.path.join(ark_common.read_folder('SIB', _DEFAULT_DIR), 'section_id_blank_error.log'))
