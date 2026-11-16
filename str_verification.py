"""Verifies landholding Section Names or Areas of Interest against their STR fields.
Launched by two buttons: "STR" (no arguments) and "AOI" (`--aoi`).
Logs into Ark (ark_common credentials/session) and saves the Check STR report as
Check_STR_(EM)_(Full).csv in the running button's folder, then writes one report there:
  STR Verification ([Folders] STRVerification) -> Error_Report.csv, rows whose Section Name
                                                  doesn't match section-township-range
  AOI ([Folders] AOI)                          -> "AOI MM.DD.YYYY.csv" (run date), rows whose
                                                  section isn't among the sections their Area of
                                                  Interest name lists, or whose name can't be read
Shows a box with the error count when run from a button (none from Mirror), or an error box with
the log str_verification_error.log in the button's folder (ark_common.run_button).
Also Mirror's "STR" step (mirror_step, STR check only) and its last step, "AOI" (aoi_mirror_step,
AOI check only). Depends on playwright.
"""
import os
import sys
import csv
import datetime
import re
import ark_common

_REPORT_URL = 'https://ark.phoenixenergy.com/report?recordId=4d424303b039c7d617785bde'  # Ark "Check STR (EM) (Full)" report

_INPUT_NAME = 'Check_STR_(EM)_(Full).csv'  # Downloaded report's file name, overwritten each run
_COLUMNS = ['Id', 'Section', 'Township', 'Range', 'Section Name', 'Township Name', None,
            'Area of Interest']  # report columns _process reads by position (None = not read); checked on download

_OUT_DIR    = ark_common.read_folder('STRVerification', r'C:\Users\Ethan Mesecher\Desktop\STR')  # STR Verification working folder ([Folders] STRVerification)
_INPUT_PATH = os.path.join(_OUT_DIR, _INPUT_NAME)  # STR Verification's downloaded report
_STR_ERROR_PATH = os.path.join(_OUT_DIR, 'Error_Report.csv')  # STR Verification output: Section Name mismatches

_AOI_DIR    = ark_common.read_folder('AOI', r'C:\Users\Ethan Mesecher\Desktop\AOI')  # AOI working folder ([Folders] AOI)
_AOI_INPUT_PATH = os.path.join(_AOI_DIR, _INPUT_NAME)  # AOI's downloaded report
_AOI_ERROR_PATH = os.path.join(_AOI_DIR, f'AOI {datetime.date.today():%m.%d.%Y}.csv')  # AOI output: rows to check by hand, named for the run date

_AOI_SKIP = ('', 'Non-Ops')  # Area of Interest values the AOI check doesn't look at
_SECTIONS_TR = (r'(\d+(?:\s*,\s*\d+)*)\s*-\s*T?(\d+)\s*([NS])\s*-\s*R?(\d+)\s*([EW])')  # "1, 12, 13-150N-100W": sections, township, range
_AOI_BODY = re.compile(rf'\s*{_SECTIONS_TR}(?:\s*,\s*{_SECTIONS_TR})*\s*', re.I)  # an AOI name's part before "_": one or more section groups
_SECTIONS_TR_RE = re.compile(_SECTIONS_TR, re.I)  # one section group, to pull each out of _AOI_BODY
_AOI_FORMAT = '1, 12, 13-150N-100W _ Name'  # example AOI name shown in the "can't be read" issue


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_report(page, aoi):
    """Download the report (60s generation wait) and save it to _AOI_INPUT_PATH (AOI) or _INPUT_PATH (STR);
    raises if it lacks _COLUMNS (Ark sent another report)."""
    dl = ark_common.trigger_download(page, _REPORT_URL, generation_wait_ms=60_000)
    input_path = _AOI_INPUT_PATH if aoi else _INPUT_PATH
    os.makedirs(os.path.dirname(input_path), exist_ok=True)
    dl.save_as(input_path)
    print(f'Saved: {input_path}', flush=True)
    ark_common.check_columns(input_path, _COLUMNS, 'Check STR')


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def _process(aoi):
    """Check each row of the downloaded report and write failures to one report.
    aoi=False (STR Verification): reads _INPUT_PATH; Section Name must equal "SS-TTTN-RRRW"
    (zero-padded section; falls back to Township Name when township/range are blank) -> _STR_ERROR_PATH.
    aoi=True (AOI): reads _AOI_INPUT_PATH; unless blank or Non-Ops, the Area of Interest name is
    parsed into the sections it covers (_aoi_sections) and the row's section (_row_section) must
    be one of them; otherwise _aoi_issue says why -> _AOI_ERROR_PATH.
    The STR check skips rows with a blank Section Name. Returns the number of failures."""
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
            township_name    = row[5]
            area_of_interest = row[7]
            if section_name == "" and not aoi:
                continue

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
            elif area_of_interest.strip() not in _AOI_SKIP:
                issue = _aoi_issue(area_of_interest,
                                   _row_section(section_name0, section0, township, range_, township_name))
                if issue:
                    errors.append((id, section_name0, combined_str, area_of_interest, issue))

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


def _aoi_sections(area_of_interest):
    """The sections an Area of Interest name covers, as a set of (section, township, range) with
    township/range like (150, 'N') / (100, 'W'); None if the name doesn't follow
    "1, 12-150N-100W[, 25, 36-151N-100W ...] _ Name". Leading zeros and spacing don't matter."""
    body = area_of_interest.split('_', 1)[0]
    if not _AOI_BODY.fullmatch(body):
        return None
    covered = set()
    for sections, t, ns, r, ew in _SECTIONS_TR_RE.findall(body):
        tr = ((int(t), ns.upper()), (int(r), ew.upper()))
        covered.update((int(s),) + tr for s in sections.split(','))
    return covered


def _row_section(section_name, section, township, range_, township_name):
    """A report row's (section, township, range) like _aoi_sections gives: from the Section Name,
    else from Section + Township + Range, else Section + Township Name; None if none can be read."""
    for text in (section_name, f'{section}-{township}-{range_}', f'{section}-{township_name}'):
        found = _aoi_sections(text)
        if found and len(found) == 1:
            return found.pop()
    return None


def _aoi_issue(area_of_interest, row_section):
    """Why a row fails the AOI check ('' if its section is in the Area of Interest): the AOI name
    can't be read, the row's section can't be read, or the section / township-range isn't listed."""
    covered = _aoi_sections(area_of_interest)
    if covered is None:
        return f"Area of Interest can't be read (expected like '{_AOI_FORMAT}')"
    if row_section is None:
        return "Section can't be read from Section Name or Section/Township/Range"
    if row_section in covered:
        return ''
    sec, (t, ns), (r, ew) = row_section
    if any(c[1:] == row_section[1:] for c in covered):
        return f"Section {sec} isn't in this Area of Interest's {t}{ns}-{r}{ew} sections"
    return f"Township-range {t}{ns}-{r}{ew} isn't in this Area of Interest"


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


def aoi_mirror_step():
    """Mirror's AOI step (its last; reported after the other steps): run the AOI check and return
    (result kind, report line) saying whether the AOI error report has any rows to review."""
    errors = main(aoi=True)
    report = os.path.basename(_AOI_ERROR_PATH)
    if errors:
        return ark_common.REVIEW, f'{ark_common.plural(errors, "row")} in the error report: review {report}'
    return ark_common.NOTHING, f'No rows in the error report ({report})'


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
