"""Fake Ark site and Playwright browser for the Ark script tests (installed by the fake_ark fixture).

The real scripts drive Chromium through Playwright and pull reports with
ark_common.trigger_download. The fake replaces both: a test serves CSV reports by URL,
the script "downloads" them from local files, and the fake records what happened
(downloads, logins, session saves, total time the script asked to wait). Waits are not
slept, so a run that would take minutes against Ark finishes instantly.
"""
import csv
import json
import os
import re
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import ark_common
import playwright.sync_api

LOGIN_PAGE = 'https://login.microsoftonline.com/common/oauth2/authorize'  # where the fake redirects a signed-out page


def write_csv(path, rows, encoding='utf-8'):
    """Writes rows (lists of strings, header first) to path as CSV and returns path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='', encoding=encoding) as f:
        csv.writer(f).writerows(rows)
    return path


def read_csv(path, encoding='utf-8-sig'):
    """Returns every row of a CSV file as a list of lists."""
    with open(path, newline='', encoding=encoding) as f:
        return list(csv.reader(f))


@contextmanager
def locked_like_excel(path):
    """Holds path open the way Excel holds an open file (others may read it but not write it)
    for the length of the with block."""
    import ctypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                     ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    # GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL
    handle = kernel32.CreateFileW(str(path), 0xC0000000, 1, None, 3, 0x80, None)
    assert handle not in (None, ctypes.c_void_p(-1).value), f'could not lock {path}'
    try:
        yield
    finally:
        kernel32.CloseHandle(handle)


class FakeDownload:
    """Stands in for a Playwright Download: a served local file plus Ark's suggested name."""

    def __init__(self, path, suggested_filename):
        """path is the served file; suggested_filename is what Ark would call it."""
        self._path = path
        self.suggested_filename = suggested_filename

    def path(self):
        """Local path of the downloaded file (Playwright's temp file)."""
        return self._path

    def save_as(self, dest):
        """Copies the download to dest."""
        shutil.copyfile(self._path, dest)


class FakePage:
    """Stands in for a Playwright Page. Supports only what the scripts call outside of
    login/trigger_download/upload (which tests replace); anything else raises."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark
        self.url = 'about:blank'
        self.drawer = None  # the Quick Reference label whose side drawer is open, else None
        self.scrolls = 0  # times the open side drawer was scrolled to its bottom (FakeArk.drawer_page)
        self.clicked_document = None  # index of the document whose download button was clicked last
        self.context = None  # the FakeContext that opened it (set by FakeContext.new_page)

    def _cancel_delete(self):
        """Like a browser leaving a page: a delete this page sent that Ark hasn't carried out yet
        (FakeArk.delete_slow) is cancelled."""
        if self._ark.pending_delete and self._ark.pending_delete[0] is self:
            self._ark.cancelled_deletes.append(self._ark.pending_delete[1])
            self._ark.pending_delete = None

    def goto(self, url, **kwargs):
        """Navigates (closing the side drawer and cancelling a delete still on its way from this page);
        lands on the Microsoft login page if that domain still needs a login."""
        self._ark.visited.append(url)
        self._cancel_delete()
        domain = urlparse(url).netloc
        self.url = LOGIN_PAGE if domain in self._ark.needs_login else url
        self.drawer, self.scrolls = None, 0

    def _shown(self, items):
        """items as the open side drawer lists them: FakeArk.drawer_page more per scroll, at most
        FakeArk.drawer_limit."""
        if self._ark.drawer_page:
            items = items[:self._ark.drawer_page * (self.scrolls + 1)]
        return items[:self._ark.drawer_limit] if self._ark.drawer_limit is not None else items

    def wait_for_timeout(self, ms):
        """Records the wait instead of sleeping (a save or delete still on its way is stored meanwhile)."""
        self._ark.waited_ms += ms
        self._ark.store_pending()
        self._ark.store_pending_delete()

    def title(self):
        """'Account - <name>' / 'Land Holding - <name>' on an account / land holding page the test
        served (FakeArk.serve_account / serve_holding), else 'Ark' (any other page, a record not
        served, or one served as never loading)."""
        kind, rid = record_at(self.url)
        name = self._ark.records.get((kind, rid)) if kind else None
        return f'{_TITLE[kind]}{name}' if name else 'Ark'

    def get_by_text(self, text, **kwargs):
        """A locator for text: only Ark's "Account Not Found" / "Land Holding Not Found" messages are
        modeled, shown on an account / land holding page whose record id the test didn't serve."""
        kind, rid = record_at(self.url)
        missing = kind in _NOT_FOUND and (kind, rid) not in self._ark.records
        return _CountLocator(int(missing and text == _NOT_FOUND[kind]))

    def evaluate(self, script, *args):
        """What merge._READ_JS returns on a served account or land holding page: the next of its
        FakeArk.pages reads (the last one repeats). merge._DRAWER_JS(part): the links of that kind in the
        open side drawer (the account's records, as _shown lists them). merge._DOC_ROWS_JS: the names of
        the account's documents in the open Documents drawer (_shown). merge._SCROLL_JS: scrolls the
        drawer (one more FakeArk.drawer_page shown). Nothing else is modeled."""
        kind, rid = record_at(self.url)
        if 'scrollTop' in script:
            self.scrolls += 1
            return None
        if 'tbody' in script:
            if kind != 'account' or self.drawer != 'Documents':
                return []
            return self._shown([doc['name'] for doc in self._ark.documents.get(rid, [])])
        if '#side-drawer' in script:
            if kind != 'account' or self.drawer is None:
                return []
            links = [RELATED_URL.format(_DRAWER_PATHS[label], r) for r, (label, owner) in self._ark.owned.items()
                     if owner == rid and label == self.drawer and _DRAWER_PATHS[label] in args[0]]
            return self._shown(links)
        reads = self._ark.pages.get(rid) if kind else None
        if not reads or 'quick-ref-rel-list' not in script:
            raise AttributeError(f'FakePage.evaluate models only merge._READ_JS on a served record page, not {self.url}')
        self._ark.evaluated.append(rid)
        return reads.pop(0) if len(reads) > 1 else reads[0]

    def reload(self, **kwargs):
        """Records the reload. Like Ark, a save still on its way (FakeArk.pending) is cancelled, and so is a
        delete still on its way from this page."""
        self._ark.reloads.append(self.url)
        self._cancel_delete()
        if self._ark.pending:
            self._ark.cancelled.append(self._ark.pending)
            self._ark.pending = None

    def close(self):
        """Closes the page (FakeArk.pages_closed); a delete still on its way from it is cancelled."""
        self._cancel_delete()
        self._ark.pages_closed += 1

    @contextmanager
    def expect_response(self, predicate, timeout=None):
        """Like Playwright's: .value is the first API answer (FakeArk.responses) sent inside the with block
        that predicate accepts; Playwright's TimeoutError at the end of the block if there's none."""
        info = _ResponseInfo()
        before = len(self._ark.responses)
        yield info
        self._ark.store_pending()  # waiting for the answer lets the save through
        info.value = next((r for r in self._ark.responses[before:] if predicate(r)), None)
        if info.value is None:
            raise playwright.sync_api.TimeoutError('no matching response')

    def get_by_role(self, role, name=None, **kwargs):
        """An account, contact, offer, title request or call page's Edit button (role 'button', name
        'Edit'), an account page's Delete button (top right), or the open window (role 'dialog': edit,
        upload or delete confirmation); nothing else is modeled."""
        kind, rid = record_at(self.url)
        editable = kind in ('account', 'holding') or kind in _RELATED_PATHS
        if editable and role == 'button' and name == 'Edit':
            return _EditButton(self._ark, rid, kind)
        if kind == 'account' and role == 'button' and name == 'Delete':
            return _DeleteButton(self._ark, rid)
        if editable and role == 'dialog':
            return _EditDialog(self._ark, self)
        raise AttributeError(f'FakePage.get_by_role models only the Edit button and window, not {role} {name!r}')

    def locator(self, selector, has_text=None, **kwargs):
        """An account page's Quick Reference entries ('[id="quick-ref-rel-list"]'), in page order as
        merge._READ_JS reads them: .nth(i) is entry i; with has_text, .first is the first entry whose label
        contains that text, any case (as Playwright matches it). Clicking one opens the side drawer on its
        label. The side drawer itself ('#side-drawer', with its Add button) and its document rows
        (merge._DOC_ROW). Nothing else is modeled."""
        if selector == '#side-drawer':
            return _Drawer(self)
        if selector == _DOC_ROW:
            return _DocRows(self)
        assert selector == '[id="quick-ref-rel-list"]', f'FakePage.locator models only Quick Reference entries, not {selector}'
        kind, rid = record_at(self.url)
        labels = [label for label, _ in self._ark.pages[rid][0]['quick']] if kind == 'account' else []
        if has_text is not None:
            labels = [label for label in labels if has_text.lower() in label.lower()]
        return _QuickEntries(self, labels)

    @contextmanager
    def expect_download(self, timeout=None, **kwargs):
        """Like Playwright's: .value is the document whose download button was clicked inside the with
        block (a FakeDownload of its contents, with Ark's download name); TimeoutError if none was."""
        info, self.clicked_document = _ResponseInfo(), None
        yield info
        kind, rid = record_at(self.url)
        if self.clicked_document is None:
            raise playwright.sync_api.TimeoutError('no download started')
        doc = self._ark.documents[rid][self.clicked_document]
        path = os.path.join(self._ark.served_dir, f'doc{len(self._ark.downloaded_documents)}.bin')
        with open(path, 'wb') as f:
            f.write(doc['content'])
        self._ark.downloaded_documents.append(doc['name'])
        info.value = FakeDownload(path, doc['suggested'])

    def __getattr__(self, name):
        """Fails loudly on any Playwright call the fake doesn't model."""
        raise AttributeError(f'FakePage has no {name!r}: the script used a Playwright call '
                             'this test does not fake (replace that function in the test)')


_TITLE = {'account': 'Account - ', 'holding': 'Land Holding - '}  # page title prefix of each record kind
_NOT_FOUND = {'account': 'Account Not Found', 'holding': 'Land Holding Not Found'}  # message for a record not served
# Pages of records an account holds (merge.MOVED), by Quick Reference label: their URL path
_RELATED_PATHS = {'Contacts': '/contacts', 'Offers': '/offers', 'Title Requests': '/title-requests',
                  'Calls & Texts': '/activities'}
RELATED_URL = 'https://ark.phoenixenergy.com{}?recordId={}'  # a contact / offer / title request / call page: path, record id
_DRAWER_PATHS = {**_RELATED_PATHS, 'Land Holdings': '/land-holdings'}  # page path of what each side drawer lists
# An edit window's box for a field label (merge._HOLDING_BOX, and merge._DETAIL_BOX in Edit Account); group 1 = the label
_HOLDING_BOX = re.compile(r'label:text-is\("(.+)"\) \+ :is\(input, textarea\)')
# Edit Account window boxes (Details tab) a merge fills in when blank: label <input> like the ones seen for
# Confirmed Phone Number / Confirmed Email Addresses on 2026-11-11 (the mailing ones assumed the same)
ACCOUNT_DETAIL_BOXES = ['Mailing Street', 'Mailing City', 'Mailing State', 'Mailing Zip Code',
                        'Confirmed Phone Number', 'Confirmed Email Addresses']
# A land holding's signer fields, as Ark has them (seen 2026-11-11): Signer 1-9, but Last Name only for
# Signer 1-2 and Capacity only for Signer 1-3
SIGNER_LABELS = ([f'Signer {n}' for n in range(1, 10)] + [f'Signer {n} Last Name' for n in (1, 2)] +
                 [f'Signer {n} Capacity' for n in (1, 2, 3)])
# Land holding fields the fake's edit window has: label -> its tab (Legal Entity, SIGNER_LABELS)
_HOLDING_EDIT_TABS = {'Legal Entity': 'Details', **dict.fromkeys(SIGNER_LABELS, 'Signer Information')}
# URL path -> record kind ('account', 'holding', or the Quick Reference label of a record an account holds)
_PATHS = {'/accounts': 'account', '/land-holdings': 'holding', **{path: label for label, path in _RELATED_PATHS.items()}}
# merge.CHECKED: the Quick Reference items account_page shows by default
CHECKED_DEFAULT = ['Documents', 'Contacts', 'Offers', 'Title Requests', 'Tasks', 'Calls & Texts', 'Land Holdings']
HOLDING_URL = 'https://ark.phoenixenergy.com/land-holdings?recordId={}'  # a land holding page, as the account page links it


def account_page(counts=None, notes=None, details=None, holdings=()):
    """What merge._READ_JS reads from an account page, laid out like Ark's: Quick Reference entries
    (History and Webinars too, then the expanded tables Ark gives the same id: a multi-line label and
    no count), the detail fields with every section twice (Ark draws the page in two layouts) and an
    unrelated "Notes" field, and the land holding links (each twice).
    counts: {label: n} shown (default every merge.CHECKED item 0, Land Holdings = len(holdings); a
    label left out isn't on the page). notes: {section: text} (default both blank, shown as "-"; None
    leaves the section off). details: {label: value} over the defaults (Created Date
    "11/6/2026 - 9:37:52 AM", the rest blank; None leaves the field off). holdings: land holding record ids."""
    if counts is None:
        counts = {**dict.fromkeys(CHECKED_DEFAULT, 0), 'Land Holdings': len(holdings)}
    notes = {'Account Notes': '', 'Call Notes': '', **(notes or {})}
    details = {'Created Date': '11/6/2026 - 9:37:52 AM', 'Account Disposition': '', 'Mailing Street': '',
               'Mailing City': '', 'Mailing State': '', 'Mailing Zip Code': '', 'Confirmed Phone Number': '',
               'Confirmed Email Addresses': '', **(details or {})}
    quick = [['History', '(141)'], *[[label, f'({n:,})'] for label, n in counts.items()], ['Webinars', '(0)'],
             ['Parent - Dummy Parent (Ruby Mesecher)\nDummy (Ruby Mesecher)', ''], ['', ''],
             ['NAME\n\t\nFIRST NAME\n\t\nPHONE\n\n\nSomeone\n\t\n(1)', '']]
    one = [['Details', 'Account Name', 'Dummy'], ['Investment', 'Notes', 'not the Account Notes']]
    one += [['System Information' if label == 'Created Date' else 'Details', label, value or '-']
            for label, value in details.items() if value is not None]
    labels = {'Account Notes': 'Notes', 'Call Notes': 'Call Notes'}
    one += [[section, labels[section], text or '-'] for section, text in notes.items() if text is not None]
    links = [[HOLDING_URL.format(h), f'Holding {h[:4]}'] for h in holdings]
    return {'quick': quick, 'fields': one + one, 'holdings': links + links}


def holding_page(fields=None, signers=()):
    """What merge._READ_JS reads from a land holding page, laid out like Ark's: no Quick Reference,
    the detail fields twice (two layouts) with others around them, and the SIGNER_LABELS fields.
    fields: {label: value} over the defaults (Legal Entity "Dummy 1", Section Name "31-9N-56W", Title
    Information blank; None leaves it off). signers: (name, last name, capacity) for Signer 1, 2, ...;
    '' for a blank part (a part Ark has no field for must be blank)."""
    fields = {'Legal Entity': 'Dummy 1', 'Section Name': '31-9N-56W', 'Title Information': '', **(fields or {})}
    sections = {'Legal Entity': 'Details', 'Section Name': 'Location Info', 'Title Information': 'Title Info'}
    one = [['Details', 'Account Name', 'Dummy 1'], ['Title Info', 'Title Source', 'Class D']]
    one += [[sections[label], label, value or '-'] for label, value in fields.items() if value is not None]
    signers = list(signers) + [('', '', '')] * (9 - len(signers))
    for n, parts in enumerate(signers, 1):
        for suffix, value in zip(('', ' Last Name', ' Capacity'), parts):
            label = f'Signer {n}{suffix}'
            if label in SIGNER_LABELS:
                one.append(['Signer Information', label, value or '-'])
            else:
                assert not value, f"Ark's land holding has no {label} field"
    return {'quick': [], 'fields': one + one, 'holdings': []}


def record_at(url):
    """(kind, record id) of an Ark account ('account'), land holding ('holding') or contact / offer / title
    request / call page URL (kind = its Quick Reference label), else (None, None)."""
    parts = urlparse(url)
    kind = _PATHS.get(parts.path.rstrip('/'))
    rid = parse_qs(parts.query).get('recordId', [None])[0]
    return (kind, rid) if kind and rid else (None, None)


class _CountLocator:
    """Locator stand-in that only knows how many elements it matches."""

    def __init__(self, n):
        """n = matching elements."""
        self._n = n

    def count(self):
        """Matching elements."""
        return self._n


_NAME_FIELD = 'label:has-text("Account Name") + input'  # merge._NAME_FIELD: the Account Name box
# merge._NOTE_BOXES: the Edit Account window's notes boxes, by section (= the tab holding it)
_NOTE_BOXES = {'Account Notes': 'label:text-is("Notes") + textarea', 'Call Notes': 'label:text-is("Call Notes") + textarea'}
_ACCOUNT_BOX = 'div:has(> label:text-matches("^Account( Name)?[ *]*$"))'  # merge._ACCOUNT_BOX: a record's Account lookup
UPDATE_URL = 'https://api-ark.phoenixenergy.com/update-sb'  # Ark's API call that stores an edited record


class _ResponseInfo:
    """What FakePage.expect_response yields; .value is set when its with block ends."""
    value = None


class _FakeRequest:
    """The request behind a _FakeResponse: method and body."""

    def __init__(self, post_data):
        """post_data: the JSON body sent."""
        self.method, self.post_data = 'POST', post_data


class _FakeResponse:
    """An Ark API answer: url, status, ok and its request."""

    def __init__(self, url, status, post_data):
        """status: HTTP status; post_data: the request body."""
        self.url, self.status, self.ok = url, status, 200 <= status < 300
        self.request = _FakeRequest(post_data)


class _QuickEntries:
    """Quick Reference entries matched by FakePage.locator, in page order: labels."""

    def __init__(self, page, labels):
        """page is the FakePage; labels those of the entries matched."""
        self._page, self._labels = page, labels

    @property
    def first(self):
        """The first entry matched."""
        return self.nth(0)

    def nth(self, index):
        """Entry index of those matched."""
        assert index < len(self._labels), f'no Quick Reference entry {index} matched (of {len(self._labels)})'
        return _QuickEntry(self._page, self._labels[index])


class _QuickEntry:
    """A Quick Reference entry on an account page: clicking it opens the side drawer on its label."""

    def __init__(self, page, label):
        """page is the FakePage; label the entry's."""
        self._page, self._label = page, label

    def click(self, **kwargs):
        """Opens the side drawer listing the account's records of this label (scrolled to the top)."""
        self._page.drawer, self._page.scrolls = self._label, 0


_DOC_ROW = '#side-drawer tbody tr'  # merge._DOC_ROW: a document row of the side drawer
_DOWNLOAD_BUTTON = 'button:has(path[d^="M12 10v2H4v-2"])'  # merge._DOWNLOAD_BUTTON: a row's download button
UPLOAD_URL = 'https://api-ark.phoenixenergy.com/related-bulk-document-upload'  # Ark's call storing uploaded documents
DELETE_URL = 'https://api-ark.phoenixenergy.com/delete-record'  # stand-in for Ark's call deleting a record
# Stand-in for a call Ark may send while deleting that names the account but only reads it (FakeArk.delete_slow)
READ_URL = 'https://api-ark.phoenixenergy.com/get-record'


class _Drawer:
    """The open side drawer; its Add button opens the Upload Account Documents window."""

    def __init__(self, page):
        """page is the FakePage."""
        self._page = page

    def get_by_role(self, role, name=None, **kwargs):
        """The drawer's Add button."""
        assert (role, name) == ('button', 'Add'), f'side drawer: no {role} {name!r} modeled'
        return _AddButton(self._page)


class _AddButton:
    """The Documents drawer's Add button."""

    def __init__(self, page):
        """page is the FakePage."""
        self._page = page

    @property
    def first(self):
        """The button itself."""
        return self

    def click(self, **kwargs):
        """Opens the upload window for the account whose Documents drawer is open."""
        kind, rid = record_at(self._page.url)
        assert self._page.drawer == 'Documents', 'Add clicked with no Documents drawer open'
        self._page._ark.editing = {'what': 'upload', 'rid': rid, 'files': []}


class _DocRows:
    """The document rows of the open drawer; nth(i).locator(merge._DOWNLOAD_BUTTON) is row i's download
    button (FakeArk.download_buttons of them; default 1)."""

    def __init__(self, page, index=None):
        """page is the FakePage; index the row picked with nth."""
        self._page, self._index = page, index

    def nth(self, index):
        """Row index."""
        return _DocRows(self._page, index)

    def locator(self, selector):
        """The row's download button."""
        assert selector == _DOWNLOAD_BUTTON, f'document row: only the download button is modeled, not {selector}'
        return _DownloadButton(self._page, self._index)


class _DownloadButton:
    """A document row's download button."""

    def __init__(self, page, index):
        """page is the FakePage; index the row."""
        self._page, self._index = page, index

    def count(self):
        """How many download buttons the row has (FakeArk.download_buttons)."""
        return self._page._ark.download_buttons

    def click(self, **kwargs):
        """Starts the row's download (see FakePage.expect_download)."""
        self._page.clicked_document = self._index


class _FileInput:
    """The upload window's file picker."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark

    @property
    def first(self):
        """The picker itself."""
        return self

    def wait_for(self, timeout=None, **kwargs):
        """Shown while the upload window is open."""

    def count(self):
        """1 while the upload window is open."""
        return int((self._ark.editing or {}).get('what') == 'upload')

    def set_input_files(self, paths):
        """Picks the files (copied, as the browser reads them then)."""
        for path in paths:
            with open(path, 'rb') as f:
                self._ark.editing['files'].append((os.path.basename(path), f.read()))


class _UploadButton:
    """The upload window's Confirm and Upload button."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark

    def click(self, **kwargs):
        """Sends the files (UPLOAD_URL answered with FakeArk.upload_status) and closes the window; on
        OK each is listed on the account under its file name (FakeArk.listed_as can rename it)."""
        editing, self._ark.editing = self._ark.editing, None
        self._ark.responses.append(_FakeResponse(UPLOAD_URL, self._ark.upload_status, '{}'))
        if self._ark.upload_status != 200:
            return
        for name, content in editing['files']:
            self._ark.uploads.append((editing['rid'], name, content))
            listed = self._ark.listed_as(name)
            if listed is not None:
                self._ark.add_document(editing['rid'], listed, content)


class _DeleteButton:
    """An account page's Delete button (top right): opens Ark's confirmation box."""

    def __init__(self, ark, rid):
        """ark is the owning FakeArk; rid the account shown."""
        self._ark, self._rid = ark, rid

    @property
    def first(self):
        """The button itself."""
        return self

    def click(self, **kwargs):
        """Opens the confirmation box."""
        self._ark.confirming = self._rid


class _ConfirmDelete:
    """The Delete button in Ark's confirmation box: FakeArk.confirm_buttons of them while it's open."""

    def __init__(self, ark, page=None):
        """ark is the owning FakeArk; page the FakePage showing the box."""
        self._ark, self._page = ark, page

    @property
    def first(self):
        """The button itself."""
        return self

    def wait_for(self, timeout=None, **kwargs):
        """Raises Playwright's TimeoutError if the box isn't showing one."""
        if not self.count():
            raise playwright.sync_api.TimeoutError('no Delete in a confirmation box')

    def count(self):
        """How many Delete buttons the box shows."""
        return self._ark.confirm_buttons if self._ark.confirming else 0

    def click(self, **kwargs):
        """Deletes the account: sends DELETE_URL naming it (answered with FakeArk.delete_status; none if
        delete_silent) and, on OK, the account is gone (unless delete_ignored). delete_slow: first a
        READ_URL call naming the account answers OK, and the delete is carried out only once a page waits
        (FakeArk.store_pending_delete); this page leaving or reloading before then cancels it."""
        rid, self._ark.confirming = self._ark.confirming, None
        if self._ark.delete_silent:
            return
        if self._ark.delete_slow:
            self._ark.responses.append(_FakeResponse(READ_URL, 200, json.dumps({'record_id': rid})))
            self._ark.pending_delete = (self._page, rid)
            return
        self._ark.delete_now(rid)


class _EditButton:
    """A record page's Edit button: clicking it opens the record's edit window (FakeArk.editing)."""

    def __init__(self, ark, rid, kind):
        """ark is the owning FakeArk; rid / kind the record whose page shows the button."""
        self._ark, self._rid, self._kind = ark, rid, kind

    @property
    def first(self):
        """The button itself (there's one)."""
        return self

    def wait_for(self, timeout=None, **kwargs):
        """Raises Playwright's TimeoutError on the page of a record the test didn't serve."""
        if self._kind != 'account' and self._rid not in self._ark.owned:
            raise playwright.sync_api.TimeoutError('no Edit button')

    def click(self, **kwargs):
        """Opens the edit window holding the record's saved values: an account's name and notes (on its
        Details tab), a contact / offer / title request / call's Account (its account's name), or a land
        holding's Account, Legal Entity and SIGNER_LABELS boxes (on its Details tab)."""
        if self._kind == 'holding':
            owner = self._ark.owned[self._rid][1]
            shown = {label: v for s, label, v in self._ark.pages[self._rid][-1]['fields']}
            fields = {label: '' if shown.get(label, '-') == '-' else shown[label] for label in _HOLDING_EDIT_TABS}
            self._ark.editing = {'what': 'holding', 'rid': self._rid, 'tab': 'Details', 'fields': fields,
                                 'account': owner, 'search': None, 'tag': self._ark.records[('account', owner)],
                                 'was': (owner, dict(fields))}
            return
        if self._kind != 'account':
            owner = self._ark.owned[self._rid][1]
            self._ark.editing = {'what': 'record', 'rid': self._rid, 'account': owner, 'search': None,
                                 'tag': self._ark.records[('account', owner)], 'was': owner}
            return
        fields = self._ark.pages[self._rid][-1]['fields']
        notes = {section: next((v for s, lab, v in fields if (s, lab) == (section, label)), '-')
                 for section, label in (('Account Notes', 'Notes'), ('Call Notes', 'Call Notes'))}
        notes = {section: '' if v == '-' else v for section, v in notes.items()}
        shown = {label: v for s, label, v in fields if s == 'Details'}
        details = {label: '' if shown[label] == '-' else shown[label] for label in ACCOUNT_DETAIL_BOXES if label in shown}
        name = self._ark.records[('account', self._rid)]
        if self._ark.edit_never_loads:
            name, notes, details = '', dict.fromkeys(notes, ''), dict.fromkeys(details, '')
        self._ark.editing = {'what': 'account', 'rid': self._rid, 'tab': 'Details', 'name': name, 'notes': notes,
                             'details': details, 'was': (name, dict(notes)), 'details_was': dict(details)}


class _EditDialog:
    """The open edit window. Its boxes, tabs and Save act on FakeArk.editing (see _SaveButton)."""

    def __init__(self, ark, page=None):
        """ark is the owning FakeArk; page the FakePage showing the window."""
        self._ark, self._page = ark, page

    def locator(self, selector):
        """The Account Name box (Details tab) or a notes box (its section's tab) of an account's window,
        or the Account lookup of a record's window, as many times as FakeArk.edit_boxes says ('name',
        'Account Notes', 'Call Notes', 'account'; default once); the upload window's file picker; any other
        selector matches nothing."""
        editing = self._ark.editing or {}
        if selector == 'input[type=file]':
            return _FileInput(self._ark)
        if selector == _ACCOUNT_BOX:
            lookup = editing.get('what') in ('record', 'holding')
            return _AccountBox(self._ark, self._ark.edit_boxes.get('account', 1) if lookup else 0)
        holding = _HOLDING_BOX.fullmatch(selector)
        if holding and editing.get('what') == 'account':
            label = holding[1]
            shown = editing['tab'] == 'Details' and label in editing['details']
            return _EditBox(self._ark, ('details', label), self._ark.edit_boxes.get(label, 1) if shown else 0)
        if holding:
            label = holding[1]
            shown = editing.get('what') == 'holding' and editing['tab'] == _HOLDING_EDIT_TABS.get(label)
            return _EditBox(self._ark, ('fields', label), self._ark.edit_boxes.get(label, 1) if shown else 0)
        if selector == _NAME_FIELD:
            tab, key = 'Details', ('name',)
        else:
            section = next((sec for sec, sel in _NOTE_BOXES.items() if sel == selector), None)
            tab, key = section, ('notes', section)
        shown = editing.get('what') == 'account' and tab is not None and editing['tab'] == tab
        return _EditBox(self._ark, key, self._ark.edit_boxes.get(key[-1], 1) if shown else 0)

    def get_by_text(self, text, exact=False, **kwargs):
        """A tab of the window, by its name; in the upload window, "Ready to Upload" under each file
        picked (at most FakeArk.ready_limit). FakeArk.tab_text_elsewhere: without exact=True, the first
        match is other text holding the tab's name (e.g. a box's label), not the tab. FakeArk.tabs_not_exact:
        with exact=True, nothing matches."""
        if text == 'Ready to Upload':
            files = len((self._ark.editing or {}).get('files', []))
            return _CountLocator(files if self._ark.ready_limit is None else min(files, self._ark.ready_limit))
        return _EditTab(self._ark, text, is_tab=exact or not self._ark.tab_text_elsewhere,
                        n=0 if exact and self._ark.tabs_not_exact else 1)

    def get_by_role(self, role, name=None, **kwargs):
        """The window's Save button, the upload window's Confirm and Upload, or the confirmation box's Delete."""
        if (role, name) == ('button', 'Confirm and Upload'):
            return _UploadButton(self._ark)
        if (role, name) == ('button', 'Delete'):
            return _ConfirmDelete(self._ark, self._page)
        assert (role, name) == ('button', 'Save'), f'edit window: no {role} {name!r} modeled'
        return _SaveButton(self._ark)

    def wait_for(self, state='visible', timeout=None):
        """Waits for the window to show or close; raises Playwright's TimeoutError if it doesn't."""
        if (self._ark.editing is None) != (state == 'hidden'):
            raise playwright.sync_api.TimeoutError(f'edit window never became {state}')


class _EditTab:
    """A tab of the Edit Account window."""

    def __init__(self, ark, text, is_tab=True, n=1):
        """ark is the owning FakeArk; text the tab's name; is_tab False: other text holding that name,
        which switches nothing when clicked; n: how many match (0: none)."""
        self._ark, self._text, self._is_tab, self._n = ark, text, is_tab, n

    @property
    def first(self):
        """The tab itself."""
        return self

    def count(self):
        """How many match (every tab asked for is there, unless n says otherwise)."""
        return self._n

    def click(self, **kwargs):
        """Switches the window to this tab (if it is the tab)."""
        assert self._n, 'clicked text that matches nothing'
        if self._is_tab:
            self._ark.editing['tab'] = self._text


class _EditBox:
    """The Account Name box or a notes box: n matches (0 = not on the tab shown). key: where its text is
    in FakeArk.editing (('name',) or ('notes', section))."""

    def __init__(self, ark, key, n):
        """ark is the owning FakeArk."""
        self._ark, self._key, self._n = ark, key, n

    @property
    def first(self):
        """The box itself."""
        return self

    def wait_for(self, timeout=None, **kwargs):
        """Raises Playwright's TimeoutError if the box isn't shown."""
        if not self._n:
            raise playwright.sync_api.TimeoutError('box never showed')

    def count(self):
        """How many boxes match."""
        return self._n

    def input_value(self):
        """The box's text."""
        value = self._ark.editing
        for k in self._key:
            value = value[k]
        return value

    def fill(self, value):
        """Replaces the box's text."""
        assert self._n == 1, 'filled a box that is not shown exactly once'
        holder = self._ark.editing
        for k in self._key[:-1]:
            holder = holder[k]
        holder[self._key[-1]] = value


class _AccountBox:
    """A record's Account lookup: the account as a tag (<p>) with an x (<svg>) that turns it into a
    search box (<input>) listing the accounts named like what's typed (get_by_text)."""

    def __init__(self, ark, n):
        """ark is the owning FakeArk; n how many lookups match (0 = not shown)."""
        self._ark, self._n = ark, n

    @property
    def first(self):
        """The lookup itself."""
        return self

    def wait_for(self, timeout=None, **kwargs):
        """Raises Playwright's TimeoutError if the lookup isn't shown."""
        if not self._n:
            raise playwright.sync_api.TimeoutError('lookup never showed')

    def count(self):
        """How many lookups match."""
        return self._n

    def locator(self, selector):
        """Its tag ('p'), the tag's x ('svg') or the search box ('input')."""
        return {'p': _LookupTag, 'svg': _LookupX, 'input': _LookupSearch}[selector](self._ark)

    def get_by_text(self, text, exact=False):
        """The accounts listed under the search whose name is exactly text (listed only once text is typed
        in full, key by key; FakeArk.search_lag: typed text the list doesn't catch up with)."""
        editing = self._ark.editing
        listed = editing['search'] == text and not self._ark.search_lag
        return _LookupOptions(self._ark, [rid for (kind, rid), name in self._ark.records.items()
                                          if kind == 'account' and name == text] if listed else [])


class _LookupPart:
    """Base for the parts of an Account lookup; .first is the part itself."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark

    @property
    def first(self):
        """The part itself."""
        return self


class _LookupTag(_LookupPart):
    """The account shown as the lookup's tag."""

    def inner_text(self):
        """The account's name ('' after the x)."""
        return self._ark.editing['tag']


class _LookupX(_LookupPart):
    """The tag's x."""

    def click(self, **kwargs):
        """Takes the account off and shows an empty search box."""
        self._ark.editing.update(tag='', search='')


class _LookupSearch(_LookupPart):
    """The lookup's search box."""

    def press_sequentially(self, text, delay=None):
        """Types text key by key (only shown after the x)."""
        assert self._ark.editing['search'] is not None, 'typed in a search box that is not shown'
        self._ark.editing['search'] = text


class _LookupOptions(_LookupPart):
    """Accounts listed under the search with one name: rids."""

    def __init__(self, ark, rids):
        """rids: the accounts listed."""
        super().__init__(ark)
        self._rids = rids

    def count(self):
        """How many are listed."""
        return len(self._rids)

    def click(self, **kwargs):
        """Picks the first: it becomes the record's Account (unless FakeArk.pick_ignored)."""
        if not self._ark.pick_ignored:
            self._ark.editing.update(account=self._rids[0], tag=self._ark.records[('account', self._rids[0])])


class _SaveButton:
    """The edit window's Save button."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark

    def click(self, **kwargs):
        """Saves, like Ark: closes the window and, if something changed, sends UPDATE_URL
        (FakeArk.responses) and leaves the change in FakeArk.pending, stored once the page waits
        (FakeArk.store_pending) and cancelled by a reload before then. The answer's status is
        FakeArk.save_status (403 for a record in FakeArk.refuse_moves); an error changes nothing.
        save_stuck: the window stays open and nothing is sent; save_ignored: Ark answers OK but nothing
        changes."""
        editing = self._ark.editing
        if self._ark.save_stuck:
            return
        self._ark.editing = None
        rid = editing['rid']
        if editing['what'] == 'account':
            details = {label: v for label, v in editing['details'].items() if v != editing['details_was'][label]}
            change = ('account', rid, editing['name'], editing['notes'], details)
            changed = (editing['name'], editing['notes']) != editing['was'] or bool(details)
        elif editing['what'] == 'holding':
            change = ('holding', rid, editing['account'], dict(editing['fields']))
            changed = (editing['account'], editing['fields']) != editing['was']
        else:
            change = ('record', rid, editing['account'])
            changed = editing['account'] != editing['was']
        if not changed:
            return
        status = 403 if rid in self._ark.refuse_moves else self._ark.save_status
        self._ark.responses.append(_FakeResponse(UPDATE_URL, status, json.dumps({'record_id': rid})))
        if self._ark.save_ignored or status != 200:
            return
        self._ark.pending = change  # sent after the window closes


class FakeContext:
    """Stands in for a Playwright BrowserContext."""

    def __init__(self, ark, storage_state):
        """storage_state is the session file the script asked to load (or None)."""
        self._ark = ark
        ark.loaded_session = storage_state

    def new_page(self, **kwargs):
        """Opens a FakePage (its .context is this context, so a script can open another tab)."""
        page = FakePage(self._ark)
        page.context = self
        return page

    def storage_state(self, path=None):
        """Records a session save and writes an empty session file."""
        self._ark.sessions_saved += 1
        if path:
            with open(path, 'w') as f:
                f.write('{}')


class FakeBrowser:
    """Stands in for a Playwright Browser."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark

    def new_context(self, storage_state=None, **kwargs):
        """Opens a FakeContext."""
        return FakeContext(self._ark, storage_state)

    def new_page(self, **kwargs):
        """Opens a FakePage directly (map_uploader does this)."""
        return FakePage(self._ark)

    def close(self):
        """Records that the browser was closed."""
        self._ark.browser_closed = True


class _FakeChromium:
    """Stands in for playwright.chromium."""

    def __init__(self, ark):
        """ark is the owning FakeArk."""
        self._ark = ark

    def launch(self, **kwargs):
        """Launches a FakeBrowser and records the launch options (e.g. headless)."""
        self._ark.launch_options = kwargs
        return FakeBrowser(self._ark)


class FakeArk:
    """Fake Ark site + Playwright. Attributes record what the script did:
    downloads (URLs pulled), logins (success_url of each login), visited (page.goto URLs),
    sessions_saved, browser_closed, waited_ms. needs_login: domains still signed out.
    records / pages / evaluated: account and land holding pages served (serve_account, serve_holding) and read.
    Records an account holds (serve_account related): owned, moves; drawer_limit lists fewer in the drawer.
    Edit windows: editing (the open window: an account's name and notes, or a record's Account, else None),
    saves ((record id, name, notes) per Save stored), responses (its API answers), reloads, pending /
    cancelled (a save is stored only once the page waits; a reload before then cancels it, as in Ark);
    save_stuck / save_ignored / save_status / edit_boxes / edit_never_loads / refuse_moves / search_lag /
    pick_ignored break them. Documents (serve_account documents): documents, downloaded_documents,
    uploads; download_buttons / ready_limit / upload_status / listed_as change how they go. drawer_page:
    the side drawer lists this many more per scroll. Delete: deleted, confirming, pending_delete /
    cancelled_deletes; confirm_buttons / delete_status / delete_ignored / delete_silent / delete_slow change
    how it goes. tab_text_elsewhere: other text in edit windows holds each tab's name; tabs_not_exact: no
    tab's text is exactly its name. pages_closed: pages closed by the script."""

    def __init__(self, served_dir):
        """served_dir holds the CSVs that serve() writes."""
        self._served_dir = served_dir
        self.served_dir = str(served_dir)  # where downloaded documents' contents are written
        self.documents = {}  # account record id -> [{'name' listed, 'suggested' download name, 'content' bytes}]
        self.downloaded_documents = []  # listed name of each document downloaded
        self.download_buttons = 1  # download buttons in each document row
        self.drawer_page = None  # the side drawer lists this many at first and this many more per scroll (None: all)
        self.ready_limit = None  # the upload window shows "Ready to Upload" under at most this many files (None: all)
        self.upload_status = 200  # HTTP status Ark answers an upload with
        self.listed_as = lambda name: name  # file name -> name Ark lists the upload under (None: not listed)
        self.uploads = []  # (account record id, file name, bytes) of each document uploaded
        self.confirming = None  # account whose delete confirmation box is open, else None
        self.confirm_buttons = 1  # Delete buttons in the confirmation box
        self.delete_status = 200  # HTTP status Ark answers a delete with
        self.delete_ignored = False  # Ark answers the delete OK but the account stays
        self.delete_silent = False  # the confirmation's Delete sends nothing
        self.delete_slow = False  # a call that only reads the account answers before the delete is carried out
        self.pending_delete = None  # (page that sent it, account record id) of a delete not carried out yet
        self.cancelled_deletes = []  # account record ids whose delete was cancelled by its page leaving first
        self.tab_text_elsewhere = False  # edit windows have other text holding each tab's name, before the tab
        self.tabs_not_exact = False  # edit window tabs' text isn't exactly their name: exact matches find none
        self.pages_closed = 0  # pages the script closed
        self.deleted = []  # record ids of accounts deleted
        self.holding_saves = []  # (land holding record id, its account, {field label: value}) of each land holding Save stored
        self.detail_saves = []  # (account record id, {ACCOUNT_DETAIL_BOXES label: new value}) of each Save changing them
        self.stale_counts = set()  # Quick Reference labels whose count stays put when records move (as Ark's Land Holdings can)
        self._reports = {}
        self.records = {}  # (kind, record id) -> name shown in its page title (None: the page never loads)
        self.pages = {}  # record id -> [what each merge._READ_JS read returns, in turn; the last repeats]
        self.evaluated = []  # record id of each account / land holding page read with page.evaluate
        self.editing = None  # the open edit window: {'what', 'rid', 'tab', ...} (an account's: 'name', 'notes', 'details'), else None
        self.saves = []  # (record id, name, notes) of each Edit Account Save
        self.reloads = []  # URL of each page.reload
        self.save_stuck = False  # Save leaves the window open and saves nothing
        self.save_ignored = False  # Save closes the window but nothing changes
        self.edit_boxes = {}  # 'name' / 'notes' -> how many of that box the window shows (default 1)
        self.save_status = 200  # HTTP status Ark answers a Save with
        self.edit_never_loads = False  # the Edit Account window's boxes stay empty (the account's data never fills in)
        self.owned = {}  # contact / offer / title request / call record id -> (Quick Reference label, account record id)
        self.moves = []  # (record id, from account, to account) of each record moved
        self.drawer_limit = None  # the side drawer lists at most this many records (None: all)
        self.refuse_moves = set()  # record ids whose Save Ark answers with 403
        self.search_lag = False  # the Account lookup's list never catches up with what's typed
        self.pick_ignored = False  # picking an account in the lookup doesn't take
        self.responses = []  # Ark API answers sent by the page (_FakeResponse), in order
        self.pending = None  # (record id, name, notes) of a Save sent but not stored yet: a reload now cancels it
        self.cancelled = []  # saves cancelled by a reload before Ark stored them
        self.downloads = []
        self.record_counts = {}  # report URL -> the Total Record Count its page shows (serve), None = unreadable
        self.logins = []
        self.visited = []
        self.needs_login = set()
        self.sessions_saved = 0
        self.browser_closed = False
        self.waited_ms = 0
        self.loaded_session = None
        self.launch_options = None

    def serve(self, url, rows, filename='report.csv', records=...):
        """Makes trigger_download(url) return a CSV of rows (header first) named filename. records is
        the Total Record Count its report page shows: by default its data rows; None = no readable count."""
        path = os.path.join(self._served_dir, str(len(self._reports)), filename)
        write_csv(path, rows)
        self._reports[url] = (path, filename)
        self.record_counts[url] = max(len(rows) - 1, 0) if records is ... else records

    def serve_account(self, record_id, name, counts=None, notes=None, details=None, holdings=(), related=None,
                      documents=()):
        """Makes the account page of record_id load with name in its title ("Account - <name>") and what
        account_page(counts, notes, details, holdings) shows; name None = a page that never finishes
        loading. Other account ids show "Account Not Found". Set pages[record_id] to a list of reads for
        a page whose values change while it loads. related: {Quick Reference label: [record ids]} of the
        contacts, offers, title requests and calls it holds (their pages, side drawer and counts).
        documents: its Documents drawer, each a name (downloaded under the same name, as a PDF) or
        (listed name, Ark's download name, bytes)."""
        related = related or {}
        if counts is None:
            counts = {**dict.fromkeys(CHECKED_DEFAULT, 0), 'Land Holdings': len(holdings),
                      **{label: len(ids) for label, ids in related.items()}, 'Documents': len(documents)}
        for label, ids in {**related, 'Land Holdings': holdings}.items():
            self.owned.update({rid: (label, record_id) for rid in ids})
        self.documents[record_id] = [{'name': d, 'suggested': d, 'content': b'%PDF-1.4 ' + d.encode()}
                                     if isinstance(d, str) else {'name': d[0], 'suggested': d[1], 'content': d[2]}
                                     for d in documents]
        self.records[('account', record_id)] = name
        self.pages[record_id] = [account_page(counts, notes, details, holdings)]

    def serve_holding(self, record_id, name, fields=None, signers=()):
        """Makes the land holding page of record_id load with name in its title ("Land Holding - <name>")
        and what holding_page(fields, signers) shows. Other land holding ids show "Land Holding Not Found"."""
        self.records[('holding', record_id)] = name
        self.pages[record_id] = [holding_page(fields, signers)]

    def store_pending(self):
        """Stores the save on its way, if any. An account's: recorded in saves as (record id, name,
        Account Notes, Call Notes), shown on its page. A record's new Account: recorded in moves, its
        Quick Reference count one less on the old account and one more on the new."""
        if not self.pending:
            return
        change, self.pending = self.pending, None
        if change[0] == 'holding':
            _, rid, to, fields = change
            label, was = self.owned[rid]
            self.owned[rid] = (label, to)
            self.holding_saves.append((rid, to, fields))
            if to != was:
                self._bump(was, label, -1)
                self._bump(to, label, 1)
            for read in self.pages[rid]:
                read['fields'] = [[s, lab, (fields[lab] or '-') if lab in fields else v] for s, lab, v in read['fields']]
            return
        if change[0] == 'record':
            _, rid, to = change
            label, was = self.owned[rid]
            self.owned[rid] = (label, to)
            self.moves.append((rid, was, to))
            self._bump(was, label, -1)
            self._bump(to, label, 1)
            return
        _, rid, name, notes, details = change
        self.saves.append((rid, name, notes['Account Notes'], notes['Call Notes']))
        if details:
            self.detail_saves.append((rid, details))
            for read in self.pages[rid]:
                read['fields'] = [[s, label, (details[label] or '-') if s == 'Details' and label in details else v]
                                  for s, label, v in read['fields']]
        self.records[('account', rid)] = name
        labels = {('Account Notes', 'Notes'): 'Account Notes', ('Call Notes', 'Call Notes'): 'Call Notes'}
        for read in self.pages[rid]:
            read['fields'] = [[s, label, (notes[labels[(s, label)]] or '-') if (s, label) in labels else v]
                              for s, label, v in read['fields']]

    def delete_now(self, rid):
        """Carries out a delete of account rid: DELETE_URL answered with delete_status and, on OK, the
        account is gone (unless delete_ignored)."""
        self.responses.append(_FakeResponse(DELETE_URL, self.delete_status, json.dumps({'record_id': rid})))
        if self.delete_status == 200 and not self.delete_ignored:
            self.records.pop(('account', rid))
            self.deleted.append(rid)

    def store_pending_delete(self):
        """Carries out the delete on its way (delete_slow), if any."""
        if self.pending_delete:
            (_, rid), self.pending_delete = self.pending_delete, None
            self.delete_now(rid)

    def _bump(self, account, label, step):
        """Changes the account page's Quick Reference count of label by step (not for stale_counts)."""
        if label in self.stale_counts:
            return
        for read in self.pages.get(account, []):
            read['quick'] = [[lab, f'({int(n.strip("()").replace(",", "")) + step:,})'] if lab == label else [lab, n]
                             for lab, n in read['quick']]

    def add_document(self, account, name, content):
        """Lists a document on the account (its Documents drawer and count), as an upload does."""
        self.documents.setdefault(account, []).append({'name': name, 'suggested': name, 'content': content})
        self._bump(account, 'Documents', 1)

    def trigger_download(self, page, report_url, generation_wait_ms=10_000):
        """Replacement for ark_common.trigger_download: like the real one, first asks about a large
        report (ark_common.confirm_download with its served record count; a No raises
        DownloadCancelled and nothing is downloaded), then returns the served report."""
        if report_url not in self._reports:
            raise AssertionError(f'Script downloaded a report the test did not serve: {report_url}')
        ark_common.confirm_download(report_url, self.record_counts[report_url])
        self.downloads.append(report_url)
        self.waited_ms += generation_wait_ms
        path, filename = self._reports[report_url]
        return FakeDownload(path, filename)

    def login(self, page, username, password, success_url='https://ark.phoenixenergy.com/**'):
        """Replacement for ark_common.login: signs the page's target domain in."""
        assert username and password, 'login called without credentials'
        self.logins.append(success_url)
        domain = urlparse(success_url.replace('**', '')).netloc
        self.needs_login.discard(domain)
        page.url = success_url.replace('**', '')

    @contextmanager
    def sync_playwright(self):
        """Replacement for playwright.sync_api.sync_playwright."""
        class _PW:
            chromium = _FakeChromium(self)
        yield _PW()

    def install(self, monkeypatch):
        """Patches ark_common and every loaded module that bound sync_playwright at import."""
        monkeypatch.setattr(ark_common, 'trigger_download', self.trigger_download)
        monkeypatch.setattr(ark_common, 'login', self.login)
        monkeypatch.setattr(playwright.sync_api, 'sync_playwright', self.sync_playwright)
        for module in list(sys.modules.values()):
            if getattr(module, 'sync_playwright', None) is not None and module is not playwright.sync_api:
                if getattr(module, '__file__', '') and os.path.dirname(os.path.abspath(module.__file__)) \
                        == os.path.dirname(os.path.abspath(ark_common.__file__)):
                    monkeypatch.setattr(module, 'sync_playwright', self.sync_playwright)


class Recorder:
    """Callable that records its calls; used to replace functions like ark_common.upload."""

    def __init__(self, result=None):
        """result is returned from every call."""
        self.calls = []
        self._result = result

    def __call__(self, *args, **kwargs):
        """Records (args, kwargs) and returns result."""
        self.calls.append((args, kwargs))
        return self._result


# (Data Loader status text, whether ark_common.upload should stop waiting). Any "X of Y" row counter means
# Ark has the data and keeps processing it after the browser closes.
LOADER_TEXTS = [
    ('0 of 5', True),            # the counter's first state: already enough
    ('3 of 5', True),
    ('5 of 5', True),
    ('Processed 12 of 12 records', True),
    ('0 of 1,400', True),        # thousands separators
    ('1,400 of 1,400', True),
    ('Uploading...', False),
    ('Save and Upload', False),
    ('Step 1 of', False),        # no second number
]


class _NullLocator:
    """Stand-in for any Playwright locator: every action succeeds and does nothing."""

    def __init__(self):
        """.first returns the same stand-in."""
        self.first = self

    def __getattr__(self, name):
        """Any method (click, wait_for, press_sequentially, ...) is a no-op."""
        return lambda *args, **kwargs: None


class FakeLoaderPage:
    """Stand-in for the Ark Data Loader page ark_common.upload drives. Every click, fill and
    wait succeeds at once; the patterns passed to get_by_text are recorded in text_patterns,
    the (role, name) of each get_by_role in roles, and each page.goto URL in visited."""

    def __init__(self):
        """Starts with nothing recorded."""
        self.text_patterns = []
        self.roles = []
        self.visited = []
        self.keyboard = _NullLocator()

    def goto(self, url, **kwargs):
        """Records the URL opened."""
        self.visited.append(url)

    def locator(self, *args, **kwargs):
        """Any CSS locator."""
        return _NullLocator()

    def get_by_role(self, role, name=None, **kwargs):
        """Records (role, name) of a role locator, e.g. ('option', <pattern for 'Cases'>)."""
        self.roles.append((role, name))
        return _NullLocator()

    def get_by_text(self, pattern, **kwargs):
        """Records the text pattern being waited for."""
        self.text_patterns.append(pattern)
        return _NullLocator()

    def __getattr__(self, name):
        """wait_for_load_state, wait_for_timeout, ... are no-ops."""
        return lambda *args, **kwargs: None


class _FakeDownloadInfo:
    """What page.expect_download yields: .value is the download."""

    def __init__(self, page):
        """page is the FakeReportPage whose click supplies the download."""
        self._page = page

    @property
    def value(self):
        """The download the "Download File" click started."""
        return self._page.download


def ready_card(name, when):
    """Text of Ark's notification for a finished export of report name made at when (datetime), as
    trigger_download reads it: title, report, time and date (seen on 11/3/2026)."""
    return (f'Your file is ready for download! For {name} Download File '
            f'{when:%I:%M %p} {when.month}/{when.day}/{when.year}')


# Ark's Data Loader notifications that never left 0% (in the panel since 10/20/2026); every download
# waited on them for 10 minutes and failed until 11/3/2026
STUCK_UPLOADS = ['Processing 50 records... 0% Complete 11:28 AM 10/20/2026',
                 'Processing 41 records... 0% Complete 11:27 AM 10/20/2026',
                 'Processing 3 records... 0% Complete 09:13 AM 10/20/2026']


class _ReportLocator(_NullLocator):
    """A FakeReportPage locator: records clicks on it as (what, page time waited so far)."""

    def __init__(self, page, what):
        """what names the element, e.g. '#notifications-btn' or 'Download'."""
        super().__init__()
        self._page = page
        self._what = what

    def click(self, *args, **kwargs):
        """Records the click and when it happened; the bell opens or closes the panel and the
        chevron menu's Download asks Ark for the export."""
        self._page.clicks.append((self._what, self._page.waited_ms))
        if self._what == '#notifications-btn':
            self._page.panel_open = not self._page.panel_open
        elif self._what == 'Download':
            self._page.requested = True


class _FileButtons(_NullLocator):
    """The "Download File" buttons in the open notifications panel, top first."""

    def __init__(self, page, index=None):
        """index picks one button (nth); None is all of them (.first: the top one, index 0)."""
        super().__init__()
        self._page = page
        self._index = index

    def nth(self, index):
        """The button at index."""
        return _FileButtons(self._page, index)

    def evaluate_all(self, script):
        """The text of each finished export's notification (one check of the panel)."""
        self._page.look()
        return self._page.files_shown()

    def click(self, *args, **kwargs):
        """Records the click and which file it downloads."""
        files = self._page.files_shown()
        index = self._index or 0
        if index >= len(files):
            raise AssertionError(f'Clicked Download File #{index} but the panel lists {len(files)}')
        self._page.clicked_file = files[index]
        self._page.clicks.append(('Download File', self._page.waited_ms))


class _TextLocator(_NullLocator):
    """Notifications in the open panel whose text matches a pattern (get_by_text)."""

    def __init__(self, page, pattern):
        """pattern is the regex or string searched for."""
        super().__init__()
        self._page = page
        self._pattern = pattern

    def filter(self, **kwargs):
        """filter(visible=True) narrows nothing in the fake."""
        return self

    def count(self):
        """How many notifications match (one check of the panel)."""
        self._page.look()
        search = self._pattern.search if hasattr(self._pattern, 'search') else (lambda t: self._pattern in t)
        return sum(1 for text in self._page.shown() if search(text))


class FakeReportPage:
    """Stand-in for an Ark report page and its notifications panel as ark_common.trigger_download
    drives it. The panel lists old_files (finished exports' notification texts, top first) and
    others (e.g. STUCK_UPLOADS). After Download is clicked, the requested export shows a progress
    card, then new_file appears at the top once the panel has been checked ready_after times before
    (None: it never does). slow_panel: the panel shows no files at the first look, before Download.
    count_texts: what the Total Record Count card reads at each look (page.evaluate), the last one
    repeating; None = the page has no such card. Records clicks as (element, waited_ms at the time),
    total waited_ms, checks after Download, and clicked_file (the notification whose Download File
    was clicked). Waits are not slept."""

    def __init__(self, old_files=(), others=(), new_file='', ready_after=0, slow_panel=False,
                 count_texts=('Total Record Count 13',)):
        """new_file '' means a "Report" export stamped now. The default count is a small report's."""
        self.count_texts = list(count_texts)
        self.count_reads = 0  # times the Total Record Count card was read
        self.old_files = list(old_files)
        self.others = list(others)
        self.new_file = ready_card('Report', datetime.now()) if new_file == '' else new_file
        self.ready_after = ready_after
        self.slow_panel = slow_panel
        self.panel_open = False
        self.requested = False
        self.looks = 0
        self.checks = 0
        self.clicks = []
        self.clicked_file = None
        self.waited_ms = 0
        self.download = FakeDownload('report.csv', 'report.csv')
        self.download_timeout = None  # ms trigger_download allowed the download to start (expect_download's timeout)

    def look(self):
        """Counts one look at the panel (a check, once the export was asked for)."""
        self.looks += 1
        if self.requested:
            self.checks += 1

    def _arrived(self):
        """Whether the requested export's file is listed yet."""
        return self.requested and self.new_file is not None and self.checks > self.ready_after

    def files_shown(self):
        """Finished exports' notification texts in the panel now, top first ([] while it's closed)."""
        if not self.panel_open or (self.slow_panel and not self.requested):
            return []
        return ([self.new_file] if self._arrived() else []) + self.old_files

    def shown(self):
        """Every notification text in the panel now ([] while it's closed)."""
        if not self.panel_open:
            return []
        progress = []
        if self.requested:
            progress = ['Preparing download for report Report ' + ('100% Complete' if self._arrived() else '40% Complete')]
        return progress + self.files_shown() + self.others

    def locator(self, selector, **kwargs):
        """The chevron, #notifications-btn or the "Download File" buttons."""
        if 'Download File' in selector:
            return _FileButtons(self)
        return _ReportLocator(self, selector)

    def get_by_role(self, role, name=None, **kwargs):
        """The chevron menu's Download button."""
        return _ReportLocator(self, 'Download')

    def get_by_text(self, pattern, **kwargs):
        """Notifications whose text matches pattern."""
        return _TextLocator(self, pattern)

    def wait_for_timeout(self, ms):
        """Adds to waited_ms instead of sleeping."""
        self.waited_ms += ms

    def evaluate(self, script):
        """The Total Record Count card's text at this look (count_texts), for ark_common._COUNT_CARD_JS."""
        assert script == ark_common._COUNT_CARD_JS, 'only the record-count script runs on the report page'
        text = self.count_texts[min(self.count_reads, len(self.count_texts) - 1)]
        self.count_reads += 1
        return text

    @contextmanager
    def expect_download(self, timeout=None, **kwargs):
        """Yields the download that the "Download File" click inside the block starts; notes timeout."""
        self.download_timeout = timeout
        yield _FakeDownloadInfo(self)

    def __getattr__(self, name):
        """goto, wait_for_url, wait_for_load_state, ... are no-ops."""
        return lambda *args, **kwargs: None
