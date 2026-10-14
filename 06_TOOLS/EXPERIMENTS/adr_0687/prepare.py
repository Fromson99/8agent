"""Freeze an offline source audit of recorded answers; no product/model call."""
from pathlib import Path
import datetime
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0687-risk-cm-recorded-answer-source-review'
PARENT = ROOT / '04_EXPERIMENTS/ADR/ADR-0686-risk-cm-public-scope-local-probe'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


source = read(PARENT / '실험/manifest.json')
assert source['reservation']['status'] == 'completed' and source['results']['status'] == 'complete'
previous = read(PARENT / 'artifacts/design/frozen.json')
paths = [PARENT / '실험/manifest.json', PARENT / 'artifacts/summary.json',
         PARENT / 'artifacts/design/frozen.json', PARENT / 'artifacts/design/dataset.json',
         ROOT / previous['release']['data_path'] / 'manifest.json',
         ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',
         ROOT / '01_DATA/GOLDEN/risk_cm/v1/questions.json',
         ROOT / '01_DATA/GOLDEN/risk_cm/v1/dataset.json',
         ROOT / '01_DATA/GOLDEN/registry-v2-risk_cm.json']
for run in source['runs']:
    path = ROOT / run['artifact_path']
    assert sha(path) == run['sha256']
    paths.append(path)
frozen = {
    'schema_version': 'recorded-answer-source-audit-v1',
    'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'parent': 'ADR-0686-experiment-v1/baseline',
    'inputs': {str(path.relative_to(ROOT)): sha(path) for path in paths},
    'cases': previous['cases'], 'run_id': 'run-001', 'arm': 'baseline',
    'product_generation': previous['release'],
    'hypothesis': 'Source citations and runtime COVERED are insufficient to establish complete correctness of these recorded public-topic answers.',
    'primary_metric': 'Per-case material claim support, governing actor, condition/exception fidelity and essential issue completeness; complete correctness count is separate from response emission.',
    'success_criteria': 'All three recorded answers are reviewed against immutable originals and accessible primary official sources; exact reason, version limitation and source coordinates support each verdict.',
    'failure_criteria': 'Unverified source/version or unresolved applicability remains unverified; an answer cannot pass merely because it cites a source or was labeled COVERED.',
    'verdict_rules': {
        'correct': 'All material claims match applicable sources and essential question requirements, with no material omissions.',
        'partial': 'Supported relevant content remains, but essential scope, explanation, source detail or requested categories are missing; no material contradiction of supplied source is identified.',
        'incorrect': 'At least one material statement contradicts applicable source, applies the wrong actor as if general, loses a condition/exception, or supplies an unsupported number.',
        'unverified': 'Source availability, effectiveness version or ambiguity prevents a justified verdict.'},
    'essential_issues': {
        'public-provision-comparison': ['Explain the conceptual/accounting distinction and statutory shortfall reserve principle.', 'Distinguish general financial-investment rules from comprehensive financial-investment-business special rules and validate every rate against its actual scope.'],
        'public-pf-downgrade': ['Explain business assessment -> asset soundness -> provisioning for assets actually subject to provisioning.', 'Do not turn any downgrade into automatic provisioning of every exposure.', 'Validate attachment references and distinguish a selected-context gap from corpus absence.'],
        'public-rp-bond-scope': ['Provide the eligible security categories and conditions together.', 'Preserve the alternatives in Article 5-18(2); do not make the rating of one alternative a universal requirement.', 'Apply automatic-investment special requirements within their exact legal scope.']},
    'review_method': 'Codex source-based offline review; no product request, external judge model or statistical generalization claim.',
    'version_policy': 'First judge consistency against the exact generation used for inference. Independently check accessible official published text; current-version uncertainties are reported separately and not silently applied retroactively.',
    'product_inputs_mutated': False, 'gold_approved': False, 'decision_eligible': False,
    'original_risk_cm_transmitted': False, 'main_wiring': 'unchanged',
    'limits': 'Known three-case in-sample review; no judge calibration, quality certification, MAIN promotion, GENOS access or answer-bank approval.',
}
put(ADR / 'artifacts/design/frozen.json', frozen)
dataset = {'name': 'risk-cm-public-topic-recorded-source-review', 'version': 'v1',
           'cases': previous['cases'], 'recorded_inputs': frozen['inputs'],
           'gold_status': 'offline-review-candidates-only'}
put(ADR / 'artifacts/design/inputs.json', dataset)
m = read(ADR / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = 'Evaluate recorded completed public answers without any new product/model invocation; prior answer-emission metrics remain unchanged.'
m['design'].update({key: frozen[key] for key in ('hypothesis', 'primary_metric', 'success_criteria', 'failure_criteria')})
m['design']['criteria_frozen_before_run'] = True
m['design']['code_isolation']['reason'] = 'Offline source review of immutable recorded answers only; no product implementation, prompt, context or retrieval candidate. Product outputs and prior experiment metrics are unchanged.'
m['design']['arms'] = [{'id': 'baseline', 'role': 'baseline', 'derived_from': [frozen['parent']],
    'changes': 'No product change; recorded output is reviewed offline against primary sources.',
    'controls': 'All three original recorded outputs and exact prior release/data/query hashes; identical pre-frozen verdict rubric.'}]
m['design']['frozen_design'] = {'path': str((ADR / 'artifacts/design/frozen.json').relative_to(ROOT)), 'sha256': sha(ADR / 'artifacts/design/frozen.json')}
m['design']['retrieval_stage_plan'] = source['design']['retrieval_stage_plan']
m['runs'] = [{'id': 'run-001', 'purpose': 'primary', 'parent_run_id': None, 'arm_ids': ['baseline'],
    'selection_rule': 'All three recorded ADR0686 public synthetic cases, without cherry-picking or rerunning product inference.',
    'status': 'planned', 'artifact_path': str((ADR / 'artifacts/run-001/review.json').relative_to(ROOT)), 'sha256': 'PENDING'}]
m['llm_policy']['llm_calls'] = []
m['dataset'].update(name=dataset['name'], version='v1', frozen_source=str((ADR / 'artifacts/design/inputs.json').relative_to(ROOT)),
    sha256=sha(ADR / 'artifacts/design/inputs.json'), legal_version_checked=False, reference_version_checked=False)
m['retrieval_accounting'] = source['retrieval_accounting']
m['retrieval_accounting']['changed'] = False
m['retrieval_accounting']['stage_ledger'] = {**source['retrieval_accounting']['stage_ledger'], 'mode': 'inherited'}
m['retrieval_accounting']['not_applicable_reason'] = 'Offline source audit performs no new product retrieval; original exact provider-context and stage ledger are inherited, not regraded for recall.'
put(ADR / '실험/manifest.json', m)
print('Frozen three recorded outputs and offline source-review rubric; model calls 0.')
