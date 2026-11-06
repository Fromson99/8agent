from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1374-grounded-mention-conflict-explicit-reuse/artifacts'
DES.mkdir(exist_ok=False)
f=read(P/'design/candidate.json')
files=list(f['selected_files'])
before={n:sha(ROOT/n) for n in files}
put(DES/'working-before.json',before)
put(DES/'candidate-parent.json',f)
for n in ('baseline','source-scope','originals','originals-origin','records','provider-policy'):
    put(DES/(n+'.json'),read(P/'design'/(n+'.json')))
shutil.copytree(P/'transport',ART/'transport')
products=['02_BACKEND/semantic_runtime/ontology_work/'+n for n in ('wiki_projection.py',)]
assert all(before[n]==f['selected_files'][n] for n in products)
criteria={'hypothesis':'A NEW source-grounded observation can be recorded without assigning an unrelated old node; preserve nodes when asserting SAME or a contradiction with an existing rule.',
 'success':['Exact preserved first Qwen comparison from1374 passes with NEW and no existing node, supported by its own original; prior graph remains unchanged, conflict preserved. Reject false quotes or unsupported links.'],
 'failure':['Any substitution of model output, loss of source proof or new physical sends.'],'limits':{'model_calls':0}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Reopenable, source-grounded charter bundle accepted by compiler',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed1374 rejected Qwen first comparison from prior recorded case',controls='Reference only')
m['design']['arms'][1].update(changes='Validate source evidence for NEW; require existing target only for comparisons against an existing node',controls='Same public originals, archived judgment, all selected statements, model and provider policy')
m['dataset'].update(name='Actual archived charter judgment and legal source snapshot',version='1354-frozen',frozen_source=str((DES/'records.json').relative_to(ROOT)),sha256=sha(DES/'records.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Fresh build once. Validation may request up to four additional proposals per stage. Stop on unknown.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[]
m['runs'][0]['selection_rule']='Replay exact first original model proposals for normalization and comparison; synthetic validation controls. No model call.'
put(DES/'replay-origins.json',{f:sha(P/'followup-conflict/canonical'/f) for f in ('001.json.gz','001-output.json.gz','002.json.gz','002-output.json.gz')})
m['dataset'].update(name='Two preserved exact proposal inputs and outputs from1374',version='1376-r1',frozen_source=str((DES/'replay-origins.json').relative_to(ROOT)),sha256=sha(DES/'replay-origins.json'))
for x in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):x['not_applicable_reason']='Fixed original authoring input; no answer/retrieval search experiment.'
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'repaired',files,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n in files:
    if sha(can/'snapshot'/n)!=f['selected_files'][n]:
        shutil.copyfile(ROOT/f['code_root']/n,can/'snapshot'/n)
assert all(sha(can/'snapshot'/n)==f['selected_files'][n] for n in files)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':products})
print(can/'snapshot')
