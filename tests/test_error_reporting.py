"""Every button script must show a message box when it fails.

The launcher runs scripts with no console, so a failure without a message box is invisible
(this was KNOWN_ISSUES "Silent failures"). Each script is run as the button runs it (as __main__)
with the browser blocked, which makes every Ark script fail on its first step. A script known to
fail silently would be marked xfail here. The map scripts must also say which package is missing.
"""
import runpy
import sys

import pytest

import ark_common
from conftest import REPO

# script -> True if it already shows a message box on failure
_SCRIPTS = {
    'tpp_lhpp.py': True,
    'cost_to_extend.py': True,
    'close_dates.py': True,
    'case_matchup.py': True,   # fails because its input CSVs are missing in the sandbox folder
    'case_unit_names.py': True,
    'section_id_blank.py': True,
    'docket_updates.py': True,  # the sandbox Hearing Dockets workbook doesn't exist
    'docket_updates_slack.py': True,  # fails because the network (Slack) is blocked
    'non_hbp_mi.py': True,
    'ppiq.py': True,
    'nai_download.py': True,
    'str_verification.py': True,
    'deceased.py': True,       # fails because its input CSVs are missing in the sandbox folder
    'qq_checker.py': True,     # no QQ_Checker.csv in the sandbox QQ folder
    'map_builder.py': True,    # no Units.csv in the sandbox Maps folder
    'map_uploader.py': True,   # no zips in the sandbox Maps folder
    'doc_inventory_roosevelt.py': True,  # the sandbox index workbook doesn't exist
    'doc_inventory_richland.py': True,
    'doc_inventory_divide.py': True,
}
# mirror.py is left out on purpose: run as __main__ it would start real steps in child processes.

_SILENT = pytest.mark.xfail(reason='KNOWN_ISSUES "Silent failures": no message box on error')


@pytest.mark.parametrize('script', [
    pytest.param(name, marks=() if shows_box else _SILENT) for name, shows_box in _SCRIPTS.items()])
def test_failure_shows_a_message_box(script, msgboxes, no_real_makedirs):
    """Running the script with no way to reach Ark ends in a message box, not silence."""
    try:
        runpy.run_path(str(REPO / script), run_name='__main__')
    except (Exception, SystemExit):
        pass
    assert msgboxes, f'{script} failed without telling the user'


@pytest.mark.parametrize('script, title', [('ppiq.py', 'PPIQ'), ('nai_download.py', 'Newly Acquired Interest'),
                                           ('str_verification.py', 'STR Verification'), ('deceased.py', 'Deceased')])
def test_error_box_names_the_error_and_the_log(script, title, msgboxes, folders, monkeypatch):
    """The box is an error titled for the button; it shows the error and where the full log went."""
    monkeypatch.setattr(sys, 'argv', [script])
    with pytest.raises(Exception):
        runpy.run_path(str(REPO / script), run_name='__main__')
    [(box_title, text)] = msgboxes
    assert box_title == title and text.startswith(f'{title} failed:\n')
    log = text.split('Details: ')[1]
    assert log.endswith('_error.log') and 'Traceback' in open(log, encoding='utf-8').read()


@pytest.mark.parametrize('script, title, package, pip_name', [
    ('map_builder.py', 'Map Builder', 'shapely', 'shapely'),
    ('map_builder.py', 'Map Builder', 'shapefile', 'pyshp'),
    ('map_uploader.py', 'Map Uploader', 'playwright', 'playwright'),
])
def test_missing_package_is_named(script, title, package, pip_name, msgboxes, monkeypatch):
    """With a package missing, the map scripts show which one to pip install instead of crashing silently."""
    for name in list(sys.modules):
        if name == package or name.startswith(package + '.'):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, package, None)  # makes `import package` raise ImportError
    with pytest.raises(SystemExit):
        runpy.run_path(str(REPO / script), run_name='__main__')
    [(box_title, text)] = msgboxes
    assert box_title == title and f'py -m pip install {pip_name}' in text


def test_run_button_returns_main_result_without_a_box(msgboxes, tmp_path):
    """A main() that works shows no error box and its result is passed back."""
    assert ark_common.run_button('X', lambda: 42, str(tmp_path / 'x_error.log')) == 42
    assert msgboxes == [] and not (tmp_path / 'x_error.log').exists()


def test_run_button_still_shows_the_box_when_the_log_cannot_be_written(msgboxes, tmp_path):
    """If the log folder can't be made (e.g. a bad folder setting), the error box still appears."""
    blocker = tmp_path / 'file'
    blocker.write_text('')
    def boom():
        raise ValueError('bad input')
    with pytest.raises(ValueError):
        ark_common.run_button('X', boom, str(blocker / 'sub' / 'x_error.log'))
    assert msgboxes == [('X', 'X failed:\nbad input')]
