"""Freeze public-topic questions and the unchanged selected service before calls."""
from pathlib import Path
import datetime
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0686-risk-cm-public-scope-local-probe'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


pointer = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation'] == 45
release = read(ROOT / pointer['manifest_path'])
assert sha(ROOT / pointer['manifest_path']) == pointer['release_manifest_sha256']
bindings = {path: sha(ROOT / path) for path in (
    'service.py', 'service/service.py', 'genos_diagnostics.py', 'genos_log_runner.py',
    '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json', pointer['manifest_path'],
    '02_BACKEND/lawrag/research/experiment_client.py', '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
    '06_TOOLS/EXPERIMENTS/adr_0686/run_probe.py')}
for path, expected in release['files'].items():
    absolute = ROOT / release['code_root'] / path
    assert sha(absolute) == expected, path
    bindings[str(absolute.relative_to(ROOT))] = expected
bindings[release['data_path'] + '/manifest.json'] = sha(ROOT / release['data_path'] / 'manifest.json')
assert bindings[release['data_path'] + '/manifest.json'] == release['data_manifest_sha256']
cases = [
    {'run_id': 'run-001', 'case_id': 'public-provision-comparison', 'topic_reference': 'RISK-CM-027',
     'question': '금융투자회사에 적용되는 공개 규정에서 대손충당금과 대손준비금은 어떻게 구분되는가?'},
    {'run_id': 'run-002', 'case_id': 'public-pf-downgrade', 'topic_reference': 'RISK-CM-029',
     'question': '부동산 PF 사업성 평가가 악화되는 경우 금융투자회사는 자산건전성 분류와 대손충당금 적립을 어떻게 연계해야 하는가?'},
    {'run_id': 'run-003', 'case_id': 'public-rp-bond-scope', 'topic_reference': 'RISK-CM-078',
     'question': '금융투자회사가 일반 고객과 원화 환매조건부매매(RP)를 하는 경우 대상 채권의 종류와 신용등급 요건은 무엇인가?'},
]
frozen = {
    'schema_version': 'risk-cm-public-topic-probe-v1',
    'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'cases': cases, 'runs': [case['run_id'] for case in cases], 'arms': ['baseline'],
    'question_origin': 'Synthetic general questions about public regulation topics. Original risk_cm wording, photos, annotations and reference evidence are excluded from product input.',
    'source_scope_route': 'Explicit approved public document_ids without external category prefix; ADR0685 category-route failure is recorded separately.',
    'question_private': False, 'product_gold': None, 'semantic_grading': False,
    'model': 'qwen/qwen3.8-27b', 'provider': 'Parasail', 'reasoning': {'effort': 'none'},
    'fallback': False, 'max_calls_per_run': 40, 'max_output_tokens': 6400,
    'pointer': pointer,
    'release': {k: v for k, v in release.items() if k not in ('files', 'integration')},
    'bindings': bindings,
    'state': 'Fresh isolated process and empty runtime for each public question; shared immutable source generation.',
    'hypothesis': 'Unchanged MAIN45 can produce nonempty source-cited answers to three general public regulation topics represented among the external-only risk_cm candidates.',
    'primary_metric': 'Nonempty final answer count with real provider receipts, source citations and verified release binding out of three requests.',
    'criteria': 'Answer emitted requires HTTP200 and nonempty answer.text; cited answer requires nonempty source_ids in answer.claims. Full and partial coverage, model/provider error and missing citations are reported separately. No legal correctness or risk_cm accuracy score is inferred.',
    'success_criteria': 'Three frozen requests are each attempted exactly once and audited; at least one nonempty cited answer is evidence that this unchanged public RAG path can emit an answer. All-three completion is reported separately.',
    'failure_criteria': 'No nonempty cited answers disproves the answer-emission hypothesis for this probe. Missing call receipts or binding drift blocks a completed audited-run claim.',
    'regression_limits': 'No production paths, active pointers, source generations, permissions or original question-bank markings may change.',
    'cost_latency_limits': 'Pinned service request budgets; at most 40 model calls per case, 6400 output tokens per call, no provider/model fallback or experiment-level retry.',
    'limitations': ['Three known topics, explicitly in-sample; no gold answers or independent semantic evaluator.',
                   'Synthetic scope-explicit questions differ from original risk_cm wording.',
                   'Local public Qwen3.8 is not a GENOS/internal-model performance test.',
                   'Selected source version is pinned; latest legal effect is not certified.'],
    'main_wiring': 'unchanged',
}
put(ADR / 'artifacts/design/frozen.json', frozen)
dataset = {'name': 'risk-cm-public-topics-synthetic', 'version': 'v2-explicit-public-scope', 'cases': cases,
           'product_gold': None, 'gold_coordinates': [], 'legal_quality_grading': False,
           'original_risk_cm_externally_transmitted': False, 'source_scope': 'public/synthetic'}
put(ADR / 'artifacts/design/dataset.json', dataset)
m = read(ADR / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = 'Observe unchanged MAIN45 answer emission on three public-topic synthetic questions with fresh state; no implementation comparison.'
m['design'].update({key: frozen[key] for key in ('hypothesis', 'primary_metric', 'success_criteria', 'failure_criteria')})
m['design']['criteria_frozen_before_run'] = True
m['design']['code_isolation']['reason'] = 'Read-only observation of the existing immutable selected MAIN45; no product implementation, prompt or retrieval candidate. Audit adapter preserves the selected wire request and supplies no alternate context.'
m['design']['arms'] = [{'id': 'baseline', 'role': 'baseline', 'derived_from': ['ADR-0681-experiment-v1/session'],
    'changes': 'None: selected MAIN45', 'controls': 'Frozen public/synthetic questions, approved public source scope, exact release/data/model binding; independent empty runtime.'}]
plan = [{'stage_id': 'catalogue', 'kind': 'source', 'parent_stage_ids': []},
        {'stage_id': 'recall', 'kind': 'retrieve', 'parent_stage_ids': ['catalogue']},
        {'stage_id': 'acquired', 'kind': 'select', 'parent_stage_ids': ['recall']},
        {'stage_id': 'presented', 'kind': 'present', 'parent_stage_ids': ['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm'] = {'baseline': plan}
m['design']['frozen_design'] = {'path': str((ADR / 'artifacts/design/frozen.json').relative_to(ROOT)), 'sha256': sha(ADR / 'artifacts/design/frozen.json')}
m['runs'] = [{'id': case['run_id'], 'purpose': 'primary', 'parent_run_id': None,
    'arm_ids': ['baseline'], 'selection_rule': 'Exactly one pre-frozen public topic per independent process, all three specified before any call.',
    'status': 'planned', 'artifact_path': str((ADR / 'artifacts' / case['run_id'] / 'result.json').relative_to(ROOT)),
    'sha256': 'PENDING'} for case in cases]
m['llm_policy']['llm_calls'] = [{'role': 'product', 'class': 'product', 'model': frozen['model'],
    'repeats': 1, 'temperature': 0, 'max_calls_per_run': 40, 'max_output_tokens': 6400}]
m['dataset'].update(name=dataset['name'], version='v1', frozen_source=str((ADR / 'artifacts/design/dataset.json').relative_to(ROOT)),
    sha256=sha(ADR / 'artifacts/design/dataset.json'), legal_version_checked=False, reference_version_checked=False)
m['retrieval_accounting']['not_applicable_reason'] = 'Unchanged retrieval; exact executed sets measured without legal gold.'
m['retrieval_accounting']['stage_ledger'].update(mode='measured', summary_run_id='run-001',
    artifact_path=str((ADR / 'artifacts/retrieval-ledger.json.gz').relative_to(ROOT)), sha256='PENDING', not_applicable_reason=None)
put(ADR / '실험/manifest.json', m)
print('Frozen three public-topic synthetic requests against unchanged MAIN45; no original internal input or product changes.')
