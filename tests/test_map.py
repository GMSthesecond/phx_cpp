"""Map button: map_builder.py (Units.csv -> shapefile zips) then map_uploader.py (zips -> Enverus).

map_builder runs against a fake BLM PLSS service that lays sections out on a grid, so the
built shapes can be checked exactly. map_uploader runs with its Enverus steps replaced by
recorders. Also covers operator_colors.py.
"""
import io
import re
import zipfile
from datetime import date

import pytest
import shapefile
from shapely.geometry import Polygon

import map_builder as mb
import map_uploader as mu
import operator_colors as oc
from fakes import Recorder, write_csv

_S = 1600.0  # side of a fake section in meters

_UNITS_HEADER = ['Unit #', 'STRs', 'State', 'Order #', 'Case #', 'Operator', 'County', 'Protest?',
                 'Well Count', 'Order Date', 'Expiration', 'PHX Ownership']


class _Response:
    """Minimal requests.Response: json() and raise_for_status()."""

    def __init__(self, data):
        """data is the decoded JSON body."""
        self._data = data

    def json(self):
        """The JSON body."""
        return self._data

    def raise_for_status(self):
        """Always OK."""


class FakeBLM:
    """Fake BLM PLSS service: one meridian ('5') per state; section n of a township sits at
    column (n-1) % 6, row (n-1) // 6 of a grid of _S-meter squares. Only `known` sections exist."""

    def __init__(self, known_sections):
        """known_sections: section numbers (in T150N R100W, ND) that BLM has data for."""
        self.known = {mb._frstdivid(('ND', n, 150, 'N', 100, 'W'), '5') for n in known_sections}
        self.queries = 0

    @staticmethod
    def _origin(fid):
        """Bottom-left corner of a section, from the section number inside its FRSTDIVID."""
        n = int(fid[-3:-1])
        return ((n - 1) % 6 * _S, -((n - 1) // 6) * _S)

    @staticmethod
    def _square(x, y, size):
        """Closed ring of a square with bottom-left corner (x, y)."""
        return [[x, y], [x, y + size], [x + size, y + size], [x + size, y], [x, y]]

    def _qq_ring(self, fid, label):
        """Ring of quarter-quarter `label` (e.g. 'NENW' = NE of the NW quarter) of a section."""
        x, y = self._origin(fid)
        inner, outer = label[:2], label[2:]
        x += (_S / 2 if outer[1] == 'E' else 0) + (_S / 4 if inner[1] == 'E' else 0)
        y += (_S / 2 if outer[0] == 'N' else 0) + (_S / 4 if inner[0] == 'N' else 0)
        return self._square(x, y, _S / 4)

    def get(self, url, params=None, timeout=None):
        """Replacement for requests.get against the three BLM layers map_builder queries."""
        self.queries += 1
        where = params['where']
        if url == mb._BLM_TOWNSHIP_URL:
            return _Response({'features': [{'attributes': {'PRINMERCD': '5'}}]})
        if url == mb._BLM_SECTION_URL:
            ids = re.findall(r"'([^']+)'", where)
            return _Response({'features': [
                {'attributes': {'FRSTDIVID': fid}, 'geometry': {'rings': [self._square(*self._origin(fid), _S)]}}
                for fid in ids if fid in self.known]})
        if url == mb._BLM_INTERSECTED_URL:
            features = []
            for fid, labels in re.findall(r"FRSTDIVID='([^']+)' AND SECDIVLAB IN \(([^)]*)\)", where):
                if fid in self.known:
                    for label in re.findall(r"'(\w+)'", labels):
                        features.append({'attributes': {'FRSTDIVID': fid, 'SECDIVLAB': label},
                                         'geometry': {'rings': [self._qq_ring(fid, label)]}})
            return _Response({'features': features})
        raise AssertionError(f'unexpected BLM URL {url}')


def _unit(unit_no, strs, operator, state='ND', order_date=''):
    """One Units.csv row."""
    return [unit_no, strs, state, '', '', operator, 'Divide', '', '', order_date, '', '']


@pytest.fixture
def maps_dir(tmp_path, monkeypatch):
    """Redirects map_builder's and map_uploader's Maps folder to a temp folder."""
    for mod in (mb, mu):
        monkeypatch.setattr(mod, '_MAPS_DIR', str(tmp_path))
    monkeypatch.setattr(mb, '_UNITS_CSV', str(tmp_path / 'Units.csv'))
    monkeypatch.setattr(mu, '_UPLOADED_DIR', str(tmp_path / 'Uploaded'))
    monkeypatch.setattr(mb, '_state_meridian_cache', {})
    return tmp_path


def _read_zip(path):
    """(field names, records, shapely polygons) from one built shapefile zip."""
    with zipfile.ZipFile(path) as zf:
        names = sorted(zf.namelist())
        base = names[0].rsplit('.', 1)[0]
        assert names == sorted(base + ext for ext in ('.shp', '.shx', '.dbf', '.prj', '.cpg'))
        r = shapefile.Reader(shp=io.BytesIO(zf.read(base + '.shp')), shx=io.BytesIO(zf.read(base + '.shx')),
                             dbf=io.BytesIO(zf.read(base + '.dbf')))
        fields = [f[0] for f in r.fields[1:]]
        return fields, [rec.as_dict() for rec in r.records()], [Polygon(s.points) for s in r.shapes()]


# ---- map_builder ----

def test_parse_strs_accepts_every_documented_form():
    """Plain STRs and aliquot parts before or after the STR all parse."""
    assert mb._parse_strs('ND', '11-3S-2W, n2-14-23N-58E, 14-23N-58E-NENE') == [
        ('ND', 11, 3, 'S', 2, 'W', None),
        ('ND', 14, 23, 'N', 58, 'E', 'N2'),
        ('ND', 14, 23, 'N', 58, 'E', 'NENE'),
    ]


@pytest.mark.parametrize('bad', ['garbage', 'N2-14-23N-58E-S2', 'XX-14-23N-58E'])
def test_parse_strs_rejects_bad_tokens(bad):
    """Malformed STRs, double aliquots and unknown aliquots raise ValueError."""
    with pytest.raises(ValueError):
        mb._parse_strs('ND', bad)


def test_helpers():
    """Section ids, aliquot expansion, serial dates and filename cleanup."""
    assert mb._frstdivid(('UT', 32, 3, 'S', 2, 'W'), '26') == 'UT260030S0020W0SN320'
    assert mb._frstdivid(('ND', 1, 150, 'N', 100, 'W'), '5') == 'ND051500N1000W0SN010'
    assert mb._qq_labels_for('NENE') == ['NENE']
    assert sorted(mb._qq_labels_for('NE')) == ['NENE', 'NWNE', 'SENE', 'SWNE']
    assert len(mb._qq_labels_for('W2')) == 8
    assert mb._parse_serial_date('46247') == date(2026, 8, 13)
    assert mb._parse_serial_date('') is None
    assert mb._sanitize_filename('Beta/Energy: "Ops".') == 'Beta_Energy_ _Ops_'


def test_builds_one_zip_per_operator(maps_dir, monkeypatch, msgboxes):
    """Units become one dated zip per operator; bad rows are listed in the summary instead."""
    blm = FakeBLM(known_sections={1, 2, 3, 4})
    monkeypatch.setattr(mb.requests, 'get', blm.get)
    write_csv(maps_dir / 'Units.csv', [
        _UNITS_HEADER,
        _unit('U1', '1-150N-100W, 2-150N-100W', 'Acme Oil', order_date='46247'),
        _unit('U2', 'N2-3-150N-100W', 'Acme Oil'),
        _unit('U3', '4-150N-100W', 'Beta/Energy'),
        _unit('U4', '4-150N-100W', ''),             # no operator
        _unit('U5', '9-150N-100W', 'Acme Oil'),     # BLM has no such section
        _unit('U6', 'garbage', 'Acme Oil'),         # unparseable
    ])

    mb.main()

    stamp = f'{date.today():%Y.%m.%d}'
    assert sorted(p.name for p in maps_dir.iterdir()) == \
        sorted(['Units.csv', f'{stamp}. Acme Oil.zip', f'{stamp}. Beta_Energy.zip'])

    fields, records, polys = _read_zip(maps_dir / f'{stamp}. Acme Oil.zip')
    assert fields == ['UNIT', 'STRS', 'STATE', 'OPERATOR', 'COUNTY', 'ORDERDATE']  # blank columns left out
    assert [r['UNIT'] for r in records] == ['U1', 'U2']
    assert records[0]['ORDERDATE'] == date(2026, 8, 13)
    assert polys[0].area == pytest.approx(2 * _S * _S)   # two whole sections
    assert polys[1].area == pytest.approx(_S * _S / 2)   # north half of one section

    title, text = msgboxes[-1]
    assert title == 'Map Builder'
    assert 'Built 3 of 6 unit(s) across 2 operator file(s)' in text
    assert 'U4: missing Operator' in text
    assert 'U5: BLM had no consistent match for 1 of 1 STR(s)' in text
    assert "U6: unrecognized STR format: 'garbage'" in text


def test_missing_units_csv_is_reported(maps_dir, msgboxes):
    """No Units.csv -> a message box saying where it was expected."""
    mb.main()
    assert msgboxes and 'Units.csv not found' in msgboxes[-1][1]


# ---- map_uploader ----

def test_uploads_dated_zips_and_moves_them(maps_dir, monkeypatch, fake_ark, msgboxes):
    """Dated zips are uploaded with their operator's color; uploaded ones move to Uploaded,
    failed ones stay for the next run; other zips are ignored."""
    for name in ('2026.09.30. Acme Oil.zip', '2026.09.30. Beta.zip', 'random.zip'):
        (maps_dir / name).write_bytes(b'')
    uploaded = []

    def fake_upload_one(page, zip_path, rgb):
        if 'Beta' in zip_path:
            raise RuntimeError('layer row never appeared')
        uploaded.append((zip_path, rgb))

    save = Recorder()
    monkeypatch.setattr(mu, '_login', Recorder())
    monkeypatch.setattr(mu, '_open_map_layers', Recorder())
    monkeypatch.setattr(mu, '_upload_one', fake_upload_one)
    monkeypatch.setattr(mu, '_save_workspace', save)

    mu.main()

    assert [p.endswith('Acme Oil.zip') for p, _ in uploaded] == [True]
    assert (maps_dir / 'Uploaded' / '2026.09.30. Acme Oil.zip').exists()
    assert (maps_dir / '2026.09.30. Beta.zip').exists() and (maps_dir / 'random.zip').exists()
    assert len(save.calls) == 1
    assert set(oc.load_colors(str(maps_dir))) == {'Acme Oil', 'Beta'}
    text = msgboxes[-1][1]
    assert 'Uploaded 1 of 2 shapefile(s)' in text and 'Beta: layer row never appeared' in text


class _EnverusLoginPage:
    """Stand-in page for map_uploader._login: opening the app while signed out lands on the Enverus
    sign-in page with a fresh state= token, as the real site does; clicking submit after the
    password signs in and goes back to the app. Records every call in steps."""

    def __init__(self):
        """Starts on a blank page with nothing recorded."""
        self.url = 'about:blank'
        self.steps = []

    def goto(self, url, **kwargs):
        """Opening the app while signed out redirects to the sign-in page."""
        self.steps.append(('goto', url))
        self.url = 'https://login.auth.enverus.com/u/login/identifier?state=fresh-token'

    def wait_for_selector(self, selector, **kwargs):
        """Records the field waited for."""
        self.steps.append(('wait', selector))

    def fill(self, selector, value):
        """Records what was typed where."""
        self.steps.append(('fill', selector, value))

    def click(self, selector):
        """The second submit (after the password) signs in and returns to the app."""
        self.steps.append(('click', selector))
        if any(s[0] == 'fill' and 'password' in s[1] for s in self.steps):
            self.url = 'https://app.enverus.com/production/'

    def wait_for_url(self, predicate, **kwargs):
        """Checks the wait accepts the app URL and rejects the sign-in page."""
        self.steps.append(('wait_for_url',))
        assert predicate(self.url), f'_login waited for a URL it never reaches: {self.url}'
        assert not predicate('https://login.auth.enverus.com/u/login/password?state=x')


def test_login_starts_from_the_app_url_not_a_captured_sign_in_link():
    """_login opens the app, which hands out a fresh sign-in page (no captured state= token that can
    expire), types the [EnverusCredentials] identifier then password, and waits to leave the sign-in site."""
    page = _EnverusLoginPage()
    mu._login(page)
    assert page.steps[0] == ('goto', mu._APP_URL)
    assert ('fill', 'input[name="username"]', 'test.user@example.com') in page.steps
    assert ('fill', 'input[type="password"]', 'not-a-real-password') in page.steps
    assert page.steps[-1] == ('wait_for_url',)
    assert not hasattr(mu, '_LOGIN_URL')


def test_no_zips_means_no_browser(maps_dir, msgboxes):
    """With nothing to upload, the uploader says so and never opens a browser."""
    mu.main()
    assert 'No dated operator zip files found' in msgboxes[-1][1]


def test_layer_name_to_operator():
    """The date prefix is stripped from a layer name to get the operator."""
    assert mu._operator_from_layer_name('2026.09.30. Acme Oil') == 'Acme Oil'
    assert mu._operator_from_layer_name('Something else') == 'Something else'


# ---- operator_colors ----

def test_no_operator_gets_a_reddish_color():
    """Colors handed to operators (palette first, then generated) never look like DI's red borders."""
    colors = {}
    handed_out = [oc.color_for_operator(f'Operator {i}', colors) for i in range(300)]
    assert not any(oc._is_reddish(c) for c in handed_out)
    assert len(set(handed_out)) == 300


def test_operator_keeps_its_color_across_runs(tmp_path):
    """A saved operator gets the same color next run; a new one gets an unused color."""
    colors = {}
    acme = oc.color_for_operator('Acme', colors)
    oc.save_colors(str(tmp_path), colors)

    reloaded = oc.load_colors(str(tmp_path))
    assert oc.color_for_operator('Acme', reloaded) == acme
    assert oc.color_for_operator('Beta', reloaded) != acme


def test_scrub_red_colors_replaces_only_reds():
    """Old reddish colors are reassigned; others are untouched."""
    colors = {'Red Co': (230, 20, 30), 'Green Co': oc._PALETTE[0]}
    assert oc.scrub_red_colors(colors) == ['Red Co']
    assert not oc._is_reddish(colors['Red Co']) and colors['Green Co'] == oc._PALETTE[0]
