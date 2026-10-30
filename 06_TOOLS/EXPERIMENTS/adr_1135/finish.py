from common import *
import subprocess,statistics
x=read(ART/'run-001/result.json');m=read(ADR/'실험/manifest.json');n=x['native']
summary='동일4질문 실제 선택은3/4로 이전과 같았다. 성립 질문은PATH1만 선택하고 충분하다고 판단했다. 미지원 전환사채 질문은NO_MATCH+ANSWER 충돌을1회 보완 후에도 반복했으나 서버가 기존 SELECT로 복귀시켜 최종2항목 답변까지 완료했다. 새모델12회, MAIN107 불변.'
report='''온톨로지 충분성·복수 선택·기존 탐색 — 실제 모델 실험 ADR1135

결론
기존 네 질문의 선택 결과는3/4로 이전과 같다. 성립 질문에서 두 경로 선택 누락은 해결되지 않았다. 모델이 “충분하다/ANSWER”로 판단해 의미 재선택은 발생하지 않았다.
별도 실제 서비스 질문에서는 온톨로지 경로 없음의 다음 행동을 모델이 잘못 제출했으나, 서버가 기존 탐색으로 복귀시켜 최종 답변까지 완료했다. 선택 판단 개선과 복구 경로 작동을 구분한다. 전체 사전 성공 기준은 미달이다.

동일 네 질문 — 같은 보관 원문120옵션,5경로,각1호출
- 성립 요건 CM023: PATH1, ANSWER. 사전 기대 PATH1+PATH2에 미달.
- 가액 하락 환급: PATH3, ANSWER. 통과.
- 기준금액 미달: PATH2, ANSWER. 통과.
- 무관한 대출 연체이자: 빈 경로, NO_MATCH, SEARCH. 통과. 이 단독 선택 실험은 SEARCH 요청에서 끝나며 실제 검색을 실행했다고 세지 않는다.
프롬프트는1134의374문자 그대로, 제품662파일도1134와 동일하다. 기존1133 실험을 소급 수정하지 않았다. 앞선3답변의 본문은 저장 시나리오와 일치하며 원문120옵션도 동일하다.

미지원 전환사채 질문 — 신규 실제 검색부터 native HTTP 실행
질문: 상속세 및 증여세법 제41조의3에서 전환사채를 받은 뒤 정산기준일까지 주식으로 전환하지 않은 경우, 증여세 정산과 이후 만기까지 미전환 시 환급은 어떻게 처리하나요?
이 사례는 이전 응답을 재생하지 않고 request-entry부터 새 모델을 호출했다. 당시 확보 원문에 결속된 경로는PATH4(혼재재산 추정)·PATH5(담보 차입 간주)2개였고, 해당 전환사채 업무 경로는 없었다.

실제8호출 순서
1. 질문을 정산/환급 두 쟁점으로 나누고 검색을 시작했다.
2. 원문을 읽어 온톨로지 선택에 진입했다.
3. 모델은 두 쟁점 모두 “맞는 경로가 없다/NO_MATCH”라고 했지만 next_action=ANSWER, missing_scope=[]를 제출했다.
4. NO_MATCH는 SEARCH여야 한다는 보완 요청에도 같은 충돌을 반복했다. 실제 전송 스키마는ANSWER/RESELECT/SEARCH 모두 허용했다.
5. 서버가 실패를 채택하지 않고 SCENARIO_CHOICE_UNRESOLVED로 기록한 뒤 기존 SELECT로 복귀했다. 모델은 FOLLOW_CONNECTION으로 연결 범위를 조사했다.
6. 기존 확보 원문으로 충분하다고 판단하고 FINISH했다.
7. 일반 ASSESS가 정산과 환급에 관한2개 claim을 생성했다.
8. 기존 COMPOSE가 최종 문장을 작성했고 HTTP200/READY, ANSWER/COVERED로 완료했다.
이 복귀 뒤 신규 UNIT_READ_CHOICE는0회다. 연결 범위를 조사하고 이미 확보한 원문을 재검토한 것이며 “복귀 후 새 조문을 추가로 읽었다”고 설명하지 않는다.

최종 답변의 내용
정산기준일까지 미전환이면 해당 기준일에 전환된 것으로 보아 규정을 적용해 정산한다는 내용과, 만기까지 미전환이면 정산기준일 기준 과세액을 환급한다는 내용이 반환됐다. 실제 문장은 run-001/scenario/scenario-uncovered/answer.txt에 보존했다. 두 claim의 인용은 보관 원문의 제41조의3에 연결됐다.
이는 해당 두 요구에 관한 반환 내용 확인이며 독립 법률 정답 인증은 아니다. 일반 RAG의 구조화 답변에는 환급 claim의 norm kind=PERMISSION이 남아 있어 의미 분류를 완전 검증했다고 하지 않는다.

무엇을 확인했나
- 실제 모델의 복수 선택 오류는 남았다.
- 모델이 스스로 RESELECT를 선택한 사례는0이다. 의미 재선택의 실모델 성공은 이번에 확인하지 못했다.
- NO_MATCH를 인식해도 next_action과 충돌할 수 있다. 형식/필드 충돌 보완1회와 의미 재선택1회는 다른 절차다.
- 충돌 후 기존 탐색 복귀와 일반 원문 답변 발행은 실제 실행에서 작동했다. 서버의 복구 결과를 모델의 올바른 SEARCH 선택으로 계산하지 않는다.
- 기존 단독 시나리오 답변에서는 재작성 모델0이다. 이번 native 사례는 일반 RAG로 돌아갔으므로 COMPOSE1회가 실행됐다.

원문·상태·비용
총 신규 모델12회(단독4+native8), 평가0. Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음 / 실제 출력상한 필드0.
입력254,895토큰·출력6,050토큰·비용$0.0744848.
단독 선택은 질문당 약4.1만 입력 토큰을 유지했다. 프롬프트 문구 감소를 전체 컨텍스트 감소로 설명하지 않는다. native 공통 어댑터 안내는 기존대로 추가되며374문자는 선택 전용 안내만의 길이다.
native HTTP 요청100.118초, 새 모델8회 전송합68.570초, 앱 준비2.504초(요청 밖). 이전 실행과 조건이 달라 전체 속도 개선율을 계산하지 않는다. 관찰 최대RSS3,337,796KiB, 실행은 하나씩 순차 진행했다.
native51근거 receipt/83span 관찰에서 원문 불일치0·권한범위 위반0. 반복 관찰을 독립83원문으로 세지 않는다. 실제 전송-저장 입력·ASSESS 원문·시나리오 본문 불일치0.
최종 인용 좌표는 단독 질문별2/2/2/0, native1개. 평가 좌표 포함은 법률 의미 정확도와 별개다.
응답 완료 뒤 wiki.projection_pending 로그1건이 남아 후속 지식 투영 완료까지 주장하지 않는다.

적용 상태
1134의157합성검사는 동일662제품파일 해시로 상속했다. 이번 새157검사로 다시 세지 않는다. 후보·모델·입출력·복구 이벤트·최종 답변을 저장했다. 선택MAIN107·GENOS·Dataiku/S3/Oracle 운영 게시 변경 없음.
사전 전체 기준 미달로 Rejected/decision_eligible=false/quality_certified=false로 종료한다. 추가 프롬프트나 제품 수정·재호출은 하지 않았다. 전역 계보 검사의 과거9오류와 신규 실험 결과는 completion-audit.json에서 구분한다.
'''
(ART/'실험결과.txt').write_text(report)
m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','reason':'Historical1133/1134 only'},'scenario':{'status':'complete','direct_route_passed':3,'direct_route_total':4,'native_recovery_pass':True,'native_model_next_action_valid':False,'primary_pass':False,'quality_certified':False,'decision_eligible':False}},comparisons=[{'paired':False,'historical_route_score':'1133 3/4;1135 3/4; no causal quality improvement claim'}],usage={**x['usage'],'new_model_calls':12,'new_evaluator_calls':0},latency={'direct_seconds':[c['seconds'] for c in x['direct']],'native_http_seconds':n['seconds'],'native_model_transport_seconds':n['model_transport_seconds'],'application_prepare_seconds':n['application_prepare_seconds'],'scopes_not_combined':True},error_taxonomy=[{'type':'required_issue_omission','count':1,'denominator':4,'detail':'CM023 missing PATH2 under frozen route rubric; final legal error not independently certified'},{'type':'other','count':2,'denominator':2,'detail':'Native selector NO_MATCH + ANSWER persisted through one schema correction; server fallback recovered'},{'type':'other','count':1,'detail':'wiki projection pending after response; downstream knowledge completion not asserted'}]);m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'))
counts=[len(c['final_cited']) for c in x['direct']]+[len(n['final_cited'])];ra=m['retrieval_accounting']
for k,v in {'before_filter':42,'after_filter':sum(counts),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':1.0,'selectivity':statistics.mean(counts)/ra['corpus_total']}.items():ra[k]={'scenario':v}
ra['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json');put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[summary,'1134는 짧은 복수 선택·충분성·재선택1회·기존SELECT 복귀를 합성157검사로 확인했다. 이번에는 제품을 바꾸지 않고 실제 모델을 실행했다.','[사전 동결](artifacts/criteria.json), [기대 경로](artifacts/rubric.json). 동일4질문 선택 모두 성공, 미지원 질문의 실제 모델 SEARCH/복귀/최종 인용을 요구했다. 사후 기준 변경 없음.','단일scenario arm.4보관 원문 선택→1신규native HTTP 순차 실행. 역사baseline 미실행. 신규native는 prefix재생0, 보완은 기존계약만 사용.','1134와662파일 동일. [동결](artifacts/freeze.json).1133의5경로 동일, CM023 알려진 질문+작성한 업무 질문4. Qwen3.8 Parasail FP8 reasoning none 출력상한 없음. 기준답변은 제품 입력 비공개.','단독 경로3/4. nativeHTTP200/READY·ANSWER/COVERED·claim2. 모델 NO_MATCH+ANSWER 오류2회 뒤 서버 복구로SELECT1회. 의미 재선택 관찰0. [상세](artifacts/실험결과.txt).','CM023은PATH1만 선택해 기대PATH2누락. native모델 다음행동 충돌은 보완에도 반복. 서버가 거절하고 복귀해 응답은 완료했다. 일반RAG 환급 PERMISSION분류와 wiki.projection_pending은 법률품질/후속투영 미인증 범위로 남겼다.','총12모델·평가0·입력254895/출력6050토큰·$0.0744848. native100.118초(모델68.570초), 단독구간과 합산비교하지 않는다.\n\n### 단계별 회수·탈락 원장\n\n[원장](artifacts/retrieval-ledger.json): case+조문 좌표42→42→7, 최종평균1.4/p50 2/p95 2. 기대좌표7/7은 법률 정확도 아님. 단독120원문옵션·native51receipt/83span관찰을 구분한다. 원문/권한/전송 불일치0.','복수 선택·충분성 안내만으로 누락을 교정하지 못했다. 반면 온톨로지 선택 실패를 기존 조사로 넘기는 제어는 실제 실행에서 작동했다. 복구 성공을 모델 선택 정확도로 세지 않는다.','인샘플·표본5·단독4와native1의 다른 실행범위. 의미재선택 실제 성공 미관찰. 기준금액 제외가PATH1에도 있는 점은 기존 평가 경로 중복 문제이며 사전3/4를 바꾸지 않는다. 독립 법률인증·전체속도개선·후속위키완료 아님.','Rejected, MAIN107·GENOS·데이터 운영 게시 변경 없음.1134 제품/프롬프트 수정0. 기존결과보존.','`06_TOOLS/EXPERIMENTS/adr_1135/direct.py`, `native.py`: 완료실행 덮어쓰기 금지. 읽기전용 `source_audit.py scenario`, `wire_audit.py scenario`, `report.py`. [산출물](artifacts/manifest.json) · [질문](실험/README.md).']
head=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected');(ADR/'README.md').write_text('---'+head+'---\n\n# 온톨로지 선택·충분성 실제 모델 실험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 c=next(v for v in read(ART/'cases.json') if v['id']==q['case_id']);r=next((v for v in x['direct'] if v['case_id']==q['case_id']),n);base='../artifacts/run-001/scenario/'+q['case_id'];native=c['mode']=='native_http_fresh'
 sections=[f"run-001/scenario, {c['mode']}, 실제 {r['calls']}호출, Qwen3.8.",c['question'],'[사전 기대 경로](../artifacts/rubric.json). 제품 입력 비공개. 원문·좌표 대조는 선택 후 수행, 독립 승인 법률 정답 없음.',f"[실제 입력]({base}/canonical) 및 [wire]({base}/wire)." if native else f"[실제 입력]({base}/input-1.json).",f'[실제 요청·응답·사용량]({base}/raw) · [최종 답변 또는 SEARCH요청 표시]({base}/answer.txt).', '선택 보완1회·서버복귀·일반 ASSESS/COMPOSE. 첫 응답 재생0.' if native else '선택1회. 컴파일/COMPOSE/평가 모델0. SEARCH선택은 이 셀에서 실행하지 않는다.', '평가모델0. 경로ID·단계전환·원문·최종출처 대조. [실행 결과](../artifacts/run-001/result.json).', '복구와2항목응답 통과, 모델다음행동은실패. 의미재선택미관찰.' if native else f"선택{r['selected_paths']}, {r['effective_action']}, 사전기준통과={r['route_pass']}."]
 sections[3]+='\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/retrieval-ledger.json): 원문→ASSESS전달→최종 인용. 골드는 선택 뒤 결합.'
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(zip(qh,sections),1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 모델5질문\n\n'+summary+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
idx=ROOT/'04_EXPERIMENTS/ADR/README.md';s=idx.read_text();line='- [ADR1135 온톨로지 실제 선택·탐색 복귀](ADR-1135-scenario-sufficiency-live/README.md) — 동일4질문3/4, 추가native질문은선택충돌뒤서버복구로최종2항목답변. 새모델12·MAIN107불변.\n'
if 'ADR1135 온톨로지 실제' not in s:idx.write_text(s.replace('# ADR workspace\n','# ADR workspace\n\n'+line,1))
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary)]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],capture_output=True,text=True);(ART/f'{args[0]}-final.txt').write_text(r.stdout+r.stderr);print(args[0],r.returncode)
