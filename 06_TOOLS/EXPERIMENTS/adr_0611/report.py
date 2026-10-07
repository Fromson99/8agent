import json,re
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards';run=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def cell(x):return str(x).replace('|','\\|').replace('\n','<br>')
def block(x):return '```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```'
def main():
 r=read(run/'result.json');s=read(run/'evidence-summary.json');b=read(A/'artifacts/design/source-binding.json');base=R/'02_BACKEND/lawrag/research/candidates/adr_0611/method-guarded-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent'
 out=['# 실제 CM 데이터 멀티턴 수정·재실험 — ADR-0611','',
 '실제 저장 CM 질문 **cm-038(대표자의 내부회계 보고 위임), cm-003(신규상장 의무보유)**에서 시작해 각각 12턴·7턴을 진행했다. 수정 전후 같은 19턴씩 총38턴이며, 정정용 후속 발언은 실험을 위해 작성했다. 모의 A/B 규정을 쓰지 않았다. 저장된 공개 원문145문서 범위를 허용하고 실제 검색·원문 읽기를 거쳤다. CM 전체61문항 전수평가는 아니다.','',
 '제품·중간 처리와 분리된 사후 평가는 qwen/qwen3.8-27b, Parasail FP8, reasoning none, temperature0, fallback 없음이다. 골든 답은 제품 입력에 제공하지 않았다. 법률 결과는 저장 CM 기준답과의 일치 평가이며 현행 법률 자문 인증은 아니다.','',
 '## 수정한 범위','',
 '| 변경 | 동작 |','|---|---|',
 '| 허용 방법 선택 | 모델은 CASE_START, FACT_UPDATE, STATE_RESTORE, HISTORY_EXPLAIN, ANSWER_PRESENT 등 등록된 메모리 작업 방법을 선택한다. 서버가 해당 방법의 동작과 시작 단계를 정한다. |',
 '| 설명·표의 권한 | 이력 조회와 표현 방법은 사실·목적·검색 계획을 몰래 바꾸지 못한다. 잘못된 필드를 제출하면 거부하고 제한된 재수정을 요청한다. |',
 '| 경험 폐기 | 명령 이름만 보고 폐기하던 분기를 제거했다. 실제 상태가 바뀌거나 판단을 다시 검토하는 경우에 이전 경험을 무효화한다. 표현만 바꾸면 확인된 경험을 보존한다. |',
 '| 이력 근거 | 이력 설명은 DB의 실제 이벤트·이전/이후 조건·복원 대상 ID로 출력한다. 모델이 과거 경위를 만들어 쓰는 경로를 없앴다. 일반 최종 답변·표는 계속 LLM이 작성한다. |',
 '| 보조 검사 | 일반 답변 작성과 검사에도 실제 정정 이력을 전달해, 존재하는 정정을 부정하는 설명을 점검하도록 했다. |','',
 '**구현 범위는 메모리 작업의 방법·권한 통제다. 법률 개념·관계·적용 경로 전체를 승인된 온톨로지로 강제하는 기능은 아직 아니다.** 현재 원문 선택 이유와 법률 개념명에는 자유 문장이 남는다.','',
 f"수정 구현의 모델 없는 상태·권한 계약 검사: **34/34**. 제품 MAIN·GENOS에 활성화하지 않은 격리 후보에서 검증했다.",'',
 '## 실제 모델 결과','',
 '| 항목 | 수정 전 BASELINE | 수정 후 GUARDED |','|---|---:|---:|']
 for label,keys in [('정상 응답 턴',('completed_turns','turns')),('상태·권한 체크',('functional_passed','functional_total')),('CM 기준답 일치',('legal_correct','legal_total')),('정정 이력 설명 정확성',('history_correct','history_total'))]:
  out.append('| '+label+' | '+' | '.join(str(s['by_arm'][a][keys[0]])+'/'+str(s['by_arm'][a][keys[1]]) for a in ('BASELINE','GUARDED'))+' |')
 out += ['', '이력 설명은 실제 이전 상태·정정·복원 과정을 모두 설명하는지 별도 사후 평가했다. 상태 점수와 법률 답변 점수는 합산하지 않는다. 한 가지 원인으로 여러 후속 턴이 막히면 체크 실패가 여러 번 집계된다.','',block(s['comparisons']),'', '## 턴별 비교','']
 for cid in ('cm-038-chain','cm-003-chain'):
  cases={a:next(c for c in p['products'] if c['case_id']==cid) for a,p in r['arms'].items()}
  out += ['### '+cid,'','| 턴 | 사용자 입력 원문 | 수정 전 | 수정 후 |','|---|---|---|---|']
  for x,y in zip(cases['BASELINE']['turns'],cases['GUARDED']['turns']):
   def desc(t):
    o=t['output'];return o.get('status','')+' / '+(' → '.join(o.get('executed',[])) or o.get('method_id') or o.get('reason') or o.get('error') or '별도 실행 없음')
   out.append(f"| {x['turn']} | {cell(x['input']['question'])} | {cell(desc(x))} | {cell(desc(y))} |")
  out += ['']
  for x,y in zip(cases['BASELINE']['turns'],cases['GUARDED']['turns']):
   out += [f"### {cid} / {x['turn']}",'','사용자: '+x['input']['question'],'']
   for arm,t in [('BASELINE',x),('GUARDED',y)]:
    o=t['output'];out += ['**'+('수정 전' if arm=='BASELINE' else '수정 후')+' 실제 답변**','',(o.get('answer') or {}).get('text') or '답변 없음: '+(o.get('reason') or o.get('error') or o.get('status','')),'']
    out += [f"[입력·응답·그 시점의 DB 상태]({run/arm/cid/('turn-'+str(t['turn']).zfill(2)+'.json')})",'']
 out += ['## 실패와 미확인 범위','',block([{'arm':a,**c} for a,g in r['functional'].items() for c in g['checks'] if not c['pass']]),'',block([x for x in r['semantic'] if not x['verdict']['correct']]),'',
 '사전 성공 기준의 서술에 재사용 요청을 세 개라고 적었지만, 실제 동결 입력·gold·실행은 arm당 두 개였다. 설명의 숫자 오류를 보존하며 결과를 본 뒤 턴을 추가하거나 점수를 바꾸지 않았다.','',
 '조건 복원·이력 설명·경험 보존이 성공해도 법률 판단의 정확성을 보장하지 않는다. 원문 누락, 적용 대상 해석, 예외·참조 연결, 온톨로지의 도메인 적합성은 각각 검증해야 한다.','',
 '## 비용·지연과 출처','',block({'usage':s['usage'],'arms':s['by_arm'],'generation':b['generation'],'generation_id':b['generation_id'],'store_sha256':b['source_store_sha256'],'scope_documents':len(b['scope_document_ids']),'source_manifest_export_allowed_unchanged':b['source_manifest_export_allowed']}),'',
 f'[실험 결정문]({A/"README.md"}) · [동결 설계·계보]({A/"실험/manifest.json"}) · [원점수]({run/"result.json"}) · [공개 원문 출처 결속]({A/"artifacts/design/source-binding.json"})','',
 f'[수정된 메모리 실행]({base/"corrected_memory.py"}) · [등록된 메모리 방법과 이력 출력]({base/"memory_methods.py"}) · [답변 작성·검사 입력]({base/"memory_rag.py"})']
 p=R/'07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_CM_MEMORY_REPAIR_20261001.md';p.write_text('\n'.join(out)+'\n');print(p)
if __name__=='__main__':main()
