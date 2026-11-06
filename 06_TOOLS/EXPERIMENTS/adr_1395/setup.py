from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
P=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1393-*/artifacts'))
f=read(P/'design/candidate-reviewed.json')
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path'])
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'working-before.json',f['selected_files']);put(DES/'candidate-parent.json',f)
claims=[]
for p in (ROOT/'04_EXPERIMENTS/ADR').glob('ADR-*/실험/manifest.json'):
 m=read(p);r=m.get('reservation',{})
 if r.get('status')=='in_progress' and int(m['adr_id'].split('-')[1])>=1387:claims.append({'adr':m['adr_id'],'scope':r['scope'],'session':r['session_id']})
put(DES/'traffic.json',{'active':claims,'base':'Completed1393 reviewed snapshot exactly working528','selected_main':pointer,
 'ownership':{'1391/1393':'Completed navigation supervisor, target binding and halt recovery; adopt exact existing bytes.','1392':'Selected146 bound chat review. Do not replace its code.','1394':'Read-only146 request audit, immutable code and data. This work does not mutate selected release.','1395':'Only ontology prompt, short final ontology review in existing investigation_supervisor, completion hook and targeted diagnostics.'},
 'shared_files':['02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py','02_BACKEND/semantic_runtime/legal_agent/completion_execution.py'],
 'integration_rule':'No working writes until all frozen candidate tests pass. Recheck all528 working hashes before first write; stop on drift. No superseding another reservation or pending live experiment.'})
criteria={'hypothesis':'The existing supervisor also receives ontology in investigation and checks final explanation/claim usage with a short reply.',
 'success':['Existing navigation action, halt, unknown and target binding contracts preserved.',
 'Final structurally valid ontology claims receive a compact model review. PASS is one field; REPAIR contains only bounded issues. No answer rewrite by reviewer.',
 'Source, claim, path and package validation remains before review. A REPAIR feeds the original one-repair ASSESS owner. Cached review adds zero physical sends; unknown review cannot be replayed.',
 'Off or no offered ontology causes zero extra calls. Use of an ontology is not forced on an ordinary question.',
 'Real native API delivers approved package and executes the review with preserved source/ACL, withdrawal and duplicate behavior.'],
 'failure':['Do not change MAIN or other ongoing experiment bytes. Preserve every failed result.','No automatic adoption, fabricated evidence, new retry owner, or budget reset.'],
 'limits':{'assessment_proposals':2,'review_calls_per_proposal':1,'external_live_calls':0},
 'timing':'Record input/schema sizes and call counts on archived and synthetic cases. Do not claim real latency or semantic quality without fresh model calls.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source-bound short ontology review reaches existing native assessment and bounded recovery',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for a in m['design']['arms']:a.update(changes='Completed1393 exact working reference' if a['id']=='baseline' else 'Extend existing supervisor with ontology decision review',controls='Same originals, ontology inputs, canonical constraints, 40-call request budget, one ASSESS supplement and concurrent selected MAIN146')
m['dataset'].update(name='Recorded1383 ontology cases and synthetic native API failures',version='supervisor-1395-v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Frozen archived source examples and synthetic API reviewer output, no physical external call',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
for v in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):v['not_applicable_reason']='Technical review integration, no new retrieval benchmark or corpus change'
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'repaired',list(f['selected_files']),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n,h in f['selected_files'].items():assert sha(can/'snapshot'/n)==h
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(f['selected_files'])})
print(can/'snapshot')
