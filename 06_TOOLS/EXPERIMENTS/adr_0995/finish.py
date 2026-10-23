"""Close one read-only diagnostic with exact trace and an explicit human-readable verdict."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');o=read(ART/'observations.json');review=read(ART/'review.json')
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert sha(ART/'known-request.json')==f['request_sha256']
r=o['native_result'];stop=read(ART/'stop.json') if (ART/'stop.json').exists() else None
summary={'status':'COMPLETE','verdict':review['verdict'],'passed':review.get('passed'),'findings':review['findings'],
 'physical_calls':r.get('model_calls',0),'replayed_attempts':r.get('replayed_model_attempts',0),'service_status':o['service_status'],'seconds':r.get('seconds'),
 'outcome':o['outcome'],'citation_integrity':o['citation_integrity'],'usage':r.get('usage',[]),'stop':stop,
 'integrity':{'candidate_files_verified':419,'main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256'],'selected_release_unchanged':all(sha(ROOT/s['base_release']['code_root']/n)==h for n,h in s['base_release']['files'].items()),'working_drift':[n for n,h in f['working_files'].items() if sha(ROOT/n)!=h]},
 'limits':review['limits'],'main_changed':False,'genos_changed':False}
save(ART/'result.json',summary)
m=read(ADR/'실험/manifest.json');assert m['design']['success_criteria']==f['design']['success_criteria']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','historical_reference_only':True,'new_calls':0},'candidate':{'status':'complete','verdict':review['verdict'],'passed':review.get('passed'),'new_calls':r.get('model_calls',0)}},comparisons=[],judge_disagreements=0,usage={'physical_calls':r.get('model_calls',0),'replayed_attempts':r.get('replayed_model_attempts',0)},latency={'service_seconds':r.get('seconds'),'paired_comparison':False},error_taxonomy=[] if review.get('passed') else [{'kind':review['verdict'],'result_path':str((ART/'result.json').relative_to(ROOT))}])
front=(ADR/'README.md').read_text().split('---',2)[1]
if review.get('passed') is False:front=front.replace('status: Proposed','status: Rejected')
parts=[f'{review["verdict"]}. 실제 모델 {r.get("model_calls",0)}회, 저장 응답 재사용 {r.get("replayed_model_attempts",0)}회. MAIN100 변경 없음.',
 '직전 ADR0992의8회 예산에서는 제434조 원문을 읽고 필수 gap을 낸 뒤 탐색으로 재진입하지 못했다. 사용자가 예산 제약을 제거하고 다음 탐색의 필요성 재검토가 실제 동작하는지 확인하도록 요청했다.',
 m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
 '동일419제품파일과 원문 세대. Qwen3.8 Parasail FP8 only, reasoning none, fallback 없음. 정상 요청 한도40회·1800초, final reserve3, 재진입2, no-progress2. 제공자 재시도0; 별도 의미 검토 호출 없음.',
 json.dumps({k:summary[k] for k in ('verdict','passed','physical_calls','replayed_attempts','service_status','seconds','outcome')},ensure_ascii=False,indent=2),
 '\n\n'.join(review['findings']),
 '모델별 정확한 요청·응답·usage와 지연은 [관찰 기록](artifacts/observations.json) 및 질문 문서에 연결했다. 한 사례 진단이며 paired speed/accuracy 비교가 아니다. 회수 구현·데이터는 바꾸지 않았고 실제 조문 읽기를 원시 journal로 기록했다.',
 review['interpretation'],'\n\n'.join(review['limits']),
 '제품 작업 코드·MAIN 포인터·GENOS 변경 없음. 이전 후보의 승인·승격을 뜻하지 않는다. 새 실행·변경은 후속 ADR로 기록하며 완료된 기록은 덮어쓰지 않는다.',
 str(Path(__file__).with_name('guard.py').relative_to(ROOT))+'; 기존 산출물에서 재실행 불가. [사전 동결](artifacts/design-freeze.json) · [판정](artifacts/review.json) · [전체 관찰](artifacts/observations.json).']
(ADR/'README.md').write_text('---'+front+'---\n\n# 추가 조사 필요성 재검토 진단\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
links=[]
for parent in ('model','replay'):
 for p in sorted((ART/'known-query/candidate'/parent).glob('*/*.json')):links.append(f'[{p.relative_to(ART/"known-query/candidate")}](../artifacts/{p.relative_to(ART)})')
row=m['questions'][0]
values=['run-001; candidate once.',json.dumps(read(ART/'known-request.json'),ensure_ascii=False,indent=2),m['design']['success_criteria'],
 '[Frozen code/data/request binding](../artifacts/design-freeze.json). Actual source headings and native events: [observations](../artifacts/observations.json).',
 'Unchanged retrieval; actual actions/reads retained. No new gold recall comparison.','\n\n'.join(links),
 'Existing native model phases. Any replay receipt explicitly marks no new external call. No judge or health-check call.',
 'Offline trace reading only; no evaluator input enters product.',json.dumps(review,ensure_ascii=False,indent=2)]
qp=ADR/'실험'/row['file'];qp.write_text('# 원래 상법 질문\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)));row['sha256']=sha(qp)
(ADR/'실험/README.md').write_text('# 사례\n\n- [원래 상법 질문]('+row['file']+')\n');save(ADR/'실험/manifest.json',m)
items=[]
for p in sorted(ART.rglob('*')):
 if p.is_file() and p!=ART/'manifest.json' and 'runtime' not in p.relative_to(ART).parts:items.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Exact frozen input, model response, replay receipt or offline finding','contains_raw_prompts_and_outputs':'model' in p.parts or 'replay' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':items})
(ADR/'RESULT.txt').write_text(f'{review["verdict"]}\n실제 모델{r.get("model_calls",0)}회, 저장 응답 재사용{r.get("replayed_model_attempts",0)}회. {r.get("seconds")}초, 서비스{o["service_status"]}.\n'+'\n'.join(review['findings'])+'\nMAIN100/GENOS 변경 없음.\n')
print(json.dumps({k:summary[k] for k in ('verdict','physical_calls','replayed_attempts','service_status','seconds')},ensure_ascii=False))
