@echo off
cd /d "%~dp0"
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
rc /nologo app.rc
cl /nologo /EHsc /D UNICODE /D _UNICODE *.cpp app.res user32.lib gdi32.lib ole32.lib shell32.lib comctl32.lib /Fe:phxcpp.exe /link /subsystem:windows
if %errorlevel% == 0 (
    explorer phxcpp.exe
    git push
) else (
    echo Build failed.
    pause
)
