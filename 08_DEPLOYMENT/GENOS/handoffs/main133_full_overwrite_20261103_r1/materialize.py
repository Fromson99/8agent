"""Build the ordinary release-gate ZIP locally, never as a nested mail attachment."""
import json
from pathlib import Path
import zipfile


def materialize_code_zip(package):
    spec = json.loads((package / 'PACKAGE.json').read_bytes())
    with zipfile.ZipFile(package / 'code.zip', 'w', compression=zipfile.ZIP_STORED) as archive:
        content = [('CODE_MANIFEST.json', (package / 'CODE_MANIFEST.json').read_bytes())]
        content += [(name, (package / spec['payload_paths'][name]).read_bytes()) for name in sorted(spec['code'])]
        for name, raw in content:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, raw)
