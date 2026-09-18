"""Trace-only failure analysis. Does not grade or alter any product output."""
from pathlib import Path
from collections import Counter
import json,hashlib
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation';A=D/'artifacts'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
results=read(A/'results.json');metrics=read(A/'metrics.json');cases=read(A/'dataset/product-cases.json');rows=[]
for c in cases:
 cid=c['id'];r=results['cases'][cid]['harness'];s=(r.get('output') or {}).get('retrieval',{}).get('term_agent',{});calls=sorted((A/'calls'/cid/'harness').glob('call-*-task_interpret'));observed=[]
 for p in calls:
  if not (p/'output.json').exists():continue
  out=read(p/'output.json')
  for x in out.get('concepts',[]):
   start=c['question'].find(x['text']);observed.append({'call':p.name,'text':x['text'],'reported_start':x['start'],'reported_end':x['end'],'actual_substring':c['question'][x['start']:x['end']],'first_exact_start':start,'first_exact_end':start+len(x['text']) if start>=0 else None})
 rows.append({'case_id':cid,'failure':s.get('failure'),'phase':s.get('task_state',{}).get('phase'),'read_count':len(s.get('read_source_ids',[])),'interpret_calls':len(calls),'distinct_request_hashes':len({sha(p/'request.json') for p in calls}),'span_observations':observed})
judge_note={'case_id':'guard-unknown','raw_judge_verdict':'correct=true','actual_phase':metrics['by_arm']['harness']['by_case']['guard-unknown']['phase'],'actual_failure':metrics['by_arm']['harness']['by_case']['guard-unknown']['failure'],'reason':'Frozen judge prompt forbids accepting system-error-only output, but judge accepted UNCONFIRMED as successful unknown handling. Trace shows span failure before concept search. No regrade or metric overwrite performed.'}
report={'judge_inconsistency':judge_note,'schema_version':'task-harness-live-diagnosis-v1','scope':'trace-only, no regrade or product changes','cases':rows,'observed_failures':dict(Counter((x['failure'] or {}).get('message','none') for x in rows))}
with (A/'diagnosis.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
text='# 실제 호출에서 확인한 원인\n\n| 질문 | 하네스 상태 | 원문 읽기 | 해석 호출 | 서로 다른 요청 수 | 실패 |\n|---|---|---:|---:|---:|---|\n'
for x in rows:text+=f"| {x['case_id']} | {x['phase']} | {x['read_count']} | {x['interpret_calls']} | {x['distinct_request_hashes']} | {(x['failure'] or {}).get('message','없음')} |\n"
text+='''
## 관측과 코드 연결

1. `TaskSession.interpret`는 LLM이 반환한 start/end로 원문을 잘라 text와 비교한다. 예컨대 첫 질문의 “집합투자”는 Python 문자 범위 `[7:11]`인데 모델은 `[8:12]`를 반환했다. “자본시장법”도 실제 `[0:5]`를 `[0:6]`으로 반환했다. 이 검사는 잘못된 좌표를 올바르게 거부했지만, 정확한 문자 계산을 모델 책임으로 둔 계약이 정상 질문을 막았다.
2. 해석 실패 때 `run`은 오류를 저장하고 재시도하지만 `interpret`의 모델 입력에는 question/initial만 들어간다. 해석 3회가 있었던 실패 사례의 request.json 해시를 비교하면 동일 입력 반복을 확인할 수 있다. 오류를 다음 호출에 전달하는 복구가 아니다.
3. 모델이 법률명 자체를 concept으로 반환한 사례도 있다. 문서 범위와 설명 대상 개념의 역할을 분리할 필요가 있다. 문자 위치 문제를 고치는 것만으로 뒤의 개념 선정·증거 검토 성공이 보장된다고 주장하지 않는다.
4. 사용자 답변에 `MODEL_OR_CONTRACT_ERROR_LIMIT` 및 `UNCONFIRMED` 같은 내부 상태가 노출됐다. 실패를 사용자에게 필요한 추가 정보와 분리된 자연어 설명으로 변환하는 처리가 필요하다.

원문 조회 전에 중단된 사례에서는 뒤의 후보 검토·근거 함의 검토·완료조건이 실제 모델로 검증되지 않았다. 기존 모의 계약61개 통과는 이 실제 작동 성공을 대신하지 않는다. 기존 탐색의 실패에도 잘못된 ID, 정확 인용 불일치, args JSON 파싱 등 별도 원인이 있다. 기존에서 설명이 생성되고 새 하네스에서는 전혀 생성되지 않은 실행 차이를 보존한다. 단회 자동 점수만으로 확정된 회귀율을 주장하지 않는다.

## 후속 변경 후보 — 이번 실험에서는 미적용

- 모델은 원문에 존재하는 의미 있는 표현을 제안하고, 문자 좌표는 코드가 exact substring 및 중복 출현 규칙으로 계산한다. 인용/범위 검증을 느슨하게 해 통과시키는 방법은 사용하지 않는다.
- 재시도에는 이전 제안·구조화된 검증 오류를 전달하고, 동일 제안 반복이면 일찍 중단하거나 확인 질문으로 전환한다.
- 해석에서 문서명·개념명·사용자 의도를 구분하고, 원문 탐색 단계까지 통과하는 새 실험을 한 뒤 근거 검토 품질을 따로 측정한다.

실제 수정·재실행은 새 ADR에서 현재 결과를 부모로 사용해야 한다. 이 문서는 실패 기록과 개선 후보이며 제품 코드 수정이나 MAIN 반영이 아니다.
'''
text+='\n## 자동 채점의 충돌 — 재채점하지 않음\n\n미등록 개념 질문을 자동 채점기는 correct=true로 보았지만, 실행은 문자 위치 오류로 INCOMPLETE였고 적절한 확인 질문이 없었다. 원래 채점 지시의 ‘시스템 오류 출력은 확인 요청으로 인정하지 않는다’와 충돌한다. 따라서 원시 지표의 보호 경계2/2를 정상 동작2/2로 받아들이면 안 된다. 매도 요청의 WAITING_USER와 이 실패를 구분한다.\n\n증권 정식 질문은 정의·예외·미발행 권리를 설명했는데도 형식적 범위 설명 누락으로 자동 실패, 의역 질문은 정의 설명이 불완전하고 한도 종료인데도 자동 통과로 판정됐다. 이 단회 evaluator를 검증된 채점기로 볼 수 없다. 기존1/6과 보호 경계 점수는 raw 자동평가 값으로만 남긴다. 새 하네스 설명0/6 및 원문 읽기0/6은 실제 trace에서도 확인된다.\n'
(A/'diagnosis.md').write_text(text)
print(json.dumps(report['observed_failures'],ensure_ascii=False))
