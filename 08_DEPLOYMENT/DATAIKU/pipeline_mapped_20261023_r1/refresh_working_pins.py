"""Refresh only changed Oracle adapter pins in working manifests; never select a release."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
CHANGED={
 '02_BACKEND/semantic_runtime/oracle_dp_io.py',
 '02_BACKEND/semantic_runtime/oracle_dp_assets.py',
 '02_BACKEND/semantic_runtime/oracle_query_catalog.py',
 '02_BACKEND/lawrag/pipeline/oracle_migration.py',
 '02_BACKEND/lawrag/pipeline/oracle_query_package.py',
 '02_BACKEND/lawrag/pipeline/oracle_query_publish.py',
 '02_BACKEND/lawrag/pipeline/oracle_query_dataiku.py',
}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
changed=[]
for path in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
    value=json.loads(path.read_text());files=value.get('files',{})
    if not set(files)&CHANGED:continue
    for file in set(files)&CHANGED:files[file]=sha(ROOT/file)
    files['02_BACKEND/semantic_runtime/physical_mapping.py']=sha(ROOT/'02_BACKEND/semantic_runtime/physical_mapping.py')
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');changed.append(str(path.relative_to(ROOT)))
path=ROOT/'00_SYSTEM/PIPELINE.json';value=json.loads(path.read_text())
for entry in value['engines'].values():
    if entry['manifest'] in changed:entry['sha256']=sha(ROOT/entry['manifest'])
path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('Working manifests refreshed:',len(changed),'; selected release unchanged')
