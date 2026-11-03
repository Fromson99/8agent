"""Combine disjoint planned cells, retaining the first failed experiment."""
from common import *
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1303-main135-nearai-answer-probe'
parents=[OLD,ADR];cells=[];cost=0;tokens=0;calls=0;unknown=0;checks=0;delivered=0
for parent in parents:
 a=read(parent/'artifacts/source-wire-audit.json');s=read(parent/'artifacts/semantic-review.json')
 for row in a['cells']:
  d=parent/'artifacts/live'/row['cell'];r=read(d/'result.json');score=next(v for v in s['rows'] if v['cell']==row['cell'])
  cells.append({'cell':row['cell'],'question':row['case_id'],'ontology':'OFF' if row['arm']=='baseline' else 'ON','verdict':score['verdict'],'basis':score['basis'],'seconds':r['request_seconds'],'physical_calls':row['physical_calls'],'reported_cost_usd':row['reported_cost_usd'],'source_articles':row['acquired_articles'],'source_mismatches':len(row['source_mismatches']),'wire_mismatches':len(row['wire_mismatches']),'http_status':r['http_status'],'claims':r['claims'],'answer_path':str((d/'answer.txt').relative_to(ROOT)),'adr':parent.name})
  cost+=row['reported_cost_usd'];tokens+=row['reported_tokens'];calls+=row['physical_calls'];unknown+=row['unknown'];checks+=row['source_checks'];delivered+=row['delivered_checks']
assert len({c['cell'] for c in cells})==len(cells),'Do not duplicate a rerun as an independent cell'
planned=[('ontology-365','OFF'),('ontology-365','ON'),('ontology-369','ON'),('ontology-369','OFF')]
ordered=[next((c for c in cells if (c['question'],c['ontology'])==(q,o)),{'cell':q+'-'+o,'question':q,'ontology':o,'verdict':'NOT_RUN','basis':'Global stop before dispatch'}) for q,o in planned]
correct=sum(c['verdict']=='PASS' for c in ordered);errors=sum(c['verdict']=='ERROR' for c in ordered);partial=sum(c['verdict']=='INCOMPLETE' for c in ordered);wrong=sum(c['verdict']=='FAIL' for c in ordered)
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-main135-nearai';OUT.mkdir(exist_ok=True)
result={'main':'MAIN135','provider':'near-ai/fp8','model':'qwen/qwen3.8-27b','reasoning':'none','fallback':False,'unique_questions':2,'predefined_cells':4,'attempted_cells':len(cells),'completed_correct':correct,'incorrect_final_answers':wrong,'technical_failures':errors,'incomplete_answers':partial,'not_run':4-len(cells),'cells':ordered,'physical_calls':calls,'unknown':unknown,'reported_cost_usd':cost,'reported_tokens':tokens,'source_span_checks':checks,'wire_delivered_span_checks':delivered,'main_changed':False,'provider_default_changed':False,'causal_provider_comparison':False,'sequence':'ADR1303 first365OFF known Oracle500 retained; ADR1304 only previously unexecuted3cells with prospective independent-cell stop rules; no failed-cell retry.'}
put(OUT/'전체실행결과.json',result)
lines=['MAIN135 Near AI 단독 실제 답변 검증 — 2026-11-03','',f'두 질문×일반OFF/온톨로지ON 네 조합. 실행 {len(cells)}/4, 완료 정답 {correct}, 내용오답 {wrong}, 미완료 {partial}, 기술실패 {errors}, 미실행 {4-len(cells)}. 미실행과 기술실패를 법률 오답률로 바꾸지 않는다.','',f'Qwen3.8-27b·NearAI FP8 only·reasoning none·출력상한없음. 총 물리 {calls}회, UNKNOWN {unknown}, 보고비용 ${cost:.8f}, 보고토큰 {tokens}. 공급자 전환 없음.','']
for c in ordered:
 lines.append(f'{c["question"]} / {c["ontology"]}: {c["verdict"]}'+(f' · {c["seconds"]:.3f}초 · {c["physical_calls"]}호출 · 주장{c["claims"]}' if 'seconds' in c else ''))
 lines.append(c['basis']);lines.append('')
lines+=['첫 실패의 구체 원인: 제365조 원문을 확보하고 중간답변의 세 규칙은 일치했다. 감독이 종료가능 설명과 CONTINUE_TARGETED/RESEARCH 행동을 함께 반환했고, 기존 독립조사 복구로 재검색한 SQL에서 ORA-01460가 발생했다. 46,901자 CLOB 범위인자가 있는 쿼리였으나 그 길이만이 원인인지는 분리검증하지 않았다. 최종ASSESS/답변에 도달하지 못했으므로 정답으로 세지 않는다.','',f'원문span 대조 {checks}, 실제전달span 대조 {delivered}. 반복대조 수와 고유원문 수는 별개다. 원문/권한/전송 검증 및 호출예산은 각 ADR source-wire-audit.json에 보존했다.','', 'MAIN135516파일과 동결실행본 동일. 실제 Oracle Gold는 읽기전용, 사건/모델기록은 격리SQLite. 첫 오류 원응답 및 실패기록은 그대로 보존하고 나머지3조합을 새ADR에서 사전동결했다. 전체 네 조합에 실패 재실행은 없다.','', '두 질문의 작은 알려진 표본이므로 전체 정답률·NearAI 안정성 우위·공급자 인과 개선율로 일반화하지 않는다. 기존MAIN133 시험과는 코드도 다르다. 이번 제공자 고정은 시험 설정이며 기본공급자/MAIN/Gold설정/제품/DB내용·DDL/메일/Git push/GENOS 현장 변경은 없다.','', '상세 기록:',str(OLD.relative_to(ROOT))+'/README.md',str(ADR.relative_to(ROOT))+'/README.md']
(OUT/'전체실행_정답과실패.txt').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='cells'},ensure_ascii=False))
