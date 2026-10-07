"""Write the user-facing table from completed audited selection results."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0516-provenance-frontier-selection'
s=json.loads((A/'artifacts/summary.json').read_text());t=s['totals']
c=json.loads((A/'artifacts/completion.json').read_text())
report=R/'07_DOCS/REFERENCE/REPORTS/LEGAL_SEARCH_PROVENANCE_SELECTION_20260922.md'
report.write_text(f'''# 회수 경로 기반 후보 선별 결과

공개145문서·기존61문항. 확보한 원문 풀을 유지하면서, Gemma가 내용과 회수 경로로 후단 후보를 선별했다. **필수 원문 보존 {t['gold_final']}/90, 후보 평균 {t['baseline_count_mean']:.1f} → {t['final_count_mean']:.1f}개.** 사전 기준 통과: {s['criteria_met']}. MAIN·GENOS 미반영.

|단계|후보|필수 원문 보존|동작|
|---|---:|---:|---|
|원문 확보 풀|평균 {t['baseline_count_mean']:.1f}|90/90|ADR0513의 전역·법령별 검색 합집합과 전문 읽기 결과를 고정 재사용|
|Gemma 1차 선별|문항당 최대16|{t['gold_first']}/90|쟁점·목차·회수 경로를 보고 읽을 조문 선택|
|누락 점검 후|평균 {t['final_count_mean']:.1f}, 최대 {t['final_count_max']}|{t['gold_final']}/90|선택 원문1200자 이내 발췌와 보류 목차·경로를 재검토해 최대8개 복구|

## 판단에 넣은 회수 이력

|정보|사용 방법|구분해야 할 점|
|---|---|---|
|검색어·검색 방식·순위|어느 쟁점에서 어떤 검색으로 발견됐는지 확인|순위가 높다고 법적 적용이 확정되지 않음|
|출발 조문·정/역참조·해소 상태|질문→검색어→출발 조문→후속 조문의 경로를 추적|역참조 방향과 미해결 좌표 후보를 구분|
|같은 원문의 재발견|서로 다른 검색어나 참조 경로에서 다시 나왔는지 확인|같은 query/edge의 global/scoped 반복은 독립 근거로 중복 계산하지 않음|
|원문 구간|경로가 가리키는 조문이 실제 질문과 관련 있는지 확인|초기 본문 없음, 선택 후 최대1200자 발췌이며 일부만 보인 원문을 없다고 판단하지 않도록 지시|
|선택·보류 상태|선택에는 모델의 쟁점·내용·경로 기반 이유를 보존|미선택은 복구 가능한 보류 상태이며 개별 무관 판정이 아님|

원시 경로·원문·해시는 서버 기록에 보존했다. 모델에는 문서/검색어 사전과 번호 기반의 행을 전달했다. 경로만으로 중요도를 고정 점수화하거나, 많이 나온 조문을 자동 채택하지 않았다. 회수 경로 없는 대조군은 실행하지 않았으므로 경로 자체의 독립 기여는 미측정이다.

## 실행 결과

- 전체61문항 중 모든 필수 근거를 남긴 문항: {t['all_gold_retained_cases']}/61. 누락 점검에서 복구한 필수 원문: {t['gold_recovered']}개.
- Gemma 실제 호출 {t['physical_calls']}회, 입력 {t['input_tokens']:,}·출력 {t['output_tokens']:,} tokens, 기록된 비용 ${t['cost_usd']:.6f}.
- 선별 시간 p50/p95: {t['selection_p50']:.1f}/{t['selection_p95']:.1f}초. **부모 검색 기록+현재 선별 합산** p50/p95: {t['composed_p50']:.1f}/{t['composed_p95']:.1f}초. 서로 다른 시점의 측정 합계이며 새 실제 종단 지연이 아니다. 자원 로딩·검색 계획·최종 답변 생성은 제외된다.
- 오류 문항 {t['error_cases']}개. 계약 검사10개 통과. 최종 ADR 정합성 검사 통과: {c['validation_passed']}.
- 초기 선별 모델은 전체 후보의 목차·회수 경로만 본다. 줄어든 숫자는 최종 답변용으로 준비한 후보 수이며, 이번 최종 답변 모델 호출은0회다.

사전 통과 기준은 **90/90 유지, 문항별24개 이하·평균20개 이하, 오류0, 합산 p95 240초 이내**였다. 미달이면 원문 회수 부모를 유지하고 이 선별 후보를 채택하지 않는다. 이 문항들은 실패 분석에 이미 사용한 인샘플이며 새 질문이나 실제 내부 데이터에서의 성능을 보장하지 않는다.

## 이전 장문 경로 실험

ADR0514는 첫 완료 문항에서233→4개로 줄였지만 선별에263초가 걸려 중단했다. 나머지 진행 호출의 최종 사용량은 미확인이고61문항 전수 성능은 집계하지 않았다. 중단 기록의 최종 표준 검사도 통과하지 않았다. ADR0515도 전체 보류 원문의 발췌를 다시 보여주다가 반복 시간초과로 중단했다. 이 실패 arm들을 부모로 삼지 않고 완료된 ADR0513 원문 풀에서 ADR0516을 분기했다.

## 코드와 원기록

- [최종 선별 ADR](../../../04_EXPERIMENTS/ADR/ADR-0516-provenance-frontier-selection/README.md)
- [61문항별 선별·누락 표](../../../04_EXPERIMENTS/ADR/ADR-0516-provenance-frontier-selection/실험/README.md)
- [선별 후보 코드](../../../02_BACKEND/lawrag/research/candidates/adr_0516/selection/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/source_selection.py)
- [원문 확보90/90 보고서](LEGAL_SEARCH_SOURCE_RECALL_20260922.md)

실행 경로는 격리 runner가 기존 원문 회수 결과의 evidence/packet/route를 소비하는 후단 단계다. 운영 API의 자동 호출·기본 모델·활성 릴리스는 변경하지 않았다. 최종 패킷은 원문 페이지·출처·세대·해시를 보존한 `PREPARED_NOT_SENT`다.
''')
index=R/'04_EXPERIMENTS/ADR/README.md';text=index.read_text()
if 'ADR-0516 목차·회수 경로 선별' not in text:
    index.write_text(text+f'\n- [ADR-0516 목차·회수 경로 선별](ADR-0516-provenance-frontier-selection/README.md) —61문항 필수 원문{t["gold_final"]}/90, 후보평균{t["baseline_count_mean"]:.1f}→{t["final_count_mean"]:.1f}; in-sample·MAIN 미반영.\n')
prior=R/'07_DOCS/REFERENCE/REPORTS/LEGAL_SEARCH_SOURCE_RECALL_20260922.md';text=prior.read_text()
if 'LEGAL_SEARCH_PROVENANCE_SELECTION_20260922.md' not in text:
    prior.write_text(text+'\n\n후속 후보 축소는 [회수 경로 기반 선별 결과](LEGAL_SEARCH_PROVENANCE_SELECTION_20260922.md)에 별도로 기록했다. 원문 확보와 후단 선별의 회수율을 구분한다.\n')
print(report)
