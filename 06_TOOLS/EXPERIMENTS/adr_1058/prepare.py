"""Reserve a lossless READ-input codec and three native API checks prospectively."""
from pathlib import Path
import json,hashlib,shutil,sys,copy
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1058-bounded-navigation-input-dedup';ART=ADR/'artifacts'
SOURCE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1057/literal-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
plan={'before_implementation':True,'hypothesis':'Exact repeated tool, connection, source and state values can be sent once and losslessly referenced, keeping saved READ inputs under100000characters without deleting context or increasing the limit.',
 'change':'Final request-local READ representation only. Factor exact repeated JSON values, including source strings, while retaining every row, permission, identity, coordinate, state and judgment. No semantic summarizer. Bounded decoder, explicit instructions, independent stored-view/hash verification before a model attempt.',
 'consumer':'Native service.py -> /v1/rag/ask -> existing READ gateway -> model_input_projection -> same canonical decision/output/source checks; audit decoder uses exact frozen codec.',
 'failure_owner':'Local input codec rejects unknown/tampered/cyclic/over-expanding references and reconstruction/hash mismatch before model reservation. No LLM repair of codec corruption. Existing bounded proposal repair and resource/model/tool/deadline budgets unchanged.',
 'success':['All4 saved read-choice views from3questions reconstruct exactly and fall below100000characters including system/schema','No omitted source, selectable action, decision requirement, scope or state','Tamper, literal-marker collision, cross-view and budget checks pass','Actual API from frozen code uses the same codec and preserves final state','Three sequential A0 live cases report all outcomes, physical calls, usage and source/ACL checks; no legal accuracy claim'],
 'stop':'Integrity, resource or unclassified transport error stops remaining cells; bounded product failure is recorded. Never replay reserved cells or raise the100000character limit.',
 'cases':['fsc-hard-005','cm-023','fsc-hard-008'],'arm':'A0','model':'qwen/qwen3.8-27b','max_calls_per_case':40,'max_tools':1024,'max_seconds':1800,'output_cap':None,
 'resources':{'workers':1,'minimum_mem_available_gib':4,'minimum_disk_free_gib':20,'process_address_space_gib':6,'share_data_and_indexes':True,'no_source_copy':True},
 'scope':'Isolated1057 continuation, current data and approved provider routing, original failures and MAIN unchanged; no GENOS activation.'}
save(ART/'implementation-plan.json',plan)
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1057-grouped-query-literal-preservation/실험/manifest.json')
m=read(ADR/'실험/manifest.json');d=m['design'];m['lineage']['hypothesis_delta']=plan['hypothesis']
d.update(hypothesis=plan['hypothesis'],primary_metric='Exact restored values and final assembled READ input characters',success_criteria='; '.join(plan['success']),failure_criteria=plan['stop'],criteria_frozen_before_run=True)
d['retrieval_stage_plan']=copy.deepcopy(parent['design']['retrieval_stage_plan']);sp=d['retrieval_stage_plan']['stages_by_arm'];sp['compact-input']=sp.pop('grouped-query')
d['code_isolation'].update(mode='candidate_snapshot',reason=None)
d['criteria_record']={'path':str((ART/'implementation-plan.json').relative_to(ROOT)),'sha256':sha(ART/'implementation-plan.json')}
d['arms'][0].update(changes='Immutable1057 reference; stored failing views include1056 FSC005/FSC008',controls='Read-only saved input comparison, no new baseline model calls')
d['arms'][1].update(changes=plan['change'],controls='Same fulltext, originals, scope, required judgments, model and limits')
m['runs'][0].update(purpose='audit',arm_ids=['compact-input'],selection_rule='Same3cases selected from previous input-budget failures before this revision; in-sample only',artifact_path=str((ART/'live-result.json').relative_to(ROOT)))
m['retrieval_accounting']=copy.deepcopy(parent['retrieval_accounting'])
m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING')
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]=None
m['dataset']={'name':'Same3approved MVP cases and1536document source; stored4READ views','version':'same1057','frozen_source':str((ART/'implementation-plan.json').relative_to(ROOT)),'sha256':sha(ART/'implementation-plan.json'),'legal_version_checked':False,'reference_version_checked':False,'note':'Source integrity and terminal-state diagnostic, evaluator data stays outside product input; legal accuracy unknown.'}
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':plan['model'],'repetitions':1,'temperature':0,'note':'3caseA0, sequential, at most40physicalcalls per case'}]
save(ADR/'실험/manifest.json',m)
live=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1057-grouped-query-literal-preservation/artifacts/live-probe-plan.json')
live.update(cases=plan['cases'],run_id='run-001',selection_rule=m['runs'][0]['selection_rule'],success=plan['success'],text='지금 반복 이런거 10만자 넘었던거 문제 해결하고 테스트해봐')
save(ART/'live-probe-plan.json',live)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
rows=read(SOURCE/'candidate.json')['files']
target=c.snapshot(ADR,'dense-input-r1',[r['target_path'] for r in rows if r['upstream_state']=='present'],experiment_id=m['experiment_id'],arm_id='compact-input',run_ids=['run-001'])
for r in rows:
    n=r['target_path'];p=target/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(SOURCE/'revisions/rev-002/snapshot'/n,p)
    if r['upstream_state']=='absent':c.register_file(target,n,upstream_state='absent')
    if p.suffix in ('.py','.json'):
        s=p.read_text()
        if 'ADR-1057-experiment-v1' in s:p.write_text(s.replace('ADR-1057-experiment-v1','ADR-1058-experiment-v1'))
c.refresh(target)
preserved=[ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',SOURCE/'candidate.json',ROOT/'04_EXPERIMENTS/ADR/ADR-1057-grouped-query-literal-preservation/실험/manifest.json',ROOT/'04_EXPERIMENTS/ADR/ADR-1056-grouped-fulltext-compact-laws/실험/manifest.json']
save(ART/'preservation.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in preserved},'disk_free_before':shutil.disk_usage(ROOT).free})
for name in ('stage_candidate.py','validate_candidate.py','common.py','run_case.py','run_matrix.py','collect_metrics.py','wire_audit.py','freeze_code.py','freeze_run.py'):
    s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1057'/name).read_text()
    s=s.replace('ADR-1057-grouped-query-literal-preservation',ADR.name).replace('adr_1057/literal-r1','adr_1058/dense-input-r1').replace('adr_1057','adr_1058').replace('ADR-1057-experiment-v1','ADR-1058-experiment-v1').replace('adr1057','adr1058').replace("'grouped-query'","'compact-input'")
    s=s.replace('release-check-v2','release-check').replace('frozen-api-v2','frozen-api').replace('tested-freeze-v2','tested-freeze')
    if name=='run_case.py':
        s=s.replace('dense-input-r1/revisions/rev-002/snapshot','dense-input-r1/revisions/rev-001/snapshot')
        s=s.replace("len(order) == 1 and order == [{'ordinal':1,'case_id':'cm-023','arm':'A0'}]","len(order) == 3 and [x['ordinal'] for x in order] == [1,2,3]")
        s=s.replace("== {('cm-023','A0')}","== {(cid,'A0') for cid in ('fsc-hard-005','cm-023','fsc-hard-008')}")
    if name=='run_matrix.py':s=s.replace("'total_cells': 1, 'matrix_complete': completed == 1","'total_cells': 3, 'matrix_complete': completed == 3")
    if name=='freeze_run.py':
        s=s.replace('ADR-1056-grouped-fulltext-compact-laws/artifacts/design-freeze.json','ADR-1057-grouped-query-literal-preservation/artifacts/design-freeze.json').replace('One case frozen','Three cases frozen').replace('Literal-preservation regression contracts and exact frozen API checks; prior1056 failures retained.','Lossless navigation input contracts and exact frozen API checks; previous failures retained.')
    (Path(__file__).parent/name).write_text(s)
print(target)
