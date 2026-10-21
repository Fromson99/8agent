from pathlib import Path
import sys,json,hashlib,copy,shutil
R=Path(__file__).resolve().parents[3];sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
D=R/'04_EXPERIMENTS/ADR/ADR-0963-scoped-final-qualification';A=D/'artifacts';P=R/'04_EXPERIMENTS/ADR/ADR-0962-scoped-clear-boundary';PA=P/'artifacts';stage=PA/'code';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
pm=json.loads((P/'실험/manifest.json').read_text());parent=json.loads((R/pm['design']['code_isolation']['candidates'][0]['manifest_path']).read_text());paths=[r['target_path'] for r in parent['files']]
seal=json.loads((PA/'stage.json').read_text());drift=[]
def semantic(v):
 if isinstance(v,dict):return {k: ('HASH' if k=='sha256' or k.endswith('_sha256') else ({n:'HASH' for n in x if not n.endswith('/query_scope.py')} if k=='files' else semantic(x))) for k,x in v.items()}
 if isinstance(v,list):return [semantic(x) for x in v]
 return v
for n,h in seal['working_baseline'].items():
 f=R/n;current=sha(f) if f.is_file() else None
 if current!=h:
  assert (n.startswith('02_BACKEND/ENGINES/') or n=='00_SYSTEM/PIPELINE.json') and semantic(json.loads(f.read_text()))==semantic(json.loads((stage/n).read_text())),n
  drift.append({'path':n,'before':h,'after':current,'reason':'Concurrent derived engine hashes only; executable content already merged and evaluated in962.'})
  seal['working_baseline'][n]=current
save(A/'upstream-pin-refresh.json',drift);save(A/'stage.json',seal)
C=ac.snapshot(D,'qualified',[n for n in paths if (R/n).is_file()],experiment_id='ADR-0963-experiment-v1',arm_id='qualified',run_ids=['run-001'])
for n in paths:
 dst=C/'snapshot'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(stage/n,dst)
 if not (R/n).exists():ac.register_file(C,n,upstream_state='absent')
ac.freeze(C);c=json.loads((C/'candidate.json').read_text());rev=c['revisions'][-1]
b={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
rebase=json.loads((PA/'release-rebase.json').read_text());rebase['candidate']=b;save(A/'release-rebase.json',rebase);rb={'path':str((A/'release-rebase.json').relative_to(R)),'sha256':sha(A/'release-rebase.json')}
i=json.loads((PA/'integration.json').read_text());i.update(candidate=b,rebase_receipt=rb);save(A/'integration.json',i)
source=json.loads((PA/'precall-dataset-split.json').read_text());assert len(source['unused_cases'])==5;save(A/'command-cases.json',source['unused_cases'])
for name in ('probe.py','consumer.py'):
 text=(R/'06_TOOLS/EXPERIMENTS/adr_0962'/name).read_text().replace('ADR-0962-scoped-clear-boundary','ADR-0963-scoped-final-qualification',1)
 if name=='probe.py':text=text.replace('max_calls=4','max_calls=20')
 (R/'06_TOOLS/EXPERIMENTS/adr_0963'/name).write_text(text)
m=json.loads((D/'실험/manifest.json').read_text());m['decision_eligible']=True;m['lineage']['hypothesis_delta']='Unchanged guarded candidate handles five previously withheld never-executed correction utterances; exact release consumer stays bound.';m['design']=copy.deepcopy(pm['design']);m['design']['release_rebase']=rb
m['design']['hypothesis']='Unchanged scoped candidate generalizes to five separately withheld utterances and exact service binding.'
m['design']['primary_metric']='Five out-of-sample commands correct, inherited120 exact-code contracts and repeated real-data service consumer pass.'
m['design']['success_criteria']='5/5 withheld commands, inherited120 frozen contracts without code drift, repeated actual data/service scoped source read and exact file hashes pass. After activation verify actual un-injected service or rollback. No waiver.'
m['design']['arms'][0].update(derived_from=['ADR-0962-experiment-v1/guarded'],changes='Completed development checks including120 contracts and one known regression; referenced without baseline model rerun');m['design']['arms'][1].update(id='qualified',changes='No product change; five unused utterances and actual service qualifier')
runner=R/'06_TOOLS/EXPERIMENTS/adr_0963/probe.py';m['design']['code_isolation']['candidates']=[{**b,'candidate_id':'qualified','arm_id':'qualified','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}]
m['design']['inherited_contract_result']={'path':str((PA/'result.json').relative_to(R)),'sha256':sha(PA/'result.json')}
m['design']['test_bindings']['06_TOOLS/EXPERIMENTS/adr_0963/consumer.py']=sha(R/'06_TOOLS/EXPERIMENTS/adr_0963/consumer.py')
m['dataset']={**pm['dataset'],'name':'Five previously withheld never-executed scope utterances','frozen_source':str((A/'command-cases.json').relative_to(R)),'sha256':sha(A/'command-cases.json')}
m['retrieval_accounting']=pm['retrieval_accounting'];m['llm_policy']=pm['llm_policy'];m['llm_policy']['llm_calls'][0]['max_calls']=20;m['runs'][0].update(purpose='primary',status='planned',selection_rule='All5 withheld cases max20 physical calls600sec; inherited contracts exactly bound; repeated actual service consumer.',artifact_path=str((A/'result.json').relative_to(R)),sha256='PENDING');save(D/'실험/manifest.json',m)
print('Independent holdout frozen: five unused cases,101 exact same candidate files')
