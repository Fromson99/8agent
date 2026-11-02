from common import *
active = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(ROOT / active['manifest_path'])
criteria = {'hypothesis': 'Bind deterministic scenario comparisons and known missing inputs directly to final presentation without model restatement or invented legal effects.', 'success': ['New scenario contexts carry verified typed field/condition metadata; old receipts remain readable.', 'Host renders all current inputs, changed values and condition statuses, including review-incomplete replies; generated claims/evidence remain separate.', 'New wire requests neither application value/link rewriting nor comparison prose; legacy receipts keep original validation.', 'Explicit computed_gap_ref expands only an offered missing FACT input at the same array position; arbitrary reasons remain byte-exact.', 'No truncation, free-prose repair, inferred permission/exception or automatic ontology approval.', 'Invalid source/context/receipt/ref is rejected; old-amount misuse checks remain and their false-positive limit is documented.', 'Native API storage/publication/repair/duplicate and receipt-tamper guards verified, exact integrated working delta.'], 'failure': ['Source/prose loss', 'Invented facts or legal conclusions', 'Weakening ACL/source/hash/state/budget checks', 'Claiming model-quality improvement without actual model evidence'], 'recovery': {'owner': 'Existing ASSESS first+one repair', 'automatic': 'Only explicitly selected server missing-input references expanded; computed display derived from bound context', 'final': 'Preserve rejected model output and source-only incomplete status; display calculation does not certify a claim'}, 'scope': 'Server calculation display and explicit computed missing-input references; no automatic effect plan or semantic prose rewrite', 'model_calls': 0, 'oracle_calls': 0, 'quality_certified': False}
put(DES / 'criteria.json', criteria)
put(DES / 'baseline.json', {'active': active, 'active_sha256': sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'), 'release': release})
m = read(ADR / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Lossless contract and source-safe recovery', success_criteria=criteria['success'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True, criteria_freeze_evidence=bind(DES / 'criteria.json'))
m['design']['arms'][0].update(changes='Selected MAIN133 and preserved ADR1286 actual failures', controls='Historical only, no causal model comparison')
m['design']['arms'][1].update(changes=criteria['scope'], controls='Same sources, authority, canonical meaning, retry and publication checks')
m['runs'][0].update(arm_ids=['verified'], artifact_path=str((ART / 'contracts/result.json').relative_to(ROOT)), selection_rule='Deterministic preservation and adversarial contract tests, native API fixtures; no live model')
m['dataset'].update(name='Scenario server computation and gap-reference contracts', version='20261103-v1', frozen_source=str((DES / 'criteria.json').relative_to(ROOT)), sha256=sha(DES / 'criteria.json'), legal_version_checked=False, reference_version_checked=False)
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
