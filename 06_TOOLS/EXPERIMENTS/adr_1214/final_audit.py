from pathlib import Path
import json,hashlib,shutil
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';O=A/'artifacts/run-001';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
baseline=read(R/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector/artifacts/run-001/originals-after.json')
actual={p:sha(R/p) for p in baseline};assert actual==baseline
b=read(D/'baseline.json');code=R/b['release']['code_root'];assert all(sha(code/p)==v for p,v in b['release']['files'].items())
result={'original_database_count':len(actual),'originals_unchanged':True,'original_hashes':actual,'engine_file_count':len(b['release']['files']),'engine_unchanged':True,'engine_root':str(code.relative_to(R)),'observed_active_pointer':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'active_pointer_changed_by_this_task':False,'free_GiB':{str(p):round(shutil.disk_usage(p).free/1024**3,3) for p in (R,Path('/mnt/c'))}}
(O/'final-integrity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('VERIFIED_ORIGINALS',len(actual),'ENGINE',len(b['release']['files']))
