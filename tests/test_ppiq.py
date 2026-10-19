"""PPIQ button (ppiq.py): downloads four Ark reports, then writes Update_Inverted.csv.

Runs against the fake Ark site with the output folder redirected to a temp folder.
"""
import pytest

import ppiq
from fakes import read_csv, write_csv

# Header-only stand-ins for each report; the analysis reads columns by position or name.
_ALL_HEADER = ['Id', 'Account Name', 'Price Paid', 'LH Name', 'LH Type']
_PAID_HEADER = ['x', 'Id', 'x', 'Account Name', 'x', 'x', 'x', 'x', 'Price Paid']
_INVERSE_HEADER = ['x', 'x', 'Status', 'Name', 'Id']
_QUEUE_HEADER = ['LandHoldingTransaction: LandHolding Id', 'LandHoldingTransaction: LandHolding Name',
                 'Offer: Status', 'LandHoldingTransaction: Total LandHolding Value']


@pytest.fixture
def ppiq_folder(tmp_path, monkeypatch):
    """Redirects the hardcoded Desktop\\PPIQ folder to a temp folder."""
    monkeypatch.setattr(ppiq, '_PPIQ_FOLDER', str(tmp_path))
    return tmp_path


def test_folder_comes_from_settings(folders):
    """PPIQ reads its folder from [Folders] PPIQ (Settings), not a hardcoded path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('ppiq_fresh', ppiq.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    assert fresh._PPIQ_FOLDER == str(folders['PPIQ'])


def test_main_shows_the_issue_count(fake_ark, ppiq_folder, monkeypatch, msgboxes):
    """The button's run ends with a box giving the number of issues and the report path."""
    monkeypatch.setattr(ppiq, '_download_files', lambda: None)
    monkeypatch.setattr(ppiq, '_run_analysis', lambda: 3)
    ppiq.main()
    assert msgboxes == [('PPIQ', f'3 issues written to:\n{ppiq_folder / "Update_Inverted.csv"}')]


def test_downloads_all_four_reports(fake_ark, ppiq_folder):
    """Every report URL is downloaded and saved under Ark's suggested file name."""
    for i, (url, _) in enumerate(ppiq._PPIQ_URLS):
        fake_ark.serve(url, [['Id'], [str(i)]], filename=f'report{i}.csv')

    ppiq._download_files()

    assert fake_ark.downloads == [url for url, _ in ppiq._PPIQ_URLS]
    assert sorted(p.name for p in ppiq_folder.iterdir()) == [f'report{i}.csv' for i in range(4)]
    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed


def test_logs_in_to_both_domains_when_signed_out(fake_ark, ppiq_folder):
    """A signed-out session logs in on phxcapitalgroup.com, then again on phoenixenergy.com."""
    for url, _ in ppiq._PPIQ_URLS:
        fake_ark.serve(url, [['Id']])
    fake_ark.needs_login = {'ark.phxcapitalgroup.com', 'ark.phoenixenergy.com'}

    ppiq._download_files()

    assert fake_ark.logins == ['https://ark.phxcapitalgroup.com/**', 'https://ark.phoenixenergy.com/**']


def test_analysis_flags_each_issue(ppiq_folder):
    """Each of the four issue types is written once; matching rows are not flagged."""
    write_csv(ppiq_folder / 'EM_All_Landholdings.csv', [
        _ALL_HEADER,
        ['LH-A', 'Smith', '100', 'Tract A', 'Mineral'],
        ['LH-B', 'Phoenix Capital Group Holdings, LLC', '', 'Tract B', 'Mineral'],
        ['LH-C', 'Jones', '0', 'Tract C', 'Lease'],
        ['LH-D', 'Doe', '100', 'Tract D', 'Mineral'],
        ['LH-E', 'Roe', '50', 'Tract E', 'Mineral'],
    ])
    write_csv(ppiq_folder / 'Landholdings_In_Queue_(EM).csv', [
        _PAID_HEADER,
        ['', 'LH-A', '', 'Smith', '', '', '', '', '100'],
        ['', 'LH-D', '', 'Doe', '', '', '', '', '100'],
        ['', 'LH-E', '', 'Roe', '', '', '', '', '50'],
    ])
    write_csv(ppiq_folder / 'All_LHs_In_Queue_(EM)_(Inverse).csv', [
        _INVERSE_HEADER,
        ['', '', 'Closed', 'Smith', 'LH-A'],
    ])
    write_csv(ppiq_folder / 'All_LHs_In_Queue_(EM).csv', [
        _QUEUE_HEADER,
        ['LH-C', 'Tract C', 'Curative', '75'],
        ['LH-D', 'Tract D', 'Closed', '40'],    # $60 off -> flagged
        ['LH-E', 'Tract E', 'Closed', '50.5'],  # 50 cents off -> not flagged
        ['', 'blank id', 'Closed', '1'],        # skipped
    ])

    ppiq._run_analysis()

    rows = read_csv(ppiq_folder / 'Update_Inverted.csv')
    assert rows[0] == ['ID', 'Price Paid', 'Type', 'Account Name', 'LH Name', 'Issue', 'Status']
    issues = {r[0]: r[5] for r in rows[1:]}
    assert issues == {
        'LH-A': 'Has price paid but not in queue',
        'LH-B': 'Landholdings in PHX account need price paid',
        'LH-C': 'Curative offers should have price paid',
        'LH-D': "LHT Doesn't match LH Price Paid",
    }
    assert {r[0]: r[6] for r in rows[1:]}['LH-A'] == 'Closed'
