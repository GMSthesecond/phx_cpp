"""QQ button (qq_checker.py): checks each landholding's Tract Description and Quarter Section against its
quarter-quarter NMA values.

The aliquot parser and the row check are tested directly; main() runs for real on a QQ_Checker.csv
written into the test's QQ folder, and the output CSV and message box are checked. No network or Ark.
"""
from datetime import date

import pytest

import qq_checker as qq
from fakes import read_csv, write_csv

_QQS = ['NENE', 'NWNE', 'SWNE', 'SENE', 'NENW', 'NWNW', 'SWNW', 'SENW',
        'NESW', 'NWSW', 'SWSW', 'SESW', 'NESE', 'NWSE', 'SWSE', 'SESE']  # the export's NMA column order
_HEADER = (['Tract Description', 'Id'] + [f'{q} NMA' for q in _QQS]
           + ['Title Information', 'State', 'Title Source', 'Account Name', 'Title Certification Date',
              'Quarter Section'])  # QQ_Checker.csv columns, as Ark exports them
_E2_E2NW = {'NENE', 'NWNE', 'SWNE', 'SENE', 'NENW', 'SENW', 'NESE', 'NWSE', 'SWSE', 'SESE'}  # what "E2, E2NW" names


def export_row(tract, qs, values, record_id='LH-1', state='ND', source='Class A', zero=''):
    """One QQ_Checker.csv row: values is {QQ: NMA}; every other QQ cell is zero ('' or '0')."""
    cells = [str(values.get(q, zero)) for q in _QQS]
    return [tract, record_id] + cells + ['title info', state, source, 'Account', '1/1/2025', qs]


def row_dict(tract, qs, qqs, zero=''):
    """export_row as the dict check_row gets, with NMA 1 in each of qqs."""
    return dict(zip(_HEADER, export_row(tract, qs, {q: 1 for q in qqs}, zero=zero)))


def run(folders, rows, encoding='utf-8'):
    """Write QQ_Checker.csv with rows, run main(), return (main's result, output CSV rows)."""
    write_csv(folders['QQ'] / 'QQ_Checker.csv', [_HEADER] + rows, encoding=encoding)
    result = qq.main()
    return result, read_csv(folders['QQ'] / f'QQ_Mismatches.{date.today():%m.%d.%Y}.csv')


# ---- Reading aliquots ----

@pytest.mark.parametrize('aliquot, expected', [
    ('NE', {'NENE', 'NWNE', 'SWNE', 'SENE'}),
    ('E2', {'NENE', 'SENE', 'NESE', 'SESE', 'NWNE', 'SWNE', 'NWSE', 'SWSE'}),
    ('E2NW', {'NENW', 'SENW'}),
    ('S2SE', {'SWSE', 'SESE'}),
    ('E2E2', {'NENE', 'SENE', 'NESE', 'SESE'}),
    ('N2N2', {'NENE', 'NWNE', 'NENW', 'NWNW'}),
    ('SWSW', {'SWSW'}),
    ('E2SWNE', {'SWNE'}),         # part of a quarter-quarter counts as the whole one
    ('W2NENE', {'NENE'}),
    ('E2W2SE', {'NWSE', 'SWSE'}),
    ('S12NE14', {'SWNE', 'SENE'}),  # fraction notation: N12 = N2, NE14 = NE
    ('SE14SW14', {'SESW'}),
    ('NW4', {'NENW', 'NWNW', 'SWNW', 'SENW'}),
    ('N2NW4', {'NENW', 'NWNW'}),
    ('ne', {'NENE', 'NWNE', 'SWNE', 'SENE'}),
])
def test_aliquot_qqs(aliquot, expected):
    """Each aliquot names the quarter-quarters it touches."""
    assert qq.aliquot_qqs(aliquot) == expected


@pytest.mark.parametrize('aliquot', ['NWNWN', 'NE2NW', 'N2SE2', 'SWNE9', 'N3NW', 'W4NW', 'NNW', 'LOT', ''])
def test_aliquot_qqs_rejects_typos(aliquot):
    """Anything that isn't a clean aliquot is None (not guessed at)."""
    assert qq.aliquot_qqs(aliquot) is None


def test_description_lists_and_joins():
    """Commas, semicolons, & and AND separate tracts; spaces around commas don't matter."""
    assert qq.description_qqs('E2, E2NW') == _E2_E2NW
    assert qq.description_qqs('E2,E2NW') == _E2_E2NW
    assert qq.description_qqs('SWNE & N2SE') == qq.description_qqs('SWNE, N2SE')
    assert qq.description_qqs('SWNE and N2SE') == qq.description_qqs('SWNE; N2SE')
    assert qq.description_qqs('NE, ') == qq.aliquot_qqs('NE')


def test_description_space_rules():
    """Two lone terms side by side are one aliquot ("NE NW" = NENW, "S2 NE" = S2NE); a whole aliquot
    followed by a word starts a new tract ("S2NE W2" = S2NE + W2, "SW SWSE" = SW + SWSE)."""
    assert qq.description_qqs('NE NW') == {'NENW'}
    assert qq.description_qqs('S2 NW, NW NW') == {'SWNW', 'SENW', 'NWNW'}
    assert qq.description_qqs('S12 SE14') == {'SWSE', 'SESE'}
    assert qq.description_qqs('S2NE W2, SE') == qq.description_qqs('S2NE, W2, SE')
    assert qq.description_qqs('SW SWSE') == qq.description_qqs('SW, SWSE')


def test_description_blank_is_empty():
    """A blank description names nothing (read, not unreadable)."""
    assert qq.description_qqs('') == set()
    assert qq.description_qqs('  ') == set()


@pytest.mark.parametrize('text', ['N2 north of the railroad ROW', 'NENE, All except NENE', 'SW NE & Lt 4 & 5',
                                  '1 acre in SE corner of SWSE', 'Part W2SW', 'SWSW = 3 acres', 'SEW2 (?)'])
def test_description_free_text_is_unreadable(text):
    """Any word that isn't an aliquot makes the whole description unreadable."""
    assert qq.description_qqs(text) is None


@pytest.mark.parametrize('quarters, expected', [
    (set(), ''), ({'NE'}, 'NE'), ({'NE', 'NW'}, 'N2'), ({'SE', 'SW'}, 'S2'), ({'NE', 'SE'}, 'E2'),
    ({'NW', 'SW'}, 'W2'), ({'NE', 'NW', 'SE'}, 'N2,SE'), ({'NE', 'SE', 'NW'}, 'N2,SE'),
    ({'NE', 'SE', 'SW'}, 'S2,NE'), ({'NW', 'SE'}, 'NW,SE'), ({'NE', 'NW', 'SE', 'SW'}, 'NW,NE,SE,SW'),
])
def test_quarter_section_wording(quarters, expected):
    """The suggested Quarter Section uses the exports' usual wording."""
    assert qq.quarter_section(quarters) == expected


# ---- Checking a row ----

def test_matching_row_passes():
    """The spec example: "E2, E2NW" with values in exactly those 10 quarter-quarters and Quarter Section
    "E2,NW" passes; so does the equivalent "N2,SE", and so do 0 cells in place of blanks."""
    assert qq.check_row(row_dict('E2, E2NW', 'E2,NW', _E2_E2NW)) is None
    assert qq.check_row(row_dict('E2, E2NW', 'N2,SE', _E2_E2NW)) is None
    assert qq.check_row(row_dict('E2, E2NW', 'E2,NW', _E2_E2NW, zero='0')) is None
    assert qq.check_row(row_dict('NW,NE,SE,SW', 'NW, NE, SE, SW', set(_QQS))) is None


def test_values_filling_more_of_the_quarter():
    """Row 3 of the real export: "E2, E2NW" but the whole NW has values. Tract mismatch only; the
    output lists the extra quarter-quarters and the suggested Quarter Section."""
    out = qq.check_row(row_dict('E2, E2NW', 'E2,NW', _E2_E2NW | {'NWNW', 'SWNW'}))
    assert out == ['LH-1', 'E2, E2NW', 'E2,NW', 'ND', 'Class A', qq.TRACT, qq.NOTE_TRACT_PART_QUARTER,
                   'NENE, NWNE, SWNE, SENE, NENW, NWNW, SWNW, SENW, NESE, NWSE, SWSE, SESE',
                   'NWNW, SWNW', '', 'N2,SE']


def test_values_in_a_quarter_the_tract_doesnt_name():
    """Values in a quarter the tract never touches: both checks fail when the Quarter Section follows the tract."""
    out = qq.check_row(row_dict('SENE', 'NE', {'SENE', 'NESE'}))
    assert out[5:7] == [qq.BOTH, f'{qq.NOTE_TRACT_OTHER_QUARTER}; {qq.NOTE_QS_MISSING}']
    assert out[8:11] == ['NESE', '', 'E2']


def test_tract_names_qqs_without_values():
    """A tract quarter-quarter with no value is a tract mismatch listed under Tract QQs Without Values."""
    out = qq.check_row(row_dict('S2SE', 'SE', {'SESE'}))
    assert out[5:7] == [qq.TRACT, qq.NOTE_TRACT_NO_VALUE]
    assert out[8:10] == ['', 'SWSE']


def test_tract_off_both_ways():
    """Extra and missing quarter-quarters at once."""
    out = qq.check_row(row_dict('S2SE', 'SE', {'SESE', 'NESE'}))
    assert out[5:7] == [qq.TRACT, qq.NOTE_TRACT_BOTH_WAYS]
    assert out[8:10] == ['NESE', 'SWSE']


@pytest.mark.parametrize('qs, note', [
    ('NE', qq.NOTE_QS_MISSING),          # values in NE and NW
    ('N2,SE', qq.NOTE_QS_EXTRA),
    ('NE,SE', qq.NOTE_QS_BOTH_WAYS),
    ('', qq.NOTE_QS_BLANK),
])
def test_quarter_section_mismatches(qs, note):
    """Quarter Section must cover exactly the quarters with values; the tract here matches."""
    out = qq.check_row(row_dict('N2N2', qs, {'NENE', 'NWNE', 'NENW', 'NWNW'}))
    assert out[5:7] == [qq.QUARTER_SECTION, note]
    assert out[10] == 'N2'


def test_no_values_at_all():
    """A row with every quarter-quarter blank or 0 fails both checks with one note."""
    out = qq.check_row(row_dict('NE', 'NE', set(), zero='0'))
    assert out[5:8] == [qq.BOTH, qq.NOTE_NO_VALUES, '']
    assert out[9] == 'NENE, NWNE, SWNE, SENE'


def test_blank_tract_with_values():
    """A blank Tract Description is a tract mismatch with its own note."""
    out = qq.check_row(row_dict('', 'NE', {'NENE'}))
    assert out[5:7] == [qq.TRACT, qq.NOTE_TRACT_BLANK]


def test_unreadable_tract():
    """Free text makes the row Unreadable; the difference columns stay blank since nothing was read."""
    out = qq.check_row(row_dict('N2 north of the railroad ROW', 'N2', {'NENE', 'NWNE', 'NENW', 'NWNW'}))
    assert out[5:7] == [qq.UNREADABLE, qq.NOTE_TRACT_UNREADABLE]
    assert out[8:10] == ['', '']


def test_unreadable_tract_and_bad_quarter_section():
    """Unreadable wins the Mismatch column; the note still reports the Quarter Section problem."""
    out = qq.check_row(row_dict('NENE, All except NENE', 'NE', {'NENE', 'NESE'}))
    assert out[5:7] == [qq.UNREADABLE, f'{qq.NOTE_TRACT_UNREADABLE}; {qq.NOTE_QS_MISSING}']


def test_unreadable_quarter_section():
    """A Quarter Section that can't be read is Unreadable too."""
    out = qq.check_row(row_dict('NE', 'NE quarter', {'NENE', 'NWNE', 'SWNE', 'SENE'}))
    assert out[5:7] == [qq.UNREADABLE, qq.NOTE_QS_UNREADABLE]


@pytest.mark.parametrize('cell, expected', [('', False), ('0', False), ('0.0', False), (' ', False),
                                            ('6.66667', True), ('1,234.5', True), ('-1', True), ('x', True)])
def test_has_value(cell, expected):
    """Blank and zero are no interest; any other number, or stray text, is a value."""
    assert qq._has_value(cell) is expected


# ---- main() ----

def test_main_writes_only_failing_rows(folders, msgboxes):
    """main() reads QQ_Checker.csv from [Folders] QQ, writes the dated CSV with only the failing rows
    (in file order), and shows the counts."""
    nw = {'NENW', 'NWNW', 'SWNW', 'SENW'}
    (checked, results), out = run(folders, [
        export_row('E2, E2NW', 'E2,NW', {q: 6.66667 for q in _E2_E2NW}, record_id='OK-1'),
        export_row('E2, E2NW', 'E2,NW', {q: 1 for q in _E2_E2NW | nw}, record_id='T-1', zero='0'),
        export_row('NW', 'N2', {q: 1 for q in nw}, record_id='Q-1', state='MT', source='Class B'),
        export_row('NE', 'NE', {}, record_id='B-1', zero='0'),
        export_row('Lt 4', 'NW', {q: 1 for q in nw}, record_id='U-1'),
    ])

    assert checked == 5 and len(results) == 4
    assert out[0] == qq._OUTPUT_HEADER
    assert [(r[0], r[5]) for r in out[1:]] == [('T-1', qq.TRACT), ('Q-1', qq.QUARTER_SECTION),
                                               ('B-1', qq.BOTH), ('U-1', qq.UNREADABLE)]
    assert out[2][3:5] == ['MT', 'Class B']
    [(title, text)] = msgboxes
    assert title == 'QQ Checker'
    assert 'Checked 5 rows: 4 mismatches.' in text
    assert 'Tract only: 1\nQuarter Section only: 1\nBoth: 1\nUnreadable: 1' in text
    assert str(folders['QQ'] / f'QQ_Mismatches.{date.today():%m.%d.%Y}.csv') in text


def test_main_nothing_fails(folders, msgboxes):
    """With every row matching, the CSV still gets its header and the box says 0 mismatches."""
    (checked, results), out = run(folders, [export_row('SWSW', 'SW', {'SWSW': 2})])
    assert (checked, results) == (1, [])
    assert out == [qq._OUTPUT_HEADER]
    assert 'Checked 1 row: 0 mismatches.' in msgboxes[0][1]


def test_main_reads_windows_1252(folders, msgboxes):
    """An export re-saved from Excel as plain CSV (Windows-1252) still reads."""
    (checked, results), out = run(folders, [export_row('NE', 'NE', {'NENE': 1}, source='Clase Ñ')],
                                  encoding='cp1252')
    assert checked == 1 and out[1][4] == 'Clase Ñ'


def test_main_without_the_export(folders, msgboxes):
    """No QQ_Checker.csv in the folder: an error naming where to save it, and no output file."""
    with pytest.raises(RuntimeError, match='QQ_Checker.csv'):
        qq.main()
    assert not list(folders['QQ'].glob('QQ_Mismatches.*'))


def test_main_missing_a_column(folders, msgboxes):
    """An export without a needed column is refused, naming the column."""
    header = [c for c in _HEADER if c != 'SESE NMA']
    write_csv(folders['QQ'] / 'QQ_Checker.csv', [header, ['NE', 'LH-1'] + [''] * (len(header) - 2)])
    with pytest.raises(RuntimeError, match='SESE NMA'):
        qq.main()
