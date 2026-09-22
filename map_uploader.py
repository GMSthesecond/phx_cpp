import ctypes
import glob
import os
import re

from playwright.sync_api import sync_playwright

import ark_common
import operator_colors as opcolors

_MAPS_DIR = ark_common.read_folder('Maps', r'C:\Users\Ethan Mesecher\Desktop\Maps')

_LOGIN_URL = (
    'https://login.auth.enverus.com/u/login/identifier?state=hKFo2SByUWZJb2JjcW9XX2F6TV90'
    'LTNueTI0Wmd6V0RuUmVwTqFur3VuaXZlcnNhbC1sb2dpbqN0aWTZIG9ON0tac3pLSHVaUW9RT1RrcEhtYkxqMmFS'
    'YjZwcmtno2NpZNkgZk1xTDZmTFE2eDFPQ3B5dER2Y3RRN0t1RkFneFVrSEE#/default'
)
_APP_URL = 'https://app.enverus.com/production/'


def _notify(message):
    ctypes.windll.user32.MessageBoxW(0, message, 'Map Uploader', 0x40)


def _zip_layer_name(zip_path):
    # DI names the saved layer after the zip's own base filename (extension stripped).
    return os.path.splitext(os.path.basename(zip_path))[0]


_NAME_PATTERN = re.compile(r'^\d{4}\.\d{2}\.\d{2}\. (.+)$')


def _operator_from_layer_name(layer_name):
    m = _NAME_PATTERN.match(layer_name)
    return m.group(1) if m else layer_name


def _login(page):
    identifier, password = ark_common.read_enverus_credentials()
    page.goto(_LOGIN_URL, wait_until='networkidle', timeout=30000)
    page.fill('input[name="username"]', identifier)
    page.click('button[type="submit"]')
    page.wait_for_selector('input[type="password"]', timeout=15_000)
    page.fill('input[type="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url('**/gallery/**', timeout=30_000)


def _open_map_layers(page):
    page.goto(_APP_URL, wait_until='networkidle', timeout=45_000)
    page.wait_for_timeout(3000)
    # Whether the panel starts open or closed depends on the workspace's own saved state,
    # so check first rather than assuming — a blind toggle click can close it instead.
    if page.locator('[title="Close Layers Panel"]').count() == 0:
        page.locator('[title="Layer Manager"]').click()
        page.wait_for_timeout(1000)


def _set_fill_color(page, row, rgb):
    # Each row has its own "Fill Color" and "Line Color" pickers (Angular <color-picker>
    # components); scoping by the title="Fill Color" section keeps us out of Line Color's
    # near-identical markup.
    fill_picker = row.locator('section[title="Fill Color"]')
    fill_picker.locator('.color-select-button').click()
    fill_picker.locator('span.custom-color-button_picker').click()
    page.wait_for_timeout(500)

    ok_btn = page.get_by_text('OK', exact=True).last
    popup = ok_btn.locator('xpath=ancestor::*').nth(-2)
    rgb_inputs = popup.locator('input:visible').all()
    if len(rgb_inputs) != 3:
        raise RuntimeError(f'expected 3 RGB inputs, found {len(rgb_inputs)}')
    for inp, value in zip(rgb_inputs, rgb):
        inp.fill(str(value))
        inp.dispatch_event('input')
        inp.dispatch_event('change')
    page.wait_for_timeout(300)
    ok_btn.click()
    # The RGB popup's closing animation can still intercept the next click for a moment;
    # wait for it to actually detach rather than trusting a fixed delay.
    try:
        ok_btn.wait_for(state='hidden', timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(500)

    # Also close the row's "Fill Color" swatch panel itself (still open underneath),
    # so it can't intercept the checkbox click either.
    close_btn = fill_picker.locator('.color-close-button')
    if close_btn.count() > 0 and close_btn.first.is_visible():
        close_btn.first.click()
        page.wait_for_timeout(300)


def _upload_one(page, zip_path, rgb):
    layer_name = _zip_layer_name(zip_path)

    page.get_by_text('ADD LAYERS', exact=False).click()
    page.wait_for_timeout(1000)

    with page.expect_file_chooser() as fc_info:
        page.get_by_text('UPLOAD SHAPEFILE', exact=False).click()
    fc_info.value.set_files(zip_path)

    # The "Shapefile ... has been successfully saved" toast shares its exact text with
    # the new row in the layer list, so a bare text search can match the toast instead of
    # the row. Wait for the toast to clear before searching.
    toast = page.get_by_text('has been successfully saved', exact=False)
    try:
        toast.wait_for(state='hidden', timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(500)

    search = page.locator('input[placeholder="Search Attributes"]')
    search.fill(layer_name)

    # Scope to this specific row's container (identified by DI's own class name) rather
    # than a bare text match, which can also hit the toast or the popup's own title text.
    row = page.locator(f'section.layer-container:has-text("{layer_name}")').first
    try:
        row.wait_for(state='visible', timeout=20_000)
    except Exception:
        raise RuntimeError(f'could not find uploaded layer row for {layer_name!r}')

    _set_fill_color(page, row, rgb)

    checkbox = row.locator('i[title="Toggle checkbox to add this layer to your map view"]')
    apply_btn = page.get_by_text('APPLY', exact=True)
    for attempt in range(5):
        checkbox.click(force=True)
        try:
            page.wait_for_function(
                'el => el.className.includes("green")', arg=checkbox.element_handle(), timeout=3000
            )
            break
        except Exception:
            if attempt == 4:
                raise RuntimeError(f'checkbox for {layer_name!r} never registered as checked')
    page.wait_for_timeout(300)

    apply_btn.click()
    page.wait_for_timeout(2000)


# Applying a layer only affects the live view: "Production (Default)" is a protected,
# read-only workspace whose own SAVE button never enables no matter what changes, so
# nothing sticks past the current tab unless it's saved into a real named workspace.
# This one is created once (via SAVE AS, marked as the account's default) and reused
# on every later run via the now-enabled plain SAVE.
_WORKSPACE_NAME = 'Phoenix Units'


def _save_workspace(page):
    header = page.locator('span.dropdown-selected-item-title')
    current_name = header.get_attribute('title') if header.count() > 0 else None

    if current_name == _WORKSPACE_NAME:
        page.locator('a[title="Save Workspace"]').click(force=True)
        page.wait_for_timeout(1500)
        return

    page.locator('a[title="Save As"]').click()
    page.wait_for_timeout(1000)
    page.locator('input[placeholder="Enter Name"]').fill(_WORKSPACE_NAME)
    page.get_by_text('Make this my default Drillinginfo workspace').click()
    page.wait_for_timeout(300)
    page.get_by_role('button', name='SAVE').click()
    page.wait_for_timeout(2000)


def main():
    zips = [
        z for z in glob.glob(os.path.join(_MAPS_DIR, '*.zip'))
        if _NAME_PATTERN.match(_zip_layer_name(z))
    ]
    if not zips:
        _notify(f'No dated operator zip files found in:\n{_MAPS_DIR}')
        return

    colors = opcolors.load_colors(_MAPS_DIR)
    rescrubbed = opcolors.scrub_red_colors(colors)
    if rescrubbed:
        opcolors.save_colors(_MAPS_DIR, colors)

    uploaded, errors = [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        _login(page)
        _open_map_layers(page)

        for zip_path in zips:
            layer_name = _zip_layer_name(zip_path)
            operator = _operator_from_layer_name(layer_name)
            rgb = opcolors.color_for_operator(operator, colors)
            try:
                _upload_one(page, zip_path, rgb)
                uploaded.append((operator, rgb))
            except Exception as e:
                errors.append(f'{operator}: {e}')

        if uploaded:
            _save_workspace(page)

        browser.close()

    opcolors.save_colors(_MAPS_DIR, colors)

    summary = f'Uploaded {len(uploaded)} of {len(zips)} shapefile(s) to drillinginfo.'
    if rescrubbed:
        summary += (
            f'\n\nReassigned {len(rescrubbed)} old reddish operator color(s): '
            + ', '.join(rescrubbed[:10])
            + ('...' if len(rescrubbed) > 10 else '')
            + '. Re-run Map for any of those operators not uploaded just now to update '
              'their color in drillinginfo too.'
        )
    if errors:
        summary += '\n\nIssues:\n' + '\n'.join(errors[:10])
    _notify(summary)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        _notify(f'Map Uploader failed:\n{e}')
