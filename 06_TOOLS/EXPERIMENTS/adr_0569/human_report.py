"""Render the new measured comparison; no product changes or model calls."""
from pathlib import Path
import json

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0569-compact-plan-smallpool'
O = A / 'artifacts/run-001'


def main():
    read = lambda p:json.loads(p.read_text())
    grade = read(O/'offline-grade.json'); audit = read(O/'phase-gate-audit.json'); data = read(O/'result.json')
    arms = ['baseline','compact','combined']; titles = ['이전 구현 재실행','개념 ID 최소 출력','최소 출력 + 소형 원문 단일 선별']
    rows = []
    def row(label, values): rows.append('| '+label+' | '+' | '.join(str(v) for v in values)+' |')
    row('질문·반복', ['7개·1회']*3)
    row('정상 완료 / 외부 호출 실패', [f"{sum(r['status']=='ANSWER' for r in data['results'] if r['arm']==a)} / {sum(r['status']=='ERROR' for r in data['results'] if r['arm']==a)}" for a in arms])
    row('전체 모델 호출', [grade['usage'][a]['calls'] for a in arms])
    row('목적 판별 추가 호출', [audit['totals'][a]['phases'].get('purpose-recognition',{}).get('calls',0) for a in arms])
    row('계획 출력 토큰', [audit['totals'][a]['phases']['source-query-plan']['output_tokens'] for a in arms])
    row('계획 생성 평균(초)', [round(audit['totals'][a]['phases']['source-query-plan']['seconds']/7,2) for a in arms])
    row('선별·누락 검토 평균(초)', [round(sum(p['seconds'] for name,p in audit['totals'][a]['phases'].items() if name in ['source-triage','source-omission-review'])/7,2) for a in arms])
    row('최종 답변 생성 평균(초)', [round(audit['totals'][a]['phases'].get('answer',{}).get('seconds',0)/7,2) for a in arms])
    row('전체 평균(초, 실패 시간 포함)', [round(audit['totals'][a]['mean_seconds'],2) for a in arms])
    row('세 구현 모두 정상 완료한6개 평균(초)', [round(audit['supplemental_common_completed_cases'][a]['mean_seconds'],2) for a in arms])
    row('전체 p50/p95(초)', [f"{audit['totals'][a]['p50']:.2f}/{audit['totals'][a]['p95']:.2f}" for a in arms])
    row('모델 입력 토큰', [grade['usage'][a]['input_tokens'] for a in arms])
    row('모델 출력 토큰', [grade['usage'][a]['output_tokens'] for a in arms])
    row('실제 청구 비용(USD)', [f"{grade['usage'][a]['cost_usd']:.8f}" for a in arms])
    row('원문 회수 합계', [grade['by_arm'][a]['read_roots'] for a in arms])
    row('원문·인용·답변 기준', [f"{grade['by_arm'][a]['correct']}/7" for a in arms])
    case_rows = []
    for case_id in ['APP-01','APP-02','APP-03','INV-01','PERF-01','MIX-01','DRIFT-01']:
        rs = [next(r for r in data['results'] if r['case_id']==case_id and r['arm']==a) for a in arms]
        case_rows.append('| '+case_id+' | '+' | '.join(f"{r['seconds']:.2f}초 / {r['model_calls']}회" for r in rs)+' |')
    failed = [g for g in grade['grades'] if not g['pass']]
    fail_text = '\n'.join(f"- {g['case_id']} / {g['arm']}: 제시 누락 {g['missing_presented']}, 인용 누락 {g['missing_cited']}, 답변 용어 누락 {g['missing_answer_terms']}." for g in failed) or '동결한 기준에 실패한 사례가 없다.'
    outcome = '충족' if audit['all_gates_passed'] else '미충족'
    text = f'''# 계획 출력과 원문 선별 호출 줄이기 — ADR-0569

기존 계획의 중복 설명을 개념 ID 배열로 바꾸고, 회수한 원문 후보 전부를 한 번에 읽을 수 있을 때 선별·누락 점검을 합쳤다. 세 구현을 동일한 합성 원문55개·질문7개로 실제 새 실행했다. 사전 동결 게이트는 {outcome}이다. 운영 MAIN은 변경하지 않았다.

## 구현

계획에는 기존 `queries`와 같은 순서의 `query_concepts`만 추가한다. 분기 이유는 기존 `reason`을 사용하며 query/reason/expected_information 객체를 검색마다 다시 생성하지 않는다. 빈 개념은 미확인으로 처리하고, DB에서 목적별 제외 관계를 컴파일한다. FTS SQL·READ guard·recall·graph는 부모 ADR0568과 바이트 동일하다.

단일 선별은 구조 전용 경로가 아니며, 후보1~16개 모두 완독했고 원문 합계16000자 이하, 실제 입력 직렬화80000자 이하일 때 사용한다. 첫 선별 호출에 후보 전부의 전체 원문을 전달해 정의·예외·위임·수치와 질문 요구의 누락도 함께 판단한다. 나머지 경로는 기존 제목·경로 선별 이후 원문 기반 누락 검토를 유지한다.

전체 후보를 제시했다는 것은 해당 후보 묶음의 입력 완전성 조건이다. 전체 corpus에서 필요한 문서를 모두 찾았다거나 모델의 법률 판단이 틀리지 않는다는 증명이 아니다. 단일 선별 대상에서는 두 번째 모델 검토를 생략한다.

## 실제 결과

기준은 ADR0568의 integrated를 이번에 다시 실행한 것이다. 지난 실험의 시간이나 현재 MAIN의 시간과 섞어 비교하지 않았다.

| 지표 | {' | '.join(titles)} |
|---|---:|---:|---:|
{chr(10).join(rows)}

| 질문 | {' | '.join(titles)} |
|---|---:|---:|---:|
{chr(10).join(case_rows)}

통합 후보의 마지막 DRIFT-01 계획 호출은 Parasail/OpenRouter HTTP503으로 실패했다. 실패의0.64초를 평균에 넣은 전체 시간 감소율 {audit['paired'][1]['wall_reduction']:.1%}와 비용 감소율 {audit['paired'][1]['cost_reduction']:.1%}는 성능 개선 근거로 사용하지 않는다. 실패가 없었던 세 구현 공통 완료6개만의 보조 비교에서는 평균 시간 감소율이 {audit['supplemental_common_completed_wall_reduction']:.1%}였다. 이는 원래7개 사전 게이트의 통과를 대신하지 않는다.

입력·출력 토큰, 단계별 실제 왕복 시간, 답변 원값을 함께 보존했다. 비용은 캐시 영향을 포함하며 응답 생성 시간도 외부 서비스 변동의 영향을 받는다. 단일 반복 결과를 현장 성능 인증으로 해석하지 않는다.

## 게이트·근거 보존

```json
{json.dumps(audit['gates'],ensure_ascii=False,indent=2)}
```

계약 테스트 {audit['contracts']['passed']}/{audit['contracts']['total']} 통과. 실제 provider 요청에 소형 후보 전체 원문이 전달됐는지도 검사했다. 미완독·큰 원문·많은 후보·직렬화 초과는 검토 생략을 막고, 구조 기반 추가 검색 판단과 후보 ID 검증을 유지한다. 변경하지 않은 graph/SQL/READ/recall은 부모와 해시 동일하며 부모의14개 계약 검증 이력을 연결한다.

부모의 gold를 바이트 그대로 사용했으며 결과 이후 기준을 완화하지 않았다. 최종 답변 입력의 근거 보존과 실제 답변 인용은 구분해 채점했다.

{fail_text}

## 해석 범위

개념 ID 최소 출력은 기존 판단에 대한 짧은 맥락 참조다. 후보 전체를 먼저 읽는 단일 선별은 기존 두 호출에서 나눠 하던 일을 한 호출에 묶는다. 원문은 이미 native READ에서 회수했고, 여기서는 모델이 실제로 읽는 시점과 입력 범위를 바꿨다.

큰 후보·복합 질문·버전 변경 사례는 원문 후보가 많아 기존 누락 검토가 유지된다. 여기서 회수 판단이나 리뷰를 더 줄이는 정책은 별도 검증 대상이다. 이번 실험은 native 계획 프롬프트/계약, SourceRecall 두 분기, READ, source_selection을 연구 runner에서 호출했다. 전체 서비스 API·기본 Compose·자동 로그 학습·실제 내부 자료·GENOS를 실행하지 않았다. 목록 모드는 native browse 후 공통 예시 원문 검색으로 계속했다.

반복 수1, 합성 질문7개, 수작업 개념 관계이므로 일반화와 현장 부하·품질은 미확인이다. 세 arm 순서를 질문별로 순환했지만 모델 출력 차이·캐시·외부 대기시간을 완전히 통제하지는 못했다. 결과를 보고 만든 후속 변경은 새 ADR에서 검증해야 한다.

## 근거

- [설계·판정]({A}/README.md)
- [계보·동결 입력·실행 manifest]({A}/실험/manifest.json)
- [단계별 시간·호출 수·게이트]({O}/phase-gate-audit.json)
- [원문·인용·답변 채점]({O}/offline-grade.json)
'''
    p = R/'07_DOCS/REFERENCE/REPORTS/COMPACT_PLAN_SMALLPOOL_20260930.md'
    p.write_text(text)
    print(p)


if __name__=='__main__':main()
