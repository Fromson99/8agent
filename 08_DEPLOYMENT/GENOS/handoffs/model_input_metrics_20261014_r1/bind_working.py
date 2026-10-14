"""Bind only this change's four reviewed files, retaining unrelated stale pins."""
import hashlib, json
from pathlib import Path
O=Path(__file__).resolve().parent; R=O.parents[3]
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
record=json.loads((O/'WORKING_INTEGRATION.json').read_bytes())
files=record['source_files']; p=R/'00_SYSTEM/PIPELINE.json'; pipeline=json.loads(p.read_bytes()); changed=[]
for entry in pipeline['engines'].values():
    name=entry['manifest']; path=R/name; before=path.read_bytes(); engine=json.loads(before); touched=False
    for n,previous in files.items():
        if n not in engine['files']: continue
        assert engine['files'][n] in (previous,sha((O/'preimage'/n).read_bytes()),sha((R/n).read_bytes())),(name,n)
        engine['files'][n]=sha((R/n).read_bytes()); touched=True
    if touched:
        path.write_bytes(enc(engine));entry['sha256']=sha(path.read_bytes());changed.append(name)
p.write_bytes(enc(pipeline))
(O/'WORKING_INTEGRATION.json').write_bytes(enc({'source_files':{n:sha((R/n).read_bytes()) for n in files},
    'engine_manifests':changed,'active_release_changed':False}))
print('Bound four source files in',len(changed),'engine manifests')
