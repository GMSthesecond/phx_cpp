#include <windows.h>
#include <shlobj.h>  // IFileDialog for the folder picker
#include <string>    // std::wstring for storing the selected folder path
#include <tchar.h>   // _tcsrchr for TCHAR-safe string searching
#include "settings.h" // KeyBinding, g_bindA/g_bindB, and all settings window logic

// Control IDs used only in the main window
#define ID_BUTTON_PICK      1  // "Choose Folder" button
#define ID_LABEL_PATH       2  // static label that shows the chosen folder path
#define ID_TITLE            3  // centered bold title at the top of the window
#define ID_BUTTON_SETTINGS  6  // button that opens the settings window
#define ID_BUTTON_DOWNLOAD  9  // button that launches download_report.py

std::wstring g_selectedFolder;      // stores the last folder the user picked
HFONT        g_hTitleFont = NULL;   // handle to the bold title font, kept alive for the lifetime of the window
HWND         g_hwndMain   = NULL;   // handle to the main window, used by the message loop

void LayoutControls(HWND hwnd) {
    RECT rc;
    GetClientRect(hwnd, &rc); // get the current drawable area of the window
    int w = rc.right;         // client width used to make control positions relative to window size

    HWND hTitle = GetDlgItem(hwnd, ID_TITLE);
    MoveWindow(hTitle,                              0,  10, w,        50, TRUE); // title spans full width so SS_CENTER has a symmetric canvas
    InvalidateRect(hTitle, NULL, TRUE);                                          // force repaint so centered text redraws after resize
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_PICK),   10,  70, 130,      30, TRUE); // folder picker button, fixed size below title
    MoveWindow(GetDlgItem(hwnd, ID_LABEL_PATH),   150,  75, w - 160,  20, TRUE); // path label stretches from after button to right edge
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_A),        10, 120,  60, 60, TRUE); // A button, left of B
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_B),        80, 120,  60, 60, TRUE); // B button, right of A
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_DOWNLOAD), 10, 190, 200, 30, TRUE); // Data Meeting Download below A/B; wider to fit full label
    MoveWindow(GetDlgItem(hwnd, ID_BUTTON_SETTINGS), 10, 230,  90, 30, TRUE); // Settings below Download
}

// Called by Windows for every event (paint, close, etc.) that happens to the main window
LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        case WM_CREATE: {
            g_hTitleFont = CreateFont( // create font for title
                -32, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE,        // -32 = 32px character height; FW_BOLD = bold weight
                DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_SWISS, TEXT("Segoe UI") // ClearType rendering, sans-serif Segoe UI
            );
            HWND hTitle = CreateWindowEx(
                0, TEXT("STATIC"), TEXT("Phoenix Land Department Reporting"),
                WS_CHILD | WS_VISIBLE | SS_CENTER | SS_NOPREFIX, // SS_CENTER horizontally centers text; SS_NOPREFIX prevents & being treated as accelerator
                0, 0, 0, 0, // placeholder position/size — LayoutControls sets the real values
                hwnd, (HMENU)ID_TITLE,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            SendMessage(hTitle, WM_SETFONT, (WPARAM)g_hTitleFont, TRUE); // apply bold font to title label

            CreateWindowEx(
                0, TEXT("BUTTON"), TEXT("Choose Folder"),
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, // BS_PUSHBUTTON = standard clickable button style
                0, 0, 0, 0,
                hwnd, (HMENU)ID_BUTTON_PICK,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            CreateWindowEx(
                0, TEXT("STATIC"), TEXT(""), // starts empty; updated with path after folder is chosen
                WS_CHILD | WS_VISIBLE | SS_LEFT | SS_NOPREFIX,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_LABEL_PATH,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            CreateWindowEx(
                0, TEXT("BUTTON"), g_bindA.label, // label comes from settings.h so it matches the initial binding
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_BUTTON_A,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            CreateWindowEx(
                0, TEXT("BUTTON"), g_bindB.label,
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_BUTTON_B,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            CreateWindowEx(
                0, TEXT("BUTTON"), TEXT("Settings"),
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_BUTTON_SETTINGS,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            CreateWindowEx(
                0, TEXT("BUTTON"), TEXT("Data Meeting Download"),
                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                0, 0, 0, 0,
                hwnd, (HMENU)ID_BUTTON_DOWNLOAD,
                ((LPCREATESTRUCT)lParam)->hInstance, NULL
            );
            LayoutControls(hwnd); // set real positions now that all controls exist
            return 0;
        }
        case WM_SIZE:
            LayoutControls(hwnd); // reposition all controls whenever the window is resized
            return 0;
        case WM_KEYDOWN:
            if (!(lParam & (1 << 30)))                    // bit 30 of lParam is 1 when key was already held — skip repeats
                HandleBoundInput(hwnd, (UINT)wParam, true);
            return 0;
        case WM_KEYUP:
            HandleBoundInput(hwnd, (UINT)wParam, false);
            return 0;
        case WM_LBUTTONDOWN:  HandleBoundInput(hwnd, VK_LBUTTON,  true);  return 0;
        case WM_LBUTTONUP:    HandleBoundInput(hwnd, VK_LBUTTON,  false); return 0;
        case WM_RBUTTONDOWN:  HandleBoundInput(hwnd, VK_RBUTTON,  true);  return 0;
        case WM_RBUTTONUP:    HandleBoundInput(hwnd, VK_RBUTTON,  false); return 0;
        case WM_MBUTTONDOWN:  HandleBoundInput(hwnd, VK_MBUTTON,  true);  return 0;
        case WM_MBUTTONUP:    HandleBoundInput(hwnd, VK_MBUTTON,  false); return 0;
        case WM_XBUTTONDOWN:  // XBUTTON messages encode which button in the high word of wParam
            HandleBoundInput(hwnd, HIWORD(wParam) == XBUTTON1 ? VK_XBUTTON1 : VK_XBUTTON2, true);
            return TRUE; // MSDN requires returning TRUE for XBUTTON messages
        case WM_XBUTTONUP:
            HandleBoundInput(hwnd, HIWORD(wParam) == XBUTTON1 ? VK_XBUTTON1 : VK_XBUTTON2, false);
            return TRUE;
        case WM_COMMAND: {
            if (LOWORD(wParam) == ID_BUTTON_PICK) {
                // Open a modern Vista-style folder picker dialog
                IFileDialog* pfd = nullptr;
                if (SUCCEEDED(CoCreateInstance(CLSID_FileOpenDialog, NULL, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&pfd)))) {
                    DWORD options;
                    pfd->GetOptions(&options);
                    pfd->SetOptions(options | FOS_PICKFOLDERS); // switch to folder-select mode
                    if (SUCCEEDED(pfd->Show(hwnd))) {           // show dialog; SUCCEEDED is false if user cancels
                        IShellItem* psi = nullptr;
                        if (SUCCEEDED(pfd->GetResult(&psi))) {
                            PWSTR folderPath = nullptr;
                            if (SUCCEEDED(psi->GetDisplayName(SIGDN_FILESYSPATH, &folderPath))) { // get the full file system path string
                                g_selectedFolder = folderPath;
                                CoTaskMemFree(folderPath); // free the COM-allocated string after copying it
                                SetWindowTextW(GetDlgItem(hwnd, ID_LABEL_PATH), g_selectedFolder.c_str()); // update label beside button
                            }
                            psi->Release(); // release the shell item COM object
                        }
                    }
                    pfd->Release(); // release the dialog COM object
                }
            } else if (LOWORD(wParam) == ID_BUTTON_SETTINGS) {
                OpenSettings(hwnd); // all settings window logic lives in settings.cpp
            } else if (LOWORD(wParam) == ID_BUTTON_DOWNLOAD) {
                // Build the script path from the directory containing the EXE
                // so download_report.py is found regardless of the working directory
                TCHAR exeDir[MAX_PATH] = {};
                GetModuleFileName(NULL, exeDir, MAX_PATH);
                TCHAR* slash = _tcsrchr(exeDir, TEXT('\\'));
                if (slash) *(slash + 1) = TEXT('\0'); // strip filename, keep trailing backslash

                // Pass the selected folder so the script saves there; Python falls
                // back to ~/Downloads if the string is empty
                TCHAR cmd[4096] = {};
                // Use 'py' (the Windows Python launcher) rather than 'python',
                // which is not in PATH on this machine
                wsprintf(cmd, TEXT("py \"%sdownload_report.py\" \"%s\""),
                    exeDir,
                    g_selectedFolder.c_str()); // returns L"" when no folder selected; Python falls back to ~/Downloads

                STARTUPINFO si = { sizeof(si) };
                PROCESS_INFORMATION pi = {};
                if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
                    CloseHandle(pi.hThread);   // we don't wait for the script to finish
                    CloseHandle(pi.hProcess);  // browser window acts as the progress indicator
                } else {
                    MessageBox(hwnd,
                        TEXT("Could not launch download_report.py.\n")
                        TEXT("Ensure Python is installed and available in your PATH."),
                        TEXT("Error"), MB_ICONERROR);
                }
            }
            return 0;
        }
        case WM_DESTROY:
            if (g_hTitleFont) DeleteObject(g_hTitleFont); // free the GDI font object to avoid a resource leak
            PostQuitMessage(0); // signal the message loop to exit with code 0
            return 0;
    }
    // Let Windows handle any messages we don't care about
    return DefWindowProc(hwnd, msg, wParam, lParam);
}

// Entry point for a Windows GUI application (equivalent to main())
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR, int nCmdShow) {
    CoInitialize(NULL); // initialize COM, required for IFileDialog

    LoadBindings(); // restore saved keybinds before any window is created so initial button labels are correct

    const TCHAR CLASS_NAME[] = TEXT("MainWindow"); // internal name linking the window class to CreateWindowEx

    // Register the main window class
    WNDCLASS wc      = {};
    wc.lpfnWndProc   = WndProc;                        // function that handles main window events
    wc.hInstance     = hInstance;                      // handle to this application
    wc.lpszClassName = CLASS_NAME;
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);     // default white background
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);    // standard arrow cursor
    RegisterClass(&wc);

    RegisterSettingsClass(hInstance); // register the settings window class defined in settings.cpp

    g_hwndMain = CreateWindowEx(
        0, CLASS_NAME, TEXT("Phoenix Land Department Reporting"),
        WS_OVERLAPPEDWINDOW,                           // standard resizable window style
        CW_USEDEFAULT, CW_USEDEFAULT, 1500, 900,       // position and size
        NULL, NULL, hInstance, NULL
    );

    ShowWindow(g_hwndMain, nCmdShow);  // make the window visible using the show state passed by Windows (e.g. normal, maximized)
    UpdateWindow(g_hwndMain);          // force an immediate paint

    // Message loop: keep the app alive, dispatching events to WndProc
    MSG msg = {};
    while (GetMessage(&msg, NULL, 0, 0)) {
        // Route bound keyboard inputs directly to WndProc so they fire even when a child control has focus
        if ((msg.message == WM_KEYDOWN || msg.message == WM_KEYUP) &&
            !Settings_IsListening() &&           // don't intercept while a rebind capture is in progress
            Settings_IsBoundKey((UINT)msg.wParam)) {
            SendMessage(g_hwndMain, msg.message, msg.wParam, msg.lParam);
        } else {
            TranslateMessage(&msg); // convert key events to character messages
            DispatchMessage(&msg);  // send the message to the appropriate WndProc
        }
    }

    CoUninitialize();          // shut down COM before exiting
    return (int)msg.wParam;    // return the exit code posted by PostQuitMessage
}
