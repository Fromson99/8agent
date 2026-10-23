"""Post-run evidence audit. No product changes, scoring rerun, or model calls."""
from common import *

o = read(ART / 'observations.json')['by_arm']['candidate']
c = read(ART / 'cycle-review.json')
e = read(ART / 'execution-review.json')
p = ART / 'known-query/candidate'
old_path = ROOT / '04_EXPERIMENTS/ADR/ADR-1022-scope-first-grounded-navigation/artifacts'
old = read(old_path / 'observations.json')['by_arm']['candidate']
events = read(p / 'events-audit.json')
steps = [x['payload'] for x in events if x['kind'] == 'INVESTIGATION_CHAIN_STEP']
assert o['service_status'] == 200 and o['native_result']['error'] is None
assert o['native_result']['model_calls'] == len(o['native_result']['usage']) == 12
assert c['valid_observation'] and len(c['applied_connection_selections']) == 2
assert c['unchanged_repeat_count'] == 0 and not c['duplicate_directory_records']
assert not c['model_finish_calls']
assert o['outcome']['stop_reason'] == 'INVESTIGATION_BUDGET'
assert o['source_checks'] == {'count': 184, 'mismatches': 0, 'scope_violations': 0}
assert e['reference_model_calls'] == 0 and e['unsupported_gap_proposals'] == 0

metrics = {}
for key, before, after in [
    ('physical_calls', old['native_result']['model_calls'], o['native_result']['model_calls']),
    ('input_tokens', old['usage']['input_tokens'], o['usage']['input_tokens']),
    ('output_tokens', old['usage']['output_tokens'], o['usage']['output_tokens']),
    ('cost_usd', old['usage']['cost_usd'], o['usage']['cost_usd']),
    ('service_seconds', old['native_result']['seconds'], o['native_result']['seconds']),
]:
    metrics[key] = {'historical_ADR1022': before, 'ADR1026': after,
                    'change_percent': (after / before - 1) * 100}
save(ART / 'comparison-review.json', {
    'comparison_type': 'historical unpaired known-question observation; no causal estimate',
    'reference': str(old_path.relative_to(ROOT)),
    'metrics': metrics,
    'historical_four_call_cycle': read(old_path / 'repeated-scope-audit.json'),
    'current_cycle_observation': {'unchanged_repeat_count': 0, 'directory_operations': 2},
    'current_actions': [{'number': s['number'], 'action': s['action'],
                         'targets': [t['label'] for t in s['targets']],
                         'reason': s['reason']} for s in steps],
})

# Compare generated wording with the exact supplied source, not external current law.
members = [t['identity']['connection_scope']['members']
           for s in steps if s['action'] == 'FOLLOW_CONNECTION'
           for t in s['targets'] if '제97조' in t['label']][0]
source = [span for member in members for span in member['spans']
          if span['block_id'] in ('1202', '1203', '1204')]
assert len(source) == 3
assessment = json.loads(read(p / 'model/call-011-service/response.json')['choices'][0]['message']['content'])
claim = assessment['claims'][4]['rule']
answer_paragraph = next(x for x in o['answer'].split('\n\n') if x.startswith('필요경비의 합산 방법'))
save(ART / 'answer-wording-review.json', {
    'scope': 'Post-run textual comparison against supplied frozen source only; not full legal grading.',
    'source': {'document_id': '61789e1949a9e2cd', 'article': '제97조 제2항 제2호', 'spans': source},
    'assessment_norm': claim['norms'][1]['text'],
    'assessment_exception': claim['exceptions'][0]['text'],
    'answer_paragraph': answer_paragraph,
    'finding': '원문 가목의 비교항은 환산취득가액 + 대통령령으로 정하는 금액이다. ASSESS 예외문은 환산취득가액을 누락하고, COMPOSE 답변은 이를 대통령령 금액 + 자본적지출액·양도비 합계로 바꿨다. 원문 확보·해시 일치만으로 생성 해석의 정확성이 보장되지 않는다.',
})

review = {
    'verdict': '연결 목록 반복0회·답변 생성 완료, 자발적 종료·호출/토큰 개선 기준 미달',
    'criteria_met': False,
    'user_problem_fully_resolved': False,
    'reference_model_calls': 0,
    'findings': [
        '사용자 재실행 요청에 따라 ADR1023 최종 검증본과 동일한 후보501파일을 ADR1026에 동결했다. 코드·프롬프트·질문·데이터·모델·예산 변경 없이 실제 서비스 진입점으로1회 실행했다. Qwen3.8/Parasail FP8, reasoning none, fallback 없음, transport retry0이다.',
        '이번에는12회 모델 호출이 모두 정상 응답했다. HTTP200, 서비스346.990860초, 전체 guard363.365366초, peak RSS3,393,458,176bytes. 입력939,172·출력6,943토큰, provider 보고 비용$0.24067588이며 사용량12/12회가 기록됐다.',
        '실제 연결 목록 조회는92조②1과97조 전체의 서로 다른2범위다. 동일 범위 반복 실행0회, 중복 directory receipt0개였다. scope_selection_count8과 catalog_count8은 원문 읽기 시 범위 재결속·근거 재검증을 포함하므로 연결 목록8회 왕복으로 세지 않는다.',
        '실제 순서: 92조②1 연결 확인 → 97조 읽기 → 97조 전체 연결 확인 → 시행령163조①③⑤ 읽기 → 163조 전체 읽기 → 시행령163조의2② 및 전체 읽기 → 법97조의2① 및 전체 읽기 → 예산 종료 → ASSESS → COMPOSE. 기존 호출7~10의 목록 왕복은 사라졌지만 특례 추가 읽기4회로 바뀌었다.',
        '모델 FINISH 선택은0회다. no_progress0으로 새 원문을 계속 확보하다 INVESTIGATION_BUDGET에 도달했고, 확보 원문8건을 최종 처리에 넘겨 PARTIAL/LIMITED_ANSWER를 생성했다. 조사 종료 문제와 전체 과도 탐색은 해결되지 않았다.',
        '완료된 ADR1022와의 비짝지은 과거 비교: 호출12→12, 입력682,477→939,172(+37.61%), 출력4,450→6,943, 비용$0.17224384→$0.24067588(+39.73%), 서비스286.876209→346.990860초(+20.95%). 호출<12·입력<682,477·자발적 FINISH라는 사전 기준을 충족하지 못했다.',
        '원문·범위 검사184건에서 불일치0·접근 범위 위반0, catalog 범위 위반0·선택 전 catalog0을 확인했다. 별도 연결 목록 모델 호출0회, 이번 ASSESS의 근거 없는 후속 조회 제안0개다. 이번 실행에 없는 잘못된 조항 제안의 차단 효과까지 실측했다고 주장하지 않는다.',
        '답변의 계산식 표현 오류도 관찰했다. 제공 원문97조②2가의 환산취득가액+대통령령 금액 비교에서 ASSESS는 환산취득가액을 누락했고 COMPOSE는 자본적지출액·양도비 합계로 바꿨다. artifacts/answer-wording-review.json에 원문·생성 문구를 결속했다. 법률 정답 검증 완료가 아니다.',
        '동일 후보 코드·검사501파일 해시를 확인했으므로 ADR1023의107개 계약검사 통과 기록을 승계했고 이번에 계약검사를 재실행하지 않았다. 이 실행 자체는 같은 후보 코드·pin의 실제 API 경로 검사다. 작업 제품 코드·선택 MAIN102·GENOS는 변경하지 않았다.',
    ],
    'interpretation': '현재 실행에서 목록 왕복이 관찰되지 않았고 실제 연결 원문에 도달했다. 그러나 추가 원문을 읽는 행동은 반복 방지 검사에 걸리지 않으며, 확보 충분성 판단과 질문 범위 제한이 해결되지 않아 예산으로 종료했다. 따라서 기계적 반복 방지 관찰과 전체 성공을 분리하고 전체 기준은 실패로 유지한다. 새로운 개선 후보나 재실행은 이 결과를 부모로 별도 사전 동결해야 한다.',
    'limitations': [
        '이미 노출된 질문1개의 단회 실행이다. 승인된 정답 gold·out-of-sample 검증이 없고, 법률 품질 인증·MAIN 승격 근거가 아니다.',
        'ADR1022는 과거 완료 실행의 참고 비교이며 이번에 함께 실행한 대조군이 아니다. 선택 범위도 과거97조①에서 이번97조 전체로 달라져 성능 차이를 단일 코드 효과로 확정할 수 없다.',
        '원문 일치 검사는 생성 해석의 정확성 검사가 아니다. 계산식 표현 오류를 보존하며 전체 법률 정답률은 미채점이다.',
        '외부 모델의 로컬 후보 실행이며 GENOS 내부 모델·현장 배포·검증은 수행하지 않았다.',
        '전역 ADR graph에는 기존9개 오류가 있었으며 이번 최종 graph 결과와 해당 ADR 관련 오류 여부는 final-checks.json에 별도 기록한다.',
    ],
    'error_taxonomy': [
        {'type': 'other', 'count': 1, 'reason': 'Native FINISH absent; investigation budget termination and preregistered call/token criteria missed.'},
        {'type': 'other', 'count': 1, 'reason': 'Generated acquisition-cost comparison expression differs from supplied source; offline wording observation, not full legal grading.'},
    ],
}
save(ART / 'manual-review.json', review)
print(json.dumps({'verdict': review['verdict'], 'metrics': metrics}, ensure_ascii=False))
