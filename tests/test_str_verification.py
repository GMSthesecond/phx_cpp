"""STR Verification and AOI buttons (str_verification.py, without / with --aoi).

The check runs on a hand-built Check STR report; main() is run against the fake Ark site
to confirm each button writes only its own report, in its own folder
([Folders] STRVerification or [Folders] AOI).
"""
import datetime
import importlib.util
import sys

import pytest

import ark_common
import str_verification as sv
from fakes import read_csv, write_csv

_HEADER = ['Id', 'Section', 'Township', 'Range', 'Section Name', 'Township Name', 'x', 'Area of Interest']


def _row(id_, section, township, range_, section_name, township_name='', aoi=''):
    """One Check STR report row in the report's column order."""
    return [id_, section, township, range_, section_name, township_name, '', aoi]


_INPUT = 'Check_STR_(EM)_(Full).csv'  # downloaded report's name in either folder
_AOI_NAME = f'AOI {datetime.date.today():%m.%d.%Y}.csv'  # AOI report's name for today's run


class Work:
    """The two temp folders a test's run of str_verification uses."""

    def __init__(self, root):
        """root is the test's tmp_path; STR and AOI get separate subfolders."""
        self.str = root / 'STR'
        self.aoi = root / 'AOI'
        self.str.mkdir()
        self.aoi.mkdir()


@pytest.fixture
def work(tmp_path, monkeypatch):
    """Redirects the STRVerification and AOI folders (and the paths derived from them) to temp folders."""
    w = Work(tmp_path)
    monkeypatch.setattr(sv, '_OUT_DIR', str(w.str))
    monkeypatch.setattr(sv, '_INPUT_PATH', str(w.str / _INPUT))
    monkeypatch.setattr(sv, '_STR_ERROR_PATH', str(w.str / 'Error_Report.csv'))
    monkeypatch.setattr(sv, '_AOI_DIR', str(w.aoi))
    monkeypatch.setattr(sv, '_AOI_INPUT_PATH', str(w.aoi / _INPUT))
    monkeypatch.setattr(sv, '_AOI_ERROR_PATH', str(w.aoi / _AOI_NAME))
    return w


_REPORT = [
    _HEADER,
    _row('LH-1', '4', '153N', '97W', '04-153N-97W'),                       # match after zero-padding
    _row('LH-2', '4', '153N', '97W', '4-153N-97W'),                        # Section Name padded too -> match
    _row('LH-3', '12', '153N', '97W', '12-153N-98W'),                      # wrong range -> STR error
    _row('LH-4', '7', '', '', '07-T153N-R97W', township_name='T153N-R97W'),  # falls back to Township Name
    _row('LH-5', '9', '153N', '97W', ''),                                  # blank Section Name -> skipped
]


def test_str_check_writes_mismatches_only(work):
    """Section Name must equal the zero-padded section-township-range."""
    write_csv(work.str / _INPUT, _REPORT)

    sv._process(aoi=False)

    rows = read_csv(work.str / 'Error_Report.csv')
    assert rows == [
        ['ID', 'Section Name', 'Combined STR', 'Issue'],
        ['LH-3', '12-153N-98W', '12-153N-97W', "Combined STR doesn't match Section Name"],
    ]
    assert list(work.aoi.iterdir()) == []


def test_aoi_check_writes_unverifiable_areas_only(work):
    """AOI must contain the section and township-range, or the Section Name; Non-Ops and blank pass."""
    write_csv(work.aoi / _INPUT, [
        _HEADER,
        _row('LH-1', '4', '153N', '97W', '04-153N-97W', aoi='Sec 4, 153N-97W'),     # section + T-R
        _row('LH-2', '5', '153N', '97W', '05-153N-97W', aoi='Unit 05-153N-97W'),    # Section Name
        _row('LH-3', '6', '153N', '97W', '06-153N-97W', aoi='Non-Ops'),
        _row('LH-4', '7', '153N', '97W', '07-153N-97W', aoi=''),
        _row('LH-5', '8', '153N', '97W', '08-153N-97W', aoi='Sec 9, 153N-97W'),     # wrong section
    ])

    sv._process(aoi=True)

    rows = read_csv(work.aoi / _AOI_NAME)
    assert rows == [
        ['ID', 'Section Name', 'Combined STR', 'Area of Interest', 'Issue'],
        ['LH-5', '08-153N-97W', '08-153N-97W', 'Sec 9, 153N-97W', 'area of interest cannot be verified automatically'],
    ]
    assert list(work.str.iterdir()) == []


def test_aoi_section_is_not_matched_inside_a_longer_number(work):
    """Section 4 should not be verified by an AOI that only mentions section 14."""
    write_csv(work.aoi / _INPUT, [
        _HEADER, _row('LH-1', '4', '153N', '97W', '04-153N-97W', aoi='Sec 14, 153N-97W')])

    sv._process(aoi=True)

    rows = read_csv(work.aoi / _AOI_NAME)
    assert [r[0] for r in rows[1:]] == ['LH-1']


def test_aoi_numbers_match_only_as_whole_numbers(work):
    """Section, township-range and Section Name count only as whole numbers: "53N-97W" isn't
    found inside "153N-97W", nor "4-153N-97W" inside "14-153N-97W"; leading zeros still match."""
    write_csv(work.aoi / _INPUT, [
        _HEADER,
        _row('LH-1', '4', '53N', '97W', '04-53N-97W', aoi='Sec 4, 153N-97W'),       # township inside a longer one
        _row('LH-2', '4', '153N', '97W', '4-153N-97W', aoi='Unit 14-153N-97W'),     # Section Name inside a longer one
        _row('LH-3', '4', '153N', '97W', '04-153N-97W', aoi='Sec 04, 153N-97W'),    # zero-padded section matches
        _row('LH-4', '4', '153N', '97W', '4-153N-97W', aoi='Unit 04-153N-97W'),     # zero-padded Section Name matches
        _row('LH-5', '14', '153N', '97W', '14-153N-97W', aoi='Secs 2, 14, 153N-97W'),  # one of several sections
    ])

    sv._process(aoi=True)

    rows = read_csv(work.aoi / _AOI_NAME)
    assert [r[0] for r in rows[1:]] == ['LH-1', 'LH-2']


@pytest.mark.parametrize('argv, own_folder, other_folder, expected_report', [
    ([], 'str', 'aoi', 'Error_Report.csv'),
    (['--aoi'], 'aoi', 'str', _AOI_NAME),
])
def test_button_arguments_pick_the_report_and_folder(fake_ark, work, monkeypatch,
                                                      argv, own_folder, other_folder, expected_report):
    """STR Verification (no args) downloads and writes Error_Report.csv in the STRVerification folder;
    AOI (--aoi) downloads and writes only the AOI file in the AOI folder. Neither touches the other's folder."""
    fake_ark.serve(sv._REPORT_URL, _REPORT)
    monkeypatch.setattr(sys, 'argv', ['str_verification.py'] + argv)

    sv.main()

    assert sorted(p.name for p in getattr(work, own_folder).iterdir()) == sorted([_INPUT, expected_report])
    assert list(getattr(work, other_folder).iterdir()) == []
    assert fake_ark.sessions_saved == 1


def test_folders_come_from_their_own_settings_keys(folders):
    """STR Verification reads [Folders] STRVerification and AOI reads [Folders] AOI."""
    spec = importlib.util.spec_from_file_location('str_verification_fresh', sv.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)  # module-level paths are read now, through the folders fixture

    assert fresh._INPUT_PATH == str(folders['STRVerification'] / _INPUT)
    assert fresh._STR_ERROR_PATH == str(folders['STRVerification'] / 'Error_Report.csv')
    assert fresh._AOI_INPUT_PATH == str(folders['AOI'] / _INPUT)
    assert fresh._AOI_ERROR_PATH == str(folders['AOI'] / _AOI_NAME)


def test_mirror_step_reports_the_mismatch_count(fake_ark, work, monkeypatch):
    """Mirror runs the STR check (never AOI, whatever the command line) and reports the mismatches."""
    fake_ark.serve(sv._REPORT_URL, _REPORT)
    monkeypatch.setattr(sys, 'argv', ['mirror.py', '--aoi'])

    assert sv.mirror_step() == (ark_common.REVIEW, '1 Section Name mismatch: review Error_Report.csv')
    assert (work.str / 'Error_Report.csv').exists()
    assert list(work.aoi.iterdir()) == []


def test_mirror_step_with_no_mismatches(fake_ark, work):
    """Every Section Name matches: Mirror reports no STR errors."""
    fake_ark.serve(sv._REPORT_URL, _REPORT[:3])

    assert sv.mirror_step() == (ark_common.NOTHING, 'No STR errors found')
