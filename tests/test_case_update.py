"""Case Update button (non_hbp_mi.py): stamps today's date on every unit and uploads them.

The Ark Data Loader step (ark_common.upload) is replaced by a recorder, so nothing is uploaded.
"""
from datetime import date

import pytest

import ark_common
import non_hbp_mi
from fakes import Recorder, read_csv


def test_stamps_every_unit_and_uploads(fake_ark, folders, monkeypatch):
    """Column 2 becomes today's date, a Last updated column is added, blank-Id rows are dropped."""
    upload = Recorder()
    monkeypatch.setattr(ark_common, 'upload', upload)
    fake_ark.serve(non_hbp_mi._REPORT_URL, [
        ['Id', 'Case Review Date', 'Unit Name'],
        ['U-1', '01/01/2020', 'Alpha'],
        ['U-2', '', 'Beta'],
        ['', '01/01/2020', 'no id'],
        ['U-3'],                                   # too short -> dropped
    ])

    non_hbp_mi.main()

    today = date.today()
    stamp = f'{today:%m/%d/%Y}'
    out_path = folders['NonHBPMI'] / f'non_hbp_mi.{today:%m.%d.%Y}.csv'
    assert read_csv(out_path) == [
        ['Id', 'Case Review Date', 'Unit Name', 'Last updated'],
        ['U-1', stamp, 'Alpha', stamp],
        ['U-2', stamp, 'Beta', stamp],
    ]
    (_page, csv_path, upload_name), kwargs = upload.calls[0]
    assert (csv_path, upload_name) == (str(out_path), f'case update {today:%m.%d.%Y}')
    assert kwargs == {'dataset': 'Units'}
    assert fake_ark.sessions_saved == 1


_HEADER = ['Id', 'Case Review Date', 'Unit Name']  # start of the Case Update report


def test_no_units_skips_the_upload(fake_ark, folders, monkeypatch):
    """An empty report means no upload (there is nothing to send; an empty upload used to time out)."""
    upload = Recorder()
    monkeypatch.setattr(ark_common, 'upload', upload)
    fake_ark.serve(non_hbp_mi._REPORT_URL, [_HEADER])

    assert non_hbp_mi.main() == 0

    assert upload.calls == []


def test_failure_still_saves_the_session_and_closes_the_browser(fake_ark, folders, monkeypatch):
    """A failed upload keeps the login (session.json) so the next run doesn't redo 2FA."""
    def broken_upload(*args, **kwargs):
        raise RuntimeError('Data Loader timed out')
    monkeypatch.setattr(ark_common, 'upload', broken_upload)
    fake_ark.serve(non_hbp_mi._REPORT_URL, [_HEADER, ['U-1', '', 'Alpha']])

    with pytest.raises(RuntimeError):
        non_hbp_mi.main()

    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed


def test_mirror_step_reports_the_units_updated(fake_ark, folders, monkeypatch):
    """Mirror gets how many units were stamped and uploaded."""
    upload = Recorder()
    monkeypatch.setattr(ark_common, 'upload', upload)
    fake_ark.serve(non_hbp_mi._REPORT_URL, [_HEADER, ['U-1', '', 'Alpha'], ['U-2', '', 'Beta']])

    assert non_hbp_mi.mirror_step() == (ark_common.UPLOADED, "Updated 2 units to today's date")
    assert len(upload.calls) == 1


def test_mirror_step_with_no_units(fake_ark, folders, monkeypatch):
    """No units in the report: Mirror reports no changes."""
    monkeypatch.setattr(ark_common, 'upload', Recorder())
    fake_ark.serve(non_hbp_mi._REPORT_URL, [_HEADER])

    assert non_hbp_mi.mirror_step() == (ark_common.NOTHING, 'No units to update')

