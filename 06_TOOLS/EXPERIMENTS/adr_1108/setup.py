from pathlib import Path
import json,hashlib,shutil,sys,importlib.util
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1108-genos-applied-mode-main';C=R/'02_BACKEND/lawrag/research/candidates/adr_1108/applied-mode-r1';S=A/'artifacts/staged-code';D=A/'artifacts/design'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text());base=json.loads((R/active['manifest_path']).read_text());code=R/base['code_root']
assert active['generation']==106 and not S.exists()
put(D/'baseline.json',{'pointer':active,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':base})
for n,h in base['files'].items():
 assert sha(code/n)==h
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code/n,p)
p=C/'snapshot/02_BACKEND/semantic_runtime/pipeline.py';p.write_text(p.read_text().replace('An explicit leading source marker narrows the request before any retrieval.','An explicit source marker selects a category or the full authorized scope.'))
for f in json.loads((C/'candidate.json').read_text())['files']:shutil.copyfile(R/f['snapshot_path'],S/f['target_path'])
# Data is shared, never duplicated; rehash only code/schema pins.
(S/'01_DATA').symlink_to(R/'01_DATA',target_is_directory=True)
sys.path.insert(0,str(R/'02_BACKEND'))
from semantic_runtime.control import rehash_engines
report=rehash_engines(S,apply=True);put(D/'rehash.json',report)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
spec=importlib.util.spec_from_file_location('adr_candidate1108',R/'06_TOOLS/COMMANDS/adr_candidate.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
existing={f['target_path'] for f in json.loads((C/'candidate.json').read_text())['files']}
changed={n:sha(S/n) for n,h in base['files'].items() if sha(S/n)!=h}
for n in changed:
 target=C/'snapshot'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(S/n,target)
 if n not in existing:m.register_file(C,target=n,upstream_state='present')
put(D/'staging.json',{'code_root':str(S.relative_to(R)),'files':{n:sha(S/n) for n in base['files']},'changed':changed,'base_manifest_sha256':active['release_manifest_sha256']})
print('staged',len(base['files']),'changed',len(changed))
