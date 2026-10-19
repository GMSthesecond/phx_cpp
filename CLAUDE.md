# Phoenix Land Department Reporting (phx_c++)

Win32 C++ launcher (`phxcpp.exe`) whose buttons run Python automation scripts next to the exe
(Mirror, top-left, runs several of them in a row via mirror.py),
plus three C++ dialogs (Settings, Organization, Rename). Each button is labeled with the Desktop
folder its work goes to (C2E, DMD, STR, ...).

**Read first:**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): diagrams, button → script map, settings.ini keys, data flow
- [docs/INDEX.md](docs/INDEX.md): every function / global / constant by file
- [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md): open bugs and risks
- [docs/TESTING.md](docs/TESTING.md): the regression tests and how to extend them

## Keep the docs in sync
Any change that adds, removes, renames or changes the role of a function, global, constant,
button, script, INI key or file path must also update, in the same change:
1. the source comment on that item,
2. its row in docs/INDEX.md,
3. docs/ARCHITECTURE.md if it affects a diagram, the button map, or the config tables,
4. docs/KNOWN_ISSUES.md: remove fixed issues, add new ones found.

## Keep the tests in sync
Any change that adds or changes behavior (a button, script, C++ dialog, INI key, or logic inside
one) must come with tests in the same change, and `py -m pytest` must pass before the work is
called done. See docs/TESTING.md for how-tos and which existing test file to copy.
1. New or changed button: update `BUTTONS` in `tests/buttons.py` (label, kind, script + args,
   `covered_by`). The app test then clicks it automatically.
2. New script, or new logic in a script: add tests to `tests/test_<script>.py` (new file for a new
   script). Cover what it reads, what it writes or uploads, and its edge cases. Use the `fake_ark`,
   `folders` and `msgboxes` fixtures and `Recorder` for upload steps.
3. New or changed C++ logic: add `TEST(...)` cases to `tests/cpp/test_<file>.cpp`. A new .cpp file
   gets a new `tests/cpp/test_<file>.cpp` that includes `win_fakes.h`, then the .cpp.
4. Bug fix: first write a test that fails because of the bug, then fix the code. When fixing a
   KNOWN_ISSUES bug, remove its xfail / `KNOWN_BUG` marker.
5. Bug found but not fixed: add it to KNOWN_ISSUES.md with an xfail (Python) or `KNOWN_BUG` (C++) test.
6. Intentional behavior change: update the affected tests' expected values. Never weaken, skip or
   delete a test just to make it pass. If a test looks wrong, say so to the user instead.
7. Update the button → tests table in docs/TESTING.md and the Tests section of docs/INDEX.md when
   test files or helpers are added.
8. Tests stay offline and harmless: redirect every new hardcoded path, credential, browser or
   network call (monkeypatch, fakes). If a script uses a service conftest.py doesn't already block,
   add the block there first.
9. In the final message, list the tests added or changed and the pytest result line.

## Comment conventions
- C++: a file header comment (purpose, which button opens it, files/INI it touches); a `//`
  comment above every function; a `//` comment on every file-scope variable, constant and struct.
- Python: a module docstring (purpose, launching button, inputs, outputs); a one-to-few-line
  docstring on every function and class; a `#` comment on every module-level constant.
- Terse plain English. No Args:/Returns: blocks, no doxygen. Don't comment locals unless non-obvious.

## Build and verify
- `build_and_run.bat` builds with MSVC into the repo folder and **launches the app**. Don't run it
  to check a build. Compile into a temp dir instead:
  `vcvars64.bat` (VS at `C:\Program Files\Microsoft Visual Studio\18\Community`), then
  `cl /nologo /EHsc /D UNICODE /D _UNICODE *.cpp <tmp>\app.res user32.lib gdi32.lib ole32.lib shell32.lib comctl32.lib /Fo<tmp>\ /Fe:<tmp>\phxcpp.exe /link /subsystem:windows`
- Python: `py -m py_compile <file>`. Don't run the scripts to test them: they log into Ark/Enverus
  and several upload to live data (C2E, Close Date, Case Update, Maps).
- **Run `py -m pytest` after every change** (about 30 s, offline). It builds the C++ into temp
  folders and clicks every button of a temp build that has stand-in scripts, so it's safe to run.
  `-m "not cpp and not app"` runs only the Python tests (about 2 s). New test code follows the
  comment conventions above.

## Gotchas
- Scripts run with `CREATE_NO_WINDOW`: `print` output is invisible. Only message boxes reach the user.
- Source files are UTF-8 without BOM (except str_verification.py, which has a BOM), LF line endings,
  and contain em dashes. Don't round-trip them through Windows PowerShell 5.1
  `Get-Content`/`Set-Content` (reads as ANSI, writes a BOM). Use the Edit tool.
- Credentials live in `%APPDATA%\PhoenixLandDept\settings.ini` (`[Credentials]`, `[EnverusCredentials]`).
  Never copy them into code, docs or output.
