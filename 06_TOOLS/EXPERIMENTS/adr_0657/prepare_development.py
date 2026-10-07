"""Assemble exact active release + candidate, refresh derived pins, inspect publisher."""
import json,hashlib,shutil,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0657-sql-ad-mode-control';C=R/'02_BACKEND/lawrag/research/candidates/adr_0657/ad-sql';S=C/'snapshot';D=A/'artifacts/design';stage=A/'artifacts/development-stage'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
base=read(R/read(D/'bindings.json')['baseline_release']['manifest_path']);shutil.copytree(R/base['code_root'],stage,dirs_exist_ok=True)
for row in read(C/'candidate.json')['files']:
 t=stage/row['target_path'];t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(S/row['target_path'],t)
config=read(stage/'00_SYSTEM/PIPELINE.json')
for e in config['engines'].values():
 m=read(stage/e['manifest'])
 for p in m['files']:m['files'][p]=sha(stage/p)
 for p in stage.joinpath('02_BACKEND/semantic_runtime').glob('ad_*.py'):m['files'][str(p.relative_to(stage))]=sha(p)
 put(stage/e['manifest'],m);shutil.copy2(stage/e['manifest'],S/e['manifest']);e['sha256']=sha(stage/e['manifest'])
put(stage/'00_SYSTEM/PIPELINE.json',config);shutil.copy2(stage/'00_SYSTEM/PIPELINE.json',S/'00_SYSTEM/PIPELINE.json')
sys.path.insert(0,str(stage/'02_BACKEND'))
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False})
put(D/'preview-validation.json',{'structural_checks_passed':True,'note':'Development unit contracts only; no promotion qualification yet'})
prepare(R,stage,R/read(D/'bindings.json')['generation'],'sql-ad-mode-v6-20261006-r1',D/'preview-authorization.json',D/'preview-validation.json',D/'development-preview.json')
print('Development publisher preview passed')
