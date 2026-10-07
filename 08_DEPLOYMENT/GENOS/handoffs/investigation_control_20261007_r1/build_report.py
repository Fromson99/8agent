"""Summarize immutable public experiment outputs, without another evaluator call."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,statistics
R=Path(__file__).resolve().parents[4];O=Path(__file__).resolve().parent
A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result=read(A/'artifacts/run-001/result.json');dataset=read(A/'artifacts/design/dataset.json')
questions={q['case_id']:q['question'] for q in dataset['cases']+dataset['regression_cases']}
rows=result['by_arm']['integrated']['cases'];kst=timezone(timedelta(hours=9))
def dur(s):
 s=round(s);return f'{s//3600}시간 {(s%3600)//60}분 {s%60}초' if s>=3600 else f'{s//60}분 {s%60}초'
def when(t):return datetime.fromisoformat(t.replace('Z','+00:00')).astimezone(kst).strftime('%Y-%m-%d %H:%M:%S KST')
manifest=read(A/'실험/manifest.json');start=manifest['reservation']['created_at'];end=manifest['reservation']['completed_at']
delta=(datetime.fromisoformat(end.replace('Z','+00:00'))-datetime.fromisoformat(start.replace('Z','+00:00'))).total_seconds()
smoke=read(A/'artifacts/main-smoke.json');smoke_events=[]
for line in (A/'artifacts/main-smoke.log').read_text().splitlines():
 try:x=json.loads(line)
 except ValueError:continue
 if x.get('api_type')=='RAG_ASK' and x.get('event')=='request.finished' and x.get('http_status')==200:smoke_events.append(x)
assert len(smoke_events)==1
main_at=smoke_events[0]['ts'];elapsed_to_main=(datetime.fromisoformat(main_at)-datetime.fromisoformat(start.replace('Z','+00:00'))).total_seconds()
issue_notes={
 'NG02':'목표 조문에 바로 도달하지 못하고 페이지 탐색을 반복해 37회 모델 시도 예산을 소진했다.',
 'NG05':'다른 조문 확보를 READ_PARENT로 시도했다. 현재 메뉴에 없는 선택 ID 및 읽기/보류 조합을 계약이 거절했다.',
 'NG13':'모델이 원문과 정확히 일치하지 않는 인용을 제출해 게시 전 차단됐다. 오답을 게시한 사례와 구분한다.',
 'IC16':'넓은 권리 목록 질문에서 탐색·읽기가 반복되어 37회 모델 시도 예산을 소진했다.',
 'IC22':'전달된 원문과 쟁점에 결속되지 않은 근거 채택을 제안해 거절됐다.',
 'IC23':'제정 주체와 회사의 작성 의무는 설명했으나 구체 적용 범위의 시행령 근거를 확보하지 못했다. 자동 judge는 불완전으로 판정했다. 실제 답변에는 회사의 일반 의무와 대통령령 위임이 이미 명시되어 있어 평가 이유 일부는 논쟁적이다. 원래 판정은 변경하지 않았다.',
 'IC24':'감독기관의 제11조 자료제출 요구를 찾아야 하는 질문에서 제36조 제5항의 정정·삭제 관련 증거자료 제출만 골라 주체/대상을 좁혔다. 해당 조문 내용 자체보다 질문 의도에 맞는 근거 선택이 문제다.',
 'IC25':'모델 단일 전송 실패로 답변을 만들지 못했다. 정의 판단의 오답으로 집계하지 않는다.',
 'IC28':'기본 정의·선택 대우는 설명했으나 장외파생상품의 서면 통지 부재를 거래 제한 가능성으로 확장했다. 원문에 없는 효과다. 자동 judge의 개인 제외 대상 관련 이유는 실제 답변에도 외국인인 개인이 명시되어 있어 일부 논쟁적이며 원래 판정은 보존했다.'}
def label(x):return '정답(자동 평가)' if x['correct'] else ('판단 오류(자동 평가)' if x['http_status']==200 else '미답변')
text=['조사 제어 통합: 맞은 문제·틀린 문제·시간·GENOS 반입 요약','',
 '1. 무엇을 구현했나',
 '법령별 검색·요청 단위 우선 정렬, 확보/전달/채택 근거 범위, 쟁점별 충분성·미확인 gaps, 번호가 있는 행동/이유 체인, 저장 원문 재열람, RETURN_TO와 제한된 재진입을 기존 v6·AD·shortcut·wiki·SQL·NFS·서비스 경로에 통합했다.',
 f'현재 로컬 MAIN: {smoke["pointer"]["release_id"]}, 활성 포인터 generation 43. 서빙 265개 파일이 동결 후보·작업 코드·선택 릴리스에서 같은 해시다. 실제 service.service 질의는 HTTP 200이었다.',
 '', '2. 결과를 어떻게 해석하나',
 '독립 질문 32개: 정상 응답 26개(81.25%), 자동 평가 정답 23개(71.875%), 판단 오류 3개, 미답변 6개. 정상 응답 중 자동 정답은 23/26(88.46%)다.',
 '회귀 질문 8개: 정상 응답 7개, 모델 제안 거절로 미답변 1개. 회귀 정상 응답 건수를 정답률로 바꾸지 않는다.',
 '계약 검사 146개 통과. 구 READ+DEFER 기대를 사용한 과거 검사 5개는 명시 제외했으며, 현재 선택 계약 검사는 모두 포함했다. 저장 압축 검증 48개 통과. 계약 통과가 법률 의미 전체의 정답 인증은 아니다.',
 '자동 judge 1회의 원문 기반 평가이며 전문가 인증이나 GENOS 내부 모델 성능이 아니다. IC23과 IC28의 자동 평가 설명에는 실제 답변과 맞지 않는 일부 이유가 있어 아래에 구분했다. 원래 23/32 판정·결과·등급은 재채점하거나 고치지 않았다.',
 '', '3. 얼마나 걸렸나',
 f'ADR0677 준비·실험·채점·정리·최종 검증의 경과: {when(start)} → {when(end)}, {dur(delta)}.',
 f'ADR0677 예약부터 실제 MAIN 서비스 질의 성공까지: {when(main_at)}, {dur(elapsed_to_main)}. 이후 서비스 프로필 차이 감사와 문서 기록을 추가했다.',
 f'독립 질문의 end-to-end 처리: 중앙값 {dur(result["by_arm"]["integrated"]["latency"]["request_p50"])}, p95 {dur(result["by_arm"]["integrated"]["latency"]["request_p95"])}, 최장 {dur(max(x["request_seconds"] for x in rows))}.',
 f'독립 질문 32개 요청 시간을 합하면 {dur(sum(x["request_seconds"] for x in rows))}; 병렬 실행 시간의 합이므로 실제 벽시계 경과와 다르다.',
 f'독립 질문 모델 통신 시간의 합은 {dur(result["by_arm"]["integrated"]["usage"]["seconds"])}다. 모델 호출·검색·SQLite·검증을 포함한 end-to-end 시간과 구분한다.',
 f'실제 MAIN 확인 질의: {dur(smoke_events[0]["duration_ms"]/1000)}, 모델 호출 {smoke["model_calls"]}회.',
 'GENOS의 내부 모델·데이터·NFS 조건에서는 시간이 달라지므로 현장 시간은 미측정이다.',
 '', '4. 독립 질문 32개 전수 표',
 'ID | 판정 | 요청 시간 | 모델 호출 | 질문']
records=[]
for x in rows:
 cid=x['case_id'];raw=read(A/f'artifacts/run-001/integrated/{cid}/result.json');answer=raw.get('output',{}).get('answer',{}).get('text','')
 note=issue_notes.get(cid,x.get('grading_reason',''))
 text.append(f'{cid} | {label(x)} | {dur(x["request_seconds"])} | {x["model_calls"]} | {questions[cid]}')
 records.append({'case_id':cid,'question':questions[cid],'classification':label(x),'http_status':x['http_status'],'request_seconds':x['request_seconds'],'model_calls':x['model_calls'],'answer':answer,'review_note':note,'original_grading_reason':x['grading_reason'],'result_path':str((A/f'artifacts/run-001/integrated/{cid}/result.json').relative_to(R)),'result_sha256':sha(A/f'artifacts/run-001/integrated/{cid}/result.json')})
text+=['','5. 판단 오류 3개와 미답변 6개의 원인']
for cid,note in issue_notes.items():text.append(f'{cid}: {note}')
text+=['','6. 회귀 질문 8개 전수','ID | 결과 | 요청 시간 | 모델 호출 | 질문']
regrecords=[]
for x in result['regressions']:
 raw=read(R/x['result_path']);sec=raw['request_seconds'];answer=raw.get('output',{}).get('answer',{}).get('text','')
 text.append(f'{x["case_id"]} | HTTP {x["http_status"]} | {dur(sec)} | {x["model_calls"]} | {questions[x["case_id"]]}')
 regrecords.append({'case_id':x['case_id'],'question':questions[x['case_id']],'http_status':x['http_status'],'request_seconds':sec,'model_calls':x['model_calls'],'error':x['error'],'answer':answer,'result_sha256':x['result_sha256']})
text+=['REG-cm-039는 같은 fulltext 표현을 새 검색으로 다시 제출해 모델 제안이 거절됐다. 결과를 성공으로 고치거나 재시도하지 않았다.',
 '', '7. 실제 MAIN 확인 답변에서 발견한 추가 오류',
 '대표이사 선정의 핵심 답은 전달된 제389조 제1항에 맞았다. 다만 질문 밖의 설명을 덧붙이며 “유한회사(제270조)”라고 썼다. 선택 원문에서 제270조의 주체는 합자회사이고 제목은 정관의 절대적 기재사항이다. 추가 회사 유형/조문 연결 오류다. 이 서비스 확인은 독립 질문의 추가 정답이나 재실험으로 합산하지 않았다.',
 '평가 실행 프로필과 서비스 실행 프로필은 전송 재시도 횟수 1회→0회 보정 한 항목이 다르다. 동결 서비스 팩터리에도 같은 보정이 있었고 실제 실행 지문과 일치했다. 원래 평가 지문은 보존했다.',
 '', '8. 다음 개선 대상으로 확인한 문제',
 '같은 자료·부모 범위를 반복 읽는 대신 목표 조문 재검색/저장 자료 재열람을 고르는 일반화, 여러 조문에 걸친 넓은 질문의 쟁점 유지, 감독 주체와 정보주체 등 질문 의도에 맞는 자료 선택, 최종 문장에서 요청 밖의 설명·원문 밖의 법적 효과를 덧붙이는 문제다. 이번 인계본에 이 후속 개선의 효과를 이미 확인한 것으로 쓰지 않는다.',
 '', '9. 저장공간·반입·현장 상태',
 '원문 데이터 세대 복사 없이 선택 경로를 재사용했다. 동일 캐시 공유와 종료한 DB의 무손실 압축으로 WSL 약 18GiB를 줄였으며 Windows C: 물리 공간은 아직 회수하지 않았다.',
 '메일에는 코드 ZIP·독립 실행 TXT·워크플로우 전체 TXT·이 보고서를 첨부한다. JS·DB·원문 데이터·환경 키를 포함하지 않는다. GENOS에서는 기존 ~/DEV에 백업 후 적용하고 기존 generation을 검증한다.',
 '로컬 MAIN 반영/메일 발송과 GENOS 코드 적용·세대 검증·Git push·코드서빙 리비전 배포·워크플로우 편집·실제 내부 질의 성공은 별도다. 현장 단계는 미수행이다.',
 '', '10. 실제 답변 및 원래 자동 평가 이유 전수']
for x in records:
 text+=['',f'[{x["case_id"]}] {x["question"]}',f'판정: {x["classification"]}, HTTP {x["http_status"]}, {dur(x["request_seconds"])}', '실제 답변:',x['answer'] or '(최종 답변 없음)', '정리:',x['review_note'], '원래 자동 평가 이유:',x['original_grading_reason']]
text+=['','11. 회귀 질문 실제 답변 전수']
for x in regrecords:text+=['',f'[{x["case_id"]}] {x["question"]}',f'HTTP {x["http_status"]}, {dur(x["request_seconds"])}',x['answer'] or '(최종 답변 없음)',f'오류: {x["error"]}' if x['error'] else '근거·상태 연결 검사 통과. 별도 의미 재채점은 하지 않았다.']
(O/'EXPERIMENT_RESULTS_UTF8.txt').write_text('\n'.join(text)+'\n')
audit={'source_experiment':'ADR-0677','source_result_sha256':sha(A/'artifacts/run-001/result.json'),'no_model_calls_or_regrade':True,'primary':records,'regressions':regrecords,'timing':{'adr_reserved_at':start,'adr_completed_at':end,'preparation_experiment_review_seconds':delta,'actual_main_service_success_at':main_at,'elapsed_to_actual_main_service_seconds':elapsed_to_main,'main_request_seconds':smoke_events[0]['duration_ms']/1000,'primary_request_seconds_sum':sum(x['request_seconds'] for x in rows),'primary_request_p50':result['by_arm']['integrated']['latency']['request_p50'],'primary_request_p95':result['by_arm']['integrated']['latency']['request_p95']}}
(O/'RESULTS_REVIEW.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'primary':len(records),'regression':len(regrecords),'report_bytes':(O/'EXPERIMENT_RESULTS_UTF8.txt').stat().st_size,'timing':audit['timing']},ensure_ascii=False))
