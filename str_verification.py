"""Verifies landholding Section Names or Areas of Interest against their STR fields.
Launched by two buttons: "STR" (no arguments) and "AOI" (`--aoi`).
Logs into Ark (ark_common credentials/session) and saves the Check STR report as
Check_STR_(EM)_(Full).csv in the running button's folder, then writes one report there:
  STR Verification ([Folders] STRVerification) -> Error_Report.csv, rows whose Section Name
                                                  doesn't match section-township-range
  AOI ([Folders] AOI)                          -> "AOI MM.DD.YYYY.csv" (run date), rows whose
                                                  Area of Interest can't be verified
Shows a box with the error count when run from a button (none from Mirror), or an error box with
the log str_verification_error.log in the button's folder (ark_common.run_button).
Also Mirror's "STR" step (mirror_step, STR check only). Depends on playwright.
"""
import os
import sys
import csv
import datetime
import re
import ark_common

_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=4d424303b039c7d617785bde'  # Ark "Check STR (EM) (Full)" report

_INPUT_NAME = 'Check_STR_(EM)_(Full).csv'  # Downloaded report's file name, overwritten each run

_OUT_DIR    = ark_common.read_folder('STRVerification', r'C:\Users\Ethan Mesecher\Desktop\STR')  # STR Verification working folder ([Folders] STRVerification)
_INPUT_PATH = os.path.join(_OUT_DIR, _INPUT_NAME)  # STR Verification's downloaded report
_STR_ERROR_PATH = os.path.join(_OUT_DIR, 'Error_Report.csv')  # STR Verification output: Section Name mismatches

_AOI_DIR    = ark_common.read_folder('AOI', r'C:\Users\Ethan Mesecher\Desktop\AOI')  # AOI working folder ([Folders] AOI)
_AOI_INPUT_PATH = os.path.join(_AOI_DIR, _INPUT_NAME)  # AOI's downloaded report
_AOI_ERROR_PATH = os.path.join(_AOI_DIR, f'AOI {datetime.date.today():%m.%d.%Y}.csv')  # AOI output: unverifiable Areas of Interest, named for the run date


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_report(page, aoi):
    """Download the report (60s generation wait) and save it to _AOI_INPUT_PATH (AOI) or _INPUT_PATH (STR)."""
    dl = ark_common.trigger_download(page, _REPORT_URL, generation_wait_ms=60_000)
    input_path = _AOI_INPUT_PATH if aoi else _INPUT_PATH
    os.makedirs(os.path.dirname(input_path), exist_ok=True)
    dl.save_as(input_path)
    print(f'Saved: {input_path}', flush=True)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def _process(aoi):
    """Check each row of the downloaded report and write failures to one report.
    aoi=False (STR Verification): reads _INPUT_PATH; Section Name must equal "SS-TTTN-RRRW"
    (zero-padded section; falls back to Township Name when township/range are blank) -> _STR_ERROR_PATH.
    aoi=True (AOI): reads _AOI_INPUT_PATH; Area of Interest (unless blank or Non-Ops) must contain
    the section plus township-range, or the Section Name, each as a whole number (_has_whole)
    -> _AOI_ERROR_PATH.
    Rows with a blank Section Name are skipped by both checks. Returns the number of failures."""
    errors = []  # (id, section_name, combined_str, area_of_interest, issue)

    with open(_AOI_INPUT_PATH if aoi else _INPUT_PATH, "r", encoding="utf-8-sig") as file:
        csv_reader = csv.reader(file)
        for i, row in enumerate(csv_reader):
            if i == 0:
                continue
            id               = row[0]
            section          = row[1]
            township         = row[2]
            range_           = row[3]
            section_name     = row[4]
            if section_name == "":
                continue
            township_name    = row[5]
            area_of_interest = row[7]

            section0      = section
            section_name0 = section_name
            if len(section) == 1 and section.isdigit() and section[0] != "0":
                section = '0' + section
            if len(section_name) > 1 and section_name[0] in "123456789" and section_name[1] == '-':
                section_name = '0' + section_name

            if township == "" or range_ == "":
                combined_str = f"{section}-{township_name}"
            else:
                combined_str = f"{section}-{township}-{range_}"

            if not aoi:
                if section_name != combined_str:
                    errors.append((id, section_name, combined_str, "", "Combined STR doesn't match Section Name"))
            elif area_of_interest not in ("Non-Ops", ""):
                if _has_whole(area_of_interest, section0 + ",") and _has_whole(area_of_interest, township + "-" + range_):
                    pass
                elif _has_whole(area_of_interest, section_name0):
                    pass
                else:
                    errors.append((id, section_name0, combined_str, area_of_interest, "area of interest cannot be verified automatically"))

    out_path = _AOI_ERROR_PATH if aoi else _STR_ERROR_PATH
    with open(out_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if aoi:
            writer.writerow(['ID', 'Section Name', 'Combined STR', 'Area of Interest', 'Issue'])
            writer.writerows(errors)
        else:
            writer.writerow(['ID', 'Section Name', 'Combined STR', 'Issue'])
            writer.writerows((e[0], e[1], e[2], e[4]) for e in errors)

    print(f'Error report: {out_path}', flush=True)
    return len(errors)


def _has_whole(text, token):
    """Whether text contains token as a whole number: no digit right before or after it, so
    "4," isn't found in "14," nor "53N-97W" in "153N-97W". Leading zeros may differ ("04," finds "4,")."""
    core = token.lstrip('0') or token
    return re.search(rf'(?<![0-9])0*{re.escape(core)}(?![0-9])', text) is not None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(aoi=None):
    """Log in to Ark, download the report, save the session, then run the STR check, or the
    AOI check when aoi is True (default: when launched with --aoi). Returns the error count."""
    if aoi is None:
        aoi = '--aoi' in sys.argv[1:]

    with ark_common.ark_page(_REPORT_URL) as page:
        _download_report(page, aoi)

    return _process(aoi)


def mirror_step():
    """Mirror's STR step: run the STR check (never AOI) and return (result kind, report line)."""
    errors = main(aoi=False)
    if errors:
        return ark_common.REVIEW, (f'{ark_common.plural(errors, "Section Name mismatch", "Section Name mismatches")}'
                                   f': review {os.path.basename(_STR_ERROR_PATH)}')
    return ark_common.NOTHING, 'No STR errors found'


def _button():
    """The STR / AOI button: run main() and show the error count and report path."""
    aoi = '--aoi' in sys.argv[1:]
    errors = main(aoi)
    if aoi:
        what = ark_common.plural(errors, 'Area of Interest', 'Areas of Interest') + ' to check by hand'
    else:
        what = ark_common.plural(errors, 'Section Name mismatch', 'Section Name mismatches')
    ark_common.notify('AOI' if aoi else 'STR Verification',
                      f'{what}.\n\nReport:\n{_AOI_ERROR_PATH if aoi else _STR_ERROR_PATH}')


if __name__ == '__main__':
    _LOG_DIR = _AOI_DIR if '--aoi' in sys.argv[1:] else _OUT_DIR  # The running button's folder
    ark_common.run_button('AOI' if '--aoi' in sys.argv[1:] else 'STR Verification', _button,
                          os.path.join(_LOG_DIR, 'str_verification_error.log'))
