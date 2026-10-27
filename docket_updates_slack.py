"""Docket Updates Slack, launched by the "Docket Updates Slack" button (bottom of column 1). This is
the Slack version of Docket Updates; since 2026-10-16 Docket Updates itself reads the Hearing Dockets
workbook (docket_updates.py). Its files carry a Slack_ prefix so they don't clash with Docket Updates' in the same folder.

Downloads every message Cheyanne Winn posted in the #docket-updates Slack channel (her posts
and her thread replies) through the Slack Web API, using the user token in settings.ini
[SlackCredentials] token. Writes Slack_Docket_Updates.csv (ID, Date, Time, Message, Reply To,
Slack TS, Link), newest first, to [Folders] DocketUpdates (default: Desktop\\Docket Updates),
replacing the last export. ID is the local send time plus Slack's
microseconds (YYYYMMDD-HHMMSS-ffffff), so it is unique per message.

Then reads the board order cases out of those messages ("Case <number> (<applicant>): <type>:
<status>", then section lines, optionally split into "(N Wells)" groups), downloads the RW cases
report from Ark (Slack_RW_Case_Info.csv, same folder) and compares each case and well group with its
RW record(s): Case Status / Order Status, Case Type and Sections. Writes Slack_Docket_Differences.csv
(see _DIFF_HEADER) with one row per pairing, plus cases missing from RW and RW sub-cases no group
matched. Also writes Slack_Not_In_RW.csv: the Slack side of every Not in RW row (case number, state as
two letters, applicant, type, status in RW's Case Status / Order Status terms, sections as written).
Shows a message box with both counts when done. Read-only: nothing is posted to Slack
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

import ark_common

_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\Docket Updates'  # output folder used when [Folders] DocketUpdates is unset
_CHANNEL_ID = 'C0881BBSFU4'  # Slack id of #docket-updates (survives a channel rename)
_USER_ID = 'U07RLNF4F44'     # Slack id of Cheyanne Winn
_WORKSPACE_URL = 'https://phxenergy.slack.com'  # base of the message links in the Link column
_API_URL = 'https://slack.com/api/'  # Slack Web API base
_PAGE_SIZE = 200  # messages per history / replies request (Slack's recommended page size)
_MAX_RETRIES = 5  # times one request is retried after Slack rate-limits it (HTTP 429)
_KEPT_SUBTYPES = {None, 'thread_broadcast', 'file_share', 'me_message'}  # message kinds exported; joins, topic changes etc. are skipped
_OUTPUT_FILE = 'Slack_Docket_Updates.csv'  # export file name (overwritten each run)
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

_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=d240bce207ca4cac3da5f8dc'  # Ark report of RW cases (Record Id, Applicant, Case Number, Case Status, Case Type, Sections; Order Status if added)
_REPORT_FILE = 'Slack_RW_Case_Info.csv'  # saved name of the RW cases report (overwritten each run)
_DIFF_FILE = 'Slack_Docket_Differences.csv'  # comparison file name (overwritten each run)
_DIFF_HEADER = ['Result', 'Differences', 'Case Number', 'RW Case Number', 'Record Id', 'Group', 'State',
                'Posted', 'Slack Applicant', 'RW Applicant', 'Slack Type', 'RW Type', 'Slack Status',
                'RW Case Status', 'RW Order Status', 'Slack Sections', 'RW Sections', 'Missing from RW',
                'Extra in RW', 'Notes', 'Link']  # comparison columns
_MATCH, _DIFFERS, _NOT_IN_RW, _NOT_IN_MESSAGE = 'Match', 'Differs', 'Not in RW', 'Not in message'  # Result values
_MISSING_FILE = 'Slack_Not_In_RW.csv'  # Slack side of every Not in RW row (overwritten each run)
_MISSING_HEADER = ['Case Number', 'State', 'Applicant', 'Case Type', 'Case Status', 'Order Status',
                   'Sections']  # Slack_Not_In_RW.csv columns; statuses in RW's terms, sections as written in Slack
_STATE_CODES = dict(zip((  # state heading (title case) -> postal code for Slack_Not_In_RW.csv
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware', 'Florida',
    'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine',
    'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska',
    'Nevada', 'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
    'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas',
    'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming'), (
    'AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH '
    'OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY').split()))
_SPACING_TYPES = ('Establish Spacing', 'Establish Overlapping Spacing', 'Establish Temporary Spacing',
                  'Establish Overlapping Temporary Spacing', 'Establish Permanent Spacing')  # RW types that count as spacing
_TYPE_RULES = [  # (pattern on the uppercased Slack type, RW types it matches or None = not compared); first hit wins. POOLING and SPACING in any order or joined any way count as Pooling and Spacing
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
_STATE_RE = re.compile(r'^[A-Z][A-Z ]*[A-Z]:$')  # state heading such as NORTH DAKOTA:
_BOARD_RE = re.compile(r'^Board Order Updates', re.I)  # message heading, ends the case above it
_WELLS_RE = re.compile(r'^\(?\s*\d+[\s-]*WELLS?\b', re.I)  # "(4 Wells)" line: starts a well group
_SECTION_RE = re.compile(r'^(\d{1,2})\s*-\s*(\d{1,3})\s*([NS])\s*-\s*(\d{1,3})\s*([EW]?)(.*)$', re.I)  # Slack section line: S-TN-RW then the part (-ALL, -W2, ...)
_RW_SECTION_RE = re.compile(r'^(?:([NSEW0-9/]+)-)?(\d{1,2})-(\d{1,3})([NS])-(\d{1,3})([EW])$')  # RW section: optional part prefix (NW-) then S-TN-RW
_PART_RE = re.compile(r'[NS][EW]|[NSEW]2')  # one aliquot step: a quarter (NE) or a half (W2)
_QUARTERS = (('NW', 0, 0), ('NE', 0, 2), ('SW', 2, 0), ('SE', 2, 2))  # quarter name and its top-left cell in the 4x4 grid


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


# ---- Sections: each section is a 4x4 grid of quarter-quarter cells (row 0 north, column 0 west) ----

def _part_cells(part):
    """Grid cells (row, col) an aliquot covers: ALL / AL / blank, W2, NE, S2SE, E2W2, ...
    Steps apply right to left (S2SE is the south half of the SE quarter). None if unreadable."""
    part = part.upper().replace('/', '').replace(' ', '')
    if part in ('', 'ALL', 'AL'):
        return {(r, c) for r in range(4) for c in range(4)}
    steps = _PART_RE.findall(part)
    if ''.join(steps) != part:
        return None
    r0, r1, c0, c1 = 0, 4, 0, 4
    for step in reversed(steps):
        for ch in step:
            if ch in 'NS' and r1 - r0 > 1:
                mid = (r0 + r1) // 2
                r0, r1 = (r0, mid) if ch == 'N' else (mid, r1)
            elif ch in 'EW' and c1 - c0 > 1:
                mid = (c0 + c1) // 2
                c0, c1 = (c0, mid) if ch == 'W' else (mid, c1)
    return {(r, c) for r in range(r0, r1) for c in range(c0, c1)}


def _section_key(sec, twp, tdir, rng, rdir):
    """Section name the way RW writes it, e.g. 11-156N-91W."""
    return f'{int(sec)}-{int(twp)}{tdir.upper()}-{int(rng)}{rdir.upper()}'


def _slack_section(line, state):
    """(cells, notes) of a Slack section line such as 11-156N-91W-W2 or 16-156N-92W-NW, E2; notes are
    any parenthesized remarks. Cells are (section, row, col). None if it isn't a readable section line.
    A missing range direction means W, except in Montana where it is unreadable."""
    m = _SECTION_RE.match(line)
    if not m:
        return None
    sec, twp, tdir, rng, rdir, rest = m.groups()
    if not rdir:
        if state == 'Montana':
            return None
        rdir = 'W'
    notes = [n.strip() for n in re.findall(r'\(([^)]*)\)', rest)]
    rest = re.sub(r'\([^)]*\)', '', rest).strip(' -:,.')
    key = _section_key(sec, twp, tdir, rng, rdir)
    cells = set()
    for part in rest.split(','):
        got = _part_cells(part)
        if got is None:
            return None
        cells |= {(key, r, c) for r, c in got}
    return cells, notes


def _rw_cells(sections):
    """Cells of an RW Sections value ("NW-11-156N-91W, 12-156N-91W"). An unreadable entry becomes
    its own cell (text, None, None), so it always shows as a difference."""
    cells = set()
    for item in (sections or '').split(','):
        item = ''.join(item.split()).upper()
        if not item:
            continue
        m = _RW_SECTION_RE.match(item)
        got = _part_cells(m[1] or 'ALL') if m else None
        if got is None:
            cells.add((item, None, None))
            continue
        key = _section_key(*m.groups()[1:])
        cells |= {(key, r, c) for r, c in got}
    return cells


def _section_order(key):
    """Sort key for section names: township, range, then section; unreadable text last."""
    nums = [int(n) for n in re.findall(r'\d+', key)]
    return (0, nums[1], nums[2], nums[0]) if len(nums) == 3 else (1, 0, 0, 0)


def _describe(cells):
    """RW-style text for cells: 11-156N-91W for a whole section, NW-11-156N-91W for a whole quarter,
    NENW-11-156N-91W for a quarter-quarter, sorted by township, range, section."""
    by_key = defaultdict(set)
    for key, r, c in cells:
        by_key[key].add((r, c))
    out = []
    for key in sorted(by_key, key=lambda k: (_section_order(k), k)):
        got = by_key[key]
        if (None, None) in got or len(got) == 16:
            out.append(key)
            continue
        for name, r0, c0 in _QUARTERS:
            quarter = {(r0 + dr, c0 + dc) for dr in (0, 1) for dc in (0, 1)}
            if quarter <= got:
                out.append(f'{name}-{key}')
            else:
                out += [f'{"NS"[r - r0]}{"WE"[c - c0]}{name}-{key}' for r, c in sorted(quarter & got)]
    return ', '.join(out)


# ---- Reading cases out of the messages ----

def _status(text):
    """Board result in a Slack status: GRANTED, PARTIALLY GRANTED, DISMISSED, DENIED or ''.
    Struck-out text (~GRANTED~) is ignored and GARNTED reads as GRANTED."""
    m = _STATUS_RE.search(re.sub(r'~[^~]*~', '', text.upper()))
    return '' if not m else 'GRANTED' if m[0] == 'GARNTED' else m[0]


def _rw_types(slack_type):
    """RW Case Types that count as a match for a Slack case type (_TYPE_RULES); None when not compared."""
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


def _group(label):
    """A new well group: its label ("4 Wells"), section lines as written, and their cells."""
    return {'label': label, 'lines': [], 'cells': set()}


def _parse_message(text):
    """Board order cases in one message, in order: the header fields plus state, groups (one per
    "(N Wells)" line, else one unnamed group) and notes (unit names and other lines inside the case,
    unreadable section lines marked "Unread:"). A header with no status takes one only from the first
    non-blank line below it, so a remark further down ("Prior application DENIED") stays a note."""
    cases, case, state, below_header = [], None, '', False
    for raw in (text or '').split('\n'):
        line = ' '.join(raw.replace('*', ' ').split())
        header = _parse_header(line)
        if header:
            case = dict(header, state=state, groups=[])
            cases.append(case)
        elif _STATE_RE.match(line):
            state, case = line[:-1].title(), None
        elif _BOARD_RE.match(line):
            case = None
        elif case is None or not line.strip('-'):
            continue
        elif below_header and not case['status'] and _status(line) and not re.search(r'\d', line):
            case['status'] = _status(line)
        elif _WELLS_RE.match(line):
            case['groups'].append(_group(' '.join(re.sub(r'[()]', ' ', line).split())))
        else:
            section = _slack_section(line, state)
            if section is None:
                case['notes'].append(f'Unread: {line}' if re.match(r'\d+\s*-', line) else line)
            else:
                if not case['groups']:
                    case['groups'].append(_group(''))
                group = case['groups'][-1]
                group['lines'].append(line.strip(' ,.'))
                group['cells'] |= section[0]
                case['notes'] += section[1]
        below_header = bool(header)
    for case in cases:
        case['groups'] = [g for g in case['groups'] if g['lines']] or [_group('')]
    return cases


def _has_info(post):
    """True when a post of a case has a status or sections (a bare mention like "Case 32384 was
    corrected" has neither)."""
    return bool(post['status']) or any(g['lines'] for g in post['groups'])


def _fill_blanks(case, older):
    """Copy each field case leaves blank (status, type, applicant, sections) from older, another post
    of the same case. A status written but not recognized ("CONTINUED") isn't blank. Returns the
    names of the fields copied."""
    filled = []
    if not case['status'] and not case['status_text'] and older['status']:
        case['status'] = older['status']
        filled.append('Status')
    for field, name in (('type', 'Type'), ('applicant', 'Applicant')):
        if not case[field] and older[field]:
            case[field] = older[field]
            filled.append(name)
    if not any(g['lines'] for g in case['groups']) and any(g['lines'] for g in older['groups']):
        case['groups'] = older['groups']
        filled.append('Sections')
    return filled


def _cases_from(rows):
    """Cases from the export rows (newest first), each with posted (date) and link added. Posts that
    share any case number are one case ("196-2025" and "196-2025 / 32-2025 FED"), taken from the newest
    post with a status or sections (all its blocks in that message), so a bare later mention ("Case
    32384 was corrected") doesn't replace it. Fields it leaves blank come from the newest older post
    that has them (_fill_blanks). Other posts are added to its notes with their status, each filled
    field says which post it came from, and every number posted is looked up in RW."""
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
            else:  # listed again in the same message: one post with both blocks' well groups
                same['groups'] = [g for g in same['groups'] + case['groups'] if g['lines']] or [_group('')]
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
    """RW cases from the Ark report as dicts of its columns plus cells (from Sections), and whether
    the report has an Order Status column. A row with a blank Record Id continues the case above
    (Ark puts extra list values there): its Sections are added to that case."""
    cases = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        has_order = 'Order Status' in (reader.fieldnames or [])
        for row in reader:
            row = {k: (v or '').strip() for k, v in row.items() if isinstance(k, str)}
            if row.get('Record Id'):
                cases.append(row)
            elif cases and row.get('Sections'):
                cases[-1]['Sections'] = ', '.join(filter(None, [cases[-1].get('Sections'), row['Sections']]))
    for case in cases:
        case['cells'] = _rw_cells(case.get('Sections'))
    return cases, has_order


def _candidates(case, index):
    """RW records for a case's numbers: the number itself and its sub-cases (<number>-...)."""
    found = []
    for n in case['numbers']:
        for rec in index.get(n.split('-')[0], []):
            cn = rec.get('Case Number', '')
            if (cn == n or cn.startswith(n + '-')) and rec not in found:
                found.append(rec)
    return found


def _pair(case, candidates):
    """Pair each well group with RW records: first every record with the same sections, then by
    position (group k with sub-case <number>-k, a lone group with <number> itself), then a single
    group still unpaired takes every record left. Returns (pairs, unpaired groups, unpaired records)."""
    groups = case['groups']
    pairs, used, open_groups = [], [], []
    for g in groups:
        same = [r for r in candidates if g['cells'] and r['cells'] == g['cells']]
        pairs += [(g, r) for r in same]
        used += same
        if not same:
            open_groups.append(g)
    unpaired = []
    for g in open_groups:
        k = groups.index(g) + 1
        names = {f'{n}-{k}' for n in case['numbers']} if len(groups) > 1 else set(case['numbers'])
        hit = [r for r in candidates if r not in used and r.get('Case Number') in names]
        pairs += [(g, r) for r in hit]
        used += hit
        if not hit:
            unpaired.append(g)
    left = [r for r in candidates if r not in used]
    if len(unpaired) == 1 and left:
        pairs += [(unpaired[0], r) for r in left]
        unpaired, left = [], []
    pairs.sort(key=lambda p: (groups.index(p[0]), p[1].get('Case Number', '')))
    return pairs, unpaired, left


def _differences(case, group, rec, has_order):
    """Fields where an RW record disagrees with the Slack case / well group: Status (Case Status),
    Order Status (only when the report has it), Type (_TYPE_RULES) and Sections (skipped when the
    message lists none)."""
    diffs = []
    expected = _EXPECTED_STATUS.get(case['status'])
    if expected:
        if rec.get('Case Status', '').lower() != expected[0].lower():
            diffs.append('Status')
        if has_order and rec.get('Order Status', '').lower() != expected[1].lower():
            diffs.append('Order Status')
    types = _rw_types(case['type'])
    if types is not None and rec.get('Case Type', '').lower() not in {t.lower() for t in types}:
        diffs.append('Type')
    if group['cells'] and group['cells'] != rec['cells']:
        diffs.append('Sections')
    return diffs


def _rw_fields(rec):
    """RW-side columns of a comparison row."""
    return {'RW Case Number': rec.get('Case Number', ''), 'Record Id': rec.get('Record Id', ''),
            'RW Applicant': rec.get('Applicant', ''), 'RW Type': rec.get('Case Type', ''),
            'RW Case Status': rec.get('Case Status', ''), 'RW Order Status': rec.get('Order Status', ''),
            'RW Sections': rec.get('Sections', '')}


def _compare(cases, rw, has_order):
    """Comparison rows (see _DIFF_HEADER) for every case, and a Counter of their Results. Each well
    group gets one row per paired RW record (Match / Differs) or a Not in RW row; RW sub-cases of a
    case that no group paired with get Not in message rows."""
    index = defaultdict(list)
    for rec in rw:
        index[rec.get('Case Number', '').split('-')[0]].append(rec)
    rows, counts = [], Counter()

    def add(fields):
        """Append one row from a dict of column values and count its Result."""
        rows.append([fields.get(h, '') for h in _DIFF_HEADER])
        counts[fields['Result']] += 1

    for case in cases:
        notes = list(case['notes'])
        if case['type'] and _rw_types(case['type']) is None:
            notes.append('Type not compared')
        if not any(g['cells'] for g in case['groups']):
            notes.append('No sections in the message')
        slack = {'Case Number': case['number'], 'State': case['state'], 'Posted': case['posted'],
                 'Slack Applicant': case['applicant'], 'Slack Type': case['type'], 'Slack Status': case['status'],
                 'Notes': '; '.join(notes), 'Link': case['link']}
        pairs, unpaired, left = _pair(case, _candidates(case, index))
        many = len(case['groups']) > 1
        for k, g in enumerate(case['groups'], 1):
            label = f'{k} of {len(case["groups"])}' + (f' ({g["label"]})' if g['label'] else '') if many else g['label']
            row = dict(slack, Group=label, **{'Slack Sections': ', '.join(g['lines'])})
            for pg, rec in pairs:
                if pg is g:
                    diffs = _differences(case, g, rec, has_order)
                    missing = g['cells'] - rec['cells'] if g['cells'] else set()
                    extra = rec['cells'] - g['cells'] if g['cells'] else set()
                    add(dict(row, Result=_DIFFERS if diffs else _MATCH, Differences=', '.join(diffs),
                             **_rw_fields(rec), **{'Missing from RW': _describe(missing),
                                                   'Extra in RW': _describe(extra)}))
            if g in unpaired:
                add(dict(row, Result=_NOT_IN_RW))
        # Only the case itself and plain <number>-<k> sub-cases: a field-rules case has dozens of
        # Roman-numeral sub-cases (32665-V-1) and an order covers only a few of them
        plain = set(case['numbers'])
        left = [r for r in left if r.get('Case Number') in plain
                or any(re.fullmatch(rf'{re.escape(n)}-\d+', r.get('Case Number', '')) for n in plain)]
        for rec in left:
            add(dict(slack, Result=_NOT_IN_MESSAGE, **_rw_fields(rec),
                     Notes='; '.join(['No well group in the message has these sections'] + notes)))
    return rows, counts


def _missing_rows(diff_rows):
    """Slack_Not_In_RW.csv rows (see _MISSING_HEADER) from the comparison rows: the Slack side of each Not in
    RW row, the state as its postal code (kept as is if unknown) and the Slack result as RW's Case
    Status / Order Status (_EXPECTED_STATUS; both blank when Slack has no result)."""
    out = []
    for row in diff_rows:
        r = dict(zip(_DIFF_HEADER, row))
        if r['Result'] != _NOT_IN_RW:
            continue
        case_status, order_status = _EXPECTED_STATUS.get(r['Slack Status'], ('', ''))
        out.append([r['Case Number'], _STATE_CODES.get(r['State'], r['State']), r['Slack Applicant'],
                    r['Slack Type'], case_status, order_status, r['Slack Sections']])
    return out


def _summary(rows, out_path):
    """Text of the finish message box about the Slack export: count, date range and where it went."""
    if not rows:
        return f'No messages from Cheyanne Winn found in #docket-updates.\n\nSaved an empty export: {out_path}'
    return (f'Saved {len(rows)} message(s) from Cheyanne Winn in #docket-updates, '
            f'{rows[-1][1]} to {rows[0][1]}.\n\nSaved: {out_path}')


def _compare_summary(case_count, rw_count, counts, diff_path, missing_path):
    """Text of the finish message box about the RW comparison: result counts and where the
    differences and Not in RW files went."""
    if not case_count:
        return 'No board order cases found in the messages, so nothing was compared with RW.'
    return (f'Compared {case_count} case(s) from the messages with {rw_count} RW case(s): '
            f'{counts[_MATCH]} match, {counts[_DIFFERS]} differ, {counts[_NOT_IN_RW]} not in RW, '
            f'{counts[_NOT_IN_MESSAGE]} RW sub-case(s) not in the message.\n\n'
            f'Saved: {diff_path}\nNot in RW list: {missing_path}')


def main():
    """Read the token, download the messages and write their CSV, then (when they hold any cases)
    download the RW report, compare, write the differences and Not in RW CSVs, and show the summary.
    A missing token, a Slack error or a CSV locked by Excel gets its own message box."""
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
    missing_path = os.path.join(out_dir, _MISSING_FILE)

    try:
        rows = _rows(_fetch_messages(token).values())
    except SlackError as e:
        _notify(f'{e}\n\nCheck the token in settings.ini [SlackCredentials].', 0x10)
        return
    try:
        _write_csv(out_path, _OUTPUT_HEADER, rows)
        cases = _cases_from(rows)
        rw, has_order = [], False
        if cases:
            report_path = os.path.join(out_dir, _REPORT_FILE)
            with ark_common.ark_page(_REPORT_URL) as page:
                ark_common.trigger_download(page, _REPORT_URL).save_as(report_path)
            rw, has_order = _read_rw(report_path)
        diff_rows, counts = _compare(cases, rw, has_order)
        _write_csv(diff_path, _DIFF_HEADER, diff_rows)
        _write_csv(missing_path, _MISSING_HEADER, _missing_rows(diff_rows))
    except PermissionError as e:
        _notify(f'Could not write {e.filename or out_path}.\n\nClose it in Excel and click Docket Updates Slack again.',
                0x10)
        return
    _notify(_summary(rows, out_path) + '\n\n' +
            _compare_summary(len(cases), len(rw), counts, diff_path, missing_path))


if __name__ == '__main__':
    ark_common.run_button('Docket Updates Slack', main,
                          os.path.join(ark_common.read_folder('DocketUpdates', _DEFAULT_DIR), 'docket_updates_slack_error.log'))
