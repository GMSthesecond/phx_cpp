"""Section Id Blank, launched by the "SIB" button.

Logs in to ark.phoenixenergy.com with Playwright and downloads two reports into the [Folders] SIB
folder (settings.ini): Landholdings_Section_Id_Blank_EM.csv (Id, Section Name, Section Id, State:
landholdings with no Section Id) and Section_ID_Getting.csv (Section: Id, Section Name: the sections
created in Ark in the last week). The new sections are merged into Section_ID_Index.csv (Section
Name, Section Id, Updated: every section, one Id per Section Name, kept between runs): a new name is
added, and a name already there that comes with a new Id gets that Id. Then the daily download is
deleted. A download listing one name with two different Ids stops the run for a manual check (the
index is left alone and the download kept). Each landholding whose Section Name matches an indexed
name (ignoring case and extra spaces) gets that Id. Writes Section_Id_Upload.MM.DD.YYYY.csv (Id,
Section Name, Section Id) and, if it has any rows, uploads it through the Ark Data Loader as a
Landholdings Update (changes live data). Landholdings with no matching section are left alone (the
section usually isn't in Ark yet). Then shows a message box with the counts. Also Mirror's "SIB"
step (mirror_step: no message box).
`py section_id_blank.py --seed` builds the index once from a full Section ID Getting download saved
in the folder as Section_ID_Getting.csv (no Ark; refuses if the index exists).
Uses ark_common for credentials, login, session.json, downloads and the upload.
"""
import csv
import os
import sys
from datetime import date

import ark_common

_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\SIB'  # folder used when [Folders] SIB is unset
_BLANK_URL = 'https://ark.phoenixenergy.com/report?recordId=63aa6abbf62cdd98fdf125b4'  # landholdings with a blank Section Id
_SECTIONS_URL = 'https://ark.phoenixenergy.com/report?recordId=a61b7fb4109328528bc92353'  # sections created in the last week, with Ids
_BLANK_FILE = 'Landholdings_Section_Id_Blank_EM.csv'  # saved name of the landholdings report (overwritten each run)
_SECTIONS_FILE = 'Section_ID_Getting.csv'  # saved name of the sections report; deleted once merged into the index
_INDEX_FILE = 'Section_ID_Index.csv'  # every section, one Id per Section Name; grows each run, never re-downloaded
_INDEX_HEADER = ['Section Name', 'Section Id', 'Updated']  # index columns; Updated = when the name got its current Id
_BLANK_COLUMNS = ['Id', 'Section Name', 'Section Id']  # landholdings report's first columns; checked on download
_SECTIONS_COLUMNS = ['Section: Id', 'Section Name']  # sections report's first columns; checked on download
_OUTPUT_HEADER = ['Id', 'Section Name', 'Section Id']  # columns of the Section_Id_Upload CSV
_MAX_LISTED = 20  # section names listed in a message box or error (the rest are counted)
_SEED_ARG = '--seed'  # command-line flag: build the index from a full download (seed)


def _notify(message, flags=0x40):
    """Show a message box titled "Section Id Blank" (info icon unless flags say otherwise)."""
    ark_common.notify('Section Id Blank', message, flags)


def _key(name):
    """Section Name as compared between the reports: uppercase, spaces collapsed."""
    return ' '.join((name or '').split()).upper()


def _listed(names):
    """Up to _MAX_LISTED names comma-joined, with how many more there are."""
    names = sorted(names)
    more = len(names) - _MAX_LISTED
    return ', '.join(names[:_MAX_LISTED]) + (f' ...and {more} more' if more > 0 else '')


def _read_download(path):
    """{name key: (Section Name, Section Id)} from a Section ID Getting download, in report order. Rows
    with no Id or no name are skipped; a name listed twice with the same Id is fine. A name listed with
    two different Ids raises RuntimeError naming them, for a manual check in Ark."""
    sections, clashes = {}, {}  # clashes: first spelling of a name -> its Ids, in report order
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            section_id = (row.get('Section: Id') or '').strip()
            name = ' '.join((row.get('Section Name') or '').split())
            if not (section_id and name):
                continue
            seen = sections.setdefault(_key(name), (name, section_id))
            if seen[1] != section_id:
                ids = clashes.setdefault(seen[0], [seen[1]])
                if section_id not in ids:
                    ids.append(section_id)
    if clashes:
        named = [f'{name} ({", ".join(ids)})' for name, ids in clashes.items()]
        raise RuntimeError(f'Section ID Getting lists {len(clashes)} Section Name(s) with more than one Section '
                           f'Id: {_listed(named)}. Check them in Ark by hand, then run SIB again. Nothing was '
                           f'added to {_INDEX_FILE}; the download is kept as {path}')
    return sections


def _read_index(path, out_dir):
    """{name key: [Section Name, Section Id, Updated]} from the index, in file order. RuntimeError if it's
    missing (saying how to rebuild it with --seed) or lists a name twice."""
    if not os.path.exists(path):
        raise RuntimeError(f'{_INDEX_FILE} is missing from {out_dir}. To rebuild it, download the full Section '
                           f'ID Getting report from Ark (every section, without the last-week filter) into that '
                           f'folder as {_SECTIONS_FILE}, then run: py section_id_blank.py {_SEED_ARG}')
    index, twice = {}, set()
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name, section_id = (row.get('Section Name') or '').strip(), (row.get('Section Id') or '').strip()
            if name and section_id:
                if _key(name) in index:
                    twice.add(name)
                index[_key(name)] = [name, section_id, (row.get('Updated') or '').strip()]
    if twice:
        raise RuntimeError(f'{_INDEX_FILE} lists {len(twice)} Section Name(s) more than once: {_listed(twice)}. '
                           'Keep one row for each, then run SIB again.')
    return index


def _merge(index, sections, today):
    """Merge a download's sections into index: a new name is added at the end, and an indexed name that
    comes with a different Id gets the new Id (both stamped today). Returns (names added, names whose
    Id was replaced)."""
    added, replaced = [], []
    for key, (name, section_id) in sections.items():
        entry = index.get(key)
        if entry is None:
            index[key] = [name, section_id, today]
            added.append(name)
        elif entry[1] != section_id:
            entry[1:] = [section_id, today]
            replaced.append(entry[0])
    return added, replaced


def _write_index(path, index):
    """Write the index (_INDEX_HEADER, then its rows) to path through a temp file, so a failed write
    can't leave half an index."""
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(_INDEX_HEADER)
        writer.writerows(index.values())
    os.replace(tmp, path)


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


def _match(landholdings, index):
    """Give each landholding the indexed Id of its Section Name.
    Returns (rows, unmatched): rows are [Id, Section Name, Section Id] to upload, unmatched are the
    landholdings with no section of that name."""
    rows, unmatched = [], []
    for record_id, name in landholdings:
        entry = index.get(_key(name))
        if entry:
            rows.append([record_id, name, entry[1]])
        else:
            unmatched.append(record_id)
    return rows, unmatched


def _write_csv(path, rows):
    """Write _OUTPUT_HEADER and rows to path as UTF-8 CSV."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(_OUTPUT_HEADER)
        writer.writerows(rows)


def _summary(count, rows, unmatched, added, replaced, out_path):
    """Text of the finish message box: counts, the output path, whether it was uploaded, and what the
    index gained (new sections, names that got a new Id)."""
    lines = [f'Found a Section Id for {len(rows)} of {count} landholding(s) with a blank Section Id.',
             f'Saved them to: {out_path}',
             'Uploaded them to Ark as a Landholdings Update.' if rows else 'Nothing to upload.']
    if unmatched:
        lines.append(f'{len(unmatched)} landholding(s) have a Section Name that isn\'t a section in Ark yet '
                     'and were left alone.')
    lines.append(f'Added {len(added)} new section(s) to {_INDEX_FILE}.')
    if replaced:
        lines.append(f'{len(replaced)} section name(s) got a new Section Id: {_listed(replaced)}')
    return '\n\n'.join(lines)


def main(quiet=False):
    """Read the index, log in, download both reports, merge the new sections into the index and delete
    their download, match landholdings to indexed names, write the dated CSV and upload it if it has any
    rows, then show the summary (not when quiet, for Mirror). Raises if the index is missing, a report
    lacks its columns (_BLANK_COLUMNS, _SECTIONS_COLUMNS) or the download lists a name with two Ids.
    Always saves the browser session and closes the browser, even on failure.
    Returns (landholdings uploaded, names added to the index, names whose Id was replaced)."""
    out_dir = ark_common.read_folder('SIB', _DEFAULT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    today = date.today()
    out_path = os.path.join(out_dir, f'Section_Id_Upload.{today:%m.%d.%Y}.csv')
    index_path = os.path.join(out_dir, _INDEX_FILE)
    index = _read_index(index_path, out_dir)  # before the browser opens: a missing index fails at once

    with ark_common.ark_page(_BLANK_URL) as page:
        for url, filename, columns, report in (
                (_BLANK_URL, _BLANK_FILE, _BLANK_COLUMNS, 'Landholdings Section Id Blank EM'),
                (_SECTIONS_URL, _SECTIONS_FILE, _SECTIONS_COLUMNS, 'Section ID Getting')):
            ark_common.trigger_download(page, url).save_as(os.path.join(out_dir, filename))
            ark_common.check_columns(os.path.join(out_dir, filename), columns, report)

        sections_path = os.path.join(out_dir, _SECTIONS_FILE)
        added, replaced = _merge(index, _read_download(sections_path), f'{today:%m/%d/%Y}')
        _write_index(index_path, index)
        os.remove(sections_path)

        landholdings = _read_blank(os.path.join(out_dir, _BLANK_FILE))
        rows, unmatched = _match(landholdings, index)
        _write_csv(out_path, rows)

        # Nothing to send when no landholding matched (an empty upload times out)
        if rows:
            ark_common.upload(page, out_path, f'section id {today:%m.%d.%Y}', dataset='Landholdings')

    if not quiet:
        _notify(_summary(len(landholdings), rows, unmatched, added, replaced, out_path))
    return len(rows), added, replaced


def seed():
    """--seed: build Section_ID_Index.csv from a full Section ID Getting download saved in the SIB folder
    as Section_ID_Getting.csv (no Ark; the download is kept). Refuses if the index already exists.
    Shows the count and returns it."""
    out_dir = ark_common.read_folder('SIB', _DEFAULT_DIR)
    index_path = os.path.join(out_dir, _INDEX_FILE)
    if os.path.exists(index_path):
        raise RuntimeError(f'{index_path} already exists; {_SEED_ARG} only builds a missing index')
    sections_path = os.path.join(out_dir, _SECTIONS_FILE)
    if not os.path.exists(sections_path):
        raise RuntimeError(f'Save a full Section ID Getting download as {sections_path} first')
    ark_common.check_columns(sections_path, _SECTIONS_COLUMNS, 'Section ID Getting')
    index = {}
    _merge(index, _read_download(sections_path), f'{date.today():%m/%d/%Y}')
    _write_index(index_path, index)
    _notify(f'Built {index_path} with {len(index):,} sections from {_SECTIONS_FILE}.')
    return len(index)


def mirror_step():
    """Mirror's SIB step: run quietly and return (result kind, report line) with the number of
    landholdings uploaded (Uploaded) or "No blank Section Ids to fill in", plus how many section names
    got a new Id in the index."""
    uploaded, _added, replaced = main(quiet=True)
    line = (f'Uploaded Section Ids for {ark_common.plural(uploaded, "landholding")}' if uploaded
            else 'No blank Section Ids to fill in')
    if replaced:
        line += f'; {ark_common.plural(len(replaced), "section name")} got a new Section Id'
    return (ark_common.UPLOADED if uploaded else ark_common.NOTHING), line


if __name__ == '__main__':
    ark_common.run_button('Section Id Blank', seed if sys.argv[1:] == [_SEED_ARG] else main,
                          os.path.join(ark_common.read_folder('SIB', _DEFAULT_DIR), 'section_id_blank_error.log'))
