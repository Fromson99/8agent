from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path(__file__).resolve().parents[3];P=R/'04_EXPERIMENTS/ADR/ADR-0734-deferred-native-read';A=R/'04_EXPERIMENTS/ADR/ADR-0735-retained-basis-consumer';D=A/'artifacts/design';D.mkdir();B=R/'02_BACKEND/lawrag/research/candidates/adr_0735/integrated';parent=R/'02_BACKEND/lawrag/research/candidates/adr_0734/integrated';pcm=json.loads((parent/'candidate.json').read_text());src=parent/'revisions/rev-001/snapshot';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for name in ['criteria.json','baseline.json','dataset.json']:shutil.copy2(P/'artifacts/design'/name,D/name)
v=json.loads((D/'criteria.json').read_text());v['scope']+=' Correct synthetic transport to read the offered laws articles; product unchanged, all criteria unchanged.';put(D/'criteria.json',v)
m=json.loads((A/'실험/manifest.json').read_text());m['lineage']['hypothesis_delta']=v['scope'];m['design'].update(hypothesis=v['scope'],primary_metric='Exact native wire binding and lossless input size reduction',success_criteria=v['contracts'],failure_criteria='Any new regression or preservation failure',criteria_frozen_before_run=True);m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for a in m['design']['arms']:a.update(changes='Completed731' if a['id']=='baseline' else v['scope'],controls='Same scope, cache, data, sources and model policy')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Inherited contracts plus canonical ordering and identical archived view measurement',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));m['dataset'].update(name='Synthetic source and durable wire contracts',version='v2',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True);m['llm_policy']['llm_calls']=[];m['retrieval_accounting'].update(changed=False,not_applicable_reason='Deterministic synthetic contracts and archived representation');m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason'];put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for row in pcm['files']:
 if (R/row['target_path']).is_file():cmd+=['--source',row['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for row in pcm['files']:
 name=row['target_path'];dest=B/'snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src/name,dest)
 if not (R/name).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(B),'--target',name,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
C=B/'snapshot';p=C/'05_TESTS/CONTRACTS/test_focused_input_modality.py';s=p.read_text();assert "if v['sources']:" in s;p.write_text(s.replace("if v['sources']:", "if v['sources'] or v.get('assessment_gaps'):"))
for name in ['measure.py','freeze.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0734'/name).read_text().replace('adr_0734','adr_0735').replace('ADR-0734-deferred-native-read','ADR-0735-retained-basis-consumer')
 if name=='freeze.py':
  pass
 (R/'06_TOOLS/EXPERIMENTS/adr_0735'/name).write_text(s)
print('isolated731 and deterministic column fix prepared')
