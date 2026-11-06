"""Snapshot loose managed-folder objects once per trial; keep logical RAW paths."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

import transport as t

EXTERNAL={'law','krx','kofia','expc','fsc','moleg','prec'}
DOCUMENTS={'.xml','.html','.htm','.pdf','.hwp','.hwpx','.docx','.doc'}


def snapshot(folder, work, prefix):
    listed = sorted(p.removeprefix('/') for p in folder.list_paths_in_partition())
    if not listed or len(listed)!=len(set(listed)):
        raise ValueError('EMPTY_OR_DUPLICATE_DOCUMENT_PATH')
    prefix = t.relative(prefix) if prefix else ''
    if prefix and prefix.split('/')[0] not in {'internal',*EXTERNAL}:
        raise ValueError('DOCUMENT_PREFIX_REQUIRES_KNOWN_RAW_SOURCE')
    names={}
    document_count=0
    for name in listed:
        t.relative(name)
        rel=PurePosixPath(prefix,name)
        internal=rel.parts[0]=='internal'
        metadata=(not internal and len(rel.parts)==2 and rel.name=='manifest.json')
        if (any(part.startswith('.') for part in rel.parts) or rel.parts[0] not in {'internal',*EXTERNAL}
                or len(rel.parts)<(3 if internal else 2)
                or (rel.suffix.lower() not in DOCUMENTS and not name.endswith('.genos.json') and not metadata)):
            raise ValueError('DOCUMENT_PATH_REQUIRES_DECLARED_SOURCE_AND_SUPPORTED_FORMAT:'+name)
        if not metadata and not name.endswith('.genos.json'):
            document_count+=1
        if name.endswith('.genos.json') and name[:-11] not in listed:
            raise ValueError('ORPHAN_DOCUMENT_SIDECAR:'+name)
        names[name]='01_DATA/RAW/'+str(rel)
    if not document_count:
        raise ValueError('NO_SOURCE_DOCUMENTS')
    archive=work/'RAW_INPUT.zip'
    manifest_path=work/'documents.json'
    with tempfile.TemporaryDirectory(dir=work,prefix='snapshot-') as temp:
        temp=Path(temp)
        items={}
        files={}
        total=0
        for name,raw_path in names.items():
            local=t.checked(temp,raw_path)
            local.parent.mkdir(parents=True,exist_ok=True)
            h=hashlib.sha256()
            size=0
            with folder.get_download_stream(name) as src, local.open('xb') as dest:
                while data:=src.read(t.CHUNK):
                    total+=len(data)
                    if total>64*1024**3:
                        raise ValueError('DOCUMENT_INPUT_SIZE_LIMIT')
                    dest.write(data)
                    h.update(data)
                    size+=len(data)
            if size==0:
                raise ValueError('EMPTY_DOCUMENT:'+name)
            files[raw_path]=local
            items[name]={'raw_path':raw_path,'bytes':size,'sha256':h.hexdigest()}
        if sorted(p.removeprefix('/') for p in folder.list_paths_in_partition())!=listed:
            raise ValueError('DOCUMENT_LIST_CHANGED_DURING_SNAPSHOT')
        if manifest_path.exists() and t.read(manifest_path)!=items:
            raise ValueError('DOCUMENTS_CHANGED_USE_NEW_TRIAL')
        t.write(manifest_path,items)
        # On a retry, use the original ZIP bytes, including its original ZIP timestamp.
        if archive.exists():
            receipt=t.read(work/'RAW_INPUT.zip.receipt.json')
            if t.sha(archive)!=receipt['sha256'] or archive.stat().st_size!=receipt['bytes']:
                raise ValueError('RAW_SNAPSHOT_CHANGED')
            return receipt
        files['01_DATA/INPUT_MAPPING/filename-exceptions.json']=Path(__file__).with_name('FILENAME_EXCEPTIONS.json')
        files['01_DATA/INPUT_MAPPING/documents.json']=manifest_path
        prepared=t.pack(files,temp/'RAW_INPUT.zip',metadata={'format':'loose-documents-v1','inventory':t.digest(items),'document_count':document_count})
        os.replace(temp/'RAW_INPUT.zip.receipt.json',work/'RAW_INPUT.zip.receipt.json')
        os.replace(temp/'RAW_INPUT.zip',archive)
        return prepared
