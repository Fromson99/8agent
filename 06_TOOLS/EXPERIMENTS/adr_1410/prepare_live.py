from common import *
import shutil
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1409-financial-explanation-first-qwen/artifacts/design'
put(DES/'authorization.json',read(old/'authorization.json'))
put(DES/'provider-policy.json',read(old/'provider-policy.json'))
criteria=read(DES/'criteria.json');criteria.update(hypothesis='One minimal final answer, no final semantic review or repair, explain known information then specific user guidance; confirmed resolved route enters existing ontology.',success=['Original source IDs and exact span receipts retained; foreign references rejected', 'Guided assessment states unresolved conditions explicitly, with original source cards unchanged', 'Actual Qwen on previously acquired CM003 originals produces explanatory paragraphs without source headers; specific followup last', 'Final-stage COMPOSE and public display use the same tested module; repeated ASSESS adds no generation', 'One final-stage generation, no review/repair; unresolved route cannot be confirmed; synthetic supplied facts resolve the same goal and confirmed route stores facts and sources'])
criteria['limits']['calls']=2;criteria['stop']='UNKNOWN halts all sends; no semantic or output-format repair. Existing confirmed429 one-provider switch only.';put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual final-stage explained content and concrete followup, native repeat-free composition and multi-turn ontology chain',success_criteria=criteria['success'],failure_criteria=['Any source/ACL/claim mismatch or additional review/repair, premature unresolved knowledge confirmation','Unknown stops external sends'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for a in m['design']['arms']:a.update(changes='Parent MAIN150 reference' if a['id']=='baseline' else 'Guided final ASSESS/COMPOSE and public presentation; source boundaries unchanged',controls='Same model, CM003 question, previously verified original source scope; synthetic user-guidance lifecycle')
m['dataset'].update(name='Actual CM003 source fixture from ADR1409, no reference answer',version='20261105',frozen_source=str((DES/'actual-cm003.json.gz').relative_to(ROOT)),sha256=sha(DES/'actual-cm003.json.gz'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['explanation'],selection_rule='One existing CM003 final-stage request with recorded actual originals; no selection by new model outcome',artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Only final answer changes; source acquisition fixed to previously verified ADR1409 CM003 originals.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='Final-stage probe consumes previously acquired originals; no retrieval or candidate filtering in this run.')
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*DES.glob('*.json'),DES/'actual-cm003.json.gz',ROOT/'02_BACKEND/lawrag/research/experiment_client.py',ROOT/'02_BACKEND/lawrag/core/request_deadline.py']
put(DES/'live-pins.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.name!='live-pins.json'},'before_calls':True})
print('Final-stage actual Qwen inputs and scripts frozen')
