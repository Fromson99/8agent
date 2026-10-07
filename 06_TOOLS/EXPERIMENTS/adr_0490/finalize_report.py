"""Finalize the historical-control comparison without rewriting inherited outputs."""
import json,hashlib
from pathlib import Path
import report
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0490-source-workflow-packing-review-repair'
def main():
 report.main()
 metric=json.loads((A/'artifacts/metrics.json').read_text());p=A/'실험/manifest.json';m=json.loads(p.read_text())
 b=metric['by_arm']['baseline'];c=metric['by_arm']['repaired'];reviewed={};table='| 질문 | 방식 | 발견 | 읽기 | 전달 | 선택 | 게시 원문 | 검토 주장 | 답변 일치 | 호출 |\n|---|---|---:|---:|---:|---:|---:|---:|---|---:|\n'
 for arm in ['baseline','repaired']:
  reviewed[arm]=0
  for x in [x for x in metric['by_case'] if x['arm']==arm]:
   row=json.loads((A/'artifacts/run-001'/x['case_id']/arm/'result.json').read_text());s=row['stages'];claims=len(row.get('result',{}).get('answer',{}).get('claims',[]));reviewed[arm]+=claims>0
   table+='| '+' | '.join(map(str,[x['case_id'],'상속 기준' if arm=='baseline' else '수정 후보',*[len(s[k]) for k in ['discovered','read','presented','selected','final_sources']],claims,x['correct'],x['calls']]))+' |\n'
 m['results']['usage']={'new_product_calls':c['calls'],'new_product_usage':c['usage'],'new_judge_calls':metric['judge_calls'],'new_judge_usage':metric['judge_usage'],'inherited_control_calls_not_new':b['calls'],'inherited_control_usage_not_new':b['usage']}
 m['results']['reviewed_answer_counts']=reviewed
 m['retrieval_accounting']['not_applicable_reason']=None;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=None
 p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 j=lambda v:'```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```'
 sections=[('결정 요약',f"추가5개 파일을 수정하고19개 계약을 통과한 뒤 Qwen 후보3문항을 새로 실행했다. 게시 {c['publication_success']}/3, 검토 주장 있는 답변 {reviewed['repaired']}/3, 분리 evaluator 기준답 일치 {c['correct']}/3, 핵심 조문 회수율 {c['gold_recall']:.1%}. 비교 기준은 ADR0489 완료 결과3건이며 새 baseline 호출은 없다.\n\n"+j(metric['verdicts'])),
 ('문제와 변경 전 구조','ADR0489는 원문 선택과 게시를 개선했지만 최종 cursor/관계 상세 metadata 크기를 덜 계산했고, 검토 모델이 claim ID 대신 주장 문장을 반환했다. 이번에는 최종 metadata를 먼저 예약하고 claim ID/text를 같은 카드로 제공하며 출력 enum을 현재 claim ID에 결속했다. 원문 선택과 나머지 실행 경로는 부모와 동일하다.'),
 ('가설과 사전 판정 기준',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+j(metric['criteria'])),
 ('실험 설계','수정 후보 CM003/018/038 각1회, 기준은 부모 run-002/source-workflow immutable 결과를 그대로 복사해 사용했다. 같은 원질문·145개 공개문서·세대·Qwen FP8 thinking off·온도0·2800출력·60000context·14회 모델/56회 도구/300초 controller 조건이다. 역사적 기준이므로 동시 paired A/B 효과로 일반화하지 않는다. 결과 후 retuning/추가 반복 없음.'),
 ('데이터·모델·재현성','후보 snapshot99개 파일을 동결했고 부모 대비 추가변경은5개다. source/grant/model/data/runner/evaluator를 호출 전 결속했다. 기존16개 계약에 포화 직전 packing, 고유 cursor, review card/enum, field-path 검사를 추가해19개 통과하고 frozen revision에서 재확인했다. [구현 및 검사 범위](IMPLEMENTATION.md). 동결 utility의 공통 출력문구와 v4 승인충돌 설명은 이전실험 문구가 남아 있으나 실제 order/run/runner는 이번의1회 신규후보/상속기준이다.'),
 ('결과',table+'\n\n'+j(metric['by_arm'])+'\n\n'+j(metric['paired_outcomes'])),
 ('사례별 오류 분석',j([{k:x[k] for k in ['case_id','arm','execution_error','publication_error','semantic_errors','limitations','phases']} for x in metric['by_case']])),
 ('비용·지연·회수 규모',j(m['results']['usage'])+'\n\n'+j(m['results']['latency'])+f"\n\ncorpus {metric['corpus_total']}개. baseline 열 비용/시간/호출은 상속한 과거 기록이며 이번 지출이 아니다. p95는3건 최댓값이다. 초기 자원 로딩 포함 wall과 controller 시간을 구분했다."),
 ('해석','답변 평가에는 답변 텍스트만, 출처 관련성 평가에는 출처 카드만 각각 제공했다. 실제 reviewed claim0인 법률 답변을 정답으로 세지 않는 사전 gate를 적용하고 raw evaluator 응답은 보존했다. source 회수/게시와 법적 정답을 분리한다. 모델별 점수의 인간 calibration은 없으며 관련성 판단은 독립 정답 인증이 아니다.'),
 ('한계와 일반화 가능 범위','부모 실패를 보고 고친 인샘플3건,1회이며 역사적 기준이다. 원래48개 설계 전체, v5 journal, canonical source 병합, oversized E 전면 재분할, 완전한 오류 생명주기/전역 repair, 인증 resume/feedback/bridge와 GENOS 검증은 남았다. 실제 공개 호출은 동일 session/outbox runner, HTTP/Open은 모의 계약에서 확인했다. MAIN 채택 근거가 아니다.'),
 ('운영 결정·롤백 조건','운영 upstream·registry·ACTIVE 릴리스·원본 export 속성은 변경하지 않았다. 연구 runner만 frozen 후보를 직접 import한다. 실패/성공 기록 모두 보존하며 후속 모델/프롬프트 수정·재실행은 새 ADR에서 진행한다. 부모 ADR0489 결과를 소급 변경하지 않았다.'),
 ('재현 명령','완료 출력을 덮어쓰지 않고 새 ADR에서 frozen parent/revision으로 반복한다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+str(A.relative_to(R))+' --final`\n\n[질문별 전체 입출력](실험/README.md) · [상세 지표](artifacts/metrics.json) · [원문/오류 감사](artifacts/execution-audit.json) · [사전 기준](PLAN.md)')]
 front=(A/'README.md').read_text().split('---',2)[1];(A/'README.md').write_text('---'+front+'---\n\n# ADR-0490: 최종 packing·검토 ID 연결 수정 Qwen\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{body}' for i,(h,body) in enumerate(sections,1))+'\n')
 (A/'실험/README.md').write_text('# 신규 수정후보 / 상속기준 비교\n\n'+table+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']}) — 제품/평가 원문과 정확한 원장" for q in m['questions'])+'\n')
 for q in m['questions']:
  p=A/'실험'/q['file'];s=p.read_text().replace('ADR-0490, run-001·run-002, v3와 v4 모두 신규 실제 Qwen 호출.','ADR-0490, run-001: 기준은 ADR0489/run-002/source-workflow 상속, repaired만 신규 실제 Qwen 호출.');p.write_text(s)
if __name__=='__main__':main()
