"""Snapshot one existing Dataiku data ZIP without unpacking or recompressing it."""
import hashlib
import os
from pathlib import PurePosixPath
import re
import tempfile

import transport as t


def archive_name(value):
    if not isinstance(value, str) or not value or PurePosixPath(t.relative(value)).suffix.lower() != '.zip':
        raise ValueError('DATA_ZIP_NAME_REQUIRED')
    return value


def snapshot(folder, work, config):
    name = archive_name(config.get('DATA_ZIP_NAME'))
    names = [p.removeprefix('/') for p in folder.list_paths_in_partition()]
    if names.count(name) != 1:
        raise ValueError('UPLOAD_EXACT_DATA_ZIP:' + name)
    expected = config.get('DATA_ZIP_SHA256', '')
    if expected and not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('DATA_ZIP_SHA256_INVALID')
    record = work / 'zip-input.json'
    output = work / 'RAW_INPUT.zip'
    digest, size = hashlib.sha256(), 0
    with tempfile.NamedTemporaryFile(dir=work, delete=False) as out:
        temporary = type(work)(out.name)
        try:
            with folder.get_download_stream(name) as source:
                while data := source.read(t.CHUNK):
                    size += len(data)
                    if size > 64 * 1024**3:
                        raise ValueError('DATA_ZIP_SIZE_LIMIT')
                    digest.update(data)
                    out.write(data)
            value = {'source_path': name, 'bytes': size, 'sha256': digest.hexdigest()}
            if not size or (expected and value['sha256'] != expected):
                raise ValueError('DATA_ZIP_HASH_OR_SIZE')
            if record.exists() and t.read(record) != value:
                raise ValueError('ZIP_INPUT_CHANGED_USE_NEW_TRIAL')
            if output.exists() and (output.stat().st_size != size or t.sha(output) != value['sha256']):
                raise ValueError('SAVED_DATA_ZIP_CHANGED')
            out.flush()
            os.fsync(out.fileno())
            if not output.exists():
                os.replace(temporary, output)
            t.write(record, value)
        finally:
            temporary.unlink(missing_ok=True)
    return dict(archive='RAW_INPUT.zip', bytes=size, sha256=value['sha256'])


def support_declaration(folder, config, raw):
    from flow_runtime import read
    from sample_input import INDEX
    name = archive_name(config.get('SUPPORT_ZIP_NAME', 'PIPELINE_SUPPORT.zip'))
    if name == INDEX['support']['file']:
        if raw['sha256'] != INDEX['raw']['sha256']:
            raise ValueError('DEMO_SUPPORT_REQUIRES_EXACT_SAMPLE')
        value = INDEX['support']
    else:
        value = read(folder, name + '.receipt.json')
        if value.get('archive') != PurePosixPath(name).name:
            raise ValueError('SUPPORT_RECEIPT_NAME_MISMATCH')
    return {k: value[k] for k in ('sha256', 'bytes')}
