from common import *
active = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(ROOT / active['manifest_path'])
criteria = {
 'hypothesis':'Explicit typed current/comparison references and one shared claim/evidence link reduce duplicate authoring while preserving independent semantic review.',
 'success':[
  'Same claim/evidence link can be reused across judgments, needs, scope reviews and requirements; every original validator still runs.',
  'Shared link expansion is deterministic, rejects duplicate/unknown/unused links, preserves reasons, exclusions, open gaps, and exact evidence scopes.',
  'Typed current application cannot select historical values; before/after comparison is explicit and keeps the current binding.',
  '245만 원 and 2,450,000원 preserve the same exact KRW value; signs and magnitudes use Decimal, no rounding or slicing.',
  'Current numeric condition display is rendered from bound server values; UNKNOWN never implies legal permission.',
  'Legacy saved receipts keep legacy readers; new receipts bind version, schema and state and revalidate on publication/cache.',
  'Native API -> saved assessment -> final rendering -> duplicate request uses the frozen code; originals and baseline case remain unchanged.'
 ],
 'failure':['Truncation, inferred adoption or deletion of gaps','Accepting foreign link/old current value or weakening evidence/ACL/hash checks','Additional retry loop or model invocation'],
 'scope':'Implement shared claim/evidence review links and typed scenario application/comparison; retain distinct semantic judgments and legacy stored contracts.',
 'model_calls':0,'oracle_calls':0,'quality_certified':False,
}
put(DES / 'criteria.json', criteria)
put(DES / 'baseline.json', {'active': active, 'active_sha256': sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'), 'release': release})
m = read(ADR / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Lossless contract and source-safe recovery', success_criteria=criteria['success'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True, criteria_freeze_evidence=bind(DES / 'criteria.json'))
m['design']['arms'][0].update(changes='Completed ADR1282 working baseline', controls='Historical only, no causal model comparison')
m['design']['arms'][1].update(changes=criteria['scope'], controls='Same sources, authority, canonical meaning, retry and publication checks')
m['runs'][0].update(arm_ids=['verified'], artifact_path=str((ART / 'contracts/result.json').relative_to(ROOT)), selection_rule='Deterministic preservation and adversarial contract tests, native API fixtures; no live model')
m['dataset'].update(name='Typed application and shared review contracts', version='20261102-v1', frozen_source=str((DES / 'criteria.json').relative_to(ROOT)), sha256=sha(DES / 'criteria.json'), legal_version_checked=False, reference_version_checked=False)
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
