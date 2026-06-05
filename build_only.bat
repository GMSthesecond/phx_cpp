@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
cl /nologo /EHsc *.cpp user32.lib gdi32.lib ole32.lib shell32.lib /Fe:hello_world.exe /link /subsystem:windows
