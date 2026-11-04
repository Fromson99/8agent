from common import *
import shutil
DES.mkdir(exist_ok=False)
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1353-ontology-acquisition-norm-link-boundary/artifacts'
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1351-integration-oneclick-provider-matrix/artifacts'
parent=read(P/'design/candidate-repaired.json')
before={n:sha(ROOT/n) for n in parent['selected_files']}
assert before==parent['selected_files'],'Concurrent working drift'
put(DES/'working-before.json',before);put(DES/'baseline.json',read(P/'design/baseline.json'));put(DES/'candidate-parent.json',parent)
for name in ['live-cases.json','grading-only.json','provider-parasail.json']:
 put(DES/name,read(old/'design'/name))
put(DES/'providers.json',{'parasail':{'tag':'parasail/fp8','name':'Parasail'}})
put(DES/'authorization.json',{'source':'user_message','text':'조항 경로 누락이랑 공백 응답 원인 제대로 찾아서 수정하고 다시 돌려봐. 검증 빼서 통과시키지 말고 실제 답변까지 나오게 해봐','session_id':'01a1a6be-d265-7f81-a248-0cb375648beb','prior':str(old/'design/authorization.json')})
criteria={'hypothesis':'Entry must validate model structure against stored metadata inside its existing bounded repair. Equivalent wire ordering puts a mutually exclusive discriminator before common open text to reduce ambiguous grammar prefixes; effect requires actual evidence.',
 'success':['Missing ancestor rejected and repaired once by model using original question; no inferred article or changed source','Original and projected schema accept same decisions; all branch fields, IDs, limits and final review retained','Actual B03-03 and B03-17 each produce supported claims with audited source/ACL/wire/budget and no duplicate sends'],
 'failure':['Unknown stops physical sends in this run; do not mislabel HTTP-body whitespace as model tokens','No success by HTTP200, raw-only output, weaker validation, answer injection, or MAIN promotion','Local grammar compilation cannot certify remote backend cause'],
 'plan':{'cases':['B03-03','B03-17'],'providers':['parasail'],'max_calls':80,'reasoning':'none','max_output_tokens':None,'model_deadline_seconds':180,'request_deadline_seconds':1800,'final_review':True,'repeats':1},
 'limits':{'heavy_workers':1,'available_start_GiB':5,'available_stop_GiB':3,'rss_GiB':5,'swap_growth_MiB':128},
 'failure_owner':'Existing request-entry bounded_decision, one durable repair, no scope mutation on rejected proposal. Only structural selection ambiguity/missing ancestor is repairable; missing document and permission/hash errors retain original paths. Transport unknown never re-sent.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Supported real answers and exact validation/evidence invariants',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed1353; historical1351 observed failures',controls='Historical observations not fresh paired baseline')
m['design']['arms'][1].update(changes='Stored structure validation in existing entry repair; equivalent discriminator-first wire order',controls='Same Qwen/provider/review/source; no source or legal meaning correction')
m['dataset'].update(name='R4 public365 and434 failure follow-up',version='20261104-r4',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Fixed365 then434, one sequential worker; UNKNOWN stop',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'repaired',list(before),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(before),'product_files':['02_BACKEND/semantic_runtime/legal_agent/request_entry.py','02_BACKEND/semantic_runtime/legal_agent/structure_selection.py','02_BACKEND/semantic_runtime/legal_agent/wire_schema.py']})
shutil.copytree(old/'transport',ART/'transport')
print(can/'snapshot')
