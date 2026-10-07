"""Human-readable exact examples and separated functional/legal results."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0613-cm-memory-current-state-authority';run=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def cell(v):return str(v).replace('|','\\|').replace('\n','<br>')
def link(title,p):return f'[{title}]({p})'
def error(o):return o.get('error') or o.get('reason') or (o.get('body') or {}).get('detail') or o.get('status')
def main():
 r=read(run/'result.json');s=read(run/'evidence-summary.json');diag=read(run/'diagnosis.json');state=read(run/'state-diagnosis.json');b=read(A/'artifacts/design/source-binding.json');contracts=[read(A/'artifacts/contracts'/n) for n in ('result.json','native-result.json')]
 out=['# 실제 CM 데이터로 검증한 멀티턴 정정·경험 재사용','', '2026-10-02 · WSL 로컬 연구 후보 · ADR0611 → ADR0612 → ADR0613','',
 '실제 저장된 **CM038 대표자의 내부회계 보고 위임**, **CM003 신규상장 의무보유** 질문과 공개 원문을 사용했다. 질문별로 12턴·7턴을 강제로 진행했고, 최종 비교는 같은 19턴씩 수정 전후 총38턴이다. 후속 정정 발언은 실험용으로 작성했다. 세 번의 비교 전체는114턴이다. CM61문항 전수평가는 아니다.','',
 '사용한 자료는 현재 선택된 원문 세대의 공개145문서와26597개 정규 조문 좌표다. 내부 자료를 외부로 전송하지 않았고 원문 export 플래그도 바꾸지 않았다. 저장 CM 기준답은 제품에 넣지 않고 실행을 모두 마친 뒤 사후 평가에서만 사용했다.','',
 '## 이번에 수정한 것','',
 '| 원인 | 수정한 동작 |','|---|---|',
 '| 설명·표를 정정으로 분류하면 확인 경험까지 폐기 | 실제 상태·판단 변경에 따라 폐기하고, 설명·표는 기존 경험을 보존 |',
 '| 작업 이름·시작 단계를 LLM이 임의로 섞음 | 등록된12가지 메모리 방법을 선택하고 서버가 허용 변경과 단계를 검사 |',
 '| 검색어를 끝없이 생성해 최초 질문 생성 실패 | 검색어 최대4개·필드 길이 제한, 불완전 JSON의1회 복구 |',
 '| 법령명을 검색 제한으로 오해해 시행세칙 누락 | 허용 문서 범위와 질문의 법령 초점을 구분하고 기존 참조 탐색 사용 |',
 '| 원문 인용·판단 검사를 통과하지 못하면 즉시 중단 | 거부된 판단과 검사 이유를 전달하여1회 재작성 후 같은 검사 적용 |',
 '| 같은 허용 조문을 두 번 고르면 전체 선별 실패 | 실제 실행 ID만 중복 제거하고 선택 사유 원문은 그대로 보존; 범위·개수 위반은 계속 거부 |',
 '| 과거 정정을 최신 사실로 오해 | 일반 답변·검사에는 현재 사실을 전달하고, 이력 설명은 실제 이벤트 조회로 처리 |',
 '| PLAN을 재시작이 아닌 중단 지점으로 오해 | 시작 단계부터 COMPOSE까지 이어지는 실제 실행 계약을 검사 모델에도 전달 |',
 '| 규칙의 조건별 설명을 새로운 사건 사실로 오해 | 일반 규칙·예외 설명과 사건에 대한 확정적 적용을 구분하도록 검사 계약 명시 |','',
 '**법률 도메인 온톨로지 전체를 구현한 상태는 아니다.** 현재 등록 방법은 메모리 작업의 권한·복원·재실행을 통제한다. 개별 법률 개념·관계·예외의 의미를 승인된 카탈로그로 강제하는 본 설계는 추가 구현 범위이며, 원문 선택과 적용 의미 판단에는 모델 오류가 남을 수 있다.','',
 '## 최종 비교 결과','',
 '수정 전은 완료된 ADR0612 RECOVERED 동결본이고, 수정 후는 ADR0613 REPAIRED다. 둘 다 새 DB에서 같은19턴을 다시 실행했다. 같은 모델의 단일 반복 비교이므로 일반적인 성능 개선율로 확대하지 않는다.','',
 '| 항목 | 수정 전 | 수정 후 |','|---|---:|---:|']
 for label,ns,ds in [('정상 응답 턴','completed_turns','turns'),('사전 기능 검사','functional_passed','functional_total'),('저장 CM 기준답 일치','legal_correct','legal_total'),('실제 정정 이력 설명','history_correct','history_total')]:
  out.append('| '+label+' | '+' | '.join(f"{s['by_arm'][a][ns]}/{s['by_arm'][a][ds]}" for a in ('BASELINE','REPAIRED'))+' |')
 out+=['',f"모델 없는 상태·권한·복구 계약 검사: {sum(c['passed'] for c in contracts)}/{sum(c['total'] for c in contracts)}.",'',
 'READY는 답변 생성 완료 상태다. 법률 정답 여부는 별도의 CM 기준답 일치 행에서 확인한다. 기능 점수와 법률 점수를 합산하지 않았다.','',
 '| 세부 기능 | 수정 전 | 수정 후 |','|---|---:|---:|']
 kinds=list(dict.fromkeys(c['kind'] for c in r['functional']['BASELINE']['checks']))
 for kind in kinds:
  out.append('| '+kind+' | '+' | '.join(f"{sum(c['pass'] for c in r['functional'][a]['checks'] if c['kind']==kind)}/{sum(c['kind']==kind for c in r['functional'][a]['checks'])}" for a in ('BASELINE','REPAIRED'))+' |')
 out+=['','답변이 실패하면 응답에 state가 없어 사전 복원 채점도 실패할 수 있다. 다음 표는 이와 별도로 DB에 저장된 실제 조건을 읽은 진단이며, 원점수를 바꾼 재채점이 아니다.','', '| 구간 | 수정 전 DB 조건 복원 | 수정 후 DB 조건 복원 |','|---|---:|---:|']
 for cid in ('cm-038-chain','cm-003-chain'):
  out.append('| '+cid+' | '+' | '.join(f"{sum(x['facts_equal'] for x in state['restorations'] if x['arm']==a and x['case_id']==cid)}/{sum(x['arm']==a and x['case_id']==cid for x in state['restorations'])}" for a in ('BASELINE','REPAIRED'))+' |')
 out+=['','## 실제 턴별 입력·응답','']
 for cid in ('cm-038-chain','cm-003-chain'):
  cases={a:next(c for c in p['products'] if c['case_id']==cid) for a,p in r['arms'].items()}
  out+=['### '+cid,'','| 턴 | 실제 사용자 입력 | 수정 전 | 수정 후 |','|---|---|---|---|']
  for x,y in zip(cases['BASELINE']['turns'],cases['REPAIRED']['turns']):
   out.append('| '+str(x['turn'])+' | '+cell(x['input']['question'])+' | '+cell(x['output'].get('status'))+' | '+cell(y['output'].get('status'))+' |')
  for x,y in zip(cases['BASELINE']['turns'],cases['REPAIRED']['turns']):
   out+=['',f"### {cid} / {x['turn']}",'','사용자: '+x['input']['question'],'']
   for a,t in [('BASELINE',x),('REPAIRED',y)]:
    o=t['output'];out+=['**'+('수정 전' if a=='BASELINE' else '수정 후')+' 실제 응답**','',(o.get('answer') or {}).get('text') or '답변 없음: '+str(error(o)), '']
    z=next(z for z in diag['arms'][a] if z['case_id']==cid and z['turn']==t['turn'])
    out+=['상태: '+str(o.get('status'))+' / 실행: '+(' → '.join(o.get('executed',[])) or '없음')+' / 방법: '+str(o.get('method_id')),
     '해당 시점 원문 확보 '+str(z['read_count'])+'개, 결정 근거 확보 '+str(len(z['decisive_read']))+'개. 실패 턴의 원문 수는 이전 성공 체크포인트일 수 있다.',link('정확한 입력·응답·그 시점 DB 상태',run/a/cid/f"turn-{t['turn']:02d}.json"),'']
 publication=read(run/'publication-diagnosis.json')
 out+=['## 최종 경험 적재의 별도 진단','', '| 묶음 | 조사 원문 | 채택 원문 | 인용 원문 | 그래프 SUPPORTED_BY |','|---|---:|---:|---:|---:|']
 for x in publication['knowledge_bundles']:
  out.append('| '+x['arm']+' / '+x['knowledge']+' / '+x['status']+' | '+str(x['read_sources'])+' | '+str(x['selected_sources'])+' | '+str(x['claim_sources'])+' | '+str(x['supported_by_sources'])+' |')
 if any(x['supported_but_not_selected'] for x in publication['knowledge_bundles']):
  out+=['', '실제 저장 그래프에서는 읽은 원문 전체에 SUPPORTED_BY 관계를 붙여, 조사했던 자료와 최종 채택한 근거를 충분히 구분하지 못했다. 최종 경험에 조사 이력을 보존하는 것은 필요하지만, 온톨로지의 근거 관계는 조사·채택·인용을 나눠야 한다. 답변 재사용은 별도 SELECT/ASSESS 결과를 사용하므로 이 진단을 곧바로 답변 오답으로 재채점하지 않았다. 공통 DB 이행이나 새 관계 타입 적용은 수행하지 않았다.','']
 out += [link('적재 그래프 진단',run/'publication-diagnosis.json'),'']
 connections=read(run/'connection-diagnosis.json')
 missing=[x for x in connections['arms']['REPAIRED'] if x['selector_requested_more'] and x['decisive_missing']]
 if missing:
  out += ['## 아직 연결하지 못한 추가 검색 신호','', '수정본에서 선별 모델은 needs_fulltext=true로 추가 탐색을 요구했지만, 프로토의 NativeExecution.SELECT 소비자는 final_ids의 존재만 검사하고 ASSESS로 진행했다. 따라서 접근 범위가145문서여도 구조 탐색으로 제26조만 읽은 뒤 시행세칙을 확보하지 못할 수 있다. 이는 모델이 추가 근거 필요성을 전혀 몰랐던 문제가 아니라, 모델 출력의 재탐색 요구를 실제 RAG 순환에 연결하지 못한 구현 문제다.','', '| 사례·턴 | 탐색 모드 | 읽은 원문 | 추가 탐색 요구 | 빠진 결정 근거 |','|---|---|---:|---|---|']
  for x in missing:out.append('| '+x['case_id']+' / '+str(x['turn'])+' | '+str(x['recall_mode'])+' | '+str(x['read_count'])+' | true | '+', '.join(x['decisive_missing'])+' |')
  out += ['',link('추가 검색 연결 진단',run/'connection-diagnosis.json'),'']
 out+=['## 실패·판정 근거','']
 for x in r['semantic']:
  if not x['verdict']['correct']:out+=['- '+x['arm']+' / '+x['case_id']+' / '+str(x['turn'])+' / '+x['kind']+': '+x['verdict']['reason']]
 for a,p in r['arms'].items():
  for c in p['products']:
   for t in c['turns']:
    if t['output'].get('status') not in ('READY','STORED','REUSED'):out+=['- 실행 실패 '+a+' / '+c['case_id']+' / '+str(t['turn'])+': '+str(error(t['output']))]
 out+=['','## 실행·출처·검증 범위','',
 '모델은 qwen/qwen3.8-27b, OpenRouter Parasail FP8, reasoning none, temperature0, 자동 fallback 없음이다. 제품과 사후 평가 모델은 같으며 사람의 법률 검증을 대체하지 않는다.','',
 '제품 MAIN, 운영 registry, 원문 세대, GENOS 배포는 변경하지 않았다. 연구 후보는 명시된 실행기에서만 주입했다.','',
 '```json',json.dumps({'usage':s['usage'],'by_arm':s['by_arm'],'source_generation':b['generation'],'generation_id':b['generation_id'],'store_sha256':b['source_store_sha256']},ensure_ascii=False,indent=2),'```','',
 link('최종 비교 실험 결정문',A/'README.md')+' · '+link('동결 설계·실행 계보',A/'실험/manifest.json')+' · '+link('원점수',run/'result.json')+' · '+link('단계별 근거 진단',run/'diagnosis.json')+' · '+link('상태 복원 진단',run/'state-diagnosis.json'),'',
 link('1차 비교 ADR0611',R/'07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_CM_MEMORY_REPAIR_20261001.md')+' · '+link('2차 비교 ADR0612',R/'07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_CM_MEMORY_RECOVERY_20261002.md')]
 p=R/'07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_CM_MEMORY_FINAL_20261002.md';p.write_text('\n'.join(out)+'\n');print(p)
if __name__=='__main__':main()
