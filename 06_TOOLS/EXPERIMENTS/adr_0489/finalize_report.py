"""Describe final implementation and observed outcomes; never changes product or grading."""
import json
from pathlib import Path
import report
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0489-source-workflow-recovery-qwen'
def main():
 report.main()
 metric=json.loads((A/'artifacts/metrics.json').read_text());m=json.loads((A/'실험/manifest.json').read_text())
 b=metric['by_arm']['baseline'];c=metric['by_arm']['source-workflow']
 j=lambda v:'```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```'
 table='| 반복 | 질문 | 방식 | 발견 | 읽기 | 모델 전달 | 선택 | 게시 원문 | 게시 | 답변 일치 | 호출 |\n|---|---|---|---:|---:|---:|---:|---:|---|---|---:|\n'
 for x in metric['by_case']:
  row=json.loads((A/'artifacts'/x['run_id']/x['case_id']/x['arm']/'result.json').read_text());s=row['stages']
  table+='| '+' | '.join(map(str,[x['run_id'],x['case_id'],'기준 v4' if x['arm']=='baseline' else '개편 후보',*[len(s[k]) for k in ['discovered','read','presented','selected','final_sources']],x['publication_status'],x['correct'],x['calls']]))+' |\n'
 sections=[('결정 요약',f"격리 후보 구현과 Qwen CM3 × 2방식 × 2반복을 실행했다. 기준 v4 게시 {b['publication_success']}/6, 후보 게시 {c['publication_success']}/6. 저장 기준답 일치는 기준 {b['correct']}/6, 후보 {c['correct']}/6. 세부 판정은 아래와 같다. 전체 v5·48개 사례 구현 완료 또는 MAIN 승격을 뜻하지 않는다.\n\n"+j(metric['verdicts'])),
 ('문제와 변경 전 구조','발견을 진전으로 세지 않아 READ 전에 종료하고, 모델이 원문과 별도 좌표 ID를 연결하며, 유효 선택도 같은 응답의 다른 오류로 유실되는 구조였다. 게시에서는 원본 속성과 외부 실험 승인 값을 같은 필드로 비교했다. 이번 변경은 기존 retrieve/select/assemble/answer·journal·outbox를 연구 snapshot에서 연결해 사용한다.'),
 ('가설과 사전 판정 기준',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+j(metric['criteria'])),
 ('실험 설계','기준은 ADR0488의 동결 v4를 새 프로세스에서 실행했다. 후보는 별도99파일 snapshot 중7파일을 수정했다. 원질문·145개 공개문서 scope·generation·Qwen FP8 thinking off·온도0·출력2800·최대14호출/56도구/300초는 공통이다. 문항/반복별 arm 순서를 교대했다. 변경 묶음의 통합 비교이며 요소별 ablation은 없다. 결과 확인 뒤 모델 코드·prompt를 수정하거나 추가 실행하지 않았다.'),
 ('데이터·모델·재현성','공개 RAW 출처·문서 artifact·store·navigation·fulltext·모델 정책·실험별 승인과 frozen code hash를 호출 전에 확인했다. immutable export_allowed는 변경하지 않았다. 후보는 전송·게시에서 현재 grant 해시·모델·목적지·scope를 검사한다. 원질문에는 기준답을 넣지 않았다. 종료 후 Qwen 단회 익명 paired evaluator가 저장 기준답 일치와 출처 관련성을 분리 평가했다.\n\n[중간 검사와 구현 범위](IMPLEMENTATION.md): 후보16개 계약 통과, frozen revision에서16개 재확인, 실제145문서 초기화 사전 점검 양쪽0호출.'),
 ('결과',table+'\n\n'+j(metric['by_arm'])+'\n\n'+j(metric['paired_outcomes'])),
 ('사례별 오류 분석',j([{k:x[k] for k in ['run_id','case_id','arm','execution_error','publication_error','semantic_errors','limitations','phases']} for x in metric['by_case']])),
 ('비용·지연·회수 규모',j(m['results']['usage'])+'\n\n'+j(m['results']['latency'])+f"\n\ncanonical corpus {metric['corpus_total']}개. 내부 payload와 실제 게시를 분리한다. p95는6개 표본의 최댓값이며 현장 추정치가 아니다. 전체 wall에는 초기 자원 로딩이 포함되고 controller300초는 로딩 후 시작한다."),
 ('해석','선택 단순화·발견 진전·오류 복구·입력 구성·정책 연결의 실행성과 관련 조 선택·법률 답변 정확도를 구분한다. 선택된 E는 실제 모델 전달 범위 전체를 보존하며 선택이 법률 ADOPT를 의미하지 않는다. 항·호 강조를 모델에게 요구하지 않으므로 해당 좌표 매칭 오류는 이 프로토콜에서 발생하지 않는다. 다른 조를 잘못 고르는 의미 오류까지 제거했다는 뜻은 아니다.'),
 ('한계와 일반화 가능 범위','기존 실패를 본 CM3 인샘플이며 독립 holdout·사람 calibration·현행 법률 정당성 검증이 아니다. 원래48개 시나리오 전체는 미구현/부분구현 상태다. canonical 조 단위 병합·선택 대기 전체 순회·최소 oversized E 자동분할·오류 생명주기·전역 오류별 재시도·v5 journal·인증 resume·feedback·service bridge·GENOS는 남아 있다. 실제 공개 Qwen 실행은 FastAPI 바깥에서 동일 session/outbox를 호출하고, HTTP/원문 열기는 모의 계약에서 검사했다. 이 차이를 현장 end-to-end 성공으로 확대하지 않는다.'),
 ('운영 결정·롤백 조건','운영 upstream 코드·registry·활성 release·원본 세대는 변경하지 않았다. 후보는 명시 research runner만 불러온다. 제외하면 기존 경로로 돌아가며 완료 artifact는 보존한다. 후속 수정/재실행은 새 ADR, MAIN 승격은 별도 holdout/명시 승인 절차를 따른다.'),
 ('재현 명령','완료 출력은 덮어쓰지 않는다. 새 ADR에 부모와 동결 revision을 연결해 반복한다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+str(A.relative_to(R))+' --final`\n\n[질문별 전체 입출력](실험/README.md) · [단계/오류 측정](artifacts/metrics.json) · [구현 diff](artifacts/implementation.diff) · [48개 대응 범위](artifacts/coverage-map.json) · [사전 계획](PLAN.md)')]
 front=(A/'README.md').read_text().split('---',2)[1]
 (A/'README.md').write_text('---'+front+'---\n\n# ADR-0489: 원문 선택·진행·오류 복구 구현 및 Qwen 반복 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{body}' for i,(h,body) in enumerate(sections,1))+'\n')
 (A/'실험/README.md').write_text('# Qwen 기준 v4 / 개편 후보 반복 검증\n\n'+table+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']}) — 모든 run·arm 입력·원응답·채점·원장" for q in m['questions'])+'\n')
 for q in m['questions']:
  p=A/'실험'/q['file'];s=p.read_text().replace('v3와 v4 모두 신규 실제 Qwen 호출','기준 v4와 개편 후보 모두 신규 실제 Qwen 호출');p.write_text(s)
if __name__=='__main__':main()
