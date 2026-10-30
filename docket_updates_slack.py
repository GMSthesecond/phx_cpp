"""Docket Updates Slack, launched by the "Docket Updates Slack" button (bottom of column 1). This is
the Slack version of Docket Updates; since 2026-10-16 Docket Updates itself reads the Hearing Dockets
workbook (docket_updates.py). Its files carry a Slack_ prefix so they don't clash with Docket Updates' in the same folder.

Downloads every message Cheyanne Winn posted in the #docket-updates Slack channel (her posts
and her thread replies) through the Slack Web API, using the user token in settings.ini
[SlackCredentials] token. Writes Parsed_Slack_Messages.csv (ID, Date, Time, Message, Reply To,
Slack TS, Link), newest first, to [Folders] DocketUpdates (default: Desktop\\Docket Updates),
replacing the last export. ID is the local send time plus Slack's
microseconds (YYYYMMDD-HHMMSS-ffffff), so it is unique per message.

Then reads the board order cases out of those messages (the "Case <number> (<applicant>): <type>:
<status>" lines, and the well count: the sum of the case's "(N Wells)" lines; sections and state headings
are not read), downloads the RW cases report from Ark (Slack_RW_Case_Info.csv, same folder) and compares
each case with its RW record(s): Case Status / Order Status and the well count (Number of Wells); Case
Type and applicant are not compared. Writes Slack_Docket_Differences.xlsx (see _DIFF_HEADER): one row per
RW record that differs, with its RW Case Notes, the differing Slack and RW cells highlighted yellow;
matches and cases missing from RW are left out. Writes Slack_Docket_Upload.csv (see _upload_row): a
best-guess Cases Update for the Data Loader with a row per differing RW record whose case has no
sub-cases (those are left to review by hand); it is NOT uploaded. Writes Slack_Not_In_RW.csv: the Slack side of every case missing from RW (case number, applicant, type, status
in RW's Case Status / Order Status terms, well count). Shows a message box with both counts when done. Read-only: nothing is posted to Slack
or uploaded to Ark.
"""
import csv
import json
import os
import re
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime
from html import unescape
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

import ark_common

_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\Docket Updates'  # output folder used when [Folders] DocketUpdates is unset
_CHANNEL_ID = 'C0881BBSFU4'  # Slack id of #docket-updates (survives a channel rename)
_USER_ID = 'U07RLNF4F44'     # Slack id of Cheyanne Winn
_WORKSPACE_URL = 'https://phxenergy.slack.com'  # base of the message links in the Link column
_API_URL = 'https://slack.com/api/'  # Slack Web API base
_PAGE_SIZE = 200  # messages per history / replies request (Slack's recommended page size)
_MAX_RETRIES = 5  # times one request is retried after Slack rate-limits it (HTTP 429)
_KEPT_SUBTYPES = {None, 'thread_broadcast', 'file_share', 'me_message'}  # message kinds exported; joins, topic changes etc. are skipped
_OUTPUT_FILE = 'Parsed_Slack_Messages.csv'  # export file name (overwritten each run)
_OUTPUT_HEADER = ['ID', 'Date', 'Time', 'Message', 'Reply To', 'Slack TS', 'Link']  # export columns
_LINK_RE = re.compile(r'<((?:https?|mailto):[^|>]*)(?:\|([^>]*))?>')  # Slack link markup <url|label> or <url>
_NO_TOKEN_HELP = (  # message box shown when settings.ini has no Slack token
    'No Slack token found.\n\n'
    'Add this to %APPDATA%\\PhoenixLandDept\\settings.ini:\n\n'
    '[SlackCredentials]\n'
    'token = xoxp-...\n\n'
    'The token is the User OAuth Token of a Slack app with the channels:history user scope '
    '(see docs/ARCHITECTURE.md, "Slack token").'
)

_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=d240bce207ca4cac3da5f8dc'  # Ark report of RW cases (uses Record Id, Case Number, Case Status; Order Status, Number of Wells, Case Notes if there)
_REPORT_FILE = 'Slack_RW_Case_Info.csv'  # saved name of the RW cases report (overwritten each run)
_RW_WELLS = 'Number of Wells'  # RW report column with a record's well count (found ignoring case)
_RW_CASE_NOTES = 'Case Notes'  # RW report column with a record's notes, shown but never compared (found ignoring case)
_RW_DATE_SIGNED = 'Date Order Signed'  # RW report column read for the upload, which only ever moves it forward
_OPTIONAL_RW = ('Order Status', _RW_WELLS)  # RW report columns compared only when the report has them
_UPLOAD_FILE = 'Slack_Docket_Upload.csv'  # best-guess Cases Update for the Data Loader; not uploaded (overwritten each run)
_UPLOAD_HEADER = ['Record Id', 'Case Status', 'Order Status', _RW_WELLS, _RW_DATE_SIGNED,
                  _RW_CASE_NOTES]  # upload columns, named as in the RW report; one the report lacks is left out
_DIFF_FILE = 'Slack_Docket_Differences.xlsx'  # workbook of the RW records that differ (overwritten each run)
_DIFF_HEADER = ['Differences', 'Case Number', 'RW Case Number', 'Record Id', 'Posted', 'Slack Status',
                'RW Case Status', 'RW Order Status', 'Slack Well Count', 'RW Well Count', 'RW Case Notes',
                'Notes', 'Link']  # differences workbook columns
_HIGHLIGHT = {  # difference -> the differences workbook columns highlighted for it
    'Status': ('Slack Status', 'RW Case Status'),
    'Order Status': ('Slack Status', 'RW Order Status'),
    'Well Count': ('Slack Well Count', 'RW Well Count'),
}
_YELLOW_FILL = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')  # highlight of a differing cell
_MATCH, _DIFFERS, _NOT_IN_RW = 'Match', 'Differs', 'Not in RW'  # Result values
_MISSING_FILE = 'Slack_Not_In_RW.csv'  # Slack side of every Not in RW row (overwritten each run)
_MISSING_HEADER = ['Case Number', 'Applicant', 'Case Type', 'Case Status', 'Order Status',
                   'Well Count']  # Slack_Not_In_RW.csv columns; statuses in RW's terms
_SPACING_TYPES = ('Establish Spacing', 'Establish Overlapping Spacing', 'Establish Temporary Spacing',
                  'Establish Overlapping Temporary Spacing', 'Establish Permanent Spacing')  # RW types that count as spacing
_TYPE_RULES = [  # (pattern on the uppercased Slack type, RW types it matches or None = no RW type); first hit wins. POOLING and SPACING in any order or joined any way count as Pooling and Spacing. Not compared with RW since 2026-10-27; _parse_header uses it to tell a type from a status
    (re.compile(r'REDEFINE FIELD|BOARD ORDER BY LAW'), None),
    (re.compile(r'^(?=.*POOLING)(?=.*SPACING).*(AMENDMENT|RECONSIDERATION|EXCEPTION)'), _SPACING_TYPES + ('Increased Density',)),
    (re.compile(r'^(?=.*POOLING).*SPACING'), ('Pooling',) + _SPACING_TYPES),
    (re.compile(r'POOLING'), ('Pooling',)),
    (re.compile(r'SPACING'), _SPACING_TYPES),
    (re.compile(r'AUTHORIZE WELLS|ADDITIONAL WELLS|INCREASED DENSITY|CAPACITY'), ('Increased Density',)),
    (re.compile(r'AUTHORIZE DRILLING'), ('Permit to Drill',)),
    (re.compile(r'REVOKE'), ('Show Cause',)),
]
_STATUS_RE = re.compile(r'PARTIALLY GRANTED|GRANTED|GARNTED|DISMISSED|DENIED')  # board results found in a status (GARNTED is a typo seen in Slack)
_EXPECTED_STATUS = {  # Slack result -> (RW Case Status, RW Order Status) it should show
    'GRANTED': ('Ordered', 'Granted'),
    'PARTIALLY GRANTED': ('Ordered', 'Granted'),
    'DENIED': ('Ordered', 'Denied'),
    'DISMISSED': ('Dismissed', ''),
}
_HEADER_RE = re.compile(r'^Cases?\s*(\d[^(:]*)(.*)$', re.I)  # case header: number text, then (applicant): type: status
_WELLS_RE = re.compile(r'^\(?\s*(\d+)[\s-]*WELLS?\b', re.I)  # "(4 Wells)" / "(5 Wells)-(CHEETAH UNIT)" line: a well group and its count


class SlackError(Exception):
    """Slack answered a request with ok: false (bad token, missing scope, ...)."""


def _notify(message, flags=0x40):
    """Show a message box titled "Docket Updates Slack" (info icon unless flags say otherwise)."""
    ark_common.notify('Docket Updates Slack', message, flags)


def _call(method, token, params):
    """GET one Slack Web API method and return its JSON. Waits and retries when rate-limited;
    raises SlackError when Slack answers ok: false."""
    url = _API_URL + method + '?' + urllib.parse.urlencode(params)
    request = Request(url, headers={'Authorization': f'Bearer {token}'})
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
            break
        except HTTPError as e:
            if e.code != 429 or attempt == _MAX_RETRIES:
                raise
            time.sleep(int(e.headers.get('Retry-After') or 1))
    if not data.get('ok'):
        error = data.get('error', 'unknown error')
        if data.get('needed'):
            error += f' (needs the {data["needed"]} scope)'
        raise SlackError(f'Slack {method} failed: {error}')
    return data


def _paged(method, token, params):
    """Every message of a paged history / replies call, following next_cursor."""
    params = dict(params, limit=_PAGE_SIZE)
    while True:
        data = _call(method, token, params)
        yield from data.get('messages', [])
        cursor = (data.get('response_metadata') or {}).get('next_cursor')
        if not cursor:
            return
        params['cursor'] = cursor


def _is_hers(msg):
    """True for a real message (not a join, topic change, ...) sent by _USER_ID."""
    return msg.get('user') == _USER_ID and msg.get('subtype') in _KEPT_SUBTYPES


def _fetch_messages(token):
    """All of _USER_ID's messages in _CHANNEL_ID, posts and thread replies, keyed by Slack ts."""
    found = {}
    for msg in _paged('conversations.history', token, {'channel': _CHANNEL_ID}):
        if _is_hers(msg):
            found[msg['ts']] = msg
        if msg.get('reply_count'):
            for reply in _paged('conversations.replies', token, {'channel': _CHANNEL_ID, 'ts': msg['ts']}):
                if reply['ts'] != msg['ts'] and _is_hers(reply):
                    found[reply['ts']] = reply
    return found


def _clean_text(text):
    """Slack markup to plain text: <url|label> becomes label, <url> becomes url, &amp; etc. decoded."""
    return unescape(_LINK_RE.sub(lambda m: m[2] or m[1], text or ''))


def _sent_at(ts):
    """Local datetime of a Slack ts ("1790971475.113259")."""
    return datetime.fromtimestamp(int(ts.partition('.')[0]))


def _message_id(ts):
    """Unique id from the send time: YYYYMMDD-HHMMSS-ffffff (local time + Slack's microseconds)."""
    micro = ts.partition('.')[2].ljust(6, '0')[:6]
    return f'{_sent_at(ts):%Y%m%d-%H%M%S}-{micro}'


def _permalink(msg):
    """Link that opens the message in Slack (a thread reply opens inside its thread)."""
    link = f'{_WORKSPACE_URL}/archives/{_CHANNEL_ID}/p{msg["ts"].replace(".", "")}'
    thread_ts = msg.get('thread_ts')
    if thread_ts and thread_ts != msg['ts']:
        link += f'?thread_ts={thread_ts}&cid={_CHANNEL_ID}'
    return link


def _rows(messages):
    """CSV rows (see _OUTPUT_HEADER) for messages, newest first. Reply To is the parent's ID."""
    rows = []
    for msg in sorted(messages, key=lambda m: float(m['ts']), reverse=True):
        sent = _sent_at(msg['ts'])
        thread_ts = msg.get('thread_ts')
        reply_to = _message_id(thread_ts) if thread_ts and thread_ts != msg['ts'] else ''
        rows.append([_message_id(msg['ts']), sent.strftime('%m/%d/%Y'), sent.strftime('%I:%M:%S %p'),
                     _clean_text(msg.get('text')), reply_to, msg['ts'], _permalink(msg)])
    return rows


def _write_csv(path, header, rows):
    """Write the header and rows as UTF-8 with a BOM, so Excel shows em dashes and accents."""
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


# ---- Reading cases out of the messages ----

def _status(text):
    """Board result in a Slack status: GRANTED, PARTIALLY GRANTED, DISMISSED, DENIED or ''.
    Struck-out text (~GRANTED~) is ignored and GARNTED reads as GRANTED."""
    m = _STATUS_RE.search(re.sub(r'~[^~]*~', '', text.upper()))
    return '' if not m else 'GRANTED' if m[0] == 'GARNTED' else m[0]


def _rw_types(slack_type):
    """RW Case Types that count as a match for a Slack case type (_TYPE_RULES); None when it has none."""
    norm = ' '.join(slack_type.upper().split())
    for pattern, types in _TYPE_RULES:
        if pattern.search(norm):
            return types
    return None


def _parse_header(line):
    """Fields of a case header line ("Case 32275 (CONTINENTAL RESOURCES, INC): Pooling: GRANTED"), or
    None if the line isn't one. Copes with missing colons, nested parentheses in the applicant, extra
    parenthesized notes before it, several numbers ("196-2025 / 32-2025 FED") and messy statuses.
    status_text is the status as written, so an unrecognized one ("CONTINUED") isn't taken as blank."""
    m = _HEADER_RE.match(line)
    if not m:
        return None
    number = ' '.join(m[1].split())
    rest = m[2].strip()
    groups = []
    while rest.startswith('('):
        depth = 0
        for i, ch in enumerate(rest):
            depth += {'(': 1, ')': -1}.get(ch, 0)
            if depth == 0:
                break
        if depth:  # unbalanced: the rest of the line is the applicant
            groups.append(rest[1:].strip())
            rest = ''
            break
        groups.append(rest[1:i].strip())
        rest = rest[i + 1:].strip()
    parts = [p.strip(' -') for p in rest.split(':')]
    parts = [p for p in parts if p]
    type_text = parts[0] if parts else ''
    status_text = parts[-1] if len(parts) > 1 else ''
    if len(parts) == 1 and _status(parts[0]) and not _rw_types(parts[0]):  # "Case 1 (X): GRANTED"
        type_text, status_text = '', parts[0]
    notes = [f'Status text: {status_text}'] if status_text.upper() not in ('', _status(status_text)) else []
    return {'number': number, 'numbers': re.findall(r'\d+(?:-\d+)*', number),
            'applicant': groups[-1] if groups else '', 'type': type_text, 'status': _status(status_text),
            'status_text': status_text, 'notes': [f'({g})' for g in groups[:-1]] + notes}


def _parse_message(text):
    """Board order cases in one message, in order: the header fields of each "Case ..." line plus
    wells, the sum of the "(N Wells)" lines below it (None when there are none). Other lines (state
    headings, sections, unit names) are skipped, except that a header with no status takes one from
    the first non-blank line below it, so a remark further down ("Prior application DENIED") isn't
    taken as the status."""
    cases, below_header = [], False
    for raw in (text or '').split('\n'):
        line = ' '.join(raw.replace('*', ' ').split())
        if not line.strip('-'):
            continue
        header = _parse_header(line)
        wells = _WELLS_RE.match(line)
        if header:
            cases.append(dict(header, wells=None))
        elif below_header and not cases[-1]['status'] and _status(line) and not re.search(r'\d', line):
            cases[-1]['status'] = _status(line)
        elif cases and wells:
            cases[-1]['wells'] = (cases[-1]['wells'] or 0) + int(wells[1])
        below_header = bool(header)
    return cases


def _has_info(post):
    """True when a post of a case says more than its number: a status (also one not recognized),
    type, applicant or well count. A bare mention like "Case 32384 was corrected" has none of them."""
    return bool(post['status'] or post['status_text'] or post['type'] or post['applicant']
                or post['wells'] is not None)


def _fill_blanks(case, older):
    """Copy each field case leaves blank (status, type, applicant, well count) from older, another
    post of the same case. A status written but not recognized ("CONTINUED") isn't blank. Returns the
    names of the fields copied."""
    filled = []
    if not case['status'] and not case['status_text'] and older['status']:
        case['status'] = older['status']
        filled.append('Status')
    for field, name in (('type', 'Type'), ('applicant', 'Applicant')):
        if not case[field] and older[field]:
            case[field] = older[field]
            filled.append(name)
    if case['wells'] is None and older['wells'] is not None:
        case['wells'] = older['wells']
        filled.append('Well Count')
    return filled


def _cases_from(rows):
    """Cases from the export rows (newest first), each with posted (date) and link added. Posts that
    share any case number are one case ("196-2025" and "196-2025 / 32-2025 FED"), taken from the newest
    post that says more than the number (_has_info), so a bare later mention ("Case 32384 was
    corrected") doesn't replace it. Fields it leaves blank come from the newest older post that has
    them (_fill_blanks). Other posts are added to its notes with their status, each filled field says
    which post it came from, and every number posted is looked up in RW."""
    posts_by_case, by_number = [], {}
    for row in rows:
        for case in _parse_message(row[3]):
            case.update(posted=row[1], link=row[6], msg_id=row[0])
            posts = next((by_number[n] for n in case['numbers'] if n in by_number), None)
            if posts is None:
                posts = []
                posts_by_case.append(posts)
            same = next((p for p in posts if p['msg_id'] == case['msg_id']), None)
            if same is None:
                posts.append(case)
            else:  # listed again in the same message: kept as one post, both blocks' wells counted
                if same['wells'] is not None and case['wells'] is not None:
                    same['wells'] += case['wells']
                same['notes'] += ['Listed more than once in this message'] + case['notes']
                same['numbers'] += [n for n in case['numbers'] if n not in same['numbers']]
                _fill_blanks(same, case)
            for n in case['numbers']:
                by_number.setdefault(n, posts)
    cases = []
    for posts in posts_by_case:
        first = next((p for p in posts if _has_info(p)), posts[0])
        filled = []
        for p in posts:
            if p is first:
                continue
            as_number = f' as {p["number"]}' if p['number'] != first['number'] else ''
            first['notes'].append(f'Also posted {p["posted"]}{as_number}: {p["status"] or "no status"}')
            first['numbers'] += [n for n in p['numbers'] if n not in first['numbers']]
            if _has_info(p):
                filled += [f'{name} from the {p["posted"]} post' for name in _fill_blanks(first, p)]
        first['notes'] += filled
        cases.append(first)
    return cases


# ---- Comparing with RW ----

def _read_rw(path):
    """RW cases from the Ark report as dicts of its columns, and the set of its column names. Names are
    trimmed, and the _UPLOAD_HEADER columns are found ignoring case ("number of wells"). Rows with a
    blank Record Id (Ark's extra list values for the case above) are skipped."""
    canonical = {c.lower(): c for c in _UPLOAD_HEADER}
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        names = {}
        for name in reader.fieldnames or []:
            names[name] = canonical.get(name.strip().lower(), name.strip())
        rows = [{names[k]: (v or '').strip() for k, v in row.items() if isinstance(k, str)} for row in reader]
    return [r for r in rows if r.get('Record Id')], set(names.values())


def _well_number(text):
    """An RW Number of Wells value as an int ('4', '4.0'), or None when blank or not a whole number."""
    try:
        value = float(text.replace(',', ''))
    except ValueError:
        return None
    return int(value) if value.is_integer() else None


def _rw_date(text):
    """An RW date ('10/05/2026', '2026-10-05', '10/05/2026 12:00 AM') as a date, or None when blank or unreadable."""
    try:
        return ark_common.parse_date(text.split(' ')[0]) if text else None
    except ValueError:
        return None


def _candidates(case, index):
    """RW records a case is compared with, by case number: for each of its numbers, the number itself
    and its plain sub-cases (<number>-1, <number>-2, ...). Only when RW has none of those are its other
    sub-cases used: a field-rules case has dozens of Roman-numeral ones (32665-V-1) and an order
    covers only a few of them."""
    found = []
    for n in case['numbers']:
        recs = [r for r in index.get(n.split('-')[0], [])
                if r.get('Case Number') == n or r.get('Case Number', '').startswith(n + '-')]
        plain = [r for r in recs if re.fullmatch(rf'{re.escape(n)}(-\d+)?', r.get('Case Number', ''))]
        found += [r for r in plain or recs if r not in found]
    return sorted(found, key=lambda r: r.get('Case Number', ''))


def _differences(case, rec, columns, rw_wells=None):
    """Fields where an RW record disagrees with the Slack case: Status (Case Status), Order Status and
    Well Count. Order Status and Well Count only when the report has the column (columns); Well Count
    only when Slack gives one, against rw_wells (the case's RW total, see _compare). Type and applicant
    aren't compared."""
    diffs = []
    expected = _EXPECTED_STATUS.get(case['status'])
    if expected:
        if rec.get('Case Status', '').lower() != expected[0].lower():
            diffs.append('Status')
        if 'Order Status' in columns and rec.get('Order Status', '').lower() != expected[1].lower():
            diffs.append('Order Status')
    if case['wells'] is not None and _RW_WELLS in columns and rw_wells != case['wells']:
        diffs.append('Well Count')
    return diffs


def _rw_fields(rec):
    """RW-side columns of a comparison row (a readable well count as a number; Case Notes as given)."""
    wells = rec.get(_RW_WELLS, '')
    return {'RW Case Number': rec.get('Case Number', ''), 'Record Id': rec.get('Record Id', ''),
            'RW Case Status': rec.get('Case Status', ''), 'RW Order Status': rec.get('Order Status', ''),
            'RW Well Count': wells if _well_number(wells) is None else _well_number(wells),
            'RW Case Notes': rec.get(_RW_CASE_NOTES, '')}


def _upload_columns(columns):
    """The _UPLOAD_HEADER columns written: Record Id plus each one the RW report has (a column the
    report lacks can't carry RW's own value forward, and a blank would clear Ark's)."""
    return [c for c in _UPLOAD_HEADER if c == 'Record Id' or c in columns]


def _upload_row(case, rec, columns):
    """(Slack_Docket_Upload.csv row for an RW record, notes for its differences row). Slack's value
    where it has one and RW's own value everywhere else, since the Data Loader writes a blank over Ark:
    - Case Status / Order Status: from Slack's result (_EXPECTED_STATUS); DISMISSED writes a blank
      Order Status on purpose, to clear it.
    - Number of Wells: Slack's well count.
    - Date Order Signed: when Slack has a result, the date of the post the case was taken from, but
      only when that is later than RW's (never moved back; an RW date that can't be read is kept and
      noted). A readable date is written MM/DD/YYYY.
    - Case Notes: that post's link, a space, then RW's notes; left as they are when they already have it."""
    values, notes = dict(rec), []
    expected = _EXPECTED_STATUS.get(case['status'])
    have = rec.get(_RW_DATE_SIGNED, '')
    signed = _rw_date(have)
    if have and signed is None:
        notes.append(f'RW {_RW_DATE_SIGNED} "{have}" not read as a date: kept in the upload')
    elif expected:
        posted = ark_common.parse_date(case['posted'])
        signed = max(signed or posted, posted)
    if expected:
        values['Case Status'], values['Order Status'] = expected
    if signed:
        values[_RW_DATE_SIGNED] = signed.strftime('%m/%d/%Y')
    if case['wells'] is not None:
        values[_RW_WELLS] = str(case['wells'])
    old = rec.get(_RW_CASE_NOTES, '')
    if case['link'] and case['link'] not in old:
        values[_RW_CASE_NOTES] = f'{case["link"]} {old}'.strip()
    return [values.get(c, '') for c in _upload_columns(columns)], notes


def _compare(cases, rw, columns):
    """Comparison rows for every case as dicts of _DIFF_HEADER columns plus Result, Slack Applicant and
    Slack Type (for _missing_rows) and Upload (the record's Slack_Docket_Upload.csv row, or None), and a
    Counter of their Results. A case gets one row per RW record found for it (_candidates; Match /
    Differs), or a Not in RW row when there is none. Slack's well count is the whole case's, so it is
    compared with the total of those records' Number of Wells (a blank or unreadable one counts 0); a
    note gives the total when several records differ from it. A differing record gets an upload row
    (_upload_row) only when it is the case's single RW record and has the case number itself; a case
    with sub-cases or several records (duplicates, two numbers) is noted for review by hand instead."""
    index = defaultdict(list)
    for rec in rw:
        index[rec.get('Case Number', '').split('-')[0]].append(rec)
    rows, counts = [], Counter()

    def add(fields):
        """Append one row from a dict of column values and count its Result."""
        rows.append(fields)
        counts[fields['Result']] += 1

    for case in cases:
        notes = list(case['notes'])
        candidates = _candidates(case, index)
        rw_wells = sum(_well_number(r.get(_RW_WELLS, '')) or 0 for r in candidates)
        if len(candidates) > 1 and case['wells'] is not None and _RW_WELLS in columns and rw_wells != case['wells']:
            notes.append(f"Slack's {case['wells']} wells compared with the {len(candidates)} RW records' "
                         f'total of {rw_wells}')
        if any(r.get('Case Number') not in case['numbers'] for r in candidates):
            held = 'sub-cases'
        elif len(candidates) > 1:
            held = f'{len(candidates)} RW records'
        else:
            held = ''
        slack = {'Case Number': case['number'], 'Posted': case['posted'], 'Slack Applicant': case['applicant'],
                 'Slack Type': case['type'], 'Slack Status': case['status'],
                 'Slack Well Count': '' if case['wells'] is None else case['wells'],
                 'Link': case['link'], 'Upload': None}
        for rec in candidates:
            diffs = _differences(case, rec, columns, rw_wells)
            row_notes = list(notes)
            upload = None
            if diffs and held:
                row_notes.append(f'Not in {_UPLOAD_FILE} ({held}): review by hand')
            elif diffs:
                upload, more = _upload_row(case, rec, columns)
                row_notes += more
            add(dict(slack, Result=_DIFFERS if diffs else _MATCH, Differences=', '.join(diffs), Upload=upload,
                     Notes='; '.join(row_notes), **_rw_fields(rec)))
        if not candidates:
            add(dict(slack, Result=_NOT_IN_RW, Notes='; '.join(notes)))
    return rows, counts


def _write_differences(path, results):
    """Write the Differs rows of results to the differences workbook: header bold, frozen and
    filterable, each difference's Slack and RW cells highlighted (_HIGHLIGHT) and Link clickable."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Differences'
    ws.append(_DIFF_HEADER)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in results:
        if r['Result'] != _DIFFERS:
            continue
        ws.append([r.get(h, '') for h in _DIFF_HEADER])
        for diff in r['Differences'].split(', '):
            for h in _HIGHLIGHT[diff]:
                ws.cell(ws.max_row, _DIFF_HEADER.index(h) + 1).fill = _YELLOW_FILL
        if r['Link']:
            link = ws.cell(ws.max_row, _DIFF_HEADER.index('Link') + 1)
            link.hyperlink, link.style = r['Link'], 'Hyperlink'
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    for i, column in enumerate(ws.columns, 1):
        ws.column_dimensions[get_column_letter(i)].width = min(50, max(len(str(c.value or '')) for c in column) + 2)
    wb.save(path)


def _missing_rows(results):
    """Slack_Not_In_RW.csv rows (see _MISSING_HEADER) from the comparison rows: the Slack side of each Not in
    RW row, with the Slack result as RW's Case Status / Order Status (_EXPECTED_STATUS; both blank when
    Slack has no result) and the Slack well count."""
    out = []
    for r in results:
        if r['Result'] != _NOT_IN_RW:
            continue
        case_status, order_status = _EXPECTED_STATUS.get(r['Slack Status'], ('', ''))
        out.append([r['Case Number'], r['Slack Applicant'], r['Slack Type'], case_status, order_status,
                    r['Slack Well Count']])
    return out


def _summary(rows, out_path):
    """Text of the finish message box about the Slack export: count, date range and where it went."""
    if not rows:
        return f'No messages from Cheyanne Winn found in #docket-updates.\n\nSaved an empty export: {out_path}'
    return (f'Saved {len(rows)} message(s) from Cheyanne Winn in #docket-updates, '
            f'{rows[-1][1]} to {rows[0][1]}.\n\nSaved: {out_path}')


def _compare_summary(case_count, rw_count, results, counts, columns, paths):
    """Text of the finish message box about the RW comparison: result counts, upload rows and the
    differing records held back from it, report columns missing (so not compared or not in the upload)
    and where the differences, upload and Not in RW files (paths, in that order) went."""
    if not case_count:
        return 'No board order cases found in the messages, so nothing was compared with RW.'
    uploads = sum(1 for r in results if r['Upload'])
    held = sum(1 for r in results if r['Result'] == _DIFFERS and not r['Upload'])
    text = (f'Compared {case_count} case(s) from the messages with {rw_count} RW case(s): '
            f'{counts[_MATCH]} match, {counts[_DIFFERS]} differ, {counts[_NOT_IN_RW]} not in RW.\n\n'
            f'{ark_common.plural(uploads, "RW record")} in the upload file; {held} differing record(s) with '
            f'sub-cases left out for review by hand. Nothing was uploaded: check the upload file, then '
            f'load it with the Ark Data Loader as a Cases Update.')
    skipped = [c for c in _OPTIONAL_RW if c not in columns]
    if skipped:
        text += f'\n\nNot compared (no such column in the RW report): {", ".join(skipped)}'
    left_out = [c for c in _UPLOAD_HEADER if c not in _upload_columns(columns)]
    if left_out:
        text += f'\n\nLeft out of the upload (no such column in the RW report): {", ".join(left_out)}'
    return text + '\n\nDifferences: {}\nUpload file: {}\nNot in RW list: {}'.format(*paths)


def main():
    """Read the token, download the messages and write their CSV, then (when they hold any cases)
    download the RW report, compare, write the differences workbook, upload CSV and Not in RW CSV, and
    show the summary. Nothing is uploaded. A missing token, a Slack error or a file locked by Excel gets
    its own message box."""
    try:
        token = ark_common.read_slack_token().strip()
    except KeyError:
        token = ''
    if not token:
        _notify(_NO_TOKEN_HELP, 0x30)
        return

    out_dir = ark_common.read_folder('DocketUpdates', _DEFAULT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, _OUTPUT_FILE)
    diff_path = os.path.join(out_dir, _DIFF_FILE)
    upload_path = os.path.join(out_dir, _UPLOAD_FILE)
    missing_path = os.path.join(out_dir, _MISSING_FILE)

    try:
        rows = _rows(_fetch_messages(token).values())
    except SlackError as e:
        _notify(f'{e}\n\nCheck the token in settings.ini [SlackCredentials].', 0x10)
        return
    try:
        _write_csv(out_path, _OUTPUT_HEADER, rows)
        cases = _cases_from(rows)
        rw, columns = [], set()
        if cases:
            report_path = os.path.join(out_dir, _REPORT_FILE)
            with ark_common.ark_page(_REPORT_URL) as page:
                ark_common.trigger_download(page, _REPORT_URL).save_as(report_path)
            rw, columns = _read_rw(report_path)
        results, counts = _compare(cases, rw, columns)
        _write_differences(diff_path, results)
        _write_csv(upload_path, _upload_columns(columns), [r['Upload'] for r in results if r['Upload']])
        _write_csv(missing_path, _MISSING_HEADER, _missing_rows(results))
    except PermissionError as e:
        _notify(f'Could not write {e.filename or out_path}.\n\nClose it in Excel and click Docket Updates Slack again.',
                0x10)
        return
    _notify(_summary(rows, out_path) + '\n\n' +
            _compare_summary(len(cases), len(rw), results, counts, columns, (diff_path, upload_path, missing_path)))


if __name__ == '__main__':
    ark_common.run_button('Docket Updates Slack', main,
                          os.path.join(ark_common.read_folder('DocketUpdates', _DEFAULT_DIR), 'docket_updates_slack_error.log'))
