from pathlib import Path
import json,hashlib,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation';D=A/'artifacts/design';P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
b=read(P/'binding.json');active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');F=R/read(D/'candidate.json')['snapshot'];files={}
paths=[p for p in F.rglob('*') if p.is_file()]+[R/b['engine_root']/p for p in b['engine_files']]+[R/p for p in b['engine_files']]+[R/p for p in b['files']]+[P/p for p in b['connector_files']]+list((R/'06_TOOLS/EXPERIMENTS/adr_1241').glob('*.py'))+list(D.glob('*.json'))
paths += [R/active['manifest_path'],R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'02_BACKEND/lawrag/core/request_deadline.py',R/'06_TOOLS/maintenance/experiment_json.py',R/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json']
paths += [P/p for p in ('binding.json','ACTIVE_MAPPING.json','ontology_settings.json','mapping_local_vctr_current.json')]
paths += list((R/b['data_path']).rglob('*.sqlite'))+list((R/b['data_path']).glob('*manifest*.json'))
for p in paths:files[str(p.relative_to(R))]=sha(p)
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
write_summary(D/'freeze.json',{'files':files,'criteria_frozen_before_dispatch':True,'read_only_database_access':True,'fixed_engine_files':489,'runtime_patch_injection':False});print('Frozen',len(files),'files')
