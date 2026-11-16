"""PPIQ button (ppiq.py): downloads four Ark reports, then writes Update_Inverted.csv.

Runs against the fake Ark site with the output folder redirected to a temp folder. The report
headers are the real ones (10/26/2026 downloads; the Inverse report as trimmed in Ark on
11/13/2026), since the analysis reads its columns by name.
"""
import pytest

import ppiq
from fakes import locked_like_excel, read_csv, write_csv

# Real headers of the four reports
_PAID_HEADER = ['Area of Interest', 'Id', 'Account Name', 'Land Holding Name', 'Section Name', 'Type', 'NMA',
                'NRA', 'Price Paid', 'State', 'County']
_ALL_HEADER = ['Id', 'Account Name', 'Price Paid', 'Land Holding Name', 'Land Holding Type', 'Deal Number']
_QUEUE_HEADER = ['Offer: Account Name', 'Offer: Offer Name', 'Offer: Status',
                 'LandHoldingTransaction: LandHolding Name', 'LandHoldingTransaction: LandHolding Id',
                 'LandHoldingTransaction: NRA', 'LandHoldingTransaction: Total LandHolding Value']
_INVERSE_HEADER = ['Offer: Offer Name', 'LandHoldingTransaction: LandHolding Id', 'Offer: Status']  # offers not in the queue; trimmed 11/13/2026
_HEADERS = {'paid': _PAID_HEADER, 'all': _ALL_HEADER, 'queue': _QUEUE_HEADER, 'inverse': _INVERSE_HEADER}  # by report key

_OUTPUT_HEADER = ['ID', 'Price Paid', 'LHT Value', 'Type', 'Account Name', 'LH Name', 'Issue', 'Status']  # Update_Inverted.csv


def paid(lh_id, price, account='acct', name='lh name', kind='Mineral Interest'):
    """A Landholdings In Queue (EM) row: a landholding with a price paid, and its details."""
    return ['', lh_id, account, name, '', kind, '', '', price, 'ND', 'Burke']


def holding(lh_id, account, price, name, kind):
    """An EM All Landholdings row."""
    return [lh_id, account, price, name, kind, '']


def lht(lh_id, name, status, value):
    """An All LHs In Queue (EM) row: one landholding transaction of a queued offer."""
    return ['offer acct', 'offer name', status, name, lh_id, '1', value]


def other(lh_id, status):
    """An All LHs In Queue (EM) (Inverse) row: one landholding transaction of an offer outside the queue."""
    return ['offer name', lh_id, status]


@pytest.fixture
def ppiq_folder(tmp_path, monkeypatch):
    """Redirects the PPIQ folder to a temp folder."""
    monkeypatch.setattr(ppiq, '_PPIQ_FOLDER', str(tmp_path))
    return tmp_path


def write_reports(folder, paid=(), holdings=(), queue=(), inverse=()):
    """Writes the four downloaded reports (header plus rows) under the names PPIQ saves them as."""
    for key, rows in (('paid', paid), ('all', holdings), ('queue', queue), ('inverse', inverse)):
        write_csv(folder / ppiq._REPORTS[key].filename, [_HEADERS[key], *rows])


def analysis_rows(folder):
    """Runs the analysis and returns Update_Inverted.csv's rows after the header (checked)."""
    ppiq._run_analysis()
    rows = read_csv(folder / 'Update_Inverted.csv')
    assert rows[0] == _OUTPUT_HEADER
    return rows[1:]


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


def serve_all(fake_ark, rows=()):
    """Serves each report with its real header plus rows, under a name Ark might give it."""
    for key, report in ppiq._REPORTS.items():
        fake_ark.serve(report.url, [_HEADERS[key], *rows], filename=f'Ark name for {key}.csv')


def test_downloads_are_saved_under_fixed_names(fake_ark, ppiq_folder):
    """Every report is downloaded and saved under PPIQ's own name for it, whatever Ark calls it, so
    a report renamed in Ark replaces last week's file instead of leaving it to be read."""
    stale = ppiq_folder / ppiq._REPORTS['all'].filename
    stale.write_text('last week', encoding='utf-8')
    serve_all(fake_ark, [['new']])

    ppiq._download_files()

    assert fake_ark.downloads == [r.url for r in ppiq._REPORTS.values()]
    assert sorted(p.name for p in ppiq_folder.iterdir()) == sorted(r.filename for r in ppiq._REPORTS.values())
    assert read_csv(stale) == [_ALL_HEADER, ['new']]
    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed


def test_downloads_have_no_fixed_waits(fake_ark, ppiq_folder):
    """Only each report's generation wait is spent; trigger_download already waits for Ark to finish
    (the 30 s between downloads and 10 s at the end were dropped 11/02/2026)."""
    serve_all(fake_ark)
    ppiq._download_files()
    assert fake_ark.waited_ms == sum(r.wait_ms for r in ppiq._REPORTS.values())


def test_logs_in_to_both_domains_when_signed_out(fake_ark, ppiq_folder):
    """A signed-out session logs in on phxcapitalgroup.com, then again on phoenixenergy.com."""
    serve_all(fake_ark)
    fake_ark.needs_login = {'ark.phxcapitalgroup.com', 'ark.phoenixenergy.com'}

    ppiq._download_files()

    assert fake_ark.logins == ['https://ark.phxcapitalgroup.com/**', 'https://ark.phoenixenergy.com/**']


def test_a_different_report_stops_the_run(fake_ark, ppiq_folder):
    """A download without the columns PPIQ reads (Ark handed back another report) raises, naming
    the report and what came back, before the next report is downloaded."""
    serve_all(fake_ark)
    first = next(iter(ppiq._REPORTS.values()))
    fake_ark.serve(first.url, [['Record Id', 'STRs']])

    with pytest.raises(RuntimeError, match=r'Landholdings In Queue \(EM\).*Record Id, STRs'):
        ppiq._download_files()
    assert fake_ark.downloads == [first.url]


def test_the_queue_report_is_refused_as_the_inverse_report(fake_ark, ppiq_folder):
    """The Inverse report's columns are a subset of All LHs In Queue (EM)'s, so a queue export handed
    back for it (e.g. an export started by hand in Ark) is told apart by the queue-only LHT value."""
    serve_all(fake_ark)
    fake_ark.serve(ppiq._REPORTS['inverse'].url, [_QUEUE_HEADER])

    with pytest.raises(RuntimeError, match=r'All LHs In Queue \(EM\) \(Inverse\)'):
        ppiq._download_files()


def test_column_names_are_matched_ignoring_capitals(ppiq_folder):
    """A header Ark sends in other capitals ("ID", "OFFER: STATUS") is still read."""
    write_reports(ppiq_folder, paid=[paid('LH-A', '100')], inverse=[other('LH-A', 'Closed')])
    for key in ('all', 'inverse'):
        path = ppiq_folder / ppiq._REPORTS[key].filename
        rows = read_csv(path)
        write_csv(path, [[h.upper() for h in rows[0]], *rows[1:]])

    assert [(r[0], r[6], r[7]) for r in analysis_rows(ppiq_folder)] == [
        ('LH-A', 'Has price paid but not in queue', 'Closed')]


@pytest.mark.parametrize('name', ['Update_Inverted.csv', ppiq._REPORTS['inverse'].filename])
def test_a_file_open_in_excel_stops_before_downloading(fake_ark, ppiq_folder, msgboxes, name):
    """If Excel has the output or a report PPIQ saves over open, PPIQ says to close it before
    downloading anything, instead of failing minutes later."""
    serve_all(fake_ark)
    path = ppiq_folder / name
    path.write_text('last week', encoding='utf-8')

    with locked_like_excel(path):
        ppiq.main()

    assert fake_ark.downloads == []
    assert msgboxes == [('PPIQ', f'{path} is open in another program (probably Excel).\n\n'
                                 'Close it and click PPIQ again.')]


def test_output_opened_during_the_run_says_to_close_it(fake_ark, ppiq_folder, msgboxes, monkeypatch):
    """Update_Inverted.csv opened in Excel while the reports download gets the same "close it" box
    when PPIQ comes to write it, not a failure box."""
    serve_all(fake_ark)
    out = ppiq_folder / 'Update_Inverted.csv'
    out.write_text('last week', encoding='utf-8')
    with locked_like_excel(out):
        monkeypatch.setattr(ppiq, '_locked_files', lambda: [])  # opened after the check at the start
        ppiq.main()

    assert len(fake_ark.downloads) == 4
    assert msgboxes == [('PPIQ', f'{out} is open in another program (probably Excel).\n\n'
                                 'Close it and click PPIQ again.')]


def test_analysis_flags_each_issue(ppiq_folder):
    """Each of the four issue types is written once; matching rows are not flagged."""
    write_reports(
        ppiq_folder,
        paid=[paid('LH-A', '100'), paid('LH-D', '100'), paid('LH-E', '50')],
        holdings=[holding('LH-A', 'Smith', '100', 'Tract A', 'Mineral'),
                  holding('LH-B', 'Phoenix Capital Group Holdings, LLC', '', 'Tract B', 'Mineral'),
                  holding('LH-C', 'Jones', '0', 'Tract C', 'Lease'),
                  holding('LH-D', 'Doe', '100', 'Tract D', 'Mineral'),
                  holding('LH-E', 'Roe', '50', 'Tract E', 'Mineral')],
        queue=[lht('LH-C', 'Tract C', 'Curative', '75'),
               lht('LH-D', 'Tract D', 'Closed', '40'),    # $60 off -> flagged
               lht('LH-E', 'Tract E', 'Closed', '50.5'),  # 50 cents off -> not flagged
               lht('', 'blank id', 'Closed', '1')],       # skipped
        inverse=[other('LH-A', 'Closed')],
    )

    rows = analysis_rows(ppiq_folder)

    assert {r[0]: r[6] for r in rows} == {
        'LH-A': 'Has price paid but not in queue',
        'LH-B': 'Landholdings in PHX account need price paid',
        'LH-C': 'Curative offers should have price paid',
        'LH-D': "LHT Doesn't match LH Price Paid",
    }
    assert {r[0]: r[7] for r in rows}['LH-A'] == 'Closed'


def test_lht_mismatch_row_shows_both_amounts_and_the_holding(ppiq_folder):
    """An LHT mismatch row has the landholding's Price Paid and the LHT value side by side, with its
    type, account and name in their own columns (the LH name used to land in Account Name, and only
    the LHT value was shown)."""
    write_reports(ppiq_folder, paid=[paid('LH-D', '100', 'Doe', 'Tract D', 'Mineral Interest')],
                  holdings=[holding('LH-D', 'Doe', '100', 'Tract D', 'Mineral Interest')],
                  queue=[lht('LH-D', 'Tract D', 'Title Approved', '40')])

    assert analysis_rows(ppiq_folder) == [
        ['LH-D', '100', '40', 'Mineral Interest', 'Doe', 'Tract D', "LHT Doesn't match LH Price Paid", 'Title Approved']]


def test_paid_holdings_are_filled_from_the_paid_report(ppiq_folder):
    """Issues for landholdings Landholdings In Queue (EM) lists take their price paid, type, account
    and name from it, so they stay filled when EM All Landholdings is cut down in Ark to the PHX
    check (here it doesn't list them at all)."""
    write_reports(ppiq_folder,
                  paid=[paid('LH-A', '100', 'Smith', 'Tract A', 'Working Interest (Lease)'),
                        paid('LH-D', '100', 'Doe', 'Tract D', 'NPRI')],
                  queue=[lht('LH-D', 'queue name D', 'Title Approved', '40')],
                  inverse=[other('LH-A', 'Docs Sent')])

    assert analysis_rows(ppiq_folder) == [
        ['LH-A', '100', '', 'Working Interest (Lease)', 'Smith', 'Tract A', 'Has price paid but not in queue', 'Docs Sent'],
        ['LH-D', '100', '40', 'NPRI', 'Doe', 'Tract D', "LHT Doesn't match LH Price Paid", 'Title Approved']]


def test_the_paid_report_wins_over_all_landholdings(ppiq_folder):
    """When both reports list a landholding, the issue row shows Landholdings In Queue (EM)'s details."""
    write_reports(ppiq_folder, paid=[paid('LH-A', '100', 'Paid acct', 'Paid name', 'NPRI')],
                  holdings=[holding('LH-A', 'All acct', '90', 'All name', 'Mineral Interest')])

    assert analysis_rows(ppiq_folder) == [
        ['LH-A', '100', '', 'NPRI', 'Paid acct', 'Paid name', 'Has price paid but not in queue', '']]


def test_queued_holding_with_no_price_is_filled_from_all_landholdings(ppiq_folder):
    """A queued landholding missing from the paid report still takes its price paid, type and account
    from EM All Landholdings (the queue report has no type, and its account is the offer's)."""
    write_reports(ppiq_folder,
                  holdings=[holding('LH-C', 'Jones', '0', 'Tract C', 'Working Interest (Wellbore Only)')],
                  queue=[lht('LH-C', 'queue name C', 'Curative Req. (EM not Paid)', '75')])

    assert analysis_rows(ppiq_folder) == [
        ['LH-C', '0', '75', 'Working Interest (Wellbore Only)', 'Jones', 'Tract C',
         'Curative offers should have price paid', 'Curative Req. (EM not Paid)']]


@pytest.mark.parametrize('dropped', ['Account Name', 'Land Holding Name', 'Type'])
def test_paid_report_without_its_detail_columns_stops_the_run(fake_ark, ppiq_folder, dropped):
    """The paid report's Account Name, Land Holding Name and Type are now read, so a download missing
    one is refused before the other reports are downloaded (rather than writing blank details)."""
    serve_all(fake_ark)
    first = ppiq._REPORTS['paid']
    fake_ark.serve(first.url, [[c for c in _PAID_HEADER if c != dropped]])

    with pytest.raises(RuntimeError, match=r'Landholdings In Queue \(EM\)'):
        ppiq._download_files()
    assert fake_ark.downloads == [first.url]


def test_holding_missing_from_all_landholdings_is_still_reported(ppiq_folder):
    """An issue for a landholding EM All Landholdings doesn't list is written with what the queue
    report knows, instead of being dropped for having no name."""
    write_reports(ppiq_folder, queue=[lht('LH-X', 'Tract X', 'Curative Req. (EM not Paid)', '75')])

    assert analysis_rows(ppiq_folder) == [
        ['LH-X', '', '75', '', '', 'Tract X', 'Curative offers should have price paid', 'Curative Req. (EM not Paid)']]


def test_a_holding_with_two_issues_gets_a_row_for_each(ppiq_folder):
    """A PHX landholding with no price paid that is also in the queue unpaid is listed under both
    issues (only the last one found used to be kept)."""
    write_reports(ppiq_folder,
                  holdings=[holding('LH-P', 'Phoenix Capital Group Holdings, LLC', '0', 'Tract P', 'Mineral')],
                  queue=[lht('LH-P', 'Tract P', 'Curative Req. (EM not Paid)', '500')],
                  inverse=[other('LH-P', 'Docs Sent')])

    assert [(r[0], r[6]) for r in analysis_rows(ppiq_folder)] == [
        ('LH-P', 'Landholdings in PHX account need price paid'),
        ('LH-P', 'Curative offers should have price paid')]


def test_a_blank_lht_value_counts_as_zero(ppiq_folder):
    """A queue row with no LHT value is compared as $0 instead of stopping the run."""
    write_reports(ppiq_folder, paid=[paid('LH-D', '100')],
                  holdings=[holding('LH-D', 'Doe', '100', 'Tract D', 'Mineral')],
                  queue=[lht('LH-D', 'Tract D', 'Closed', '')])

    assert [r[6] for r in analysis_rows(ppiq_folder)] == ["LHT Doesn't match LH Price Paid"]


def test_output_keeps_accented_names_in_excel(ppiq_folder):
    """Update_Inverted.csv starts with a UTF-8 byte order mark, so Excel shows "Peña" instead of "PeÃ±a"."""
    write_reports(ppiq_folder, paid=[paid('LH-A', '100', 'José Peña', 'Tract A', 'Mineral')],
                  holdings=[holding('LH-A', 'José Peña', '100', 'Tract A', 'Mineral')])

    rows = analysis_rows(ppiq_folder)

    assert (ppiq_folder / 'Update_Inverted.csv').read_bytes().startswith(b'\xef\xbb\xbf')
    assert rows[0][4] == 'José Peña'


@pytest.mark.xfail(strict=True, reason='KNOWN_ISSUES: a blank Id becomes an issue row')
def test_rows_with_a_blank_id_are_skipped(ppiq_folder):
    """A Landholdings In Queue (EM) or EM All Landholdings row with no Id is skipped, as the queue
    reports' are, instead of becoming an issue row with a blank ID."""
    write_reports(ppiq_folder, paid=[paid('', '100')],
                  holdings=[holding('', 'Phoenix Capital Group Holdings, LLC', '', 'Tract', 'Mineral')])

    assert analysis_rows(ppiq_folder) == []


@pytest.mark.xfail(strict=True, reason="KNOWN_ISSUES: an amount that isn't a number stops the run without saying where")
def test_an_amount_that_isnt_a_number_names_the_report(ppiq_folder):
    """An amount PPIQ can't read stops the run with an error naming the report and the value, so
    the row can be found (it used to say only "could not convert string to float")."""
    write_reports(ppiq_folder, paid=[paid('LH-A', '(100.00)')], queue=[lht('LH-A', 'Tract A', 'Closed', '100')])

    with pytest.raises(ValueError, match=r'Landholdings In Queue \(EM\).*\(100\.00\)'):
        ppiq._run_analysis()
