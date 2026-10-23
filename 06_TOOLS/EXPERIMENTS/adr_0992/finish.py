"""Offline, source-linked accounting; no evaluator can change product output."""
from common import *
import sys,statistics
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
s=read(ART/'stage.json');f=read(ART/'design-freeze.json')
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots'][a]/n)==h for a,files in f['files'].items() for n,h in files.items())
assert sha(ART/'cases.json')==f['cases_sha256'] and sha(ART/'grading-only.json')==f['grading_sha256']
drift=[n for n,h in f['working_files'].items() if sha(ROOT/n)!=h]
pointer_unchanged=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
selected_unchanged=all(sha(ROOT/s['base_release']['code_root']/n)==h for n,h in s['base_release']['files'].items())
native=ART/'known-query/candidate';nr=read(native/'result.json') if (native/'result.json').exists() else {}
response=read(native/'response.json') if (native/'response.json').exists() else {}
body=response.get('body',{});assembly=body.get('assembly',{});answer=body.get('answer',{});agent=assembly.get('term_agent',{})
text=answer.get('text','').replace(' ','');trace=[];prompts=[];all_calls=[]
def calls(folder):
 rows=[]
 for p in sorted(folder.glob('model/call-*/request.json')):
  request=read(p);raw=read(p.with_name('response.json')) if p.with_name('response.json').exists() else {}
  value={};view={}
  try:value=json.loads(raw['choices'][0]['message']['content'])
  except (KeyError,IndexError,ValueError):pass
  for msg in request.get('messages',[]):
   if msg.get('role')=='user':
    try:view=json.loads(msg['content']).get('view',{})
    except (ValueError,AttributeError):pass
  rows.append({'path':str(p.parent.relative_to(ROOT)),'phase':view.get('source_stage',view.get('phase')),'choice':value.get('choice'),'system_chars':sum(len(m.get('content','')) for m in request.get('messages',[]) if m.get('role')=='system'),'claims':len(value.get('claims',[])),'gaps':value.get('gaps',[]),'provider_error':raw.get('error'),'usage':raw.get('usage',{})})
 return rows
trace=calls(native);all_calls.extend(trace)
native_checks={'service_200':response.get('status')==200,'source434':any(x.get('id')=='article:816aee85d53f84a3b2f322dd' for x in assembly.get('context',[])),
 'both_thresholds':('3분의2' in text or '2/3' in text) and ('3분의1' in text or '1/3' in text),'claims':bool(answer.get('claims')),
 'citation_integrity':agent.get('citation_integrity')=='ORIGINAL_SPANS','within8calls':nr.get('model_calls',99)<=8}
manual=read(ART/'native-review.json') if (ART/'native-review.json').exists() else {}
native_checks.update(manual.get('checks',{}))
native_checks['no_all_subjects_required_gap']=manual.get('checks',{}).get('no_all_subjects_required_gap',False)
gold=read(ART/'grading-only.json');scores={a:[] for a in ('baseline','candidate')};case_results=[]
for case in read(ART/'cases.json'):
 row={'case_id':case['id'],'arms':{}}
 for arm in scores:
  path=ART/'trials'/case['id']/arm
  if not (path/'result.json').exists():continue
  result=read(path/'result.json');accepted=result.get('accepted',{});expected=gold[case['id']]
  claims=accepted.get('claims',[]);material=any(g.get('material') for g in accepted.get('gaps',[]))
  ct=json.dumps(claims,ensure_ascii=False).replace(' ','')
  checks={'validated':result.get('error') is None,'material':material==expected['material_required'],'claims':bool(claims) or not expected['claim_required'],'requested_terms':all(t.replace(' ','') in ct for t in expected['required_terms'])}
  passed=all(checks.values());scores[arm].append(passed);cr=calls(path);all_calls.extend(cr)
  row['arms'][arm]={'passed':passed,'checks':checks,'calls':result.get('calls'),'seconds':result.get('seconds'),'usage':result.get('usage'),'error':result.get('error'),'gaps':accepted.get('gaps',[]),'model_trace':cr}
 case_results.append(row)
stop=read(ART/'stop.json') if (ART/'stop.json').exists() else None
required=('formula-missing','comparison-missing','explicit-list-missing')
dependencies=all(all(next(r for r in case_results if r['case_id']==cid)['arms'].get('candidate',{}).get('checks',{}).get(k,False) for k in ('validated','material')) for cid in required)
native_complete=response.get('status')==200
prompt_metrics=read(ART/'assessment-instructions.json')
passed=prompt_metrics['reduction_percent']>=40 and all(native_checks.values()) and len(scores['candidate'])==5 and sum(scores['candidate'])>=4 and dependencies and not stop
summary={'status':'COMPLETE' if len(scores['candidate'])==5 else 'PARTIAL','passed':passed,'native':{'service_status':response.get('status'),'checks':native_checks,'model_calls':nr.get('model_calls'),'seconds':nr.get('seconds'),'trace':trace,'review':manual},'scores':{a:{'passed':sum(v),'total':len(v)} for a,v in scores.items()},'cases':case_results,'physical_calls':len(all_calls),'stop':stop,'contracts':{'passed':241,'initial_fixture_failures':2,'corrected_fixture_passed':2,'baseline_budget_failures':2,'candidate_budget_passed':2},'integrity':{'candidate_product_files':419,'candidate_fixture_files':5,'working_drift':drift,'selected_release_unchanged':selected_unchanged,'main_pointer_unchanged':pointer_unchanged},'prompt_constants':read(ART/'prompt-constants.json'),'main_changed_by_this_task':False,'genos_changed':False,'limits':['In-sample development probe; no MAIN qualification or legal-answer certification.','Native limits8calls/retry0/wall480 equal ADR0991, different from MAIN100 normal40calls.','One native candidate execution; no contemporaneous paired end-to-end latency comparison.','Synthetic fixed-evidence decisions check dependency behavior, not corpus retrieval quality.']}
assert len(all_calls)<=18
summary['necessary_dependency_gaps_preserved']=dependencies
summary['assessment_instruction_characters']=prompt_metrics
summary['actual_prompt_characters']=read(ART/'actual-prompt-size.json')
summary['concurrent_execution']=read(ART/'concurrent-execution-authorization.json')
summary['findings']=[
 'Native question returned source434 and both thresholds in five calls/44.27s, but material gap still expanded to other special-resolution subjects; semantic target not met.',
 'Quorum-complete: both arms invented a need to inspect possible other exceptions; candidate also sought actual member count although only the rule was requested.',
 'Comparison-missing: both arms correctly required the missing special-inspection source; candidate dropped the known seven-day regular-inspection claim, a frozen-gate regression.',
 'Formula/comparison/explicit-list necessary gaps were retained in all three candidate cases; stale excluded topic was correctly omitted in both arms.',
 'Explicit-list candidate also omitted the known first item (not a frozen claim-required gate here); preserve as an additional observed risk.',
 'Runtime original retention and budget consistency passed deterministic tests. The combined prompt/runtime package fails semantic gates and remains isolated.']
save(ART/'result.json',summary)
m=read(ADR/'실험/manifest.json');assert m['design']['success_criteria']==f['design']['success_criteria']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={a:{'status':'complete','passed_cases':sum(v),'executed_cases':len(v),'native_calls':nr.get('model_calls',0) if a=='candidate' else 0} for a,v in scores.items()},comparisons=[{'metric':'fixed-evidence adequacy','baseline':summary['scores']['baseline'],'candidate':summary['scores']['candidate']}],judge_disagreements=0,usage={'physical_calls':len(all_calls)},latency={'native_seconds':nr.get('seconds'),'paired_end_to_end':False},error_taxonomy=[] if passed else [{'kind':(stop or {}).get('reason','FROZEN_GATE_FAILURE'),'result_path':str((ART/'result.json').relative_to(ROOT))}])
front=(ADR/'README.md').read_text().split('---',2)[1]
if len(scores['candidate'])==5 and not passed:front=front.replace('status: Proposed','status: Rejected')
parts=[f'격리 후보의 프롬프트와 실행 코드 수정. 계약241통과; 실제 요청{len(all_calls)}회. 기준 통과={passed}. MAIN100 변경 없음.',
 '기존 ASSESS는 남은 조사1회에도 재진입하지만 탐색은2회를 요구했다. 중단 경로는 이전 ASSESS에 전달한 확보 원문을 회수하지 못했다. 같은 모의 API2사례에서 기준 모두실패/후보 모두통과. 활성4단계 중복 지시를 정리하고 의미·범위·근거 계약을 유지했다.',
 m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling']+'\n\n'+m['design']['failure_recovery']['experiment_dispatch'],
 'Qwen3.8 / qwen/qwen3.8-27b, Parasail FP8 only, reasoning none, fallback false. 후보419제품파일+5계약fixture를 동결했다. 같은 원문으로 두 프롬프트를 비교하며 채점 정답은 제품 입력에서 제외했다.',
 json.dumps({'native':summary['native'],'scores':summary['scores']},ensure_ascii=False,indent=2),
 '\n\n'.join(summary['findings'])+'\n\n[각 사례 결과](artifacts/result.json). 최초 계약2실패는 이전 fixture의 team_id=t가 현행 권한 입력에 맞지 않아 발생했다. test_team으로 교정한 별도 fixture2검사를 통과했으며 최초 실패는 보존했다.',
 f'실제 모델 요청{len(all_calls)}회. 원래 질문 서비스 구간{nr.get("seconds")}초, 응답상태{response.get("status")}. 회수 구현·데이터 불변. 입력량·사용량·개별 지연은 원시 기록과 result.json에 보존; 과거 실행과 속도 우열을 확정하지 않는다.',
 '실행 수정은 원문을 보존하고 무의미한 예산 재진입을 막는다. 충분성과 추가 조사 필요성은 기존 모델 호출 안에서 판단하며 새 평가 호출은 추가하지 않았다. 프롬프트 단축과 판단 개선의 인과는 이 작은 표본 범위를 넘지 않는다.',
 '\n\n'.join(summary['limits']),
 '작업은 격리 후보에 보존. 제품 MAIN 승격·GENOS 반입·Git commit/push는 수행하지 않았다. 선택 포인터와 코드의 최종 동일성은 result.json의 integrity에서 확인한다. 후속 수정·모델 재실행은 새 ADR로 시작한다.',
 '06_TOOLS/EXPERIMENTS/adr_0992/guard.py (동결된 단일 실행; 기존 산출물 재실행 금지). [사전 동결](artifacts/design-freeze.json) · [결과](artifacts/result.json).']
(ADR/'README.md').write_text('---'+front+'---\n\n# 프롬프트 정리와 확보 원문 보존\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
index=[]
for row in m['questions']:
 cid=row['case_id'];dirs=[native] if cid=='known-special-resolution' else [ART/'trials'/cid/a for a in scores]
 links=[]
 for folder in dirs:
  for p in sorted(folder.glob('model/call-*/*.json')):links.append(f'[{p.relative_to(folder)}](../artifacts/{p.relative_to(ART)})')
 case=read(ART/'known-request.json') if cid=='known-special-resolution' else next(c for c in read(ART/'cases.json') if c['id']==cid)
 values=['run-001; original candidate once or fixed-evidence paired decisions.',json.dumps(case,ensure_ascii=False,indent=2),m['design']['success_criteria'],'[Frozen source/code/model/runner](../artifacts/design-freeze.json).','Native reads preserved in exact model payloads; synthetic decisions use fixed originals.','\n\n'.join(links) or 'Not dispatched because persistent experiment stop was recorded.','No new product model stage; no evaluator request.','Offline frozen exact expected materiality and required source details; grading-only is never product input.','[Case result](../artifacts/result.json).']
 p=ADR/'실험'/row['file'];p.write_text('# '+cid+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)));row['sha256']=sha(p);index.append(f'- [{cid}]({row["file"]})')
(ADR/'실험/README.md').write_text('# 사례\n\n'+'\n'.join(index)+'\n');save(ADR/'실험/manifest.json',m)
files=[]
for p in sorted(ART.rglob('*')):
 if p.is_file() and p!=ART/'manifest.json' and 'runtime' not in p.relative_to(ART).parts:files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen input, native/probe output, contract or result record','contains_raw_prompts_and_outputs':'model' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0992','files':files})
(ADR/'RESULT.txt').write_text(f'프롬프트·확보 원문 보존 후보: 계약241통과. 모델요청{len(all_calls)}회.\n원래 상법 질문: 서비스{response.get("status")}, {nr.get("model_calls")}회, {nr.get("seconds")}초.\n합성5사례: {summary["scores"]}. 전체 사전기준 {passed}.\nMAIN100/GENOS 변경 없음. 인샘플 후보이며 MAIN 승격 근거로 사용하지 않음.\n')
print(json.dumps({k:summary[k] for k in ('status','passed','scores','physical_calls','stop','integrity')},ensure_ascii=False))
