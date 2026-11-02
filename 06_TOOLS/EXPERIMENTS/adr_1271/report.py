"""Final user-facing report from preserved experiment receipts."""
from common import *
out=ROOT/'09_ARTIFACTS/AUDITS/20261102-agent-loop-qwen-recovery'
v=read(RUN/'result.json');tests=read(ART/'working-full-recovery-002/result.json')
experiments=[]
for number in (1266,1268,1269,1270,1271):
 p=next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{number}-*'))/'artifacts/run-001/result.json'
 experiments.append({'adr':number,'path':str(p.relative_to(ROOT)),'sha256':sha(p),'result':read(p)})
summary={'selected_release':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'working_code_binding':read(ART/'post-integration-code-binding.json'),
 'final_tests':{k:tests[k] for k in ('passed','failed','exit_code','elapsed_seconds','code_unchanged','active_pointer_unchanged')},
 'live_fault_verification':v,'experiments':experiments,'main_promoted':False,
 'limits':['SQLite synthetic originals for three injected-fault cells; Oracle/NFS/GENOS not tested',
           'Actual assessment contract rejection and provider UNKNOWN remain possible',
           'Related loop test suite, not every repository test or legal quality benchmark']}
put(out/'final-summary.json',summary)
rows='\n'.join(f"- {c['case_id']}: {c['status']}, HTTP{c['http_status']}, 실제 {c['metrics']['physical_calls']}호출, {c['seconds']:.3f}초, 재조회 추가호출 {c['metrics']['duplicate']['extra_model_calls']}회" for c in v['cells'])
report=f'''에이전트 루프 수정 및 실제 Qwen 검증 — 2026-11-02

결론
확인된 코드 결함을 작업 코드에 수정했고, 실제 Qwen 응답에 중복선택·충돌선택·잘린 JSON을 주입한 세 사례 모두 보완 → 원문 검토 → 최종 답변 저장 → 동일 요청 재조회까지 통과했다.
그러나 모든 422가 사라진 것은 아니다. 실제 근거 연결을 끝내지 못한 최종 검토의 422와 공급자 응답 기한 종료의 504는 별도 남은 조건이다. 안전 중단을 답변 복구 성공으로 세지 않았다.

수정 내용과 반영 범위
1. 앞선 오류 처리·복구 변경: 응답 결속 거절에서 미정의 예외 참조로 원인을 가리는 문제, 종료/UNKNOWN 요청의 재전송, session→investigation 소유권 전이 틈을 보완했다.
2. ADR1267: v6/v7 선택 계약에 v8 source_ref가 들어가던 오류를 수정. 구형 DEPENDENCY는 모델이 고른 현재 전달 원문의 정확한 본문으로 source_quote를 결속하며 v8은 유지한다. 제품1+pin37=38파일.
3. ADR1271: 모델에게 보이는 body:제1조 좌표를 제1조만 허용하는 검증기가 거절하던 오류를 수정. 접두사와 coordinate_scope가 정확히 같을 때만 정규화한다. 범위 충돌·여러 조문·불완전 좌표는 구조화된 보완 오류로 거절하고 원문·권한 검증은 유지한다. 제품1+pin31=32파일.
작업 코드와 마지막 실제 검증 후보518파일 해시 동일. 선택 MAIN130/oracle-progress-dedup-20261031-r1은 변경하지 않았다. 작업 수정과 선택 릴리스 반영은 다르다. GENOS 배포/Oracle 변경/DDL/Git push/메일0.

최종 회귀 검사
작업 코드의 관련 에이전트 루프 통합 검사: {tests['passed']}통과/{tests['failed']}실패, {tests['elapsed_seconds']:.3f}초. 하나의 실행 결과이며 코드·선택 포인터 변경0.
종전589개 분할 통과와 추가 후보71개는 겹치는 검사를 포함하므로 합쳐서 독립 표본 수로 세지 않는다. 이번 통합 목록은 전체 저장소의 모든 테스트가 아니다.
현재 전체 기능의 native API 복구, 구형 v6/v7/v8 호환, 중복·충돌·알 수 없는 대상·깨진 JSON, 판단/최종검토 보완, 결과불명·전송기 예외, 요청 재사용·입력 충돌·동시 소유권, 부분 읽기/도구 오류·원문/필요/범위 연결을 포함한다.
반복 판단 충돌의 제한 답변(claims=[]), 반복 최종검토 오류422, UNKNOWN504, 전송기 예외502는 정상적인 완전 답변과 분리한다. 동시 요청 검증은 모의 전송기의 실제 native API 검사이며 동시 실모델 부하 시험은 아니다.
재현: .venv/bin/python 06_TOOLS/maintenance/check_agent_loop_recovery.py --code-root /home/jin/8-AGENT --output <새로운_결과_디렉터리>

마지막 실제 Qwen 오류주입 검증(ADR1271)
모델 qwen/qwen3.8-27b, Parasail fp8, 실제 native /v1/rag/ask 전체 프로필. SQLite 고정 합성3조문·온톨로지OFF. 공급자 원본과 실험이 변경한 응답을 각각 해시로 보존했다. 최초 오류는 실험에서 넣었으며, 보완·그 이후 판단은 실제 Qwen 응답이다.
{rows}
총 {v['physical_model_calls']}물리 호출, UNKNOWN0, 보고 비용 ${v['reported_cost_usd']:.8f}. 세 답변 모두 저장·동일답변 재조회·추가 호출0. 확보 원문12대조/전달28대조, 불일치·권한 위반·전송 재구성 불일치0. 자원중단0·관측 swap증가0. 실제 Oracle/NFS/GENOS 및 법률 품질·운영 오류율 인증은 아니다.

앞선 실패와 남은 문제 — 원본을 성공으로 덮어쓰지 않았다
- ADR1266 실제 공개 법률 원문: 최종 검토 최초 오류를 실제 모델 보완으로 해결, 기본 요청HTTP200/500자. 10물리(정상9/4291),371.820초,$0.03083913. 다만 초기 실험 전송 승인 객체의 재조회 검증 오류로 재조회500/추가모델0, 전체 실험Rejected. 이후 실험 연결기를 바로잡았다.
- ADR1268: 두 번째 호출 HTTP200헤더 뒤 공백만 수신하여179.924초 기한 종료/UNKNOWN, 전체504. 재조회504/추가모델0, 주입 도달 전 종료. 2물리/230.935초, 보고$0.00211704, UNKNOWN 사용량 미보고. 같은 UNKNOWN 셀 재전송0.
- ADR1269: FULLTEXT가 원문을 먼저 확보하여 READ 주입이 일어나지 않았다. HTTP200 두 번, 자연적인 최종 NEED_TARGET_CLAIM_LINK 오류422 한 번. 23물리/$0.048214974. 성공답변2개를 오류주입 복구로 세지 않음. 모두 재조회 추가모델0.
- ADR1270: 세 주입 모두 실제 보완까지 도달했지만 body:제1조의 후속 좌표 거절로 각422. 9물리/$0.01681156. 이 실패에서 ADR1271 수정 가설을 만들었다.
- 과거 감사의 모델 예산 합계는 재조회 journal에 복원된 누적 예산을 중복 합산했다. 실제 물리 요청·attempt 행·누적 예산 최댓값으로 다시 확인한7감사 모두 일치, 재조회 추가모델0. 원래 감사는 보존하고 budget-accounting-correction.json으로 정정 관계를 남겼다.
- 첫 작업 반영 검사는 projection 모듈과 같은 pin37을 예상했으나 source_goal 모듈은 pin31이어서 쓰기 전에 차단했다. 반영 전 잘못 시작한 검사는 중단해 보존하고, 정확한 변경32파일을 확인한 뒤 현재 최종 통합 검사를 별도로 실행했다.

남은 한계
모델이 보완 후에도 필요-원문-주장 연결을 만들지 못하면 검증을 느슨하게 해서200으로 바꾸지 않고422로 종료한다. 공급자 UNKNOWN은 안전하게504로 남기고 같은 요청을 자동 재전송하지 않는다. 이 두 상황을 없앴다고 주장하지 않는다.
실험 간 질문·원문·모델 경로가 다르므로 전체 성공률이나 속도 개선율을 합산하지 않는다. 실제 Qwen3사례는 합성 원문의 기술 검증이며 실제 법률 전체 질문의 정확성 검증과 다르다.

근거
04_EXPERIMENTS/ADR/ADR-1267-legacy-selection-contract-repair
04_EXPERIMENTS/ADR/ADR-1271-source-goal-coordinate-recovery
04_EXPERIMENTS/ADR/ADR-1271-source-goal-coordinate-recovery/artifacts/working-full-recovery-002/result.json
04_EXPERIMENTS/ADR/ADR-1271-source-goal-coordinate-recovery/artifacts/run-001/result.json
09_ARTIFACTS/AUDITS/20261102-agent-loop-qwen-recovery/final-summary.json
'''
(out/'수정과_실제실험_결과.txt').write_text(report)
print('Wrote final report;',tests['passed'],'tests;',v['fault_cases_passed'],'live recovery cases')
