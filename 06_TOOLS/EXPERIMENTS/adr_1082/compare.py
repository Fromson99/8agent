"""Descriptive historical/live comparison; no product mutation or new model calls."""
from common import *

OLD = ROOT / '04_EXPERIMENTS/ADR/ADR-1075-main104-post-sql-live-check/artifacts/run-001'
for name, digest in read(DES / 'historical-reference.json')['files'].items():
    assert sha(ROOT / name) == digest, name
assert read(OLD / 'fsc-hard-005/request.json') == read(RUN / 'fsc-hard-005/request.json')
old_binding, new_binding = read(OLD / 'binding.json'), read(RUN / 'binding.json')
for field in ('profile', 'profile_sha256', 'data_path', 'model_policy_sha256', 'search_selection_fingerprint'):
    assert old_binding[field] == new_binding[field], field

def metrics(base):
    report = read(base / 'result.json')
    audit = read(base / 'fsc-hard-005/audit.json')
    spans = report['latency']['observed_spans']
    views = [s['seconds'] for s in spans if s['function'] == 'Investigation.view']
    definitions = [s['seconds'] for s in spans if s['function'] == 'definition_entry.verified']
    return {
        'MAIN': report['MAIN'], 'success_criteria_met': report['success_criteria_met'],
        'http_status': report['http_status'], 'native_status': report['native_status'],
        'native_final_states': audit['state'],
        'request_seconds': report['latency']['request_seconds'],
        'model_transport_seconds': report['latency']['physical_model_transport_seconds'],
        'non_model_seconds': report['latency']['non_model_request_seconds'],
        'view_count': len(views), 'view_seconds': sum(views),
        'view_mean_seconds': sum(views) / len(views) if views else None,
        'definition_verification_count': len(definitions), 'definition_verification_seconds': sum(definitions),
        'model_calls': report['model_calls'], 'source_checks': report['source_checks'],
        'actual_models': report['actual_models'], 'actual_providers': report['actual_providers'],
        'answer_path': str((base / 'fsc-hard-005/answer.txt').relative_to(ROOT)),
    }

before, after = metrics(OLD), metrics(RUN)
changes = {}
for field in ('request_seconds', 'model_transport_seconds', 'non_model_seconds', 'view_seconds', 'view_mean_seconds'):
    a, b = before[field], after[field]
    changes[field] = {'difference_seconds': b-a, 'observed_reduction_percent': (1-b/a)*100} if a and b is not None else None
comparison = {
    'baseline': before, 'current': after, 'differences': changes,
    'same_request_profile_data_model_policy': True,
    'new_fresh_question_runs': 1, 'fresh_baseline_runs': 0, 'offline_evaluator_calls': 0,
    'interpretation': 'Historical single fresh run versus new single fresh run. Choices and reading extent may differ; these are descriptive differences, not isolated SQL effect or a latency distribution. Model transport includes audited transport I/O. View and definition spans nest inside non-model time and must not be added to it.',
    'controlled_evidence_separate': 'ADR1081: same35views,736.499598113→93.717707418seconds,87.275percent reduction,0newmodelcalls. MAIN104 already contained the original definition-query fix; MAIN105 additionally narrows permission queries and reuses unchanged source verification within one menu construction.',
    'genos_executed': False, 'legal_accuracy_scored': False,
}
put(RUN / 'historical-comparison.json', comparison)
labels = [('request_seconds','전체 요청'), ('model_transport_seconds','모델 통신'), ('non_model_seconds','모델 밖 처리'), ('view_seconds','탐색 화면 구성 합계'), ('view_mean_seconds','화면당 평균')]
rows = '\n'.join(f"| {label} | {before[key]:.3f}초 | {after[key]:.3f}초 | {changes[key]['observed_reduction_percent']:.2f}% |" for key,label in labels if changes[key])
text = '# MAIN105 실제 질문 시간 비교\n\n동일한 공개 질문·데이터·프로필·모델 정책을 사용해 현재 선택 MAIN105에 새 요청을 한 번 보냈다. 이전 MAIN104의 완료된 실제 실행과 비교한다.\n\n'
text += '| 항목 | 이전 MAIN104 | 현재 MAIN105 | 관찰된 감소 |\n|---|---:|---:|---:|\n' + rows + '\n\n'
text += f"모델 호출 {before['model_calls']}→{after['model_calls']}회, 화면 구성 {before['view_count']}→{after['view_count']}회, 읽은 조문 {before['source_checks']['read_articles']}→{after['source_checks']['read_articles']}개, 근거 단위 {before['source_checks']['evidence_units']}→{after['source_checks']['evidence_units']}개.\n\n"
text += '한 번씩의 관찰이며 모델의 선택과 조사량이 달라질 수 있다. 전체 감소율을 SQL만의 효과나 일반적인 서비스 개선율로 해석하지 않는다. 화면 구성 시간은 모델 밖 처리의 일부이고 정의 검증 시간은 화면 시간에 포함되므로 합산하지 않는다. 앱 최초 로딩은 별도이며 GENOS 현장 속도와 법률 정답률은 측정하지 않았다.\n\n'
text += '[실제 답변](fsc-hard-005/answer.txt) · [구조화 비교와 최종 상태](historical-comparison.json) · [원문·권한 감사](fsc-hard-005/audit.json)\n'
(RUN / 'COMPARISON.md').write_text(text)
print(json.dumps({'before': {k:before[k] for k in ('request_seconds','model_transport_seconds','non_model_seconds','view_count','view_seconds','model_calls','source_checks')}, 'after': {k:after[k] for k in ('request_seconds','model_transport_seconds','non_model_seconds','view_count','view_seconds','model_calls','source_checks')}}, ensure_ascii=False))
