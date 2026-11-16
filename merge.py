"""Merge accounts, launched by the "Merge" button (column 3) once its link window (merge.cpp) has
the two Ark accounts to merge: `py merge.py <record id or link> <record id or link>` (order doesn't
matter).

Opens each account's page in Ark with the saved login (ark_common.ark_page, logging in if Ark asks)
and reads its name (page title), its DETAILS (Created Date, Account Disposition, mailing address,
confirmed phone and email), what it holds (the Quick Reference counts in CHECKED: Documents,
Contacts, Offers, ...), its NOTES (Account Notes, Call Notes) and the land holdings listed on it.
Then opens each land holding and reads its HOLDING_FIELDS (Legal Entity, Section Name, Title
Information) and signers. Shows everything side by side in a review window (_show_review). An item a
page doesn't show (other kinds of account lack Offers, Title Requests, Land Holdings) is shown as not
on the page.

In the window the user picks the account to keep (the survivor) or closes it (nothing changes). If
either account has land holdings, a second window (_show_holdings) lists every land holding of both,
where the user sets each one's Legal Entity and signers, picked from what the land holdings have or
typed in (holding_plans turns that into what changes). After a Yes in a box listing the changes, Merge
edits both accounts in Ark (apply_merge, through each account's Edit Account window): the other account
is renamed "<name> (merge)", the kept one "<name> (keep)", and note blocks go above the kept account's
notes: merge_note (today's date, _INITIALS, the merge account's mailing address / phone / email /
parent account where they differ, its Account Notes in quotes) on its Account Notes, merge_call_note
(the same with its Call Notes) on its Call Notes. The kept account's blank Confirmed Phone Number /
Confirmed Email Addresses, and its mailing address if wholly blank, are filled from the merge account's
(blank_fills; left out of the note). Each account is reloaded to check Ark kept the change. Then the merge account's contacts, offers, title
requests and calls & texts (MOVED) get the kept account as their Account, one record at a time
(move_records, rereading the list until none are left); a record Ark won't move is listed in the
closing box instead of stopping the run. Its land holdings move to the kept account and every land
holding whose Legal Entity or signers were changed gets them (update_holdings, through each land
holding's edit window, checked after saving). Its documents are downloaded to [Folders] Merges (default
Desktop\\Merges) under a name Windows allows, with an extension (_file_name), uploaded to the kept
account, and deleted from that folder once Ark lists them there (move_documents; the merge account
keeps its copies). Side drawer lists are scrolled until they show everything Ark counts (_listed).
Tasks aren't moved.
Last, if nothing is left on the merge account (no records, no land holdings as its drawer lists them,
every document copied, no problems), both accounts open in the browser for review and the closing box
asks whether to delete the merge account (delete_account: Delete, top right, then Delete in Ark's
confirmation box), after which the kept account loses its " (keep)" (untag_kept); otherwise the box
says why it wasn't deleted. A bad or missing account, or anything else that fails, ends in an
error box (log: merge_error.log in %APPDATA%\\PhoenixLandDept, since Merge has no Desktop folder).
"""
import datetime
import os
import re
import sys
import time
import webbrowser

import ark_common

ACCOUNT_URL = 'https://ark.phoenixenergy.com/accounts?recordId={}'  # an account's page in Ark, by record id
_RECORD_ID = re.compile(r'[0-9a-f]{24}', re.I)  # an Ark record id: 24 hex digits
# A link to an Ark account page (any Ark domain, other query parts and a #fragment allowed); group 1 = record id
_ACCOUNT_LINK = re.compile(r'https?://[^/?#\s]+/accounts/?\?(?:[^#\s]*&)?recordId=([0-9a-f]{24})(?:[&#]\S*)?', re.I)
_TITLE_PREFIX = 'Account - '  # an account page's title once loaded: "Account - <Account Name>"
_NOT_FOUND = 'Account Not Found'  # what Ark shows (in about a second) for a record id with no account
_HOLDING_PREFIX = 'Land Holding - '  # a land holding page's title once loaded: "Land Holding - <name>"
# What a land holding page shows for a record that doesn't exist: a guess from the account page's
# message (not seen live); if wrong, a missing holding fails after _OPEN_TIMEOUT_MS instead of at once
_HOLDING_NOT_FOUND = 'Land Holding Not Found'
_OPEN_TIMEOUT_MS = 30_000  # give up on a page showing neither its name nor its Not Found message after this long
_POLL_MS = 250  # how often _open_record rechecks the page
_SETTLE_MS = 1_000  # _read_page reads the page again after this long and takes it once two reads agree

# Quick Reference items checked on each account, in the order listed (labels as Ark shows them)
CHECKED = ['Documents', 'Contacts', 'Offers', 'Title Requests', 'Tasks', 'Calls & Texts', 'Land Holdings']
# Account fields shown for review (not changed by a merge): (section heading on the page, field label)
DETAILS = [('System Information', 'Created Date'), ('Details', 'Account Disposition'),
           ('Details', 'Mailing Street'), ('Details', 'Mailing City'), ('Details', 'Mailing State'),
           ('Details', 'Mailing Zip Code'), ('Details', 'Confirmed Phone Number'),
           ('Details', 'Confirmed Email Addresses')]
# Account text fields read: (section heading, field label); shown under the section's name
NOTES = [('Account Notes', 'Notes'), ('Call Notes', 'Call Notes')]
# Land holding fields read: (section heading, field label); signers are read separately (_signers)
HOLDING_FIELDS = [('Details', 'Legal Entity'), ('Location Info', 'Section Name'), ('Title Info', 'Title Information')]
_SIGNER_SECTION = 'Signer Information'  # land holding section holding Signer 1-9 and the Capacity / Last Name Ark has (_SIGNER_BOX_LIMITS)
_SIGNER = re.compile(r'Signer (\d+)')  # a signer's own field label; "Signer N Capacity" / "Signer N Last Name" go with it
_SIGNER_PARTS = [('Signer', ''), ('Last Name', ' Last Name'), ('Capacity', ' Capacity')]  # a signer's parts: (key, field label after "Signer N")
_MAX_SIGNERS = 9  # a land holding has Signer 1-9
# Highest Signer number Ark has each part's box for (seen 2026-11-11): the name for Signer 1-9, Last Name
# only for Signer 1-2, Capacity only for Signer 1-3
_SIGNER_BOX_LIMITS = {'Signer': _MAX_SIGNERS, 'Last Name': 2, 'Capacity': 3}
_LEGAL_ENTITY = 'Legal Entity'  # the land holding field the user picks for each land holding
_HOLDING_BOX = 'label:text-is("{}") + :is(input, textarea)'  # a land holding edit window's box for a field label
# The edit window's tab holding each. Ark's tab text isn't exactly the name (the signers one wasn't found
# that way live), so the first text containing it is clicked when no text is exactly it (_open_tab loose)
_HOLDING_TABS = {_LEGAL_ENTITY: 'Details', 'signers': 'Signer Information'}
_HOLDINGS_LABEL = 'Land Holdings'  # Quick Reference label of an account's land holdings
# A Quick Reference entry (and, as Ark reuses the id, each expanded table), in the order _READ_JS reads them
_QUICK_ENTRY = '[id="quick-ref-rel-list"]'
_HOLDING_PATH = '/land-holdings?recordId='  # path in a land holding page link
_COUNT = re.compile(r'\((\d[\d,]*)\)')  # a Quick Reference count as shown: "(12)", "(1,234)"
_NOT_SHOWN = 'not on this page'  # how the review shows an item or field the page doesn't have
# JS for page.evaluate, the same on account and land holding pages: the Quick Reference entries as
# [label, count text] (Ark reuses their id for the expanded tables, which _counts drops), every detail
# field as [section heading, field label, value text] (each section is on the page twice, in two
# layouts; _fields takes the first) and the land holding links as [href, text]
_READ_JS = r"""() => ({
  quick: [...document.querySelectorAll('[id="quick-ref-rel-list"]')].map(el => {
    const kids = [...el.children].filter(c => c.tagName === 'DIV');
    return [kids[1] ? kids[1].innerText.trim() : '', kids[2] ? kids[2].innerText.trim() : ''];
  }),
  fields: [...document.querySelectorAll('div.font-medium.text-lighter')].map(label => {
    const value = label.nextElementSibling;
    const grid = label.closest('.grid'), head = grid && grid.previousElementSibling;
    return [head ? head.innerText.trim() : '', label.innerText.trim(), value ? value.innerText : null];
  }),
  holdings: [...document.querySelectorAll('a[href*="/land-holdings?recordId="]')].map(a => [a.href, a.innerText.trim()]),
})"""

# ─── Merge step constants ──────────────────────────────────────────────────────
_TAG = re.compile(r'\s*\((?:keep|merge)\)\s*$', re.I)  # a "(keep)" / "(merge)" already on a name, taken off before tagging
_INITIALS = 'RM'  # initials in the note block's first line: "<mm/dd/yyyy> RM - Notes from merge:"
# Mailing address fields, in the order the note block lists them (labels as in DETAILS)
_MAILING = ['Mailing Street', 'Mailing City', 'Mailing State', 'Mailing Zip Code']
_PHONE = 'Confirmed Phone Number'  # account phone field compared by merge_differences
_EMAIL = 'Confirmed Email Addresses'  # account email field compared by merge_differences
_PARENT = 'Parent Account'  # an account's parent (read by _parent; in 'details'), compared by merge_differences
_PARENT_ENTRY = 'Parent - '  # Ark's Quick Reference hierarchy entry naming an account's parent: "Parent - <name>..."
_LIST_SPLIT = re.compile(r'[,;/\n]+')  # separates several phone numbers or emails in one field
_EDIT_BUTTON = 'Edit'  # a record page's button that opens its edit window (Edit Account, Edit Offers, ...)
_NAME_FIELD = 'label:has-text("Account Name") + input'  # Account Name box in the Edit Account window (Details tab)
# The notes boxes of the Edit Account window: section (also the name of the tab holding it) -> its box
# An Edit Account window's box for a Details field label (on the Details tab the window opens on; seen for
# Confirmed Phone Number / Confirmed Email Addresses 2026-11-11, the mailing boxes taken to be the same)
_DETAIL_BOX = 'label:text-is("{}") + :is(input, textarea)'
_NOTE_BOXES = {'Account Notes': 'label:text-is("Notes") + textarea',
               'Call Notes': 'label:text-is("Call Notes") + textarea'}
_SAVE_BUTTON = 'Save'  # edit window button that saves the changes
# Records moved from the merge account to the kept one: (Quick Reference label, path in their page links,
# word for one, word for several)
MOVED = [('Contacts', '/contacts?recordId=', 'contact', 'contacts'),
         ('Offers', '/offers?recordId=', 'offer', 'offers'),
         ('Title Requests', '/title-requests?recordId=', 'title request', 'title requests'),
         ('Calls & Texts', '/activities?recordId=', 'call / text', 'calls & texts')]
# JS for page.evaluate(part): links in the side drawer that a Quick Reference entry opens (its full list
# of that kind of record) whose href contains part
_DRAWER_JS = r"""(part) => [...document.querySelectorAll('#side-drawer a[href*="' + part + '"]')].map(a => a.href)"""
# The Account lookup in a contact / offer / title request / call's edit window ("Account" or "Account
# Name *"; not "Account Owner Name"): the account as a tag (<p>) with an x (its first <svg>), which
# turns it into a search box listing matching accounts
_ACCOUNT_BOX = 'div:has(> label:text-matches("^Account( Name)?[ *]*$"))'
_KEY_DELAY_MS = 50  # the account search is typed key by key: a value filled in all at once doesn't search
_RECORD_LINK = re.compile(r'recordId=([0-9a-f]{24})', re.I)  # the record id in a record page link
# Folder the merge account's documents are downloaded to before they're uploaded to the kept account
# (emptied of them once uploaded) when [Folders] Merges is unset
_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\Merges'
_DOCUMENTS = 'Documents'  # Quick Reference label whose side drawer lists an account's documents
# JS for page.evaluate: the file name (first cell) of each row of the side drawer's table
_DOC_ROWS_JS = r"""() => [...document.querySelectorAll('#side-drawer tbody tr')].map(tr => {
  const cell = tr.querySelector('td'); return cell ? cell.innerText.trim() : ''; })"""
_DOC_ROW = '#side-drawer tbody tr'  # a row of the side drawer's table (one document)
# JS for page.evaluate: scrolls every scrollable box in the side drawer to its bottom, so a long list
# (which Ark loads as it's scrolled) shows its next rows
_SCROLL_JS = r"""() => { for (const el of document.querySelectorAll('#side-drawer, #side-drawer *'))
  if (el.scrollHeight > el.clientHeight) el.scrollTop = el.scrollHeight; }"""
_STILL_READS = 3  # _listed stops scrolling once this many reads in a row list nothing new
_LIST_TIMEOUT_MS = 120_000  # _listed gives up scrolling a list that keeps growing after this long
_DOWNLOAD_PART = '_merge_download.part'  # a document's file name in the folder until its real name is known
_BAD_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')  # characters Windows doesn't allow in a file name
# Extensions taken from the name Ark lists a document under (anything else after a dot there, e.g.
# "Lease No.5", is part of the name)
_KNOWN_EXTENSIONS = {'pdf', 'doc', 'docx', 'docm', 'xls', 'xlsx', 'xlsm', 'csv', 'txt', 'rtf', 'msg', 'eml',
                     'jpg', 'jpeg', 'png', 'gif', 'tif', 'tiff', 'bmp', 'heic', 'zip', 'ppt', 'pptx',
                     'kml', 'kmz', 'htm', 'html', 'xml', 'json', 'odt', 'ods'}
_SUGGESTED_EXTENSION = re.compile(r'\.(?=[a-z0-9]*[a-z])([a-z0-9]{1,5})$', re.I)  # an extension (1-5 letters / digits, at least one a letter) on Ark's download name
# A file's first bytes -> its extension, for a document neither name gives one (_sniff_extension)
_MAGIC = [(b'%PDF', '.pdf'), (b'\x89PNG\r\n\x1a\n', '.png'), (b'\xff\xd8\xff', '.jpg'), (b'GIF8', '.gif'),
          (b'II*\x00', '.tif'), (b'MM\x00*', '.tif'), (b'{\\rtf', '.rtf')]
_ZIP_MAGIC = b'PK\x03\x04'  # a zip file, or a Word / Excel / PowerPoint file (zips inside)
_ZIP_KINDS = [('word/', '.docx'), ('xl/', '.xlsx'), ('ppt/', '.pptx')]  # folder inside the zip -> its extension
_OLE_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'  # an old Office file (.doc / .xls / .msg)
# Stream named inside an old Office file -> its extension (names are stored in UTF-16)
_OLE_KINDS = [('WordDocument', '.doc'), ('Workbook', '.xls'), ('__substg1.0_', '.msg')]
# A document row's download button, told apart by its tray-and-arrow icon (the row also has view,
# edit and a red delete button, which Merge never clicks)
_DOWNLOAD_BUTTON = 'button:has(path[d^="M12 10v2H4v-2"])'
_ADD_BUTTON = 'Add'  # the Documents side drawer's button that opens "Upload Account Documents"
_FILE_INPUT = 'input[type=file]'  # the upload window's file picker (takes several files)
_UPLOAD_BUTTON = 'Confirm and Upload'  # the upload window's button that uploads the files picked
# What the upload window shows under each file once it's taken it in; uploading before every file
# shows it closes the window and uploads nothing
_READY = 'Ready to Upload'
_UPLOAD_URL = 'api-ark.phoenixenergy.com/related-bulk-document-upload'  # Ark's call that stores uploaded documents
_TRANSFER_TIMEOUT_MS = 120_000  # give up on one download, or on the upload window closing, after this long
# Ark's API call that stores an edited record. The Edit Account window closes before it's sent, so
# Merge waits for its answer (a reload before then cancels the save)
_UPDATE_URL = 'api-ark.phoenixenergy.com/update-sb'
# Yes/No box (MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2: No is the default) and its Yes answer
_ASK_FLAGS, _IDYES = 0x124, 6
_DELETE_BUTTON = 'Delete'  # the account page's button (top right) that deletes it, and the one in Ark's confirmation box
_API = 'api-ark.phoenixenergy.com'  # Ark's API: a delete is taken as done once a call to it naming the account answers
_CHANGE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')  # API calls that change data (page reads use GET)


def record_id(text):
    """The record id (lowercase) in a pasted account link or bare record id; ValueError if neither."""
    text = text.strip()
    if _RECORD_ID.fullmatch(text):
        return text.lower()
    m = _ACCOUNT_LINK.fullmatch(text)
    if not m:
        raise ValueError(f'Not a link to an Ark account: {text}')
    return m[1].lower()


class _Stopwatch:
    """How long a wait loop has gone on: the pauses it took (sleep) or the real time since it started,
    whichever is more. Real time catches a loop whose every look is slow (e.g. reopens a page); the
    pauses keep tests on time, where they return at once."""

    def __init__(self):
        """Starts it."""
        self.slept, self.start = 0, time.monotonic()

    def elapsed_ms(self):
        """Milliseconds gone so far."""
        return max(self.slept, (time.monotonic() - self.start) * 1000)

    def sleep(self, page, ms):
        """Pause ms on page."""
        page.wait_for_timeout(ms)
        self.slept += ms


def _reason(e):
    """What went wrong, for a note in the closing box: the first line of error e's message without a
    trailing ":" (a link follows it there), or e's kind (e.g. "OSError") if it has no message."""
    return str(e).split('\n')[0].rstrip(':').strip() or type(e).__name__


def _open_record(page, url, prefix, not_found):
    """Show the record at url on page (logging in and reopening it if Ark asks) and return its name
    from the title ("<prefix><name>"). Raises if the page shows not_found or doesn't load within
    _OPEN_TIMEOUT_MS."""
    if page.url != url:
        page.goto(url)
    if ark_common.needs_login(page):
        ark_common.ensure_login(page)
        page.goto(url)  # the login lands on Ark's home page, not the record
    waited = 0
    while True:
        title = page.title()
        if title.startswith(prefix) and title[len(prefix):].strip():
            return title[len(prefix):].strip()
        if page.get_by_text(not_found).count():
            raise RuntimeError(f'Ark shows "{not_found}"; check the link:\n{url}')
        if waited >= _OPEN_TIMEOUT_MS:
            raise RuntimeError(f"Ark didn't finish opening the page in {_OPEN_TIMEOUT_MS // 1000} s:\n{url}")
        page.wait_for_timeout(_POLL_MS)
        waited += _POLL_MS


def _counts(raw):
    """{label: n} of the Quick Reference counts in a _READ_JS read (first of each label)."""
    shown = {}
    for label, count in raw['quick']:
        m = _COUNT.fullmatch(count)
        if m and label not in shown:
            shown[label] = int(m[1].replace(',', ''))
    return shown


def _quick_index(raw, label):
    """Index in a _READ_JS read of the Quick Reference entry _counts takes for label (the first with
    exactly that label and a count), so the entry clicked is the one counted; None if there's none."""
    return next((i for i, (shown, count) in enumerate(raw['quick']) if shown == label and _COUNT.fullmatch(count)),
                None)


def _fields(raw):
    """{(section, label): value} of the detail fields in a _READ_JS read: the first copy of each,
    trimmed; Ark's "-" for an empty field becomes ''."""
    found = {}
    for section, label, value in raw['fields']:
        if (section, label) not in found and value is not None:
            value = value.strip()
            found[(section, label)] = '' if value == '-' else value
    return found


def _holding_links(raw):
    """Land holding page URLs linked from an account page, in page order, each once."""
    return list(dict.fromkeys(href for href, _ in raw['holdings']))


def _read_page(page, ready):
    """A _READ_JS read of the page, taken once ready(read) is true and two reads _SETTLE_MS apart
    agree, so values still loading aren't taken. Raises if never ready within _OPEN_TIMEOUT_MS; after
    that long ready but changing, takes the last read."""
    waited, last = 0, None
    while True:
        raw = page.evaluate(_READ_JS)
        if ready(raw) and raw == last:
            return raw
        if waited >= _OPEN_TIMEOUT_MS:
            if not ready(raw):
                raise RuntimeError(f"Ark didn't finish showing the page in {_OPEN_TIMEOUT_MS // 1000} s:\n{page.url}")
            return raw
        last = raw
        page.wait_for_timeout(_SETTLE_MS)
        waited += _SETTLE_MS


def _signers(fields):
    """The land holding's signers from its Signer Information section, in number order: one
    {'Signer': name, 'Last Name': ..., 'Capacity': ...} per signer with any of the three filled."""
    numbers = sorted({int(m[1]) for (section, label) in fields
                      if section == _SIGNER_SECTION and (m := _SIGNER.fullmatch(label))})
    signers = []
    for n in numbers:
        signer = {part: fields.get((_SIGNER_SECTION, f'Signer {n}{suffix}'), '') for part, suffix in _SIGNER_PARTS}
        if any(signer.values()):
            signers.append(signer)
    return signers


def _parent(raw, fields):
    """An account's parent account from a _READ_JS read: a "Parent Account" field in any section, else
    the first line of Ark's Quick Reference hierarchy entry "Parent - <name>", else ''."""
    found = next((value for (section, label), value in fields.items() if label == _PARENT), None)
    if found is not None:
        return found
    entry = next((label for label, _ in raw['quick'] if label.startswith(_PARENT_ENTRY)), '')
    return entry.split('\n')[0][len(_PARENT_ENTRY):].strip()


def _read_holding(page, url):
    """Open one land holding and return {'name', 'url', 'fields': {label: value or None}, 'signers'}."""
    name = _open_record(page, url, _HOLDING_PREFIX, _HOLDING_NOT_FOUND)
    fields = _fields(_read_page(page, lambda raw: bool(raw['fields'])))
    return {'name': name, 'url': url,
            'fields': {label: fields.get((section, label)) for section, label in HOLDING_FIELDS},
            'signers': _signers(fields)}


def _read_account(page, rid):
    """Open account rid and read it: {'name', 'url', 'counts': {label: n or None}, 'details': {label:
    value or None, plus 'Parent Account' (_parent)}, 'notes': {section: text or None}, 'holdings':
    [_read_holding, ...], 'holdings_missing': land holdings counted but not found}. None = not on the
    page, '' = blank. The land holdings are the ones linked on the page; if the Quick Reference counts
    more, its Land Holdings side drawer (scrolled, _related_links) is read for the rest."""
    url = ACCOUNT_URL.format(rid)
    name = _open_record(page, url, _TITLE_PREFIX, _NOT_FOUND)
    raw = _read_page(page, lambda raw: bool(_counts(raw)))
    counts, fields, links = _counts(raw), _fields(raw), _holding_links(raw)
    account = {'name': name, 'url': url,
               'counts': {label: counts.get(label) for label in CHECKED},
               'details': {**{label: fields.get((section, label)) for section, label in DETAILS},
                           _PARENT: _parent(raw, fields)},
               'notes': {section: fields.get((section, label)) for section, label in NOTES}}
    total = account['counts'][_HOLDINGS_LABEL] or 0
    if total > len(links):
        links = list(dict.fromkeys(links + _related_links(page, url, _HOLDINGS_LABEL, _HOLDING_PATH)[0]))
    account['holdings_missing'] = max(total - len(links), 0)
    account['holdings'] = [_read_holding(page, link) for link in links]
    return account


# ─── Merge step: names and the note block ──────────────────────────────────────

def untagged_name(name):
    """name without a " (keep)" / " (merge)" at the end."""
    return _TAG.sub('', name).rstrip()


def tagged_name(name, tag):
    """name with " (tag)" at the end ("keep" or "merge"), replacing a (keep) / (merge) already there."""
    return f'{untagged_name(name)} ({tag})'


def _plain(text):
    """text lowercased with its whitespace collapsed, for comparing values typed differently."""
    return ' '.join((text or '').split()).lower()


def _mailing(details):
    """An account's mailing address on one line, "street, city, state zip", blank parts left out."""
    street, city, state, zip_code = (details.get(label) or '' for label in _MAILING)
    last = ' '.join(p for p in (state.strip(), zip_code.strip()) if p)
    return ', '.join(p for p in (street.strip(), city.strip(), last) if p)


def _phones(text):
    """The phone numbers in a phone field, each as its last 10 digits (so a leading 1 doesn't matter)."""
    return {re.sub(r'\D', '', p)[-10:] for p in _LIST_SPLIT.split(text or '') if re.sub(r'\D', '', p)}


def _emails(text):
    """The email addresses in an email field, lowercased."""
    return {e.strip().lower() for e in _LIST_SPLIT.split(text or '') if e.strip()}


def _blank(value):
    """True for a field on the page with nothing in it ('' or spaces); None (not on the page) isn't blank."""
    return value is not None and not value.strip()


def blank_fills(keep, merge):
    """{field label: value} the kept account gets from the merge account where its own is blank: Confirmed
    Phone Number and Confirmed Email Addresses each on its own; the mailing address (_MAILING) only when every
    part of the kept one is blank, and then only the parts the merge account has. In DETAILS order."""
    k, m = keep['details'], merge['details']
    fills = {label: m[label].strip() for label in (_PHONE, _EMAIL) if _blank(k.get(label)) and (m.get(label) or '').strip()}
    if all(_blank(k.get(label)) for label in _MAILING):
        fills.update({label: m[label].strip() for label in _MAILING if (m.get(label) or '').strip()})
    return {label: fills[label] for _, label in DETAILS if label in fills}


def merge_differences(keep, merge):
    """Lines for the note block: the merge account's mailing address, phone, email and parent account,
    each only if it has one the kept account doesn't (a phone or email already on the kept account isn't
    listed; the parent only if it differs). What blank_fills copies to the kept account isn't listed."""
    keep = {**keep, 'details': {**keep['details'], **blank_fills(keep, merge)}}
    lines = []
    address = _mailing(merge['details'])
    if address and _plain(address) != _plain(_mailing(keep['details'])):
        lines.append(f'Mailing Address: {address}')
    phone, email = (merge['details'].get(label) or '' for label in (_PHONE, _EMAIL))
    if phone.strip() and not _phones(phone) <= _phones(keep['details'].get(_PHONE)):
        lines.append(f'Phone: {phone.strip()}')
    if email.strip() and not _emails(email) <= _emails(keep['details'].get(_EMAIL)):
        lines.append(f'Email: {email.strip()}')
    parent = (merge['details'].get(_PARENT) or '').strip()
    if parent and _plain(parent) != _plain(keep['details'].get(_PARENT)):
        lines.append(f'Parent Account: {parent}')
    return lines


def merge_note(keep, merge, today):
    """The block that goes above the kept account's Account Notes, or '' if there's nothing to add:
    "<mm/dd/yyyy> RM - Notes from merge:", merge_differences lines, then the merge account's Account
    Notes between lines holding only a double quote."""
    lines = merge_differences(keep, merge)
    notes = (merge['notes'].get('Account Notes') or '').strip()
    if notes:
        lines += ['"', notes, '"']
    if not lines:
        return ''
    return '\n'.join([f'{today:%m/%d/%Y} {_INITIALS} - Notes from merge:'] + lines)


def merge_call_note(merge, today):
    """The block that goes above the kept account's Call Notes, or '' if the merge account has none:
    "<mm/dd/yyyy> RM - Notes from merge:", then its Call Notes between lines holding only a double quote."""
    notes = (merge['notes'].get('Call Notes') or '').strip()
    return f'{today:%m/%d/%Y} {_INITIALS} - Notes from merge:\n"\n{notes}\n"' if notes else ''


def note_blocks(keep, merge, today):
    """{section: block} for the kept account's notes: Account Notes (merge_note) and Call Notes
    (merge_call_note); '' where there's nothing to add."""
    return {'Account Notes': merge_note(keep, merge, today), 'Call Notes': merge_call_note(merge, today)}


def combined_notes(block, existing):
    """The kept account's new notes: the block, a blank line, then the notes it had."""
    existing = (existing or '').strip()
    return f'{block}\n\n{existing}' if existing else block


def _to_move(account):
    """What of account's MOVED records there are to move, as text ("1 offer, 2 calls & texts"), or ''."""
    return ', '.join(ark_common.plural(account['counts'][label], one, several)
                     for label, _, one, several in MOVED if account['counts'][label])


def _confirm_text(accounts, keep, blocks, folder, plans=()):
    """The Yes/No box text listing what apply_merge will change in Ark (land holdings as plans say,
    documents through folder), and that Merge asks again before deleting the merge account."""
    k, m = accounts[keep], accounts[1 - keep]
    merge_name, keep_name = tagged_name(m['name'], 'merge'), tagged_name(k['name'], 'keep')
    lines = ['Merge will change these accounts in Ark:', '',
             f'Rename "{m["name"]}" to "{merge_name}"', f'Rename "{k["name"]}" to "{keep_name}"', '']
    fills = blank_fills(k, m)
    if fills:
        lines += [f'Fill in "{k["name"]}" blank fields from "{m["name"]}":'] + [
            f'- {label}: {value}' for label, value in fills.items()] + ['']
    for section, block in blocks.items():
        if block:
            lines += [f'Add to the top of "{k["name"]}" {section}:', '', block, '']
        else:
            lines += [f'Nothing to add to the {section}.', '']
    moving = _to_move(m)
    lines.append(f'Move from "{merge_name}" to "{keep_name}": {moving}' if moving else
                 f'No contacts, offers, title requests or calls & texts to move from "{m["name"]}".')
    if plans:
        lines += ['', 'Land holdings:'] + [f'- {_plan_text(p, keep_name)}' for p in plans] + ['']
    else:
        lines.append('No land holdings to move or change.')
    documents = m['counts'].get(_DOCUMENTS)
    lines.append(f'Copy {ark_common.plural(documents, "document")} to "{keep_name}" (downloaded to {folder}, uploaded, '
                 'then deleted from that folder; the merge account keeps its copies)' if documents else
                 f'No documents to copy from "{m["name"]}".')
    lines += ['', f'Then, if everything moved, Merge asks before deleting "{merge_name}", and once it\'s deleted '
                  f'renames "{keep_name}" back to "{untagged_name(keep_name)}".']
    return '\n'.join(lines + ['', 'Go ahead?'])


# ─── Merge step: changing the accounts in Ark ──────────────────────────────────

def _field(dialog, selector, what):
    """The one box matching selector in an edit window (waits for it to show); raises if there isn't
    exactly one, before anything is saved."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    box = dialog.locator(selector)
    try:
        box.first.wait_for(timeout=_OPEN_TIMEOUT_MS)
    except PlaywrightTimeout:
        pass
    if box.count() != 1:
        raise RuntimeError(f"Ark's edit window shows {box.count()} {what} boxes instead of 1, "
                           'so Merge stopped without saving this record.')
    return box


def _save(page, dialog, url, changed):
    """Click the edit window's Save and, if changed, wait for Ark to store the record at url
    (_UPDATE_URL answered for its record id); then wait for the window to close. Raises if Ark doesn't
    answer within _OPEN_TIMEOUT_MS or answers with an error."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    rid = _RECORD_LINK.search(url)[1].lower()
    save = dialog.get_by_role('button', name=_SAVE_BUTTON, exact=True)
    try:
        if not changed:
            save.click()  # nothing changed (e.g. already tagged by an earlier try): Ark sends nothing
        else:
            with page.expect_response(lambda r: _UPDATE_URL in r.url and rid in (r.request.post_data or ''),
                                      timeout=_OPEN_TIMEOUT_MS) as answer:
                save.click()
            if not answer.value.ok:
                raise RuntimeError(f'Ark refused to save the record (error {answer.value.status}):\n{url}')
        dialog.wait_for(state='hidden', timeout=_OPEN_TIMEOUT_MS)
    except PlaywrightTimeout:
        raise RuntimeError(f"Ark didn't finish saving the record within {_OPEN_TIMEOUT_MS // 1000} s of Save, "
                           f'so the change may not have been saved:\n{url}') from None


def _loaded_name_box(page, dialog, shown_name, url):
    """The Account Name box, once it holds the account's name (shown_name, from the page title): the
    window fills in a moment after it opens, and the notes must not be read before then. Raises if it
    doesn't within _OPEN_TIMEOUT_MS."""
    box = _field(dialog, _NAME_FIELD, 'Account Name')
    waited = 0
    while _plain(box.input_value()) != _plain(shown_name):
        if waited >= _OPEN_TIMEOUT_MS:
            raise RuntimeError(f"Ark's Edit Account window didn't show the account's name \"{shown_name}\" within "
                               f'{_OPEN_TIMEOUT_MS // 1000} s, so Merge stopped without saving it:\n{url}')
        page.wait_for_timeout(_POLL_MS)
        waited += _POLL_MS
    return box


def _edit_account(page, url, name, blocks=None, fills=None):
    """Open the account at url, set its Account Name to name in its Edit Account window, fill each of
    fills ({Details field label: value}; _DETAIL_BOX, raising before saving if the box isn't blank any more)
    and put each non-blank block of blocks ({section: block}) above that section's notes (combined_notes,
    on the section's tab: _open_tab, exact name first); then Save and wait for Ark to store it (_save).
    Returns {section: notes saved}."""
    shown_name = _open_record(page, url, _TITLE_PREFIX, _NOT_FOUND)
    page.get_by_role('button', name=_EDIT_BUTTON, exact=True).first.click()
    dialog = page.get_by_role('dialog')
    _loaded_name_box(page, dialog, shown_name, url).fill(name)
    for label, value in (fills or {}).items():
        box = _field(dialog, _DETAIL_BOX.format(label), label)
        if box.input_value().strip():
            raise RuntimeError(f'"{shown_name}" now has a {label} ("{box.input_value().strip()}"), so Merge '
                               f'stopped without saving it:\n{url}')
        box.fill(value)
    saved = {}
    for section, block in (blocks or {}).items():
        if block:
            _open_tab(dialog, section, loose=True)
            box = _field(dialog, _NOTE_BOXES[section], section)
            saved[section] = combined_notes(block, box.input_value())
            box.fill(saved[section])
    _save(page, dialog, url, name != shown_name or bool(saved) or bool(fills))
    return saved


def _check_saved(page, url, name, notes=None, fills=None):
    """Reload the account at url and raise unless it shows name, each of notes ({section: text}) and each
    of fills ({Details field label: value})."""
    page.reload()
    shown = _open_record(page, url, _TITLE_PREFIX, _NOT_FOUND)
    if shown != name:
        raise RuntimeError(f'Ark still shows the account as "{shown}" after renaming it to "{name}":\n{url}')
    if notes or fills:
        fields = _fields(_read_page(page, lambda raw: bool(_counts(raw))))
        for section, label in NOTES:
            if section in (notes or {}) and _plain(fields.get((section, label))) != _plain(notes[section]):
                raise RuntimeError(f"Ark doesn't show the new {section} on \"{name}\" after saving them; "
                                   f'check the account:\n{url}')
        sections = {label: section for section, label in DETAILS}
        for label, value in (fills or {}).items():
            if _plain(fields.get((sections[label], label))) != _plain(value):
                raise RuntimeError(f"Ark doesn't show {label} \"{value}\" on \"{name}\" after saving it; "
                                   f'check the account:\n{url}')


def _open_drawer(page, url, label, even_empty=False):
    """Open the account at url and, if its Quick Reference counts any label records (or even_empty), click
    that entry (the one counted, _quick_index; not another whose text merely contains label) to open the
    side drawer listing them. Returns the count. Raises if even_empty and the page has no such entry."""
    page.goto(url)
    _open_record(page, url, _TITLE_PREFIX, _NOT_FOUND)
    raw = _read_page(page, lambda raw: bool(_counts(raw)))
    count = _counts(raw).get(label, 0)
    if count or even_empty:
        index = _quick_index(raw, label)
        if index is None:
            raise RuntimeError(f'The account\'s Quick Reference has no "{label}", so Merge couldn\'t open it:\n{url}')
        page.locator(_QUICK_ENTRY).nth(index).click()
    return count


def _listed(page, read, count):
    """read(page) (a list from the open side drawer), scrolling the drawer to its bottom between reads
    (_SCROLL_JS: Ark loads a long list as it's scrolled) until it has count items, or _STILL_READS reads
    in a row add nothing (after _LIST_TIMEOUT_MS at most), or it stays empty for _OPEN_TIMEOUT_MS
    (_Stopwatch time)."""
    watch, last, still = _Stopwatch(), None, 0
    while True:
        items = read(page)
        if len(items) >= count or watch.elapsed_ms() >= (_LIST_TIMEOUT_MS if items else _OPEN_TIMEOUT_MS):
            return items
        still = still + 1 if items and items == last else 0
        if still >= _STILL_READS:
            return items
        last = items
        page.evaluate(_SCROLL_JS)
        watch.sleep(page, _SETTLE_MS)


def _related_links(page, url, label, part):
    """The record links (href containing part) in the side drawer that the account at url opens from its
    Quick Reference entry label, once they're all listed (as many as its count) or stop changing.
    Returns (links, count)."""
    count = _open_drawer(page, url, label)
    if not count:
        return [], 0
    return _listed(page, lambda p: list(dict.fromkeys(p.evaluate(_DRAWER_JS, part))), count), count


def _move_record(page, url, from_name, to_name):
    """Open the record at url (a contact, offer, title request or call / text), change its Account from
    from_name to to_name in its edit window (x on the account, type the new name, pick the one exact
    match) and Save (_save). Raises, without saving, if the window doesn't show from_name, the search
    doesn't find exactly one to_name, or the pick doesn't take."""
    page.goto(url)
    dialog = _open_edit(page)
    _pick_account(page, _account_lookup(page, dialog, from_name), to_name)
    _save(page, dialog, url, True)


def _open_edit(page):
    """Click the record page's Edit button (once it shows) and return its edit window."""
    edit = page.get_by_role('button', name=_EDIT_BUTTON, exact=True).first
    edit.wait_for(timeout=_OPEN_TIMEOUT_MS)
    edit.click()
    return page.get_by_role('dialog')


def _account_lookup(page, dialog, owner_name):
    """The edit window's Account lookup (_ACCOUNT_BOX), once it shows owner_name: the window fills in a
    moment after it opens, so nothing may be read or changed before then. Raises (nothing saved) if it
    shows another account after _OPEN_TIMEOUT_MS."""
    box = _field(dialog, _ACCOUNT_BOX, 'Account').first
    tag, waited = box.locator('p').first, 0
    while _plain(tag.inner_text()) != _plain(owner_name):
        if waited >= _OPEN_TIMEOUT_MS:
            raise RuntimeError(f'its Account shows "{tag.inner_text()}", not "{owner_name}", so it was left alone')
        page.wait_for_timeout(_POLL_MS)
        waited += _POLL_MS
    return box


def _pick_account(page, box, to_name):
    """Change the Account lookup box to to_name: x on the account shown, type to_name key by key, pick
    the one exact match. Raises (nothing saved) if the search doesn't find exactly one or the pick
    doesn't take."""
    box.locator('svg').first.click()
    page.wait_for_timeout(_SETTLE_MS)  # the default list loads first and would replace the search's
    box.locator('input').first.press_sequentially(to_name, delay=_KEY_DELAY_MS)
    match, waited = box.get_by_text(to_name, exact=True), 0
    while not match.count() and waited < _OPEN_TIMEOUT_MS:
        page.wait_for_timeout(_POLL_MS)
        waited += _POLL_MS
    if match.count() != 1:
        raise RuntimeError(f'searching for the account "{to_name}" found {match.count()} accounts with '
                           'exactly that name instead of 1, so it was left alone')
    match.first.click()
    if _plain(box.locator('p').first.inner_text()) != _plain(to_name):
        raise RuntimeError(f'Ark didn\'t take "{to_name}" as its Account, so it was left alone')


def _account_counts(page, url):
    """Open the account at url and return its Quick Reference counts ({label: n})."""
    page.goto(url)
    _open_record(page, url, _TITLE_PREFIX, _NOT_FOUND)
    return _counts(_read_page(page, lambda raw: bool(_counts(raw))))


def _with_listed_holdings(page, url, counts):
    """counts (the account at url's Quick Reference), with Land Holdings replaced by how many its Land
    Holdings drawer lists when Ark counts some: right after land holdings move, Ark's count can stay at
    the old number for a while (seen 2026-11-11), so the list is what's trusted. Leaves the drawer open."""
    if not counts.get(_HOLDINGS_LABEL):
        return counts
    links, _ = _related_links(page, url, _HOLDINGS_LABEL, _HOLDING_PATH)
    return {**counts, _HOLDINGS_LABEL: len(links)}


def move_records(page, merge_url, merge_name, keep_name):
    """Move every MOVED record of the merge account (at merge_url) to the kept account, one at a time
    (_move_record). After each pass through the side drawer's list it's read again, so records it didn't
    list the first time (each record moved leaves the list) go in a later pass; each record is tried
    once. Returns ({label: number moved}, [problems]): a record that couldn't be moved, or records
    counted but never listed. What's still on the merge account is counted once, at the end of apply_merge."""
    moved, problems = {}, []
    for label, part, one, several in MOVED:
        moved[label], tried = 0, set()
        while True:
            links, count = _related_links(page, merge_url, label, part)
            todo = [link for link in links if link not in tried]
            if not todo:
                break
            for link in todo:
                tried.add(link)
                try:
                    _move_record(page, link, merge_name, keep_name)
                    moved[label] += 1
                except Exception as e:  # noqa: BLE001  (one record failing shouldn't stop the others)
                    problems.append(f"The {one} at {link} wasn't moved: {_reason(e)}")
        if len(links) < count:
            problems.append(f'{ark_common.plural(count - len(links), one, several)} counted on "{merge_name}" '
                            "but not listed, so not moved")
    return moved, problems


def _document_names(page, url, even_empty=False):
    """The names the account at url's Documents side drawer lists (scrolled until all are listed, see
    _listed), and how many documents its Quick Reference counts: (names, count). Leaves the drawer open
    if there are any, or even_empty (_open_drawer)."""
    count = _open_drawer(page, url, _DOCUMENTS, even_empty)
    names = _listed(page, lambda p: [n.strip() for n in p.evaluate(_DOC_ROWS_JS)], count) if count else []
    return names, count


def _known_extension(name):
    """name's extension in lowercase (".pdf") if it ends in one of _KNOWN_EXTENSIONS, else ''."""
    stem, ext = os.path.splitext(name.strip())
    return ext.lower() if stem and ext[1:].lower() in _KNOWN_EXTENSIONS else ''


def _sniff_extension(path):
    """The extension the file at path's contents show (_MAGIC; a zip's folders tell .docx / .xlsx /
    .pptx from .zip; an old Office file's streams tell .doc / .xls / .msg), or '' if unknown."""
    import zipfile
    with open(path, 'rb') as f:
        data = f.read()
    for magic, ext in _MAGIC:
        if data.startswith(magic):
            return ext
    if data.startswith(_ZIP_MAGIC):
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            return ''
        return next((ext for folder, ext in _ZIP_KINDS if any(n.startswith(folder) for n in names)), '.zip')
    if data.startswith(_OLE_MAGIC):
        return next((ext for stream, ext in _OLE_KINDS if stream.encode('utf-16-le') in data), '')
    return ''


def _file_name(listed, suggested, path):
    """The name a downloaded document is saved under: the name Ark lists it under (else its download
    name) with characters Windows doesn't allow replaced by "_", plus an extension when that name has
    none of _KNOWN_EXTENSIONS: the download name's, else what the file at path holds (_sniff_extension).
    Raises if neither tells the file type."""
    base = (listed or '').strip() or os.path.splitext(suggested or '')[0]
    base = _BAD_NAME_CHARS.sub('_', base).strip().rstrip('. ') or 'document'
    if _known_extension(base):
        return base
    m = _SUGGESTED_EXTENSION.search((suggested or '').strip())
    ext = f'.{m[1].lower()}' if m else _sniff_extension(path)
    if not ext:
        raise RuntimeError("its file type couldn't be told from its name or its contents, so it wasn't copied")
    return base + ext


def _document_key(name):
    """A document name as compared after uploading: lowercased and trimmed, without a known extension
    (Ark may list an upload with or without it)."""
    name = name.strip()
    ext = _known_extension(name)
    return _plain(name[:-len(ext)] if ext else name)


def _free_path(folder, name):
    """folder\\name, or "name (2).ext", "(3)", ... if that file is already there."""
    stem, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 2
    while os.path.exists(path):
        path, n = os.path.join(folder, f'{stem} ({n}){ext}'), n + 1
    return path


def download_documents(page, merge_url, folder):
    """Download each document of the merge account (at merge_url) into folder with its download button
    (_DOWNLOAD_BUTTON; never the row's other buttons), first as _DOWNLOAD_PART, then renamed to
    _file_name (a name Windows allows, with an extension; _free_path if taken). Returns ([paths
    downloaded], [problems]); documents counted but not listed are a problem."""
    os.makedirs(folder, exist_ok=True)
    names, count = _document_names(page, merge_url)  # leaves the drawer open on them
    paths, problems = [], []
    if len(names) < count:
        problems.append(f'{ark_common.plural(count - len(names), "document")} counted on the merge account but '
                        'not listed, so not copied')
    for i, name in enumerate(names):
        button = page.locator(_DOC_ROW).nth(i).locator(_DOWNLOAD_BUTTON)
        part = _free_path(folder, _DOWNLOAD_PART)
        try:
            if button.count() != 1:
                raise RuntimeError(f'its row has {button.count()} download buttons instead of 1')
            with page.expect_download(timeout=_TRANSFER_TIMEOUT_MS) as download:
                button.click()
            download.value.save_as(part)
            path = _free_path(folder, _file_name(name, download.value.suggested_filename, part))
            os.replace(part, path)
            paths.append(path)
        except Exception as e:  # noqa: BLE001  (one document failing shouldn't stop the others)
            if os.path.exists(part):
                os.remove(part)
            problems.append(f'The document "{name}" wasn\'t downloaded: {_reason(e)}')
    return paths, problems


def upload_documents(page, keep_url, paths):
    """Upload the files at paths to the kept account (at keep_url) through its Documents side drawer's
    upload window, then check its list (names compared by _document_key) until it shows them all or
    _OPEN_TIMEOUT_MS (_Stopwatch time) has gone. Returns ([paths Ark now lists], [problems])."""
    from collections import Counter
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    before = Counter(map(_document_key, _document_names(page, keep_url, even_empty=True)[0]))  # drawer left open
    page.locator('#side-drawer').get_by_role('button', name=_ADD_BUTTON, exact=True).first.click()
    dialog = page.get_by_role('dialog')
    folder = os.path.dirname(paths[0])
    _field(dialog, _FILE_INPUT, 'file picker').set_input_files(paths)
    ready, waited = dialog.get_by_text(_READY), 0
    while ready.count() < len(paths) and waited < _OPEN_TIMEOUT_MS:
        page.wait_for_timeout(_POLL_MS)
        waited += _POLL_MS
    if ready.count() < len(paths):
        return [], [f"Ark's upload window shows {ready.count()} of {len(paths)} documents ready to upload after "
                    f'{_OPEN_TIMEOUT_MS // 1000} s, so none were uploaded; they were kept in {folder}']
    try:
        with page.expect_response(lambda r: _UPLOAD_URL in r.url, timeout=_TRANSFER_TIMEOUT_MS) as answer:
            dialog.get_by_role('button', name=_UPLOAD_BUTTON, exact=True).click()
        if not answer.value.ok:
            return [], [f'Ark refused the upload (error {answer.value.status}); the documents were kept in {folder}']
        dialog.wait_for(state='hidden', timeout=_TRANSFER_TIMEOUT_MS)
    except PlaywrightTimeout:
        return [], [f"Ark didn't finish the upload within {_TRANSFER_TIMEOUT_MS // 1000} s, so the documents may "
                    f'not have been uploaded; they were kept in {folder}']
    wanted = before + Counter(_document_key(os.path.basename(p)) for p in paths)
    watch = _Stopwatch()
    while True:  # Ark lists an upload a moment after the window closes
        after = Counter(map(_document_key, _document_names(page, keep_url)[0]))
        if all(after[n] >= wanted[n] for n in wanted) or watch.elapsed_ms() >= _OPEN_TIMEOUT_MS:
            break
        watch.sleep(page, _SETTLE_MS)
    done, problems, seen = [], [], Counter(before)
    for path in paths:
        name = os.path.basename(path)
        seen[_document_key(name)] += 1
        if after[_document_key(name)] >= seen[_document_key(name)]:
            done.append(path)
        else:
            problems.append(f'The document "{name}" doesn\'t show on the kept account after uploading; '
                            f'it was kept in {os.path.dirname(path)}')
    return done, problems


def move_documents(page, merge_url, keep_url, folder):
    """Copy the merge account's documents to the kept account: download them to folder, upload them,
    and delete from folder each one Ark then lists on the kept account (the merge account keeps its
    copies). Returns (number copied, [problems])."""
    paths, problems = download_documents(page, merge_url, folder)
    if not paths:
        return 0, problems
    done, more = upload_documents(page, keep_url, paths)
    for path in done:
        os.remove(path)
    return len(done), problems + more


# ─── Merge step: land holdings ─────────────────────────────────────────────────

def _signer_key(signers):
    """Signers as compared: each signer's parts lowercased with whitespace collapsed."""
    return [tuple(_plain(s.get(part)) for part, _ in _SIGNER_PARTS) for s in signers]


def clean_signers(signers):
    """Signers as saved: each part trimmed, signers with nothing filled left out, at most _MAX_SIGNERS."""
    cleaned = [{part: (s.get(part) or '').strip() for part, _ in _SIGNER_PARTS} for s in signers]
    return [s for s in cleaned if any(s.values())][:_MAX_SIGNERS]


def missing_signer_boxes(signers):
    """The "Signer N <part>" labels signers fill in that Ark has no box for (_SIGNER_BOX_LIMITS), in order."""
    return [f'Signer {n}{suffix}' for n, s in enumerate(signers, 1) for part, suffix in _SIGNER_PARTS
            if n > _SIGNER_BOX_LIMITS[part] and (s.get(part) or '').strip()]


def holding_choices(accounts):
    """{land holding url: {'Legal Entity': text, 'signers': [signer, ...]}} for every land holding of
    both accounts as it is now: the land holdings window's starting point."""
    return {h['url']: {_LEGAL_ENTITY: h['fields'].get(_LEGAL_ENTITY) or '', 'signers': [dict(s) for s in h['signers']]}
            for account in accounts for h in account['holdings']}


def holding_options(accounts):
    """What the land holdings window offers to pick from, taken from both accounts' land holdings, each
    once in the order found: (Legal Entities, signer lists [(label, signers)], capacities)."""
    entities, sets, capacities, seen = [], [], [], set()
    for account in accounts:
        for h in account['holdings']:
            entity = (h['fields'].get(_LEGAL_ENTITY) or '').strip()
            if entity and entity not in entities:
                entities.append(entity)
            key = tuple(_signer_key(h['signers']))
            if key and key not in seen:
                seen.add(key)
                sets.append((f'{"; ".join(_signer_text(s) for s in h["signers"])} (from {h["name"]})', h['signers']))
            for s in h['signers']:
                if s['Capacity'] and s['Capacity'] not in capacities:
                    capacities.append(s['Capacity'])
    return entities, sets, capacities


def holding_plans(accounts, keep, choices):
    """What the merge step does to each land holding, given choices (as holding_choices): one
    {'url', 'name', 'move', 'owner', 'legal_entity', 'signers'} per land holding of the merge account
    (move: all go to the kept account) and per land holding of the kept one whose Legal Entity or signers
    change. legal_entity / signers: the new value (clean_signers), or None when unchanged (compared
    lowercased, spacing aside); owner: index of the account holding it now."""
    plans = []
    for i, account in enumerate(accounts):
        for h in account['holdings']:
            choice = choices.get(h['url']) or holding_choices([{'holdings': [h]}])[h['url']]
            entity = (choice.get(_LEGAL_ENTITY) or '').strip()
            signers = clean_signers(choice.get('signers') or [])
            plan = {'url': h['url'], 'name': h['name'], 'move': i != keep, 'owner': i,
                    'legal_entity': entity if _plain(entity) != _plain(h['fields'].get(_LEGAL_ENTITY)) else None,
                    'signers': signers if _signer_key(signers) != _signer_key(h['signers']) else None}
            if plan['move'] or plan['legal_entity'] is not None or plan['signers'] is not None:
                plans.append(plan)
    return plans


def _plan_text(plan, keep_name):
    """One land holding's line in the Yes/No box: its name, then what changes."""
    what = [f'move to "{keep_name}"'] if plan['move'] else []
    if plan['legal_entity'] is not None:
        what.append(f'Legal Entity "{plan["legal_entity"]}"' if plan['legal_entity'] else 'Legal Entity blank')
    if plan['signers'] is not None:
        what.append('signers ' + ('; '.join(_signer_text(s) for s in plan['signers']) or 'none'))
    return f'{plan["name"]}: {", ".join(what)}'


def _holding_box(dialog, label):
    """The one box for field label in a land holding's edit window (_HOLDING_BOX); raises if not exactly one."""
    return _field(dialog, _HOLDING_BOX.format(label), label)


def _open_tab(dialog, name, loose=False):
    """Click the edit window's tab called name: the text that is exactly name, if there is one; else,
    if loose, the first text containing it (how the notes and Signer Information tabs are found live), else nothing."""
    tab = dialog.get_by_text(name, exact=True)
    if tab.count():
        tab.first.click()
    elif loose:
        dialog.get_by_text(name).first.click()


def _update_holding(page, plan, owner_name, keep_name):
    """Change one land holding as plan says, in its edit window: wait for its Account lookup to show
    owner_name (the window has loaded), pick keep_name if it moves, set the Legal Entity box (on its tab,
    _HOLDING_TABS) and the signer boxes Ark has (_SIGNER_BOX_LIMITS; blank past the last signer), Save
    (_save), then reload it and raise unless it shows the new Legal Entity and signers. Raises before
    opening it if a signer fills a part Ark has no box for (missing_signer_boxes)."""
    url = plan['url']
    missing = missing_signer_boxes(plan['signers'] or [])
    if missing:
        raise RuntimeError(f'Ark has no {", ".join(missing)} box, so Merge stopped without saving this record.')
    page.goto(url)
    _open_record(page, url, _HOLDING_PREFIX, _HOLDING_NOT_FOUND)
    dialog = _open_edit(page)
    box = _account_lookup(page, dialog, owner_name)
    if plan['move']:
        _pick_account(page, box, keep_name)
    if plan['legal_entity'] is not None:
        _open_tab(dialog, _HOLDING_TABS[_LEGAL_ENTITY])
        _holding_box(dialog, _LEGAL_ENTITY).fill(plan['legal_entity'])
    if plan['signers'] is not None:
        _open_tab(dialog, _HOLDING_TABS['signers'], loose=True)
        blank = dict.fromkeys((part for part, _ in _SIGNER_PARTS), '')
        for n, signer in enumerate(plan['signers'] + [blank] * (_MAX_SIGNERS - len(plan['signers'])), 1):
            for part, suffix in _SIGNER_PARTS:
                if n > _SIGNER_BOX_LIMITS[part]:
                    continue
                field = _holding_box(dialog, f'Signer {n}{suffix}')
                if field.input_value() != signer[part]:
                    field.fill(signer[part])
    _save(page, dialog, url, True)
    page.reload()
    held = _read_holding(page, url)
    if plan['legal_entity'] is not None and _plain(held['fields'].get(_LEGAL_ENTITY)) != _plain(plan['legal_entity']):
        raise RuntimeError(f'Ark doesn\'t show the new Legal Entity "{plan["legal_entity"]}" after saving')
    if plan['signers'] is not None and _signer_key(held['signers']) != _signer_key(plan['signers']):
        raise RuntimeError("Ark doesn't show the new signers after saving")


def update_holdings(page, plans, names, keep_name):
    """Carry out every land holding plan (_update_holding; names: each account's name now, by index, for
    the owner). One that fails is noted and the rest go on. Returns ({'updated': n, 'moved': n}, [problems])."""
    done, problems = {'updated': 0, 'moved': 0}, []
    for plan in plans:
        try:
            _update_holding(page, plan, names[plan['owner']], keep_name)
            done['updated'] += 1
            done['moved'] += plan['move']
        except Exception as e:  # noqa: BLE001  (one land holding failing shouldn't stop the others)
            problems.append(f'The land holding "{plan["name"]}" at {plan["url"]} wasn\'t changed: {_reason(e)}')
    return done, problems


def delete_blockers(counts):
    """Why an account with these Quick Reference counts can't be deleted yet: records of a MOVED kind
    or land holdings still on it (callers put in the land holdings listed: _with_listed_holdings). [] =
    nothing left to move."""
    reasons = [f'Ark still counts {ark_common.plural(counts[label], one, several)} on it'
               for label, _, one, several in MOVED if counts.get(label)]
    if counts.get(_HOLDINGS_LABEL):
        reasons.append(f'Ark still counts {ark_common.plural(counts[_HOLDINGS_LABEL], "land holding")} on it')
    return reasons


def apply_merge(page, accounts, keep, blocks, folder, plans=()):
    """Change both accounts in Ark: rename the one not kept "<name> (merge)", then rename the kept one
    (accounts[keep]) "<name> (keep)" and put blocks ({section: block}) above its notes, checking each
    after it's saved; then move the merge account's MOVED records to the kept one (move_records), carry
    out the land holding plans (update_holdings: move the merge account's, set Legal Entities and
    signers) and copy its documents there by way of folder (move_documents). The kept account's save also
    fills its blank fields from the merge account (blank_fills). Last, recount the merge account for
    'blockers': why it can't be deleted yet (delete_blockers, land holdings as its drawer lists them,
    documents not all copied, problems noted; [] = it can). Returns {'merge_name', 'keep_name', 'filled',
    'moved', 'holdings', 'documents', 'problems', 'blockers'}."""
    k, m = accounts[keep], accounts[1 - keep]
    merge_name, keep_name = tagged_name(m['name'], 'merge'), tagged_name(k['name'], 'keep')
    fills = blank_fills(k, m)
    _edit_account(page, m['url'], merge_name)
    _check_saved(page, m['url'], merge_name)
    notes = _edit_account(page, k['url'], keep_name, blocks, fills)
    _check_saved(page, k['url'], keep_name, notes, fills)
    moved, problems = move_records(page, m['url'], merge_name, keep_name)
    names = [keep_name if i == keep else merge_name for i in range(len(accounts))]
    holdings, more = update_holdings(page, plans, names, keep_name)
    problems += more
    documents, more = move_documents(page, m['url'], k['url'], folder)
    problems += more
    left = _with_listed_holdings(page, m['url'], _account_counts(page, m['url']))
    blockers = delete_blockers(left)
    if documents < (left.get(_DOCUMENTS) or 0):
        blockers.append(f'{ark_common.plural(left[_DOCUMENTS], "document")} on it, {documents} copied')
    if problems:
        blockers.append('the problems above need a look first')
    return {'merge_name': merge_name, 'keep_name': keep_name, 'filled': fills, 'moved': moved, 'holdings': holdings,
            'documents': documents, 'problems': problems, 'blockers': blockers}


def delete_account(page, url, name):
    """Delete the merge account at url: reopen it and check it's still named name and has nothing left
    to move (delete_blockers; land holdings as its drawer lists them, _with_listed_holdings, then the page is
    opened again to close the drawer), click Delete (top right), then Delete in Ark's confirmation box, wait for
    Ark's answer naming the account, and open the link in another tab (reloaded while it still shows the
    account) to check Ark shows "Account Not Found". The page itself is left alone: if that answer was
    another call naming the account, the delete may still be on its way, and leaving would cancel it.
    Raises, before deleting, if the name, the counts or the confirmation box aren't as expected; after,
    if Ark refuses, doesn't answer or still shows the account after _OPEN_TIMEOUT_MS."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    page.goto(url)
    shown = _open_record(page, url, _TITLE_PREFIX, _NOT_FOUND)
    if shown != name:
        raise RuntimeError(f'The account is now named "{shown}", not "{name}", so Merge didn\'t delete it:\n{url}')
    counts = _counts(_read_page(page, lambda raw: bool(_counts(raw))))
    if counts.get(_HOLDINGS_LABEL):
        counts = _with_listed_holdings(page, url, counts)
        page.goto(url)
        _open_record(page, url, _TITLE_PREFIX, _NOT_FOUND)
    blockers = delete_blockers(counts)
    if blockers:
        raise RuntimeError(f'Merge didn\'t delete "{name}": {"; ".join(blockers)}.\n{url}')
    rid = _RECORD_LINK.search(url)[1].lower()
    page.get_by_role('button', name=_DELETE_BUTTON, exact=True).first.click()
    confirm = page.get_by_role('dialog').get_by_role('button', name=_DELETE_BUTTON, exact=True)
    try:
        confirm.first.wait_for(timeout=_OPEN_TIMEOUT_MS)
    except PlaywrightTimeout:
        pass
    if confirm.count() != 1:
        raise RuntimeError(f"Ark's confirmation box shows {confirm.count()} Delete buttons instead of 1, so "
                           f'"{name}" wasn\'t deleted:\n{url}')
    try:
        with page.expect_response(lambda r: _API in r.url and r.request.method in _CHANGE_METHODS
                                  and rid in r.url + (r.request.post_data or ''), timeout=_OPEN_TIMEOUT_MS) as answer:
            confirm.first.click()
    except PlaywrightTimeout:
        raise RuntimeError(f"Ark didn't answer the delete within {_OPEN_TIMEOUT_MS // 1000} s; check whether "
                           f'"{name}" is still there:\n{url}') from None
    if not answer.value.ok:
        raise RuntimeError(f'Ark refused to delete "{name}" (error {answer.value.status}):\n{url}')
    check = page.context.new_page()
    try:
        check.goto(url)
        watch = _Stopwatch()
        while not check.get_by_text(_NOT_FOUND).count():
            if watch.elapsed_ms() >= _OPEN_TIMEOUT_MS:
                raise RuntimeError(f'Ark still shows "{name}" after deleting it; check the account:\n{url}')
            watch.sleep(check, _SETTLE_MS)
            if check.title().startswith(_TITLE_PREFIX):  # still shown: look again, the delete may be on its way
                check.reload()
    finally:
        check.close()


def untag_kept(page, url, keep_name):
    """Once the merge account is deleted: rename the kept account at url from keep_name back to its name
    without " (keep)" (untagged_name), in a new tab of page's browser (the page that deleted is left
    alone), and check Ark kept it (_check_saved). Returns the new name."""
    name = untagged_name(keep_name)
    tab = page.context.new_page()
    try:
        _edit_account(tab, url, name)
        _check_saved(tab, url, name)
    finally:
        tab.close()
    return name


def _done_text(accounts, keep, blocks, result):
    """The box shown when apply_merge has finished: what changed, any problems to fix by hand, and why
    the merge account isn't deleted (result['blockers']) or the question whether to delete it now."""
    k, m = accounts[keep], accounts[1 - keep]
    lines = [f'Renamed "{m["name"]}" to "{result["merge_name"]}" and "{k["name"]}" to "{result["keep_name"]}".']
    if result.get('filled'):
        lines.append(f'Filled in "{result["keep_name"]}" blank {", ".join(result["filled"])} from the merge account.')
    added = [section for section, block in blocks.items() if block]
    lines.append(f'Added the notes from the merge to the top of its {" and ".join(added)}.' if added else
                 'There were no notes to add.')
    moved = ', '.join(ark_common.plural(result['moved'][label], one, several)
                      for label, _, one, several in MOVED if result['moved'].get(label))
    lines.append(f'Moved to "{result["keep_name"]}": {moved}.' if moved else 'No records were moved.')
    holdings = result.get('holdings') or {}
    if holdings.get('updated'):
        lines.append(f'Changed {ark_common.plural(holdings["updated"], "land holding")} '
                     f'({holdings["moved"]} moved to "{result["keep_name"]}").')
    if result['documents']:
        lines.append(f'Copied {ark_common.plural(result["documents"], "document")} to "{result["keep_name"]}".')
    if result['problems']:
        lines += ['', 'Needs a look (not done):'] + [f'- {p}' for p in result['problems']]
    if result['blockers']:
        lines += ['', f'"{result["merge_name"]}" wasn\'t deleted, because:'] + [f'- {b}' for b in result['blockers']]
        lines.append('Delete it in Ark by hand once that\'s sorted out.')
    else:
        lines += ['', 'Both accounts are open in your browser. Review them, then:', '',
                  f'Delete "{result["merge_name"]}" from Ark now? This can\'t be undone. "{result["keep_name"]}" '
                  f'is then renamed "{untagged_name(result["keep_name"])}".']
    return '\n'.join(lines)


# ─── Review window ─────────────────────────────────────────────────────────────

def _shown(value):
    """How the review window shows a field value: the text, "blank", or _NOT_SHOWN for None."""
    return _NOT_SHOWN if value is None else value or 'blank'


def _shown_count(n):
    """How the review window shows a Quick Reference count: the number, "none", or _NOT_SHOWN."""
    return _NOT_SHOWN if n is None else 'none' if n == 0 else f'{n:,}'


def _signer_text(signer):
    """One signer as a line: "Jane Doe (Last Name: Doe, Capacity: Trustee)", blank parts left out."""
    extra = ', '.join(f'{part}: {signer[part]}' for part in ('Last Name', 'Capacity') if signer[part])
    name = signer['Signer'] or '(no name)'
    return f'{name} ({extra})' if extra else name


def _holding_lines(holding):
    """The review window's lines for one land holding (after its name): Legal Entity, Section Name,
    Signers, Title Information."""
    fields = holding['fields']
    signers = '; '.join(_signer_text(s) for s in holding['signers']) or 'none'
    return [f'Legal Entity: {_shown(fields["Legal Entity"])}', f'Section Name: {_shown(fields["Section Name"])}',
            f'Signers: {signers}', f'Title Information: {_shown(fields["Title Information"])}']


def review_rows(accounts):
    """What the review window shows, top to bottom, as ('heading', text) and ('row', label, [one
    text per account]) items: names, links, DETAILS, Parent Account, CHECKED counts, NOTES. Land
    holdings are drawn separately (_holding_lines)."""
    rows = [('heading', 'Account'),
            ('row', 'Name', [a['name'] for a in accounts]),
            ('row', 'Link', [a['url'] for a in accounts])]
    rows += [('row', label, [_shown(a['details'][label]) for a in accounts]) for _, label in DETAILS]
    rows.append(('row', _PARENT, [_shown(a['details'].get(_PARENT)) for a in accounts]))
    rows.append(('heading', 'What each account holds'))
    rows += [('row', label, [_shown_count(a['counts'][label]) for a in accounts]) for label in CHECKED]
    rows.append(('heading', 'Notes'))
    rows += [('row', section, [_shown(a['notes'][section]) for a in accounts]) for section, _ in NOTES]
    return rows


def _review_window(accounts, master=None):
    """Builds (doesn't run) the review window: a scrolling grid with a column per account showing
    review_rows, then each account's land holdings (names open the page in the browser), and a "Keep
    Account N" button per account plus Cancel. Returns the window: a new Tk root, or a Toplevel of
    master (tests share one Tk that way); its .keep is the index of the account picked, None until one is."""
    import tkinter as tk
    from tkinter import font as tkfont
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on scaled displays
    except (AttributeError, OSError):
        pass

    root = tk.Toplevel(master) if master is not None else tk.Tk()
    root.title('Merge Accounts - Review')
    root.geometry('1100x800')
    bold = tkfont.nametofont('TkDefaultFont', root=root).copy()
    bold.configure(weight='bold')
    big = bold.copy()
    big.configure(size=bold.cget('size') + 2)
    link_font = tkfont.nametofont('TkDefaultFont', root=root).copy()
    link_font.configure(underline=True)

    root.keep = None

    def choose(i):
        """Remember account i as the one to keep and close the window."""
        root.keep = i
        root.destroy()

    bar = tk.Frame(root)
    bar.pack(side='bottom', fill='x', padx=10, pady=8)
    tk.Label(bar, text='Nothing has been changed in Ark yet. Pick the account to keep (the other is merged '
                       'into it); Merge asks before changing anything.', anchor='w').pack(side='left')
    tk.Button(bar, text='Cancel', width=12, command=root.destroy).pack(side='right')
    for i in reversed(range(len(accounts))):
        tk.Button(bar, text=f'Keep Account {i + 1}', width=16,
                  command=lambda i=i: choose(i)).pack(side='right', padx=(0, 8))

    canvas = tk.Canvas(root, highlightthickness=0)
    scroll = tk.Scrollbar(root, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    grid = tk.Frame(canvas, padx=12, pady=8)
    canvas.create_window((0, 0), window=grid, anchor='nw')
    grid.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll(int(-e.delta / 120), 'units'))
    wrap = 420  # pixels before a value wraps onto the next line

    def cell(text, row, column, pady=2, **options):
        """A wrapped, left-aligned label in the grid (pady: space above / below its cell); returns it."""
        label = tk.Label(grid, text=text, justify='left', anchor='nw', wraplength=wrap, **options)
        label.grid(row=row, column=column, sticky='nw', padx=6, pady=pady)
        return label

    def link(text, url, row, column):
        """A clickable label that opens url in the browser."""
        label = cell(text, row, column, fg='#0645ad', cursor='hand2', font=link_font)
        label.bind('<Button-1>', lambda e: webbrowser.open(url))

    r = 0
    for i, account in enumerate(accounts):
        cell(f'Account {i + 1}', r, i + 1, font=big)
    r += 1
    for item in review_rows(accounts):
        if item[0] == 'heading':
            cell(item[1], r, 0, font=bold, pady=(12, 2))
        else:
            _, label, texts = item
            cell(label, r, 0, fg='#555555')
            for i, text in enumerate(texts):
                if label == 'Link':
                    link(text, text, r, i + 1)
                else:
                    cell(text, r, i + 1)
        r += 1

    cell('Land Holdings', r, 0, font=bold, pady=(12, 2))
    r += 1
    for i, account in enumerate(accounts):
        rr = r
        if not account['holdings']:
            cell('none' if account['counts']['Land Holdings'] is not None else _NOT_SHOWN, rr, i + 1)
            rr += 1
        for holding in account['holdings']:
            link(holding['name'], holding['url'], rr, i + 1)
            cell('\n'.join(_holding_lines(holding)), rr + 1, i + 1)
            rr += 2
        if account['holdings_missing']:
            cell(f"{account['holdings_missing']} more land holding(s) counted but not listed on the account "
                 'page, so not read', rr, i + 1, fg='#c00000')
    return root


def _show_review(accounts):
    """Shows the review window in front of everything and waits until it's closed. Returns the index
    of the account picked to keep, or None if the window was closed without picking."""
    root = _review_window(accounts)
    root.lift()
    root.attributes('-topmost', True)
    root.after(500, lambda: root.attributes('-topmost', False))
    root.focus_force()
    root.mainloop()
    return root.keep


# ─── Land holdings window ──────────────────────────────────────────────────────

class _SignerRows:
    """One land holding's signers in the land holdings window: a header, then a row of Signer, Last Name
    and Capacity boxes per signer (Capacity offers capacities seen), up to _MAX_SIGNERS; a Last Name or
    Capacity box Ark doesn't have for that signer (_SIGNER_BOX_LIMITS) is disabled. .rows: each row's
    StringVars; .boxes: each row's widgets (both in _SIGNER_PARTS order)."""

    def __init__(self, frame, capacities):
        """frame: where the rows go; capacities: the Capacity box's choices."""
        import tkinter as tk
        self._frame, self._capacities, self.rows, self.boxes = frame, capacities, [], []
        for c, text in enumerate(('Signer', 'Last Name', 'Capacity')):
            tk.Label(frame, text=text, fg='#555555').grid(row=0, column=c, sticky='w', padx=(0, 6))

    def add(self, signer=None):
        """Add a row (filled from signer, a {'Signer', 'Last Name', 'Capacity'} dict); none past _MAX_SIGNERS."""
        import tkinter as tk
        from tkinter import ttk
        if len(self.rows) >= _MAX_SIGNERS:
            return
        values = [tk.StringVar(self._frame, (signer or {}).get(part, '')) for part, _ in _SIGNER_PARTS]
        r = len(self.rows) + 1
        state = ['normal' if r <= _SIGNER_BOX_LIMITS[part] else 'disabled' for part, _ in _SIGNER_PARTS]
        boxes = [tk.Entry(self._frame, textvariable=values[0], width=30, state=state[0]),
                 tk.Entry(self._frame, textvariable=values[1], width=20, state=state[1]),
                 ttk.Combobox(self._frame, textvariable=values[2], values=self._capacities, width=28, state=state[2])]
        for c, box in enumerate(boxes):
            box.grid(row=r, column=c, sticky='w', padx=(0, 6) if c < 2 else 0, pady=1)
        self.rows.append(values)
        self.boxes.append(boxes)

    def set(self, signers):
        """Show signers: fill the rows in order (adding rows as needed) and blank the rest."""
        while len(self.rows) < min(len(signers), _MAX_SIGNERS):
            self.add()
        for r, values in enumerate(self.rows):
            for v, (part, _) in zip(values, _SIGNER_PARTS):
                v.set(signers[r].get(part, '') if r < len(signers) else '')

    def get(self):
        """The signers as typed (clean_signers: trimmed, blank rows left out)."""
        return clean_signers([{part: v.get() for v, (part, _) in zip(values, _SIGNER_PARTS)} for values in self.rows])


def _holdings_window(accounts, keep, master=None):
    """Builds (doesn't run) the land holdings window: every land holding of both accounts (the merge
    account's say they move to the kept one) with its Section Name, Title Information and what it has
    now, a Legal Entity box (pick one the land holdings have, or type one) and its signers' boxes
    (_SignerRows; "Copy signers from" fills them with another land holding's; Add signer); a "Set every
    land holding to" row applies one Legal Entity and signer list to all; Continue / Cancel. Returns the
    window (a new Tk root, or a Toplevel of master); .choices is set by Continue (as holding_choices) and
    stays None otherwise; .editors = {url: {'entity': StringVar, 'signers': _SignerRows, 'copy': Combobox}},
    .all_entity / .all_signers (StringVars) and .apply_all() are the Set every row's (tests use them)."""
    import tkinter as tk
    from tkinter import font as tkfont, ttk
    root = tk.Toplevel(master) if master is not None else tk.Tk()
    root.title('Merge Accounts - Land Holdings')
    root.geometry('1100x800')
    bold = tkfont.nametofont('TkDefaultFont', root=root).copy()
    bold.configure(weight='bold')
    link_font = tkfont.nametofont('TkDefaultFont', root=root).copy()
    link_font.configure(underline=True)
    entities, sets, capacities = holding_options(accounts)
    current = holding_choices(accounts)
    set_names = [label for label, _ in sets] + ['No signers']
    set_signers = dict(sets + [('No signers', [])])
    root.choices, root.editors = None, {}

    def finish():
        """Keep what's in every land holding's boxes as the answer and close the window."""
        root.choices = {url: {_LEGAL_ENTITY: e['entity'].get().strip(), 'signers': e['signers'].get()}
                        for url, e in root.editors.items()}
        root.destroy()

    bar = tk.Frame(root)
    bar.pack(side='bottom', fill='x', padx=10, pady=8)
    tk.Label(bar, text="Pick each land holding's Legal Entity and signers, from the lists or typed in. Nothing is "
                       'changed in Ark until you say Yes.', anchor='w').pack(side='left')
    tk.Button(bar, text='Cancel', width=12, command=root.destroy).pack(side='right')
    tk.Button(bar, text='Continue', width=12, command=finish).pack(side='right', padx=(0, 8))

    top = tk.Frame(root, padx=12, pady=8)
    top.pack(side='top', fill='x')
    tk.Label(top, text='Set every land holding to:', font=bold).grid(row=0, column=0, sticky='w', padx=(0, 8))
    root.all_entity, root.all_signers = tk.StringVar(root), tk.StringVar(root)
    tk.Label(top, text='Legal Entity').grid(row=0, column=1, sticky='w')
    ttk.Combobox(top, textvariable=root.all_entity, values=entities, width=34).grid(row=0, column=2, padx=(4, 12))
    tk.Label(top, text='Signers').grid(row=0, column=3, sticky='w')
    ttk.Combobox(top, textvariable=root.all_signers, values=set_names, state='readonly', width=44).grid(
        row=0, column=4, padx=(4, 12))

    def apply_all():
        """Put the Set every row's Legal Entity (if any) and signers (if picked) into every land holding."""
        for e in root.editors.values():
            if root.all_entity.get().strip():
                e['entity'].set(root.all_entity.get().strip())
            if root.all_signers.get() in set_signers:
                e['signers'].set(set_signers[root.all_signers.get()])
    root.apply_all = apply_all
    tk.Button(top, text='Apply to all', command=apply_all).grid(row=0, column=5)

    canvas = tk.Canvas(root, highlightthickness=0)
    scroll = tk.Scrollbar(root, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    body = tk.Frame(canvas, padx=12, pady=4)
    canvas.create_window((0, 0), window=body, anchor='nw')
    body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll(int(-e.delta / 120), 'units'))

    for i, account in enumerate(accounts):
        role = 'kept' if i == keep else 'its land holdings move to the kept account'
        tk.Label(body, text=f'Account {i + 1}: {account["name"]} ({role})', font=bold, anchor='w').pack(
            fill='x', pady=(12, 2))
        if not account['holdings']:
            tk.Label(body, text='No land holdings', anchor='w').pack(fill='x')
        if account['holdings_missing']:
            tk.Label(body, text=f"{account['holdings_missing']} more land holding(s) counted but not found, so they "
                                "can't be changed here", fg='#c00000', anchor='w').pack(fill='x')
        for h in account['holdings']:
            box = tk.Frame(body, bd=1, relief='groove', padx=8, pady=6)
            box.pack(fill='x', pady=4)
            name = tk.Label(box, text=h['name'], fg='#0645ad', cursor='hand2', font=link_font, anchor='w')
            name.grid(row=0, column=0, columnspan=3, sticky='w')
            name.bind('<Button-1>', lambda e, url=h['url']: webbrowser.open(url))
            fields = h['fields']
            now = '; '.join(_signer_text(s) for s in h['signers']) or 'none'
            tk.Label(box, justify='left', anchor='w', wraplength=1000, fg='#555555',
                     text=f'Section Name: {_shown(fields.get("Section Name"))}    Title Information: '
                          f'{_shown(fields.get("Title Information"))}\nNow: Legal Entity '
                          f'{_shown(fields.get(_LEGAL_ENTITY))}; signers {now}').grid(
                row=1, column=0, columnspan=3, sticky='w')
            entity = tk.StringVar(box, current[h['url']][_LEGAL_ENTITY])
            tk.Label(box, text='Legal Entity').grid(row=2, column=0, sticky='w', pady=(6, 0))
            ttk.Combobox(box, textvariable=entity, values=entities, width=50).grid(
                row=2, column=1, sticky='w', pady=(6, 0))
            tk.Label(box, text='Signers').grid(row=3, column=0, sticky='nw', pady=(6, 0))
            rows_frame = tk.Frame(box)
            rows_frame.grid(row=3, column=1, sticky='w', pady=(6, 0))
            rows = _SignerRows(rows_frame, capacities)
            for signer in current[h['url']]['signers']:
                rows.add(signer)
            if not rows.rows:
                rows.add()
            side = tk.Frame(box)
            side.grid(row=3, column=2, sticky='nw', padx=(12, 0), pady=(6, 0))
            copy = ttk.Combobox(side, values=set_names, state='readonly', width=40)
            copy.set('Copy signers from...')
            copy.pack(anchor='w')
            copy.bind('<<ComboboxSelected>>',
                      lambda e, c=copy, r=rows: r.set(set_signers.get(c.get(), [])))
            tk.Button(side, text='Add signer', command=rows.add).pack(anchor='w', pady=(4, 0))
            root.editors[h['url']] = {'entity': entity, 'signers': rows, 'copy': copy}
    return root


def _show_holdings(accounts, keep):
    """Shows the land holdings window in front of everything and waits until it's closed. Returns the
    choices (as holding_choices) from Continue, or None if it was closed or cancelled."""
    root = _holdings_window(accounts, keep)
    root.lift()
    root.attributes('-topmost', True)
    root.after(500, lambda: root.attributes('-topmost', False))
    root.focus_force()
    root.mainloop()
    return root.choices


def main(argv=None):
    """Open both accounts given on the command line (argv, default sys.argv[1:]), read them and
    their land holdings (_read_account) and show the review window. If an account is picked to keep
    and either has land holdings, the land holdings window (_show_holdings) picks each one's Legal
    Entity and signers (closing it changes nothing); then (holding_plans) if the Yes/No box gets a
    Yes, change both in Ark (apply_merge) and say what was done and what
    wasn't (_done_text). If nothing blocks deleting the merge account, both accounts open in the
    browser for review and that box asks Yes/No (No by default) whether to delete it: Yes deletes it
    (delete_account), takes " (keep)" off the kept account (untag_kept) and says so (a warning if the
    rename fails). Otherwise it's a warning box saying why it wasn't deleted. Returns the accounts read,
    in the order given."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        raise ValueError(f'Merge needs links to two accounts, got {len(args)}')
    ids = [record_id(a) for a in args]
    if ids[0] == ids[1]:
        raise ValueError(f'Both links are the same account: {ACCOUNT_URL.format(ids[0])}')

    with ark_common.ark_page(ACCOUNT_URL.format(ids[0])) as page:
        accounts = [_read_account(page, rid) for rid in ids]
    keep = _show_review(accounts)
    if keep is None:
        return accounts
    blocks = note_blocks(accounts[keep], accounts[1 - keep], datetime.date.today())
    for section, block in blocks.items():
        if block and accounts[keep]['notes'][section] is None:
            raise RuntimeError(f'"{accounts[keep]["name"]}" has no {section} on its page, so the notes from the '
                               'merge have nowhere to go. Nothing was changed in Ark.')
    plans = []
    if any(account['holdings'] for account in accounts):
        choices = _show_holdings(accounts, keep)
        if choices is None:
            return accounts
        plans = holding_plans(accounts, keep, choices)
    folder = ark_common.read_folder('Merges', _DEFAULT_DIR)
    if ark_common.notify('Merge', _confirm_text(accounts, keep, blocks, folder, plans), _ASK_FLAGS) != _IDYES:
        return accounts

    with ark_common.ark_page(accounts[keep]['url']) as page:
        result = apply_merge(page, accounts, keep, blocks, folder, plans)
    done = _done_text(accounts, keep, blocks, result)
    if result['blockers']:
        ark_common.notify('Merge', done, 0x30)
        return accounts
    merge_url = accounts[1 - keep]['url']
    for url in (accounts[keep]['url'], merge_url):
        webbrowser.open(url)
    if ark_common.notify('Merge', done, _ASK_FLAGS) != _IDYES:
        return accounts
    keep_url, final = accounts[keep]['url'], untagged_name(result['keep_name'])
    with ark_common.ark_page(merge_url) as page:
        delete_account(page, merge_url, result['merge_name'])
        try:
            untag_kept(page, keep_url, result['keep_name'])
            text, flags = f'Deleted "{result["merge_name"]}" from Ark and renamed "{result["keep_name"]}" to "{final}".', 0x40
        except Exception as e:  # noqa: BLE001  (the delete went through; say so, and what's left to do)
            text, flags = (f'Deleted "{result["merge_name"]}" from Ark, but couldn\'t rename "{result["keep_name"]}" '
                           f'back to "{final}": {_reason(e)}.\nRename it in Ark by hand:\n{keep_url}', 0x30)
    ark_common.notify('Merge', text, flags)
    return accounts


if __name__ == '__main__':
    ark_common.run_button('Merge', main, os.path.join(ark_common._APP_DIR, 'merge_error.log'))
