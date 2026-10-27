"""QQ Checker, launched by the "QQ" button.

Reads QQ_Checker.csv (an Ark landholdings export) from the [Folders] QQ folder (settings.ini; default
Desktop\\QQ) and checks every row's Tract Description and Quarter Section against its 16 quarter-quarter
NMA columns (NENE NMA ... SESE NMA). A quarter-quarter "has a value" when its cell is a nonzero number;
blank and 0 both mean no interest.
- Tract Description must name exactly the quarter-quarters with values. It is a list of aliquots
  (E2, E2NW, S12NE14, NW4, "NE NW", lists joined by commas or &); a partial quarter-quarter
  (E2SWNE) counts as the whole quarter-quarter. Free text it can't read (lots, metes and bounds,
  "except ...") makes the row Unreadable.
- Quarter Section must cover exactly the quarters that have any value; any equivalent wording
  passes (E2,NW = N2,SE).
Writes QQ_Mismatches.MM.DD.YYYY.csv (Id, Tract Description, Quarter Section, State, Title Source,
Mismatch, Note, the quarter-quarters with values and how they differ, the Quarter Section the values
support) to the same folder, one row per failing landholding, then shows a message box with the
counts. Reads and writes local files only (no Ark login, no upload). Not a Mirror step.
"""
import csv
import os
import re
from datetime import date
from functools import lru_cache

import ark_common

_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\QQ'  # folder used when [Folders] QQ is unset
_INPUT_FILE = 'QQ_Checker.csv'  # the export to check, put in the folder by hand
_QQS = ['NENE', 'NWNE', 'SWNE', 'SENE', 'NENW', 'NWNW', 'SWNW', 'SENW',
        'NESW', 'NWSW', 'SWSW', 'SESW', 'NESE', 'NWSE', 'SWSE', 'SESE']  # quarter-quarters, in the export's column order
_QUARTERS = ['NW', 'NE', 'SE', 'SW']  # quarter order used when writing a Quarter Section
_REQUIRED_COLUMNS = ['Id', 'Tract Description', 'Quarter Section'] + [f'{qq} NMA' for qq in _QQS]  # must be in the export
_OUTPUT_HEADER = ['Id', 'Tract Description', 'Quarter Section', 'State', 'Title Source', 'Mismatch', 'Note',
                  'QQs With Values', 'Values Outside Tract', 'Tract QQs Without Values',
                  'Expected Quarter Section']  # columns of the QQ_Mismatches CSV
_TERM = r'[NS][EW]|[NSEW]2'  # one aliquot step: a quarter (NE) or a half (N2)
_ALIQUOT = re.compile(f'(?:{_TERM})+')  # a whole aliquot such as E2SWNE
_SINGLE = re.compile(f'(?:{_TERM})')  # a lone quarter or half, which joins the next word ("NE NW" = NENW)
_SEPARATORS = re.compile(r'[,;&]|\bAND\b')  # split a description into separate tracts
# Mismatch column values
TRACT = 'Tract'
QUARTER_SECTION = 'Quarter Section'
BOTH = 'Both'
UNREADABLE = 'Unreadable'
# Note column texts, one per kind of problem, so the export sorts by kind
NOTE_NO_VALUES = 'No quarter-quarter has a value'
NOTE_TRACT_PART_QUARTER = 'Values fill more of a quarter than the tract names'
NOTE_TRACT_OTHER_QUARTER = 'Values in a quarter the tract doesn\'t name'
NOTE_TRACT_NO_VALUE = 'Tract names quarter-quarters with no value'
NOTE_TRACT_BOTH_WAYS = 'Values and tract differ both ways'
NOTE_TRACT_BLANK = 'Tract Description is blank'
NOTE_TRACT_UNREADABLE = 'Tract Description couldn\'t be read'
NOTE_QS_MISSING = 'Quarter Section leaves out quarters with values'
NOTE_QS_EXTRA = 'Quarter Section names quarters with no values'
NOTE_QS_BOTH_WAYS = 'Quarter Section names the wrong quarters'
NOTE_QS_BLANK = 'Quarter Section is blank'
NOTE_QS_UNREADABLE = 'Quarter Section couldn\'t be read'


def _folder():
    """The working folder: [Folders] QQ, else _DEFAULT_DIR."""
    return ark_common.read_folder('QQ', _DEFAULT_DIR)


def _notify(message, flags=0x40):
    """Show a message box titled "QQ Checker" (info icon unless flags say otherwise)."""
    ark_common.notify('QQ Checker', message, flags)


def _normalize(word):
    """Uppercase and turn fraction notation into plain aliquots: N12 -> N2, SE14 / SE4 -> SE."""
    word = re.sub(r'([NSEW])12', r'\g<1>2', word.upper())
    return re.sub(r'(NE|NW|SE|SW)(?:14|4)', r'\1', word)


def aliquot_qqs(aliquot):
    """The quarter-quarters an aliquot touches (E2NW -> {NENW, SENW}; E2SWNE -> {SWNE}), or None if it
    isn't one. Steps apply right to left, each narrowing a box over the 4x4 grid of quarter-quarters."""
    aliquot = _normalize(aliquot)
    if not _ALIQUOT.fullmatch(aliquot):
        return None
    west, east, south, north = 0.0, 4.0, 0.0, 4.0
    for step in reversed(re.findall(_TERM, aliquot)):
        half_w, half_h = (east - west) / 2, (north - south) / 2
        if step in ('NE', 'NW', 'N2'):
            south += half_h
        if step in ('SE', 'SW', 'S2'):
            north -= half_h
        if step in ('NE', 'SE', 'E2'):
            west += half_w
        if step in ('NW', 'SW', 'W2'):
            east -= half_w
    return {qq for qq in _QQS if _overlaps(_cell(qq), (west, east, south, north))}


def _cell(qq):
    """(west, south) corner of a quarter-quarter on the 4x4 grid (SW corner of the section = 0, 0)."""
    small, quarter = qq[:2], qq[2:]
    return (2 * (quarter[1] == 'E') + (small[1] == 'E'), 2 * (quarter[0] == 'N') + (small[0] == 'N'))


def _overlaps(corner, box):
    """True if the 1x1 cell at corner overlaps box (west, east, south, north) by more than an edge."""
    x, y = corner
    west, east, south, north = box
    return x < east and x + 1 > west and y < north and y + 1 > south


@lru_cache(maxsize=None)
def description_qqs(text):
    """The quarter-quarters (a frozenset) a Tract Description or Quarter Section names, or None if any
    part can't be read; cached, since the same descriptions repeat across thousands of rows. Tracts are split on , ; & and AND; within a tract, two lone terms next to each other join
    ("NE NW" = NENW, "S2 NE" = S2NE) and other words are separate tracts ("S2NE W2" = S2NE + W2)."""
    qqs = set()
    for tract in _SEPARATORS.split(text.upper()):
        words = [_normalize(w.strip('.')) for w in tract.split()]
        i = 0
        while i < len(words):
            word = words[i]
            if (_SINGLE.fullmatch(word) and i + 1 < len(words) and _SINGLE.fullmatch(words[i + 1])):
                word, i = word + words[i + 1], i + 1
            found = aliquot_qqs(word)
            if found is None:
                return None
            qqs |= found
            i += 1
    return frozenset(qqs)


def _quarters(qqs):
    """The quarters (NE, NW, SE, SW) that hold any of qqs."""
    return {qq[2:] for qq in qqs}


def quarter_section(quarters):
    """Shortest Quarter Section for a set of quarters, worded as the exports usually are:
    N2 / S2 / E2 / W2, then N2 or S2 plus the odd quarter, NW,NE,SE,SW for all four."""
    if len(quarters) == 4:
        return 'NW,NE,SE,SW'
    for half, pair in (('N2', {'NE', 'NW'}), ('S2', {'SE', 'SW'}), ('E2', {'NE', 'SE'}), ('W2', {'NW', 'SW'})):
        if pair <= quarters:
            return ','.join([half] + [q for q in _QUARTERS if q in quarters - pair])
    return ','.join(q for q in _QUARTERS if q in quarters)


def _has_value(cell):
    """True if an NMA cell holds interest: a nonzero number, or any other text that isn't blank."""
    cell = (cell or '').strip()
    try:
        return float(cell.replace(',', '')) != 0
    except ValueError:
        return bool(cell)


def _list(qqs):
    """Quarter-quarters as text, in the export's column order."""
    return ', '.join(qq for qq in _QQS if qq in qqs)


def _tract_note(tract, named, valued):
    """Note for the Tract Description check, or '' if it matches. named is None when unreadable."""
    if named is None:
        return NOTE_TRACT_UNREADABLE
    if named == valued:
        return ''
    if not tract.strip():
        return NOTE_TRACT_BLANK
    extra, missing = valued - named, named - valued
    if extra and missing:
        return NOTE_TRACT_BOTH_WAYS
    if missing:
        return NOTE_TRACT_NO_VALUE
    return NOTE_TRACT_PART_QUARTER if _quarters(extra) <= _quarters(named) else NOTE_TRACT_OTHER_QUARTER


def _qs_note(text, named, valued):
    """Note for the Quarter Section check, or '' if it matches. named is None when unreadable."""
    if named is None:
        return NOTE_QS_UNREADABLE
    have, want = _quarters(named), _quarters(valued)
    if have == want:
        return ''
    if not text.strip():
        return NOTE_QS_BLANK
    if have - want and want - have:
        return NOTE_QS_BOTH_WAYS
    return NOTE_QS_EXTRA if have - want else NOTE_QS_MISSING


def check_row(row):
    """Check one export row (a dict by column name). Returns the output row, or None if it passes."""
    tract, qs = row.get('Tract Description') or '', row.get('Quarter Section') or ''
    valued = {qq for qq in _QQS if _has_value(row.get(f'{qq} NMA'))}
    named, qs_named = description_qqs(tract), description_qqs(qs)
    tract_note, qs_note = _tract_note(tract, named, valued), _qs_note(qs, qs_named, valued)
    if not tract_note and not qs_note:
        return None
    if named is None or qs_named is None:
        mismatch = UNREADABLE
    else:
        mismatch = BOTH if tract_note and qs_note else TRACT if tract_note else QUARTER_SECTION
    note = NOTE_NO_VALUES if not valued else '; '.join(n for n in (tract_note, qs_note) if n)
    return [row.get('Id', ''), tract, qs, row.get('State', ''), row.get('Title Source', ''), mismatch, note,
            _list(valued),
            '' if named is None else _list(valued - named),
            '' if named is None else _list(named - valued),
            quarter_section(_quarters(valued))]


def _read_rows(path):
    """Yield the export's rows as dicts. Raises RuntimeError if a _REQUIRED_COLUMNS column is missing.
    Reads UTF-8, falling back to Windows-1252 (Excel's plain "CSV" save)."""
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            with open(path, newline='', encoding=encoding) as f:
                reader = csv.DictReader(f)
                missing = [c for c in _REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
                if missing:
                    raise RuntimeError(f'{_INPUT_FILE} is missing column(s): {", ".join(missing)}')
                return list(reader)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f'{_INPUT_FILE} isn\'t UTF-8 or Windows-1252 text')


def _summary(checked, results, out_path):
    """Text of the finish message box: rows checked, mismatches by Mismatch kind, and the output path."""
    counts = {kind: sum(1 for r in results if r[5] == kind) for kind in (TRACT, QUARTER_SECTION, BOTH, UNREADABLE)}
    lines = [f'Checked {ark_common.plural(checked, "row")}: '
             f'{ark_common.plural(len(results), "mismatch", "mismatches")}.']
    if results:
        lines.append(f'Tract only: {counts[TRACT]}\nQuarter Section only: {counts[QUARTER_SECTION]}\n'
                     f'Both: {counts[BOTH]}\nUnreadable: {counts[UNREADABLE]}')
    lines.append(f'Saved to: {out_path}')
    return '\n\n'.join(lines)


def main():
    """Check every row of QQ_Checker.csv in the folder, write QQ_Mismatches.<date>.csv (header only if
    nothing fails) and show the summary box. Raises if the export is missing or lacks a column.
    Returns (rows checked, output rows)."""
    folder = _folder()
    in_path = os.path.join(folder, _INPUT_FILE)
    if not os.path.exists(in_path):
        raise RuntimeError(f'No {_INPUT_FILE} found. Save the export as:\n{in_path}')
    rows = _read_rows(in_path)
    results = [r for r in map(check_row, rows) if r]

    out_path = os.path.join(folder, f'QQ_Mismatches.{date.today():%m.%d.%Y}.csv')
    # BOM so Excel opens it as UTF-8 (descriptions and names can hold non-ASCII text)
    with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(_OUTPUT_HEADER)
        writer.writerows(results)

    _notify(_summary(len(rows), results, out_path))
    return len(rows), results


if __name__ == '__main__':
    ark_common.run_button('QQ Checker', main, os.path.join(_folder(), 'qq_checker_error.log'))
