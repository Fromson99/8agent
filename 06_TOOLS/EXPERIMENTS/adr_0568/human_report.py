"""Render measured results and integration boundaries, without product imports."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql'
OUT = ADR / 'artifacts/run-001'


def read(path):
    return json.loads(path.read_text())


def main():
    grade = read(OUT / 'offline-grade.json')
    audit = read(OUT / 'action-scope-audit.json')
    data = read(OUT / 'result.json')
    b, c = 'baseline', 'integrated'
    metrics = [
        ('추가 목적 판별 호출', 0, audit['totals'][c]['standalone_purpose_calls']),
        ('전체 모델 호출', grade['usage'][b]['calls'], grade['usage'][c]['calls']),
        ('원문 회수 합계', grade['by_arm'][b]['read_roots'], grade['by_arm'][c]['read_roots']),
        ('규정 질문 3개 원문 회수', grade['by_arm'][b]['app_read_roots'], grade['by_arm'][c]['app_read_roots']),
        ('검색 SQL 실행 횟수', audit['totals'][b]['executed_rank_calls'], audit['totals'][c]['executed_rank_calls']),
        ('검색 SQL에서 가져온 행', audit['totals'][b]['fetched_rows'], audit['totals'][c]['fetched_rows']),
        ('검색 SQL 시간 합계(초)', round(audit['totals'][b]['sql_seconds'], 5), round(audit['totals'][c]['sql_seconds'], 5)),
        ('모델 입력 토큰', grade['usage'][b]['input_tokens'], grade['usage'][c]['input_tokens']),
        ('모델 출력 토큰', grade['usage'][b]['output_tokens'], grade['usage'][c]['output_tokens']),
        ('실제 청구 비용(USD)', f"{grade['usage'][b]['cost_usd']:.8f}", f"{grade['usage'][c]['cost_usd']:.8f}"),
        ('질문당 평균 시간(초)', round(grade['latency'][b]['mean_seconds'], 2), round(grade['latency'][c]['mean_seconds'], 2)),
        ('계획 단계 시간 합계(초)', round(audit['totals'][b]['plan_seconds'], 2), round(audit['totals'][c]['plan_seconds'], 2)),
        ('계획 입력 토큰', audit['totals'][b]['planner_input_tokens'], audit['totals'][c]['planner_input_tokens']),
        ('계획 출력 토큰', audit['totals'][b]['planner_output_tokens'], audit['totals'][c]['planner_output_tokens']),
        ('동결한 원문·인용·답변 용어 기준', f"{grade['by_arm'][b]['correct']}/7", f"{grade['by_arm'][c]['correct']}/7"),
    ]
    rows = '\n'.join(f'| {name} | {before} | {after} |' for name, before, after in metrics)
    cases = []
    for cid in ['APP-01', 'APP-02', 'APP-03', 'INV-01', 'PERF-01', 'MIX-01', 'DRIFT-01']:
        rs = {r['arm']: r for r in data['results'] if r['case_id'] == cid}
        gs = {g['arm']: g for g in grade['grades'] if g['case_id'] == cid}
        cases.append(f"| {cid} | {len(rs[b].get('read_ids', []))} → {len(rs[c].get('read_ids', []))} | "
            f"{rs[b]['seconds']:.2f} → {rs[c]['seconds']:.2f} | "
            f"{'통과' if gs[b]['pass'] else '미통과'} → {'통과' if gs[c]['pass'] else '미통과'} |")
    actions = '\n'.join(f"| {a['action']['query']} | {','.join(a['action']['concept_refs'])} | "
        f"{a['allowed_count']} | {'허용' if a['c_allowed'] else '제외'} |" for a in audit['mixed_actions'])
    failures = [g for g in grade['grades'] if not g['pass']]
    error_text = '\n'.join(f"- {g['case_id']} / {g['arm']}: 필수 제시 누락 {g['missing_presented']}, "
        f"필수 인용 누락 {g['missing_cited']}, 필수 답변 용어 누락 {g['missing_answer_terms']}." for g in failures) or '모든 사례가 동결한 기준을 통과했다.'
    text = f'''# 기존 검색 계획에 개념을 연결한 실험 — ADR-0568

로컬 합성 원문 55개, 질문 7개를 기준·후보 각각 한 번 실행했다. 별도 목적 판별 호출 없이 기존 계획에서 검색 행동별 개념을 생성하고, DB 관계를 컴파일해 검색 SQL 실행 전에 적용했다. 개념 제약 기능 판정은 {'통과' if audit['scope_success'] else '미통과'}다. 전체 속도 개선 여부는 아래 실제 측정값으로 구분한다.

## 실행한 구조

`기존 catalogue 계획 호출 → 검색 행동별 concept_refs → DB EXCLUDES/INSTANCE_OF 관계 → 허용 원문 좌표 → backend rowid projection → FTS SQL → native READ·선별 → 연구용 답변 호출`

후보는 계획의 각 검색 행동에 `concept_refs`, 이유, 기대 정보를 함께 출력한다. 개념 ID 선택은 이 모델 호출에서 수행한다. 제외 관계는 프롬프트에 C 금지 목록으로 적지 않고 DB에 둔다. 이번 관계는 `적용규정 확인 --EXCLUDES--> 실적 자료`, 원문 노드는 `INSTANCE_OF 실적 자료`다. 검색 이유가 바뀌면 다른 개념을 선택할 수 있다.

실제 변경한 SQL에는 `MATCH`와 함께 `rowid IN (...)`을 전달한다. 검색된 행을 Python에서 버리는 시점보다 앞에서 제약이 작동한다. 동일한 논리 원문 좌표를 공통 READ 검증에도 사용해 직접 읽기와 상위 노드 읽기로 우회할 수 없게 했다. 복합 질문의 READ 허용 범위는 개별 검색 목적의 합집합이므로 실적 목적에서 합법적으로 회수한 자료는 읽을 수 있다.

## 측정 결과

| 지표 | 기준 | 후보 |
|---|---:|---:|
{rows}

규정 질문의 원문 회수 감소율은 {grade['app_read_reduction']:.1%}다. 전체 시간 감소율은 {grade['wall_reduction']:.1%}, 비용 감소율은 {grade['cost_reduction']:.1%}다. 음수는 증가를 뜻한다. 비용은 응답의 실제 청구값이며 캐시 영향을 포함한다. 단일 반복·교대 순서이며 외부 모델 지연과 캐시를 통제한 성능 인증이 아니다.

| 질문 | 원문 회수 기준 → 후보 | 시간(초) 기준 → 후보 | 동결 기준 판정 기준 → 후보 |
|---|---:|---:|---|
{chr(10).join(cases)}

계획 출력에 검색어·이유·기대 정보를 추가하면서 출력 토큰이 늘었다. 추가 호출 0회가 추가 처리 시간 0초를 뜻하지는 않는다. 이번 SQL 실행 계획에서는 후보에 임시 ORDER BY 정렬도 생겼다. 읽을 행을 줄이는 효과와 검색 엔진의 실제 계산 비용을 같은 것으로 해석하면 안 된다.

## 복합 질문과 제약 해제

MIX-01 실제 계획에서 규정과 실적에 서로 다른 개념을 선택했는지 검사한 결과: {audit['mixed_action_scopes_passed']}.

| 실제 검색 행동 | 개념 | 허용 원문 수 | 실적 자료 C |
|---|---|---:|---|
{actions}

복합 질문 전체와 자동 생성된 목적 미확인 검색 변형은 보수적으로 전체 허용 범위를 사용한다. 따라서 복합 질문의 모든 탐색이 줄어드는 구현은 아니다. 검색 변형까지 부모 행동의 개념을 일관되게 이어주는 계약은 후속 작업이다.

문서 내용·버전이 바뀐 DRIFT-01에서 분류 근거를 재검토하도록 제외 제약을 해제했는지: {audit['drift_fallback_observed']}. 알 수 없는 개념·충돌하는 개념에는 hard 제외를 적용하지 않는다. 지원하지 않는 ID는 계획 검증에서 거부한다.

## 품질과 검증

필수 원문이 최종 답변 입력에 모두 제시되었는지: {audit['required_originals_presented100']}. 후보만의 동결 기준 실패 수: {audit['paired']['baseline_only_correct']}. 검색 SQL 반환값이 전달한 허용 좌표 안에 있는지: {audit['sql_scope_applied']}.

원문 제시와 최종 답변 인용을 구분했다. 부모 실험의 gold를 바이트 그대로 사용했으며, 결과를 보고 기준을 완화하지 않았다.

{error_text}

계약 테스트 {audit['contracts']['passed']}/{audit['contracts']['total']} 통과. 복합·미확인·충돌·버전 변경·우회 READ와 동일 검색어의 BM25 순서 및 동점 처리를 검사했다. 실제 모델 호출은 양쪽 기존 catalogue 계획과 native source_selection을 사용했고, native SourceRecall 두 분기와 READ를 실행했다.

## 확인 범위와 다음 구현 방향

개념·자료 분류·제외 관계는 수작업 합성이다. 실제 사용자 로그를 밤에 모아 개념으로 묶는 학습은 실행하지 않았다. 기존 계획 프롬프트와 계약을 연구 runner에서 호출했으며 전체 BoundedSourceSession/서비스 API/기본 Compose는 실행하지 않았다. 목록 모드는 native browse 이후 양쪽 공통 원문 예시 검색으로 계속했다. 다른 검색 backend의 공통 scope 소비는 모의 계약만 검증했으며 실제 ANN·벡터 backend 연동은 미구현이다.

기준과 후보의 검색 계획 자체도 달라지므로 전체 SQL 행 감소를 rowid 제약 하나의 효과로만 귀속할 수 없다. 동일 검색어·동일 허용 좌표의 별도 native 계약 검사로 SQL 제약과 기존 BM25 순위 보존을 확인했다. 소형 rowid 목록 구현은 대규모 인덱스에서 별도 부하 확인이 필요하다.

후속 후보에서는 기존 행동의 이유·기대 정보를 재사용하고 개념 ID만 추가하는 방향으로 계획 출력 비용을 줄일 수 있다. 이번 결과를 보고 만든 변경은 새 ADR에서 검증해야 한다. MAIN·generation31·운영 registry·GENOS는 변경하지 않았다.

## 근거

- [실험 설계와 판정](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql/README.md)
- [동결한 계보·입력·실행 manifest](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql/실험/manifest.json)
- [행동별 제약과 SQL 단계 분석](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql/artifacts/run-001/action-scope-audit.json)
- [원문·인용·답변 기준 판정](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql/artifacts/run-001/offline-grade.json)
'''
    path = ROOT / '07_DOCS/REFERENCE/REPORTS/INTEGRATED_ACTION_CONCEPT_SCOPE_20260930.md'
    path.write_text(text)
    print(path)


if __name__ == '__main__':
    main()
