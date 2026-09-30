# Architecture — Phoenix Land Department Reporting

`phxcpp.exe` is a small Win32 launcher (C++) with a grid of buttons. Most buttons run a
Python script that sits next to the exe; a few open dialogs written in C++. The scripts
automate Ark (Phoenix's land system), Enverus/drillinginfo and local Box Drive folders.

Companion docs:
- [INDEX.md](INDEX.md) — every function, global and constant, by file
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) — bugs and risks found while documenting

> Diagrams use [Mermaid](https://mermaid.js.org). They render on GitHub, and in VS Code's
> Markdown preview with the *Markdown Preview Mermaid Support* extension.

---

## 1. System overview

```mermaid
flowchart LR
    user([User])

    subgraph exe["phxcpp.exe (C++, Win32)"]
        main["main.cpp<br/>main window + button dispatch"]
        settings["settings.cpp<br/>Settings dialog"]
        organize["organize.cpp<br/>Organize (finance CSV)"]
        rename["rename.cpp<br/>Rename (files + MP3 tags)"]
    end

    subgraph py["Python scripts (py.exe, no console)"]
        arkScripts["Ark scripts<br/>ppiq, tpp_lhpp, download_report,<br/>cost_to_extend, str_verification,<br/>close_dates, non_hbp_mi, case_matchup"]
        index["doc_inventory_roosevelt / richland / divide"]
        map["map_builder → map_uploader"]
        deceased["deceased.py"]
        ark_common["ark_common.py<br/>(shared helpers)"]
        opcolors["operator_colors.py"]
    end

    subgraph local["Local files"]
        ini[("%APPDATA%\PhoenixLandDept\<br/>settings.ini · session.json ·<br/>organize_rules.ini")]
        desk[("Desktop working folders<br/>(CSV / XLSX / ZIP outputs)")]
        box[("Box Drive<br/>C:\Cloud\Box")]
    end

    subgraph web["External sites"]
        arkSite["Ark<br/>ark.phoenixenergy.com<br/>ark.phxcapitalgroup.com"]
        enverus["Enverus<br/>app.enverus.com"]
        blm["BLM PLSS<br/>gis.blm.gov"]
    end

    user --> main
    main -->|opens| settings & organize & rename
    main -->|"CreateProcess py script.py"| arkScripts & index & map & deceased

    settings -->|"writes [Folders]"| ini
    organize --> ini
    organize & rename --> desk

    arkScripts --> ark_common
    map --> ark_common
    map --> opcolors
    ark_common -->|"reads credentials, folders, session"| ini
    ark_common -->|"Playwright browser"| arkSite

    arkScripts --> desk
    index --> box
    index --> desk
    deceased --> desk
    map --> blm
    map --> enverus
    map --> desk
```

**How a script button works:** `WM_COMMAND` in `main.cpp` finds the exe folder, builds
`py "<exeDir>\script.py"` and calls `CreateProcess` with `CREATE_NO_WINDOW`. It does not
wait (except Index and Map, below). With no console, a script's only visible output is
its own message box. Scripts that don't show one fail silently.

---

## 2. Button map

Layout is set in `LayoutControls` (main.cpp); labels and ids are in the `buttons[]`
table in `WM_CREATE`. **Yellow** = not implemented yet (listed in `g_unwiredButtonIds`).

| Col | Button | Runs | Changes live data? |
|---|---|---|---|
| 1 | PPIQ | `ppiq.py` | No (downloads + local CSV) |
| 1 | Index | `doc_inventory_roosevelt.py` → `_richland.py` → `_divide.py` (background thread, progress bar) | Appends to `Index of Scanned Docs.xlsx` in Box |
| 1 | STR Verification | `str_verification.py` | No |
| 1 | TPP-LHPP | `tpp_lhpp.py` | No |
| 1 | Data Meeting Download | `download_report.py` | No |
| 1 | Cost to Extend | `cost_to_extend.py` | **Yes — Ark Landholdings Update** |
| 1 | Settings *(bottom-left)* | `OpenSettings` (settings.cpp) | settings.ini |
| 2 | ELMI, DNM, HBPNW, LE, LHP, NHBPW, SIB, UNLE, SL | *(yellow — TODO)* | — |
| 3 | Case Matchup | `case_matchup.py` | No |
| 3 | Deceased | `deceased.py` | No (writes upload CSV only) |
| 3 | HBP Wells | *(yellow — TODO)* | — |
| 3 | Organize | `OpenOrganize` (organize.cpp) | No |
| 3 | Rename | `OpenRename` (rename.cpp) | **Renames files / rewrites MP3s** |
| 4 | Close Date | `close_dates.py` | **Yes — Ark Landholdings Update** |
| 4 | Case Update | `non_hbp_mi.py` | **Yes — Ark Units Update** |
| 5 | Map | `map_builder.py` then `map_uploader.py` (background thread) | **Yes — Enverus layers/workspace** |

Not launched by any button: `box_copy_deals.py` (one-off, run by hand).

### Adding a new script button
1. `#define ID_BUTTON_X <unused id>` at the top of main.cpp.
2. Add `{ ID_BUTTON_X, TEXT("Label") }` to `buttons[]` in `WM_CREATE`.
3. Add a `MoveWindow` line for it in `LayoutControls`.
4. Add an `else if (LOWORD(wParam) == ID_BUTTON_X)` branch in `WM_COMMAND` (copy an existing launch branch).
5. Update this table and [INDEX.md](INDEX.md).

---

## 3. Python module dependencies

```mermaid
flowchart TD
    ark_common["ark_common.py<br/>read_credentials · read_enverus_credentials<br/>read_folder · login · trigger_download · _SESSION"]
    opcolors["operator_colors.py"]

    ppiq --> ark_common
    tpp_lhpp --> ark_common
    download_report --> ark_common
    cost_to_extend --> ark_common
    str_verification --> ark_common
    close_dates --> ark_common
    non_hbp_mi --> ark_common
    case_matchup -->|read_folder only| ark_common
    map_builder -->|read_folder only| ark_common
    map_uploader -->|"read_folder, read_enverus_credentials"| ark_common
    map_uploader --> opcolors

    deceased["deceased.py (no local imports)"]
    doc_inv["doc_inventory_*.py (no local imports)"]
    box_copy["box_copy_deals.py (standalone)"]
```

Third-party libraries: `playwright` (all Ark scripts, map_uploader; imported by ark_common
so every importer needs it), `openpyxl` (tpp_lhpp, doc_inventory), `PyPDF2` (doc_inventory),
`requests`, `pyshp`, `shapely` (map_builder).

### Typical Ark script flow

Used by ppiq, tpp_lhpp, download_report, cost_to_extend, str_verification, close_dates and non_hbp_mi.

```mermaid
flowchart LR
    A[read_credentials] --> B["launch Chromium<br/>with session.json"]
    B --> C[open report URL]
    C -->|redirected to Microsoft / Cloudflare| D[ark_common.login]
    C -->|already signed in| E
    D --> E["ark_common.trigger_download<br/>(chevron → Download → wait → notifications)"]
    E --> F[process CSV locally]
    F --> G{uploads?}
    G -->|"cost_to_extend, close_dates, non_hbp_mi"| H["_upload via Ark Data Loader"]
    G -->|others| I[write output CSV / XLSX]
    H --> J[save session.json, close browser]
    I --> J
```

---

## 4. Background runs: Index and Map

### Index — stdout protocol

`RunIndexScripts` runs on its own thread. `RunOneIndexScript` pipes each script's stdout
and parses two tags:

| Line | Meaning |
|---|---|
| `@PROGRESS <done> <total>` | moves the progress bar; `total = -1` → marquee (Richland) |
| `@DONE <processed>` | new documents added, shown in the final summary |

A tag can appear anywhere in a line. The scripts print a `\rProcessing: …` line with no newline
just before each tag, so the tag usually lands mid-line.

```mermaid
sequenceDiagram
    participant U as User
    participant M as main.cpp (UI thread)
    participant T as RunIndexScripts (thread)
    participant P as doc_inventory_county.py
    U->>M: click Index
    M->>T: CreateThread
    T->>M: disable button, show progress bar
    loop Roosevelt, Richland, Divide
        T->>P: CreateProcess (stdout → pipe)
        P-->>T: @PROGRESS done total
        T->>M: PBM_SETPOS / status text
        P-->>T: @DONE processed
        P->>P: append rows to Index of Scanned Docs.xlsx
    end
    T->>M: hide progress, re-enable button
    T->>U: "New documents added" message box
```

### Map

```mermaid
sequenceDiagram
    participant M as main.cpp
    participant T as RunMapThenUpload (thread)
    participant B as map_builder.py
    participant UP as map_uploader.py
    M->>T: CreateThread
    T->>M: button "Building..."
    T->>B: run and wait
    B->>B: Units.csv → BLM PLSS geometry → one zip per operator
    T->>M: button "Uploading..."
    T->>UP: run and wait (always, even if the build failed)
    UP->>UP: upload zips to Enverus, color by operator, save "Phoenix Units" workspace
    UP->>UP: move uploaded zips to Maps\Uploaded (failed ones stay for the next run)
    T->>M: button "Map", re-enabled
```

---

## 5. C++ dialogs

### Settings (settings.cpp)
A modeless popup; the main window stays disabled until it closes. It has four rows
(Data Meeting Download, STR Verification, Close Dates, Maps). **Change** opens the
`PickFolder` COM folder picker, then `SaveFolders` writes `[Folders]` in settings.ini.
`LoadFolders` runs once at startup.

### Organize (organize.cpp)

```mermaid
flowchart TD
    A[Organize clicked] --> B["LoadRules + LoadScrubWords<br/>(organize_rules.ini)"]
    B --> C["read Desktop\Organization\Data.CSV"]
    C --> D{for each transaction}
    D -->|"amount &gt; 0"| I[Income]
    D -->|FindRule matches| R["rule's category"]
    D -->|no rule| Q["ClassifyTx dialog<br/>pick snippet + category"]
    Q -->|Confirm| S[SaveRule] --> R
    Q -->|Ignore| S
    Q -->|Skip| X[dropped]
    R -->|"Ignore rule"| X
    I & R --> E["DayRow: sum amount +<br/>ScrubDesc note"]
    E --> F["write Organized.CSV<br/>one row per day, 15 categories + notes"]
```

### Rename (rename.cpp)

```mermaid
flowchart LR
    A[Rename clicked] --> B[RenameDlg]
    B -->|"1. Generate"| C["GenerateCSV:<br/>list Desktop\Rename,<br/>read MP3 artist → rename.csv"]
    C --> D[user edits New Filename / New Artist]
    D -->|"2. Apply"| E["ApplyRenames:<br/>MoveFile + WriteMp3Artist"]
    E --> F[summary box]
```

---

## 6. Configuration and shared state

All under `%APPDATA%\PhoenixLandDept\`.

### settings.ini

| Section / key | Written by | Read by |
|---|---|---|
| `[Folders] DataMeetingDownload` | Settings dialog | download_report |
| `[Folders] STRVerification` | Settings dialog | str_verification |
| `[Folders] CloseDates` | Settings dialog | close_dates |
| `[Folders] Maps` | Settings dialog | map_builder, map_uploader |
| `[Folders] CaseMatchup` | *nothing (edit by hand)* | case_matchup |
| `[Folders] NonHBPMI` | *nothing* | non_hbp_mi |
| `[Folders] CostToExtend` | *nothing* | cost_to_extend |
| `[Credentials] username, password` | *by hand* | every Ark script, via `ark_common.read_credentials` |
| `[EnverusCredentials] identifier, password` | *by hand* | map_uploader, via `ark_common.read_enverus_credentials` |

When a `[Folders]` key is missing, each script falls back to a hardcoded Desktop path.

### Other shared files

| File | Owner | Purpose |
|---|---|---|
| `session.json` | Ark scripts, via `ark_common._SESSION` | Playwright login cookies; skips re-login |
| `organize_rules.ini` | organize.cpp | `[Rules]` snippet → category, `[ScrubWords]`, `[Meta] ColumnSchema` |
| `<Maps>\operator_colors.json` | operator_colors.py | stable fill color per operator |

### Hardcoded working folders (no setting)

| Feature | Path |
|---|---|
| PPIQ | `Desktop\PPIQ` |
| TPP-LHPP | `Desktop\TPP-LHPP` |
| Deceased | `Desktop\Bring out your dead` |
| Organize | `Desktop\Organization` (`Data.CSV` → `Organized.CSV`) |
| Rename | `Desktop\Rename` |
| Index | Box `Land\Title Folder\Document Images\...`, `Index of Scanned Docs.xlsx`, output `Desktop\Steph Suko` |

---

## 7. Build

`build_and_run.bat` compiles every `*.cpp` with MSVC (VS at `...\Visual Studio\18\Community`),
embeds the manifest, launches the exe with `explorer` (Device Guard blocks `start`), and
then **runs `git push`**. Python scripts are not compiled; they must sit next to the exe.
