"""GENOS-side unpacking of an uploaded raw-document ZIP, retaining source bytes."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import uuid
import zipfile

import transport as t

SOURCES = {'internal', 'external', 'law', 'krx', 'kofia', 'expc', 'fsc', 'moleg', 'prec'}
DOCUMENTS = {'.xml', '.html', '.htm', '.pdf', '.hwp', '.hwpx', '.docx', '.doc'}


def target_name(name):
    t.relative(name)
    relative = name.removeprefix('01_DATA/RAW/')
    parts = PurePosixPath(relative).parts
    if not parts or parts[0] not in SOURCES or len(parts) < (3 if parts[0] == 'internal' else 2):
        raise ValueError('RAW_ZIP_REQUIRES_SOURCE_PATH:' + name)
    if any(part.startswith('.') for part in parts):
        raise ValueError('RAW_ZIP_HIDDEN_PATH')
    sidecar = relative.endswith('.genos.json')
    metadata = parts[0] != 'internal' and len(parts) == 2 and parts[-1] == 'manifest.json'
    if not sidecar and not metadata and PurePosixPath(relative).suffix.lower() not in DOCUMENTS:
        raise ValueError('RAW_ZIP_UNSUPPORTED_MEMBER:' + name)
    return '01_DATA/RAW/' + relative, not (sidecar or metadata)


def unpack(archive, workspace):
    with zipfile.ZipFile(archive) as z:
        if 'TRANSPORT.json' in z.namelist():
            return t.unpack(archive, workspace, prefixes=('01_DATA/RAW/', '01_DATA/INPUT_MAPPING/'))
        entries = z.infolist()
        names = [e.filename for e in entries]
        if len(names) != len(set(names)):
            raise ValueError('RAW_ZIP_DUPLICATE_MEMBER')
        mapped, total, documents = {}, 0, 0
        for entry in entries:
            t.relative(entry.filename.rstrip('/') if entry.is_dir() else entry.filename)
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise ValueError('RAW_ZIP_SPECIAL_MEMBER')
            if entry.is_dir():
                continue
            name, document = target_name(entry.filename)
            if name in mapped or entry.file_size <= 0:
                raise ValueError('RAW_ZIP_DUPLICATE_TARGET_OR_EMPTY_FILE')
            mapped[name] = entry
            total += entry.file_size
            documents += int(document)
        if not documents or total > 100 * 1024**3 or shutil.disk_usage(workspace).free < total + 512*t.CHUNK:
            raise ValueError('RAW_ZIP_EMPTY_OR_CAPACITY')
        for name in mapped:
            if name.endswith('.genos.json') and name[:-11] not in mapped:
                raise ValueError('RAW_ZIP_ORPHAN_SIDECAR')
        files, inventory = {}, {}
        for name, entry in mapped.items():
            destination = t.checked(workspace, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name('.raw-zip-' + uuid.uuid4().hex)
            digest, size = hashlib.sha256(), 0
            try:
                with z.open(entry) as source, temporary.open('xb') as out:
                    while data := source.read(t.CHUNK):
                        size += len(data)
                        if size > entry.file_size:
                            raise ValueError('RAW_ZIP_MEMBER_SIZE')
                        digest.update(data)
                        out.write(data)
                if size != entry.file_size:
                    raise ValueError('RAW_ZIP_MEMBER_SIZE')
                item = {'bytes': size, 'sha256': digest.hexdigest()}
                if destination.exists():
                    if destination.stat().st_size != size or t.sha(destination) != item['sha256']:
                        raise ValueError('RAW_ZIP_RESTORE_CONFLICT')
                else:
                    temporary.rename(destination)
                files[name] = item
                inventory[name.removeprefix('01_DATA/RAW/')] = dict(item, raw_path=name)
            finally:
                temporary.unlink(missing_ok=True)
        mapping = Path(workspace) / '01_DATA/INPUT_MAPPING'
        mapping.mkdir(parents=True, exist_ok=True)
        t.write(mapping / 'documents.json', inventory)
        shutil.copyfile(Path(__file__).parent / '00_SYSTEM/FILENAME_EXCEPTIONS.json', mapping / 'filename-exceptions.json')
        for path in (mapping / 'documents.json', mapping / 'filename-exceptions.json'):
            files[path.relative_to(workspace).as_posix()] = {'bytes': path.stat().st_size, 'sha256': t.sha(path)}
        return {'format': t.FORMAT, 'files': files,
                'metadata': {'format': 'uploaded-raw-zip-v1', 'document_count': documents,
                             'source_zip_sha256': t.sha(archive), 'inventory': t.digest(inventory)}}
