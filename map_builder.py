import ctypes
import csv
import os
import re
import zipfile
from datetime import date, timedelta

import requests
import shapefile  # pyshp
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

import ark_common

_MAPS_DIR = ark_common.read_folder('Maps', r'C:\Users\Ethan Mesecher\Desktop\Maps')
_UNITS_CSV = os.path.join(_MAPS_DIR, 'Units.csv')

_BLM_TOWNSHIP_URL    = 'https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/1/query'
_BLM_SECTION_URL     = 'https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/2/query'
_BLM_INTERSECTED_URL = 'https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/3/query'

# Aliquot parts (fractional sections): BLM publishes official quarter-quarter (40-acre)
# geometry directly, so halves and quarters are built by combining those rather than by
# bisecting a section polygon ourselves — safer, since sections aren't always perfect
# squares (correction lines, government lots, etc).
_QUARTERS = ('NE', 'NW', 'SE', 'SW')
_HALF_TO_QUARTERS = {'N2': ('NE', 'NW'), 'S2': ('SE', 'SW'), 'E2': ('NE', 'SE'), 'W2': ('NW', 'SW')}
_VALID_ALIQUOTS = set(_QUARTERS) | set(_HALF_TO_QUARTERS) | {inner + outer for inner in _QUARTERS for outer in _QUARTERS}


def _qq_labels_for(aliquot):
    """Returns the BLM quarter-quarter labels making up an aliquot part: a QQ code like
    'NENE' maps to itself; a quarter like 'NE' expands to its 4 QQ pieces; a half like
    'N2' expands to the 8 QQ pieces of its 2 constituent quarters."""
    if len(aliquot) == 4:
        return [aliquot]
    if aliquot in _QUARTERS:
        return [inner + aliquot for inner in _QUARTERS]
    outer_quarters = _HALF_TO_QUARTERS[aliquot]
    return [inner + outer for outer in outer_quarters for inner in _QUARTERS]

# Many states (Utah included — see Duchesne/Uintah counties, surveyed under the separate
# Uintah Meridian rather than Salt Lake) were surveyed under more than one principal
# meridian, and an STR alone doesn't say which one it belongs to. Rather than hardcoding
# a guess per state, the meridians actually used in a given state are looked up from BLM
# and each is tried in turn until one has data for the STR.
_state_meridian_cache = {}


def _meridians_for_state(state_abbr):
    if state_abbr not in _state_meridian_cache:
        params = {
            'f': 'json',
            'where': f"STATEABBR='{state_abbr}'",
            'outFields': 'PRINMERCD',
            'returnGeometry': 'false',
            'returnDistinctValues': 'true',
            'orderByFields': 'PRINMERCD',
        }
        resp = requests.get(_BLM_TOWNSHIP_URL, params=params, timeout=30)
        resp.raise_for_status()
        codes = [f['attributes']['PRINMERCD'] for f in resp.json().get('features', [])]
        _state_meridian_cache[state_abbr] = codes
    return _state_meridian_cache[state_abbr]

_STR_RE = re.compile(
    r'^\s*(?:([A-Za-z0-9]{2,4})-)?(\d{1,2})-(\d{1,3})([NS])-(\d{1,3})([EW])(?:-([A-Za-z0-9]{2,4}))?\s*$',
    re.IGNORECASE
)

# Matches the projection DI's own shapefile exports use (WGS 84 Web Mercator), and happens
# to be the BLM service's native spatial reference too, so no reprojection is needed.
_PRJ_WKT = (
    'PROJCS["WGS_1984_Web_Mercator_Auxiliary_Sphere",'
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Mercator_Auxiliary_Sphere"],'
    'PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],'
    'PARAMETER["Central_Meridian",0.0],PARAMETER["Standard_Parallel_1",0.0],'
    'PARAMETER["Auxiliary_Sphere_Type",0.0],UNIT["Meter",1.0]]'
)


def _notify(message):
    ctypes.windll.user32.MessageBoxW(0, message, 'Map Builder', 0x40)


# Order Date / Expiration come out of the spreadsheet as serial day numbers (e.g.
# '46247'), not text dates — this is the epoch Excel/Sheets count from.
_SERIAL_DATE_EPOCH = date(1899, 12, 30)


def _parse_serial_date(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return _SERIAL_DATE_EPOCH + timedelta(days=int(value))
    except ValueError:
        return None


def _parse_int(value):
    value = (value or '').strip()
    try:
        return int(value)
    except ValueError:
        return None


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def _sanitize_filename(name):
    return _INVALID_FILENAME_CHARS.sub('_', name).strip(' .')


def _row_label(row):
    return row['unit_no'] or row['order_no'] or '(unlabeled row)'


def _frstdivid(base, prinmercd):
    # BLM's section id is deterministic from the STR, e.g. section 32 of T3S R2W under
    # Utah's Salt Lake Meridian becomes "UT260030S0020W0SN320" — no lookup needed, just
    # zero-padded assembly. The '0' after each zero-padded number is BLM's
    # township/range "fraction code" (unused here). The meridian code itself must also be
    # zero-padded to 2 digits in the id even though BLM's own PRINMERCD field stores some
    # of them unpadded (e.g. North Dakota's is the single digit '5', not '05').
    state_abbr, section, twp_no, twp_dir, rng_no, rng_dir = base
    return (
        f'{state_abbr}{int(prinmercd):02d}{twp_no:03d}0{twp_dir}'
        f'{rng_no:03d}0{rng_dir}0SN{section:02d}0'
    )


def _parse_strs(state_abbr, strs_field):
    """Returns the list of (state, section, twp_no, twp_dir, rng_no, rng_dir, aliquot)
    components for one unit's STRs field; raises ValueError on any token that doesn't
    look like a section-township-range, optionally with an aliquot part either before or
    after it (e.g. '11-3S-2W', '14-23N-58E-N2', 'N2-14-23N-58E', '14-23N-58E-NENE')."""
    components = []
    for token in strs_field.split(','):
        token = token.strip()
        if not token:
            continue
        m = _STR_RE.match(token)
        if not m:
            raise ValueError(f'unrecognized STR format: {token!r}')
        leading_aliquot, section, twp_no, twp_dir, rng_no, rng_dir, trailing_aliquot = m.groups()
        if leading_aliquot and trailing_aliquot:
            raise ValueError(f'aliquot part given both before and after the STR: {token!r}')
        aliquot = leading_aliquot or trailing_aliquot
        if aliquot:
            aliquot = aliquot.upper()
            if aliquot not in _VALID_ALIQUOTS:
                raise ValueError(f'unrecognized aliquot part {aliquot!r} in {token!r}')
        else:
            aliquot = None
        components.append((
            state_abbr, int(section), int(twp_no), twp_dir.upper(), int(rng_no), rng_dir.upper(), aliquot
        ))
    return components


def _fetch_by_ids(frstdivids):
    """Queries the BLM PLSS section layer and returns {section_id: shapely Polygon}."""
    found = {}
    batch_size = 50
    for i in range(0, len(frstdivids), batch_size):
        batch = frstdivids[i:i + batch_size]
        id_list = ','.join(f"'{fid}'" for fid in batch)
        params = {
            'f': 'json',
            'where': f'FRSTDIVID IN ({id_list})',
            'outFields': 'FRSTDIVID',
            'returnGeometry': 'true',
        }
        resp = requests.get(_BLM_SECTION_URL, params=params, timeout=30)
        resp.raise_for_status()
        for feature in resp.json().get('features', []):
            fid = feature['attributes']['FRSTDIVID']
            rings = feature['geometry']['rings']
            # PLSS sections are simple rectangles in the overwhelming majority of cases,
            # so each ring is treated as its own polygon rather than resolving hole nesting.
            polys = [Polygon(ring) for ring in rings if len(ring) >= 4]
            if polys:
                found[fid] = unary_union(polys) if len(polys) > 1 else polys[0]
    return found


def _fetch_aliquot_polygons(needs):
    """needs: {base_frstdivid: set_of_qq_labels}. Returns {(base_frstdivid, qq_label):
    polygon} for whichever of those official 40-acre quarter-quarter pieces BLM has."""
    found = {}
    items = list(needs.items())
    batch_size = 10
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        clauses = []
        for fid, labels in batch:
            label_list = ','.join(f"'{label}'" for label in labels)
            clauses.append(f"(FRSTDIVID='{fid}' AND SECDIVLAB IN ({label_list}))")
        params = {
            'f': 'json',
            'where': ' OR '.join(clauses),
            'outFields': 'FRSTDIVID,SECDIVLAB',
            'returnGeometry': 'true',
        }
        resp = requests.get(_BLM_INTERSECTED_URL, params=params, timeout=30)
        resp.raise_for_status()
        for feature in resp.json().get('features', []):
            fid = feature['attributes']['FRSTDIVID']
            label = feature['attributes']['SECDIVLAB']
            rings = feature['geometry']['rings']
            polys = [Polygon(ring) for ring in rings if len(ring) >= 4]
            if polys:
                found[(fid, label)] = unary_union(polys) if len(polys) > 1 else polys[0]
    return found


def _fetch_all_section_pieces(base_frstdivids):
    """Returns {base_frstdivid: [polygon, ...]} for every quarter-quarter *and*
    government-lot piece BLM has on record for that section — used as a fallback for a
    half/quarter whose section isn't cleanly subdivided into quarter-quarters (part of it
    replaced by government lots along a river, lake, or international border, say)."""
    found = {}
    ids = list(base_frstdivids)
    batch_size = 20
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i + batch_size]
        id_list = ','.join(f"'{fid}'" for fid in batch)
        params = {
            'f': 'json',
            'where': f'FRSTDIVID IN ({id_list})',
            'outFields': 'FRSTDIVID',
            'returnGeometry': 'true',
        }
        resp = requests.get(_BLM_INTERSECTED_URL, params=params, timeout=30)
        resp.raise_for_status()
        for feature in resp.json().get('features', []):
            fid = feature['attributes']['FRSTDIVID']
            rings = feature['geometry']['rings']
            polys = [Polygon(ring) for ring in rings if len(ring) >= 4]
            if polys:
                geom = unary_union(polys) if len(polys) > 1 else polys[0]
                found.setdefault(fid, []).append(geom)
    return found


def _pieces_in_aliquot(pieces, section_geom, aliquot):
    """Classifies each piece (quarter-quarter or government lot) as belonging to the
    requested half/quarter by comparing its centroid to the section's own centroid —
    lots run along a section's outer edge rather than straddling its center, so this
    reliably sorts them even though they have no directional label of their own."""
    cx, cy = section_geom.centroid.x, section_geom.centroid.y
    wanted = [aliquot] if aliquot in _QUARTERS else list(_HALF_TO_QUARTERS[aliquot])
    matches = []
    for geom in pieces:
        px, py = geom.centroid.x, geom.centroid.y
        quarter = ('N' if py >= cy else 'S') + ('E' if px >= cx else 'W')
        if quarter in wanted:
            matches.append(geom)
    return matches


def _fetch_all_meridians(components):
    """For every state present in components, queries BLM once per meridian used in that
    state. Returns {(state, meridian): {component: polygon}} — every meridian's results
    kept separately, since a unit's sections must all come from the *same* meridian (two
    STRs can each resolve under a different meridian while pointing at two completely
    unrelated real-world townships that just happen to share the same numbers). A
    component only counts as resolved for a meridian if every quarter-quarter piece its
    aliquot part needs was found — a partial fractional-section match would be a shape
    smaller than the unit actually is, which is worse than flagging it as unresolved."""
    by_state = {}
    for c in components:
        by_state.setdefault(c[0], set()).add(c)

    results = {}
    for state_abbr, comps in by_state.items():
        whole = [c for c in comps if c[6] is None]
        aliquot = [c for c in comps if c[6] is not None]
        for prinmercd in _meridians_for_state(state_abbr):
            by_component = {}

            if whole:
                id_for = {c: _frstdivid(c[:6], prinmercd) for c in whole}
                found = _fetch_by_ids(list(id_for.values()))
                for c in whole:
                    if id_for[c] in found:
                        by_component[c] = found[id_for[c]]

            if aliquot:
                plan = {c: (_frstdivid(c[:6], prinmercd), _qq_labels_for(c[6])) for c in aliquot}
                needs = {}
                for base_id, labels in plan.values():
                    needs.setdefault(base_id, set()).update(labels)
                found = _fetch_aliquot_polygons(needs)

                unresolved = []
                for c in aliquot:
                    base_id, labels = plan[c]
                    pieces = [found[(base_id, label)] for label in labels if (base_id, label) in found]
                    if len(pieces) == len(labels):
                        by_component[c] = unary_union(pieces) if len(pieces) > 1 else pieces[0]
                    elif len(c[6]) != 4:  # half/quarter only — see _pieces_in_aliquot
                        unresolved.append(c)

                # Fallback for a half/quarter whose section has some government lots
                # instead of a clean quarter-quarter grid (common along rivers, lakes,
                # and the international border) — classify every available piece
                # (quarter-quarters and lots alike) spatially instead of by label.
                if unresolved:
                    base_ids = {plan[c][0] for c in unresolved}
                    whole_polys = _fetch_by_ids(list(base_ids))
                    all_pieces = _fetch_all_section_pieces(base_ids)
                    for c in unresolved:
                        base_id = plan[c][0]
                        section_geom = whole_polys.get(base_id)
                        pieces = all_pieces.get(base_id)
                        if not section_geom or not pieces:
                            continue
                        matches = _pieces_in_aliquot(pieces, section_geom, c[6])
                        if matches:
                            by_component[c] = unary_union(matches) if len(matches) > 1 else matches[0]

            results[(state_abbr, prinmercd)] = by_component
    return results


# A unit whose sections straddle a real meridian boundary (e.g. a Uintah County unit
# split between the Uintah and a neighboring meridian) can have STRs resolve under two
# different meridians and still be one contiguous unit. But the same STR numbers can also
# coincidentally exist under another meridian at a real, unrelated township many miles
# away. This distance is the cutoff between "plausibly the same unit" and "wrong place" —
# comfortably bigger than one township (~10km) but nowhere near the ~200km gap seen for a
# genuinely unrelated match.
_MAX_NEIGHBOR_METERS = 50_000


def _resolve_unit(state_abbr, components, meridian_results):
    """Resolves a unit's STRs to polygons. A meridian that covers every STR is preferred
    outright (the common case — a unit surveyed entirely under one meridian). Failing
    that, the remaining STRs are matched to whichever other meridian's candidate polygon
    sits closest to the STRs that already resolved, as long as it's close enough
    (_MAX_NEIGHBOR_METERS) to plausibly be part of the same unit rather than a
    same-numbered township somewhere else entirely."""
    meridians = _meridians_for_state(state_abbr)

    coverage = {
        prinmercd: meridian_results.get((state_abbr, prinmercd), {})
        for prinmercd in meridians
    }

    for prinmercd, by_component in coverage.items():
        if all(c in by_component for c in components):
            return [by_component[c] for c in components], []

    seed_meridian = max(meridians, key=lambda m: sum(1 for c in components if c in coverage[m]), default=None)
    chosen = {}
    if seed_meridian is not None:
        chosen = {c: coverage[seed_meridian][c] for c in components if c in coverage[seed_meridian]}

    if chosen:
        anchor = unary_union(list(chosen.values())).centroid
        for c in components:
            if c in chosen:
                continue
            best_poly, best_dist = None, None
            for prinmercd, by_component in coverage.items():
                if prinmercd == seed_meridian or c not in by_component:
                    continue
                dist = by_component[c].centroid.distance(anchor)
                if best_dist is None or dist < best_dist:
                    best_poly, best_dist = by_component[c], dist
            if best_poly is not None and best_dist <= _MAX_NEIGHBOR_METERS:
                chosen[c] = best_poly

    missing = [c for c in components if c not in chosen]
    return [chosen[c] for c in components if c in chosen], missing


def _polygon_to_parts(geom):
    """Flattens a shapely (Multi)Polygon into pyshp's expected list-of-rings, with the
    winding order (clockwise exterior, counterclockwise holes) the shapefile spec requires."""
    parts = []
    polys = geom.geoms if geom.geom_type == 'MultiPolygon' else [geom]
    for poly in polys:
        poly = orient(poly, sign=-1.0)
        parts.append(list(poly.exterior.coords))
        for interior in poly.interiors:
            parts.append(list(interior.coords))
    return parts


# (DBF field name, type, size (None for 'D'), source CSV key used to test for blankness,
# value to write for a given unit). A field is left off the shapefile entirely when every
# unit going into it has a blank value for the field's source column — no point shipping
# an attribute nobody filled in.
_FIELD_SPECS = [
    ('UNIT', 'C', 40, 'unit_no', lambda u: u['unit_no']),
    ('STRS', 'C', 254, 'strs_text', lambda u: u['strs_text']),
    ('STATE', 'C', 2, 'state_abbr', lambda u: u['state_abbr']),
    ('ORDER_NO', 'C', 20, 'order_no', lambda u: u['order_no']),
    ('CASE_NO', 'C', 20, 'case_no', lambda u: u['case_no']),
    ('OPERATOR', 'C', 60, 'operator', lambda u: u['operator']),
    ('COUNTY', 'C', 30, 'county', lambda u: u['county']),
    ('PROTEST', 'C', 10, 'protest', lambda u: u['protest']),
    ('WELLS', 'N', 5, 'wells', lambda u: _parse_int(u['wells'])),
    ('ORDERDATE', 'D', None, 'order_date', lambda u: _parse_serial_date(u['order_date'])),
    ('EXPIRES', 'D', None, 'expiration', lambda u: _parse_serial_date(u['expiration'])),
    ('PHX_OWN', 'C', 20, 'phx_ownership', lambda u: u['phx_ownership']),
]


def _build_shapefile(units, out_base):
    active_specs = [
        spec for spec in _FIELD_SPECS
        if any(u[spec[3]].strip() for u in units)
    ]

    # pyshp treats anything after the *last* period in its target as a file extension to
    # strip, so a name like "Operator Name.20260903" would silently lose the date suffix
    # unless the .shp extension is spelled out explicitly here.
    with shapefile.Writer(out_base + '.shp', shapeType=shapefile.POLYGON) as w:
        for name, ftype, size, _, _ in active_specs:
            if ftype == 'D':
                w.field(name, 'D')
            else:
                w.field(name, ftype, size=size)
        for u in units:
            w.poly(_polygon_to_parts(u['geom']))
            w.record(**{name: value_fn(u) for name, _, _, _, value_fn in active_specs})

    with open(out_base + '.prj', 'w') as f:
        f.write(_PRJ_WKT)
    with open(out_base + '.cpg', 'w') as f:
        f.write('UTF-8')


def main():
    if not os.path.isfile(_UNITS_CSV):
        _notify(
            f'Units.csv not found at:\n{_UNITS_CSV}\n\n'
            'Set the Maps folder in Settings, or place Units.csv there.'
        )
        return

    rows = []
    with open(_UNITS_CSV, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append({
                'unit_no': row.get('Unit #', '').strip(),
                'strs_text': row.get('STRs', '').strip(),
                'state_abbr': row.get('State', '').strip().upper(),
                'order_no': row.get('Order #', '').strip(),
                'case_no': row.get('Case #', '').strip(),
                'operator': row.get('Operator', '').strip(),
                'county': row.get('County', '').strip(),
                'protest': row.get('Protest?', '').strip(),
                'wells': row.get('Well Count', '').strip(),
                'order_date': row.get('Order Date', '').strip(),
                'expiration': row.get('Expiration', '').strip(),
                'phx_ownership': row.get('PHX Ownership', '').strip(),
            })

    if not rows:
        _notify('Units.csv has no rows to map.')
        return

    per_unit_components = []
    all_components = []
    errors = []
    for row in rows:
        label = _row_label(row)
        if not row['operator']:
            errors.append(f'{label}: missing Operator')
            continue
        if not row['state_abbr']:
            errors.append(f'{label}: missing State')
            continue
        try:
            components = _parse_strs(row['state_abbr'], row['strs_text'])
        except ValueError as e:
            errors.append(f'{label}: {e}')
            continue
        per_unit_components.append((row, components))
        all_components.extend(components)

    unique_components = list(dict.fromkeys(all_components))
    meridian_results = _fetch_all_meridians(unique_components)

    units = []
    for row, components in per_unit_components:
        label = _row_label(row)
        polys, missing = _resolve_unit(row['state_abbr'], components, meridian_results)
        if missing:
            errors.append(f'{label}: BLM had no consistent match for {len(missing)} of {len(components)} STR(s)')
        if not polys:
            continue
        geom = unary_union(polys) if len(polys) > 1 else polys[0]
        units.append({**row, 'geom': geom})

    if not units:
        _notify('No unit geometry could be built.\n\n' + '\n'.join(errors[:10]))
        return

    by_operator = {}
    for u in units:
        by_operator.setdefault(u['operator'], []).append(u)

    stamp = date.today().strftime('%Y.%m.%d')
    built = []
    for operator, op_units in by_operator.items():
        out_name = f'{stamp}. {_sanitize_filename(operator)}'
        out_base = os.path.join(_MAPS_DIR, out_name)
        _build_shapefile(op_units, out_base)

        zip_path = out_base + '.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for ext in ('.shp', '.shx', '.dbf', '.prj', '.cpg'):
                zf.write(out_base + ext, out_name + ext)
        for ext in ('.shp', '.shx', '.dbf', '.prj', '.cpg'):
            os.remove(out_base + ext)
        built.append((operator, len(op_units), zip_path))

    summary = f'Built {len(units)} of {len(rows)} unit(s) across {len(built)} operator file(s):\n'
    summary += '\n'.join(f'  {operator} ({count}): {os.path.basename(path)}' for operator, count, path in built)
    if errors:
        summary += '\n\nIssues:\n' + '\n'.join(errors[:10])
        if len(errors) > 10:
            summary += f'\n...and {len(errors) - 10} more'
    _notify(summary)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        _notify(f'Map Builder failed:\n{e}')
