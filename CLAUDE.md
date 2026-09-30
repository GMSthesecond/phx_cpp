# Phoenix Land Department Reporting (phx_c++)

Win32 C++ launcher (`phxcpp.exe`) whose buttons run Python automation scripts next to the exe,
plus three C++ dialogs (Settings, Organize, Rename).

**Read first:**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): diagrams, button → script map, settings.ini keys, data flow
- [docs/INDEX.md](docs/INDEX.md): every function / global / constant by file
- [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md): open bugs and risks

## Keep the docs in sync
Any change that adds, removes, renames or changes the role of a function, global, constant,
button, script, INI key or file path must also update, in the same change:
1. the source comment on that item,
2. its row in docs/INDEX.md,
3. docs/ARCHITECTURE.md if it affects a diagram, the button map, or the config tables,
4. docs/KNOWN_ISSUES.md: remove fixed issues, add new ones found.

## Comment conventions
- C++: a file header comment (purpose, which button opens it, files/INI it touches); a `//`
  comment above every function; a `//` comment on every file-scope variable, constant and struct.
- Python: a module docstring (purpose, launching button, inputs, outputs); a one-to-few-line
  docstring on every function and class; a `#` comment on every module-level constant.
- Terse plain English. No Args:/Returns: blocks, no doxygen. Don't comment locals unless non-obvious.

## Build and verify
- `build_and_run.bat` builds with MSVC, **launches the app, and runs `git push`**. Don't run it
  to check a build. Compile into a temp dir instead:
  `vcvars64.bat` (VS at `C:\Program Files\Microsoft Visual Studio\18\Community`), then
  `cl /nologo /EHsc /D UNICODE /D _UNICODE *.cpp <tmp>\app.res user32.lib gdi32.lib ole32.lib shell32.lib comctl32.lib /Fo<tmp>\ /Fe:<tmp>\phxcpp.exe /link /subsystem:windows`
- Python: `py -m py_compile <file>`. Don't run the scripts to test them: they log into Ark/Enverus
  and several upload to live data (Cost to Extend, Close Date, Case Update, Map).

## Gotchas
- Scripts run with `CREATE_NO_WINDOW`: `print` output is invisible. Only message boxes reach the user.
- Source files are UTF-8 without BOM (except str_verification.py, which has a BOM), LF line endings,
  and contain em dashes. Don't round-trip them through Windows PowerShell 5.1
  `Get-Content`/`Set-Content` (reads as ANSI, writes a BOM). Use the Edit tool.
- Credentials live in `%APPDATA%\PhoenixLandDept\settings.ini` (`[Credentials]`, `[EnverusCredentials]`).
  Never copy them into code, docs or output.
