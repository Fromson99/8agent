from pathlib import Path
import json,sys,hashlib
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1258-main129-fixed-cap-oracle-live';D=A/'artifacts/design';T=R/'06_TOOLS/EXPERIMENTS/adr_1258';read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
b=read(D/'before.json')['binding'];F=R/read(D/'candidate.json')['snapshot'];paths=[p for p in F.rglob('*') if p.is_file()]+[R/b['engine_root']/p for p in b['engine_files']]+[R/p for p in b['files']]+list(T.glob('*.py'))+list(D.glob('*.json'))
paths += [R/read(D/'active-main129.json')['manifest_path'],R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',R/'06_TOOLS/maintenance/experiment_json.py',R/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json',R/'06_TOOLS/EXPERIMENTS/adr_1244/test_records.py',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py']
paths += list((R/b['data_path']).rglob('*.sqlite'))+list((R/b['data_path']).glob('*manifest*.json'))
files={str(p.relative_to(R)):sha(p) for p in paths};sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
write_summary(D/'freeze.json',{'files':files,'criteria_frozen_before_dispatch':True,'source_database_read_only':True,'isolated_agent_namespace_writes':True,'fixed_engine_files':495,'global_main_pointer_not_required_to_stay129':'Pinned snapshot of MAIN129; parallel root/MAIN work cannot change loaded code','product_patch_injection':False});print('Frozen',len(files),'MAIN129 source495; no global working mutation')
