"""Dataiku filesystem extraction. Managed folders must expose a filesystem path."""
import argparse
from pathlib import Path
import transport as t


def restore(upload, destination):
    upload, destination = Path(upload), Path(destination)
    with t.lock(destination / 'restore.lock'):
        result = {}
        for name, prefixes in [('RAW_INPUT.zip', ('01_DATA/RAW/', '01_DATA/INPUT_MAPPING/')),
                               ('PIPELINE_SUPPORT.zip', ('01_DATA/LEXICON/', '01_DATA/CATALOG/'))]:
            archive = upload / name
            receipt = t.read(upload / (name + '.receipt.json'))
            if t.sha(archive) != receipt['sha256'] or archive.stat().st_size != receipt['bytes']:
                raise ValueError('UPLOAD_HASH: ' + name)
            result[name] = t.unpack(archive, destination, prefixes=prefixes)
        t.write(destination / 'restored-inputs.json', result)
        return {'status': 'RESTORED', 'data_root': str((destination / '01_DATA').resolve())}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upload', required=True, type=Path)
    p.add_argument('--destination', required=True, type=Path)
    a = p.parse_args()
    print(restore(a.upload, a.destination))
