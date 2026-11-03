from common import *
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==133
criteria={'hypothesis':'Shared authenticated console connects maintained workspace/domain and scenario panels, explicit source/glossary ports and exact scenario displays without widening permissions or changing source facts.',
 'success':['Both actual Streamlit entries reach existing review and new workspace with durable writes and identity isolation',
 'Trusted host authoring ports bind operator/source snapshot/ACL/glossary and close resources; reader and writer scopes are separate',
 'Runtime readiness distinguishes OFF/empty/ready/error without model calls or implicit activation',
 'Only exact offered computed references in model reason fields trigger existing bounded repair; originals and arbitrary prose stay intact',
 'Scenario current needs separate historical declarations without text replacement; saved/current displays preserve context',
 'Updated tests enforce compiler compatibility and source DOM fidelity, not historical whole-file hash',
 'Contracts, real Oracle isolated authoring/reader and exact serving/UI package bindings verified; failures preserved'],
 'failure':['ACL/source/version/receipt weakening','Lost raw text or historical state','False publication/activation','Unexpected repeated model request','Unverified code selected'],
 'scope':'Implementation and synthetic contracts; actual model follow-up is separate ADR; no retrieval quality comparison',
 'authorization':'User accepted the concrete repair plan with 한 번 진행해봐 (actual message: 한번진행해봐); local MAIN/Gold and UI package included, no field deployment/Git push/email',
 'quality_certified':False,'existing_main':active,'known_live_limits':'ADR1290 NOT_PASSED preserved; N1 unregistered, UNKNOWN not retried',
 'resource_limits':{'minimum_available_ram_gib':3,'max_process_rss_gib':4,'maximum_swap_growth_mib':128,'serial_heavy_processes':True}}
put(DES/'criteria.json',criteria);put(DES/'baseline.json',{'active':active,'active_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release,
 'gold_binding':read(GOLD/'binding.json'),'gold_files':{str(p.relative_to(ROOT)):sha(p) for p in GOLD.iterdir() if p.is_file()}})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Authenticated end-to-end wiring and lossless consumer contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'))
m['design']['arms'][0].update(changes='MAIN133 and preserved ADR1289/1290 results',controls='Historical baseline, no causal model comparison')
m['design']['arms'][1].update(changes=criteria['scope'],controls='Same source/version/ACL/approval/state/model budget')
m['runs'][0].update(arm_ids=['verified'],selection_rule='Deterministic contract and native consumers; no semantic effect comparison',artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
m['dataset'].update(name='Console, Oracle ports and scenario presentation contracts',version='20261103-v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
reason='Connection and contract implementation; no retrieval selection comparison'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sources=set(release['files'])
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
 sources.add(str(p.relative_to(ROOT)));sources.update(read(p).get('files',{}))
for n in ('app.py','ontology_app.py','ontology_private_app.py','ontology_dashboard.py','ontology_dashboard_model.py','ontology_dashboard_demo.py','test_ontology_dashboard.py'):
 sources.add('03_FRONTEND/APPS/legal-knowledge-streamlit/'+n)
for n in ('test_wiki_workspace.py','test_genos_answer_reference_display.py'):sources.add('05_TESTS/CONTRACTS/'+n)
sources.update(['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py'])
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'verified',sorted(sources),experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'])
put(DES/'candidate-path.json',{'candidate':str(C.relative_to(ROOT)),'snapshot':str((C/'snapshot').relative_to(ROOT))})
put(DES/'working-before.json',{n:sha(ROOT/n) for n in sources})
print(C/'snapshot',len(sources))
