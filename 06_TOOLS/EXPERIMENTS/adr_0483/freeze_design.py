"""Freeze ADR-0483 inputs and design before the Qwen call."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0483-qwen-ambiguous-reference-probe'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0483/qwen-reference-review'
RUNNER = ROOT / '06_TOOLS/EXPERIMENTS/adr_0483/run_probe.py'
MODEL = 'qwen/qwen3.5-122b-a10b'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def main():
    target = ADR / 'artifacts/frozen-design.json'
    if target.exists():
        raise RuntimeError('Design already frozen')
    manifest = json.loads((ADR / '실험/manifest.json').read_text())
    candidate = json.loads((CAND / 'candidate.json').read_text())
    revision = candidate['revisions'][0]
    paths = [ADR / 'PLAN.md', ADR / 'fixture.json', CAND / 'candidate.json', RUNNER,
             ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
    design = {
        'schema_version': 'qwen-reference-probe-design-v1',
        'authorization': {
            'source': 'current_user_message',
            'text': '한번 임시로 실험해봐 llm은 qwen써보고',
            'scope': 'synthetic-only Qwen reference-resolution probe',
            'destination': 'https://openrouter.ai/api/v1',
            'model': MODEL,
            'fallback_allowed': False
        },
        'dataset': {'path': str((ADR / 'fixture.json').relative_to(ROOT)), 'sha256': sha(ADR / 'fixture.json'), 'cases': 12},
        'model': {'id': MODEL, 'class': 'product', 'temperature': 0, 'reasoning': 'off', 'calls': 1, 'max_output_tokens': 4096},
        'criteria': {'exact_cases_min': 10, 'unknown_false_resolutions_max': 0, 'outside_candidate_ids_max': 0,
                     'cost_usd_max': 0.10, 'latency_seconds_max': 120},
        'file_hashes': {str(p.relative_to(ROOT)): sha(p) for p in paths},
        'main_wiring': 'unchanged'
    }
    write(target, design)
    m = manifest
    m['lineage']['hypothesis_delta'] = 'Add one candidate-bound Qwen review after deterministic unresolved-reference detection; preserve UNKNOWN and forbid free target generation.'
    m['design'].update(
        hypothesis='Candidate-bound Qwen resolves at least 10/12 synthetic range/context references without resolving any of four intentionally unknowable cases.',
        primary_metric='Exact decision plus exact candidate ID set per case',
        success_criteria='Qwen >=10/12 exact; false resolution on 4 UNKNOWN cases=0; outside-candidate IDs=0; cost <=USD0.10; latency <=120s.',
        failure_criteria='Any success condition fails; preserve the failed output and do not promote.',
        criteria_frozen_before_run=True)
    m['design']['arms'][0].update(changes='Current unresolved behavior: preserve all selected hard cases as UNKNOWN.', controls='Same 12 synthetic cases, candidates, evidence and gold-free product input.')
    m['design']['arms'][1].update(changes='One candidate-bound Qwen product call chooses RESOLVED/MULTI_TARGET/UNKNOWN.', controls='Same cases; gold removed; candidate IDs closed; no repair, fallback or judge.')
    runner = RUNNER
    m['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[{
        'candidate_id': 'qwen-reference-review', 'experiment_id': m['experiment_id'], 'arm_id': 'qwen-review', 'run_ids': ['run-001'],
        'manifest_path': str((CAND / 'candidate.json').relative_to(ROOT)), 'manifest_sha256': sha(CAND / 'candidate.json'),
        'revision_id': revision['revision_id'], 'revision_sha256': revision['revision_sha256'],
        'runner_path': str(runner.relative_to(ROOT)), 'runner_sha256': sha(runner)}])
    m['runs'][0].update(selection_rule='Twelve hand-authored synthetic cases fixed before call: four ranges, four contextual/alias, four must-abstain.',
                        artifact_path='04_EXPERIMENTS/ADR/ADR-0483-qwen-ambiguous-reference-probe/artifacts/run-001/result.json')
    m['llm_policy']['llm_calls'] = [{'role': 'reference_resolution', 'class': 'product', 'model': MODEL,
                                     'arm_id': 'qwen-review', 'repeats': 1, 'temperature': 0, 'reasoning': 'off'}]
    m['llm_policy']['experiment_override'] = {
        'schema_version': 'user-authorized-experiment-models-v1', 'main_wiring': 'unchanged',
        'authorization': design['authorization'], 'allowed_models': [MODEL],
        'frozen_design_path': str(target.relative_to(ROOT)), 'frozen_design_sha256': sha(target)}
    m['dataset'].update(name='synthetic ambiguous legal references', version='v1',
                        frozen_source=str((ADR / 'fixture.json').relative_to(ROOT)), sha256=sha(ADR / 'fixture.json'),
                        legal_version_checked=True, reference_version_checked=True)
    m['retrieval_accounting'].update(not_applicable_reason='Closed candidate lists are fixture inputs; no corpus retrieval is executed or changed.')
    m['retrieval_accounting']['stage_ledger']['not_applicable_reason'] = 'Closed candidate lists are fixture inputs; no corpus retrieval is executed or changed.'
    write(ADR / '실험/manifest.json', m)
    print('ADR-0483 design frozen')

if __name__ == '__main__':
    main()

