"""MSVC build helper for the C++ tests (test_cpp.py) and the button test (test_app_buttons.py).

Uses the same Visual Studio install and cl flags as build_and_run.bat, but always builds into
a temp folder and never launches anything. Set the PHX_VCVARS environment variable to use a
different vcvars64.bat.
"""
import os
import pathlib
import subprocess

from conftest import REPO

# vcvars64.bat of the Visual Studio install build_and_run.bat uses
VCVARS = os.environ.get(
    'PHX_VCVARS', r'C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat')
_VS_INSTALLER = r'C:\Program Files (x86)\Microsoft Visual Studio\Installer'  # holds vswhere.exe, which vcvars64.bat calls
LIBS = 'user32.lib gdi32.lib ole32.lib shell32.lib comctl32.lib'  # same libraries as build_and_run.bat


def available():
    """True if the Visual Studio build tools are installed where expected."""
    return os.path.isfile(VCVARS)


def _run(commands, out_dir):
    """Runs commands in a Visual Studio developer environment with out_dir as the working
    folder, stopping at the first failure. Returns (succeeded, compiler output)."""
    out_dir = pathlib.Path(out_dir)
    assert out_dir.resolve() != REPO.resolve(), 'test builds must never go into the repo folder'
    lines = ['@echo off', f'call "{VCVARS}" >nul']
    for cmd in commands:
        lines += [cmd, 'if errorlevel 1 exit /b 1']
    script = out_dir / 'build.bat'
    script.write_text('\r\n'.join(lines) + '\r\n', encoding='ascii')
    env = dict(os.environ, PATH=_VS_INSTALLER + os.pathsep + os.environ.get('PATH', ''))
    result = subprocess.run(['cmd', '/c', str(script)], cwd=out_dir, capture_output=True,
                            text=True, env=env, timeout=600)
    return result.returncode == 0, result.stdout + result.stderr


def build_app(out_dir):
    """Builds phxcpp.exe (all top-level *.cpp, icon, manifest) into out_dir.
    Returns (path to the exe, succeeded, compiler output)."""
    ok, log = _run([
        f'rc /nologo /i "{REPO}" /fo app.res "{REPO / "app.rc"}"',
        f'cl /nologo /EHsc /D UNICODE /D _UNICODE "{REPO}\\*.cpp" app.res {LIBS} '
        f'/Fe:phxcpp.exe /link /subsystem:windows',
        f'mt -nologo -manifest "{REPO / "phxcpp.exe.manifest"}" -outputresource:phxcpp.exe;1',
    ], out_dir)
    return pathlib.Path(out_dir) / 'phxcpp.exe', ok, log


def build_cpp_tests(out_dir):
    """Builds tests/cpp/*.cpp into out_dir/cpp_tests.exe (a console program).
    Returns (path to the exe, succeeded, compiler output)."""
    ok, log = _run([
        f'cl /nologo /EHsc /std:c++17 /D UNICODE /D _UNICODE "{REPO}\\tests\\cpp\\*.cpp" {LIBS} '
        f'/Fe:cpp_tests.exe /link /subsystem:console',
    ], out_dir)
    return pathlib.Path(out_dir) / 'cpp_tests.exe', ok, log
