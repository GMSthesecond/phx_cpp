"""SIB button (section_id_blank.py): fills in landholdings' blank Section Id from the section with
the same Section Name.

main() runs for real against a fake Ark that serves both reports; the saved reports, the output
CSV, the upload call and the finish message box are checked. The Ark Data Loader step
(ark_common.upload) is replaced by a recorder, so nothing is uploaded.
"""
from datetime import date

import pytest

import ark_common
import section_id_blank as sib
from fakes import Recorder, read_csv

_BLANK_HEADER = ['Id', 'Section Name', 'Section Id', 'State']  # columns of Landholdings Section Id Blank EM
_SECTIONS_HEADER = ['Section: Id', 'Section Name', 'Section: Section Name', 'Section: Quarter Section',
                    'Section: Quarter Quarter']  # columns of Section ID Getting


def landholding(record_id, name, section_id='', state='MT'):
    """One Landholdings Section Id Blank EM row."""
    return [record_id, name, section_id, state]


def section(section_id, name):
    """One Section ID Getting row."""
    return [section_id, name, name, '', '']


@pytest.fixture(autouse=True)
def upload(monkeypatch):
    """Replaces the Data Loader upload with a recorder for every test here."""
    rec = Recorder()
    monkeypatch.setattr(ark_common, 'upload', rec)
    return rec


def run(fake_ark, folders, landholdings, sections, quiet=False):
    """Serve both reports, run main(), and return (main's result, output rows, output folder)."""
    fake_ark.serve(sib._BLANK_URL, [_BLANK_HEADER] + landholdings, filename='3c9e-uuid')
    fake_ark.serve(sib._SECTIONS_URL, [_SECTIONS_HEADER] + sections, filename='b81f-uuid')
    result = sib.main(quiet=quiet)
    out = folders['SIB']
    return result, read_csv(out / f'Section_Id_Upload.{date.today():%m.%d.%Y}.csv'), out


def _box(msgboxes):
    """Text of the single message box the run showed."""
    assert len(msgboxes) == 1, msgboxes
    title, text = msgboxes[0]
    assert title == 'Section Id Blank'
    return text


def test_matches_by_section_name_and_uploads(fake_ark, folders, msgboxes, upload):
    """Each landholding whose Section Name is a section gets that section's Id, every landholding on
    a shared section gets a row, and the CSV is uploaded as a Landholdings Update."""
    result, rows, out = run(fake_ark, folders,
                            [landholding('LH-1', '23-30N-54E'), landholding('LH-2', '22-30N-54E'),
                             landholding('LH-3', '23-30N-54E')],
                            [section('S-23', '23-30N-54E'), section('S-22', '22-30N-54E'),
                             section('S-99', '1-1-UL')])

    assert rows == [['Id', 'Section Name', 'Section Id'],
                    ['LH-1', '23-30N-54E', 'S-23'],
                    ['LH-2', '22-30N-54E', 'S-22'],
                    ['LH-3', '23-30N-54E', 'S-23']]
    assert result == (3, [])
    today = f'{date.today():%m.%d.%Y}'
    assert len(upload.calls) == 1
    (_page, csv_path, upload_name), kwargs = upload.calls[0]
    assert csv_path == str(out / f'Section_Id_Upload.{today}.csv')
    assert upload_name == f'section id {today}'
    assert kwargs == {'dataset': 'Landholdings'}
    assert fake_ark.downloads == [sib._BLANK_URL, sib._SECTIONS_URL]
    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed
    assert 'Found a Section Id for 3 of 3' in _box(msgboxes)


def test_reports_are_saved_under_their_fixed_names(fake_ark, folders, msgboxes):
    """Both downloads land in the SIB folder as Landholdings_Section_Id_Blank_EM.csv and
    Section_ID_Getting.csv, whatever name Ark gave them."""
    _, _, out = run(fake_ark, folders, [landholding('LH-1', '5-1N-1E')], [section('S-5', '5-1N-1E')])

    assert read_csv(out / sib._BLANK_FILE)[1] == ['LH-1', '5-1N-1E', '', 'MT']
    assert read_csv(out / sib._SECTIONS_FILE)[1][:2] == ['S-5', '5-1N-1E']


def test_names_match_ignoring_case_and_spaces(fake_ark, folders, msgboxes):
    """'12-33n-55e ' matches the section '12-33N-55E'; the landholding keeps its own spelling."""
    _, rows, _ = run(fake_ark, folders, [landholding('LH-1', ' 12-33n-55e ')],
                     [section('S-12', '12-33N-55E')])

    assert rows[1:] == [['LH-1', '12-33n-55e', 'S-12']]


def test_unmatched_landholdings_are_left_alone(fake_ark, folders, msgboxes, upload):
    """A Section Name with no section in Ark gets no row (the section isn't created yet), and the box
    counts them."""
    _, rows, _ = run(fake_ark, folders,
                     [landholding('LH-1', '1-1-UL', state='TX'), landholding('LH-2', '5-1N-1E')],
                     [section('S-5', '5-1N-1E')])

    assert rows[1:] == [['LH-2', '5-1N-1E', 'S-5']]
    assert "1 landholding(s) have a Section Name that isn't a section in Ark yet" in _box(msgboxes)


def test_a_name_on_two_sections_is_left_out_and_named(fake_ark, folders, msgboxes):
    """A Section Name shared by two different sections can't be told apart: its landholdings are left
    out and the box names it. The same Id listed twice is not ambiguous."""
    result, rows, _ = run(fake_ark, folders,
                          [landholding('LH-1', '9-2N-2E'), landholding('LH-2', '5-1N-1E')],
                          [section('S-9a', '9-2N-2E'), section('S-9b', '9-2N-2E'),
                           section('S-5', '5-1N-1E'), section('S-5', '5-1N-1E')])

    assert rows[1:] == [['LH-2', '5-1N-1E', 'S-5']]
    assert result == (1, ['9-2N-2E'])
    text = _box(msgboxes)
    assert '1 Section Name(s) match more than one section' in text
    assert '9-2N-2E' in text


def test_skips_rows_with_an_id_already_or_missing_fields(fake_ark, folders, msgboxes):
    """Rows that already have a Section Id, or lack an Id or Section Name, are not touched."""
    _, rows, _ = run(fake_ark, folders,
                     [landholding('LH-1', '5-1N-1E', section_id='S-OLD'),
                      landholding('', '5-1N-1E'),
                      landholding('LH-3', ''),
                      landholding('LH-4', '5-1N-1E')],
                     [section('S-5', '5-1N-1E'), section('', '6-1N-1E'), section('S-7', '')])

    assert rows[1:] == [['LH-4', '5-1N-1E', 'S-5']]
    assert 'Found a Section Id for 1 of 1' in _box(msgboxes)


def test_nothing_matched_writes_an_empty_csv_and_skips_upload(fake_ark, folders, msgboxes, upload):
    """With no matches the CSV has only its header and nothing is uploaded."""
    result, rows, _ = run(fake_ark, folders, [landholding('LH-1', '1-1-UL')], [section('S-5', '5-1N-1E')])

    assert rows == [['Id', 'Section Name', 'Section Id']]
    assert result == (0, [])
    assert upload.calls == []
    assert 'Nothing to upload.' in _box(msgboxes)


@pytest.mark.parametrize('url, header, report', [
    (sib._BLANK_URL, ['Record Id', 'STRs', 'Unit Name'], 'Landholdings Section Id Blank EM'),
    (sib._SECTIONS_URL, ['Id', 'Name'], 'Section ID Getting'),
])
def test_a_different_report_from_ark_is_not_uploaded(fake_ark, folders, msgboxes, upload, url, header, report):
    """Ark handing back another report for either URL raises, naming it, instead of uploading."""
    fake_ark.serve(sib._BLANK_URL, [_BLANK_HEADER, landholding('LH-1', '5-1N-1E')])
    fake_ark.serve(sib._SECTIONS_URL, [_SECTIONS_HEADER, section('S-5', '5-1N-1E')])
    fake_ark.serve(url, [header, ['x', 'y', 'z']])

    with pytest.raises(RuntimeError, match=report):
        sib.main()
    assert upload.calls == []
    assert fake_ark.browser_closed


def test_mirror_step_reports_the_upload_quietly(fake_ark, folders, msgboxes):
    """Mirror gets the number uploaded and no message box appears."""
    fake_ark.serve(sib._BLANK_URL, [_BLANK_HEADER, landholding('LH-1', '5-1N-1E'), landholding('LH-2', '5-1N-1E')])
    fake_ark.serve(sib._SECTIONS_URL, [_SECTIONS_HEADER, section('S-5', '5-1N-1E')])

    assert sib.mirror_step() == (ark_common.UPLOADED, 'Uploaded Section Ids for 2 landholdings')
    assert msgboxes == []


def test_mirror_step_mentions_ambiguous_names_after_an_upload(fake_ark, folders, msgboxes):
    """An upload plus an ambiguous name stays in the Uploaded group and points at the SIB button."""
    fake_ark.serve(sib._BLANK_URL, [_BLANK_HEADER, landholding('LH-1', '5-1N-1E'), landholding('LH-2', '9-2N-2E')])
    fake_ark.serve(sib._SECTIONS_URL, [_SECTIONS_HEADER, section('S-5', '5-1N-1E'),
                                       section('S-9a', '9-2N-2E'), section('S-9b', '9-2N-2E')])

    assert sib.mirror_step() == (ark_common.UPLOADED, 'Uploaded Section Ids for 1 landholding; '
                                 '1 Section Name matched more than one section: run SIB to see them')


def test_mirror_step_with_only_ambiguous_names_needs_review(fake_ark, folders, msgboxes, upload):
    """Nothing uploaded but an ambiguous name: Mirror files it under Needs review."""
    fake_ark.serve(sib._BLANK_URL, [_BLANK_HEADER, landholding('LH-1', '9-2N-2E')])
    fake_ark.serve(sib._SECTIONS_URL, [_SECTIONS_HEADER, section('S-9a', '9-2N-2E'), section('S-9b', '9-2N-2E')])

    assert sib.mirror_step() == (ark_common.REVIEW,
                                 '1 Section Name matched more than one section: run SIB to see them')
    assert upload.calls == []


def test_mirror_step_with_nothing_to_fill_in(fake_ark, folders, msgboxes):
    """No matches: Mirror reports nothing to do."""
    fake_ark.serve(sib._BLANK_URL, [_BLANK_HEADER, landholding('LH-1', '1-1-UL')])
    fake_ark.serve(sib._SECTIONS_URL, [_SECTIONS_HEADER, section('S-5', '5-1N-1E')])

    assert sib.mirror_step() == (ark_common.NOTHING, 'No blank Section Ids to fill in')
