"""PPIQ (price paid / in queue) check, launched by the "PPIQ" button.

Downloads four Ark landholding reports (_REPORTS, on ark.phxcapitalgroup.com and ark.phoenixenergy.com)
into the PPIQ folder ([Folders] PPIQ) with Playwright, each under a fixed file name and checked for
the columns it's read by, then cross-checks price paid against the curative queue and writes one row
per issue found to Update_Inverted.csv in the same folder (UTF-8 with BOM, for Excel).
Shows a summary box when done, a "close it" box if one of those files is open in Excel (checked
before downloading), or an error box (log: ppiq_error.log in the folder).
Uses ark_common for credentials ([Credentials]), login, session.json and report downloads.
"""
import csv
import os
from typing import NamedTuple
from urllib.parse import urlparse

import ark_common

# Download/output folder ([Folders] PPIQ, set in Settings)
_PPIQ_FOLDER = ark_common.read_folder('PPIQ', r"C:\Users\Ethan Mesecher\Desktop\PPIQ")


class _Report(NamedTuple):
    """One Ark report PPIQ downloads."""
    name: str      # the report's name in Ark, for error messages
    url: str
    wait_ms: int   # time between triggering generation and checking the notifications panel
    filename: str  # saved under this name whatever Ark calls it, so a renamed report can't leave last week's file to be read
    columns: tuple  # the columns read from it, by header name (any capitals); a download without them is another report
    excludes: tuple = ()  # columns it never has; a download with one is another report (one whose columns include all of these)


_LH_ID = 'LandHoldingTransaction: LandHolding Id'  # queue reports: the transaction's landholding
_LH_NAME = 'LandHoldingTransaction: LandHolding Name'
_STATUS = 'Offer: Status'
_LHT_VALUE = 'LandHoldingTransaction: Total LandHolding Value'

# The four reports by key, in download order; a report on another domain than the one before it gets its own login check
_REPORTS = {
    'paid': _Report('Landholdings In Queue (EM)', 'https://ark.phxcapitalgroup.com/report?recordId=679290fbcd9e6c677fc1cb5d',
                    30_000, 'Landholdings_In_Queue_(EM).csv',
                    ('Id', 'Price Paid', 'Account Name', 'Land Holding Name', 'Type')),  # landholdings with a price paid, and their details for the issue rows; slow to prepare
    'all': _Report('EM All Landholdings', 'https://ark.phxcapitalgroup.com/report?recordId=6734f573e60ff45d13cc57a0',
                   60_000, 'EM_All_Landholdings.csv',
                   ('Id', 'Account Name', 'Price Paid', 'Land Holding Name', 'Land Holding Type')),  # every landholding: the PHX check, and details of issues the paid report doesn't list
    'queue': _Report('All LHs In Queue (EM)', 'https://ark.phxcapitalgroup.com/report?recordId=6792a720ccb927b757c7a6be',
                     10_000, 'All_LHs_In_Queue_(EM).csv', (_LH_ID, _LH_NAME, _STATUS, _LHT_VALUE)),  # transactions of offers in the queue
    'inverse': _Report('All LHs In Queue (EM) (Inverse)', 'https://ark.phoenixenergy.com/report?recordId=67f99dc7ca970119b2f06532',
                       80_000, 'All_LHs_In_Queue_(EM)_(Inverse).csv', (_LH_ID, _STATUS),
                       (_LHT_VALUE,)),  # transactions of every other offer; read for statuses. Trimmed in Ark 11/13/2026 to Offer Name, LandHolding Id, Status, so an LHT value means the queue report came instead
}

_OUTPUT_FILE = 'Update_Inverted.csv'  # the issues, written to _PPIQ_FOLDER (overwritten each run)
_OUTPUT_HEADER = ['ID', 'Price Paid', 'LHT Value', 'Type', 'Account Name', 'LH Name', 'Issue', 'Status']  # one row per issue
_PHX_ACCOUNT = 'Phoenix Capital Group Holdings, LLC'  # every landholding in this account should have a price paid
_MAX_DIFF = 1  # an LHT value more than this many dollars from the price paid is a mismatch

# Issue column values, in the order the checks run
_NOT_IN_QUEUE = 'Has price paid but not in queue'
_PHX_NO_PRICE = 'Landholdings in PHX account need price paid'
_QUEUE_NO_PRICE = 'Curative offers should have price paid'
_LHT_MISMATCH = "LHT Doesn't match LH Price Paid"


def _download_files():
    """Log in to Ark and download every report in _REPORTS into _PPIQ_FOLDER under its filename,
    stopping at one without its columns (_check_columns). Checks the login again when a report is on
    another domain (phoenixenergy.com for the last); saves the session to session.json
    (ark_common.ark_page, also after an error)."""
    os.makedirs(_PPIQ_FOLDER, exist_ok=True)
    reports = list(_REPORTS.values())
    domain = urlparse(reports[0].url).netloc

    # Opening the first report primes the session / login for its domain
    with ark_common.ark_page(reports[0].url, success_url=f'https://{domain}/**') as page:
        for report in reports:
            if urlparse(report.url).netloc != domain:
                domain = urlparse(report.url).netloc
                page.goto(report.url)
                ark_common.ensure_login(page, success_url=f'https://{domain}/**')

            dl = ark_common.trigger_download(page, report.url, generation_wait_ms=report.wait_ms)
            dest = os.path.join(_PPIQ_FOLDER, report.filename)
            dl.save_as(dest)
            print(f'Saved: {dest}', flush=True)
            _check_columns(report)


def _column_indexes(report, header):
    """Position of each of report.columns in header, ignoring capitals; RuntimeError naming the
    report and the columns it has if one is missing or one of report.excludes is there (Ark sent
    another report)."""
    header = [h.strip() for h in header]
    names = [h.casefold() for h in header]
    if any(c.casefold() not in names for c in report.columns) or any(c.casefold() in names for c in report.excludes):
        raise RuntimeError(f'Ark sent a different report than {report.name} '
                           f'(columns: {", ".join(header) or "none"}); run PPIQ again')
    return [names.index(c.casefold()) for c in report.columns]


def _check_columns(report):
    """Raise unless report's saved CSV has every column PPIQ reads from it (_column_indexes)."""
    with open(os.path.join(_PPIQ_FOLDER, report.filename), newline='', encoding='utf-8-sig') as f:
        _column_indexes(report, next(csv.reader(f), []))


def _read(report):
    """Yield each row of report's saved CSV as {column: stripped value} for its columns only
    (blank lines skipped). RuntimeError if a column is missing."""
    with open(os.path.join(_PPIQ_FOLDER, report.filename), newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        at = list(zip(report.columns, _column_indexes(report, next(reader, []))))
        for row in reader:
            if row:
                yield {c: row[i].strip() if i < len(row) else '' for c, i in at}


def _money(text):
    """A report amount as a float; blank counts as 0."""
    return float(text.replace('$', '').replace(',', '') or 0)


def _run_analysis():
    """Compare the four downloaded CSVs and write one row per issue to Update_Inverted.csv.

    Flags landholdings with price paid but not in queue, PHX-owned landholdings (_PHX_ACCOUNT) with no
    price paid, queued offers' landholdings with no price paid, and LHT values more than _MAX_DIFF
    from the price paid. A landholding with two issues gets two rows. Price paid, type, account and
    name come from Landholdings In Queue (EM) when it lists the landholding, else from EM All
    Landholdings (the LH name from the queue report if neither has it), so EM All Landholdings is
    needed only for the PHX check and the queued landholdings with no price paid.
    Returns the number of issues written.
    """
    holdings = {r['Id']: r for r in _read(_REPORTS['all'])}
    paid = {r['Id']: r for r in _read(_REPORTS['paid'])}
    details = dict(holdings)  # landholding id -> its Price Paid / Account Name / Land Holding Name / Land Holding Type
    details.update({lh_id: {**r, 'Land Holding Type': r['Type']} for lh_id, r in paid.items()})
    queue = {r[_LH_ID]: r for r in _read(_REPORTS['queue']) if r[_LH_ID]}
    other_statuses = {}  # landholding id -> statuses of its offers outside the queue, first seen first
    for r in _read(_REPORTS['inverse']):
        if r[_LH_ID]:
            seen = other_statuses.setdefault(r[_LH_ID], [])
            if r[_STATUS] not in seen:
                seen.append(r[_STATUS])

    def statuses(lh_id):
        """The landholding's offer statuses outside the queue, comma-joined."""
        return ', '.join(other_statuses.get(lh_id, []))

    issues = [(lh_id, _NOT_IN_QUEUE, statuses(lh_id)) for lh_id in paid if lh_id not in queue]
    issues += [(lh_id, _PHX_NO_PRICE, statuses(lh_id)) for lh_id, h in holdings.items()
               if h['Account Name'] == _PHX_ACCOUNT and _money(h['Price Paid']) == 0]
    issues += [(lh_id, _QUEUE_NO_PRICE, q[_STATUS]) for lh_id, q in queue.items() if lh_id not in paid]
    issues += [(lh_id, _LHT_MISMATCH, queue[lh_id][_STATUS]) for lh_id, p in paid.items()
               if lh_id in queue and abs(_money(p['Price Paid']) - _money(queue[lh_id][_LHT_VALUE])) > _MAX_DIFF]

    with open(os.path.join(_PPIQ_FOLDER, _OUTPUT_FILE), 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(_OUTPUT_HEADER)
        for lh_id, issue, status in issues:
            h = details.get(lh_id, {})
            q = queue.get(lh_id, {})
            writer.writerow([lh_id, h.get('Price Paid', ''), q.get(_LHT_VALUE, ''),
                             h.get('Land Holding Type', ''), h.get('Account Name', ''),
                             h.get('Land Holding Name') or q.get(_LH_NAME, ''), issue, status])
    return len(issues)


def _locked_files():
    """Paths of the report CSVs and Update_Inverted.csv in _PPIQ_FOLDER that exist but can't be
    written (open in Excel), so PPIQ can say so before spending minutes on downloads."""
    locked = []
    for name in [r.filename for r in _REPORTS.values()] + [_OUTPUT_FILE]:
        path = os.path.join(_PPIQ_FOLDER, name)
        try:
            with open(path, 'r+b'):
                pass
        except FileNotFoundError:
            pass
        except PermissionError:
            locked.append(path)
    return locked


def _close_it(path):
    """Warning box: path is open elsewhere (probably Excel); close it and run PPIQ again."""
    ark_common.notify('PPIQ', f'{path} is open in another program (probably Excel).\n\n'
                              'Close it and click PPIQ again.', 0x30)


def main():
    """Download the reports, run the analysis and show how many issues were written. Stops with a
    "close it" box (_close_it) if a file PPIQ writes is open in Excel: before downloading
    (_locked_files), or when it comes to write Update_Inverted.csv."""
    locked = _locked_files()
    if locked:
        _close_it(locked[0])
        return
    _download_files()
    output = os.path.join(_PPIQ_FOLDER, _OUTPUT_FILE)
    try:
        issues = _run_analysis()
    except PermissionError as e:
        if os.path.normcase(str(e.filename)) != os.path.normcase(output):
            raise
        _close_it(output)
        return
    ark_common.notify('PPIQ', f'{ark_common.plural(issues, "issue")} written to:\n{output}')


if __name__ == '__main__':
    ark_common.run_button('PPIQ', main, os.path.join(_PPIQ_FOLDER, 'ppiq_error.log'))
