"""Publish a schema-readable ADR index and verify every byte in its inventory."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'maintenance'))
from experiment_json import SUMMARY_LIMIT, write_raw_json, write_summary


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_inventory(root, catalogue):
    with gzip.open(catalogue,'rt') as stream:
        record=json.load(stream)
    for row in record['files']:
        path=root/row['path']
        if path.stat().st_size!=row['bytes'] or digest(path)!=row['sha256']:
            raise ValueError('Artifact changed: '+row['path'])
    return len(record['files'])


def seal(root, adr):
    artifacts=adr/'artifacts'
    manifest=artifacts/'manifest.json'
    previous=json.loads(manifest.read_text())
    if 'verified_inventory' in previous:
        catalogue=root/previous['verified_inventory']['path']
        assert digest(catalogue)==previous['verified_inventory']['sha256']
        return verify_inventory(root,catalogue)
    if 'raw_json' in previous:
        ref=previous['raw_json'];compressed=Path(ref['path'])
        assert digest(compressed)==ref['stored_sha256']
        with gzip.open(compressed,'rb') as stream:
            content=stream.read()
        assert hashlib.sha256(content).hexdigest()==ref['content_sha256']
        original=json.loads(content)
    else:
        original=previous
    expected_id='-'.join(adr.name.split('-')[:2])
    if original.get('schema_version')!='adr-artifacts-v1' or original.get('adr_id')!=expected_id:
        raise ValueError('Wrong artifact inventory for '+expected_id)
    # The finalizer, hash command and completion record appended to this log.
    # Its previous recorded value remains in the original observer version.
    for row in original['files']:
        path=root/row['path']
        if path==artifacts/'oneclick.log':
            with path.open('rb') as stream:
                prefix=stream.read(row['bytes'])
            if len(prefix)!=row['bytes'] or hashlib.sha256(prefix).hexdigest()!=row['sha256']:
                raise ValueError('Finalization log was modified before its append boundary')
            row['bytes']=path.stat().st_size
            row['sha256']=digest(path)
    catalogue=artifacts/'final-file-inventory.json.gz'
    if not catalogue.exists():
        write_raw_json(catalogue,original)
    count=verify_inventory(root,catalogue)
    with gzip.open(catalogue,'rt') as stream:
        assert json.load(stream)==original
    catalogue_row={'path':str(catalogue.relative_to(root)),'sha256':digest(catalogue),'bytes':catalogue.stat().st_size}
    index={'schema_version':'adr-artifacts-v1','adr_id':expected_id,'verified_inventory':catalogue_row,
           'verified_files':count,'files':[catalogue_row]+[
               {'path':row['path'],'sha256':row['sha256']} for row in original['files']]}
    if len(json.dumps(index,ensure_ascii=False,separators=(',',':')).encode())+1>SUMMARY_LIMIT:
        # The compact manifest binds the complete size-and-hash catalogue.
        # verify_inventory above checks all physical files in either representation.
        index['files']=[catalogue_row]
    temporary=artifacts/'.sealed-manifest.json'
    write_summary(temporary,index)
    versions=artifacts/'.observer-versions'
    versions.mkdir(exist_ok=True)
    original_pointer=versions/('manifest-before-seal-'+digest(manifest)+'.json')
    if not original_pointer.exists():
        os.link(manifest,original_pointer)
    os.replace(temporary,manifest)
    return count
