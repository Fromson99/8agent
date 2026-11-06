from common import *
import tarfile
baseline=read(DES/'baseline.json');candidate=read(DES/'candidate-selected.json');C=ROOT/candidate['code_root']
assert all(sha(C/n)==h for n,h in candidate['selected_files'].items())
assert all(sha(ROOT/baseline['release']['code_root']/n)==h for n,h in baseline['release']['files'].items())
cells=[];allcalls=[]
for case in read(DES/'live-cases.json'):
 base=ART/'public-live'/(case['id']+'-selected-host-r5')
 if not (base/'result.json').exists():
  cells.append({'case_id':case['id'],'executed':False,'reason':'not run after stop'});continue
 calls=read(base/'calls.json') if (base/'calls.json').exists() else [];allcalls+=calls
 result=read(base/'result.json')['turns'][0];response=read(base/'turn-1/response.json.gz')['body'];agent=(response.get('assembly') or {}).get('term_agent') or {}
 text=(base/'turn-1/public-answer.txt').read_text() if (base/'turn-1/public-answer.txt').exists() else (response.get('message') or '')
 cells.append({**result,'executed_trial':True,'public_answer':text,'source_reply_contract':agent.get('source_reply_contract'),'context_count':len((response.get('assembly') or {}).get('context') or []),'answer_coverage':agent.get('answer_coverage'),'stop_reason':agent.get('stop_reason')})
 paths=[p for p in (base/'runtime').rglob('*') if p.is_file()]
 ref=write_raw_json(base/'runtime-files-sha256.json.gz',[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(paths)])
usage={'physical_calls':len(allcalls),'normal':sum(c['status']=='responded' and c.get('http_status')==200 for c in allcalls),'unknown':sum(c['status']=='unknown' for c in allcalls),'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in allcalls),'reported_tokens':sum((c.get('usage') or {}).get('total_tokens',0) for c in allcalls),'replay':0,'grader_calls':0,'automatic_retry_after_unknown':0}
audit=read(ART/'source-wire-audit.json')
assert all(a['budget_matches'] and not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches')) for a in audit['cells'])
report={'scope':'Final source-only presentation only, MAIN150 backend unchanged; CM exact-question host authorization; Risk excluded by prompt/task guidance','changes':read(DES/'changes.json'),'cells':cells,'usage':usage,'source_audit':audit,'tests':{'passed':40,'failed':3,'all_three_also_before':True,'notes':'3 existing chatId/old multiturn fixture failures; missing test-path and initial baseline loader-path failures retained'},'main_promoted':False,'genos_deployed':False,'quality_certified':False,'current_main':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')}
put(ART/'result.json',report)
lines=['설명 먼저·불확실성 마지막 — 실제 CM/Qwen 결과','', '변경: 최종 표시 한 파일. 확인한 원문의 안내 → 마지막 적용 불확실성과 추가 정보 질문. 검색·판단·프롬프트·원문·정상 답변 유지.', '기존 financial CM012·003만 실행. Risk CM은 최신 AGENTS 태그/작업 지침으로 로컬 시험에서 제외. 자동 질문별 서비스 차단 없음.','']
for c in cells:
 lines.extend([c['case_id'],json.dumps({k:v for k,v in c.items() if k not in ('public_answer','step')},ensure_ascii=False),'실제 표시문:',c.get('public_answer','미실행'),''])
lines.extend(['호출·비용: '+json.dumps(usage,ensure_ascii=False),'표시 검사40통과/기존3실패, 동일 실패는 수정 전 표시에서도 재현. 초기 실행기 권한/스코프 실패는 외부호출0으로 모두 보존.','최종 답변에 도달하지 못한 경우 새로운 표시 형식의 실모델 통과로 계산하지 않는다. 선택 MAIN 승격/GENOS 현장 적용 없음.'])
(ART/'실제_CM_답변.txt').write_text('\n'.join(lines)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'explanation':report},comparisons=[],judge_disagreements=0,usage=usage,latency={'request_seconds':[c.get('request_seconds') for c in cells]},error_taxonomy={'initial_runner_failures_external_calls':0,'existing_contract_failures':3,'live_statuses':[c.get('status') for c in cells]})
for arm in m['design']['arms']:arm.update(changes='Completed MAIN150 reference, not rerun' if arm['id']=='baseline' else 'Final display only, one workflow file; current backend byte-identical',controls='Same MAIN150 profile/model/source and bounded host CM/public-source authorization')
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
content=['최종 표시 한 파일 수정. 실제 결과는 artifacts/실제_CM_답변.txt. 작업 코드만 변경하며 MAIN150은 유지한다.','자료와 판단 연결이 미완료인 응답에 내부 검토 목록과 중복 실패가 노출되고, 첫 안내가 미확정 선언으로 시작했다.',json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'CM012 다음003 한 번씩. 실제 root service에서 동결된 표시 후보를 선택하며, 나머지529파일은 MAIN150 동일. 기존 CM 승인과 현재 financial 공개 원문 교집합으로 host 권한을 제한한다. 질문을 public으로 표시하지 않고 빈 세션만 사용한다.','CM source sha와 후보530파일·모델 정책은 design에 동결. Qwen3.8 Parasail FP8/none·출력상한 없음. 기존 확인된429만 원래 정책의 NearAI1회 전환. 정답·좌표 입력0.','[실제 표시문과 결과](artifacts/실제_CM_답변.txt)',json.dumps([{k:c.get(k) for k in ('case_id','http_status','status','answer_coverage','stop_reason','claims','context_count','physical_calls')} for c in cells],ensure_ascii=False),json.dumps(usage,ensure_ascii=False),'원문 안내 순서의 계약 검사와 실제 모델의 완성 답변 여부를 구분한다. 잘못된 과거 판단을 요약 답변으로 전환하지 않는다.','인샘플 2질문·각1회. 읽은 원문이 없는 CLARIFY/전송실패는 원문 기반 최종 표시 시험이 아니다. 초기 host 권한 연결 실패는 모두 모델0이며 보존. 실제 현장/일반 법률 품질 인증 아님.','작업 표시 변경만 유지·MAIN 승격0. Risk CM은 태그와 작업 지침만 적용한다. 저장 답변·원문/ACL·검토 판단은 불변.','setup.py → preflight host-r5 → live.py cm-012 --host-r5 → live.py cm-003 --host-r5 → audit.py → ledger.py → finish.py. 실험 결과는 덮어쓰거나 동일 요청을 자동 재실행하지 않는다.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 기존 CM 실제 Qwen과 설명 우선 표시\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,content),1))+'\n')
for q,c in zip(m['questions'],cells):
 p=ADR/'실험'/q['file'];s=p.read_text();s=s.replace('실행 전 동결.',c.get('public_answer','미실행')+'\n\n'+json.dumps({k:c.get(k) for k in ('http_status','status','physical_calls','claims','context_count')},ensure_ascii=False));s=s.replace('MAIN150 동일530','MAIN150 백엔드 동일529+표시1');p.write_text(s)
(ADR/'실험/README.md').write_text('# 실제 질문\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'};paths.update(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1409','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Actual CM Qwen or preserved local failed preflight, exact sources and contract checks','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts)} for p in sorted(paths)]})
print(json.dumps({'cells':[{k:c.get(k) for k in ('case_id','http_status','status','claims','context_count')} for c in cells],'usage':usage},ensure_ascii=False))
