"""Deceased button (deceased.py): splits a deceased owner's holdings among heirs.

main() runs against the [Folders] Deceased folder, redirected to a temp folder by the folders fixture.
"""
import pytest

import deceased
from fakes import read_csv, write_csv

_N_COLUMNS = 163  # columns in the Ark landholding export and in deceased_upload.csv

# Column indexes in the deceased account export (see deceased.py)
_ACCOUNT_NAME, _LE, _TYPE, _TITLE_SOURCE, _SECTION_NAME, _TRACT, _TITLE_INFO = 1, 2, 3, 8, 10, 17, 18
_MINERAL_INTEREST, _FIRST_NMA, _LAST_NMA, _COST_TO_EXTEND = 23, 25, 40, 157


def _holding(section_name, holding_type='Mineral', nma='40', interest='0.5'):
    """One 163-column row of the deceased account's landholding export."""
    row = [''] * _N_COLUMNS
    row[0], row[_ACCOUNT_NAME], row[_LE] = 'ACC-DEAD', 'Estate of J. Doe', 'J. Doe'
    row[_TYPE], row[_TITLE_SOURCE], row[_SECTION_NAME] = holding_type, 'Probate', section_name
    row[_TITLE_INFO] = 'Original title.'
    row[_MINERAL_INTEREST] = interest
    for i in range(_FIRST_NMA, _LAST_NMA + 1):
        row[i] = '0'
    row[_FIRST_NMA] = nma
    row[_COST_TO_EXTEND] = '1000'
    return row


def _heir(legal_entity, share):
    """One heir_template.csv row (20 columns)."""
    return [share, f'ACC-{legal_entity}', f'{legal_entity} Account', legal_entity, 'Individual',
            f'{legal_entity} Signer', 'Self', legal_entity.split()[-1]] + [''] * 11 + ['Heir title note.']


@pytest.fixture
def tmp_path(folders):
    """The [Folders] Deceased folder (temp), under the name the tests already use."""
    return folders['Deceased']


def _run(tmp_path, holdings, heirs):
    """Writes both inputs to the Deceased folder, runs deceased.main(), and returns the output rows."""
    write_csv(tmp_path / 'EM_Deceased_Account_Distribution_(LH).csv', [['header'] * _N_COLUMNS] + holdings)
    write_csv(tmp_path / 'heir_template.csv', [['header'] * 20] + heirs)
    deceased.main()
    return read_csv(tmp_path / 'deceased_upload.csv')


def test_runs_twice_in_one_process_without_mixing_results(tmp_path, msgboxes):
    """Each main() starts fresh (no rows left over from the last run), and the box gives the row count and file."""
    _run(tmp_path, [_holding('01-150N-100W')], [_heir('Ann Doe', '0.5'), _heir('Bob Doe', '0.5')])
    rows = _run(tmp_path, [_holding('02-150N-100W')], [_heir('Cy Doe', '1')])
    assert len(rows) == 2 and rows[1][2] == 'Cy Doe'
    assert msgboxes[-1] == ('Deceased', f'Wrote 1 heir row to:\n{tmp_path / "deceased_upload.csv"}')


def test_each_heir_gets_a_scaled_copy_of_each_holding(tmp_path):
    """2 heirs x 2 holdings = 4 rows; NMA, interest and cost to extend scale by share."""
    rows = _run(tmp_path, [_holding('01-150N-100W'), _holding('02-150N-100W', nma='80')],
                [_heir('Ann Doe', '0.25'), _heir('Bob Doe', '0.75')])

    header, body = rows[0], rows[1:]
    assert len(header) == _N_COLUMNS and all(len(r) == _N_COLUMNS for r in body)
    col = {name: header.index(name) for name in
           ('Legal Entity', 'Section Name', 'NENE NMA', 'Mineral Interest', 'Total Cost to Extend',
            'Title Landman', 'Title Information', 'Signer 1')}
    got = {(r[col['Legal Entity']], r[col['Section Name']]): r for r in body}
    assert set(got) == {(h, s) for h in ('Ann Doe', 'Bob Doe') for s in ('01-150N-100W', '02-150N-100W')}

    bob_02 = got[('Bob Doe', '02-150N-100W')]
    assert float(bob_02[col['NENE NMA']]) == 60.0          # 80 x 0.75
    assert float(bob_02[col['Mineral Interest']]) == 0.375  # 0.5 x 0.75
    assert float(bob_02[col['Total Cost to Extend']]) == 750.0
    assert bob_02[col['Title Landman']] == 'EM'
    assert bob_02[col['Signer 1']] == 'Bob Doe Signer'
    info = bob_02[col['Title Information']]
    assert info.startswith('Heir title note.') and 'heir to Estate of J. Doe' in info and info.endswith('Original title.')


def test_holdings_differing_only_by_type_are_kept(tmp_path):
    """A Mineral and a Royalty holding in the same section both reach every heir, each with its own NMA."""
    rows = _run(tmp_path, [_holding('01-150N-100W', 'Mineral', nma='40'),
                           _holding('01-150N-100W', 'Royalty', nma='80')],
                [_heir('Ann Doe', '0.5'), _heir('Bob Doe', '0.5')])
    header, body = rows[0], rows[1:]
    le, kind, nene = header.index('Legal Entity'), header.index('Land Holding Type'), header.index('NENE NMA')
    got = sorted((r[le], r[kind], float(r[nene])) for r in body)
    assert got == [('Ann Doe', 'Mineral', 20.0), ('Ann Doe', 'Royalty', 40.0),
                   ('Bob Doe', 'Mineral', 20.0), ('Bob Doe', 'Royalty', 40.0)]


def test_identical_section_and_type_holdings_are_kept(tmp_path):
    """Two holdings matching on legal entity, section, type and title source (e.g. separate tracts)
    are still separate rows for the heir."""
    tract_a, tract_b = _holding('01-150N-100W', nma='10'), _holding('01-150N-100W', nma='30')
    tract_a[_TRACT], tract_b[_TRACT] = 'Lot 1', 'Lot 2'
    rows = _run(tmp_path, [tract_a, tract_b], [_heir('Ann Doe', '1')])
    header, body = rows[0], rows[1:]
    tract, nene = header.index('Tract Description'), header.index('NENE NMA')
    assert sorted((r[tract], float(r[nene])) for r in body) == [('Lot 1', 10.0), ('Lot 2', 30.0)]
