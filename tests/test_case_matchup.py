"""Case Matchup button (case_matchup.py): flags unit docket fields that disagree with their cases.

Offline script, so main() runs for real against CSVs in a temp folder.
Hearing dates are far in the past or future so results don't depend on today's date.
"""
import pytest

import case_matchup as cm
from fakes import read_csv, write_csv

_CASES_HEADER = ['Name', 'Case Number', 'Case Type', 'Hearing Date', 'Applicant', 'Continued?', 'STRs',
                 'x', 'x', 'x', 'Order Status', 'Order Number', 'Continued Hearing Date']
_UNITS_HEADER = ['Unit #', 'x', 'STRs', 'Cases', 'Spacing Hearing Date', 'Spacing Status',
                 'Spacing Order Number', 'Pooling Status', 'Pooling Hearing Date', 'Pooling Order Number',
                 'x', 'Record Id', 'Orders', 'Docket Notes']

_STRS = '1-150N-100W, 2-150N-100W'  # the unit used in most tests


def case_row(number, kind='Spacing', strs=_STRS, hearing='01/15/2020', applicant='Other Oil',
             status='', order='', continued='', continued_date=''):
    """One All_Cases.csv row."""
    return ['n', number, kind, hearing, applicant, continued, strs, '', '', '', status, order, continued_date]


def unit_row(record_id='REC-1', strs=_STRS, cases='', spacing_date='', spacing_status='',
             spacing_order='', pooling_status='', pooling_date='', pooling_order='', orders='', notes=''):
    """One units docket row."""
    return ['Unit 1', '', strs, cases, spacing_date, spacing_status, spacing_order,
            pooling_status, pooling_date, pooling_order, '', record_id, orders, notes]


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    """Redirects the CaseMatchup folder; returns a writer for (cases, units) rows."""
    monkeypatch.setattr(cm, '_IN_DIR', str(tmp_path))
    monkeypatch.setattr(cm, '_CASES_PATH', str(tmp_path / 'All_Cases.csv'))
    monkeypatch.setattr(cm, '_UNITS_PATH', str(tmp_path / 'units.csv'))

    def write(cases, units):
        write_csv(tmp_path / 'All_Cases.csv', [_CASES_HEADER] + cases)
        write_csv(tmp_path / 'units.csv', [_UNITS_HEADER] + units)
    return write


def _notes():
    """Notes for each unit after matching (reads the CSVs written by the inputs fixture)."""
    return [u['notes'] for u in cm._process(cm._read_units(), cm._read_cases())]


def test_consistent_unit_has_no_notes(inputs):
    """A unit whose fields all agree with its one granted spacing case is not flagged."""
    inputs([case_row('C-1', status='Granted', order='ORD-1')],
           [unit_row(cases='C-1', spacing_date='01/15/2020', spacing_status='Granted',
                     spacing_order='ORD-1', orders='ORD-1')])
    assert _notes() == ['']


def test_strs_match_in_any_order(inputs):
    """STR sets are compared ignoring order, spacing and case."""
    inputs([case_row('C-1', strs='2-150n-100w,1-150N-100W', status='Granted', order='ORD-1')],
           [unit_row(cases='C-1', spacing_date='01/15/2020', spacing_status='Granted',
                     spacing_order='ORD-1', orders='ORD-1')])
    assert _notes() == ['']


def test_missing_case_and_wrong_fields_are_noted(inputs):
    """A matching case not on the unit produces notes for each field that disagrees."""
    inputs([case_row('C-1', status='Granted', order='ORD-1')], [unit_row()])
    notes = _notes()[0].split('\n')
    assert 'Spacing hearing date should be 01/15/2020 per Case C-1' in notes
    assert 'Spacing order number should be ORD-1 per Case C-1' in notes
    assert 'Spacing status should be Granted per Case C-1' in notes
    assert 'Spacing order ORD-1 (Case C-1) should be listed in Orders' in notes
    assert 'Case C-1 matches this unit but is missing from Cases' in notes


def test_case_no_longer_matching_is_noted(inputs):
    """A case listed on the unit whose STRs no longer match is flagged."""
    inputs([case_row('C-1', strs='9-150N-100W')], [unit_row(cases='C-1')])
    assert "Case C-1 is listed in Cases but no longer matches this unit's STRs" in _notes()[0]


@pytest.mark.parametrize('docket_notes, flagged', [
    ('', True),
    ('Spacing Case C-1 - DENIED', False),
    ('Case C-1 dismissed by NDIC', False),
    ('case c-1, denied.', False),                 # any capitalization, punctuation after the number
    ('Cases C-12 and C-1 denied', False),         # listed after a longer number
    ('Case C-14 DENIED', True),                   # a longer number isn't this case
    ('Case C-10 denied; see C-1 notes', False),   # both words anywhere in the notes, as before
])
def test_denied_case_must_be_noted(inputs, docket_notes, flagged):
    """A denied case must be documented in Docket Notes ("denied" or "dismissed")."""
    inputs([case_row('C-1', status='Denied')],
           [unit_row(cases='C-1', spacing_status='Not Started', notes=docket_notes)])
    assert ('Case C-1 is DENIED but not noted in Docket Notes' in _notes()[0]) == flagged


def test_commingling_matches_on_overlap(inputs):
    """Commingling cases only need one shared STR; other types need the exact set."""
    inputs([case_row('C-COM', kind='Commingling', strs='1-150N-100W'),
            case_row('C-SP', kind='Spacing', strs='1-150N-100W')],
           [unit_row()])
    notes = _notes()[0]
    assert 'Case C-COM matches this unit' in notes
    assert 'C-SP' not in notes


def test_pick_best_prefers_granted_then_phoenix_then_latest():
    """_pick_best: Granted wins, then a Phoenix applicant, then the latest hearing; never Denied."""
    def c(number, status='', applicant='Other', hearing='01/01/2020'):
        return {'case_number': number, 'order_status': status, 'applicant': applicant,
                'effective_hearing_date': hearing}
    assert cm._pick_best([c('old'), c('granted', status='Granted', hearing='01/01/2010')])['case_number'] == 'granted'
    assert cm._pick_best([c('new', hearing='01/01/2025'), c('phx', applicant='Phoenix Operating')])['case_number'] == 'phx'
    assert cm._pick_best([c('a', hearing='01/01/2020'), c('b', hearing='06/01/2021')])['case_number'] == 'b'
    assert cm._pick_best([c('denied', status='Denied')]) is None


def test_continued_hearing_date_supersedes_original(inputs):
    """Once a case is continued, its continued hearing date is the one expected on the unit."""
    inputs([case_row('C-1', hearing='01/15/2020', continued='Yes', continued_date='12/01/2099')],
           [unit_row(cases='C-1', spacing_date='01/15/2020', spacing_status='Docketed')])
    notes = _notes()[0]
    assert 'Spacing hearing date should be 12/01/2099 per Case C-1' in notes
    assert 'Spacing status' not in notes  # future hearing -> Docketed, which matches


def test_main_writes_export_and_summary(inputs, tmp_path, msgboxes):
    """main() writes Case_Matchup_Export.<date>.csv for every unit and shows a summary box."""
    inputs([case_row('C-1', status='Granted', order='ORD-1')],
           [unit_row('REC-1'), unit_row('REC-2', strs='5-150N-100W'), unit_row('')])  # blank Record Id skipped

    cm.main()

    exports = list(tmp_path.glob('Case_Matchup_Export.*.csv'))
    assert len(exports) == 1
    rows = read_csv(exports[0])
    assert rows[0] == cm._OUTPUT_HEADER
    assert [r[0] for r in rows[1:]] == ['REC-1', 'REC-2']
    assert rows[2][-1] == ''  # REC-2 matches nothing and has nothing to flag
    title, text = msgboxes[-1]
    assert title == 'Case Matchup'
    assert 'Processed 2 unit(s) against 1 case(s).' in text and '1 unit(s) have notes to review.' in text


def test_denied_note_for_another_case_does_not_count(inputs):
    """A note about case C-14 being denied should not document case C-1 (it used to: substring match)."""
    inputs([case_row('C-1', status='Denied')],
           [unit_row(cases='C-1', spacing_status='Not Started', notes='Case C-14 DENIED')])
    assert 'Case C-1 is DENIED but not noted in Docket Notes' in _notes()[0]
