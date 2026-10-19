"""The button spec: every button on the main window and what clicking it must do.

test_wiring.py checks main.cpp and the docs against this table, and test_app_buttons.py
clicks every button in a test build and checks the click does what is listed here.
When you add, rename, rewire or move a button, update BUTTONS and COLUMNS (the tests tell you
if you forget).
"""
from dataclasses import dataclass, field

SCRIPT = 'script'      # click launches one Python script next to the exe: target = [script, args...]
SEQUENCE = 'sequence'  # click runs scripts one after another on a background thread: target = [script, ...]
DIALOG = 'dialog'      # click opens a C++ window: target = its window class name
INLINE = 'inline'      # click runs C++ code that reads/writes personal files: not clicked by the app test
TODO = 'todo'          # not implemented yet: drawn yellow, click does nothing
DISABLED = 'disabled'  # works but is greyed out (main.cpp g_disabledButtonIds): target = [script, args...] it
                       # launches once re-enabled; a click while greyed out does nothing


@dataclass
class Button:
    """One main-window button: its label, what a click does, and the test file covering its logic."""
    label: str
    kind: str
    target: object = None
    covered_by: list = field(default_factory=list)


BUTTONS = [
    # Top-left corner: asks Yes/No, then runs mirror.py --stop-file <path> (which runs the green buttons'
    # work in a row); reads Stop while it runs
    Button('Mirror', SEQUENCE, ['mirror.py'], ['test_mirror.py', 'test_cpp.py']),
    # Column 1
    Button('Close Date', SCRIPT, ['close_dates.py'], ['test_close_dates.py']),
    Button('Case Update', SCRIPT, ['non_hbp_mi.py'], ['test_case_update.py']),
    Button('Index', SEQUENCE, ['doc_inventory_roosevelt.py', 'doc_inventory_richland.py',
                               'doc_inventory_divide.py'], ['test_index.py']),
    Button('Cases Unit Names', SCRIPT, ['case_unit_names.py'], ['test_case_unit_names.py']),
    Button('STR', SCRIPT, ['str_verification.py'], ['test_str_verification.py']),
    Button('TPP-LHPP', SCRIPT, ['tpp_lhpp.py'], ['test_tpp_lhpp.py']),
    Button('C2E', SCRIPT, ['cost_to_extend.py'], ['test_cost_to_extend.py']),
    Button('Docket Updates', SCRIPT, ['docket_updates.py'], ['test_docket_updates.py']),
    # The old Slack version of Docket Updates, kept greyed out in case it is needed again
    Button('Docket Updates Slack', DISABLED, ['docket_updates_slack.py'], ['test_docket_updates_slack.py']),
    # Bottom-left corner
    Button('Settings', DIALOG, 'SettingsWindow', ['test_cpp.py']),
    # Column 2
    Button('PPIQ', SCRIPT, ['ppiq.py'], ['test_ppiq.py']),
    Button('AOI', SCRIPT, ['str_verification.py', '--aoi'], ['test_str_verification.py']),
    Button('DMD', SCRIPT, ['download_report.py'], ['test_download_report.py']),
    Button('Organization', INLINE, 'RunOrganize', ['test_cpp.py']),
    # Column 3
    Button('Unit Connect to Cases', SCRIPT, ['case_matchup.py'], ['test_case_matchup.py']),
    Button('Bring out your dead', SCRIPT, ['deceased.py'], ['test_deceased.py']),
    Button('Rename', DIALOG, 'RenameDlg', ['test_cpp.py']),
    Button('Maps', SEQUENCE, ['map_builder.py', 'map_uploader.py'], ['test_map.py']),
    # Column 4 (not implemented yet)
    Button('ELMI', TODO),
    Button('DNM', TODO),
    Button('HBPNW', TODO),
    Button('LE', TODO),
    Button('LHP', TODO),
    Button('NHBPW', TODO),
    Button('SIB', TODO),
    Button('UNLE', TODO),
    Button('SL', TODO),
    Button('HBP Wells', TODO),
]

# Main-window columns left to right, each listed top to bottom (Mirror and Settings sit outside them)
COLUMNS = [
    ['Close Date', 'Case Update', 'Index', 'Cases Unit Names', 'STR', 'TPP-LHPP',
     'C2E', 'Docket Updates', 'Docket Updates Slack'],
    ['PPIQ', 'AOI', 'DMD', 'Organization'],
    ['Unit Connect to Cases', 'Bring out your dead', 'Rename', 'Maps'],
    ['ELMI', 'DNM', 'HBPNW', 'LE', 'LHP', 'NHBPW', 'SIB', 'UNLE', 'SL', 'HBP Wells'],
]
COLUMN_HEADERS = ['Daily', 'Set Date', 'As Needed', 'In Progress']  # label above each of COLUMNS
CORNER_BUTTONS = ['Mirror', 'Settings']  # placed outside the columns (top-left and bottom-left)


def by_label(label):
    """The Button with this label."""
    return next(b for b in BUTTONS if b.label == label)
