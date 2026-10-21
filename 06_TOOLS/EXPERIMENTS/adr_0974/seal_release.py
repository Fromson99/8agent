"""Bind the qualified exact candidate to a non-activating release preview."""
from common import *
import sys,resource
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'02_BACKEND'))
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
from semantic_runtime.control import prepare
assert read(ART/'analysis.json')['strict_success'];assert read(ART/'contracts-final.json')['passed']
seal=read(ART/'stage.json');base=read(ROOT/seal['base_pointer']['manifest_path'])
save(ART/'preview-auth.json',{'purpose':'integration_preview'})
save(ART/'preview-validation.json',{'structural_checks_passed':True,'contracts':{'path':str((ART/'contracts-final.json').relative_to(ROOT)),'sha256':sha(ART/'contracts-final.json')}})
prepare(ROOT,ROOT/seal['roots']['candidate'],ROOT/base['data_path'],'structural-set-preview-0974',ART/'preview-auth.json',ART/'preview-validation.json',ART/'integration-preview.json')
m=read(ADR/'실험/manifest.json');binding={k:v for k,v in m['design']['code_isolation']['candidates'][0].items() if k in ('manifest_path','manifest_sha256','revision_id','revision_sha256')}
integration=read(ART/'integration-preview.json');files=base['files'].copy()
for row in integration['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
candidate=read(ROOT/binding['manifest_path']);assert {r['path'] for r in integration['changes']}<={r['target_path'] for r in candidate['files']}
assert files==seal['files']['candidate']
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':seal['base_pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{}}
save(ART/'release-rebase.json',rebase);reference={'path':str((ART/'release-rebase.json').relative_to(ROOT)),'sha256':sha(ART/'release-rebase.json')}
integration.update(candidate=binding,rebase_receipt=reference)
for row in integration['changes']:row['reason']='Previously authorized model-owned routing/set selection, explicit mandatory scope and numeric bound outputs, derived pins'
save(ART/'integration.json',integration);m['design']['release_rebase']=reference;save(ADR/'실험/manifest.json',m)
print('Qualified preview',len(files),'files; activation not performed')
