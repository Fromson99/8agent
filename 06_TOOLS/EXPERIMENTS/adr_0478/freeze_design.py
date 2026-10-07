"""Freeze explicit user authority, inputs and criteria before any paid call."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0478-action-feedback-qwen-retest'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0478/qwen-retest'


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
    auth = {'source': 'user_message', 'text': 'qwen재검증만 일단 해봐. 앞서 승인한 공개 원문만 사용하는 CM003 단독 재검증; 영구 전송 정책 변경 없음.',
            'scope': 'ADR0478 CM003 public-source Qwen product probe only; no evaluator, private unrelated data or MAIN change.', 'fallback_allowed': False}
    paths = [ADR / 'PLAN.md', ADR / 'fixture.json', CAND / 'candidate.json', generation / 'manifest.json',
             ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', ROOT / '00_SYSTEM/PIPELINE.json',
             ROOT / '06_TOOLS/EXPERIMENTS/adr_0478/run_autonomy.py']
    stages = [{'stage_id': 'discovered', 'kind': 'source', 'parent_stage_ids': []}]
    for name, parent in [('read', 'discovered'), ('presented', 'read'), ('selected', 'presented'), ('answer', 'selected')]:
        stages.append({'stage_id': name, 'kind': 'present' if name == 'answer' else 'select', 'parent_stage_ids': [parent]})
    design = {'configs': {'qwen-retest': {'model': model, 'thinking_level': 'off'}}, 'scope_authorization': auth,
              'export_authorization': {'authorized': True, 'model': model, 'destination': 'https://openrouter.ai/api/v1',
                   'source': 'explicit_current_user_message', 'scope_document_ids': sorted(fixture['public_scope_document_ids']),
                   'source_store_sha256': source['store_sha256'], 'immutable_export_flags_changed': False},
              'file_hashes': {str(p.relative_to(ROOT)): sha(p) for p in paths},
              'stage_plan': {'baseline': stages, 'qwen-retest': stages},
              'success_criteria': 'Autonomous controller reaches FINAL with cited reviewed claims; decisive source passage delivery/selection/retention audited post-run; independent legal accuracy not scored.',
              'limits': {'model_calls': 14, 'tool_actions': 56, 'controller_seconds': 300, 'context_chars': 60000, 'output_tokens': 2800},
              'repetitions': 1, 'judge_calls': 0, 'baseline_execution': 'not_executed_parent_structural_reference_only'}
    write(target, design)
    m = manifest
    m['lineage']['hypothesis_delta'] = 'Retest unchanged ADR0477 rev002 action-feedback with explicitly authorized Qwen; no post-outcome code changes or repeat.'
    m['design'].update(hypothesis=design['success_criteria'], primary_metric='Autonomous completion with cited source retention; not legal accuracy',
                       success_criteria=design['success_criteria'], failure_criteria='No valid final cited claims, missing source evidence, contract error or exhausted budget; preserve all failures.', criteria_frozen_before_run=True)
    m['design']['arms'][0].update(changes='Parent scripted structural reference only; no baseline retrieval/model run.', controls='Parent frozen implementation/source')
    m['design']['arms'][1].update(changes='Actual Qwen instead of scripted replies; explicit source export binding.', controls='Same source-first controller, question, scope and budgets')
    m['design']['retrieval_stage_plan']['stages_by_arm'] = design['stage_plan']
    candidate = json.loads((CAND / 'candidate.json').read_text())
    revision = candidate['revisions'][0]
    runner = ROOT / '06_TOOLS/EXPERIMENTS/adr_0478/run_autonomy.py'
    m['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[{
        'candidate_id': 'qwen-retest', 'experiment_id': m['experiment_id'], 'arm_id': 'qwen-retest', 'run_ids': ['run-001'],
        'manifest_path': str((CAND / 'candidate.json').relative_to(ROOT)), 'manifest_sha256': sha(CAND / 'candidate.json'),
        'revision_id': 'rev-001', 'revision_sha256': revision['revision_sha256'],
        'runner_path': str(runner.relative_to(ROOT)), 'runner_sha256': sha(runner)}])
    m['runs'][0]['selection_rule'] = 'User-selected CM003; one live autonomous run, no scripted card selection or product gold.'
    m['llm_policy']['llm_calls'] = [{'role': 'investigate_compose_review', 'class': 'product', 'model': model,
                                   'thinking_level': 'off', 'arm_id': 'qwen-retest', 'repeats': 1, 'temperature': 0}]
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

