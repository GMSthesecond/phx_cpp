"""Case Unit Names button (case_unit_names.py): names each case after the unit with the same STRs.

main() runs for real against a fake Ark that serves the units and cases reports; the
output CSV, the upload call and the finish message box are checked. The Ark Data Loader step
(ark_common.upload) is replaced by a recorder, so nothing is uploaded.
"""
from datetime import date

import pytest

import ark_common
import case_unit_names as cun
from fakes import Recorder, read_csv

_UNITS_HEADER = ['Record Id', 'STRs', 'Unit Name']  # columns of the units report
_CASES_HEADER = ['Record Id', 'Applicant', 'PHX Unit Name', 'Sections']  # columns of the cases report
_STRS = '1-150N-100W, 2-150N-100W'  # the STR set used in most tests


def unit(record_id, name, strs=_STRS):
    """One units-report row."""
    return [record_id, strs, name]


def case(record_id, strs=_STRS, name=''):
    """One cases-report row (a blank record_id makes it a continuation row)."""
    return [record_id, 'Phoenix Operating LLC' if record_id else '', name, strs]


@pytest.fixture(autouse=True)
def upload(monkeypatch):
    """Replaces the Data Loader upload with a recorder for every test here."""
    rec = Recorder()
    monkeypatch.setattr(ark_common, 'upload', rec)
    return rec


def run(fake_ark, folders, units, cases):
    """Serve both reports, run main(), and return (output rows, output folder)."""
    fake_ark.serve(cun._UNITS_URL, [_UNITS_HEADER] + units, filename='9f1c-uuid')
    fake_ark.serve(cun._CASES_URL, [_CASES_HEADER] + cases, filename='a7d2-uuid')
    cun.main()
    out = folders['CaseUnitNames']
    today = date.today().strftime('%m.%d.%Y')
    return read_csv(out / f'Case_Unit_Names.{today}.csv'), out


def _box(msgboxes):
    """Text of the single message box the run showed."""
    assert len(msgboxes) == 1, msgboxes
    title, text = msgboxes[0]
    assert title == 'Case Unit Names'
    return text


def test_downloads_both_reports_and_writes_one_row_per_case(fake_ark, folders, msgboxes):
    """Both reports are saved under their fixed names and each matched case gets its unit's name."""
    rows, out = run(fake_ark, folders,
                    [unit('U-1', 'ARCHES'), unit('U-2', 'BISON', '5-150N-100W')],
                    [case('C-1'), case('C-2', '5-150N-100W')])
    assert rows == [['Record Id', 'PHX Unit Name'], ['C-1', 'ARCHES'], ['C-2', 'BISON']]
    assert fake_ark.downloads == [cun._UNITS_URL, cun._CASES_URL]
    assert (out / 'Units_For_Case_Names.csv').is_file() and (out / 'Phoenix_Cases_Fixes.csv').is_file()
    assert fake_ark.sessions_saved == 1
    text = _box(msgboxes)
    assert 'Matched 2 of 2 case(s)' in text
    assert 'replaced' not in text and 'left out' not in text


def test_logs_in_when_signed_out(fake_ark, folders, msgboxes):
    """A signed-out session goes through ark_common.login before downloading."""
    fake_ark.needs_login = {'ark.phoenixenergy.com'}
    run(fake_ark, folders, [unit('U-1', 'ARCHES')], [case('C-1')])
    assert fake_ark.logins == ['https://ark.phoenixenergy.com/**']
    assert len(fake_ark.downloads) == 2


def test_strs_match_in_any_order_case_and_spacing(fake_ark, folders, msgboxes):
    """STR sets are compared ignoring order, letter case and extra spaces."""
    rows, _ = run(fake_ark, folders, [unit('U-1', 'ARCHES')], [case('C-1', '2-150n-100w ,  1-150N-100W')])
    assert rows[1:] == [['C-1', 'ARCHES']]


def test_only_the_exact_same_strs_match(fake_ark, folders, msgboxes):
    """A case whose STRs are a subset, superset or overlap of a unit's is left out and counted."""
    rows, _ = run(fake_ark, folders, [unit('U-1', 'ARCHES')],
                  [case('C-sub', '1-150N-100W'),
                   case('C-super', _STRS + ', 3-150N-100W'),
                   case('C-overlap', '1-150N-100W, 3-150N-100W'),
                   case('C-blank', '')])
    assert rows == [['Record Id', 'PHX Unit Name']]
    assert '4 case(s) had no unit with the same STRs and were left out' in _box(msgboxes)


def test_units_without_a_name_are_ignored(fake_ark, folders, msgboxes):
    """A unit with a blank Unit Name never names a case, even when another unit has the same STRs."""
    rows, _ = run(fake_ark, folders, [unit('U-1', ''), unit('U-2', 'ARCHES')], [case('C-1')])
    assert rows[1:] == [['C-1', 'ARCHES']]
    rows, _ = run(fake_ark, folders, [unit('U-1', '  ')], [case('C-1')])
    assert rows[1:] == []


def test_several_units_with_the_same_strs_are_comma_joined(fake_ark, folders, msgboxes):
    """Differently named units on one STR set are joined, sorted; repeated names appear once."""
    rows, _ = run(fake_ark, folders,
                  [unit('U-1', 'Klondike E'), unit('U-2', 'Klondike'),
                   unit('U-3', 'GOTHAM', '5-150N-100W'), unit('U-4', 'GOTHAM', '5-150N-100W')],
                  [case('C-1'), case('C-2', '5-150N-100W')])
    assert rows[1:] == [['C-1', 'Klondike, Klondike E'], ['C-2', 'GOTHAM']]


def test_replaced_names_are_listed_in_the_message_box(fake_ark, folders, msgboxes):
    """A case with a different existing PHX Unit Name gets the matched name and is listed; one
    that already has the matched name, or none, is not listed."""
    rows, _ = run(fake_ark, folders, [unit('U-1', 'RED BULL')],
                  [case('C-wrong', name='ARCHES'), case('C-right', name='RED BULL'), case('C-blank')])
    assert rows[1:] == [['C-wrong', 'RED BULL'], ['C-blank', 'RED BULL']]
    text = _box(msgboxes)
    assert '1 case(s) already had a different PHX Unit Name' in text
    assert 'C-wrong: ARCHES -> RED BULL' in text
    assert 'C-right' not in text and 'C-blank' not in text


def test_continuation_rows_add_existing_names_but_not_sections(fake_ark, folders, msgboxes):
    """Ark's blank-Record-Id rows belong to the case above: their PHX Unit Name counts as an
    existing name, and their Sections don't change what the case matches."""
    rows, _ = run(fake_ark, folders,
                  [unit('U-1', 'SUGAR RAY'), unit('U-2', 'OTHER', '9-150N-100W')],
                  [case('', '9-150N-100W', name='STRAY'),  # continuation row before any case: ignored
                   case('C-1', name='SUGAR RAY'), case('', name='BENJAMIN FRANKLIN'),
                   case('', '9-150N-100W'),
                   case('C-2'), case('', name='SUGAR RAY')])
    assert rows[1:] == [['C-1', 'SUGAR RAY']]  # C-2 already has SUGAR RAY (from its continuation row)
    text = _box(msgboxes)
    assert 'C-1: SUGAR RAY, BENJAMIN FRANKLIN -> SUGAR RAY' in text
    assert 'C-2' not in text and 'STRAY' not in text


def test_cases_that_already_have_the_right_name_are_left_out(fake_ark, folders, msgboxes):
    """Only cases whose PHX Unit Name needs fixing go in the CSV: a case already holding the
    matched name(s), in any order, is left out and counted in the message box."""
    rows, out = run(fake_ark, folders,
                    [unit('U-1', 'ARCHES'), unit('U-2', 'Klondike', '5-150N-100W'),
                     unit('U-3', 'Klondike E', '5-150N-100W')],
                    [case('C-right', name='ARCHES'),
                     case('C-both', '5-150N-100W', name='Klondike E'), case('', name='Klondike'),
                     case('C-half', '5-150N-100W', name='Klondike'),
                     case('C-blank')])
    assert rows[1:] == [['C-half', 'Klondike, Klondike E'], ['C-blank', 'ARCHES']]
    text = _box(msgboxes)
    assert 'Matched 4 of 4 case(s)' in text
    assert '2 case(s) already had the right PHX Unit Name and were left out of the CSV.' in text
    assert f'Saved 2 case(s) to fix: {out}' in text
    assert 'C-half: Klondike -> Klondike, Klondike E' in text


def test_csv_is_header_only_when_every_case_is_already_right(fake_ark, folders, msgboxes):
    """When nothing needs fixing the CSV is still written, with just the header."""
    rows, _ = run(fake_ark, folders, [unit('U-1', 'ARCHES')], [case('C-1', name='ARCHES')])
    assert rows == [['Record Id', 'PHX Unit Name']]
    assert 'Saved 0 case(s) to fix' in _box(msgboxes)


def test_long_replaced_list_is_cut_short_and_saved_in_full(fake_ark, folders, msgboxes):
    """Past _MAX_LISTED replacements the box says how many more, and Replaced_Names lists them all."""
    count = cun._MAX_LISTED + 5
    _, out = run(fake_ark, folders, [unit('U-1', 'NEW')], [case(f'C-{i}', name='OLD') for i in range(count)])
    text = _box(msgboxes)
    assert f'C-{cun._MAX_LISTED - 1}: OLD -> NEW' in text
    assert f'C-{cun._MAX_LISTED}:' not in text
    assert '...and 5 more' in text
    today = date.today().strftime('%m.%d.%Y')
    full = read_csv(out / f'Replaced_Names.{today}.csv')
    assert full[0] == ['Record Id', 'Old PHX Unit Name', 'New PHX Unit Name']
    assert len(full) == count + 1


def test_short_replaced_list_writes_no_extra_file(fake_ark, folders, msgboxes):
    """When every replacement fits in the box, no Replaced_Names CSV is written."""
    _, out = run(fake_ark, folders, [unit('U-1', 'NEW')], [case('C-1', name='OLD')])
    assert not list(out.glob('Replaced_Names*'))


def test_rerun_overwrites_the_downloaded_reports(fake_ark, folders, msgboxes):
    """A second run replaces the saved reports instead of failing or keeping the old data."""
    run(fake_ark, folders, [unit('U-1', 'OLD NAME')], [case('C-1')])
    rows, _ = run(fake_ark, folders, [unit('U-1', 'NEW NAME')], [case('C-1')])
    assert rows[1:] == [['C-1', 'NEW NAME']]


# ---- Upload ----

def test_cases_to_fix_are_uploaded_as_a_case_update(fake_ark, folders, msgboxes, upload):
    """The dated CSV is uploaded once through the Data Loader with the "Cases" dataset, and the box says so."""
    run(fake_ark, folders, [unit('U-1', 'ARCHES')], [case('C-1'), case('C-2', name='OLD')])

    today = date.today().strftime('%m.%d.%Y')
    [((_page, csv_path, upload_name), kwargs)] = upload.calls
    assert csv_path == str(folders['CaseUnitNames'] / f'Case_Unit_Names.{today}.csv')
    assert upload_name == f'case unit names {today}'
    assert kwargs == {'dataset': 'Cases'}
    text = _box(msgboxes)
    assert 'Uploaded them to Ark as a Case Update.' in text
    assert 'The upload replaced it' in text and 'C-2: OLD -> ARCHES' in text


def test_nothing_to_fix_skips_the_upload(fake_ark, folders, msgboxes, upload):
    """When no case needs a new name there is no upload (an empty upload times out), and the box says so."""
    run(fake_ark, folders, [unit('U-1', 'ARCHES')], [case('C-1', name='ARCHES'), case('C-2', '9-150N-100W')])

    assert upload.calls == []
    text = _box(msgboxes)
    assert 'Nothing to upload.' in text and 'Uploaded' not in text


def test_failed_upload_still_saves_the_session_and_closes_the_browser(fake_ark, folders, monkeypatch, msgboxes):
    """A failed upload keeps the login (session.json) so the next run doesn't redo 2FA, and the
    error reaches the caller (the __main__ handler shows it) instead of a success box."""
    def broken_upload(*args, **kwargs):
        raise RuntimeError('Data Loader timed out')
    monkeypatch.setattr(ark_common, 'upload', broken_upload)

    with pytest.raises(RuntimeError):
        run(fake_ark, folders, [unit('U-1', 'ARCHES')], [case('C-1')])

    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed
    assert msgboxes == []


# ---- Mirror step ----

def test_mirror_step_reports_only_the_upload(fake_ark, folders, msgboxes, upload):
    """Mirror gets one line with how many cases were uploaded (not the matched/replaced/unmatched
    totals the button's box shows), and no message box appears."""
    fake_ark.serve(cun._UNITS_URL, [_UNITS_HEADER, unit('U-1', 'ARCHES')], filename='u.csv')
    fake_ark.serve(cun._CASES_URL, [_CASES_HEADER, case('C-1'), case('C-2', name='OLD'),
                                    case('C-3', name='ARCHES'), case('C-4', '9-150N-100W')], filename='c.csv')

    assert cun.mirror_step() == (ark_common.UPLOADED, 'Uploaded PHX Unit Names for 2 cases')
    assert len(upload.calls) == 1
    assert msgboxes == []


def test_mirror_step_with_nothing_to_upload(fake_ark, folders, msgboxes, upload):
    """Every case already right: Mirror reports no changes, nothing is uploaded and no box appears."""
    fake_ark.serve(cun._UNITS_URL, [_UNITS_HEADER, unit('U-1', 'ARCHES')], filename='u.csv')
    fake_ark.serve(cun._CASES_URL, [_CASES_HEADER, case('C-1', name='ARCHES')], filename='c.csv')

    assert cun.mirror_step() == (ark_common.NOTHING, 'No case unit names to upload')
    assert upload.calls == []
    assert msgboxes == []
