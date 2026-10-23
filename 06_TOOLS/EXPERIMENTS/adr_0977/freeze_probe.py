from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');c=ROOT/s['candidate_dir'];ac.freeze(c);assert not ac.validate(c)
record=read(c/'candidate.json');revision=record['revisions'][-1]
cases=[
 ('p1','상법에서 주주총회 특별결의요건에 대해서 알려줘',['상법']),
 ('p2','민법에서 계약 해제의 기준을 알려줘',['민법']),
 ('p3','상법과 민법 안에서 책임에 관한 규정들을 비교해줘',['상법','민법']),
 ('p4','상법은 지난번 교육 얘기이고, 이번엔 민법에서 취소 요건을 찾아줘',['민법']),
 ('p5','법령을 따로 제한하지 않고 계약의 일반적인 기준을 찾아줘',[]),
 ('p6','상법 전체에서 정관 변경에 필요한 의결 기준이 궁금해',['상법']),
 ('p7','민법에 따른 법인의 의사결정을 설명해줘',['민법']),
 ('p8','상법 제434조 원문을 설명해줘',['상법'])]
save(ART/'probe-cases.json',[{'id':i,'question':q} for i,q,_ in cases]);save(ART/'probe-grading-only.json',{i:want for i,_,want in cases})
m=read(ADR/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
 'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],
 'manifest_path':str((c/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(c/'candidate.json'),
 'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
 'runner_path':str((ROOT/'06_TOOLS/EXPERIMENTS/adr_0977/probe_case.py').relative_to(ROOT)),
 'runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_0977/probe_case.py')}])
m['dataset']={'name':'Known and developer-authored public entry diagnostics','version':'scope-probe-v1',
 'frozen_source':str((ART/'probe-cases.json').relative_to(ROOT)),'sha256':sha(ART/'probe-cases.json'),
 'legal_version_checked':True,'reference_version_checked':True,'version_scope':'Published metadata only; not legal correctness'}
m['llm_policy']['llm_calls']=[{'role':'request-entry','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['design']['call_order']='p1,p3,p5,p7 baseline then candidate; even cases reverse. One physical call per case per arm, no adaptive retry.'
save(ADR/'실험/manifest.json',m)
save(ART/'probe-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'cases_sha256':sha(ART/'probe-cases.json'),'grading_sha256':sha(ART/'probe-grading-only.json'),'model_policy_sha256':sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')})
print('Frozen 8 public scope cases, 16 single model decisions; no quality promotion')
