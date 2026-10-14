"""Extract downloaded archives locally, rejecting paths outside the target."""
import argparse
import os
from pathlib import Path
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('stage', choices=['original', 'iter3', 'iter5'])
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
archive = root / 'servers' / 'downloads' / f'{args.stage}_servers.zip'
target = root / 'servers' / f'{args.stage}_servers'
target.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(archive) as bundle:
    entries = bundle.infolist()
    print(f'{args.stage}: extracting {len(entries)} entries', flush=True)
    for index, entry in enumerate(entries, 1):
        destination = (target / entry.filename).resolve()
        if not destination.is_relative_to(target.resolve()):
            raise ValueError(f'Archive path escapes destination: {entry.filename}')
        native_path = ('\\\\?\\' + str(destination)) if os.name == 'nt' else str(destination)
        if entry.is_dir():
            os.makedirs(native_path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(native_path), exist_ok=True)
            with bundle.open(entry) as source, open(native_path, 'wb') as output:
                import shutil
                shutil.copyfileobj(source, output)
        if index % 25000 == 0:
            print(f'{args.stage}: {index}/{len(entries)}', flush=True)
print(f'{args.stage}: extraction complete', flush=True)
