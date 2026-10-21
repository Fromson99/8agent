from pathlib import Path
import json,hashlib,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0927-connected-source-release-binding';Q=R/'04_EXPERIMENTS/ADR/ADR-0926-connected-source-release-qualification';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists();assert read(Q/'실험/manifest.json')['reservation']['status']=='completed'
b=read(Q/'artifacts/design/binding.json');full=b['candidate'];b['candidate']={k:full[k] for k in ('manifest_path','manifest_sha256','revision_id','revision_sha256')}
put(D/'binding.json',b);put(D/'full-research-candidate-binding.json',full)
for n in ('baseline.json','concurrent-working-only.json'):put(D/n,read(Q/'artifacts/design'/n))
c={'hypothesis':'Exact four-field release candidate binding preserves the already-qualified source inventory and passes the actual stable integration checker; no product changes.',
 'required':['Actual release integration checker accepts exact candidate binding and all387 staged files','All immutable candidate source hashes remain equal to parent qualification','Parent162 passing checks and actual service consumers remain bound unchanged','MAIN88 pointer unchanged until explicit activation'],
 'model_calls':0,'legal_holdout':False,'failure':'Any revision/hash/dependency mismatch blocks activation.'};put(D/'criteria.json',c)
rebase=read(Q/'artifacts/design/release-rebase.json');rebase['candidate']=b['candidate'];rebase['evaluation']='Same completed ADR0926 qualified387-file product and162checks; exact four-field binding correction after fail-closed preparation. No source changes.';put(D/'release-rebase.json',rebase)
rb={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')}
integration=read(Q/'artifacts/design/integration.json');integration.update(candidate=b['candidate'],rebase_receipt=rb);put(D/'integration.json',integration)
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=c['hypothesis'];m['design'].update(hypothesis=c['hypothesis'],primary_metric='Actual exact release integration contract and candidate file census',success_criteria=c['required'],failure_criteria=[c['failure']],criteria_frozen_before_run=True,release_rebase=rb)
m['design']['arms']=[{'id':'qualified','role':'candidate','derived_from':['ADR-0926-experiment-v1/qualified'],'changes':'Release binding metadata only; product unchanged','controls':'Exact completed parent source and162technical passes'}];m['design']['code_isolation'].update(mode='not_applicable',reason='No product change; exact completed candidate reused.',candidates=[])
m['runs'][0].update(arm_ids=['qualified'],selection_rule='Actual stable release integration checker; parent162checks and consumer evidence retained; no legal holdout.',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='connected-source-exact-release-binding',version='20261019-r1',frozen_source=str((D/'binding.json').relative_to(R)),sha256=sha(D/'binding.json'));m['llm_policy']['llm_calls']=[]
why='Finite release metadata contract; no model/retrieval comparison.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why;put(A/'실험/manifest.json',m)
old=read(Q/'artifacts/design/freeze.json');files={p:h for p,h in old['files'].items() if p.startswith(b['code_root']+'/')}
for p in [*D.glob('*.json'),*T.glob('*.py'),Q/'실험/manifest.json',Q/'artifacts/run-001/result.json',Q/'artifacts/packager-preview.json',Q/'artifacts/candidate-consumer.json',Q/'artifacts/working-consumer.json',Q/'artifacts/main-prepare.log',R/'02_BACKEND/semantic_runtime/release_integration.py',R/'02_BACKEND/semantic_runtime/release_qualification.py']:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'code_root':b['code_root'],'candidate':b['candidate'],'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'legal_holdout':False})
print('Frozen exact four-field release metadata; product unchanged')
