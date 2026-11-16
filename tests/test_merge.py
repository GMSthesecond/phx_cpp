"""Merge button (merge.py): reads the two account links, opens both accounts and their land holdings in
the fake Ark, reads their details, counts, notes and land holding fields, and shows them in the review
window (recorded by conftest's reviews fixture; the window itself is built here with _review_window
and never run). Then, with an account picked to keep (reviews.keep), the land holdings window's choices
(holdings fixture; that window is built here with _holdings_window and never run) and Yes in the box,
renames both, adds the note blocks, moves records and land holdings, copies documents and deletes the
merge account through the fake Ark's edit windows, drawers and buttons (fakes._EditDialog and others).
The link window is tested in tests/cpp/test_merge.cpp and test_app_buttons.py.
"""
import json
import re
import types
from datetime import date

import pytest

import fakes
import merge
from fakes import HOLDING_URL, account_page, holding_page

ID_1 = '298bf830230991db2c6679eb'  # Dummy 1, a test account made for Merge
ID_2 = '2176a2baecb3919109798abe'  # Dummy 2
LINK_1 = f'https://ark.phoenixenergy.com/accounts?recordId={ID_1}'  # as copied from the address bar
LINK_2 = f'https://ark.phoenixenergy.com/accounts?recordId={ID_2}'
LH_A, LH_B, LH_C = 'a92ec114c57d218a3c71ced4', 'f530f6e36fab04af99c49689', '7c0f840b3bab319b3a1ec9e3'  # land holding ids
NO_SIGNERS = {'Legal Entity': 'Dummy 1', 'Section Name': '31-9N-56W', 'Title Information': ''}  # holding_page defaults


def serve_dummies(fake_ark, **first):
    """Serves Dummy 1 (with first's serve_account options) and a plain Dummy 2."""
    fake_ark.serve_account(ID_1, 'Dummy 1', **first)
    fake_ark.serve_account(ID_2, 'Dummy 2')


# ─── Links ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('text', [
    LINK_1,
    ID_1,
    f'  {LINK_1}\r\n',                                                   # blanks around a paste
    LINK_1.upper().replace('HTTPS://ARK.PHOENIXENERGY.COM', 'https://ark.phoenixenergy.com'),
    f'https://ark.phoenixenergy.com/accounts/?recordId={ID_1}',          # trailing slash
    f'https://ark.phoenixenergy.com/accounts?tab=history&recordId={ID_1}&x=1#top',
    f'https://ark.phxcapitalgroup.com/accounts?recordId={ID_1}',         # Ark's other domain
    f'http://ark.phoenixenergy.com/accounts?RECORDID={ID_1}',
])
def test_record_id_from_a_link_or_bare_id(text):
    """A link to an account page or the bare id gives the id in lowercase."""
    assert merge.record_id(text) == ID_1


@pytest.mark.parametrize('text', [
    '',
    'Dummy 1',
    f'https://ark.phoenixenergy.com/landholdings?recordId={ID_1}',      # a landholding, not an account
    f'https://ark.phoenixenergy.com/report?recordId={ID_1}',
    'https://ark.phoenixenergy.com/accounts?recordId=298bf830230991db2c6679e',   # one digit short
    'https://ark.phoenixenergy.com/accounts?recordId=298bf830230991db2c6679ebb',  # one too many
    'https://ark.phoenixenergy.com/accounts?recordId=298bf830230991db2c6679ez',   # not hex
    'https://ark.phoenixenergy.com/accounts',
    f'{LINK_1} {LINK_2}',                                               # two links in one box
    f'ark.phoenixenergy.com/accounts?recordId={ID_1}',                  # no https://
])
def test_record_id_rejects_anything_else(text):
    """Text that isn't one account link or record id is refused."""
    with pytest.raises(ValueError, match='Not a link to an Ark account'):
        merge.record_id(text)


@pytest.mark.parametrize('args, error', [
    ([], 'needs links to two accounts, got 0'),
    ([LINK_1], 'needs links to two accounts, got 1'),
    ([LINK_1, LINK_2, LINK_2], 'needs links to two accounts, got 3'),
    ([LINK_1, ID_1.upper()], 'Both links are the same account'),
    ([LINK_1, 'Dummy 2'], 'Not a link to an Ark account: Dummy 2'),
])
def test_bad_arguments_stop_before_ark_opens(fake_ark, args, error):
    """Wrong argument counts, the same account twice or a non-link stop before a browser opens."""
    with pytest.raises(ValueError, match=error):
        merge.main(args)
    assert fake_ark.visited == [] and fake_ark.launch_options is None


# ─── Reading the accounts ──────────────────────────────────────────────────────

def test_reads_both_accounts_and_shows_the_review(fake_ark, msgboxes, reviews):
    """Both accounts are opened with the saved login, read, and shown in the review window (no message
    box); nothing is downloaded or uploaded, and the session is saved before the window opens."""
    serve_dummies(fake_ark)

    accounts = merge.main([LINK_1, LINK_2])

    assert [(a['name'], a['url']) for a in accounts] == [('Dummy 1', LINK_1), ('Dummy 2', LINK_2)]
    assert accounts[0] == {
        'name': 'Dummy 1', 'url': LINK_1,
        'counts': dict.fromkeys(merge.CHECKED, 0),
        'details': {'Created Date': '11/6/2026 - 9:37:52 AM', 'Account Disposition': '', 'Mailing Street': '',
                    'Mailing City': '', 'Mailing State': '', 'Mailing Zip Code': '', 'Confirmed Phone Number': '',
                    'Confirmed Email Addresses': '', 'Parent Account': 'Dummy Parent (Ruby Mesecher)'},
        'notes': {'Account Notes': '', 'Call Notes': ''},
        'holdings_missing': 0, 'holdings': []}
    assert reviews == [accounts]
    assert msgboxes == []
    assert fake_ark.visited == [LINK_1, LINK_2], 'each account page is opened once'
    assert fake_ark.downloads == [] and fake_ark.logins == []
    assert fake_ark.sessions_saved == 1 and fake_ark.browser_closed


def test_reads_details_counts_and_notes(fake_ark, reviews):
    """Each account gets its own details, Quick Reference counts (thousands separators read) and
    notes (blanks around them trimmed, several lines kept); the unrelated "Notes" field elsewhere on the
    page isn't taken for Account Notes."""
    fake_ark.serve_account(ID_1, 'Dummy 1', counts={
        'Documents': 3, 'Contacts': 1, 'Offers': 1, 'Title Requests': 0, 'Tasks': 2, 'Calls & Texts': 1234,
        'Land Holdings': 0}, notes={'Account Notes': '  Dummy 1 an\nsecond line  ', 'Call Notes': 'Dummy 1 cn'},
        details={'Account Disposition': 'Deceased', 'Mailing Street': '1 Main St', 'Mailing City': 'Billings',
                 'Mailing State': 'MT', 'Mailing Zip Code': '59101', 'Confirmed Phone Number': '(406) 555-0100',
                 'Confirmed Email Addresses': 'a@example.com\nb@example.com'})
    fake_ark.serve_account(ID_2, 'Dummy 2', details={'Created Date': '11/6/2026 - 9:38:38 AM'})

    first, second = merge.main([LINK_1, LINK_2])

    assert first['counts'] == {'Documents': 3, 'Contacts': 1, 'Offers': 1, 'Title Requests': 0, 'Tasks': 2,
                               'Calls & Texts': 1234, 'Land Holdings': 0}
    assert first['notes'] == {'Account Notes': 'Dummy 1 an\nsecond line', 'Call Notes': 'Dummy 1 cn'}
    assert first['details'] == {
        'Created Date': '11/6/2026 - 9:37:52 AM', 'Account Disposition': 'Deceased', 'Mailing Street': '1 Main St',
        'Mailing City': 'Billings', 'Mailing State': 'MT', 'Mailing Zip Code': '59101',
        'Confirmed Phone Number': '(406) 555-0100', 'Confirmed Email Addresses': 'a@example.com\nb@example.com',
        'Parent Account': 'Dummy Parent (Ruby Mesecher)'}
    assert second['details']['Created Date'] == '11/6/2026 - 9:38:38 AM'
    assert second['notes'] == {'Account Notes': '', 'Call Notes': ''}


@pytest.mark.parametrize('fields, quick, parent', [
    ([['Details', 'Parent Account', 'Smith Holdings']], [['Parent - Other (Owner)\nChild', '']], 'Smith Holdings'),
    ([['Hierarchy', 'Parent Account', '']], [], ''),                     # the field wins, blank or not
    ([], [['Parent - Dummy Parent (Ruby Mesecher)\nDummy (Ruby Mesecher)', '']], 'Dummy Parent (Ruby Mesecher)'),
    ([], [['History', '(3)']], ''),                                      # neither: blank
])
def test_parent_account_from_its_field_or_the_hierarchy_entry(fields, quick, parent):
    """An account's parent: a "Parent Account" field in any section, else the first line of Ark's
    "Parent - <name>" Quick Reference entry, else blank."""
    raw = {'quick': quick, 'fields': fields, 'holdings': []}
    assert merge._parent(raw, merge._fields(raw)) == parent


def test_items_a_page_doesnt_show_are_none(fake_ark, reviews):
    """Other kinds of account have no Offers, Title Requests or Land Holdings in their Quick Reference,
    and a page may lack a field or notes section: those are None, not 0 or blank."""
    fake_ark.serve_account(ID_1, 'Investor', counts={'Documents': 0, 'Contacts': 1, 'Tasks': 0, 'Calls & Texts': 0},
                           notes={'Call Notes': None}, details={'Account Disposition': None})
    fake_ark.serve_account(ID_2, 'Dummy 2')

    first, _ = merge.main([LINK_1, LINK_2])

    assert first['counts'] == {'Documents': 0, 'Contacts': 1, 'Offers': None, 'Title Requests': None, 'Tasks': 0,
                               'Calls & Texts': 0, 'Land Holdings': None}
    assert first['notes'] == {'Account Notes': '', 'Call Notes': None}
    assert first['details']['Account Disposition'] is None
    assert first['holdings'] == [] and first['holdings_missing'] == 0


def test_values_are_read_once_the_page_settles(fake_ark, reviews):
    """Values still loading aren't taken: the page is read until two reads _SETTLE_MS apart agree."""
    serve_dummies(fake_ark)
    loading = {'quick': [], 'fields': [], 'holdings': []}
    partial = account_page({'Documents': 0, 'Contacts': 0})
    final = account_page({'Documents': 2, 'Contacts': 1, 'Offers': 0, 'Title Requests': 0, 'Tasks': 0,
                          'Calls & Texts': 0, 'Land Holdings': 0}, notes={'Account Notes': 'loaded'})
    fake_ark.pages[ID_1] = [loading, partial, final]

    first, _ = merge.main([LINK_1, LINK_2])

    assert first['counts']['Documents'] == 2 and first['notes']['Account Notes'] == 'loaded'
    assert fake_ark.evaluated == [ID_1] * 4 + [ID_2] * 2
    assert fake_ark.waited_ms == 4 * merge._SETTLE_MS


def test_no_quick_reference_fails_after_the_time_limit(fake_ark, reviews):
    """An account page whose Quick Reference never shows fails after _OPEN_TIMEOUT_MS, naming the
    page, and no review window opens."""
    serve_dummies(fake_ark)
    fake_ark.pages[ID_2] = [{'quick': [], 'fields': [], 'holdings': []}]

    with pytest.raises(RuntimeError, match=re.escape(f"didn't finish showing the page in 30 s:\n{LINK_2}")):
        merge.main([LINK_1, LINK_2])
    assert reviews == []


def test_command_line_arguments_are_read(fake_ark, reviews, monkeypatch):
    """With no argv, main() reads sys.argv like the button's `py merge.py <id> <id>`."""
    serve_dummies(fake_ark)
    monkeypatch.setattr('sys.argv', ['merge.py', ID_1, ID_2])

    assert [a['name'] for a in merge.main()] == ['Dummy 1', 'Dummy 2']


def test_order_and_form_of_the_links_dont_matter(fake_ark, reviews):
    """The accounts are read in the order given, as bare ids (what the link window passes) or links."""
    serve_dummies(fake_ark)

    assert [a['url'] for a in merge.main([ID_2, ID_1.upper()])] == [LINK_2, LINK_1]
    assert fake_ark.visited == [LINK_2, LINK_1]


def test_logs_in_then_opens_the_first_account(fake_ark, reviews):
    """A signed-out session logs in, and the first account is opened again since the login lands on
    Ark's home page."""
    serve_dummies(fake_ark)
    fake_ark.needs_login = {'ark.phoenixenergy.com'}

    assert [a['name'] for a in merge.main([LINK_1, LINK_2])] == ['Dummy 1', 'Dummy 2']
    assert fake_ark.logins == ['https://ark.phoenixenergy.com/**']
    assert fake_ark.visited == [LINK_1, LINK_1, LINK_2]


def test_names_with_dashes_and_the_same_name_twice(fake_ark, reviews):
    """The whole name after "Account - " is kept, and duplicates (the usual reason to merge) are fine."""
    fake_ark.serve_account(ID_1, 'Smith - Jones Trust')
    fake_ark.serve_account(ID_2, 'Smith - Jones Trust')

    assert [a['name'] for a in merge.main([LINK_1, LINK_2])] == ['Smith - Jones Trust'] * 2


def test_account_ark_doesnt_have(fake_ark, msgboxes, reviews):
    """A record id with no account (Ark shows "Account Not Found") stops the run at once with the
    link; no review window opens and the session is still saved."""
    fake_ark.serve_account(ID_1, 'Dummy 1')

    with pytest.raises(RuntimeError, match=re.escape(f'Ark shows "Account Not Found"; check the link:\n{LINK_2}')):
        merge.main([LINK_2, LINK_1])
    assert fake_ark.waited_ms == 0, 'should fail as soon as Ark says Not Found'
    assert reviews == [] and msgboxes == []
    assert fake_ark.sessions_saved == 1


def test_account_page_that_never_loads(fake_ark, reviews):
    """A page that shows neither a name nor Not Found fails after _OPEN_TIMEOUT_MS, naming the link."""
    fake_ark.serve_account(ID_1, None)
    fake_ark.serve_account(ID_2, 'Dummy 2')

    with pytest.raises(RuntimeError, match=re.escape(f"didn't finish opening the page in 30 s:\n{LINK_1}")):
        merge.main([LINK_1, LINK_2])
    assert fake_ark.waited_ms == merge._OPEN_TIMEOUT_MS
    assert reviews == []


# ─── Land holdings ─────────────────────────────────────────────────────────────

def test_reads_each_land_holding_of_each_account(fake_ark, reviews):
    """Every land holding linked on an account page (each once, though the page links it twice) is
    opened after its account and read for Legal Entity, Section Name, Title Information and signers."""
    fake_ark.serve_account(ID_1, 'Dummy 1', holdings=[LH_A, LH_B])
    fake_ark.serve_account(ID_2, 'Dummy 2', holdings=[LH_C])
    fake_ark.serve_holding(LH_A, '32-9N-56W-Dummy 11', fields={'Section Name': '32-9N-56W'})
    fake_ark.serve_holding(LH_B, '31-9N-56W-Dummy 1', fields={'Title Information': 'Ignore this :D'},
                           signers=[('Dummy 1', '1', '')])
    fake_ark.serve_holding(LH_C, '33-9N-56W-Dummy 2', fields={'Legal Entity': 'Dummy 2', 'Section Name': '33-9N-56W'})

    first, second = merge.main([LINK_1, LINK_2])

    assert first['counts']['Land Holdings'] == 2 and first['holdings_missing'] == 0
    assert first['holdings'] == [
        {'name': '32-9N-56W-Dummy 11', 'url': HOLDING_URL.format(LH_A), 'signers': [],
         'fields': {'Legal Entity': 'Dummy 1', 'Section Name': '32-9N-56W', 'Title Information': ''}},
        {'name': '31-9N-56W-Dummy 1', 'url': HOLDING_URL.format(LH_B),
         'signers': [{'Signer': 'Dummy 1', 'Last Name': '1', 'Capacity': ''}],
         'fields': {'Legal Entity': 'Dummy 1', 'Section Name': '31-9N-56W', 'Title Information': 'Ignore this :D'}}]
    assert [h['fields']['Legal Entity'] for h in second['holdings']] == ['Dummy 2']
    assert fake_ark.visited == [LINK_1, HOLDING_URL.format(LH_A), HOLDING_URL.format(LH_B),
                                LINK_2, HOLDING_URL.format(LH_C)]


def test_signers_in_number_order_blank_ones_left_out(fake_ark, reviews):
    """Signers come back in number order with their Last Name and Capacity; a signer with only a last
    name or capacity is kept, and one with nothing filled is left out. (Ark has Last Name only for Signer
    1-2 and Capacity only for Signer 1-3.)"""
    fake_ark.serve_account(ID_1, 'Dummy 1', holdings=[LH_A])
    fake_ark.serve_account(ID_2, 'Dummy 2')
    fake_ark.serve_holding(LH_A, 'LH', signers=[('Jane Doe', 'Doe', 'Trustee'), ('', 'Roe', ''),
                                                ('', '', 'Personal Representative'), ('', '', ''), ('John Roe', '', '')])

    first, _ = merge.main([LINK_1, LINK_2])

    assert first['holdings'][0]['signers'] == [
        {'Signer': 'Jane Doe', 'Last Name': 'Doe', 'Capacity': 'Trustee'},
        {'Signer': '', 'Last Name': 'Roe', 'Capacity': ''},
        {'Signer': '', 'Last Name': '', 'Capacity': 'Personal Representative'},
        {'Signer': 'John Roe', 'Last Name': '', 'Capacity': ''}]


def test_land_holding_fields_a_page_doesnt_show_are_none(fake_ark, reviews):
    """A land holding page without one of the fields gives None for it."""
    fake_ark.serve_account(ID_1, 'Dummy 1', holdings=[LH_A])
    fake_ark.serve_account(ID_2, 'Dummy 2')
    fake_ark.serve_holding(LH_A, 'LH', fields={'Title Information': None})

    first, _ = merge.main([LINK_1, LINK_2])

    assert first['holdings'][0]['fields']['Title Information'] is None


def test_land_holdings_counted_but_not_linked_are_reported(fake_ark, reviews):
    """When the Quick Reference counts more land holdings than the page links (it may list only some),
    the ones not read are counted in holdings_missing."""
    counts = {**dict.fromkeys(merge.CHECKED, 0), 'Land Holdings': 5}
    fake_ark.serve_account(ID_1, 'Dummy 1', counts=counts, holdings=[LH_A, LH_B])
    fake_ark.serve_account(ID_2, 'Dummy 2')
    fake_ark.serve_holding(LH_A, 'A')
    fake_ark.serve_holding(LH_B, 'B')

    first, second = merge.main([LINK_1, LINK_2])

    assert len(first['holdings']) == 2 and first['holdings_missing'] == 3
    assert second['holdings_missing'] == 0


def test_land_holding_ark_doesnt_have(fake_ark, reviews):
    """A linked land holding Ark can't find fails the run, naming its link."""
    fake_ark.serve_account(ID_1, 'Dummy 1', holdings=[LH_A])
    fake_ark.serve_account(ID_2, 'Dummy 2')

    with pytest.raises(RuntimeError, match=re.escape(
            f'Ark shows "Land Holding Not Found"; check the link:\n{HOLDING_URL.format(LH_A)}')):
        merge.main([LINK_1, LINK_2])
    assert reviews == []


def test_land_holding_values_are_read_once_the_page_settles(fake_ark, reviews):
    """A land holding page still filling in is read again until two reads agree."""
    fake_ark.serve_account(ID_1, 'Dummy 1', holdings=[LH_A])
    fake_ark.serve_account(ID_2, 'Dummy 2')
    fake_ark.serve_holding(LH_A, 'LH')
    fake_ark.pages[LH_A] = [{'quick': [], 'fields': [], 'holdings': []},
                            holding_page({'Legal Entity': 'Loading'}), holding_page({'Legal Entity': 'Dummy 1 Trust'})]

    first, _ = merge.main([LINK_1, LINK_2])

    assert first['holdings'][0]['fields']['Legal Entity'] == 'Dummy 1 Trust'


# ─── Review window ─────────────────────────────────────────────────────────────

def _account(name, url, **changes):
    """An account as main() returns it, all blank / 0, with changes applied."""
    account = {'name': name, 'url': url, 'counts': dict.fromkeys(merge.CHECKED, 0),
               'details': {label: '' for _, label in merge.DETAILS},
               'notes': {section: '' for section, _ in merge.NOTES}, 'holdings_missing': 0, 'holdings': []}
    for key, value in changes.items():
        account[key] = {**account[key], **value} if isinstance(value, dict) else value
    return account


def _holding(name, legal='Dummy 1', section='31-9N-56W', title='', signers=()):
    """A land holding as main() returns it."""
    return {'name': name, 'url': HOLDING_URL.format(name), 'signers': list(signers),
            'fields': {'Legal Entity': legal, 'Section Name': section, 'Title Information': title}}


ACCOUNTS = [  # two accounts like the Dummy ones, with something in most fields
    _account('Dummy 1', LINK_1, counts={'Contacts': 1, 'Offers': 1, 'Land Holdings': 2, 'Calls & Texts': 1234},
             details={'Created Date': '11/6/2026 - 9:37:52 AM', 'Mailing City': 'Billings'},
             notes={'Account Notes': 'Dummy 1 an'},
             holdings=[_holding('31-9N-56W-Dummy 1', title='Ignore this :D',
                                signers=[{'Signer': 'Dummy 1', 'Last Name': '1', 'Capacity': ''}]),
                       _holding('32-9N-56W-Dummy 11', section='32-9N-56W')]),
    _account('Dummy 2', LINK_2, counts={'Documents': 1, 'Title Requests': 1, 'Offers': None},
             details={'Created Date': '11/6/2026 - 9:38:38 AM', 'Account Disposition': None},
             notes={'Call Notes': 'Dummy 2 CN'}, holdings_missing=3),
]


def test_review_rows_put_the_accounts_side_by_side():
    """review_rows lists names, links, details, counts and notes with one text per account: blank
    fields say "blank", 0 says "none", items not on a page say so."""
    rows = merge.review_rows(ACCOUNTS)
    table = {item[1]: item[2] for item in rows if item[0] == 'row'}

    assert [item[1] for item in rows if item[0] == 'heading'] == ['Account', 'What each account holds', 'Notes']
    assert list(table) == ['Name', 'Link', *(label for _, label in merge.DETAILS), 'Parent Account', *merge.CHECKED,
                           'Account Notes', 'Call Notes']
    assert table['Parent Account'] == ['not on this page', 'not on this page']  # _account has none
    assert table['Name'] == ['Dummy 1', 'Dummy 2']
    assert table['Link'] == [LINK_1, LINK_2]
    assert table['Created Date'] == ['11/6/2026 - 9:37:52 AM', '11/6/2026 - 9:38:38 AM']
    assert table['Account Disposition'] == ['blank', 'not on this page']
    assert table['Mailing City'] == ['Billings', 'blank']
    assert table['Contacts'] == ['1', 'none']
    assert table['Calls & Texts'] == ['1,234', 'none']
    assert table['Offers'] == ['1', 'not on this page']
    assert table['Account Notes'] == ['Dummy 1 an', 'blank']
    assert table['Call Notes'] == ['blank', 'Dummy 2 CN']


def test_holding_lines():
    """A land holding is shown as Legal Entity, Section Name, Signers (name, then Last Name and
    Capacity when filled, "; " between signers) and Title Information."""
    holding = _holding('LH', title='', signers=[{'Signer': 'Jane Doe', 'Last Name': 'Doe', 'Capacity': 'Trustee'},
                                                {'Signer': '', 'Last Name': 'Roe', 'Capacity': ''},
                                                {'Signer': 'Bo', 'Last Name': '', 'Capacity': ''}])
    assert merge._holding_lines(holding) == [
        'Legal Entity: Dummy 1', 'Section Name: 31-9N-56W',
        'Signers: Jane Doe (Last Name: Doe, Capacity: Trustee); (no name) (Last Name: Roe); Bo',
        'Title Information: blank']
    assert merge._holding_lines(_holding('LH', legal=None))[0] == 'Legal Entity: not on this page'
    assert merge._holding_lines(_holding('LH'))[2] == 'Signers: none'


@pytest.fixture(scope='module')
def tk_root():
    """One hidden Tk for every window test: Tk started and torn down over and over in one process
    sometimes fails to load its own files ("couldn't read ... msgs/en.msg")."""
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def window(tk_root):
    """The review window for ACCOUNTS, built hidden (in tk_root) and never run; destroyed afterwards."""
    root = merge._review_window(ACCOUNTS, master=tk_root)
    root.withdraw()
    root.update_idletasks()
    yield root
    root.destroy()


def _labels(widget):
    """Every Label under widget (depth first)."""
    found = []
    for child in widget.winfo_children():
        if child.winfo_class() == 'Label':
            found.append(child)
        found += _labels(child)
    return found


def _grid(root):
    """{(row, column): text} of every Label placed in the review window's grid."""
    cells = {}
    for label in _labels(root):
        info = label.grid_info()
        if info:
            cells[(int(info['row']), int(info['column']))] = label.cget('text')
    return cells


def _row_of(cells, text, column=0):
    """Grid rows whose cell in column shows exactly text."""
    return [r for (r, c), t in cells.items() if c == column and t == text]


def test_review_window_shows_every_value_in_its_accounts_column(window):
    """A header per account, then each review row: its label in column 0, Account 1's text in column 1
    and Account 2's in column 2, in review_rows order."""
    cells = _grid(window)
    assert cells[(0, 1)] == 'Account 1' and cells[(0, 2)] == 'Account 2'
    rows = merge.review_rows(ACCOUNTS)
    for r, item in enumerate(rows, 1):
        if item[0] == 'heading':
            assert cells[(r, 0)] == item[1]
        else:
            assert (cells[(r, 0)], cells[(r, 1)], cells[(r, 2)]) == (item[1], *item[2])


def test_review_window_lists_each_accounts_land_holdings(window):
    """Under the Land Holdings heading (after the review rows), each account's holdings are listed in its
    column: the name (a link), then its lines; an account with none says so, and land holdings counted
    but not read are shown in red."""
    cells = _grid(window)
    heading = len(merge.review_rows(ACCOUNTS)) + 1
    assert cells[(heading, 0)] == 'Land Holdings'
    first, second = ACCOUNTS[0]['holdings']
    assert cells[(heading + 1, 1)] == first['name']
    assert cells[(heading + 2, 1)] == '\n'.join(merge._holding_lines(first))
    assert cells[(heading + 3, 1)] == second['name']
    assert cells[(heading + 4, 1)] == '\n'.join(merge._holding_lines(second))
    assert cells[(heading + 1, 2)] == 'none'
    assert cells[(heading + 2, 2)].startswith('3 more land holding(s) counted but not listed')
    [missing] = [w for w in _labels(window) if w.cget('text').startswith('3 more')]
    assert missing.cget('fg') == '#c00000'


def test_review_window_links_open_in_the_browser(window, monkeypatch):
    """Clicking an account link or land holding name opens it in the browser."""
    opened = []
    monkeypatch.setattr(merge.webbrowser, 'open', opened.append)
    for text in (LINK_1, '31-9N-56W-Dummy 1'):
        [label] = [w for w in _labels(window) if w.cget('text') == text]
        label.event_generate('<Button-1>')
    assert opened == [LINK_1, HOLDING_URL.format('31-9N-56W-Dummy 1')]


def _buttons(widget):
    """Every Button under widget (depth first)."""
    found = [c for c in widget.winfo_children() if c.winfo_class() == 'Button']
    return found + [b for c in widget.winfo_children() for b in _buttons(c)]


def test_review_window_offers_keep_buttons_and_cancel(window):
    """The window says nothing was changed in Ark yet, and has a Keep button per account and Cancel."""
    assert window.title() == 'Merge Accounts - Review'
    assert any('Nothing has been changed in Ark yet' in w.cget('text') for w in _labels(window))
    assert sorted(b.cget('text') for b in _buttons(window)) == ['Cancel', 'Keep Account 1', 'Keep Account 2']
    assert window.keep is None


@pytest.mark.parametrize('text, keep', [('Keep Account 1', 0), ('Keep Account 2', 1), ('Cancel', None)])
def test_review_window_buttons_answer_and_close(tk_root, text, keep):
    """A Keep button closes the window with that account's index as its answer; Cancel with None."""
    root = merge._review_window(ACCOUNTS, master=tk_root)
    root.withdraw()
    [button] = [b for b in _buttons(root) if b.cget('text') == text]
    button.invoke()
    assert root.keep == keep
    assert not root.winfo_exists()


# ─── Merge step: names and the note block ──────────────────────────────────────

@pytest.mark.parametrize('name, tag, tagged', [
    ('Dummy 1', 'keep', 'Dummy 1 (keep)'),
    ('Dummy 1', 'merge', 'Dummy 1 (merge)'),
    ('Dummy 1 (merge)', 'keep', 'Dummy 1 (keep)'),      # a merge started over the other way round
    ('Dummy 1 (Keep) ', 'keep', 'Dummy 1 (keep)'),      # not tagged twice
    ('Smith Family (Trust)', 'merge', 'Smith Family (Trust) (merge)'),  # other brackets stay
])
def test_tagged_name(name, tag, tagged):
    """(keep) / (merge) goes at the end of the name, replacing either one already there."""
    assert merge.tagged_name(name, tag) == tagged


def _with(details=None, notes=None):
    """An account (as main() reads it) with these details and Account Notes, the rest blank."""
    return _account('X', LINK_1, details=details or {}, notes={'Account Notes': notes} if notes is not None else {})


MERGE_INFO = {'Mailing Street': '1 Main St', 'Mailing City': 'Billings', 'Mailing State': 'MT',
              'Mailing Zip Code': '59101', 'Confirmed Phone Number': '(406) 555-0100',
              'Confirmed Email Addresses': 'd2@example.com'}  # a merge account with every compared field filled
# A kept account with its own (different) address, phone and email, so none of MERGE_INFO is copied into blanks
KEEP_INFO = {'Mailing City': 'Denver', 'Confirmed Phone Number': '303-555-0100',
             'Confirmed Email Addresses': 'd1@example.com'}


def test_merge_differences_lists_what_the_kept_account_lacks():
    """Against a kept account with other values, the merge account's mailing address (one line), phone
    and email are all listed."""
    assert merge.merge_differences(_with(KEEP_INFO), _with(MERGE_INFO)) == [
        'Mailing Address: 1 Main St, Billings, MT 59101', 'Phone: (406) 555-0100', 'Email: d2@example.com']


def test_merge_differences_skips_the_same_values_typed_differently():
    """The same address in another case / spacing, the same phone number in another format (or with a
    leading 1), and the same email in capitals aren't listed."""
    keep = _with({'Mailing Street': '1 MAIN  ST', 'Mailing City': 'billings', 'Mailing State': 'mt',
                  'Mailing Zip Code': '59101', 'Confirmed Phone Number': '1-406-555-0100',
                  'Confirmed Email Addresses': 'D2@Example.com'})
    assert merge.merge_differences(keep, _with(MERGE_INFO)) == []


def test_merge_differences_skips_blank_and_lists_partial_differences():
    """A blank field on the merge account isn't listed; a different zip makes the whole address listed;
    a phone / email list with one number or address the kept account lacks is listed as it is."""
    keep = _with({**MERGE_INFO, 'Confirmed Phone Number': '406-555-0100', 'Confirmed Email Addresses': 'a@x.com'})
    merging = _with({**MERGE_INFO, 'Mailing Zip Code': '59102', 'Confirmed Phone Number': '406-555-0100, 406-555-0199',
                     'Confirmed Email Addresses': ''})
    assert merge.merge_differences(keep, merging) == [
        'Mailing Address: 1 Main St, Billings, MT 59102', 'Phone: 406-555-0100, 406-555-0199']
    assert merge.merge_differences(_with(MERGE_INFO), _with({'Mailing City': None})) == []  # not on the page


def test_blank_fills_copy_the_merge_accounts_values_into_the_kept_accounts_blanks():
    """Against a blank kept account every field the merge account has is filled in (trimmed, in DETAILS
    order), and none of them goes in the note."""
    assert merge.blank_fills(_with(), _with({**MERGE_INFO, 'Mailing Street': ' 1 Main St '})) == MERGE_INFO
    assert list(merge.blank_fills(_with(), _with(MERGE_INFO))) == [label for _, label in merge.DETAILS if label in MERGE_INFO]
    assert merge.merge_differences(_with(), _with(MERGE_INFO)) == []


def test_blank_fills_take_the_address_only_as_a_whole():
    """A kept account with part of an address (just a city) keeps it: the merge account's address goes in
    the note instead, while its phone and email still fill the kept account's blank ones. A kept field of
    only spaces counts as blank."""
    keep = _with({'Mailing City': 'Denver', 'Confirmed Phone Number': '  '})
    assert merge.blank_fills(keep, _with(MERGE_INFO)) == {'Confirmed Phone Number': '(406) 555-0100',
                                                           'Confirmed Email Addresses': 'd2@example.com'}
    assert merge.merge_differences(keep, _with(MERGE_INFO)) == ['Mailing Address: 1 Main St, Billings, MT 59101']


def test_blank_fills_skip_fields_not_on_the_page_and_blank_merge_values():
    """A kept field the page doesn't show (None) isn't filled (nor is the address if any part is missing),
    and a blank merge account field fills nothing."""
    assert merge.blank_fills(_with({'Confirmed Phone Number': None, 'Mailing Zip Code': None}), _with(MERGE_INFO)) == {
        'Confirmed Email Addresses': 'd2@example.com'}
    assert merge.blank_fills(_with(), _with()) == {}


def test_merge_note_layout():
    """Date (mm/dd/yyyy) and RM, the differences, then the merge account's notes between quote lines."""
    block = merge.merge_note(_with(KEEP_INFO), _with(MERGE_INFO, notes='  Called 5/1.\nWants offer.  '), date(2026, 11, 6))
    assert block == ('11/06/2026 RM - Notes from merge:\n'
                     'Mailing Address: 1 Main St, Billings, MT 59101\n'
                     'Phone: (406) 555-0100\n'
                     'Email: d2@example.com\n'
                     '"\nCalled 5/1.\nWants offer.\n"')


def test_merge_note_with_only_notes_or_nothing():
    """No differences: just the date line and the quoted notes. No differences and no notes (blank or
    not on the page): nothing to add."""
    assert merge.merge_note(_with(), _with(notes='Dummy 2 an'), date(2026, 1, 2)) == \
        '01/02/2026 RM - Notes from merge:\n"\nDummy 2 an\n"'
    assert merge.merge_note(_with(), _with(), date(2026, 1, 2)) == ''
    assert merge.merge_note(_with(), _account('X', LINK_1, notes={'Account Notes': None}), date(2026, 1, 2)) == ''


def test_combined_notes_puts_the_block_above_with_a_blank_line():
    """The block, a blank line, the existing notes; with no existing notes, just the block."""
    assert merge.combined_notes('B', 'old\nnotes\n') == 'B\n\nold\nnotes'
    assert merge.combined_notes('B', '  ') == 'B'
    assert merge.combined_notes('B', None) == 'B'


# ─── Merge step: changing the accounts in Ark ──────────────────────────────────

class _Today(date):
    """A date whose today() is 11/06/2026, for a fixed note block."""

    @classmethod
    def today(cls):
        """11/06/2026."""
        return cls(2026, 11, 6)


@pytest.fixture
def merging(fake_ark, reviews, msgboxes, monkeypatch):
    """Dummy 1 (mailing city Billings, phone 406-555-0100, notes "Dummy 1 an" / "Dummy 1 cn", a contact and
    an offer) and Dummy 2 (another mailing city and phone, notes "Dummy 2 an" / "Dummy 2 CN", a title
    request and a call), like the practice accounts; today 11/06/2026, and Dummy 1 picked to keep in the
    review window. (Dummy 1 has its own city and phone so Dummy 2's go in the note, not into blanks.)"""
    monkeypatch.setattr(merge, 'datetime', types.SimpleNamespace(date=_Today))
    fake_ark.serve_account(ID_1, 'Dummy 1', notes={'Account Notes': 'Dummy 1 an', 'Call Notes': 'Dummy 1 cn'},
                           details={'Mailing City': 'Billings', 'Confirmed Phone Number': '406-555-0100'},
                           related={'Contacts': [CONTACT], 'Offers': [OFFER]})
    fake_ark.serve_account(ID_2, 'Dummy 2', notes={'Account Notes': 'Dummy 2 an', 'Call Notes': 'Dummy 2 CN'},
                           details={'Mailing City': 'Denver', 'Confirmed Phone Number': '303-555-0100'},
                           related={'Title Requests': [REQUEST], 'Calls & Texts': [CALL]})
    reviews.keep = 0
    return fake_ark


CONTACT, OFFER, REQUEST, CALL = ('fb3feb315e84cbbe8ab0f3d1', 'ebda84528a14aa8366705b5a', 'a0661ec7d152eb7490d9c0e2',
                                 'dc6a59567e1c152644f12bdd')  # the practice contact, offer, title request and call
BLOCK = '11/06/2026 RM - Notes from merge:\nMailing Address: Denver\nPhone: 303-555-0100\n"\nDummy 2 an\n"'  # merging's
CALL_BLOCK = '11/06/2026 RM - Notes from merge:\n"\nDummy 2 CN\n"'  # merging's Call Notes block


def test_merge_call_note():
    """The Call Notes block: the date line and the merge account's Call Notes in quotes (no address /
    phone / email lines); nothing when it has none."""
    merging_account = _account('X', LINK_2, notes={'Call Notes': ' Left VM.\nCall back. '}, details=MERGE_INFO)
    assert merge.merge_call_note(merging_account, date(2026, 11, 6)) == \
        '11/06/2026 RM - Notes from merge:\n"\nLeft VM.\nCall back.\n"'
    assert merge.merge_call_note(_with(), date(2026, 11, 6)) == ''
    assert merge.merge_call_note(_account('X', LINK_2, notes={'Call Notes': None}), date(2026, 11, 6)) == ''
    assert merge.note_blocks(_with(), merging_account, date(2026, 11, 6))['Call Notes'] == \
        merge.merge_call_note(merging_account, date(2026, 11, 6))


def test_keep_renames_adds_both_note_blocks_moves_the_records_and_deletes(merging, msgboxes, browser_tabs):
    """Keep Account 1 and Yes: Dummy 2 is renamed "Dummy 2 (merge)" (its notes untouched), then Dummy 1
    "Dummy 1 (keep)" with a block above its Account Notes and one above its Call Notes; each is reloaded
    to check; then Dummy 2's title request and call get Dummy 1 as their Account. The box listed it all
    first. With nothing left on Dummy 2, both accounts open in the browser and the Done box asks whether
    to delete it; Yes deletes it (Delete, then Delete in Ark's confirmation), then Dummy 1 (keep) is
    renamed back to Dummy 1 (in another tab, checked after a reload) and a last box says so."""
    merge.main([LINK_1, LINK_2])

    notes = (BLOCK + '\n\nDummy 1 an', CALL_BLOCK + '\n\nDummy 1 cn')
    assert merging.saves == [(ID_2, 'Dummy 2 (merge)', 'Dummy 2 an', 'Dummy 2 CN'), (ID_1, 'Dummy 1 (keep)', *notes),
                             (ID_1, 'Dummy 1', *notes)]
    assert merging.moves == [(REQUEST, ID_2, ID_1), (CALL, ID_2, ID_1)]
    assert merging.owned[CONTACT] == ('Contacts', ID_1) and merging.owned[OFFER] == ('Offers', ID_1)
    assert merging.reloads == [LINK_2, LINK_1, LINK_1]
    assert merging.detail_saves == []
    [(_, confirm), (_, done), (_, deleted)] = msgboxes
    assert confirm == ('Merge will change these accounts in Ark:\n\n'
                       'Rename "Dummy 2" to "Dummy 2 (merge)"\nRename "Dummy 1" to "Dummy 1 (keep)"\n\n'
                       f'Add to the top of "Dummy 1" Account Notes:\n\n{BLOCK}\n\n'
                       f'Add to the top of "Dummy 1" Call Notes:\n\n{CALL_BLOCK}\n\n'
                       'Move from "Dummy 2 (merge)" to "Dummy 1 (keep)": 1 title request, 1 call / text\n'
                       'No land holdings to move or change.\n'
                       'No documents to copy from "Dummy 2".\n\n'
                       'Then, if everything moved, Merge asks before deleting "Dummy 2 (merge)", and once it\'s '
                       'deleted renames "Dummy 1 (keep)" back to "Dummy 1".\n\nGo ahead?')
    assert done == ('Renamed "Dummy 2" to "Dummy 2 (merge)" and "Dummy 1" to "Dummy 1 (keep)".\n'
                    'Added the notes from the merge to the top of its Account Notes and Call Notes.\n'
                    'Moved to "Dummy 1 (keep)": 1 title request, 1 call / text.\n\n'
                    'Both accounts are open in your browser. Review them, then:\n\n'
                    'Delete "Dummy 2 (merge)" from Ark now? This can\'t be undone. "Dummy 1 (keep)" is then '
                    'renamed "Dummy 1".')
    assert browser_tabs == [LINK_1, LINK_2]
    assert merging.deleted == [ID_2]
    assert deleted == 'Deleted "Dummy 2 (merge)" from Ark and renamed "Dummy 1 (keep)" to "Dummy 1".'
    assert merging.records[('account', ID_1)] == 'Dummy 1'
    assert merging.editing is None and merging.browser_closed


def test_keep_the_second_account(merging, reviews):
    """Keep Account 2: Dummy 1 becomes the merge account; its city, phone and notes go into Dummy 2's
    notes, its contact and offer move to Dummy 2, and once it's deleted Dummy 2 loses its "(keep)"."""
    reviews.keep = 1
    merge.main([LINK_1, LINK_2])
    block = '11/06/2026 RM - Notes from merge:\nMailing Address: Billings\nPhone: 406-555-0100\n"\nDummy 1 an\n"\n\nDummy 2 an'
    call_block = '11/06/2026 RM - Notes from merge:\n"\nDummy 1 cn\n"\n\nDummy 2 CN'
    assert merging.saves == [(ID_1, 'Dummy 1 (merge)', 'Dummy 1 an', 'Dummy 1 cn'),
                             (ID_2, 'Dummy 2 (keep)', block, call_block), (ID_2, 'Dummy 2', block, call_block)]
    assert merging.moves == [(CONTACT, ID_1, ID_2), (OFFER, ID_1, ID_2)]


def test_every_record_of_each_kind_is_moved(fake_ark, reviews, msgboxes):
    """Several of each kind on the merge account: each record is moved, kind by kind, and counted."""
    ids = {label: [f'{n:x}{i}'.ljust(24, '0') for i in range(3)] for n, (label, *_) in enumerate(merge.MOVED, 10)}
    fake_ark.serve_account(ID_1, 'Dummy 1')
    fake_ark.serve_account(ID_2, 'Dummy 2', related=ids)
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert [rid for rid, _, _ in fake_ark.moves] == [rid for label in ids for rid in ids[label]]
    assert 'Moved to "Dummy 1 (keep)": 3 contacts, 3 offers, 3 title requests, 3 calls & texts.' in msgboxes[1][1]


def test_closing_the_review_or_answering_no_changes_nothing(merging, reviews, msgboxes):
    """Closing the window without picking asks nothing and changes nothing; No in the box changes nothing."""
    reviews.keep = None
    merge.main([LINK_1, LINK_2])
    assert msgboxes == [] and merging.saves == [] and merging.moves == [] and merging.editing is None

    reviews.keep, msgboxes.answers = 0, [7]
    merge.main([LINK_1, LINK_2])
    assert [title for title, _ in msgboxes] == ['Merge'] and merging.saves == [] and merging.moves == []


def test_nothing_to_add_or_move(fake_ark, reviews, msgboxes):
    """A merge account with no differences, no notes and no records: both are only renamed, and the boxes
    say there's nothing to add or move."""
    fake_ark.serve_account(ID_1, 'Dummy 1', notes={'Account Notes': 'keep me', 'Call Notes': 'me too'})
    fake_ark.serve_account(ID_2, 'Dummy 2')
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert fake_ark.saves == [(ID_2, 'Dummy 2 (merge)', '', ''), (ID_1, 'Dummy 1 (keep)', 'keep me', 'me too'),
                              (ID_1, 'Dummy 1', 'keep me', 'me too')]
    assert fake_ark.moves == []
    confirm, done = msgboxes[0][1], msgboxes[1][1]
    assert 'Nothing to add to the Account Notes.' in confirm and 'Nothing to add to the Call Notes.' in confirm
    assert 'No contacts, offers, title requests or calls & texts to move from "Dummy 2".' in confirm
    assert 'There were no notes to add.\nNo records were moved.' in done


def test_only_call_notes_to_add(fake_ark, reviews, msgboxes):
    """A merge account with only Call Notes: only the kept account's Call Notes get a block."""
    fake_ark.serve_account(ID_1, 'Dummy 1')
    fake_ark.serve_account(ID_2, 'Dummy 2', notes={'Call Notes': 'Dummy 2 CN'})
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    [_, (_, name, account_notes, call_notes), _] = fake_ark.saves
    assert account_notes == '' and call_notes.endswith('"\nDummy 2 CN\n"')
    assert 'Added the notes from the merge to the top of its Call Notes.' in msgboxes[1][1]


def test_merging_again_doesnt_tag_twice(fake_ark, reviews):
    """Accounts already tagged from an earlier try get the new tag in place of the old one (and, after the
    delete, the kept one goes back to its name without a tag)."""
    fake_ark.serve_account(ID_1, 'Dummy 1 (merge)')
    fake_ark.serve_account(ID_2, 'Dummy 2 (keep)')
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert [save[1] for save in fake_ark.saves] == ['Dummy 2 (merge)', 'Dummy 1 (keep)', 'Dummy 1']


@pytest.mark.parametrize('section', ['Account Notes', 'Call Notes'])
def test_kept_account_without_a_notes_section_stops_before_changing_anything(fake_ark, reviews, msgboxes, section):
    """If the kept account's page lacks the notes section a block goes into, Merge stops before asking
    or changing anything."""
    fake_ark.serve_account(ID_1, 'Dummy 1', notes={section: None})
    fake_ark.serve_account(ID_2, 'Dummy 2', notes={'Account Notes': 'Dummy 2 an', 'Call Notes': 'Dummy 2 CN'})
    reviews.keep = 0
    with pytest.raises(RuntimeError, match=f'"Dummy 1" has no {section} on its page'):
        merge.main([LINK_1, LINK_2])
    assert msgboxes == [] and fake_ark.saves == []


def test_already_tagged_merge_account_isnt_saved_again(fake_ark, reviews):
    """A merge account already named "(merge)" by an earlier try has nothing to change: its window is
    closed with Save (Ark sends nothing, so Merge doesn't wait for an answer) and only the kept one is saved
    (tagged, then untagged after the delete)."""
    fake_ark.serve_account(ID_1, 'Dummy 1')
    fake_ark.serve_account(ID_2, 'Dummy 2 (merge)')
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert fake_ark.saves == [(ID_1, 'Dummy 1 (keep)', '', ''), (ID_1, 'Dummy 1', '', '')]
    assert fake_ark.editing is None


def test_waits_for_ark_to_store_each_save(merging):
    """Ark closes the window before storing the change, so Merge waits for its update answer for that
    record before going on: one answer per save, in order (both accounts, each record moved, then the kept
    account's "(keep)" taken off after the delete)."""
    merge.main([LINK_1, LINK_2])
    assert [json.loads(r.request.post_data)['record_id'] for r in merging.responses
            if r.url == fakes.UPDATE_URL] == [ID_2, ID_1, REQUEST, CALL, ID_1]
    assert merging.cancelled == [] and merging.pending is None


def test_save_that_never_finishes_stops_the_merge(merging):
    """If Ark sends no answer within 30 s of Save, Merge stops there (the kept account isn't touched)."""
    merging.save_stuck = True
    with pytest.raises(RuntimeError, match="didn't finish saving the record within 30 s of Save"):
        merge.main([LINK_1, LINK_2])
    assert merging.saves == [] and merging.moves == []


def test_save_ark_refuses_stops_the_merge(merging):
    """An error answer to an account's save stops Merge with its status."""
    merging.save_status = 500
    with pytest.raises(RuntimeError, match=re.escape('Ark refused to save the record (error 500)')):
        merge.main([LINK_1, LINK_2])
    assert merging.saves == []


def test_edit_window_that_never_fills_in_stops_without_saving(merging):
    """If the Edit Account window's name box never shows the account's name (its data didn't load), Merge
    stops after 30 s without saving, so empty notes are never written over real ones."""
    merging.edit_never_loads = True
    before = merging.waited_ms
    with pytest.raises(RuntimeError, match='didn\'t show the account\'s name "Dummy 2" within 30 s'):
        merge.main([LINK_1, LINK_2])
    assert merging.saves == [] and merging.waited_ms - before >= 30_000


def test_rename_ark_didnt_keep_stops_the_merge(merging):
    """If the reloaded account still shows its old name, Merge stops with an error saying so."""
    merging.save_ignored = True
    with pytest.raises(RuntimeError, match='Ark still shows the account as "Dummy 2" after renaming it to "Dummy 2 '):
        merge.main([LINK_1, LINK_2])


@pytest.mark.parametrize('boxes, error', [
    ({'name': 0}, 'shows 0 Account Name boxes instead of 1'),
    ({'name': 2}, 'shows 2 Account Name boxes instead of 1'),
    ({'Account Notes': 0}, 'shows 0 Account Notes boxes instead of 1'),
    ({'Call Notes': 2}, 'shows 2 Call Notes boxes instead of 1'),
])
def test_edit_window_not_as_expected_stops_without_saving(merging, boxes, error):
    """An Edit Account window without exactly one Account Name (or notes) box stops Merge before that
    account is saved: a bad name box before anything is saved, a bad notes box after only the merge
    account was renamed."""
    merging.edit_boxes = boxes
    with pytest.raises(RuntimeError, match=error):
        merge.main([LINK_1, LINK_2])
    assert merging.saves == ([] if 'name' in boxes else [(ID_2, 'Dummy 2 (merge)', 'Dummy 2 an', 'Dummy 2 CN')])
    assert merging.moves == []


def test_notes_tabs_are_clicked_by_their_exact_name(merging):
    """Other text in the Edit Account window holding a notes tab's name (e.g. the box's "Call Notes"
    label) isn't clicked instead of the tab: both note blocks are still saved."""
    merging.tab_text_elsewhere = True
    merge.main([LINK_1, LINK_2])
    assert merging.saves[1] == (ID_1, 'Dummy 1 (keep)', BLOCK + '\n\nDummy 1 an', CALL_BLOCK + '\n\nDummy 1 cn')


def test_notes_tabs_whose_text_isnt_exactly_their_name_are_still_found(merging):
    """If no text in the window is exactly a notes tab's name (say the tab shows a count too), the
    first text containing it is clicked, as before: both note blocks are still saved."""
    merging.tabs_not_exact = True
    merge.main([LINK_1, LINK_2])
    assert merging.saves[1] == (ID_1, 'Dummy 1 (keep)', BLOCK + '\n\nDummy 1 an', CALL_BLOCK + '\n\nDummy 1 cn')


def test_quick_reference_entries_are_clicked_by_their_exact_label(merging, msgboxes):
    """An entry before the real one whose text only contains a label (Ark gives expanded tables the
    same id) isn't the one clicked: the merge account's records are still listed and moved."""
    merging.pages[ID_2][0]['quick'].insert(0, ['TITLE REQUESTS\n\t\nCALLS & TEXTS\n\t\n(2)', ''])
    merge.main([LINK_1, LINK_2])
    assert merging.moves == [(REQUEST, ID_2, ID_1), (CALL, ID_2, ID_1)]
    assert _problems(msgboxes) == []


def test_check_saved_compares_the_notes(fake_ark):
    """_check_saved fails if the reloaded account's Account Notes or Call Notes aren't the ones saved
    (spacing aside)."""
    import ark_common
    fake_ark.serve_account(ID_1, 'Dummy 1', notes={'Account Notes': 'line one\nline two', 'Call Notes': 'cn'})
    with ark_common.ark_page(LINK_1) as page:
        merge._check_saved(page, LINK_1, 'Dummy 1', {'Account Notes': 'line one  \nline two', 'Call Notes': 'cn'})
        with pytest.raises(RuntimeError, match="doesn't show the new Account Notes"):
            merge._check_saved(page, LINK_1, 'Dummy 1', {'Account Notes': 'something else'})
        with pytest.raises(RuntimeError, match="doesn't show the new Call Notes"):
            merge._check_saved(page, LINK_1, 'Dummy 1', {'Call Notes': 'something else'})


def test_check_saved_compares_the_fields_filled_in(fake_ark):
    """_check_saved fails if the reloaded account doesn't show a field filled in (spacing and case aside)."""
    import ark_common
    fake_ark.serve_account(ID_1, 'Dummy 1', details={'Confirmed Phone Number': '406-555-0100'})
    with ark_common.ark_page(LINK_1) as page:
        merge._check_saved(page, LINK_1, 'Dummy 1', fills={'Confirmed Phone Number': ' 406-555-0100 '})
        with pytest.raises(RuntimeError, match='doesn\'t show Confirmed Phone Number "303-555-0100"'):
            merge._check_saved(page, LINK_1, 'Dummy 1', fills={'Confirmed Phone Number': '303-555-0100'})


def test_blank_fields_of_the_kept_account_are_filled_from_the_merge_account(fake_ark, reviews, msgboxes):
    """Dummy 1 (kept) has no address, phone or email; Dummy 2 has them all: the Yes/No box lists them, the
    kept account's save fills them in (checked after the reload), they're left out of the note (nothing to
    add) and the Done box says so."""
    fake_ark.serve_account(ID_1, 'Dummy 1')
    fake_ark.serve_account(ID_2, 'Dummy 2', details=MERGE_INFO)
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert fake_ark.detail_saves == [(ID_1, MERGE_INFO)]
    confirm, done = msgboxes[0][1], msgboxes[1][1]
    assert _section(confirm, 'Fill in "Dummy 1" blank fields from "Dummy 2":') == [
        'Mailing Street: 1 Main St', 'Mailing City: Billings', 'Mailing State: MT', 'Mailing Zip Code: 59101',
        'Confirmed Phone Number: (406) 555-0100', 'Confirmed Email Addresses: d2@example.com']
    assert 'Nothing to add to the Account Notes.' in confirm
    assert ('Filled in "Dummy 1 (keep)" blank Mailing Street, Mailing City, Mailing State, Mailing Zip Code, '
            'Confirmed Phone Number, Confirmed Email Addresses from the merge account.') in done
    assert fake_ark.deleted == [ID_2]


def test_a_field_filled_since_it_was_read_stops_before_saving_the_kept_account(fake_ark, reviews, msgboxes, monkeypatch):
    """If the kept account's phone box isn't blank any more when its edit window opens, Merge stops
    without saving it (only the merge account was renamed) rather than overwrite it."""
    fake_ark.serve_account(ID_1, 'Dummy 1', details={'Confirmed Phone Number': '303-555-0100'})
    fake_ark.serve_account(ID_2, 'Dummy 2', details=MERGE_INFO)
    real_read = merge._read_account

    def read_blank_phone(page, rid):
        """_read_account, as if Dummy 1's phone was blank when it was read."""
        account = real_read(page, rid)
        if rid == ID_1:
            account['details']['Confirmed Phone Number'] = ''
        return account
    monkeypatch.setattr(merge, '_read_account', read_blank_phone)
    reviews.keep = 0
    with pytest.raises(RuntimeError, match=r'"Dummy 1" now has a Confirmed Phone Number \("303-555-0100"\), so Merge '
                                           'stopped without saving it'):
        merge.main([LINK_1, LINK_2])
    assert [save[:2] for save in fake_ark.saves] == [(ID_2, 'Dummy 2 (merge)')] and fake_ark.detail_saves == []


def test_the_kept_account_keeps_its_tag_when_the_delete_is_declined(merging, msgboxes):
    """No to the delete: Dummy 1 stays "Dummy 1 (keep)" (it's only untagged once the merge account is gone)."""
    msgboxes.answers = [6, 7]
    merge.main([LINK_1, LINK_2])
    assert merging.records[('account', ID_1)] == 'Dummy 1 (keep)' and len(merging.saves) == 2


def test_a_rename_that_fails_after_the_delete_is_a_warning(merging, msgboxes, monkeypatch):
    """If taking "(keep)" off fails once the merge account is deleted, the last box says the delete went
    through and what to rename by hand (not an error box)."""
    def fails(page, url, keep_name):
        """untag_kept, failing like a save Ark doesn't answer."""
        raise RuntimeError(f"Ark didn't finish saving the record within 30 s of Save:\n{url}")
    monkeypatch.setattr(merge, 'untag_kept', fails)
    merge.main([LINK_1, LINK_2])
    assert merging.deleted == [ID_2]
    assert msgboxes[-1][1] == ('Deleted "Dummy 2 (merge)" from Ark, but couldn\'t rename "Dummy 1 (keep)" back to '
                               '"Dummy 1": Ark didn\'t finish saving the record within 30 s of Save.\n'
                               f'Rename it in Ark by hand:\n{LINK_1}')


# ─── Merge step: records that can't be moved ───────────────────────────────────

def _section(text, heading):
    """The "- " lines listed under heading in a box's text (up to the next blank line)."""
    lines = text.split('\n')
    if heading not in lines:
        return []
    after = lines[lines.index(heading) + 1:]
    return [line[2:] for line in after[:after.index('') if '' in after else None] if line.startswith('- ')]


def _problems(msgboxes):
    """The "Needs a look" lines of the Done box (a warning box when there are any)."""
    return _section(msgboxes[-1][1], 'Needs a look (not done):')


def test_a_record_ark_refuses_to_move_is_noted_and_the_rest_still_move(merging, msgboxes):
    """A record whose save Ark refuses is listed in the Done box (a warning) with the reason, and Ark's
    count of what's left on the merge account once, as why it wasn't deleted; the other records are still
    moved. It's tried once (not again on the next pass), and the merge account isn't deleted."""
    merging.refuse_moves = {REQUEST}
    merge.main([LINK_1, LINK_2])
    assert merging.moves == [(CALL, ID_2, ID_1)]
    url = fakes.RELATED_URL.format('/title-requests', REQUEST)
    assert _problems(msgboxes) == [f"The title request at {url} wasn't moved: Ark refused to save the record (error 403)"]
    assert _section(msgboxes[-1][1], '"Dummy 2 (merge)" wasn\'t deleted, because:') == [
        'Ark still counts 1 title request on it', 'the problems above need a look first']
    assert 'Moved to "Dummy 1 (keep)": 1 call / text.' in msgboxes[-1][1]
    assert sum(r.url == fakes.UPDATE_URL for r in merging.responses) == 4  # 2 accounts, the refused one once, the call
    assert merging.deleted == [] and len(msgboxes) == 2


def test_a_kept_account_name_shared_with_another_account_moves_nothing(merging, msgboxes):
    """If another account already has the kept account's new name, the search finds two: no record is
    moved, each is noted."""
    merging.serve_account('0' * 24, 'Dummy 1 (keep)')
    merge.main([LINK_1, LINK_2])
    assert merging.moves == []
    problems = _problems(msgboxes)
    assert sum('found 2 accounts with exactly that name instead of 1, so it was left alone' in p for p in problems) == 2
    assert 'No records were moved.' in msgboxes[-1][1]


def test_a_search_that_never_lists_the_account_is_noted(merging, msgboxes):
    """If the lookup never lists the kept account, the record is left alone after 30 s and noted."""
    merging.search_lag = True
    merge.main([LINK_1, LINK_2])
    assert merging.moves == []
    assert all('found 0 accounts with exactly that name' in p for p in _problems(msgboxes)[:2])


def test_a_pick_that_doesnt_take_is_noted(merging, msgboxes):
    """If picking the account doesn't change the lookup's tag, the record isn't saved and is noted."""
    merging.pick_ignored = True
    merge.main([LINK_1, LINK_2])
    assert merging.moves == [] and merging.responses[2:] == []
    assert 'Ark didn\'t take "Dummy 1 (keep)" as its Account, so it was left alone' in _problems(msgboxes)[0]


def test_a_record_without_an_account_lookup_is_noted(merging, msgboxes):
    """An edit window without exactly one Account lookup leaves the record alone and notes it."""
    merging.edit_boxes = {'account': 0}
    merge.main([LINK_1, LINK_2])
    assert merging.moves == []
    assert "shows 0 Account boxes instead of 1" in _problems(msgboxes)[0]


def test_records_the_drawer_lists_later_are_moved_in_another_pass(fake_ark, reviews, msgboxes):
    """If the side drawer lists only the first 2 of 3 records (however far it's scrolled), those are
    moved, the list is read again and the third (now listed) is moved too."""
    fake_ark.serve_account(ID_1, 'Dummy 1')
    fake_ark.serve_account(ID_2, 'Dummy 2', related={'Calls & Texts': [f'c{i}'.ljust(24, '0') for i in range(3)]})
    fake_ark.drawer_limit = 2
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert len(fake_ark.moves) == 3
    assert _problems(msgboxes) == [] and fake_ark.deleted == [ID_2]


def test_a_long_list_is_scrolled_until_every_record_shows(fake_ark, reviews, msgboxes):
    """A drawer that lists 2 more records each time it's scrolled is scrolled until it lists all 5, and
    all are moved in one pass."""
    ids = [f'c{i}'.ljust(24, '0') for i in range(5)]
    fake_ark.serve_account(ID_1, 'Dummy 1')
    fake_ark.serve_account(ID_2, 'Dummy 2', related={'Calls & Texts': ids})
    fake_ark.drawer_page = 2
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert [rid for rid, _, _ in fake_ark.moves] == ids


def test_records_never_listed_are_noted_and_block_the_delete(fake_ark, reviews, msgboxes, browser_tabs):
    """Records the drawer never lists are noted, nothing is moved, and the merge account isn't deleted
    (no question asked, no tabs opened): the box says why."""
    fake_ark.serve_account(ID_1, 'Dummy 1')
    fake_ark.serve_account(ID_2, 'Dummy 2', related={'Calls & Texts': [f'c{i}'.ljust(24, '0') for i in range(3)]})
    fake_ark.drawer_limit = 0
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert fake_ark.moves == [] and fake_ark.deleted == [] and browser_tabs == []
    assert _problems(msgboxes) == ['3 calls & texts counted on "Dummy 2 (merge)" but not listed, so not moved']
    assert _section(msgboxes[-1][1], '"Dummy 2 (merge)" wasn\'t deleted, because:') == [
        'Ark still counts 3 calls & texts on it', 'the problems above need a look first']


def test_a_record_already_on_another_account_is_left_alone(merging, msgboxes, monkeypatch):
    """A record whose Account isn't the merge account when its window opens (moved by someone else after
    the list was read) is left alone after 30 s and noted."""
    merging.serve_account('1' * 24, 'Someone Else')
    url = fakes.RELATED_URL.format('/title-requests', REQUEST)
    real_links = merge._related_links

    def listed_then_moved(page, account_url, label, part):
        """_related_links; the title request is listed, then moved to Someone Else."""
        links = real_links(page, account_url, label, part)
        if label == 'Title Requests':
            merging.owned[REQUEST] = ('Title Requests', '1' * 24)
        return links
    monkeypatch.setattr(merge, '_related_links', listed_then_moved)
    merge.main([LINK_1, LINK_2])
    assert merging.moves == [(CALL, ID_2, ID_1)]
    assert _problems(msgboxes)[0] == (f'The title request at {url} wasn\'t moved: its Account shows "Someone Else", '
                                      'not "Dummy 2 (merge)", so it was left alone')


# ─── Merge step: documents ─────────────────────────────────────────────────────

PDF, PNG = b'%PDF-1.7 fake', b'\x89PNG\r\n\x1a\nfake'  # the start of a PDF / PNG file


def _zip_bytes(tmp_path, inside):
    """A zip file's bytes holding one file at the path inside (e.g. 'word/document.xml')."""
    import zipfile
    path = tmp_path / 'z.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(inside, 'x')
    return path.read_bytes()


@pytest.fixture
def two_with_documents(fake_ark, reviews, msgboxes, folders):
    """Dummy 1 (kept) and Dummy 2 to merge into it, whose documents a test passes; [Folders] Merges is
    the test's own folder. Returns a function serving Dummy 2 with those documents."""
    reviews.keep = 0
    fake_ark.serve_account(ID_1, 'Dummy 1')

    def serve(*documents):
        """Serves Dummy 2 holding documents (see FakeArk.serve_account)."""
        fake_ark.serve_account(ID_2, 'Dummy 2', documents=documents)
    return serve


def test_documents_are_copied_with_names_and_extensions(fake_ark, two_with_documents, msgboxes, folders, tmp_path):
    """Each document is downloaded and uploaded to the kept account under a name Windows allows, ending
    in an extension: the listed name's own, else Ark's download name's, else the type its contents show.
    The folder is emptied, Dummy 2 keeps its copies, and with everything copied it's deleted."""
    docx = _zip_bytes(tmp_path, 'word/document.xml')
    two_with_documents(('Deed.PDF', 'Deed.PDF', PDF),                  # listed name has an extension
                       ('Mineral Lease', 'Mineral Lease.docx', docx),  # Ark's download name has one
                       ('Plat', 'download', PNG),                      # only the contents tell
                       ('Lease No.5 1/2/2020', 'file', PDF))           # "/" not allowed; ".5 1/2/2020" isn't an extension
    merge.main([LINK_1, LINK_2])

    assert [(rid, name, content) for rid, name, content in fake_ark.uploads] == [
        (ID_1, 'Deed.PDF', PDF), (ID_1, 'Mineral Lease.docx', docx), (ID_1, 'Plat.png', PNG),
        (ID_1, 'Lease No.5 1_2_2020.pdf', PDF)]
    assert list(folders['Merges'].iterdir()) == []
    assert len(fake_ark.documents[ID_2]) == 4
    assert 'Copied 4 documents to "Dummy 1 (keep)".' in msgboxes[1][1]
    assert 'Copy 4 documents to "Dummy 1 (keep)"' in msgboxes[0][1]
    assert fake_ark.deleted == [ID_2]


@pytest.mark.parametrize('inside, ext', [('word/document.xml', '.docx'), ('xl/workbook.xml', '.xlsx'),
                                         ('ppt/slides/s1.xml', '.pptx'), ('notes.txt', '.zip')])
def test_zip_based_files_are_told_apart(tmp_path, inside, ext):
    """A zip is a Word, Excel or PowerPoint file by the folder inside it, else a plain zip."""
    path = tmp_path / 'f'
    path.write_bytes(_zip_bytes(tmp_path, inside))
    assert merge._sniff_extension(str(path)) == ext


@pytest.mark.parametrize('content, ext', [
    (PDF, '.pdf'), (PNG, '.png'), (b'\xff\xd8\xff\xe0jpg', '.jpg'), (b'II*\x00tif', '.tif'), (b'MM\x00*tif', '.tif'),
    (b'GIF89a', '.gif'), (b'{\\rtf1', '.rtf'),
    (merge._OLE_MAGIC + 'WordDocument'.encode('utf-16-le'), '.doc'),
    (merge._OLE_MAGIC + 'Workbook'.encode('utf-16-le'), '.xls'),
    (merge._OLE_MAGIC + '__substg1.0_0037'.encode('utf-16-le'), '.msg'),
    (merge._OLE_MAGIC + b'other', ''), (b'just text', ''), (b'PK\x03\x04 broken zip', ''),
])
def test_file_types_from_their_contents(tmp_path, content, ext):
    """The extension a file's first bytes (or an old Office file's streams) show; '' if unknown."""
    path = tmp_path / 'f'
    path.write_bytes(content)
    assert merge._sniff_extension(str(path)) == ext


@pytest.mark.parametrize('listed, suggested, name', [
    ('Deed.pdf', 'other.docx', 'Deed.pdf'),            # the listed name's extension wins
    ('Deed', 'Deed.PDF', 'Deed.pdf'),                  # else the download name's, lowercased
    ('Smith v. Jones', 'Smith v. Jones.pdf', 'Smith v. Jones.pdf'),
    ('a<b>c:d"e|f?g*h', 'x.pdf', 'a_b_c_d_e_f_g_h.pdf'),
    ('Trailing dots. ', 'x.pdf', 'Trailing dots.pdf'),
    ('', 'From Ark.tif', 'From Ark.tif'),              # nothing listed: Ark's download name
    ('Scan', 'scan.12', 'Scan.pdf'),                   # "12" isn't an extension: the contents tell (a PDF)
])
def test_file_names(tmp_path, listed, suggested, name):
    """The name a document is saved under."""
    path = tmp_path / 'f'
    path.write_bytes(PDF)
    assert merge._file_name(listed, suggested, str(path)) == name


def test_a_document_of_unknown_type_isnt_copied_and_blocks_the_delete(fake_ark, two_with_documents, msgboxes,
                                                                     folders, browser_tabs):
    """A document whose name and contents don't tell its type isn't uploaded (and its download is
    removed); the box says so and why Dummy 2 wasn't deleted, without asking."""
    two_with_documents(('Notes', 'Notes', b'plain text'), 'Deed.pdf')
    merge.main([LINK_1, LINK_2])
    assert [name for _, name, _ in fake_ark.uploads] == ['Deed.pdf']
    assert list(folders['Merges'].iterdir()) == []
    assert _problems(msgboxes) == ['The document "Notes" wasn\'t downloaded: its file type couldn\'t be told from '
                                   'its name or its contents, so it wasn\'t copied']
    assert _section(msgboxes[-1][1], '"Dummy 2 (merge)" wasn\'t deleted, because:') == [
        '2 documents on it, 1 copied', 'the problems above need a look first']
    assert fake_ark.deleted == [] and browser_tabs == [] and len(msgboxes) == 2


def test_a_document_failing_with_no_message_is_noted(fake_ark, two_with_documents, msgboxes, monkeypatch):
    """A document whose download fails with an error that has no message is noted under the error's
    kind, and the other documents are still copied (the run doesn't stop)."""
    real_file_name = merge._file_name

    def no_message_for_a(listed, suggested, path):
        """merge._file_name, but A.pdf fails with a bare OSError."""
        if listed == 'A.pdf':
            raise OSError()
        return real_file_name(listed, suggested, path)
    monkeypatch.setattr(merge, '_file_name', no_message_for_a)
    two_with_documents('A.pdf', 'B.pdf')
    merge.main([LINK_1, LINK_2])
    assert [name for _, name, _ in fake_ark.uploads] == ['B.pdf']
    assert _problems(msgboxes) == ['The document "A.pdf" wasn\'t downloaded: OSError']


def test_the_upload_check_stops_after_30_s_even_when_each_look_is_slow(fake_ark, two_with_documents, msgboxes,
                                                                       monkeypatch):
    """Waiting for the kept account to list an upload counts the time each look at its Documents takes,
    not just the pauses between looks: with every look taking 10 s, it gives up after about 30 s."""
    clock = types.SimpleNamespace(monotonic=lambda: fake_ark.waited_ms / 1000)  # time passes as the fake page waits
    monkeypatch.setattr(merge, 'time', clock, raising=False)
    real_names, looks = merge._document_names, []

    def slow_look(page, url, *args, **kwargs):
        """merge._document_names, taking 10 s on the kept account."""
        if url == LINK_1:
            looks.append(url)
            fake_ark.waited_ms += 10_000
        return real_names(page, url, *args, **kwargs)
    monkeypatch.setattr(merge, '_document_names', slow_look)
    fake_ark.listed_as = lambda name: None
    two_with_documents('Deed.pdf')
    merge.main([LINK_1, LINK_2])
    assert 2 <= len(looks) <= 5  # the look before uploading, then about 3 (not 31) while waiting
    assert 'doesn\'t show on the kept account after uploading' in _problems(msgboxes)[0]


def test_a_long_document_list_is_scrolled(fake_ark, two_with_documents, msgboxes):
    """A Documents drawer that lists one more per scroll is scrolled until it lists all 3."""
    fake_ark.drawer_page = 1
    two_with_documents('A.pdf', 'B.pdf', 'C.pdf')
    merge.main([LINK_1, LINK_2])
    assert [name for _, name, _ in fake_ark.uploads] == ['A.pdf', 'B.pdf', 'C.pdf']
    assert fake_ark.deleted == [ID_2]


def test_documents_counted_but_not_listed_are_noted(fake_ark, two_with_documents, msgboxes):
    """Documents the drawer never lists (however far it's scrolled) aren't copied; that's noted and
    blocks the delete."""
    fake_ark.drawer_limit = 1
    two_with_documents('A.pdf', 'B.pdf')
    merge.main([LINK_1, LINK_2])
    assert [name for _, name, _ in fake_ark.uploads] == ['A.pdf']
    assert _problems(msgboxes) == ['1 document counted on the merge account but not listed, so not copied']
    assert fake_ark.deleted == []


def test_an_upload_listed_without_its_extension_counts_as_copied(fake_ark, two_with_documents, msgboxes, folders):
    """Ark may list an upload without its extension; it still counts as copied."""
    fake_ark.listed_as = lambda name: name.rsplit('.', 1)[0]
    two_with_documents('Deed.pdf')
    merge.main([LINK_1, LINK_2])
    assert _problems(msgboxes) == [] and list(folders['Merges'].iterdir()) == []
    assert fake_ark.deleted == [ID_2]


def test_an_upload_ark_doesnt_list_is_kept_in_the_folder(fake_ark, two_with_documents, msgboxes, folders):
    """A document Ark doesn't list on the kept account after uploading stays in the folder and is noted."""
    fake_ark.listed_as = lambda name: None
    two_with_documents('Deed.pdf')
    merge.main([LINK_1, LINK_2])
    assert [p.name for p in folders['Merges'].iterdir()] == ['Deed.pdf']
    assert _problems(msgboxes) == [f'The document "Deed.pdf" doesn\'t show on the kept account after uploading; '
                                   f'it was kept in {folders["Merges"]}']
    assert fake_ark.deleted == []


# ─── Merge step: land holdings ─────────────────────────────────────────────────

JANE = {'Signer': 'Jane Doe', 'Last Name': 'Doe', 'Capacity': 'Trustee'}  # a signer
BO = {'Signer': 'Bo Roe', 'Last Name': 'Roe', 'Capacity': ''}  # another


def _two(holdings_1=(), holdings_2=()):
    """ACCOUNTS-like Dummy 1 and Dummy 2 holding these land holdings (_holding dicts)."""
    return [_account('Dummy 1', LINK_1, holdings=list(holdings_1)), _account('Dummy 2', LINK_2, holdings=list(holdings_2))]


def test_clean_signers():
    """Parts trimmed, signers with nothing filled dropped, at most 9 kept."""
    assert merge.clean_signers([{'Signer': ' Jane Doe ', 'Last Name': 'Doe', 'Capacity': None},
                                {'Signer': ' ', 'Last Name': '', 'Capacity': ''}, {'Last Name': 'Roe'}]) == [
        {'Signer': 'Jane Doe', 'Last Name': 'Doe', 'Capacity': ''}, {'Signer': '', 'Last Name': 'Roe', 'Capacity': ''}]
    assert len(merge.clean_signers([{'Signer': str(n)} for n in range(12)])) == 9


def test_holding_options_offer_what_either_account_has():
    """Legal Entities, signer lists (labelled with the land holding they're from) and capacities from
    both accounts' land holdings, each once in the order found; blanks left out."""
    accounts = _two([_holding('A', legal='Dummy 1', signers=[JANE]), _holding('B', legal='', signers=[])],
                    [_holding('C', legal='Dummy 2 Trust', signers=[JANE, BO]), _holding('D', legal='Dummy 1',
                                                                                  signers=[dict(JANE, Signer='jane  doe')])])
    entities, sets, capacities = merge.holding_options(accounts)
    assert entities == ['Dummy 1', 'Dummy 2 Trust']
    assert sets == [('Jane Doe (Last Name: Doe, Capacity: Trustee) (from A)', [JANE]),
                    ('Jane Doe (Last Name: Doe, Capacity: Trustee); Bo Roe (Last Name: Roe) (from C)', [JANE, BO])]
    assert capacities == ['Trustee']


def test_holding_options_list_a_capacity_once_when_one_land_holding_has_it_twice():
    """Two signers of one land holding with the same capacity give it once in the capacities offered."""
    accounts = _two([_holding('A', signers=[JANE, dict(BO, Capacity='Trustee'), dict(BO, Signer='Al Roe',
                                                                                   Capacity='Heir')])])
    assert merge.holding_options(accounts)[2] == ['Trustee', 'Heir']


def test_holding_plans_move_the_merge_accounts_and_change_what_was_picked():
    """Every merge account land holding moves; the kept account's are planned only if their Legal Entity
    or signers change (case and spacing aside); unchanged values are None."""
    a, b = _holding('A', legal='Dummy 1', signers=[JANE]), _holding('B', legal='Dummy 1')
    c, d = _holding('C', legal='Dummy 2'), _holding('D', legal='Dummy 2', signers=[BO])
    accounts = _two([a, b], [c, d])
    choices = merge.holding_choices(accounts)
    choices[a['url']] = {'Legal Entity': ' dummy  1 ', 'signers': [dict(JANE, Signer='JANE DOE')]}  # same, typed differently
    choices[b['url']] = {'Legal Entity': 'Dummy 1 Trust', 'signers': [JANE]}
    choices[d['url']] = {'Legal Entity': 'Dummy 2', 'signers': []}
    plans = merge.holding_plans(accounts, 0, choices)
    assert plans == [
        {'url': b['url'], 'name': 'B', 'move': False, 'owner': 0, 'legal_entity': 'Dummy 1 Trust', 'signers': [JANE]},
        {'url': c['url'], 'name': 'C', 'move': True, 'owner': 1, 'legal_entity': None, 'signers': None},
        {'url': d['url'], 'name': 'D', 'move': True, 'owner': 1, 'legal_entity': None, 'signers': []}]
    assert merge._plan_text(plans[0], 'Dummy 1 (keep)') == ('B: Legal Entity "Dummy 1 Trust", signers Jane Doe '
                                                            '(Last Name: Doe, Capacity: Trustee)')
    assert merge._plan_text(plans[2], 'Dummy 1 (keep)') == 'D: move to "Dummy 1 (keep)", signers none'
    assert merge._plan_text(dict(plans[1], legal_entity=''), 'K') == 'C: move to "K", Legal Entity blank'


def _serve_holdings(fake_ark):
    """Dummy 1 with land holding A (Legal Entity Dummy 1, signer Jane) and Dummy 2 with B (Dummy 2, no
    signers) and C (Dummy 2, signers Bo and Jane)."""
    fake_ark.serve_account(ID_1, 'Dummy 1', holdings=[LH_A])
    fake_ark.serve_account(ID_2, 'Dummy 2', holdings=[LH_B, LH_C])
    fake_ark.serve_holding(LH_A, 'A', fields={'Legal Entity': 'Dummy 1'}, signers=[('Jane Doe', 'Doe', 'Trustee')])
    fake_ark.serve_holding(LH_B, 'B', fields={'Legal Entity': 'Dummy 2'})
    fake_ark.serve_holding(LH_C, 'C', fields={'Legal Entity': 'Dummy 2'},
                           signers=[('Bo Roe', 'Roe', ''), ('Jane Doe', 'Doe', 'Trustee')])


def test_land_holdings_move_and_take_the_legal_entity_and_signers_picked(fake_ark, reviews, holdings, msgboxes):
    """Keep Dummy 1: the land holdings window gets both accounts; B and C move to "Dummy 1 (keep)", B takes
    a typed Legal Entity and Jane as signer, C keeps its own, and A (kept) drops its signer. The Yes/No box
    lists each, every change is saved and checked, and Dummy 2 (merge), now empty, is deleted."""
    _serve_holdings(fake_ark)
    reviews.keep = 0

    def choose(accounts, keep):
        """B: typed Legal Entity, Jane; A: no signers; C as it is."""
        choices = merge.holding_choices(accounts)
        choices[HOLDING_URL.format(LH_B)] = {'Legal Entity': 'Dummy 1 Family Trust', 'signers': [JANE]}
        choices[HOLDING_URL.format(LH_A)]['signers'] = []
        return choices
    holdings.choose = choose

    merge.main([LINK_1, LINK_2])

    [(accounts, keep)] = holdings
    assert [a['name'] for a in accounts] == ['Dummy 1', 'Dummy 2'] and keep == 0
    confirm = msgboxes[0][1]
    assert _section(confirm, 'Land holdings:') == [
        'A: signers none',
        'B: move to "Dummy 1 (keep)", Legal Entity "Dummy 1 Family Trust", signers Jane Doe (Last Name: Doe, '
        'Capacity: Trustee)',
        'C: move to "Dummy 1 (keep)"']
    saved = {rid: (owner, fields) for rid, owner, fields in fake_ark.holding_saves}
    assert list(saved) == [LH_A, LH_B, LH_C]
    assert saved[LH_A][0] == ID_1 and saved[LH_A][1]['Signer 1'] == '' and saved[LH_A][1]['Signer 1 Capacity'] == ''
    assert saved[LH_B][0] == ID_1 and saved[LH_B][1]['Legal Entity'] == 'Dummy 1 Family Trust'
    assert (saved[LH_B][1]['Signer 1'], saved[LH_B][1]['Signer 1 Last Name'], saved[LH_B][1]['Signer 1 Capacity']) == \
        ('Jane Doe', 'Doe', 'Trustee')
    assert saved[LH_C] == (ID_1, {**saved[LH_C][1], 'Signer 1': 'Bo Roe', 'Signer 2': 'Jane Doe'})
    assert 'Changed 3 land holdings (2 moved to "Dummy 1 (keep)").' in msgboxes[1][1]
    assert fake_ark.deleted == [ID_2]


def test_signers_past_the_new_last_one_are_blanked(fake_ark, reviews, holdings, msgboxes):
    """C goes from Bo and Jane to just Jane: Signer 1 becomes Jane and Signer 2 is emptied."""
    _serve_holdings(fake_ark)
    reviews.keep = 0

    def choose(accounts, keep):
        """C: Jane only."""
        choices = merge.holding_choices(accounts)
        choices[HOLDING_URL.format(LH_C)]['signers'] = [JANE]
        return choices
    holdings.choose = choose
    merge.main([LINK_1, LINK_2])
    [fields] = [f for rid, _, f in fake_ark.holding_saves if rid == LH_C]
    assert [fields[f'Signer {n}{s}'] for n in (1, 2) for s in ('', ' Last Name', ' Capacity')] == \
        ['Jane Doe', 'Doe', 'Trustee', '', '', '']


AL = {'Signer': 'Al Roe', 'Last Name': '', 'Capacity': 'Heir'}  # a third signer (Ark has Capacity, no Last Name, for Signer 3)
CY = {'Signer': 'Cy Poe', 'Last Name': '', 'Capacity': ''}  # a fourth (Ark has only the name for Signer 4-9)


def _choose_signers(name, signers):
    """A holdings.choose that gives land holding name (LH_A / LH_B / LH_C) these signers, the rest as they are."""
    def choose(accounts, keep):
        """name: signers; the rest as they are."""
        choices = merge.holding_choices(accounts)
        choices[HOLDING_URL.format(name)]['signers'] = signers
        return choices
    return choose


def test_the_signer_tab_is_found_when_its_text_isnt_exactly_its_name(fake_ark, reviews, holdings, msgboxes):
    """No text in Ark's Edit Land Holding window is exactly "Signer Information" (the dummies' run on
    2026-11-11 stopped every signer change with "0 Signer 1 boxes"), so the first text containing it is
    clicked, as for the notes tabs, and the new signers are saved."""
    _serve_holdings(fake_ark)
    fake_ark.tabs_not_exact = True
    reviews.keep = 0
    holdings.choose = _choose_signers(LH_C, [JANE])
    merge.main([LINK_1, LINK_2])
    assert _problems(msgboxes) == []
    [fields] = [f for rid, _, f in fake_ark.holding_saves if rid == LH_C]
    assert (fields['Signer 1'], fields['Signer 2']) == ('Jane Doe', '')


def test_signers_fill_only_the_boxes_ark_has(fake_ark, reviews, holdings, msgboxes):
    """Ark has Last Name boxes only for Signer 1-2 and Capacity only for Signer 1-3: four signers on B
    are saved without looking for the others, and the merge account is deleted."""
    _serve_holdings(fake_ark)
    reviews.keep = 0
    holdings.choose = _choose_signers(LH_B, [JANE, BO, AL, CY])
    merge.main([LINK_1, LINK_2])
    assert _problems(msgboxes) == []
    [fields] = [f for rid, _, f in fake_ark.holding_saves if rid == LH_B]
    assert {label: fields[label] for label in ('Signer 3', 'Signer 3 Capacity', 'Signer 4', 'Signer 5')} == {
        'Signer 3': 'Al Roe', 'Signer 3 Capacity': 'Heir', 'Signer 4': 'Cy Poe', 'Signer 5': ''}
    assert 'Signer 3 Last Name' not in fields and 'Signer 4 Capacity' not in fields
    assert fake_ark.deleted == [ID_2]


def test_missing_signer_boxes():
    """The Signer N parts filled in that Ark has no box for: Last Name past Signer 2, Capacity past Signer 3."""
    assert merge.missing_signer_boxes([JANE, BO, AL, CY]) == []
    assert merge.missing_signer_boxes([JANE, BO, dict(AL, **{'Last Name': 'Roe'}), dict(CY, Capacity='Heir')]) == [
        'Signer 3 Last Name', 'Signer 4 Capacity']


def test_a_signer_part_ark_has_no_box_for_stops_that_land_holding(fake_ark, reviews, holdings, msgboxes):
    """A third signer with a Last Name (Ark has no Signer 3 Last Name box) isn't dropped silently: B isn't
    changed and is noted, C still moves, and the merge account isn't deleted."""
    _serve_holdings(fake_ark)
    reviews.keep = 0
    holdings.choose = _choose_signers(LH_B, [JANE, BO, dict(AL, **{'Last Name': 'Roe'})])
    merge.main([LINK_1, LINK_2])
    assert [rid for rid, _, _ in fake_ark.holding_saves] == [LH_C]
    assert _problems(msgboxes)[0] == (f'The land holding "B" at {HOLDING_URL.format(LH_B)} wasn\'t changed: Ark has '
                                      'no Signer 3 Last Name box, so Merge stopped without saving this record.')
    assert fake_ark.deleted == []


def test_closing_the_land_holdings_window_changes_nothing(fake_ark, reviews, holdings, msgboxes):
    """Closing the land holdings window ends the run before the Yes/No box: nothing is changed."""
    _serve_holdings(fake_ark)
    reviews.keep = 0
    holdings.choose = lambda accounts, keep: None
    merge.main([LINK_1, LINK_2])
    assert msgboxes == [] and fake_ark.saves == [] and fake_ark.holding_saves == []


def test_no_land_holdings_window_without_land_holdings(merging, holdings):
    """Accounts without land holdings skip the land holdings window."""
    merge.main([LINK_1, LINK_2])
    assert holdings == [] and merging.holding_saves == []


def test_a_land_holding_that_fails_is_noted_and_the_rest_go_on(fake_ark, reviews, holdings, msgboxes):
    """A land holding whose edit window lacks a signer box isn't saved and is noted; the others are
    still changed, and the merge account isn't deleted."""
    _serve_holdings(fake_ark)
    reviews.keep = 0

    def choose(accounts, keep):
        """New signers on B (its window lacks Signer 1's box); C moves as it is."""
        choices = merge.holding_choices(accounts)
        choices[HOLDING_URL.format(LH_B)]['signers'] = [JANE]
        return choices
    holdings.choose = choose
    real = merge._update_holding

    def b_breaks(page, plan, owner_name, keep_name):
        """_update_holding, with B's window missing its Signer 1 box."""
        fake_ark.edit_boxes = {'Signer 1': 0} if plan['name'] == 'B' else {}
        return real(page, plan, owner_name, keep_name)
    import unittest.mock
    with unittest.mock.patch.object(merge, '_update_holding', b_breaks):
        merge.main([LINK_1, LINK_2])
    assert [rid for rid, _, _ in fake_ark.holding_saves] == [LH_C]
    assert _problems(msgboxes)[0] == (f'The land holding "B" at {HOLDING_URL.format(LH_B)} wasn\'t changed: Ark\'s edit '
                                      'window shows 0 Signer 1 boxes instead of 1, so Merge stopped without saving this record.')
    assert fake_ark.deleted == []


def test_a_land_holding_change_ark_doesnt_show_is_noted(fake_ark, reviews, holdings, msgboxes, monkeypatch):
    """If the reloaded land holding doesn't show the new Legal Entity, it's noted."""
    _serve_holdings(fake_ark)
    reviews.keep = 0

    def choose(accounts, keep):
        """A: a new Legal Entity."""
        choices = merge.holding_choices(accounts)
        choices[HOLDING_URL.format(LH_A)]['Legal Entity'] = 'New LLC'
        return choices
    holdings.choose = choose
    real_read = merge._read_holding
    monkeypatch.setattr(merge, '_read_holding', lambda page, url: {**real_read(page, url), 'fields': {
        **real_read(page, url)['fields'], 'Legal Entity': 'Old'}} if url == HOLDING_URL.format(LH_A) and
        fake_ark.holding_saves else real_read(page, url))
    merge.main([LINK_1, LINK_2])
    assert any('Ark doesn\'t show the new Legal Entity "New LLC" after saving' in p for p in _problems(msgboxes))


def test_land_holdings_the_page_doesnt_link_are_read_from_the_drawer(fake_ark, reviews):
    """When the Quick Reference counts more land holdings than the page links, the Land Holdings side
    drawer is read for the rest."""
    counts = {**dict.fromkeys(merge.CHECKED, 0), 'Land Holdings': 2}
    fake_ark.serve_account(ID_1, 'Dummy 1', counts=counts, holdings=[LH_A])
    fake_ark.owned[LH_B] = ('Land Holdings', ID_1)  # in the drawer, not linked on the page
    fake_ark.serve_account(ID_2, 'Dummy 2')
    fake_ark.serve_holding(LH_A, 'A')
    fake_ark.serve_holding(LH_B, 'B')
    first, _ = merge.main([LINK_1, LINK_2])
    assert [h['name'] for h in first['holdings']] == ['A', 'B'] and first['holdings_missing'] == 0


def test_parent_account_goes_in_the_note_when_it_differs():
    """The merge account's parent is listed like its email: only when it has one and it differs."""
    def with_parent(parent):
        """An account whose parent is parent."""
        return _account('X', LINK_1, details={'Parent Account': parent})
    assert merge.merge_differences(with_parent('Keep Parent'), with_parent('Other Parent')) == [
        'Parent Account: Other Parent']
    assert merge.merge_differences(with_parent('Same  parent'), with_parent('same parent')) == []
    assert merge.merge_differences(with_parent('Keep Parent'), with_parent('')) == []
    assert merge.merge_differences(with_parent(None), with_parent('New Parent')) == ['Parent Account: New Parent']


# ─── Land holdings window ──────────────────────────────────────────────────────

HOLDING_ACCOUNTS = _two([_holding('A', legal='Dummy 1', signers=[JANE])],
                        [_holding('B', legal='Dummy 2', signers=[]), _holding('C', legal='Dummy 2', signers=[BO, JANE])])


@pytest.fixture
def holdings_window(tk_root):
    """The land holdings window for HOLDING_ACCOUNTS (Dummy 1 kept), built hidden and never run."""
    root = merge._holdings_window(HOLDING_ACCOUNTS, 0, master=tk_root)
    root.withdraw()
    root.update_idletasks()
    yield root
    if root.winfo_exists():
        root.destroy()


def _url(name):
    """A test land holding's url."""
    return HOLDING_URL.format(name)


def test_holdings_window_starts_from_what_each_land_holding_has(holdings_window):
    """Each land holding of both accounts gets boxes holding its Legal Entity and signers now (one blank
    row when it has none); the merge account is said to move; Continue answers with them."""
    w = holdings_window
    assert w.title() == 'Merge Accounts - Land Holdings'
    assert list(w.editors) == [_url('A'), _url('B'), _url('C')]
    assert w.editors[_url('A')]['entity'].get() == 'Dummy 1'
    assert w.editors[_url('C')]['signers'].get() == [BO, JANE]
    assert len(w.editors[_url('B')]['signers'].rows) == 1
    texts = [lab.cget('text') for lab in _labels(w)]
    assert 'Account 1: Dummy 1 (kept)' in texts
    assert 'Account 2: Dummy 2 (its land holdings move to the kept account)' in texts
    [cont] = [b for b in _buttons(w) if b.cget('text') == 'Continue']
    cont.invoke()
    assert w.choices == merge.holding_choices(HOLDING_ACCOUNTS)


def test_holdings_window_takes_typed_values(holdings_window):
    """A Legal Entity and signers typed in come back trimmed; a signer row emptied is left out."""
    w = holdings_window
    w.editors[_url('B')]['entity'].set('  My Own LLC ')
    rows = w.editors[_url('C')]['signers']
    rows.rows[0][0].set('')
    rows.rows[0][1].set('')
    [cont] = [b for b in _buttons(w) if b.cget('text') == 'Continue']
    cont.invoke()
    assert w.choices[_url('B')]['Legal Entity'] == 'My Own LLC'
    assert w.choices[_url('C')]['signers'] == [JANE]


def test_holdings_window_copies_signers_from_another_land_holding(holdings_window):
    """Picking a signer list in a land holding's "Copy signers from" fills its rows (adding rows as
    needed); "No signers" empties them."""
    w = holdings_window
    copy = w.editors[_url('B')]['copy']
    label = [v for v in copy.cget('values') if v.endswith('(from C)')][0]
    copy.set(label)
    copy.event_generate('<<ComboboxSelected>>')
    assert w.editors[_url('B')]['signers'].get() == [BO, JANE]
    copy.set('No signers')
    copy.event_generate('<<ComboboxSelected>>')
    assert w.editors[_url('B')]['signers'].get() == []


def test_holdings_window_applies_one_choice_to_every_land_holding(holdings_window):
    """The Set every row puts its Legal Entity and signer list into every land holding."""
    w = holdings_window
    w.all_entity.set('Dummy 1')
    w.all_signers.set(merge.holding_options(HOLDING_ACCOUNTS)[1][0][0])  # the first signer list: Jane (from A)
    w.apply_all()
    assert {url: (e['entity'].get(), e['signers'].get()) for url, e in w.editors.items()} == {
        _url(n): ('Dummy 1', [JANE]) for n in 'ABC'}


def test_holdings_window_add_signer_stops_at_nine(holdings_window):
    """Add signer adds a row, up to Signer 9."""
    rows = holdings_window.editors[_url('A')]['signers']
    [add] = [b for b in _buttons(holdings_window) if b.cget('text') == 'Add signer'][:1]
    for _ in range(12):
        add.invoke()
    assert len(rows.rows) == 9


def test_holdings_window_greys_out_boxes_ark_doesnt_have(holdings_window):
    """Ark has Last Name boxes only for Signer 1-2 and Capacity only for Signer 1-3, so past those the
    window's Last Name / Capacity boxes are disabled."""
    rows = holdings_window.editors[_url('A')]['signers']
    while len(rows.rows) < 4:
        rows.add()
    assert [[str(box.cget('state')) for box in boxes[1:]] for boxes in rows.boxes] == [
        ['normal', 'normal'], ['normal', 'normal'], ['disabled', 'normal'], ['disabled', 'disabled']]


def test_holdings_window_cancel_answers_none(holdings_window):
    """Cancel closes the window with no answer."""
    [cancel] = [b for b in _buttons(holdings_window) if b.cget('text') == 'Cancel']
    cancel.invoke()
    assert holdings_window.choices is None and not holdings_window.winfo_exists()


# ─── Merge step: deleting the merge account ────────────────────────────────────

def test_answering_no_to_the_delete_keeps_the_merge_account(merging, msgboxes, browser_tabs):
    """No to the delete question leaves Dummy 2 (merge) in Ark; the accounts were opened for review."""
    msgboxes.answers = [6, 7]
    merge.main([LINK_1, LINK_2])
    assert merging.deleted == [] and browser_tabs == [LINK_1, LINK_2] and len(msgboxes) == 2
    assert merging.records[('account', ID_2)] == 'Dummy 2 (merge)'


def test_a_stale_land_holdings_count_doesnt_block_the_delete(fake_ark, reviews, holdings, msgboxes):
    """Ark's Land Holdings count can stay at the old number for a while after land holdings move: the
    merge account still counts 2 but its Land Holdings drawer lists none, so it's deleted (checked after
    the merge step and again right before deleting)."""
    _serve_holdings(fake_ark)
    fake_ark.stale_counts = {'Land Holdings'}
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert fake_ark.owned[LH_B][1] == ID_1 and fake_ark.owned[LH_C][1] == ID_1
    assert _problems(msgboxes) == [] and fake_ark.deleted == [ID_2]


def test_a_land_holding_left_on_the_merge_account_blocks_the_delete(fake_ark, reviews, msgboxes, browser_tabs):
    """A merge account land holding that couldn't be moved (its edit window has no Account lookup) is
    noted, and the merge account isn't deleted: the box says why and asks nothing."""
    fake_ark.serve_account(ID_1, 'Dummy 1')
    fake_ark.serve_account(ID_2, 'Dummy 2', holdings=[LH_A])
    fake_ark.serve_holding(LH_A, 'Holding A')
    fake_ark.edit_boxes = {'account': 0}
    reviews.keep = 0
    merge.main([LINK_1, LINK_2])
    assert fake_ark.deleted == [] and browser_tabs == [] and len(msgboxes) == 2
    assert _problems(msgboxes) == [f'The land holding "Holding A" at {HOLDING_URL.format(LH_A)} wasn\'t changed: '
                                   "Ark's edit window shows 0 Account boxes instead of 1, so Merge stopped without "
                                   'saving this record.']
    assert _section(msgboxes[-1][1], '"Dummy 2 (merge)" wasn\'t deleted, because:') == [
        'Ark still counts 1 land holding on it', 'the problems above need a look first']
    assert msgboxes[-1][1].endswith("Delete it in Ark by hand once that's sorted out.")


def _delete(fake_ark, name='Dummy 2 (merge)'):
    """Runs merge.delete_account on Dummy 2 as name, in a fake browser."""
    import ark_common
    with ark_common.ark_page(LINK_2) as page:
        merge.delete_account(page, LINK_2, name)


def test_delete_checks_the_account_again_first(fake_ark):
    """Right before deleting, the account must still have the merge name and nothing left to move;
    otherwise nothing is deleted."""
    fake_ark.serve_account(ID_2, 'Dummy 2 (merge)', related={'Contacts': [CONTACT]})
    with pytest.raises(RuntimeError, match=re.escape('Merge didn\'t delete "Dummy 2 (merge)": Ark still counts 1 contact on it.')):
        _delete(fake_ark)
    with pytest.raises(RuntimeError, match=re.escape('now named "Dummy 2 (merge)", not "Dummy 2 (gone)"')):
        _delete(fake_ark, 'Dummy 2 (gone)')
    assert fake_ark.deleted == [] and fake_ark.confirming is None


@pytest.mark.parametrize('setting, error', [
    ({'confirm_buttons': 0}, "confirmation box shows 0 Delete buttons instead of 1"),
    ({'confirm_buttons': 2}, "confirmation box shows 2 Delete buttons instead of 1"),
    ({'delete_status': 500}, re.escape('Ark refused to delete "Dummy 2 (merge)" (error 500)')),
    ({'delete_silent': True}, "didn't answer the delete within 30 s"),
    ({'delete_ignored': True}, re.escape('Ark still shows "Dummy 2 (merge)" after deleting it')),
])
def test_a_delete_that_doesnt_go_through_stops_with_an_error(fake_ark, setting, error):
    """A confirmation box without exactly one Delete button deletes nothing; a delete Ark refuses,
    doesn't answer, or doesn't carry out stops with an error saying so."""
    fake_ark.serve_account(ID_2, 'Dummy 2 (merge)')
    for key, value in setting.items():
        setattr(fake_ark, key, value)
    with pytest.raises(RuntimeError, match=error):
        _delete(fake_ark)
    assert fake_ark.deleted == []


def test_delete_isnt_cut_short_by_an_earlier_answer_naming_the_account(fake_ark):
    """If a call that only reads the account answers before the delete itself, Merge doesn't leave the
    page (which would cancel the delete still on its way): it checks for Account Not Found in another
    tab, which it closes."""
    fake_ark.serve_account(ID_2, 'Dummy 2 (merge)')
    fake_ark.delete_slow = True
    _delete(fake_ark)
    assert fake_ark.deleted == [ID_2] and fake_ark.cancelled_deletes == []
    assert fake_ark.pages_closed == 1


def test_delete_waits_for_arks_answer_then_checks_the_account_is_gone(fake_ark):
    """The delete sends one call naming the account and then the account page shows Account Not Found."""
    fake_ark.serve_account(ID_2, 'Dummy 2 (merge)')
    _delete(fake_ark)
    assert fake_ark.deleted == [ID_2]
    assert [json.loads(r.request.post_data)['record_id'] for r in fake_ark.responses] == [ID_2]
    assert fake_ark.visited[-1] == LINK_2


# ─── As the button runs it ─────────────────────────────────────────────────────

def test_error_box_and_log_in_appdata(fake_ark, msgboxes, monkeypatch, tmp_path):
    """Run as the button runs it, a failure shows a Merge error box naming the error and
    merge_error.log in the app's settings folder (Merge has no Desktop folder)."""
    import runpy
    import ark_common
    from conftest import REPO
    monkeypatch.setattr(ark_common, '_APP_DIR', str(tmp_path))
    monkeypatch.setattr('sys.argv', ['merge.py', LINK_1, LINK_2])  # neither account is served

    with pytest.raises(RuntimeError):
        runpy.run_path(str(REPO / 'merge.py'), run_name='__main__')
    [(title, text)] = msgboxes
    assert title == 'Merge' and text.startswith('Merge failed:\nArk shows "Account Not Found"')
    log = tmp_path / 'merge_error.log'
    assert text.endswith(f'Details: {log}') and 'Traceback' in log.read_text(encoding='utf-8')
