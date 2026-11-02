from common import *
active = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(ROOT / active['manifest_path'])
criteria = {
    'hypothesis': 'Exact text references, server-owned condition results and explicit unresolved-gap references remove copying obligations without cutting text or changing legal opinions.',
    'success': [
        'All projected text restores exactly, including long suffix exceptions, Unicode and whitespace; no semantic summary or slicing.',
        'Current facts and scenario authority are explicit; original request scope, evidence and history remain available.',
        'Condition results are host-owned on the wire and exactly checked after expansion; foreign values are rejected.',
        'Missing material gaps can be linked only under existing unambiguous request mapping; full gap reason and original proposal remain unchanged.',
        'Malformed/ambiguous/cross-issue/foreign-evidence proposals still fail; incomplete review stays incomplete.',
        'Native API, saved receipt, duplicate request and failure display use the same frozen code and engine pins.',
    ],
    'failure': ['Text truncation, inferred legal claims, suppressed gaps or weaker ACL/hash/revision checks', 'Extra physical model calls or changes to retry/UNKNOWN policy'],
    'scope': 'First implementation of the approved plan: authoritative input, host constants, lossless gap reference repair and precise diagnostics. A full semantic review-contract redesign and replacement of numeric prose checks require a separate versioned change.',
    'model_calls': 0, 'oracle_calls': 0, 'quality_certified': False,
}
put(DES / 'criteria.json', criteria)
put(DES / 'baseline.json', {'active': active, 'active_sha256': sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'), 'release': release})
m = read(ADR / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Lossless contract and source-safe recovery', success_criteria=criteria['success'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True, criteria_freeze_evidence=bind(DES / 'criteria.json'))
m['design']['arms'][0].update(changes='Completed ADR1281 historical diagnosis', controls='Historical only, no causal model comparison')
m['design']['arms'][1].update(changes=criteria['scope'], controls='Same sources, authority, canonical meaning, retry and publication checks')
m['runs'][0].update(arm_ids=['verified'], artifact_path=str((ART / 'contracts/result.json').relative_to(ROOT)), selection_rule='Deterministic preservation and adversarial contract tests, native API fixtures; no live model')
m['dataset'].update(name='Lossless input and gap reference contracts', version='20261102-v1', frozen_source=str((DES / 'criteria.json').relative_to(ROOT)), sha256=sha(DES / 'criteria.json'), legal_version_checked=False, reference_version_checked=False)
m['llm_policy']['llm_calls'] = []
reason = 'Contract-only change; no retrieval selection or legal-quality comparison'
m['retrieval_accounting']['not_applicable_reason'] = reason
m['retrieval_accounting']['stage_ledger']['not_applicable_reason'] = reason
put(ADR / '실험/manifest.json', m)
sources = set(release['files'])
for p in (ROOT / '02_BACKEND/ENGINES').rglob('*.json'):
    sources.add(str(p.relative_to(ROOT))); sources.update(read(p).get('files', {}))
sources.update(['02_BACKEND/lawrag/research/experiment_client.py', '02_BACKEND/lawrag/research/openrouter_legal_adapter.py', '02_BACKEND/lawrag/core/request_deadline.py'])
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac
c = ac.snapshot(ADR, 'verified', sorted(sources), experiment_id=m['experiment_id'], arm_id='verified', run_ids=['run-001'])
put(DES / 'candidate-path.json', {'candidate': str(c.relative_to(ROOT)), 'snapshot': str((c / 'snapshot').relative_to(ROOT))})
put(DES / 'working-before.json', {n: sha(ROOT / n) for n in sorted(sources)})
print(c / 'snapshot', len(sources))
