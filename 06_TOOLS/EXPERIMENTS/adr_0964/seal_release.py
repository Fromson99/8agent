from pathlib import Path
import json,hashlib,sys,resource
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'02_BACKEND'));D=R/'04_EXPERIMENTS/ADR/ADR-0964-scoped-main-integration';A=D/'artifacts'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
from semantic_runtime.control import prepare
p=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text());base=json.loads((R/p['manifest_path']).read_text())
prepare(R,A/'code',R/base['data_path'],'scoped-multiturn-preview-0964',A/'preview-auth.json',A/'preview-validation.json',A/'integration-preview.json')
m=json.loads((D/'실험/manifest.json').read_text());b={k:v for k,v in m['design']['code_isolation']['candidates'][0].items() if k in ('manifest_path','manifest_sha256','revision_id','revision_sha256')}
i=json.loads((A/'integration-preview.json').read_text());files=base['files'].copy()
for row in i['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
c=json.loads((R/b['manifest_path']).read_text());cp={r['target_path'] for r in c['files']};assert {r['path'] for r in i['changes']}<=cp
stage=json.loads((A/'stage.json').read_text());assert all(stage['files'].get(n)==h for n,h in files.items())
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':p['release_manifest_sha256'],'candidate':b,'staged_files':files,'excluded_candidate_paths':{n:'Inherited unconfigured engine pin retained in test closure; not selected for serving' for n in cp-set(files)}}
save(A/'release-rebase.json',rebase);bind={'path':str((A/'release-rebase.json').relative_to(R)),'sha256':sha(A/'release-rebase.json')};i['candidate']=b;i['rebase_receipt']=bind
for row in i['changes']:
 n=row['path'];row['reason']='Scope/multiturn implementation and exact consumer binding' if 'legal_agent' in n or 'ENGINES' in n or n.endswith('PIPELINE.json') else 'Preserve pre-existing recovery/workflow/disabled-knowledge code, fixed in evaluated baseline'
save(A/'integration.json',i);m['design']['release_rebase']=bind;save(D/'실험/manifest.json',m)
print('Release stage sealed',len(files),'files,',len(i['changes']),'changes')
