"""Reserve criteria and inherit only the preceding candidate's bound code."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-1056-grouped-fulltext-compact-laws'
ART = ADR/'artifacts'
SOURCE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1055/delta-repair-r1'
def read(p): return json.loads(p.read_text())
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

plan = {
 'before_implementation':True,
 'hypothesis':'Preserve AI-authored query groups and phrase/AND/OR semantics; remove per-law repeated choice schema without losing authorized law names or choices.',
 'input':'Existing request-entry queries strings; bounded AND/OR/parentheses/quoted phrases. Adjacent words mean AND. Each word/quoted span preserves its ordered content tokens as a phrase. Separate queries are OR alternatives. Opt-in policy; old lists retain legacy OR.',
 'scope':'Local SQLite own-block fulltext MVP; no source or index rebuild. Reject unsupported grouped-query backends explicitly rather than silently flattening.',
 'consumer':'request_entry -> law_candidates -> unit_fulltext -> law_overview -> read-choice -> existing canonical navigation execution',
 'recovery_owner':'Existing request-entry/read-choice bounded_decision validates syntax before admission/execute and owns its existing single correction. No new model call or retry layer.',
 'budget':'Same physical model/tool/deadline/search-round budgets. Changed boolean grouping is a new query; equivalent normalized expressions are duplicates. Empty results stay missing, not proof of absence.',
 'state':'Durable JSON query plan, bound index/ACL/query cursors and presentation-local law references; originals, authority, judgment repair and failure history preserved.',
 'success_criteria':['Phrase and boolean fixtures retain intended hits and exclude single weak-token distractors', 'Legacy query tests pass', 'Same source/ACL and stale cursor checks pass; no raw query injection', 'All matched law names remain visible with matched expressions; one law action description; invalid references rejected before execution', 'Article cap20/more/progressive reads/ancestor scope and duplicate request contracts pass', 'Stored largest failing input can be losslessly law-projected with smaller assembled input, without original/evidence/state loss', 'Actual API uses exact candidate pins; zero external calls'],
 'failure_criteria':['Silent OR fallback', 'Omitted law/original or permission/state bypass', 'Extra unbounded retries or budget reset', 'Mutation of past experiment/index/MAIN'],
 'verification':'Small synthetic fulltext fixtures and native API sequentially; saved first-read payloads streamed one at a time for wire-size diagnostic. No 111-cell live run or claim of legal answer quality.',
 'resources':{'max_single_process_rss_gib':3,'minimum_mem_available_gib':3,'minimum_disk_free_gib':20,'maximum_new_artifacts_mib':200,'workers':1,'shared_immutable_data':True,'copy_source_or_indexes':False},
 'retrieval_evaluation':'Synthetic contracts only, no real legal corpus retrieval measurement or gold evaluation. Candidate-set assertions are deterministic code tests; no legal recall claim.',
 'model_calls':0,
}
save(ART/'implementation-plan.json',plan)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=plan['hypothesis']
d=m['design'];d.update(hypothesis=plan['hypothesis'],primary_metric='Query semantics, lossless menu projection and bounded native API contracts',success_criteria='; '.join(plan['success_criteria']),failure_criteria='; '.join(plan['failure_criteria']),criteria_frozen_before_run=True)
d['code_isolation'].update(mode='candidate_snapshot',reason=None)
d['criteria_record']={'path':str((ART/'implementation-plan.json').relative_to(ROOT)),'sha256':sha(ART/'implementation-plan.json')}
d['arms'][0].update(changes='Completed1055 code reference, including1052 overview and1054 step-state; no live baseline rerun',controls='Read-only immutable predecessor')
d['arms'][1].update(changes=plan['hypothesis'],controls='Same originals, data, permissions, budgets, judgment repair; no external calls')
m['runs'][0].update(arm_ids=['grouped-query'],selection_rule=plan['verification'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[]
m['dataset']={'name':'Synthetic grouped-query and lossless law-menu contracts; saved1054 input-size diagnostic','version':'v1','frozen_source':str((ART/'implementation-plan.json').relative_to(ROOT)),'sha256':sha(ART/'implementation-plan.json'),'legal_version_checked':False,'reference_version_checked':False,'note':plan['retrieval_evaluation']}
reason=plan['retrieval_evaluation']
m['retrieval_accounting']['not_applicable_reason']=reason
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
save(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
rows=read(SOURCE/'candidate.json')['files']
target=c.snapshot(ADR,'grouped-query-r1',[r['target_path'] for r in rows if r['upstream_state']=='present'],experiment_id=m['experiment_id'],arm_id='grouped-query',run_ids=['run-001'])
for r in rows:
    n=r['target_path'];p=target/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(SOURCE/'revisions/rev-001/snapshot'/n,p)
    if r['upstream_state']=='absent':c.register_file(target,n,upstream_state='absent')
c.refresh(target)
preserved=[ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',SOURCE/'candidate.json',ROOT/'04_EXPERIMENTS/ADR/ADR-1054-ontology-mvp-state-binding/실험/manifest.json']
save(ART/'preservation.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in preserved},'inherited_files':{r['target_path']:sha(SOURCE/'revisions/rev-001/snapshot'/r['target_path']) for r in rows},'disk_free_before':shutil.disk_usage(ROOT).free})
for name in ('stage_candidate.py','validate_candidate.py'):
    value=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1055'/name).read_text().replace('ADR-1055-judgment-link-delta-repair',ADR.name).replace('adr_1055/delta-repair-r1','adr_1056/grouped-query-r1')
    if name=='stage_candidate.py':value=value.replace("files.update({name:sha(root/name) for name in additions})","files.update({name:sha(root/name) for name in additions})\n            files['02_BACKEND/semantic_runtime/fulltext_query.py']=sha(root/'02_BACKEND/semantic_runtime/fulltext_query.py')\n            files['02_BACKEND/semantic_runtime/legal_agent/law_choice_projection.py']=sha(root/'02_BACKEND/semantic_runtime/legal_agent/law_choice_projection.py')")
    (Path(__file__).parent/name).write_text(value)
print(target)
