import csv
import os
import subprocess

_CSV_PATH = r'C:\Users\Ethan Mesecher\Downloads\Continental\EM - Deal Numbers.csv'
_SOURCE_DIR = r'C:\Cloud\Box\Deal Folder\Closed'
_DEST_DIR = r'C:\Users\Ethan Mesecher\Downloads\Continental'

# this was a one-time program
    
def read_deal_data(csv_path):
    """Returns a dict mapping deal_number -> sorted list of unique Base OGLs."""
    deal_ogls = {}
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader)  # skip header row
        for row in reader:
            if not row or not row[0].strip():
                continue
            deal_num = row[0].strip()
            ogl = row[1].strip() if len(row) > 1 else ''
            deal_ogls.setdefault(deal_num, set())
            if ogl:
                deal_ogls[deal_num].add(ogl)
    return {k: sorted(v) for k, v in deal_ogls.items()}


def find_matching_folders(source_dir, deal_numbers):
    matches = {}
    duplicates = {}
    for entry in os.scandir(source_dir):
        if not entry.is_dir():
            continue
        # Folder names are like "4375 - Johnson, Andrew, D (...)"
        deal_num = entry.name.split()[0]
        if deal_num not in deal_numbers:
            continue
        if deal_num in matches:
            duplicates.setdefault(deal_num, [matches[deal_num]]).append(entry.path)
        else:
            matches[deal_num] = entry.path
    return matches, duplicates


def make_dest_name(ogls, original_name):
    prefix = ', '.join(ogls)
    return f'{prefix} - {original_name}'


def main():
    deal_data = read_deal_data(_CSV_PATH)
    print(f'Unique deal numbers in CSV: {len(deal_data)}')

    matches, duplicates = find_matching_folders(_SOURCE_DIR, deal_data.keys())

    if duplicates:
        print('Warning: multiple folders found for the same deal number (using first match):')
        for deal_num, paths in duplicates.items():
            for p in paths:
                print(f'  {deal_num}: {p}')

    missing = deal_data.keys() - matches.keys()
    if missing:
        print(f'No folder found for deal numbers: {sorted(missing, key=int)}')

    print(f'\nCopying {len(matches)} folders to {_DEST_DIR}')
    os.makedirs(_DEST_DIR, exist_ok=True)

    for deal_num, src_path in sorted(matches.items(), key=lambda x: int(x[0])):
        original_name = os.path.basename(src_path)
        ogls = deal_data[deal_num]
        dest_name = make_dest_name(ogls, original_name) if ogls else original_name
        dest_path = os.path.join(_DEST_DIR, dest_name)
        if os.path.exists(dest_path):
            print(f'  Skip (already exists): {dest_name}')
            continue
        print(f'  Copying: {dest_name} ... ', end='', flush=True)
        result = subprocess.run(
            ['robocopy', src_path, dest_path, '/E', '/COPY:DAT'],
            capture_output=True, text=True
        )
        # robocopy exit codes 0-7 are success/informational; 8+ are errors
        if result.returncode >= 8:
            print(f'FAILED (robocopy exit {result.returncode})')
            print(result.stdout)
        else:
            print('done')

    print('\nFinished.')


if __name__ == '__main__':
    main()
