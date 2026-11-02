from common import *
from copy import deepcopy
DES.mkdir(parents=True,exist_ok=True)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==131
criteria={'hypothesis':'Exact model-declared claim, adopted evidence and reviewed scope edges can bind an omitted target without another model judgment; exhausted review returns a truthful source-only response and same-session follow-up can preserve evidence without publishing rejected claims.',
 'success':['Deterministic target binding changes target_refs only; no invented claims, evidence, needs or resolutions; raw/hash/receipt retained and all original validators run',
 'Malformed, unknown, unacquired, excluded, wrong issue, hash/ACL/stale and ambiguous scope cannot be repaired into accepted evidence',
 'After one review repair, independently valid new source requests use existing bounded reentry; otherwise verified sources may be delivered with no claims and explicit incomplete review',
 'Native API duplicates cost zero model calls; failed UNKNOWN still never auto-replays; no extra COMPOSE model for source-only reply',
 'Follow-up with facts or changed scope keeps the existing case and revalidates affected stages; no failed opinion becomes successful shortcut',
 'Actual request stats distinguish planning, investigation and correction; no unmeasured production speed or quality claim'],
 'failure':['Weakened evidence/ACL/hash/revision validation','Treat rejected legal judgment as verified answer','Same state reopens exhausted correction budget','Changes to Oracle data/schema or provider retry policy'],
 'model_calls_in_this_technical_audit':0,'oracle_calls':0,'resources':{'heavy_processes':1,'rss_GiB':4,'minimum_available_GiB':3,'max_swap_growth_MiB':128},
 'historical_case':'ADR1269 malformed-json final ASSESS: explicit C1+source+USE range but its target omitted from MN target_refs; both assessments identical.'}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'active_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Evidence-safe recovery, no redundant model calls and native follow-up preservation',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'))
m['design']['arms'][0].update(changes='Historical MAIN131 and exact failed response; read-only regression reproduction',controls='Same sources, model output, evidence validation and call budgets')
m['design']['arms'][1].update(changes='Exact edge reconciliation and explicit source-only incomplete result plus follow-up visibility',controls='Same validators, strict source isolation, provider/UNKNOWN/budgets unchanged')
m['runs'][0].update(arm_ids=['repaired'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='Historical structural defect plus synthetic adversarial contracts and native API multi-turn scenarios')
m['dataset'].update(name='Historical rejected review and synthetic native API recovery fixtures',version='20261102-main131',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[];reason='Recovery contract audit; no retrieval or model-quality effect benchmark'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sources=set(release['files'])
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):sources.add(str(p.relative_to(ROOT)));sources.update(read(p).get('files',{}))
sources.update(['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py'])
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'repaired',sorted(sources),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
put(DES/'candidate-path.json',{'candidate':str(C.relative_to(ROOT)),'snapshot':str((C/'snapshot').relative_to(ROOT))})
put(DES/'working-before.json',{n:sha(ROOT/n) for n in sorted(sources)})
print(C/'snapshot')
