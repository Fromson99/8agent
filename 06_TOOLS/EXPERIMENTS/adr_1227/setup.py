from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1227-source-first-authoring-semantics'
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
a=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
b=json.loads((ROOT/a['manifest_path']).read_text());assert a['generation']==122
criteria={'hypothesis':'Remove prior-opinion anchoring by a separate source-only normative analysis; bind typed actions/modality/conditions and comparison checks to that analysis. Recorded reason/purpose nullable with explicit raw role evidence, never accumulator explanation.',
'success':['Source-only call has no observations/base/glossary; exact source and immutable receipt binding','All coordinated actions and modality of selected source norms restored deterministically; conditions selected only from separately classified source conditions or performance requirements','SUPPORTED contradicting a declared semantic mismatch rejected; unknown remains unknown','Absent recorded reason/purpose stays absent; explicit labeled or textual role requires exact raw proof; full claim/identifier copying rejected','Original canonical storage/profile/compiler unchanged; old stored data readable','Synthetic positive/negative/workflow contracts and existing regression with explicitly adapted mock wire fixtures; no hidden extra repairs','Frozen candidate/local MAIN consumer/data bindings verified before integration'],
'failure':'Any fabricated source, inferred legal answer by server, weakened original validator, stale source acceptance, hidden retry or new regression blocks integration',
'external_model_calls':0,'semantic_quality_certified':False,'max_parallel_heavy_processes':1,'legacy_fixture_adaptation':'Mock generator responses mechanically translate absent canonical reason/purpose and canonical coordinates to the new request contract; no product validation bypass. New tests exercise new source-only stage.',
'actual_experiment':'Separate ADR, same approved originals5/records2/glossary9, OpenRouter Qwen3.8 max9physical, Parasail; confirmed429 only one NearAI fallback. New source-analysis calls included.',
'compatibility':'profile.py/profile_schema.py/assembly_ir.py/assembly_compiler.py unchanged; receipts additive; original direct operator save remains validated canonical API; model-generated path requires new wire contract'}
d=ADR/'artifacts/design';d.mkdir(parents=True,exist_ok=True)
write_summary(d/'criteria.json',criteria)
write_summary(d/'baseline.json',{'active':a,'manifest':b,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':{n:sha(ROOT/n) for n in b['files']}})
m=json.loads((ADR/'실험/manifest.json').read_text());m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Synthetic contract preservation; actual semantic comparison separately',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((d/'criteria.json').relative_to(ROOT)),'sha256':sha(d/'criteria.json')},execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':['ADR-1225-experiment-v1/authoring-contract'],'changes':'Exact MAIN122','controls':'same canonical profiles and sources'},{'id':'source-first','role':'candidate','derived_from':['baseline'],'changes':criteria['hypothesis'],'controls':'same source authority and original canonical validators'}])
m['dataset'].update(name='Synthetic source-only analysis and recorded-role contracts',version='v1',frozen_source=str((d/'criteria.json').relative_to(ROOT)),sha256=sha(d/'criteria.json'))
m['llm_policy']['llm_calls']=[];m['runs'][0].update(arm_ids=['baseline','source-first'],selection_rule='All predeclared synthetic cases',artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
m['retrieval_accounting']['not_applicable_reason']='Authoring semantic contracts';m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='No retrieval experiment'
(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
print(ac.snapshot(ADR,'source-first',sorted(b['files']),experiment_id=m['experiment_id'],arm_id='source-first',run_ids=['run-001']))
