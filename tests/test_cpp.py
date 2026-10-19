"""C++ unit tests for the Organize, Rename and Settings buttons (sources in tests/cpp).

Compiles tests/cpp/*.cpp (which #include organize.cpp, rename.cpp and settings.cpp) into a
temp folder, runs cpp_tests.exe once, and reports each C++ TEST as its own pytest item, so they
show up individually in the VS Code Testing panel. KNOWN_BUG tests report as xfail.
To add a C++ test, write a TEST(name) in tests/cpp/test_<file>.cpp; it is picked up automatically.
"""
import re
import subprocess

import pytest

import ark_common
import msvc
from conftest import FOLDER_KEYS, REPO

CPP_DIR = REPO / 'tests' / 'cpp'  # C++ test sources


def _declared_tests():
    """Names of every TEST / KNOWN_BUG in tests/cpp, read from the source."""
    names = []
    for path in sorted(CPP_DIR.glob('test_*.cpp')):
        names += re.findall(r'^(?:TEST|KNOWN_BUG)\((\w+)', path.read_text(encoding='utf-8'), re.M)
    return names


@pytest.fixture(scope='module')
def cpp_run(tmp_path_factory):
    """Builds and runs cpp_tests.exe once. Returns ({test name: (status, detail)}, sandbox folder)."""
    if not msvc.available():
        pytest.skip(f'Visual Studio build tools not found at {msvc.VCVARS}')
    out_dir = tmp_path_factory.mktemp('cpp_build')
    exe, ok, log = msvc.build_cpp_tests(out_dir)
    if not ok:
        pytest.fail(f'C++ tests did not compile:\n{log}', pytrace=False)
    sandbox = tmp_path_factory.mktemp('cpp_sandbox')
    run = subprocess.run([str(exe), str(sandbox)], capture_output=True, encoding='utf-8', errors='replace',
                         timeout=120)
    results = {}
    for line in run.stdout.splitlines():
        m = re.match(r'(PASS|FAIL|KNOWN|FIXED) (\w+)(?: :: (.*))?$', line)
        if m:
            results[m[2]] = (m[1], m[3] or '')
    if not results:
        pytest.fail(f'cpp_tests.exe printed no results (exit {run.returncode}):\n{run.stdout}\n{run.stderr}',
                    pytrace=False)
    return results, sandbox


@pytest.mark.cpp
@pytest.mark.parametrize('name', _declared_tests())
def test_cpp(name, cpp_run):
    """One C++ test from tests/cpp."""
    results, _ = cpp_run
    status, detail = results.get(name, ('MISSING', 'did not run: cpp_tests.exe stopped before reaching it'))
    if status == 'KNOWN':
        pytest.xfail(detail)
    if status == 'FIXED':
        pytest.fail(f'{name} is marked KNOWN_BUG but now passes: change it to TEST and remove its '
                    'docs/KNOWN_ISSUES.md entry', pytrace=False)
    if status != 'PASS':
        pytest.fail(detail, pytrace=False)


@pytest.mark.cpp
def test_python_reads_settings_written_by_cpp(cpp_run, monkeypatch):
    """Every setting the Settings dialog writes comes back unchanged through ark_common (read_folder,
    read_setting, read_credentials, ...), which is how every script reads them. Sign-ins include a %
    so configparser interpolation can't mangle a password."""
    _, sandbox = cpp_run
    ini = sandbox / 'settings_for_python.ini'
    assert ini.exists(), 'settings_save_then_load_round_trips did not leave its INI behind'
    monkeypatch.setattr(ark_common, '_INI_PATH', str(ini))
    for key in FOLDER_KEYS:
        assert ark_common.read_folder(key, 'default') == 'D:\\Test\\' + key, key
    assert ark_common.read_setting('Files', 'IndexWorkbook', 'default') == r'D:\Test\IndexWorkbook'
    assert ark_common.read_folder('NotASetting', 'default') == 'default'
    assert ark_common.read_credentials() == ('username 100% = ok; #1', 'password 100% = ok; #1')
    assert ark_common.read_enverus_credentials() == ('identifier 100% = ok; #1', 'password 100% = ok; #1')
    assert ark_common.read_slack_token() == 'token 100% = ok; #1'
