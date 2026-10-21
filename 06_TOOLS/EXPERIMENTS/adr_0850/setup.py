from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0850-minimal-output-qualification';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0850/qualified';P=R/'02_BACKEND/lawrag/research/candidates/adr_0848/compact'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists();D.mkdir(exist_ok=True)
criteria={'hypothesis':'Preserve the existing normalization and partial-operation owners while decoding minimal replies; authoritative consumer checks and raw/decoded receipts remain separate.',
 'success':['all finite technical states pass','existing 121 regression contracts retained','no extra physical calls for allowed mechanical normalization','legacy partial consumers receive unchanged raw partial value','numbered references decode against full reconstructed schema','literal quote/unknown/conflicting/state rejection preserved','all integrated source bytes equal the qualified revision'],
 'failure':['semantic inference','permission/hash/state bypass','silent retry or raw overwrite','existing canonical response differs'],
 'matrix':{'host_constant':['omitted','exact','conflict'],'source_arity':[0,1,3],
   'legacy_partial_protocol':['TurnDecision','SourceSelectionDecision'],'reply':['complete','partial'],
   'deduplication':['disabled','enabled'],'transport':['success','unknown'],'role':['navigation','assessment','comparison','AD','VLM']},
 'evaluation':'finite software contract boundary cases declared before qualification; not legal holdout or actual model latency/accuracy certification',
 'model_calls':0,'MAIN':'generation81 unchanged; working integration only after successful technical qualification',
 'failure_ownership':'Existing gateway/stage; projection never retries; deadlines/call budgets unchanged; partial consumers retain their own validators.'}
put(D/'criteria.json',criteria)
put(D/'working-before.json',{x['target_path']:sha(R/x['target_path']) if (R/x['target_path']).exists() else None for x in read(P/'candidate.json')['files']})
put(D/'baseline.json',{'pointer':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
old=read(P/'candidate.json');S=P/'revisions'/old['revisions'][-1]['revision_id']/'snapshot'
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','qualified','--experiment-id','ADR-0850-experiment-v1','--arm-id','qualified','--run-id','run-001']
for x in old['files']:
 if x['upstream_state']=='present':cmd+=['--source',x['target_path']]
subprocess.run(cmd,cwd=R,check=True)
for x in old['files']:
 target=C/'snapshot'/x['target_path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(S/x['target_path'],target)
 if x['upstream_state']=='absent':subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',x['target_path'],'--upstream-state','absent'],cwd=R,check=True)
for name in ('run_tests.py','repin.py'):
 text=(R/'06_TOOLS/EXPERIMENTS/adr_0848'/name).read_text().replace('adr_0848/compact','adr_0850/qualified')
 (Path(__file__).parent/name).write_text(text)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact reconstruction and consumer/normalization integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Completed ADR0848 codec with explicit preserved legacy consumer boundaries' if arm['id']=='qualified' else 'Completed ADR0848 and retained working before hashes',controls=['same canonical contracts and sources','no real model calls','same retry/deadline owner'])
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='minimal-output-boundary-contracts',version='20261016-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=False,reference_version_checked=False)
m['runs'][0].update(selection_rule='All declared finite technical boundary states plus retained contracts',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
reason='No retrieval modification or legal-quality comparison; output/consumer contracts only.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
print('Prospective finite contracts and isolated candidate ready')
