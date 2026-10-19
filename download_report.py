"""Data Meeting Download, launched by the "DMD" button.

Logs in to ark.phoenixenergy.com with Playwright and downloads the two data-meeting
reports into the [Folders] DataMeetingDownload folder (settings.ini), saving each as
<name>.MM.DD.YYYY.csv, then shows a box saying where. On error shows an error box
(log: download_report_error.log in the folder). Uses ark_common for credentials, login,
session.json and downloads.
"""
import os
import ark_common
from datetime import date

# Both reports are downloaded on every Data Meeting Download run
_DEFAULT_DIR = r'C:\Users\Ethan Mesecher\Desktop\DMD'  # folder used when [Folders] DataMeetingDownload is unset
_REPORT_URLS = [
    'https://ark.phoenixenergy.com/report?recordId=6789387edb62d9fbb70d6b8b',
    'https://ark.phoenixenergy.com/report?recordId=67bf95077dd3a6a940c3fe13',
]


def _out_dir():
    """The output folder: [Folders] DataMeetingDownload, else _DEFAULT_DIR."""
    return ark_common.read_folder('DataMeetingDownload', _DEFAULT_DIR)


def _trigger_and_save(page, out_dir, report_url):
    """Download one report and save it to out_dir with today's date appended to its name."""
    dl = ark_common.trigger_download(page, report_url)

    # The server doesn't send a Content-Disposition filename, so suggested_filename
    # is just a UUID. Strip any existing extension, append today's date as
    # month.day.year, then force a .csv extension so the file is usable immediately.
    filename = dl.suggested_filename or 'report'
    base = filename[:-4] if filename.endswith('.csv') else filename
    today = date.today().strftime('%m.%d.%Y')  # e.g. 06.03.2026
    dest = os.path.join(out_dir, f'{base}.{today}.csv')
    dl.save_as(dest)
    print(f'Saved: {dest}', flush=True)


def main():
    """Resolve the output folder, log in if needed, download both reports, save the session and
    show where they went."""
    out_dir = _out_dir()
    os.makedirs(out_dir, exist_ok=True)


    with ark_common.ark_page(_REPORT_URLS[0]) as page:
        for url in _REPORT_URLS:
            _trigger_and_save(page, out_dir, url)

    ark_common.notify('Data Meeting Download', f'Saved {len(_REPORT_URLS)} reports to:\n{out_dir}')


if __name__ == '__main__':
    ark_common.run_button('Data Meeting Download', main, os.path.join(_out_dir(), 'download_report_error.log'))
