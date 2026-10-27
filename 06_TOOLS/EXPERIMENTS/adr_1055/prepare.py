"""Record the repair contract before editing an isolated continuation."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-1055-judgment-link-delta-repair'
ART = ADR/'artifacts'
SOURCE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1054/step-state-r1'
def read(p): return json.loads(p.read_text())
def save(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

plan = {
    'before_implementation': True,
    'scope': 'Modern ASSESS retained-judgment link corrections only; existing full repair for other failures',
    'failure_class': 'Typed field-consistency errors with exact judgment IDs and paths',
    'owner': 'completion_execution existing assessment DecisionJournal; gateway same-error repair remains disabled',
    'input': 'Original request, affected judgment rows, compatible existing claims, their exact current originals and user facts only; no full rejected assessment or unrelated history',
    'patch': 'Only affected final-review judgment rows. Model explicitly chooses USE/CONDITIONAL with actual shared-source claims or UNRESOLVED/NOT_USED with reason. No core claim, gap, need, conflict, original, permission or revision edits.',
    'validation': 'Independently validate core claims first; bind patch to original proposal/context/evidence hashes; strict target-ID set; merge into unchanged original; revalidate full schema/core/review/source contracts before commit',
    'budget': 'Replace existing one correction, never add a second repair; same physical call/tool/deadline budget and resume ledger; no output cap',
    'failure': 'Repeated link-consistency failure may retain only independently verified core claims as LIMITED_ANSWER with all prior judgments/needs/conflicts and explicit incomplete review. Shape/evidence/ACL/hash/state failures remain blocked; no closure or adoption inferred.',
    'checks': ['normal unchanged', 'missing/shared-source link repair', 'only target rows mutable', 'no compatible claim', 'all independent link errors batched', 'repeat failure bounded/incomplete visible', 'other schema failure unchanged', 'bad original/claim/ACL/hash/state blocked', 'resume/replay/unknown outcome/budget retained', 'actual API publication and reuse using exact pins'],
    'model_calls': 0,
    'quality_claim': 'Synthetic contracts only; no live-model success rate or latency conclusion',
    'preservation': 'ADR1054 service/frozen inputs/results and MAIN unchanged; no concurrent full-corpus process',
}
save(ART/'implementation-plan.json', plan)
m = read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta'] = 'Repair only broken final judgment links without full assessment regeneration; independently verified originals/claims and durable limits remain mandatory.'
d=m['design']; d.update(hypothesis=m['lineage']['hypothesis_delta'], primary_metric='Synthetic partial repair, unchanged core/evidence, bounded failure and API publication contracts',
    success_criteria='All scoped contracts pass on frozen code; patch contains only affected rows and relevant originals; no extra correction; incomplete review visible; zero external model calls',
    failure_criteria='Unrelated field mutation, evidence/ACL/revision bypass, hidden unresolved state, repeated correction, MAIN or running1054 mutation', criteria_frozen_before_run=True)
d['code_isolation'].update(mode='candidate_snapshot', reason=None)
d['criteria_record']={'path':str((ART/'implementation-plan.json').relative_to(ROOT)), 'sha256':sha(ART/'implementation-plan.json')}
d['arms'][0].update(changes='Completed1052 lineage reference; frozen1054 implementation dependency, not a completed quality parent',controls='No paired live quality evaluation')
d['arms'][1].update(changes='Typed judgment-link errors and scoped delta correction with full revalidation',controls='Same sources, claims, scope, state and total budgets')
m['runs'][0].update(arm_ids=['delta-repair'],selection_rule='Sequential small synthetic unit and native API fixtures; no full corpus or live calls',artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[]
m['dataset']={'name':'Synthetic judgment-link recovery contracts','version':'v1','frozen_source':str((ART/'implementation-plan.json').relative_to(ROOT)),'sha256':sha(ART/'implementation-plan.json'),'legal_version_checked':False,'reference_version_checked':False,'note':'No legal gold or live corpus evaluation'}
reason='No retrieval comparison; synthetic fixtures only test existing native API wiring and source preservation.'
m['retrieval_accounting']['not_applicable_reason']=reason
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
save(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as c
rows=read(SOURCE/'candidate.json')['files']
target=c.snapshot(ADR,'delta-repair-r1',[r['target_path'] for r in rows if r['upstream_state']=='present'],experiment_id=m['experiment_id'],arm_id='delta-repair',run_ids=['run-001'])
for r in rows:
    n=r['target_path']; p=target/'snapshot'/n
    p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(SOURCE/'revisions/rev-001/snapshot'/n,p)
    if r['upstream_state']=='absent':c.register_file(target,n,upstream_state='absent')
c.refresh(target)
save(ART/'preservation.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in [
    ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json', ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
    ROOT/'02_BACKEND/semantic_runtime/legal_agent/completion_execution.py',ROOT/'02_BACKEND/semantic_runtime/legal_agent/read_judgment_final.py',
    SOURCE/'candidate.json',ROOT/'04_EXPERIMENTS/ADR/ADR-1054-ontology-mvp-state-binding/artifacts/design-freeze.json']},
    'inherited_files':{r['target_path']:sha(SOURCE/'revisions/rev-001/snapshot'/r['target_path']) for r in rows}})
for name in ['validate_candidate.py','stage_candidate.py']:
    s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1054'/name).read_text().replace('ADR-1054-ontology-mvp-state-binding',ADR.name).replace('adr_1054/step-state-r1','adr_1055/delta-repair-r1')
    if name=='stage_candidate.py':s=s.replace("'step_state.py',", "'read_judgment_repair.py', 'step_state.py',")
    (Path(__file__).parent/name).write_text(s)
print(target)
