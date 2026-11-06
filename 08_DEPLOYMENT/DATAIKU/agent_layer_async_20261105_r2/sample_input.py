"""Read a locally packed, pinned input without extracting or compressing it in DSS."""
import hashlib
import os
import tempfile
from pathlib import Path
import json

INDEX=json.loads(Path(__file__).with_name('SAMPLE.json').read_text())


def snapshot(folder,work,prefix):
    record=INDEX['raw']
    h=hashlib.sha256()
    size=0
    out=work/'RAW_INPUT.zip'
    with tempfile.NamedTemporaryFile(dir=work,delete=False) as dst:
        tmp=Path(dst.name)
        try:
            with folder.get_download_stream(record['file']) as src:
                while chunk:=src.read(1024*1024):
                    size+=len(chunk)
                    if size>record['bytes']:
                        raise ValueError('SAMPLE_ZIP_CHANGED')
                    h.update(chunk)
                    dst.write(chunk)
            if size!=record['bytes'] or h.hexdigest()!=record['sha256']:
                raise ValueError('SAMPLE_ZIP_CHANGED')
            dst.flush()
            os.fsync(dst.fileno())
            os.replace(tmp,out)
        finally:
            tmp.unlink(missing_ok=True)
    return dict(archive='RAW_INPUT.zip',bytes=size,sha256=h.hexdigest())
