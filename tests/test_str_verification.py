"""STR Verification and AOI buttons (str_verification.py, without / with --aoi), and their
Mirror steps (mirror_step, aoi_mirror_step).

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

_HEADER = ['Id', 'Section', 'Township', 'Range', 'Section Name', 'Township Name', 'Section Id', 'Area of Interest']


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


_TWO_TOWNSHIPS = '2, 11-146N-102W, 26, 35-147N-102W _ Seek And Destroy'  # AOI spanning two townships (real name)


@pytest.mark.parametrize('name, expected', [
    ('13, 24-1S-1E _ Lupine', {(13, (1, 'S'), (1, 'E')), (24, (1, 'S'), (1, 'E'))}),
    ('24, 25, 36-39N-71W', {(24, (39, 'N'), (71, 'W')), (25, (39, 'N'), (71, 'W')),
                            (36, (39, 'N'), (71, 'W'))}),                                   # no "_ Name"
    (_TWO_TOWNSHIPS, {(2, (146, 'N'), (102, 'W')), (11, (146, 'N'), (102, 'W')),
                      (26, (147, 'N'), (102, 'W')), (35, (147, 'N'), (102, 'W'))}),
    ('19-155N-89W, 24-155N-90W _ George', {(19, (155, 'N'), (89, 'W')), (24, (155, 'N'), (90, 'W'))}),
    ('3, 10-28N-56E, 29, 32-29N-56E _ Poseidon (Super Unit)',
     {(3, (28, 'N'), (56, 'E')), (10, (28, 'N'), (56, 'E')), (29, (29, 'N'), (56, 'E')), (32, (29, 'N'), (56, 'E'))}),
    ('04,09 - 153n - 097w _ Spacing', {(4, (153, 'N'), (97, 'W')), (9, (153, 'N'), (97, 'W'))}),  # zeros, case, spaces
    ('Sec 4, 153N-97W', None),          # not the AOI name format
    ('4, 9 _ Missing Township', None),
    ('4, 9-153N _ Missing Range', None),
])
def test_aoi_names_parse_into_the_sections_they_cover(name, expected):
    """Every format seen in the 11/10/2026 report parses section by section, each section tied to
    its own township-range; names that don't follow the format give None."""
    assert sv._aoi_sections(name) == expected


@pytest.mark.parametrize('section_name, section, township, range_, township_name, expected', [
    ('04-153N-97W', '4', '153N', '97W', '153N-97W', (4, (153, 'N'), (97, 'W'))),
    ('25-162N-92W', '25', '162', '92W', '162-92W', (25, (162, 'N'), (92, 'W'))),   # Township lacks N: Section Name wins
    ('', '20', '160N', '97W', '160N-97W', (20, (160, 'N'), (97, 'W'))),            # blank name: S-T-R fields
    ('28-36-3N-TP', '7', '', '', 'T153N-R97W', (7, (153, 'N'), (97, 'W'))),        # bad name, no T/R: Township Name
    ('', '', '', '', '', None),
])
def test_row_section_reads_the_name_then_the_str_fields(section_name, section, township, range_,
                                                        township_name, expected):
    """A row's section comes from its Section Name, else Section/Township/Range, else Township Name."""
    assert sv._row_section(section_name, section, township, range_, township_name) == expected


def test_aoi_check_writes_rows_outside_their_area_only(work):
    """The row's section must be one the AOI name lists; Non-Ops and blank AOIs are skipped."""
    write_csv(work.aoi / _INPUT, [
        _HEADER,
        _row('LH-1', '4', '153N', '97W', '04-153N-97W', aoi='4, 9-153N-97W _ Alpha'),        # first section
        _row('LH-2', '9', '153N', '97W', '09-153N-97W', aoi='4, 9-153N-97W _ Alpha'),        # last section
        _row('LH-3', '6', '153N', '97W', '06-153N-97W', aoi='Non-Ops'),
        _row('LH-4', '7', '153N', '97W', '07-153N-97W', aoi=''),
        _row('LH-5', '8', '153N', '97W', '08-153N-97W', aoi='4, 9-153N-97W _ Alpha'),        # wrong section
        _row('LH-6', '4', '154N', '97W', '04-154N-97W', aoi='4, 9-153N-97W _ Alpha'),        # wrong township
        _row('LH-7', '4', '153N', '97W', '04-153N-97W', aoi='Sec 4, 153N-97W'),              # unreadable AOI
    ])

    assert sv._process(aoi=True) == 3

    rows = read_csv(work.aoi / _AOI_NAME)
    assert rows == [
        ['ID', 'Section Name', 'Combined STR', 'Area of Interest', 'Issue'],
        ['LH-5', '08-153N-97W', '08-153N-97W', '4, 9-153N-97W _ Alpha',
         "Section 8 isn't in this Area of Interest's 153N-97W sections"],
        ['LH-6', '04-154N-97W', '04-154N-97W', '4, 9-153N-97W _ Alpha',
         "Township-range 154N-97W isn't in this Area of Interest"],
        ['LH-7', '04-153N-97W', '04-153N-97W', 'Sec 4, 153N-97W',
         "Area of Interest can't be read (expected like '1, 12, 13-150N-100W _ Name')"],
    ]
    assert list(work.str.iterdir()) == []


def test_aoi_section_is_tied_to_its_own_township(work):
    """In an AOI spanning two townships, a section counts only under the township it's listed
    with: 26-146N-102W isn't covered by "2, 11-146N-102W, 26, 35-147N-102W". The old check
    passed it, because "26," and "146N-102W" each appear somewhere in the name."""
    write_csv(work.aoi / _INPUT, [
        _HEADER,
        _row('LH-1', '26', '146N', '102W', '26-146N-102W', aoi=_TWO_TOWNSHIPS),   # 26 is listed under 147N only
        _row('LH-2', '11', '147N', '102W', '11-147N-102W', aoi=_TWO_TOWNSHIPS),   # 11 is listed under 146N only
        _row('LH-3', '2', '146N', '102W', '02-146N-102W', aoi=_TWO_TOWNSHIPS),
        _row('LH-4', '11', '146N', '102W', '11-146N-102W', aoi=_TWO_TOWNSHIPS),
        _row('LH-5', '26', '147N', '102W', '26-147N-102W', aoi=_TWO_TOWNSHIPS),
        _row('LH-6', '35', '147N', '102W', '35-147N-102W', aoi=_TWO_TOWNSHIPS),
    ])

    sv._process(aoi=True)

    rows = read_csv(work.aoi / _AOI_NAME)
    assert [r[0] for r in rows[1:]] == ['LH-1', 'LH-2']


def test_aoi_section_is_not_matched_inside_a_longer_number(work):
    """Section 4 isn't covered by an AOI that lists section 14, nor township 53N by one listing 153N."""
    write_csv(work.aoi / _INPUT, [
        _HEADER,
        _row('LH-1', '4', '153N', '97W', '04-153N-97W', aoi='14, 23-153N-97W _ Beta'),
        _row('LH-2', '4', '53N', '97W', '04-53N-97W', aoi='4, 9-153N-97W _ Alpha'),
    ])

    sv._process(aoi=True)

    rows = read_csv(work.aoi / _AOI_NAME)
    assert [r[0] for r in rows[1:]] == ['LH-1', 'LH-2']


def test_aoi_reads_rows_with_a_bad_township_or_blank_section_name(work):
    """Rows the old check got wrong or skipped: Township "162" without N (real row, 11/10/2026)
    is read from its Section Name; a blank Section Name is read from Section/Township/Range."""
    write_csv(work.aoi / _INPUT, [
        _HEADER,
        _row('LH-1', '25', '162', '92W', '25-162N-92W', '162-92W', aoi='13, 24, 25, 36-162N-92W _ Sandor'),
        _row('LH-2', '20', '160N', '97W', '', '160N-97W', aoi='17, 20, 29-160N-97W _ Gamma'),
        _row('LH-3', '21', '160N', '97W', '', '160N-97W', aoi='17, 20, 29-160N-97W _ Gamma'),
        _row('LH-4', '', '', '', '', '', aoi='17, 20, 29-160N-97W _ Gamma'),
    ])

    sv._process(aoi=True)

    rows = read_csv(work.aoi / _AOI_NAME)
    assert [(r[0], r[4]) for r in rows[1:]] == [
        ('LH-3', "Section 21 isn't in this Area of Interest's 160N-97W sections"),
        ('LH-4', "Section can't be read from Section Name or Section/Township/Range"),
    ]


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


def test_aoi_mirror_step_reports_the_rows_to_review(fake_ark, work, monkeypatch):
    """Mirror's AOI step runs the AOI check only (whatever the command line), writes the dated
    report in the AOI folder, and says how many rows it has and to review it."""
    fake_ark.serve(sv._REPORT_URL, [
        _HEADER,
        _row('LH-1', '4', '153N', '97W', '04-153N-97W', aoi='4, 9-153N-97W _ Alpha'),
        _row('LH-2', '8', '153N', '97W', '08-153N-97W', aoi='4, 9-153N-97W _ Alpha'),
        _row('LH-3', '9', '154N', '97W', '09-154N-97W', aoi='4, 9-153N-97W _ Alpha'),
    ])
    monkeypatch.setattr(sys, 'argv', ['mirror.py'])

    assert sv.aoi_mirror_step() == (ark_common.REVIEW, f'2 rows in the error report: review {_AOI_NAME}')
    assert [r[0] for r in read_csv(work.aoi / _AOI_NAME)[1:]] == ['LH-2', 'LH-3']
    assert list(work.str.iterdir()) == []


def test_aoi_mirror_step_with_an_empty_report(fake_ark, work):
    """Every row is inside its AOI: the step says the error report has no rows (and still writes it)."""
    fake_ark.serve(sv._REPORT_URL, [
        _HEADER, _row('LH-1', '4', '153N', '97W', '04-153N-97W', aoi='4, 9-153N-97W _ Alpha')])

    assert sv.aoi_mirror_step() == (ark_common.NOTHING, f'No rows in the error report ({_AOI_NAME})')
    assert read_csv(work.aoi / _AOI_NAME) == [['ID', 'Section Name', 'Combined STR', 'Area of Interest', 'Issue']]


def test_aoi_mirror_step_one_row_is_singular(fake_ark, work):
    """One row reads "1 row", not "1 rows"."""
    fake_ark.serve(sv._REPORT_URL, [
        _HEADER, _row('LH-2', '8', '153N', '97W', '08-153N-97W', aoi='4, 9-153N-97W _ Alpha')])

    assert sv.aoi_mirror_step() == (ark_common.REVIEW, f'1 row in the error report: review {_AOI_NAME}')


def test_mirror_step_with_no_mismatches(fake_ark, work):
    """Every Section Name matches: Mirror reports no STR errors."""
    fake_ark.serve(sv._REPORT_URL, _REPORT[:3])

    assert sv.mirror_step() == (ark_common.NOTHING, 'No STR errors found')


@pytest.mark.parametrize('aoi', [False, True])
def test_a_different_report_from_ark_fails_clearly(fake_ark, work, aoi):
    """Ark handing back another report (Mirror's STR step got the 3-column units report on
    10/21/2026 and failed with "IndexError: list index out of range") raises naming the report,
    and writes no error report."""
    fake_ark.serve(sv._REPORT_URL, [['Record Id', 'STRs', 'Unit Name'], ['U-1', '11-3S-2W, 2-3S-2W', 'Velma']])

    with pytest.raises(RuntimeError, match='Check STR.*Record Id, STRs, Unit Name'):
        sv.main(aoi=aoi)
    assert not (work.str / 'Error_Report.csv').exists()
    assert not (work.aoi / _AOI_NAME).exists()
