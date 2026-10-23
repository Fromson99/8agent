from common import *
import shutil
s=read(ART/'stage.json');C=ROOT/s['roots']['candidate']
audit=ROOT/'09_ARTIFACTS/AUDITS/20261022-connection-delivery-call-control';assert not audit.exists();audit.mkdir(parents=True)
# Copy reviewed files only; do not overwrite the whole experimental snapshot.
files=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('connection_scope.py','decision_projection.py','evidence_inventory.py','unit_relations.py','law_navigation.py')]
files += ['05_TESTS/CONTRACTS/test_answer_progress_api.py','05_TESTS/CONTRACTS/test_retained_partial_connections.py']
# The candidate's 14-call profile remains experimental: the native required-source
# criterion failed. Deterministic defects can be fixed without activating it.
manifests=list((ROOT/'02_BACKEND/ENGINES').rglob('*.json'))
tracked=files+['00_SYSTEM/PIPELINE.json']+[str(p.relative_to(ROOT)) for p in manifests]
before={}
for n in tracked:
 p=ROOT/n
 if p.exists():
  if n in s['working_before']:assert sha(p)==s['working_before'][n],n
  before[n]=sha(p);dest=audit/'before'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
 else:before[n]=None
save(audit/'before.json',before)
for n in files:
 if before[n] is None:assert not (ROOT/n).exists()
 shutil.copyfile(C/n,ROOT/n)
for p in manifests:
 v=read(p)
 if 'files' not in v:continue
 v['files']={n:sha(ROOT/n) for n in v['files']};save(p,v)
p=ROOT/'00_SYSTEM/PIPELINE.json';v=read(p)
for e in v['engines'].values():e['sha256']=sha(ROOT/e['manifest'])
save(p,v)
save(audit/'after.json',{'copied':{n:sha(ROOT/n) for n in files},'tracked':{n:sha(ROOT/n) for n in tracked},'candidate_dir':s['candidate_dir'],'candidate_revision_sha256':read(ROOT/s['candidate_dir']/'candidate.json')['revisions'][-1]['revision_sha256'],'experimental_profile_integrated':False,'reason':'Required163 coverage not met; do not activate budget14/progress default based on this probe. Existing opt-in control preserved.','main_pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
print('Integrated',len(files),'reviewed files; repinned',len(manifests),'manifests; selected/profile unchanged')
