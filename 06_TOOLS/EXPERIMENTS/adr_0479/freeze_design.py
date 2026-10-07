"""Freeze explicit user authority, inputs and criteria before any paid call."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0479-bounded-linked-evidence'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0479/linked-context'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    target = ADR / 'artifacts/frozen-design.json'
    if target.exists():
        raise RuntimeError('Design is already frozen')
    manifest = json.loads((ADR / '실험/manifest.json').read_text())
    fixture = json.loads((ADR / 'fixture.json').read_text())
    generation = ROOT / fixture['generation']
    source = json.loads((generation / 'manifest.json').read_text())
    model = 'qwen/qwen3.5-122b-a10b'
    auth = {'source': 'user_message', 'text': '한번 진행해봐 — 제한된 연결 원문 보존 구현과 CM003 Qwen 1회 검증. 앞서 승인한 공개 원문만 사용; 영구 전송 정책 변경 없음.',
            'scope': 'ADR0479 CM003 public-source Qwen product probe only; no evaluator, private unrelated data or MAIN change.', 'fallback_allowed': False}
    paths = [ADR / 'PLAN.md', ADR / 'fixture.json', CAND / 'candidate.json', generation / 'manifest.json',
             ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', ROOT / '00_SYSTEM/PIPELINE.json',
             ROOT / '06_TOOLS/EXPERIMENTS/adr_0479/run_autonomy.py',
             ROOT / '05_TESTS/CONTRACTS/test_source_first_linked_context.py',
             ADR / 'artifacts/contracts-002/result.json']
    stages = [{'stage_id': 'discovered', 'kind': 'source', 'parent_stage_ids': []}]
    for name, parent in [('read', 'discovered'), ('presented', 'read'), ('packed', 'presented'), ('answer', 'packed')]:
        stages.append({'stage_id': name, 'kind': 'present' if name == 'answer' else 'select', 'parent_stage_ids': [parent]})
    design = {'configs': {'linked-context': {'model': model, 'thinking_level': 'off'}}, 'scope_authorization': auth,
              'export_authorization': {'authorized': True, 'model': model, 'destination': 'https://openrouter.ai/api/v1',
                   'source': 'explicit_current_user_message', 'scope_document_ids': sorted(fixture['public_scope_document_ids']),
                   'source_store_sha256': source['store_sha256'], 'immutable_export_flags_changed': False},
              'file_hashes': {str(p.relative_to(ROOT)): sha(p) for p in paths},
              'stage_plan': {'baseline': stages, 'linked-context': stages},
              'success_criteria': 'Already-read direct marked-reference evidence retained in compose/review within two source roots and 3000 extra text characters; no automatic selection or extra model phase. CM003 reference agreement inspected post-run, not independent legal accuracy.',
              'limits': {'model_calls': 14, 'tool_actions': 56, 'controller_seconds': 300, 'context_chars': 60000, 'output_tokens': 2800, 'extra_sources': 2, 'extra_text_chars': 3000},
              'repetitions': 1, 'judge_calls': 0, 'baseline_execution': 'not_executed_parent_structural_reference_only'}
    write(target, design)
    m = manifest
    m['lineage']['hypothesis_delta'] = 'Retain bounded directly linked already-read evidence with server-owned context, without changing model selection or adding review phases. One Qwen run, no post-outcome code changes/repeat.'
    m['design'].update(hypothesis=design['success_criteria'], primary_metric='Bounded supplemental retention and explicit model citation; not legal accuracy',
                       success_criteria=design['success_criteria'], failure_criteria='No valid final cited claims, missing source evidence, contract error or exhausted budget; preserve all failures.', criteria_frozen_before_run=True)
    m['design']['arms'][0].update(changes='Parent scripted structural reference only; no baseline retrieval/model run.', controls='Parent frozen implementation/source')
    m['design']['arms'][1].update(changes='Bounded linked READ context instead of selected-only compose/review context; explicit source export binding.', controls='Same Qwen model, question, public source scope, navigation and budgets; historical baseline only')
    m['design']['retrieval_stage_plan']['stages_by_arm'] = design['stage_plan']
    candidate = json.loads((CAND / 'candidate.json').read_text())
    revision = candidate['revisions'][0]
    runner = ROOT / '06_TOOLS/EXPERIMENTS/adr_0479/run_autonomy.py'
    m['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[{
        'candidate_id': 'linked-context', 'experiment_id': m['experiment_id'], 'arm_id': 'linked-context', 'run_ids': ['run-001'],
        'manifest_path': str((CAND / 'candidate.json').relative_to(ROOT)), 'manifest_sha256': sha(CAND / 'candidate.json'),
        'revision_id': 'rev-001', 'revision_sha256': revision['revision_sha256'],
        'runner_path': str(runner.relative_to(ROOT)), 'runner_sha256': sha(runner)}])
    m['runs'][0]['selection_rule'] = 'User-selected CM003; one live autonomous run, no scripted card selection or product gold.'
    m['llm_policy']['llm_calls'] = [{'role': 'investigate_compose_review', 'class': 'product', 'model': model,
                                   'thinking_level': 'off', 'arm_id': 'linked-context', 'repeats': 1, 'temperature': 0}]
    m['llm_policy']['experiment_override'] = {'schema_version': 'user-authorized-experiment-models-v1', 'main_wiring': 'unchanged',
                    'authorization': auth, 'allowed_models': [model], 'frozen_design_path': str(target.relative_to(ROOT)), 'frozen_design_sha256': sha(target)}
    m['dataset'].update(name='CM003 public-source autonomous probe', version='parent-0475-fixture',
                        frozen_source=str((ADR / 'fixture.json').relative_to(ROOT)), sha256=sha(ADR / 'fixture.json'),
                        legal_version_checked=False, reference_version_checked=False)
    m['retrieval_accounting'].update(changed=True, not_applicable_reason=None)
    m['retrieval_accounting']['stage_ledger'].update(mode='measured', not_applicable_reason=None)
    write(ADR / '실험/manifest.json', m)
    print('Design and input hashes frozen before first model call')


if __name__ == '__main__':
    main()


