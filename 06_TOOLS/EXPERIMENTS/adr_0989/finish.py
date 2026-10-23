"""Offline accounting only; never dispatches a model request."""
from common import *
import sys, xml.etree.ElementTree as ET
sys.path.insert(0, str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS, QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json')
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert all(sha(ROOT/n)==h for n,h in f['working_files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
assert all(sha(ROOT/s['base_release']['code_root']/n)==h for n,h in s['base_release']['files'].items())
out=ART/'known-query/candidate';r=read(out/'result.json');response=read(out/'response.json')
stop=read(ART/'stop.json') if (ART/'stop.json').exists() else None
calls=[]
for p in sorted((out/'model').glob('call-*/response.json')):
    raw=read(p)
    calls.append({'call':p.parent.name,'error_code':(raw.get('error') or {}).get('code'),'completed_choice':bool(raw.get('choices'))})
tests=list(ET.parse(ART/'stop-policy-tests.xml').getroot().iter('testcase'))
old=ROOT/'04_EXPERIMENTS/ADR/ADR-0988-grounded-expansion-decision/artifacts'
historical=ROOT/'04_EXPERIMENTS/ADR/ADR-0985-model-resolved-scope-authority/artifacts/known-query'
history=[]
for p in sorted((historical/'model').glob('call-*/response.json')):
    raw=read(p);v=json.loads(raw['choices'][0]['message']['content'])
    history.append({'call':p.parent.name,'choice':v.get('choice'),'output_fields':list(v)})
summary={'status':'MODEL_EVALUATION_UNAVAILABLE' if stop else 'SERVICE_COMPLETED',
 'physical_calls':r['model_calls'],'service_status':response.get('status'),'seconds':r['seconds'],
 'completed_answers':int(response.get('status')==200),'source_quality':None if stop else 'requires offline inspection',
 'stop':stop,'guard':read(ART/'guard-result.json'),'calls':calls,
 'checks':{'physical_limit':r['model_calls']<=8,'no_call_after_failure':bool(stop and r['model_calls']==stop['calls']),
 'stop_tests':len(tests),'stop_test_errors':sum(t.find('error') is not None or t.find('failure') is not None for t in tests),
 'unchanged_candidate_files':len(f['files']['candidate']),'unchanged_working_files':len(f['working_files']),
 'unchanged_selected_release_files':len(s['base_release']['files']),'main_pointer_unchanged':True},
 'prior_experiment':{'baseline_original_calls':read(old/'known-query/baseline/result.json')['model_calls'],
 'candidate_original_calls':read(old/'known-query/candidate/result.json')['model_calls'],
 'synthetic_calls':sum(read(p)['calls'] for p in (old/'trials').glob('*/*/result.json')),
 'root_cause':'run_case saved a failed result but exited zero; guard checked exit code/resources only and continued subsequent planned cases after provider429.'},
 'historical_completed_question':{'result_path':str((historical/'result.json').relative_to(ROOT)),
 'model_calls':read(historical/'result.json')['model_calls'],'seconds':read(historical/'result.json')['seconds'],'phases':history,
 'interpretation':'Entry1, search/read choice2, assessment1, additional read/assessment twice4, composition1. No claim that all expansion is unnecessary in general.'},
 'main_changed':False,'genos_changed':False,'quality_certified':False}
save(ART/'result.json',summary)
m=read(ADR/'실험/manifest.json')
assert m['design']['success_criteria']==f['design']['success_criteria']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','historical_reference_only':True,'new_physical_calls':0},'candidate':{'status':'complete','evaluation':'unavailable','physical_calls':r['model_calls'],'service_status':response.get('status'),'correct':None}},comparisons=[],judge_disagreements=0,usage={'physical_calls':r['model_calls'],'successful_model_responses':sum(c['completed_choice'] for c in calls)},latency={'service_seconds':r['seconds'],'failure_latency_only':True},error_taxonomy=[{'kind':'provider429','calls':r['model_calls'],'retained':True}])
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[
 'Provider429 on the first request; stopped after one physical call. No accuracy or speed claim. MAIN100 unchanged.',
 'Previous20requests were a comparison experiment: baseline original3, candidate original1, eight paired probes16. The runner advanced after recorded provider errors because it checked process exit alone. This recheck preserves that history and corrects experiment stopping.',
 m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
 m['design']['sampling'],
 'Product419files unchanged from frozen ADR0988 candidate. Same public source generation and Qwen3.8 Parasail FP8, reasoning none, no fallback. Native and physical caps8, transport retries0, wall480seconds; source/ACL/hash/state validators retained. This budget differs from MAIN100 and is not a paired performance test.',
 json.dumps(summary['checks'],ensure_ascii=False,indent=2)+'\n\nOne call, zero complete model responses; service503. Source quality unavailable.',
 'Provider error429 preserved under artifacts/known-query/candidate/model. Sticky stop denies further dispatch; the process exits2 and the outer runner also reads saved results. Seven mock tests cover zero-exit recorded failure, first-failure preservation, restart stop, budget and normal completion.',
 f'Physical calls: {r["model_calls"]}; service interval: {r["seconds"]:.3f}s; this is failure latency, not answer speed. No model judge or separate health check.',
 'Existing assessment and next-tool choice remain separate. The candidate adds source-bound prior opinions and requested-need guidance to existing calls; it does not add a review call or implement full phase fusion.',
 'One in-sample question; first-call provider failure prevents assessment of grounded expansion, answer correctness or speed. Source/permission/version and selected-release integrity were checked without claiming GENOS field validation.',
 'No promotion or production edits. MAIN100 remains selected. Exact prior artifacts preserved. Any future model attempt must be a separately reserved experiment; do not rerun this directory.',
 'Frozen design: [design-freeze.json](artifacts/design-freeze.json). Result: [result.json](artifacts/result.json). Runner: 06_TOOLS/EXPERIMENTS/adr_0989/guard.py. Completed output directories and stop marker prohibit in-place replay.'
]
(ADR/'README.md').write_text('---'+front+'---\n\n# 추가 탐색 후보 단일 질문 재확인\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
q=m['questions'][0];request=read(ART/'known-request.json')
values=['run-001, candidate only; historical baseline has zero new calls.',json.dumps(request,ensure_ascii=False,indent=2),m['design']['success_criteria'],
 '[Frozen request](../artifacts/known-request.json), [code/model/source binding](../artifacts/design-freeze.json).',
 'No corpus retrieval recall comparison. Provider failed before a full source investigation.',
 '[Exact model request](../artifacts/known-query/candidate/model/call-001-service/request.json) and [provider response](../artifacts/known-query/candidate/model/call-001-service/response.json).',
 'Existing native phases; physical cap8, provider error stops immediately. Actual calls1.',
 'Offline accounting only, no model judge, correct=null because no completed answer.',json.dumps(summary,ensure_ascii=False,indent=2)]
qp=ADR/'실험'/q['file'];qp.write_text('# known-special-resolution\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)));q['sha256']=sha(qp)
(ADR/'실험/README.md').write_text('# 실험 질문\n\n- [원래 상법 질문]('+q['file']+')\n')
save(ADR/'실험/manifest.json',m)
rows=[]
for p in sorted(ART.rglob('*')):
    if not p.is_file() or p==ART/'manifest.json' or 'runtime' in p.relative_to(ART).parts:continue
    rows.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen configuration, exact inputs/outputs, failures and stop checks','contains_raw_prompts_and_outputs':'model' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0989','files':rows})
(ADR/'RESULT.txt').write_text('원래 상법 질문 단일 재확인: 첫 제공자 요청429로 모델1회에서 중단. 추가 호출0, 답변·속도 개선 검증 불가.\n이전20회는 원래 질문 기준3+후보1+합성8사례의 기준/후보16회. 실패 결과를 저장한 프로세스의 종료0만 보고 다음 사례를 진행한 실험 실행기 오류였다.\n이번 실행기는 제공자/전송 오류 즉시 중단 기록을 저장하고 추가 요청을 거부하며, 실행 결과의 실패와 프로세스 종료를 모두 확인한다. 중단·예산·재개·정상 경로7검사 통과.\n기존 완료 질문은9회: 요청 해석1, 검색·읽기 선택2, 평가1, 추가 읽기 선택/평가 두 차례4, 답변 작성1. 후보 수정으로 감소하는지는 미확인.\n후보419파일·작업419파일·선택 릴리스419파일과 MAIN100 포인터 불변. GENOS·Git commit/push 미수행.\n')
print(json.dumps({'physical_calls':r['model_calls'],'stop':stop,'checks':summary['checks']},ensure_ascii=False))
