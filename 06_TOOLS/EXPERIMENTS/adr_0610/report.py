"""Render observed responses and immutable state receipts, without changing grades."""
import hashlib,json,re,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples';run=A/'artifacts/run-001'
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def link(p,label):return f'[{label}]({p})'
def block(x):return '```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```'
def cell(s):return str(s).replace('|','\\|').replace('\n','<br>')
r=json.loads((run/'result.json').read_text());grades=r['grades'];products=r['products'];rows=[(c['case_id'],t) for c in products for t in c['turns']]
usage=r['summary']['usage'];cost=sum(u.get('usage',{}).get('cost',0) or 0 for u in usage)
passed=sum(g['passed'] for g in grades);total=sum(g['total'] for g in grades)
failed=[{'case':g['case_id'],**c} for g in grades for c in g['checks'] if not c['pass']]
bykind={}
for g in grades:
 for c in g['checks']:
  v=bykind.setdefault(c['kind'],[0,0]);v[0]+=int(c['pass']);v[1]+=1
allpass=sum(all(c['pass'] for c in g['checks'] if c['turn']==t['turn']) for g in grades for t in next(x for x in products if x['case_id']==g['case_id'])['turns'])
report=R/'07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_FORCED_MULTITURN_EXAMPLES_20261001.md'
out=['# 실제 모델 강제 멀티턴 예시 — ADR-0610','',
'22턴 입력을 사전에 고정하고 실제 Qwen3.8(27B), Parasail FP8, reasoning none, fallback 없음으로 실행했다. 원문은 **모의승인규정**이다. 실제 법률 해석 결과가 아니다.',
'현재 실행 대상은 완료된 ADR-0609 프로토의 동일한 코드다. 새로 설계한 domain-control-v1의 등록된 개념·방법·경로와 사전/사후 검증은 구현하지 않았다. 이 문서의 모델 답변은 실제 응답이며, 설계 예시로 만든 답변이 아니다.',
f'사전 체크포인트 **{passed}/{total}**, 해당 턴의 모든 체크를 통과한 턴 **{allpass}/{len(rows)}**. 이는 상태·목표·복원·실행 범위·표·설명 여부를 함께 보는 기능 판정이며 법률 정확도 비율이 아니다. 실제 모델 성공 호출 {len(usage)}회, 성공 호출 보고 비용 ${cost:.6f}.',
'모의 원문: 제1조 “국내 대상의 승인 절차는 A이다. 해외 대상의 승인 절차는 B이다.” / 제2조 “긴급 사건은 별도 예외를 확인해야 한다.” 제2조에는 구체적 예외 절차가 없다.',
(A/'artifacts/causal-review.md').read_text(), '## 기능별 사전 판정','| 검사 | 통과/전체 |','|---|---:|']
labels={'status':'응답 상태','procedure_token':'절차 A/B 문구','target':'수정 대상 질문','unconfirmed_not_published':'미확인 답변의 지식 발행 차단','active_route_current':'현재 상태와 활성 루트 일치','executed_stages':'지정 재실행 범위','unrelated_goals_unchanged':'다른 질문 보존','restored_fact_state':'과거 조건의 정확한 복원','markdown_table':'표 형식','requested_natural_explanation':'설명 응답 존재 여부(내용 정확성 제외)'}
for k,v in bykind.items():out.append(f'| {labels.get(k,k)} | {v[0]}/{v[1]} |')
out += ['', '## 전체 대화 한눈에 보기','조건부 READY 상태만으로 정답을 판정하지 않았다. 실제 답변·실행 단계·상태 체크를 아래에 함께 남긴다.','| 사례·턴 | 사용자 입력 원문 | 실제 상태 | 다시 실행한 단계 |','|---|---|---|---|']
for cid,t in rows:
 o=t['output'];out.append(f"| {cid}/{t['turn']} ({t['input']['session_id']}) | {cell(t['input']['question'])} | {o.get('status')} | {cell(' → '.join(o.get('executed',[])) or '실행 목록 없음')} |")
out += ['','## 실패한 사전 체크 원문',block(failed),'','## 턴별 실제 답변과 수정 근거']
for cid,t in rows:
 o=t['output'];out += ['',f"### {cid} / {t['turn']} — {t['input']['session_id']}",f"사용자: {t['input']['question']}",'', '실제 답변:', '', (o.get('answer') or {}).get('text') or ('**자연어 답변 없음.** '+(o.get('error') or o.get('reason') or '응답에는 상태·이벤트·노드 등의 구조화 데이터만 있다.'))]
 proposed=[]
 for folder in sorted((run/'provider').glob('call-*')):
  n=int(folder.name.split('-')[1])
  if t['provider_attempt_start']<=n<=t['provider_attempt_end'] and ('memory-resolve' in folder.name) and (folder/'output.json').exists():proposed.append(json.loads((folder/'output.json').read_text()))
 events=[e for e in t['db']['event'] if e['request']==t['input']['request_id']]
 cmd=events[-1]['command'] if events else proposed[-1] if proposed else {}
 out += ['', '실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):',block({'status':o.get('status'),'goal_id':o.get('goal_id'),'revision':o.get('revision'),'executed':o.get('executed'),'command':cmd,'state':o.get('state') or (events[-1]['after_state'] if events else None),'events_for_this_request':[e['id'] for e in events],'active_knowledge_count':sum(k['status']=='ACTIVE' for k in t['db']['knowledge'])}),link(run/cid/f"turn-{t['turn']:02d}.json",'실제 입력·응답·DB 상태 전체')]
last=rows[-1][1]['db']
out += ['', '## 저장과 과거 기록의 처리', '작업용 session/event/node와 재사용할 knowledge/ontology를 구분한다. 모든 발언은 작업 이력을 이어가기 위해 남을 수 있지만, 확인되지 않은 답변은 지식 묶음으로 발행하지 않는다. 틀린 루트는 ACTIVE에서 제외하고 감사 이력으로 보존한다.',block({'knowledge':[{'id':k['id'],'bundle':k['bundle'],'revision':k['revision'],'status':k['status'],'state':k['payload']['state']} for k in last['knowledge']],'routes':{s:sum(x['status']==s for x in last['route']) for s in ('ACTIVE','RETIRED')},'ontology_node_count':len(last['ontology_node']),'ontology_edge_count':len(last['ontology_edge'])}),
'## 재현·원시 근거',link(A/'README.md','실험 결정문')+' · '+link(A/'실험/manifest.json','계보·모델·동결 계약')+' · '+link(run/'result.json','원점수와 전체 결과')+' · '+link(run/'memory.sqlite','실제 실험 DB'),
'운영 MAIN·GENOS에 적용한 결과가 아니다. 단일 모의 원문, 사전에 강제로 정한 사용자 턴, 한 번 실행한 탐색 실험이다. 긴 실제 업무 대화의 일반 성능은 이 결과로 확정할 수 없다.']
rendered='\n'.join(out)+'\n'
rendered=re.sub(r'(?m)^(#{1,6} .+)\n(?!\n)',r'\1\n\n',rendered)
rendered=re.sub(r'(?m)([^\n])\n(?=\|)',r'\1\n\n',rendered, count=1)
report.write_text(rendered)
put(run/'readable-summary.json',{'passed':passed,'total':total,'all_checks_passed_turns':allpass,'turns':len(rows),'by_kind':bykind,'failures':failed,'report':str(report.relative_to(R)),'scoring_unchanged':True})
print(json.dumps({'report':str(report),'passed':passed,'total':total,'fully_passing_turns':allpass,'by_kind':bykind},ensure_ascii=False))
