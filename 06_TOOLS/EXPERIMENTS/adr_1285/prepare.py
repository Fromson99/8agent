from common import *
active = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(ROOT / active['manifest_path'])
criteria = {
 'hypothesis':'Restrict scenario links to explicit condition applications, keep nonadopting claim references host-owned, and separate current application from optional historical comparison without modifying originals.',
 'success':[
  'Unlinked approval/exception explanations are allowed when unchanged; changed conditions still require actual claim coverage.',
  'Current prose cannot reuse replaced amounts even with historical references or no application link; original GENERAL_RULE remains intact.',
  'Optional comparison_text preserves full before/after prose separately; equivalent KRW units remain exact and unknown approval remains unknown.',
  'Nonadopting review rows retain full gap/evidence/status/reason and host-owned empty claim list, without a shared claim link.',
  'Shared-link errors use model-visible paths and retain per-row cardinality constraints and original canonical validation.',
  'Scenario input is assembled from separate task/facts before serialization; no slicing or parsing of a rendered question; baseline/source/old receipt compatibility retained.',
  'Native API normal/repair/repeated failure/publication/duplicate and full600character gap checks; working and frozen code equal.'
 ],
 'failure':['Text truncation or semantic guessing','Accepting historical amount as current through comparison refs or unlinked claims','Loss of evidence/ACL/hash/unknown/budget constraints','Automatic model retry beyond existing single repair'],
 'recovery':{'owner':'completion_execution ASSESS existing first+one repair','auto_correction':'Only schema-fixed empty lists; no claims, gaps, opinions or prose rewritten','final':'Existing source-only INCOMPLETE after unresolved contracts, failed proposal preserved'},
 'scope':'ADR1284 observed errors; new versioned application receipt, state-preserving review projection, structured scenario input; integrate verified delta only',
 'model_calls':0,'oracle_calls':0,'quality_certified':False,
}
put(DES / 'criteria.json', criteria)
put(DES / 'baseline.json', {'active': active, 'active_sha256': sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'), 'release': release})
m = read(ADR / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Lossless contract and source-safe recovery', success_criteria=criteria['success'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True, criteria_freeze_evidence=bind(DES / 'criteria.json'))
m['design']['arms'][0].update(changes='Completed ADR1284 actual failures, identical working code', controls='Historical only, no causal model comparison')
m['design']['arms'][1].update(changes=criteria['scope'], controls='Same sources, authority, canonical meaning, retry and publication checks')
m['runs'][0].update(arm_ids=['verified'], artifact_path=str((ART / 'contracts/result.json').relative_to(ROOT)), selection_rule='Deterministic preservation and adversarial contract tests, native API fixtures; no live model')
m['dataset'].update(name='Scenario review scope and comparison contracts', version='20261102-v1', frozen_source=str((DES / 'criteria.json').relative_to(ROOT)), sha256=sha(DES / 'criteria.json'), legal_version_checked=False, reference_version_checked=False)
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
