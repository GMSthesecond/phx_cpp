@echo off
rem Runs the regression tests in tests\ (see docs\TESTING.md). Safe to double-click:
rem nothing logs into Ark/Enverus, uploads, or touches your real files.
cd /d "%~dp0"
py -m pytest --version >nul 2>&1 || py -m pip install pytest
py -m pytest %*
pause
