"""For NEW experiment writers: bounded summaries and separately compressed raw data.

Do not replace writers inside already frozen experiments. This helper is not
part of GENOS serving and does not change any model request or response.
"""
from pathlib import Path
import gzip
import hashlib
import json
import os

SUMMARY_LIMIT = 1024 * 1024

def encoded_chunks(value):
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    for part in encoder.iterencode(value):
        yield part.encode('utf-8')
    yield b'\n'

def _publish(temp, path):
    # Exclusive publication: no silent replacement of a previous experiment.
    os.link(temp, path)
    temp.unlink()
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)

def write_summary(path, value):
    """Write <=1 MiB of summary/metrics/references; never silently truncate."""
    path = Path(path)
    assert path.suffix == '.json' and not path.exists()
    # Bound serialization before creating any output file.
    body = bytearray()
    for block in encoded_chunks(value):
        if len(body) + len(block) > SUMMARY_LIMIT:
            raise ValueError('Summary exceeds 1 MiB; use write_raw_json and store its returned reference.')
        body.extend(block)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.writing')
    with temp.open('xb') as f:
        f.write(body); f.flush(); os.fsync(f.fileno())
    _publish(temp, path)

def write_raw_json(path, value):
    """Write raw JSON directly as gzip and return a small content reference.

    Path must end in .json.gz. Save the returned reference with write_summary.
    Both content and stored-file hashes are included; no facts are discarded.
    """
    path = Path(path)
    assert path.name.endswith('.json.gz') and not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.writing')
    h = hashlib.sha256(); original_bytes = 0
    with temp.open('xb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0, compresslevel=1) as f:
            for block in encoded_chunks(value):
                h.update(block); original_bytes += len(block); f.write(block)
        raw.flush(); os.fsync(raw.fileno())
    restored = hashlib.sha256(); restored_bytes = 0
    with gzip.open(temp, 'rb') as f:
        while block := f.read(4 * 1024**2):
            restored.update(block); restored_bytes += len(block)
    assert restored.hexdigest() == h.hexdigest() and restored_bytes == original_bytes
    with temp.open('rb') as f: stored_hash = hashlib.file_digest(f, 'sha256').hexdigest()
    size = temp.stat().st_size
    _publish(temp, path)
    return dict(path=str(path), encoding='gzip', content_sha256=h.hexdigest(),
                stored_sha256=stored_hash, original_bytes=original_bytes, stored_bytes=size)
