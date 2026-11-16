"""SIB button (section_id_blank.py): fills in landholdings' blank Section Id from the section with
the same Section Name, using Section_ID_Index.csv (every section, kept between runs) that each run's
small Section ID Getting download (sections created in the last week) is merged into.

main() runs for real against a fake Ark that serves both reports; the index, the saved reports, the
output CSV, the upload call and the finish message box are checked. The Ark Data Loader step
(ark_common.upload) is replaced by a recorder, so nothing is uploaded. seed() (--seed) is tested too.
"""
from datetime import date

import pytest

import ark_common
import section_id_blank as sib
from fakes import Recorder, read_csv, write_csv

_BLANK_HEADER = ['Id', 'Section Name', 'Section Id', 'State']  # columns of Landholdings Section Id Blank EM
_SECTIONS_HEADER = ['Section: Id', 'Section Name', 'Section: Section Name', 'Section: Quarter Section',
                    'Section: Quarter Quarter']  # columns of Section ID Getting
_TODAY = f'{date.today():%m/%d/%Y}'  # the index's Updated stamp for a row added or changed by this run
_OLD = '10/01/2026'  # Updated stamp of rows already in a test's index


def landholding(record_id, name, section_id='', state='MT'):
    """One Landholdings Section Id Blank EM row."""
    return [record_id, name, section_id, state]


def section(section_id, name):
    """One Section ID Getting row."""
    return [section_id, name, name, '', '']


def indexed(name, section_id, updated=_OLD):
    """One Section_ID_Index.csv row."""
    return [name, section_id, updated]


@pytest.fixture(autouse=True)
def upload(monkeypatch):
    """Replaces the Data Loader upload with a recorder for every test here."""
    rec = Recorder()
    monkeypatch.setattr(ark_common, 'upload', rec)
    return rec


def write_index(folders, rows):
    """Writes Section_ID_Index.csv with rows to the SIB folder; returns its path."""
    return write_csv(str(folders['SIB'] / sib._INDEX_FILE), [sib._INDEX_HEADER] + rows)


def read_index(folders):
    """Rows of Section_ID_Index.csv, header first."""
    return read_csv(folders['SIB'] / sib._INDEX_FILE)


def serve(fake_ark, landholdings, sections):
    """Serves both reports (header + rows), under names other than the fixed ones."""
    fake_ark.serve(sib._BLANK_URL, [_BLANK_HEADER] + landholdings, filename='3c9e-uuid')
    fake_ark.serve(sib._SECTIONS_URL, [_SECTIONS_HEADER] + sections, filename='b81f-uuid')


def run(fake_ark, folders, landholdings, sections, index=(), quiet=False):
    """Write the index, serve both reports, run main(), and return (main's result, output rows, output folder)."""
    write_index(folders, list(index))
    serve(fake_ark, landholdings, sections)
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
    assert result == (3, ['23-30N-54E', '22-30N-54E', '1-1-UL'], [])
    today = f'{date.today():%m.%d.%Y}'
    assert len(upload.calls) == 1
    (_page, csv_path, upload_name), kwargs = upload.calls[0]
    assert csv_path == str(out / f'Section_Id_Upload.{today}.csv')
    assert upload_name == f'section id {today}'
    assert kwargs == {'dataset': 'Landholdings'}
    assert fake_ark.downloads == [sib._BLANK_URL, sib._SECTIONS_URL]
    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed
    assert 'Found a Section Id for 3 of 3' in _box(msgboxes)


def test_sections_already_in_the_index_still_match(fake_ark, folders, msgboxes, upload):
    """The point of the index: a section created weeks ago is no longer in the daily download, but its
    landholdings still get its Id."""
    _, rows, _ = run(fake_ark, folders, [landholding('LH-1', '5-1N-1E'), landholding('LH-2', '9-2N-2E')],
                     [section('S-9', '9-2N-2E')], index=[indexed('5-1N-1E', 'S-5')])

    assert rows[1:] == [['LH-1', '5-1N-1E', 'S-5'], ['LH-2', '9-2N-2E', 'S-9']]


def test_new_sections_are_appended_to_the_index(fake_ark, folders, msgboxes):
    """A name not in the index is added at the end with today's date; rows already there are kept as
    they were, including a name the download repeats with the same Id."""
    result, _, _ = run(fake_ark, folders, [], [section('S-5', '5-1N-1E'), section('S-9', '9-2N-2E')],
                       index=[indexed('5-1N-1E', 'S-5'), indexed('1-1N-1W', 'S-1')])

    assert read_index(folders) == [sib._INDEX_HEADER, indexed('5-1N-1E', 'S-5'), indexed('1-1N-1W', 'S-1'),
                                   indexed('9-2N-2E', 'S-9', _TODAY)]
    assert result == (0, ['9-2N-2E'], [])
    assert 'Added 1 new section(s) to Section_ID_Index.csv.' in _box(msgboxes)


def test_a_name_that_comes_with_a_new_id_gets_it(fake_ark, folders, msgboxes, upload):
    """An indexed name downloaded with a different Id (the section was re-created) takes the new Id,
    dated today, in its place in the index; landholdings get the new Id and the box names it."""
    result, rows, _ = run(fake_ark, folders, [landholding('LH-1', '5-1N-1E')], [section('S-5-NEW', '5-1n-1e')],
                          index=[indexed('5-1N-1E', 'S-5-OLD'), indexed('1-1N-1W', 'S-1')])

    assert read_index(folders) == [sib._INDEX_HEADER, indexed('5-1N-1E', 'S-5-NEW', _TODAY), indexed('1-1N-1W', 'S-1')]
    assert rows[1:] == [['LH-1', '5-1N-1E', 'S-5-NEW']]
    assert result == (1, [], ['5-1N-1E'])
    assert '1 section name(s) got a new Section Id: 5-1N-1E' in _box(msgboxes)


def test_the_daily_download_is_deleted_once_merged(fake_ark, folders, msgboxes):
    """Section_ID_Getting.csv is gone after the run (its sections are in the index); the landholdings
    report stays under its fixed name, whatever name Ark gave it."""
    _, _, out = run(fake_ark, folders, [landholding('LH-1', '5-1N-1E')], [section('S-5', '5-1N-1E')])

    assert not (out / sib._SECTIONS_FILE).exists()
    assert not (out / (sib._INDEX_FILE + '.tmp')).exists()
    assert read_csv(out / sib._BLANK_FILE)[1] == ['LH-1', '5-1N-1E', '', 'MT']


def test_a_name_with_two_ids_in_the_download_stops_for_a_manual_check(fake_ark, folders, msgboxes, upload):
    """A download listing one Section Name with two different Ids raises naming it and its Ids: nothing is
    added to the index, nothing is uploaded, and the download is kept to look at."""
    write_index(folders, [indexed('1-1N-1W', 'S-1')])
    serve(fake_ark, [landholding('LH-1', '5-1N-1E')],
          [section('S-9a', '9-2N-2E'), section('S-9b', ' 9-2n-2E'), section('S-5', '5-1N-1E')])

    with pytest.raises(RuntimeError, match=r'1 Section Name\(s\) with more than one Section Id: '
                                           r'9-2N-2E \(S-9a, S-9b\)\. Check them in Ark by hand'):
        sib.main()

    assert read_index(folders) == [sib._INDEX_HEADER, indexed('1-1N-1W', 'S-1')]
    assert (folders['SIB'] / sib._SECTIONS_FILE).exists()
    assert upload.calls == []
    assert fake_ark.browser_closed


def test_a_missing_index_stops_before_ark_is_opened(fake_ark, folders, msgboxes, upload):
    """With no Section_ID_Index.csv the run fails at once, saying how to rebuild it with --seed, instead
    of starting a new index from one week of sections."""
    serve(fake_ark, [landholding('LH-1', '5-1N-1E')], [section('S-5', '5-1N-1E')])

    with pytest.raises(RuntimeError, match='Section_ID_Index.csv is missing.*--seed'):
        sib.main()

    assert fake_ark.downloads == [] and upload.calls == []
    assert not (folders['SIB'] / sib._INDEX_FILE).exists()


def test_an_index_listing_a_name_twice_stops(fake_ark, folders, msgboxes, upload):
    """A name in the index twice (e.g. edited by hand) raises naming it rather than picking one Id."""
    write_index(folders, [indexed('5-1N-1E', 'S-5'), indexed('5-1n-1e ', 'S-5b')])
    serve(fake_ark, [landholding('LH-1', '5-1N-1E')], [])

    with pytest.raises(RuntimeError, match=r'more than once: 5-1n-1e'):
        sib.main()
    assert fake_ark.downloads == [] and upload.calls == []


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


def test_skips_rows_with_an_id_already_or_missing_fields(fake_ark, folders, msgboxes):
    """Rows that already have a Section Id, or lack an Id or Section Name, are not touched; sections
    with no Id or no name aren't indexed."""
    _, rows, _ = run(fake_ark, folders,
                     [landholding('LH-1', '5-1N-1E', section_id='S-OLD'),
                      landholding('', '5-1N-1E'),
                      landholding('LH-3', ''),
                      landholding('LH-4', '5-1N-1E')],
                     [section('S-5', '5-1N-1E'), section('', '6-1N-1E'), section('S-7', '')])

    assert rows[1:] == [['LH-4', '5-1N-1E', 'S-5']]
    assert read_index(folders)[1:] == [indexed('5-1N-1E', 'S-5', _TODAY)]
    assert 'Found a Section Id for 1 of 1' in _box(msgboxes)


def test_nothing_matched_writes_an_empty_csv_and_skips_upload(fake_ark, folders, msgboxes, upload):
    """With no matches the CSV has only its header and nothing is uploaded."""
    result, rows, _ = run(fake_ark, folders, [landholding('LH-1', '1-1-UL')], [section('S-5', '5-1N-1E')])

    assert rows == [['Id', 'Section Name', 'Section Id']]
    assert result == (0, ['5-1N-1E'], [])
    assert upload.calls == []
    assert 'Nothing to upload.' in _box(msgboxes)


@pytest.mark.parametrize('url, header, report', [
    (sib._BLANK_URL, ['Record Id', 'STRs', 'Unit Name'], 'Landholdings Section Id Blank EM'),
    (sib._SECTIONS_URL, ['Id', 'Name'], 'Section ID Getting'),
])
def test_a_different_report_from_ark_is_not_uploaded(fake_ark, folders, msgboxes, upload, url, header, report):
    """Ark handing back another report for either URL raises, naming it, instead of uploading; the
    index is left as it was."""
    write_index(folders, [indexed('1-1N-1W', 'S-1')])
    serve(fake_ark, [landholding('LH-1', '5-1N-1E')], [section('S-5', '5-1N-1E')])
    fake_ark.serve(url, [header, ['x', 'y', 'z']])

    with pytest.raises(RuntimeError, match=report):
        sib.main()
    assert upload.calls == []
    assert fake_ark.browser_closed
    assert read_index(folders) == [sib._INDEX_HEADER, indexed('1-1N-1W', 'S-1')]


def test_seed_builds_the_index_from_a_full_download(folders, msgboxes):
    """--seed turns a full Section ID Getting download in the folder into the index (dated today) and
    keeps the download; no Ark involved."""
    write_csv(str(folders['SIB'] / sib._SECTIONS_FILE),
              [_SECTIONS_HEADER, section('S-5', '5-1N-1E'), section('S-9', '9-2N-2E'), section('S-5', '5-1N-1E')])

    assert sib.seed() == 2

    assert read_index(folders) == [sib._INDEX_HEADER, indexed('5-1N-1E', 'S-5', _TODAY), indexed('9-2N-2E', 'S-9', _TODAY)]
    assert (folders['SIB'] / sib._SECTIONS_FILE).exists()
    assert 'with 2 sections' in _box(msgboxes)


def test_seed_refuses_an_existing_index_or_a_missing_download(folders, msgboxes):
    """--seed never overwrites an index, and says to save the full download first when it isn't there."""
    with pytest.raises(RuntimeError, match='Save a full Section ID Getting download'):
        sib.seed()
    write_index(folders, [indexed('1-1N-1W', 'S-1')])
    write_csv(str(folders['SIB'] / sib._SECTIONS_FILE), [_SECTIONS_HEADER, section('S-5', '5-1N-1E')])
    with pytest.raises(RuntimeError, match='already exists'):
        sib.seed()
    assert read_index(folders) == [sib._INDEX_HEADER, indexed('1-1N-1W', 'S-1')]


def test_seed_with_a_name_on_two_ids_builds_nothing(folders, msgboxes):
    """A full download with one name on two Ids is reported for a manual check and no index is written."""
    write_csv(str(folders['SIB'] / sib._SECTIONS_FILE),
              [_SECTIONS_HEADER, section('S-9a', '9-2N-2E'), section('S-9b', '9-2N-2E')])
    with pytest.raises(RuntimeError, match='9-2N-2E'):
        sib.seed()
    assert not (folders['SIB'] / sib._INDEX_FILE).exists()


def test_mirror_step_reports_the_upload_quietly(fake_ark, folders, msgboxes):
    """Mirror gets the number uploaded and no message box appears."""
    write_index(folders, [])
    serve(fake_ark, [landholding('LH-1', '5-1N-1E'), landholding('LH-2', '5-1N-1E')], [section('S-5', '5-1N-1E')])

    assert sib.mirror_step() == (ark_common.UPLOADED, 'Uploaded Section Ids for 2 landholdings')
    assert msgboxes == []


@pytest.mark.parametrize('landholdings, kind, start', [
    ([landholding('LH-1', '5-1N-1E')], ark_common.UPLOADED, 'Uploaded Section Ids for 1 landholding'),
    ([], ark_common.NOTHING, 'No blank Section Ids to fill in'),
])
def test_mirror_step_mentions_names_that_got_a_new_id(fake_ark, folders, msgboxes, landholdings, kind, start):
    """A replaced Id is added to the line, uploaded or not; it doesn't make the step need review."""
    write_index(folders, [indexed('5-1N-1E', 'S-OLD'), indexed('9-2N-2E', 'S-9-OLD')])
    serve(fake_ark, landholdings, [section('S-NEW', '5-1N-1E'), section('S-9-NEW', '9-2N-2E')])

    assert sib.mirror_step() == (kind, f'{start}; 2 section names got a new Section Id')


def test_mirror_step_with_nothing_to_fill_in(fake_ark, folders, msgboxes):
    """No matches: Mirror reports nothing to do."""
    write_index(folders, [])
    serve(fake_ark, [landholding('LH-1', '1-1-UL')], [section('S-5', '5-1N-1E')])

    assert sib.mirror_step() == (ark_common.NOTHING, 'No blank Section Ids to fill in')
