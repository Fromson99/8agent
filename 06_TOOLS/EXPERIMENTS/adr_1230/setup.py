from common import *
import shutil
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1228-source-first-authoring-live';technical=ROOT/'04_EXPERIMENTS/ADR/ADR-1229-source-meaning-evidence/artifacts'
assert read(technical/'checks-first.json')['passed']==82 and read(technical/'checks-first.json')['failed']==0
f=read(technical/'design/freeze-current.json');baseline=read(prior/'artifacts/design/baseline.json');x=read(prior/'artifacts/live/execution.json')
assert x['calls']==5 and all(r['normalization']=='SAVED' for r in x['results'])
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer_sha256']
put(DES/'baseline.json',baseline)
for n in ('cases.json','originals.json'):raw(DES/n,read(prior/'artifacts/design'/n))
put(ART/'evaluation-only/expectations.json',read(prior/'artifacts/evaluation-only/expectations.json'))
files=[p for p in (prior/'artifacts/live/objects').rglob('*') if p.is_file()]+[prior/'artifacts/live/work.sqlite',prior/'artifacts/live/binding.json',prior/'artifacts/live/execution.json']+[prior/f'artifacts/live/saved-007-{k}-normalized.json' for k in ('a','b')]
put(DES/'continuation.json',{'source':str((prior/'artifacts/live').relative_to(ROOT)),'binding':read(prior/'artifacts/live/binding.json'),'observations':[r['observation'] for r in x['results']],'files':{str(p.relative_to(ROOT)):sha(p) for p in files},'previous_physical_calls':5,'remaining_physical_calls':4,'normalized_content_unchanged':True})
criteria=read(prior/'artifacts/design/criteria.json');criteria.update(hypothesis='Interpreted text and exact supporting quote separated for every source-only norm part; same bad judgment and absence criteria evaluated after accumulation.',changes='Only1229 meaning/evidence candidate; exact1228 normalized records reused/read-validated, original prior failed source jobs retained. New candidate identity creates new bounded source job, no replay of prior failed job.',maximum_physical_calls=4,stop_rule='One frozen continuation batch; at most4 new physical requests including429fallback/repairs, combined1228+1230<=9; stop unknown/resource; B accumulation requires A draft.')
put(DES/'criteria.json',criteria);put(DES/'technical-binding.json',f)
m=read(ADR/'실험/manifest.json');pm=read(prior/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Two source analyses and compiled drafts from already validated normalization; same predeclared semantic criteria',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')},execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':['ADR-1228-experiment-v1/source-first'],'changes':'Stored1228 failure/normalized2','controls':'Same raw/source/glossary/model'},{'id':'meaning-evidence','role':'candidate','derived_from':['baseline'],'changes':criteria['changes'],'controls':'Same model/authority/canonical validation; no expected answer in product'}]);m['runs'][0].update(arm_ids=['meaning-evidence'],selection_rule=criteria['selection'],artifact_path=str((RUN/'result.json').relative_to(ROOT)));m['llm_policy']=pm['llm_policy'];m['dataset']={**pm['dataset'],'frozen_source':str((DES/'cases.json').relative_to(ROOT)),'sha256':sha(DES/'cases.json')};m['retrieval_accounting']=pm['retrieval_accounting'];(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
names=sorted(set(baseline['release']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'})
C=ac.snapshot(ADR,'meaning-evidence',names,experiment_id=m['experiment_id'],arm_id='meaning-evidence',run_ids=['run-001'])
for n,h in f['files'].items():
 dest=C/'snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/f['code_root']/n,dest);assert sha(dest)==h
 if n not in names:ac.register_file(C,n,upstream_state='absent');names.append(n)
ac.freeze(C);assert not ac.validate(C)
v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(DES/'candidate.json',{'code_root':str(code.relative_to(ROOT)),'files':{n:sha(code/n) for n in names},'candidate_revision':binding,'serving_files':489,'research_transport_files':1})
print('Frozen490; original normalized2 preserved; new physical<=4, cumulative<=9')
