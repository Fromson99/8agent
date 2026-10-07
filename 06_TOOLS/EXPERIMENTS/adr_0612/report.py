import json,re
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery';run=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def cell(x):return str(x).replace('|','\\|').replace('\n','<br>')
def block(x):return '```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```'
def main():
 r=read(run/'result.json');s=read(run/'evidence-summary.json');b=read(A/'artifacts/design/source-binding.json');base=R/'02_BACKEND/lawrag/research/candidates/adr_0612/bounded-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent'
 out=['# 실제 CM 데이터 멀티턴 수정·재실험 — ADR-0612','',
 '실제 저장 CM 질문 **cm-038(대표자의 내부회계 보고 위임), cm-003(신규상장 의무보유)**에서 시작해 각각 12턴·7턴을 진행했다. 수정 전후 같은 19턴씩 총38턴이며, 정정용 후속 발언은 실험을 위해 작성했다. 모의 A/B 규정을 쓰지 않았다. 저장된 공개 원문145문서 범위를 허용하고 실제 검색·원문 읽기를 거쳤다. CM 전체61문항 전수평가는 아니다.','',
 '제품·중간 처리와 분리된 사후 평가는 qwen/qwen3.8-27b, Parasail FP8, reasoning none, temperature0, fallback 없음이다. 골든 답은 제품 입력에 제공하지 않았다. 법률 결과는 저장 CM 기준답과의 일치 평가이며 현행 법률 자문 인증은 아니다.','',
 '## 수정한 범위','', '수정 전은 ADR0611 GUARDED 동결본이다. 출력·범위·판단 복구가 이번 변경이고, 아래 방법 통제·이력·경험 보존은 그 부모에서 상속했다.','',
 '| 변경 | 동작 |','|---|---|',
 '| 유한한 출력·복구 | 검색어 최대4개와 필드 길이 한도를 둔다. 잘린 응답·JSON 형식 오류는 같은 입력으로 한 번만 복구하고 재실패하면 중단한다. |',
 '| 접근 범위와 검색 초점 | 질문에 법령명이 등장해도 허용 문서를 그 법령으로 축소하지 않는다. 명시적 문서 제한만 EXPLICIT로 처리하고, 기본 AUTHORIZED 범위에서 기존 참조 탐색을 사용한다. |',
 '| 판단 복구 | 원문 인용·의미 검사에서 거부되면 실패한 판단과 이유를 전달해 ASSESS를 한 번 다시 수행한다. 재검사를 통과해야 답변 단계로 간다. |',
 '| 상속한 허용 방법 선택 | 모델은 CASE_START, FACT_UPDATE, STATE_RESTORE, HISTORY_EXPLAIN, ANSWER_PRESENT 등 등록된 메모리 작업 방법을 선택한다. 서버가 해당 방법의 동작과 시작 단계를 정한다. |',
 '| 설명·표의 권한 | 이력 조회와 표현 방법은 사실·목적·검색 계획을 몰래 바꾸지 못한다. 잘못된 필드를 제출하면 거부하고 제한된 재수정을 요청한다. |',
 '| 경험 폐기 | 명령 이름만 보고 폐기하던 분기를 제거했다. 실제 상태가 바뀌거나 판단을 다시 검토하는 경우에 이전 경험을 무효화한다. 표현만 바꾸면 확인된 경험을 보존한다. |',
 '| 이력 근거 | 이력 설명은 DB의 실제 이벤트·이전/이후 조건·복원 대상 ID로 출력한다. 모델이 과거 경위를 만들어 쓰는 경로를 없앴다. 일반 최종 답변·표는 계속 LLM이 작성한다. |',
 '| 보조 검사 | 일반 답변 작성과 검사에도 실제 정정 이력을 전달해, 존재하는 정정을 부정하는 설명을 점검하도록 했다. |','',
 '**구현 범위는 메모리 작업의 방법·권한 통제다. 법률 개념·관계·적용 경로 전체를 승인된 온톨로지로 강제하는 기능은 아직 아니다.** 현재 원문 선택 이유와 법률 개념명에는 자유 문장이 남는다.','',
 f"수정 구현의 모델 없는 상태·권한 계약 검사: **43/43**. 제품 MAIN·GENOS에 활성화하지 않은 격리 후보에서 검증했다.",'',
 '## 실제 모델 결과','', '정상 응답은 내용의 정답 여부와 별개다. READY는 답변을 생성했다는 상태이며, 법률 기준답 일치는 아래 별도 행에서 본다.','',
 '| 항목 | 수정 전 BASELINE | 수정 후 RECOVERED |','|---|---:|---:|']
 for label,keys in [('정상 응답 턴',('completed_turns','turns')),('상태·권한 체크',('functional_passed','functional_total')),('CM 기준답 일치',('legal_correct','legal_total')),('정정 이력 설명 정확성',('history_correct','history_total'))]:
  out.append('| '+label+' | '+' | '.join(str(s['by_arm'][a][keys[0]])+'/'+str(s['by_arm'][a][keys[1]]) for a in ('BASELINE','RECOVERED'))+' |')
 out += ['', '이력 설명은 실제 이전 상태·정정·복원 과정을 모두 설명하는지 별도 사후 평가했다. 상태 점수와 법률 답변 점수는 합산하지 않는다. 한 가지 원인으로 여러 후속 턴이 막히면 체크 실패가 여러 번 집계된다.','',block(s['comparisons']),'', '## 턴별 비교','']
 for cid in ('cm-038-chain','cm-003-chain'):
  cases={a:next(c for c in p['products'] if c['case_id']==cid) for a,p in r['arms'].items()}
  out += ['### '+cid,'','| 턴 | 사용자 입력 원문 | 수정 전 | 수정 후 |','|---|---|---|---|']
  for x,y in zip(cases['BASELINE']['turns'],cases['RECOVERED']['turns']):
   def desc(t):
    o=t['output'];return o.get('status','')+' / '+(' → '.join(o.get('executed',[])) or o.get('method_id') or o.get('reason') or o.get('error') or '별도 실행 없음')
   out.append(f"| {x['turn']} | {cell(x['input']['question'])} | {cell(desc(x))} | {cell(desc(y))} |")
  out += ['']
  for x,y in zip(cases['BASELINE']['turns'],cases['RECOVERED']['turns']):
   out += [f"### {cid} / {x['turn']}",'','사용자: '+x['input']['question'],'']
   for arm,t in [('BASELINE',x),('RECOVERED',y)]:
    o=t['output'];out += ['**'+('수정 전' if arm=='BASELINE' else '수정 후')+' 실제 답변**','',(o.get('answer') or {}).get('text') or '답변 없음: '+(o.get('reason') or o.get('error') or o.get('status','')),'']
    out += [f"[입력·응답·그 시점의 DB 상태]({run/arm/cid/('turn-'+str(t['turn']).zfill(2)+'.json')})",'']
 out += ['## 실패와 미확인 범위','', '확인된 구조적 원인: 첫 CM038 근거 보완 호출에서 C001·C002를 각각 두 번 선택했다. 모든 ID가 허용 목록 안이었지만 중복 ID 검사에서 전체 선별이 실패했다. 또한 복원 후 검사 모델이 이전 이벤트를 최신 상태로 잘못 읽거나, 원문에 있는 기관별 일반 규칙 설명을 사건 사실 추가로 오해했다. 현재 상태 복원과 최종 답변 검증은 서로 다른 성공 조건이다.','', '아래 원점수는 실행 전 동결한 채점 기준을 그대로 사용한다. 초기 답변이 실패하면 출력 state가 없어 복원 비교도 실패할 수 있으므로, 상태 체인의 실제 복원 여부는 별도 진단 자료에서 구분한다.','',block([{'arm':a,**c} for a,g in r['functional'].items() for c in g['checks'] if not c['pass']]),'',block([x for x in r['semantic'] if not x['verdict']['correct']]),'',
 '이번 실험은 처음부터 arm당 재사용 2회·복원 4회를 동결했다. 이력·표 이후 경험 보존은 해당 질문의 묶음으로 확인했다. ADR0611의 단순 통과 개수와 직접 합산하지 않는다.','',
 '조건 복원·이력 설명·경험 보존이 성공해도 법률 판단의 정확성을 보장하지 않는다. 원문 누락, 적용 대상 해석, 예외·참조 연결, 온톨로지의 도메인 적합성은 각각 검증해야 한다.','',
 '## 비용·지연과 출처','',block({'usage':s['usage'],'arms':s['by_arm'],'generation':b['generation'],'generation_id':b['generation_id'],'store_sha256':b['source_store_sha256'],'scope_documents':len(b['scope_document_ids']),'source_manifest_export_allowed_unchanged':b['source_manifest_export_allowed']}),'',
 f'[실험 결정문]({A/"README.md"}) · [동결 설계·계보]({A/"실험/manifest.json"}) · [원점수]({run/"result.json"}) · [공개 원문 출처 결속]({A/"artifacts/design/source-binding.json"})','',
 f'[수정된 메모리 실행]({base/"corrected_memory.py"}) · [등록된 메모리 방법과 이력 출력]({base/"memory_methods.py"}) · [답변 작성·검사 입력]({base/"memory_rag.py"})']
 p=R/'07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_CM_MEMORY_RECOVERY_20261002.md';p.write_text('\n'.join(out)+'\n');print(p)
if __name__=='__main__':main()
