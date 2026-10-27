"""Static wiring checks (no build, runs in about a second).

Reads main.cpp, settings.cpp, the Python scripts and the docs as text and checks the pieces
that have to agree whenever a button is added or changed: unique control ids, a layout
line and a click handler for every button, every launched script exists, the button spec
in buttons.py matches the app, every button has a test file, the docs list every button and
script, and the settings.ini [Folders] keys line up between C++ and Python.
Also byte-compiles and imports every script so a syntax error or missing package shows up here.
"""
import importlib
import py_compile
import re

import pytest

from buttons import BUTTONS, COLUMN_HEADERS, COLUMNS, CORNER_BUTTONS, DIALOG, HIDDEN, SCRIPT, SEQUENCE, TODO
from conftest import REPO

MAIN_CPP = (REPO / 'main.cpp').read_text(encoding='utf-8')  # main window source
SETTINGS_CPP = (REPO / 'settings.cpp').read_text(encoding='utf-8')  # Settings dialog source
ARCHITECTURE_MD = (REPO / 'docs' / 'ARCHITECTURE.md').read_text(encoding='utf-8')  # button map lives here
INDEX_MD = (REPO / 'docs' / 'INDEX.md').read_text(encoding='utf-8')  # every script has a section here
PY_SCRIPTS = sorted(p.name for p in REPO.glob('*.py'))  # every Python file next to the exe

# Scripts that do all their work at import time (no main()), so they are never imported here.
RUNS_AT_IMPORT = set()


def _defines():
    """{macro name: value} for every #define <name> <number> in main.cpp."""
    return {m[1]: int(m[2]) for m in re.finditer(r'#define\s+(ID_\w+)\s+(\d+)', MAIN_CPP)}


def _button_table():
    """[(id macro, label)] from the buttons[] table in WM_CREATE."""
    return re.findall(r'\{\s*(ID_BUTTON_\w+),\s*TEXT\("([^"]*)"\)\s*\}', MAIN_CPP)


def _layout_ids():
    """Button id macros positioned by LayoutControls."""
    body = MAIN_CPP[MAIN_CPP.index('void LayoutControls'):MAIN_CPP.index('LRESULT CALLBACK WndProc')]
    return set(re.findall(r'GetDlgItem\(hwnd,\s*(ID_BUTTON_\w+)\)', body))


def _command_branches():
    """{id macro: branch body} for each `LOWORD(wParam) == ID_BUTTON_X` branch in WM_COMMAND."""
    body = MAIN_CPP[MAIN_CPP.index('case WM_COMMAND'):MAIN_CPP.index('case WM_DESTROY')]
    parts = re.split(r'if \(LOWORD\(wParam\) == (ID_BUTTON_\w+)\)', body)
    return dict(zip(parts[1::2], parts[2::2]))


def _unwired_ids():
    """Id macros listed in g_unwiredButtonIds (drawn yellow)."""
    m = re.search(r'g_unwiredButtonIds\[\]\s*=\s*\{(.*?)\};', MAIN_CPP, re.S)
    return set(re.findall(r'ID_BUTTON_\w+', m[1]))


def _hidden_ids():
    """Id macros listed in g_hiddenButtonIds (hidden)."""
    m = re.search(r'g_hiddenButtonIds\[\]\s*=\s*\{(.*?)\};', MAIN_CPP, re.S)
    return set(re.findall(r'ID_BUTTON_\w+', m[1]))


def _mirror_steps():
    """[(button label, uploads)] from the g_mirrorSteps table in main.cpp, in order."""
    m = re.search(r'g_mirrorSteps\[\]\s*=\s*\{(.*?)\};', MAIN_CPP, re.S)
    labels = dict(_button_table())
    return [(labels[id_name], uploads == 'true')
            for id_name, uploads in re.findall(r'\{\s*(ID_BUTTON_\w+),\s*(true|false)\s*\}', m[1])]


def _locked_during_mirror():
    """Button labels in main.cpp's g_lockedDuringMirror."""
    m = re.search(r'g_lockedDuringMirror\[\]\s*=\s*\{(.*?)\};', MAIN_CPP, re.S)
    labels = dict(_button_table())
    return {labels[i] for i in re.findall(r'ID_BUTTON_\w+', m[1])}


def _launched_scripts():
    """Every script name main.cpp launches: py "<exeDir>script.py" lines plus the Index steps[] table."""
    return set(re.findall(r'%s(\w+\.py)', MAIN_CPP)) | set(re.findall(r'TEXT\("(\w+\.py)"\)', MAIN_CPP))


def test_control_ids_are_unique():
    """Two controls sharing an id would make one button fire the other's handler."""
    defines = _defines()
    seen = {}
    for name, value in defines.items():
        assert value not in seen, f'{name} and {seen[value]} both use id {value}'
        seen[value] = name


def test_button_spec_matches_app():
    """tests/buttons.py lists exactly the buttons main.cpp creates."""
    app_labels = [label for _, label in _button_table()]
    spec_labels = [b.label for b in BUTTONS]
    missing = set(app_labels) - set(spec_labels)
    extra = set(spec_labels) - set(app_labels)
    assert not missing, f'New button(s) {sorted(missing)} need an entry in tests/buttons.py'
    assert not extra, f'tests/buttons.py lists {sorted(extra)}, which main.cpp no longer creates'
    assert len(app_labels) == len(set(app_labels)), 'Two buttons share a label'


def test_every_button_has_a_defined_id():
    """Each buttons[] entry uses an id that is #defined."""
    defines = _defines()
    for id_name, label in _button_table():
        assert id_name in defines, f'{label}: {id_name} is not #defined'


def test_every_button_is_laid_out():
    """Each button has a MoveWindow line in LayoutControls (otherwise it sits at 0,0 with no size)."""
    laid_out = _layout_ids()
    for id_name, label in _button_table():
        assert id_name in laid_out, f'{label}: add a MoveWindow line for {id_name} in LayoutControls'


def test_every_button_has_a_click_handler():
    """Each button has a WM_COMMAND branch, and only unfinished buttons have an empty one."""
    branches = _command_branches()
    for id_name, label in _button_table():
        assert id_name in branches, f'{label}: add an `else if (LOWORD(wParam) == {id_name})` branch'


def test_yellow_buttons_match_spec():
    """g_unwiredButtonIds (yellow) is exactly the TODO buttons in the spec, and they do nothing."""
    ids_by_label = {label: id_name for id_name, label in _button_table()}
    todo_ids = {ids_by_label[b.label] for b in BUTTONS if b.kind == TODO}
    assert _unwired_ids() == todo_ids
    branches = _command_branches()
    for id_name in todo_ids:
        assert 'CreateProcess' not in branches[id_name]


def test_hidden_buttons_match_spec():
    """g_hiddenButtonIds is exactly the HIDDEN buttons in the spec, none of them is a Mirror step, and
    each one's handler still launches its spec script and LayoutControls still places it, so bringing
    it back is one line."""
    ids_by_label = {label: id_name for id_name, label in _button_table()}
    hidden = [b for b in BUTTONS if b.kind == HIDDEN]
    assert _hidden_ids() == {ids_by_label[b.label] for b in hidden}
    branches = _command_branches()
    mirror_labels = {label for label, _ in _mirror_steps()}
    for b in hidden:
        script, *args = b.target
        expected = f'LaunchScript(hwnd, TEXT("{script}")' + (f', TEXT("{" ".join(args)}")' if args else '') + ')'
        assert expected in branches[ids_by_label[b.label]], f'{b.label}: expected the handler to run {script}'
        assert b.label not in mirror_labels, f'{b.label} is hidden, so Mirror must not run it'
        assert f'GetDlgItem(hwnd, {ids_by_label[b.label]})' in MAIN_CPP, f'{b.label}: keep its LayoutControls line'


def test_mirror_steps_match_mirror_py():
    """main.cpp's g_mirrorSteps (green buttons, confirmation box) lists the same buttons, in the same
    order and with the same uploads flags, as STEPS in mirror.py (what actually runs)."""
    import mirror
    assert _mirror_steps() == [(step.name, step.uploads) for step in mirror.STEPS]


def test_buttons_sharing_the_ark_login_are_locked_during_mirror():
    """Every button whose script uses the Ark session (session.json) is a Mirror step or is in
    g_lockedDuringMirror, so it can't run alongside Mirror and fight over the login."""
    covered = {label for label, _ in _mirror_steps()} | _locked_during_mirror()
    for b in BUTTONS:
        if b.kind not in (SCRIPT, SEQUENCE) or b.label == 'Mirror':
            continue
        scripts = [t for t in b.target if t.endswith('.py')]
        if any('_SESSION' in (REPO / s).read_text(encoding='utf-8-sig') for s in scripts):
            assert b.label in covered, f'{b.label} uses the Ark login: add it to g_lockedDuringMirror in main.cpp'


@pytest.mark.xfail(strict=True, reason='KNOWN_ISSUES: Docket Updates and Docket Updates Slack sign in through '
                                       'ark_page but are not locked during Mirror')
def test_buttons_using_ark_page_are_locked_during_mirror():
    """Like the test above, but also counts scripts that use the Ark login through ark_common.ark_page
    (which loads and saves session.json) without naming _SESSION themselves."""
    covered = {label for label, _ in _mirror_steps()} | _locked_during_mirror()
    for b in BUTTONS:
        if b.kind not in (SCRIPT, SEQUENCE) or b.label == 'Mirror':
            continue
        scripts = [t for t in b.target if t.endswith('.py')]
        if any('ark_page(' in (REPO / s).read_text(encoding='utf-8-sig') for s in scripts):
            assert b.label in covered, f'{b.label} uses the Ark login: add it to g_lockedDuringMirror in main.cpp'


def test_script_buttons_launch_the_spec_script():
    """Each SCRIPT button's handler launches the spec script and arguments through LaunchScript."""
    ids_by_label = {label: id_name for id_name, label in _button_table()}
    branches = _command_branches()
    for b in BUTTONS:
        if b.kind != SCRIPT:
            continue
        script, *args = b.target
        expected = f'LaunchScript(hwnd, TEXT("{script}")' + (f', TEXT("{" ".join(args)}")' if args else '') + ')'
        assert expected in branches[ids_by_label[b.label]], \
            f'{b.label}: expected the handler to run {script} {" ".join(args)}'


def test_launched_scripts_exist():
    """Every script main.cpp launches is in the repo (and so ships next to the exe)."""
    for script in _launched_scripts():
        assert (REPO / script).is_file(), f'main.cpp launches {script}, which does not exist'
    for b in BUTTONS:
        if b.kind in (SCRIPT, SEQUENCE, HIDDEN):
            for script in b.target:
                if script.endswith('.py'):
                    assert script in _launched_scripts(), f'{b.label}: main.cpp never launches {script}'


def test_every_working_button_has_tests():
    """Every implemented button names a test file in the spec, and that file exists."""
    for b in BUTTONS:
        if b.kind == TODO:
            continue
        assert b.covered_by, f'{b.label}: list the test file(s) covering it in tests/buttons.py'
        for name in b.covered_by:
            assert (REPO / 'tests' / name).is_file(), f'{b.label}: tests/{name} does not exist'


def test_every_button_has_one_place_in_the_layout_spec():
    """COLUMNS plus CORNER_BUTTONS in buttons.py name every shown (not HIDDEN) button exactly once."""
    placed = [label for column in COLUMNS for label in column] + CORNER_BUTTONS
    assert sorted(placed) == sorted(b.label for b in BUTTONS if b.kind != HIDDEN)


def test_column_headers_match_the_spec():
    """main.cpp's g_columnHeaders are COLUMN_HEADERS in buttons.py, one per column."""
    table = MAIN_CPP[MAIN_CPP.index('g_columnHeaders[] = {'):]
    table = table[:table.index('};')]
    assert re.findall(r'TEXT\("([^"]*)"\)', table) == COLUMN_HEADERS
    assert len(COLUMN_HEADERS) == len(COLUMNS)


def test_docs_list_every_button_and_script():
    """docs/ARCHITECTURE.md's button map names every button, and docs/INDEX.md every script."""
    button_map = ARCHITECTURE_MD[ARCHITECTURE_MD.index('## 2. Button map'):ARCHITECTURE_MD.index('## 3.')]
    for b in BUTTONS:
        assert b.label in button_map, f'Add {b.label} to the button map in docs/ARCHITECTURE.md'
    for script in PY_SCRIPTS:
        stem = script[:-3].replace('doc_inventory_', '')  # the three county scripts share one section
        assert stem in INDEX_MD, f'Add {script} to docs/INDEX.md'


def _settings_rows():
    """{(section, key)} of every row in settings.cpp's s_settings table."""
    return set(re.findall(r'\{\s*TEXT\("(\w+)"\),\s*TEXT\("(\w+)"\),\s*TEXT\("[^"]*"\),\s*SETTING_', SETTINGS_CPP))


def _settings_read():
    """{(section, key)} that the Python scripts read with read_folder / read_setting, plus the
    folders Organize and Rename read with GetSetting."""
    read = set()
    for script in PY_SCRIPTS:
        text = (REPO / script).read_text(encoding='utf-8-sig')
        read |= {('Folders', k) for k in re.findall(r"read_folder\(\s*'(\w+)'", text)}
        read |= set(re.findall(r"read_setting\(\s*'(\w+)',\s*'(\w+)'", text))
    for cpp in ('organize.cpp', 'rename.cpp'):
        read |= set(re.findall(r'GetSetting\(L"(\w+)",\s*L"(\w+)"\)', (REPO / cpp).read_text(encoding='utf-8')))
    return read


def test_settings_keys_are_read_and_editable():
    """Every folder/file row in the Settings dialog is read by some script, every folder or file a
    script reads has a Settings row (nothing left to edit by hand), and every key is in the
    settings.ini table in docs/ARCHITECTURE.md."""
    rows = _settings_rows()
    paths = {(s, k) for s, k in rows if s in ('Folders', 'Files')}
    read = _settings_read()
    assert paths, 'Could not find the s_settings rows in settings.cpp'
    assert paths <= read, f'Settings has rows {sorted(paths - read)} but nothing reads them'
    assert read <= rows, f'{sorted(read - rows)} are read but have no row in the Settings dialog'
    for section, key in rows:
        assert f'`[{section}] {key}`' in ARCHITECTURE_MD, f'Document [{section}] {key} in docs/ARCHITECTURE.md'


def test_sandbox_covers_every_folder_setting():
    """conftest.FOLDER_KEYS (the folders tests redirect to the sandbox) lists every [Folders] row,
    so no test can fall back to a real Desktop folder."""
    from conftest import FOLDER_KEYS
    assert {k for s, k in _settings_rows() if s == 'Folders'} == set(FOLDER_KEYS)


@pytest.mark.parametrize('script', PY_SCRIPTS)
def test_script_compiles(script, tmp_path):
    """The script has no syntax errors."""
    py_compile.compile(str(REPO / script), cfile=str(tmp_path / 'out.pyc'), doraise=True)


@pytest.mark.parametrize('script', [s for s in PY_SCRIPTS if s not in RUNS_AT_IMPORT])
def test_script_imports(script):
    """The script imports cleanly: its packages are installed and module-level code runs."""
    importlib.import_module(script[:-3])


def test_default_organize_rules_are_valid():
    """default_organize_rules.ini (copied to a new machine's organize_rules.ini on first use) has
    [Rules] mapping to real columns (0-15) and ColumnSchema=2, so it is never re-migrated."""
    import configparser
    ini = configparser.ConfigParser(delimiters=('=',), strict=False, interpolation=None)
    ini.optionxform = str
    ini.read(REPO / 'default_organize_rules.ini', encoding='mbcs')
    assert ini.has_section('Rules') and len(ini['Rules']) > 0, 'default_organize_rules.ini has no [Rules]'
    bad = {k: v for k, v in ini['Rules'].items() if not (v.isdigit() and 0 <= int(v) <= 15)}
    assert not bad, f'Rules with no valid column: {bad}'
    assert ini.get('Meta', 'ColumnSchema', fallback='') == '2', 'Set [Meta] ColumnSchema=2'
