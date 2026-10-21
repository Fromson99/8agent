"""Seal a small code-only execution closure, sharing immutable source data."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[3]
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0957/scoped'
A=ROOT/'04_EXPERIMENTS/ADR/ADR-0957-multiturn-structured-scope/artifacts'
STAGE=A/'code'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
pointer=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
base=json.loads((ROOT/pointer['manifest_path']).read_text())
files=set(base['files'])
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
    obj=json.loads(p.read_text());files.update(obj.get('files',{}));files.add(str(p.relative_to(ROOT)))
files.update(row['target_path'] for row in json.loads((C/'candidate.json').read_text())['files'])
for rel in sorted(files):
    candidate=C/'snapshot'/rel
    src=candidate if candidate.is_file() else ROOT/rel
    dst=STAGE/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
new='02_BACKEND/semantic_runtime/legal_agent/query_scope.py'
# All current engine consumers of corrected_memory/law_navigation bind the helper too.
for p in (STAGE/'02_BACKEND/ENGINES').rglob('*.json'):
    m=json.loads(p.read_text())
    if 'files' not in m:continue
    if '02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py' in m['files']:
        m['files'][new]=sha(STAGE/new)
    for rel in m['files']:m['files'][rel]=sha(STAGE/rel)
    save(p,m)
config=json.loads((STAGE/'00_SYSTEM/PIPELINE.json').read_text())
def pins(value):
    if isinstance(value,dict):
        if value.get('manifest') and 'sha256' in value and (STAGE/value['manifest']).is_file():value['sha256']=sha(STAGE/value['manifest'])
        for v in value.values():pins(v)
    elif isinstance(value,list):
        for v in value:pins(v)
pins(config);save(STAGE/'00_SYSTEM/PIPELINE.json',config)
manifest={rel:sha(STAGE/rel) for rel in sorted(files)}
save(A/'stage.json',{'code_root':str(STAGE.relative_to(ROOT)),'files':manifest,
    'base_pointer':pointer,'base_pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'working_baseline':{rel:sha(ROOT/rel) if (ROOT/rel).is_file() else None for rel in files}})
print('staged',len(manifest),'files; no source data copied')
