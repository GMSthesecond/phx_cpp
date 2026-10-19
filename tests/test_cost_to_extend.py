"""Cost to Extend button (cost_to_extend.py): flags rows where NMA x $/acre is off, then uploads.

The Ark Data Loader step (ark_common.upload) is replaced by a recorder, so nothing is uploaded.
"""
from datetime import date

import pytest

import ark_common
import cost_to_extend
from fakes import Recorder, read_csv


def _row(record_id, total, nma, per_acre, notes='old notes'):
    """A 14-column report row: A=Id, C=Total Cost to Extend, D=NMA, E=$/Acre, N=Notes."""
    row = [''] * 14
    row[0], row[2], row[3], row[4], row[13] = record_id, total, nma, per_acre, notes
    return row


@pytest.fixture
def upload(monkeypatch):
    """Replaces the Data Loader upload with a recorder."""
    rec = Recorder()
    monkeypatch.setattr(ark_common, 'upload', rec)
    return rec


def test_writes_corrections_and_uploads_them(fake_ark, folders, upload):
    """Rows off by more than $10 get the calculated cost and a dated note, and are uploaded."""
    fake_ark.serve(cost_to_extend._REPORT_URL, [
        ['Id'] + [''] * 13,
        _row('LH-1', '$1,000.00', '10', '150'),    # calculated 1500 -> off by 500
        _row('LH-2', '1500', '10', '150.5'),       # calculated 1505 -> within $10
        _row('LH-3', 'n/a', '10', '150'),          # unparseable -> skipped
        ['LH-4', 'too', 'short'],                  # fewer than 14 columns -> skipped
        _row('', '1', '1', '1'),                   # no Id -> skipped
    ], filename='c2e_report.csv')

    cost_to_extend.main()

    today = date.today()
    out_path = folders['CostToExtend'] / f'cost_to_extend.{today:%m.%d.%Y}.csv'
    rows = read_csv(out_path)
    assert rows[0] == ['Id', 'Total Cost to Extend', 'Lease Notes & Additional Documentation']
    assert rows[1:] == [['LH-1', '1500.0',
                         f'{today:%m/%d/%Y} EM - Updated to match calculated cost to extend.\n\nold notes']]

    assert len(upload.calls) == 1
    (_page, csv_path, upload_name), kwargs = upload.calls[0]
    assert csv_path == str(out_path)
    assert upload_name == f'cost to extend {today:%m.%d.%Y}'
    assert kwargs == {'dataset': 'Landholdings'}
    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed


def test_nothing_to_fix_skips_export_and_upload(fake_ark, folders, upload):
    """When every row is within $10 there is no CSV and no upload."""
    fake_ark.serve(cost_to_extend._REPORT_URL, [['Id'] + [''] * 13, _row('LH-1', '100', '1', '100')],
                   filename='c2e_report.csv')

    cost_to_extend.main()

    assert upload.calls == []
    assert not list(folders['CostToExtend'].glob('cost_to_extend.*.csv'))


def test_mirror_step_reports_the_fixes_uploaded(fake_ark, folders, upload):
    """Mirror gets how many landholdings were fixed and uploaded."""
    fake_ark.serve(cost_to_extend._REPORT_URL, [
        ['Id'] + [''] * 13, _row('LH-1', '1000', '10', '150'), _row('LH-2', '1', '10', '150'),
        _row('LH-3', '100', '1', '100')], filename='c2e_report.csv')

    assert cost_to_extend.mirror_step() == (ark_common.UPLOADED, 'Uploaded fixes for 2 landholdings')
    assert len(upload.calls) == 1


def test_mirror_step_with_nothing_to_fix(fake_ark, folders, upload):
    """Every row within $10: Mirror reports no errors found."""
    fake_ark.serve(cost_to_extend._REPORT_URL, [['Id'] + [''] * 13, _row('LH-1', '100', '1', '100')],
                   filename='c2e_report.csv')

    assert cost_to_extend.mirror_step() == (ark_common.NOTHING, 'No cost to extend errors found')
    assert upload.calls == []

