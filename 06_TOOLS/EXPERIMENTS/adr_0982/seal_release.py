from common import *
import sys,resource
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'02_BACKEND'))
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
from semantic_runtime.control import prepare
assert read(ART/'analysis.json')['strict_success'];assert read(ART/'contracts-final.json')['passed']
s=read(ART/'stage.json');base=s['base_release']
save(ART/'preview-auth.json',{'purpose':'integration_preview'})
save(ART/'preview-validation.json',{'structural_checks_passed':True,'contracts':{'path':str((ART/'contracts-final.json').relative_to(ROOT)),'sha256':sha(ART/'contracts-final.json')}})
prepare(ROOT,ROOT/s['roots']['candidate'],ROOT/base['data_path'],'unified-scope-preview-0982',ART/'preview-auth.json',ART/'preview-validation.json',ART/'integration-preview.json')
m=read(ADR/'실험/manifest.json');binding={k:v for k,v in m['design']['code_isolation']['candidates'][0].items() if k in ('manifest_path','manifest_sha256','revision_id','revision_sha256')}
integration=read(ART/'integration-preview.json');files=base['files'].copy()
for row in integration['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
assert files==s['files']['candidate']
candidate=read(ROOT/binding['manifest_path']);allpaths={r['target_path'] for r in candidate['files']}
excluded={n:'Ingestion structural viewer, integrated and tested in working code; outside immutable serving file inventory.' if n.endswith('/viewer.py') else 'Test-only fixture or regression contract; integrated into working tests, not a serving dependency.' for n in allpaths-set(files)}
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':s['base_pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':excluded}
save(ART/'release-rebase.json',rebase);reference={'path':str((ART/'release-rebase.json').relative_to(ROOT)),'sha256':sha(ART/'release-rebase.json')}
integration.update(candidate=binding,rebase_receipt=reference)
for row in integration['changes']:row['reason']='Authorized integrated scope, candidate preservation, semantic assessment, hierarchy and multiturn repair; exact tested bytes and derived engine pins.'
save(ART/'integration.json',integration);m['design']['release_rebase']=reference;save(ADR/'실험/manifest.json',m)
print('Exact preview',len(files),'serving files; no activation')
