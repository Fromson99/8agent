"""Freeze prospective integration/generation checks before candidate implementation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0571-nightly-concept-route-system'
C = R/'02_BACKEND/lawrag/research/candidates/adr_0571/integrated'
P = R/'02_BACKEND/lawrag/research/candidates/adr_0569/combined/revisions/rev-001/snapshot'
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def tool(*args): subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),*args],cwd=R,check=True)

def main():
    m=json.loads((A/'실험/manifest.json').read_text())
    criteria={
        'contract':'full HTTP ask -> native session -> source bundle -> publication -> durable journal; no lost required original, no extra online classifier',
        'generation':'native journals become source-bound episodes; offline model consolidates action reasons to concepts and GUIDE relations; no answer-as-truth; no exclusion from mere non-selection',
        'scope':'verified EXCLUDES applies before SQL/READ; unknown/mixed/policy/data drift keeps unrestricted authorised scope; generic compile API supports list/traverse/read as well as search',
        'night':'Asia/Seoul 00:00 inclusive to06:00 exclusive; bounded slice, lock, cursor/idempotence, failures persist and resume; JSONL events + SQLite + readable status',
        'acceptance':'all deterministic contract checks; four new paired synthetic full-API cases preserve source/citation and complete; generated concepts are supported by original selection reasons',
        'limitations':'four synthetic cases and one generation run; engineering gate, no legal quality/GENOS/speed certification; generated GUIDE is experience, EXCLUDES requires explicit reviewed evidence',
    }
    m['design'].update(hypothesis='Log-derived concepts are consumable by existing request planning without a classifier; guarded complete-pool selection removes a redundant call.',
        primary_metric='source/citation preservation and end-to-end contracts; successful offline generation and bounded resumable nightly builds',
        success_criteria=criteria, failure_criteria=['original loss','unsupported exclusion','privacy breach','work outside window','non-idempotent builds'],criteria_frozen_before_run=True)
    m['dataset'].update(name='Four unseen synthetic approval/delegation questions plus read-only native-journal intake',version='nightly-contract-v1',classification='SYNTHETIC',legal_version_checked=True,reference_version_checked=True)
    cases=[{'id':f'H{i+1:02}','question':q} for i,q in enumerate([
        '이사회 승인을 받아야 하는 원칙과 위임 예외를 설명해 주세요.',
        '적법하게 권한을 위임한 경우에도 이사회 승인이 필요한지 확인해 주세요.',
        '위임하지 않은 경우 승인 원칙은 무엇인가요?',
        '이사회 승인 규정과 그 예외에 관한 원문을 함께 확인해 주세요.'
    ])]
    write(A/'artifacts/design/cases.json',cases)
    write(A/'artifacts/design/criteria.json',criteria)
    m['dataset'].update(frozen_source=str((A/'artifacts/design/cases.json').relative_to(R)),sha256=sha(A/'artifacts/design/cases.json'))
    m['llm_policy']['llm_calls']=[{'role':'planning/selection/compose/concept-generation','class':'product','model':'google/gemma-4-31b-it','repeats':1}]
    m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
    m['runs'][0].update(case_ids=[c['id'] for c in cases],selection_rule='All four prospectively frozen unseen synthetic cases, paired baseline/integrated order rotates; one generation batch; no post-hoc repairs',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
    parent=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0569-compact-plan-smallpool/실험/manifest.json').read_text())
    stages=parent['design']['retrieval_stage_plan']['stages_by_arm']['combined']
    m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ['baseline','integrated']}
    m['retrieval_accounting'].update(changed=True,corpus_total=3,not_applicable_reason=None,
        stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((A/'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)),'sha256':'PENDING','not_applicable_reason':None})
    write(A/'실험/manifest.json',m)
    paths=['02_BACKEND/semantic_runtime/legal_agent/'+x for x in ['source_query_planning.py','source_recall.py','source_recall_global.py','source_selection.py','bounded_source_session.py']]
    paths+=['02_BACKEND/semantic_runtime/fulltext.py','02_BACKEND/semantic_runtime/app.py','06_TOOLS/pipeline.py']
    args=['adr_candidate.py','snapshot','--adr',str(A.relative_to(R)),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
    for p in paths: args+=['--source',p]
    tool(*args)
    for p in paths:
        if (P/p).exists(): shutil.copyfile(P/p,C/'snapshot'/p)
    write(A/'artifacts/design/upstream.json',{'active_pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'files':{p:sha(R/p) for p in paths}})
    print('prospective design recorded; inherited compact/complete-pool candidate copied')

if __name__=='__main__': main()
