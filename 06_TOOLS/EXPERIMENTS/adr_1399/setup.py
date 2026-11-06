from common import *
import shutil,importlib.util
from cases import cases
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/ptr['manifest_path'])
files=list(release['files'])+['02_BACKEND/semantic_runtime/legal_agent/reason_decision_review.py','02_BACKEND/semantic_runtime/ontology_work/reason_review.py']
assert len(set(files))==530
pins={n:sha(ROOT/n) for n in files}
put(DES/'baseline.json',{'pointer':ptr,'release':release,'source':'Current completed common review implementation; includes preserved parallel lifecycle changes; no product edits in this experiment'})
put(DES/'source-code.json',{'files':pins})
rows,gold=cases();put(DES/'probe-cases.json',rows);put(DES/'offline-expectations.json',gold)
question='상법 제365조 제2항에서 연 2회 이상 결산기를 정한 회사는 언제 총회를 소집하나요?'
put(DES/'live-cases.json',[{'id':'public-native','arms':['common-review'],'document_ids':['7bbe815ff43b6635'],'steps':[{'number':1,'question':question,'mode':'외규'}]}])
criteria={'authorization':'실험해봐 qwen으로','hypothesis':'The shared diagnostic catches reason/decision conflicts without rejecting consistent partial/nonuse/different-axis decisions, and the primary reconsideration is checked before downstream acceptance.',
 'success':['All five seeded contradictions receive structurally valid REPAIR with exact actual fields and a literal rationale quote.','All seven consistent controls receive PASS; legal correctness is a separate responsibility.','For the five seeded contradictions, existing bounded_decision supplies the initial controlled proposal, then only actual Qwen supplies a full primary reconsideration and the same reviewer checks it. Acceptance and exact proposed action are recorded through the real work journal. This is a boundary harness, not natural error frequency or a full source-tool execution.','One fresh public-law native API question uses actual Qwen at every product stage with default validators and common review enabled; source-supported answer and duplicate physical0 required.'],
 'failure':['No added output cap or hidden format/transport retry. Any UNKNOWN or remote5xx stops all future external sends in this ADR.','Keep faulty proposals and failed diagnoses; no product/schema/prompt correction after outcome. Misclassification stays failed, not retried with revised expectations.'],
 'limits':{'physical_total':64,'probe_max':22,'native_request_max':40,'single_physical_seconds':180,'native_request_seconds':1800,'probe_per_case_seconds':600,'heavy_workers':1,'available_ram_start_gib':5,'available_ram_floor_gib':3,'rss_gib':5,'swap_growth_mib':128,'reported_cost_stop_usd':3},
 'repair_case_ids':['case-01','case-03','case-05','case-07','case-09'],'order':[r['id'] for r in rows],'repeat':1,'source_scope':['synthetic','public'],'no_reference_answers_in_product':True,'real_generation_replay':0,'promotion':False,
 'collision_note':'1398 was concurrently reserved for different task1 alternate-provider scope. Its claim was inspected before reserving1399; no same-scope reservation was bypassed.'}
put(DES/'criteria.json',criteria)
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1397-multiturn-knowledge-lifecycle-qwen/artifacts/design'
put(DES/'source-scope.json',read(old/'source-scope.json'))
policy=read(old/'provider-policy.json');policy['providers']=policy['providers'][:1];policy['reason']='ADR1399 uses configured Parasail FP8 only. One listed provider makes effective switching zero.';policy['authorization']={'source':'user_message','text':'실험해봐 qwen으로','session_id':'01a1a9ef-01a7-7be3-8b83-ea8f815bb3e8'}
put(DES/'provider-policy.json',policy)
auth=read(old/'authorization.json');auth.update(user_request=criteria['authorization'],cases_sha256=sha(DES/'live-cases.json'),scope='This isolated frozen experiment: public Commercial Act single question and synthetic contradiction/consistent probes only; no operational publication')
put(DES/'authorization.json',auth)
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1397-multiturn-knowledge-lifecycle-qwen/artifacts/transport',ART/'transport')
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']='First actual Qwen probe of completed task2 common review implementation; frozen current code with no product changes.'
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Five conflict detections, seven non-rejections, primary reconsideration acceptance and one actual native source-backed answer; no population rate estimate',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for a in m['design']['arms']:a.update(changes='Historical implementation reference, not run' if a['id']=='baseline' else 'Unchanged working common-review code, current preserved lifecycle consumers',controls='Same frozen Qwen3.8 Parasail FP8/none, current originals and strict validators; no output cap or fallback')
m['runs'][0].update(arm_ids=['common-review'],selection_rule='Fixed12 interleaved boundary cases, then bounded primary reconsideration for five predeclared seeded faults, then public native1. Stop globally on UNKNOWN or resource boundary.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='Shared reason-decision synthetic paired boundary probe and public Commercial Act native request',version='ADR1399-r1',frozen_source=str((DES/'probe-cases.json').relative_to(ROOT)),sha256=sha(DES/'probe-cases.json'))
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','common-review')};m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'common-review',files,experiment_id=m['experiment_id'],arm_id='common-review',run_ids=['run-001']);ac.freeze(can);assert not ac.validate(can),ac.validate(can)
v=read(can/'candidate.json');rev=v['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot';assert all(sha(C/n)==pins[n] for n in files)
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':pins,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-repaired.json',desc)
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='common-review',experiment_id=m['experiment_id'],arm_id='common-review',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'probe.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'probe.py'))]);put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.name!='freeze-public.json'},'before_model_calls':True})
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf);e,c,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':e,'files':c,'errors':errors});print('FROZEN',len(files),e,c,'model calls0',flush=True)
