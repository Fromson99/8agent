"""Prospective defect fix: retain a literal when context-free POS filtering empties it."""
from pathlib import Path
import json,hashlib,shutil,sys,copy
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1057-grouped-query-literal-preservation';ART=ADR/'artifacts'
SOURCE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1056/grouped-query-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
plan={'before_implementation':True,'hypothesis':'Valid literal words must not be rejected solely because context-free POS tagging removes all content tokens.',
      'change':'If a literal has no content forms, preserve its NFKC letter/number sequences as one quoted FTS phrase. Never drop an AND operand, change OR/AND, invent synonyms or rebuild the shared index. Punctuation-only remains an actionable validation error.',
      'entry':'Existing grouped query compiler in request-entry and navigation search; same bounded one-repair owner.',
      'failure':'Malformed syntax, unsupported operators, empty punctuation, stale cursor, permission/hash/state violations retain existing errors. No extra model/retry layer.',
      'success':['Original CM023 queries are admitted deterministically','Real in-memory FTS retains 요건 and does not broaden to records lacking that operand','Zero-hit literal remains zero, not invalid nor proof of absence','Existing grouped syntax/ACL/cursor/API and provider scope checks pass','One real CM023 A0 call sequence records terminal outcome; no correctness claim'],
      'baseline':'Completed ADR-1056-experiment-v1/grouped-query; original failure preserved',
      'verification':'Synthetic contracts then exact frozen service API, followed by one CM023 A0 live case; no paired accuracy test.',
      'limits':{'workers':1,'minimum_mem_available_gib':4,'minimum_disk_free_gib':20,'process_address_space_gib':6,'model_calls_per_case':40,'tools':1024,'seconds':1800,'output_cap':None},
      'scope':'Local SQLite only. No MAIN, GENOS, source, index or golden-answer change.'}
save(ART/'implementation-plan.json',plan)
old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1056-grouped-fulltext-compact-laws/실험/manifest.json')
m=read(ADR/'실험/manifest.json');d=m['design']
d.update(hypothesis=plan['hypothesis'],primary_metric='Literal preservation, native admission and observed terminal state',success_criteria='; '.join(plan['success']),failure_criteria=plan['failure'],criteria_frozen_before_run=True,retrieval_stage_plan=copy.deepcopy(old['design']['retrieval_stage_plan']))
d['code_isolation'].update(mode='candidate_snapshot',reason=None)
d['criteria_record']={'path':str((ART/'implementation-plan.json').relative_to(ROOT)),'sha256':sha(ART/'implementation-plan.json')}
d['arms'][0].update(changes='Completed1056 reference only, no live baseline rerun',controls='Frozen preceding source and code')
d['arms'][1].update(changes=plan['change'],controls='Same data/model/prompts/budgets and source/authority/state validation')
m['runs'][0].update(purpose='audit',arm_ids=['grouped-query'],selection_rule='Only CM023 A0, selected from exact reproduced parser defect before this revision',artifact_path=str((ART/'live-result.json').relative_to(ROOT)))
m['retrieval_accounting']=copy.deepcopy(old['retrieval_accounting'])
m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING')
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]=None
m['dataset']={'name':'Approved CM023 product question; same1536documents and evaluator source bindings','version':'same1056','frozen_source':str((ART/'implementation-plan.json').relative_to(ROOT)),'sha256':sha(ART/'implementation-plan.json'),'legal_version_checked':False,'reference_version_checked':False,'note':'No legal accuracy grading; inherited reference targets stay outside product context.'}
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repetitions':1,'temperature':0,'note':'One CM023 A0 sequence with same40call budget'}]
save(ADR/'실험/manifest.json',m)
live=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1056-grouped-fulltext-compact-laws/artifacts/live-probe-plan.json')
live.update(cases=['cm-023'],run_id='run-001',selection_rule=m['runs'][0]['selection_rule'],success='CM023 valid query reaches native search; report later budget and judgment failures separately, not as parser failure.',text='한번 만들어보고 실행해봐 몇몇개의 질문으로 — confirmed parser defect follow-up, one case')
save(ART/'live-probe-plan.json',live)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
rows=read(SOURCE/'candidate.json')['files']
target=c.snapshot(ADR,'literal-r1',[r['target_path'] for r in rows if r['upstream_state']=='present'],experiment_id=m['experiment_id'],arm_id='grouped-query',run_ids=['run-001'])
for r in rows:
    n=r['target_path'];p=target/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(SOURCE/'revisions/rev-001/snapshot'/n,p)
    if r['upstream_state']=='absent':c.register_file(target,n,upstream_state='absent')
    if p.suffix in ('.py','.json'):
        s=p.read_text()
        if 'ADR-1056-experiment-v1' in s:p.write_text(s.replace('ADR-1056-experiment-v1','ADR-1057-experiment-v1'))
c.refresh(target)
preserved=[ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',SOURCE/'candidate.json',ROOT/'04_EXPERIMENTS/ADR/ADR-1056-grouped-fulltext-compact-laws/실험/manifest.json']
save(ART/'preservation.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in preserved},'disk_free_before':shutil.disk_usage(ROOT).free})
for name in ('stage_candidate.py','validate_candidate.py','common.py','run_case.py','run_matrix.py','collect_metrics.py','wire_audit.py','freeze_code.py','freeze_run.py'):
    s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1056'/name).read_text()
    s=s.replace('ADR-1056-grouped-fulltext-compact-laws',ADR.name).replace('adr_1056/grouped-query-r1','adr_1057/literal-r1').replace('adr_1056','adr_1057').replace('ADR-1056-experiment-v1','ADR-1057-experiment-v1').replace('adr1056','adr1057')
    if name=='freeze_code.py':s=s.replace("['run-001','run-002']","['run-001']")
    if name=='run_matrix.py':s=s.replace("'total_cells': 3, 'matrix_complete': completed == 3","'total_cells': 1, 'matrix_complete': completed == 1")
    if name=='freeze_run.py':
        s=s.replace('ADR-1054-ontology-mvp-state-binding/artifacts/design-freeze.json','ADR-1056-grouped-fulltext-compact-laws/artifacts/design-freeze.json').replace('176 focused contracts and exact frozen API/model binding checks; 11 broader legacy failures reproduced unchanged on1055.','Literal-preservation regression contracts and exact frozen API checks; prior1056 failures retained.').replace('Three cases frozen','One case frozen')
    (Path(__file__).parent/name).write_text(s)
print(target)
