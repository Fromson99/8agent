from common import *
DES.mkdir(exist_ok=True)
previous=ROOT/'04_EXPERIMENTS/ADR/ADR-1297-main134-display-observer-live/artifacts'
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1292-rag-ontology-console-integration/artifacts/design/freeze.json')
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');selected=read(ROOT/pointer['manifest_path'])
assert pointer['generation']==134
assert all(sha(ROOT/n)==h for n,h in parent['files'].items())
assert all(parent['files'].get(n)==h for n,h in selected['files'].items())
cases=[{'id':f'{mode}-{n}-{chars}','mode':mode,'source_count':n,'extra_text_chars':chars}
 for mode in ('per-source','bulk') for n in (2,10,40,100,200) for chars in (100,)]
cases += [{'id':f'per-source-{n}-1000','mode':'per-source','source_count':n,'extra_text_chars':1000} for n in (40,200)]
put(DES/'cases.json',cases)
criteria={'hypothesis':'Ordinary final ASSESS still asks multiple overlapping review ledgers; mandatory judgment/need/scope rows and reference menus grow with acquired sources and acquisition history. Shared claim/evidence links currently apply only to hypothetical scenarios.',
 'success':['Reconstruct actual ordinary ASSESS generation schema and actual provider user/schema exactly before scaling',
 'Use unchanged current MAIN134 functions for schema preparation, reference binding and final provider encoding',
 'Keep two actual synthetic originals; add uniquely identified synthetic originals and preserve every character through projection',
 'Measure2/10/40/100/200 sources separately for per-source goals and one bulk scope; measure40/200 with1000-character added originals',
 'Separate schema bytes/system bytes/user bytes, required row counts, source bytes, repeated IDs and output sections; never equate required-name occurrences across alternatives to one response field count',
 'Separate transport timeout evidence, actual review contract errors, structural growth and untested causal model effect',
 'No external model, original record rewrite, production/MAIN/DB/policy edits'],
 'failure':'Exact observed-wire mismatch blocks growth measurements. Bounds/memory failure is recorded and no larger cell runs. This is offline structural diagnosis, not model success or throughput certification.',
 'resources':{'minimum_start_available_GiB':5,'minimum_available_GiB':3,'max_RSS_GiB':4,'max_swap_growth_MiB':128,'minimum_disk_GiB':20},
 'repeats':1,'timing':'One diagnostic construction per cell, no p95 or service-speed claim',
 'scope':'Current ordinary RAG scaling only; actual scenario request analyzed as observed. No synthetic output accepted as a product answer.'}
put(DES/'criteria.json',criteria)
inputs=[previous/'live/review-whatif/canonical/003.json.gz',previous/'live/review-whatif/raw/call-004/request.json.gz',previous/'live/review-whatif/binding.json',previous/'wire-schema-audit.json',previous/'record-inspection.json']
inputs += list((previous/'live/review-whatif/raw').glob('call-*/*.json.gz'))
inputs += list((previous/'live/review-whatif/raw').glob('call-*/finished.json'))
inputs += list((previous/'live/review-whatif/canonical').glob('*-summary.json'))
inputs += list((previous/'live/review-whatif/canonical').glob('*.json.gz'))
put(DES/'inputs.json',{'prior_artifacts':str(previous.relative_to(ROOT)),'files':{str(p.relative_to(ROOT)):sha(p) for p in inputs}})
put(DES/'selected.json',{'pointer':pointer,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'serving_files':len(selected['files']),'serving_subset_exact':True})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual wire size and compulsory review-row growth by evidence count/history',success_criteria=criteria['success'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Actual MAIN134 two-source baseline and scenario records, no new model',controls='Completed parent unchanged')
m['design']['arms'][1].update(changes='Offline synthetic source count and acquisition-history topology; unchanged product functions',controls='Same question, facts, two baseline originals, approved ontology and prompt')
m['runs'][0].update(arm_ids=['verified'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='Preregistered12 structural cells; single construction each; no live generation')
m['dataset'].update(name='MAIN134 actual synthetic wire and offline cardinality/length scaling',version='20261103-v1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[]
reason='No retrieval execution or ranking change; controlled post-retrieval input/schema growth only'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
candidate=ac.snapshot(ADR,'verified',sorted(parent['files']),experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'])
put(DES/'candidate.json',{'path':str(candidate.relative_to(ROOT))})
put(ADR/'실험/manifest.json',m)
print('Prepared12 offline cells, unchanged',len(parent['files']),'files')
