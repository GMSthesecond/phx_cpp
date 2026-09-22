import ctypes
import csv
import os
from datetime import date, datetime

import ark_common


def _notify(message):
    ctypes.windll.user32.MessageBoxW(0, message, 'Case Matchup', 0x40)


_IN_DIR = ark_common.read_folder('CaseMatchup', r'C:\Users\Ethan Mesecher\Desktop\Unit Connect to Cases')
_CASES_PATH = os.path.join(_IN_DIR, 'All_Cases.csv')
_UNITS_PATH = os.path.join(_IN_DIR, 'Phoenix_Bakken_Units_-_Cases_Docket_Information_(Ruby).csv')

_OUTPUT_HEADER = [
    'Record Id', 'Unit #',
    'Spacing Hearing Date', 'Spacing Status', 'Spacing Order Number',
    'Pooling Status', 'Pooling Hearing Date', 'Pooling Order Number',
    'Orders', 'Docket Notes',
    'Existing Cases', 'Notes',
]

_DATE_FORMATS = ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%Y/%m/%d')


def _parse_date(value):
    value = (value or '').strip()
    if not value:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _split_list(value):
    return [part.strip() for part in value.split(',') if part.strip()]


def _split_strs(value):
    return {part.strip().upper() for part in value.split(',') if part.strip()}


def _dedup_ordered(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _read_cases():
    cases = []
    with open(_CASES_PATH, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if len(row) < 13 or not row[0].strip():
                continue
            case_type = row[2].strip()
            case_type_lower = case_type.lower()
            if 'density' in case_type_lower:
                kind = 'density'
            elif 'spacing' in case_type_lower:
                kind = 'spacing'
            elif 'pooling' in case_type_lower:
                kind = 'pooling'
            else:
                kind = 'other'
            continued = row[5].strip().lower() in ('y', 'yes')
            hearing_date = row[3].strip()
            continued_hearing_date = row[12].strip()
            cases.append({
                'case_number': row[1].strip(),
                'case_type': case_type,
                'kind': kind,
                'hearing_date': hearing_date,
                'continued_hearing_date': continued_hearing_date,
                # The date actually used to determine status/hearing dates --
                # once a case is continued, the continued date supersedes the
                # original hearing date as the one that matters.
                'effective_hearing_date': continued_hearing_date if continued and continued_hearing_date else hearing_date,
                'applicant': row[4].strip(),
                'continued': continued,
                'is_partial_match_type': case_type_lower in ('commingling', 'permit protest'),
                'strs': _split_strs(row[6]),
                'order_status': row[10].strip(),
                'order_number': row[11].strip(),
            })
    return cases


def _strs_match(case_strs, unit_strs):
    """A case matches a unit only if they cover the exact same set of STRs
    (order doesn't matter, but the sets must be equal in size and content)."""
    if not case_strs or not unit_strs:
        return False
    return case_strs == unit_strs


def _strs_overlap(case_strs, unit_strs):
    """For Commingling and Permit Protest cases, a match only requires at
    least one shared STR, not an exact set match (a case covering
    24-148N-98W matches a unit covering 24-148N-98W, 25-148N-98W)."""
    if not case_strs or not unit_strs:
        return False
    return not case_strs.isdisjoint(unit_strs)


def _read_units():
    units = []
    with open(_UNITS_PATH, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if len(row) < 14 or not row[11].strip():
                continue
            units.append({
                'unit_number': row[0].strip(),
                'strs': _split_strs(row[2]),
                'cases': row[3].strip(),
                'spacing_hearing_date': row[4].strip(),
                'spacing_status': row[5].strip(),
                'spacing_order_number': row[6].strip(),
                'pooling_status': row[7].strip(),
                'pooling_hearing_date': row[8].strip(),
                'pooling_order_number': row[9].strip(),
                'record_id': row[11].strip(),
                'orders': row[12].strip(),
                'docket_notes': row[13].strip(),
            })
    return units


def _is_denied(case):
    return case['order_status'].strip().lower() == 'denied'


def _is_granted(case):
    return case['order_status'].strip().lower() == 'granted'


def _pick_best(candidates):
    """Priority among non-denied candidates: a Granted case wins; otherwise a
    case whose Applicant includes "Phoenix"; otherwise the most recent
    hearing date. Ties within a tier are broken by the most recent date.
    Denied cases are never selected here -- they only ever produce a note."""
    non_denied = [c for c in candidates if not _is_denied(c)]
    if not non_denied:
        return None

    granted = [c for c in non_denied if _is_granted(c)]
    pool = granted or [c for c in non_denied if 'phoenix' in c['applicant'].lower()] or non_denied

    best, best_parsed = None, None
    for c in pool:
        parsed = _parse_date(c['effective_hearing_date'])
        if best is None or (parsed is not None and (best_parsed is None or parsed > best_parsed)):
            best, best_parsed = c, parsed
    return best


_BLANK_STATUSES = ('', 'not started')


def _compute_status(best, has_denied):
    """Returns (expected_status, source_case). expected_status is None when
    blank or "Not Started" are both acceptable (no relevant, non-denied case)."""
    if best is None:
        return ('Not Started', None) if has_denied else (None, None)
    if _is_granted(best):
        return ('Granted', best)
    hearing = _parse_date(best['effective_hearing_date'])
    if hearing is not None and hearing <= date.today():
        return ('Case Heard', best)
    return ('Docketed', best)


def _status_matches(existing_status, expected_status):
    existing = existing_status.strip().lower()
    if expected_status is None or expected_status == 'Not Started':
        return existing in _BLANK_STATUSES
    return existing == expected_status.lower()


def _mentions_case(text, case_number, keyword):
    """Whether docket-notes text documents the given case alongside a keyword
    (matches the existing staff convention, e.g. "Spacing Case 31842 - DENIED")."""
    if not case_number:
        return False
    text_lower = text.lower()
    return case_number.lower() in text_lower and keyword.lower() in text_lower


def _mentions_case_denied(text, case_number):
    """"Denied" and "Dismissed" are used interchangeably by staff for the same
    outcome, so either word in the docket notes counts as documented."""
    return _mentions_case(text, case_number, 'denied') or _mentions_case(text, case_number, 'dismiss')


def _build_notes(unit, matched):
    notes = []

    denied_numbers = {c['case_number'] for c in matched if _is_denied(c)}
    # Denied/dismissed cases stay on the unit's case list, but their
    # orders/dates/status must not be pulled up into the unit -- they only
    # ever live on the case itself.
    active_matched = [c for c in matched if c['case_number'] not in denied_numbers]

    spacing_cases = [c for c in active_matched if c['kind'] == 'spacing']
    density_cases = [c for c in active_matched if c['kind'] == 'density']
    pooling_cases = [c for c in active_matched if c['kind'] == 'pooling']
    other_cases = [c for c in active_matched if c['kind'] == 'other']

    for c in _dedup_ordered_cases(c for c in matched if _is_denied(c)):
        if not _mentions_case_denied(unit['docket_notes'], c['case_number']):
            notes.append(f"Case {c['case_number']} is DENIED but not noted in Docket Notes")

    best_spacing = _pick_best(spacing_cases)
    if best_spacing:
        if best_spacing['effective_hearing_date'] and best_spacing['effective_hearing_date'] != unit['spacing_hearing_date']:
            notes.append(
                f"Spacing hearing date should be {best_spacing['effective_hearing_date']} "
                f"per Case {best_spacing['case_number']}"
            )
        if best_spacing['order_number'] and best_spacing['order_number'] != unit['spacing_order_number']:
            notes.append(
                f"Spacing order number should be {best_spacing['order_number']} "
                f"per Case {best_spacing['case_number']}"
            )

    spacing_has_denied = any(_is_denied(c) for c in spacing_cases)
    expected_spacing_status, spacing_status_case = _compute_status(best_spacing, spacing_has_denied)
    if not _status_matches(unit['spacing_status'], expected_spacing_status):
        label = expected_spacing_status or 'Not Started'
        suffix = f" per Case {spacing_status_case['case_number']}" if spacing_status_case else ''
        notes.append(f"Spacing status should be {label}{suffix}")

    best_density = _pick_best(density_cases)

    best_pooling = _pick_best(pooling_cases)
    if best_pooling:
        if best_pooling['effective_hearing_date'] and best_pooling['effective_hearing_date'] != unit['pooling_hearing_date']:
            notes.append(
                f"Pooling hearing date should be {best_pooling['effective_hearing_date']} "
                f"per Case {best_pooling['case_number']}"
            )
        if best_pooling['order_number'] and best_pooling['order_number'] != unit['pooling_order_number']:
            notes.append(
                f"Pooling order number should be {best_pooling['order_number']} "
                f"per Case {best_pooling['case_number']}"
            )

    pooling_has_denied = any(_is_denied(c) for c in pooling_cases)
    expected_pooling_status, pooling_status_case = _compute_status(best_pooling, pooling_has_denied)
    if not _status_matches(unit['pooling_status'], expected_pooling_status):
        label = expected_pooling_status or 'Not Started'
        suffix = f" per Case {pooling_status_case['case_number']}" if pooling_status_case else ''
        notes.append(f"Pooling status should be {label}{suffix}")

    order_bearing = [c for c in spacing_cases + density_cases + pooling_cases if not _is_denied(c) and c['order_number']]
    distinct_orders = _dedup_ordered(c['order_number'] for c in order_bearing)
    if len(distinct_orders) > 3:
        detail = ', '.join(f"{c['order_number']} (Case {c['case_number']})" for c in order_bearing)
        notes.append(f"More than 3 spacing/density/pooling orders matched to this unit: {detail}")

    existing_orders = set(_split_list(unit['orders']))
    orders_sources = [('Spacing', best_spacing), ('Density', best_density), ('Pooling', best_pooling)]
    for label, c in orders_sources:
        if c and c['order_number'] and c['order_number'] not in existing_orders:
            notes.append(f"{label} order {c['order_number']} (Case {c['case_number']}) should be listed in Orders")
    for c in other_cases:
        if c['order_number'] and c['order_number'] not in existing_orders:
            notes.append(f"Order {c['order_number']} from Case {c['case_number']} is not listed in Orders")

    order_to_case = {c['order_number']: c for c in matched if c['order_number']}
    order_fields = [
        ('Spacing Order Number', unit['spacing_order_number']),
        ('Pooling Order Number', unit['pooling_order_number']),
        ('Orders', unit['orders']),
    ]
    for field_label, field_value in order_fields:
        for order_number in _split_list(field_value):
            case = order_to_case.get(order_number)
            if case is None:
                notes.append(f"{field_label} lists order {order_number}, which doesn't match any attached case")
            elif case['case_number'] in denied_numbers:
                notes.append(
                    f"{field_label} lists order {order_number} from Case {case['case_number']}, "
                    f"which is denied/dismissed -- that order should only be recorded on the case, not the unit"
                )

    old_numbers = _split_list(unit['cases'])
    matched_numbers = {c['case_number'] for c in matched}
    for n in _dedup_ordered(c['case_number'] for c in matched):
        if n not in old_numbers:
            notes.append(f"Case {n} matches this unit but is missing from Cases")
    for n in old_numbers:
        if n not in matched_numbers:
            notes.append(f"Case {n} is listed in Cases but no longer matches this unit's STRs")

    return '\n'.join(notes)


def _dedup_ordered_cases(cases):
    seen = set()
    out = []
    for c in cases:
        if c['case_number'] not in seen:
            seen.add(c['case_number'])
            out.append(c)
    return out


def _process(units, cases):
    for unit in units:
        matched = [
            c for c in cases
            if (_strs_overlap(c['strs'], unit['strs']) if c['is_partial_match_type']
                else _strs_match(c['strs'], unit['strs']))
        ]
        unit['notes'] = _build_notes(unit, matched)
    return units


def _write_output(units, out_path):
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(_OUTPUT_HEADER)
        for unit in units:
            writer.writerow([
                unit['record_id'], unit['unit_number'],
                unit['spacing_hearing_date'], unit['spacing_status'], unit['spacing_order_number'],
                unit['pooling_status'], unit['pooling_hearing_date'], unit['pooling_order_number'],
                unit['orders'], unit['docket_notes'],
                unit['cases'], unit['notes'],
            ])


def main():
    os.makedirs(_IN_DIR, exist_ok=True)
    cases = _read_cases()
    units = _read_units()
    units = _process(units, cases)

    today_file_str = date.today().strftime('%m.%d.%Y')
    out_path = os.path.join(_IN_DIR, f'Case_Matchup_Export.{today_file_str}.csv')
    _write_output(units, out_path)

    flagged_count = sum(1 for unit in units if unit['notes'])
    _notify(
        f'Processed {len(units)} unit(s) against {len(cases)} case(s).\n'
        f'{flagged_count} unit(s) have notes to review.\n\n'
        f'Saved: {out_path}'
    )


if __name__ == '__main__':
    import traceback
    try:
        main()
    except Exception:
        log_path = os.path.join(_IN_DIR, 'case_matchup_error.log')
        os.makedirs(_IN_DIR, exist_ok=True)
        with open(log_path, 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
        ctypes.windll.user32.MessageBoxW(
            0, f'Case Matchup failed. See:\n{log_path}', 'Case Matchup', 0x10
        )
        raise
