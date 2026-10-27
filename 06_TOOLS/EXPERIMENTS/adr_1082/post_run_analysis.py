"""Describe the failed live observation; no rerun, rescore, or product changes.

The frozen compare.py was not executed: a failed request cannot establish a
completed-response speedup. Preserve that tool and all frozen criteria unchanged.
"""
from common import *
import collections, gzip

OLD = ROOT / '04_EXPERIMENTS/ADR/ADR-1075-main104-post-sql-live-check/artifacts/run-001'
cell = RUN / 'fsc-hard-005'
freeze = read(DES / 'freeze.json')
assert all(sha(ROOT/n) == h for n,h in freeze['scripts'].items())
assert all(sha(ROOT/n) == h for n,h in read(DES/'historical-reference.json')['files'].items())
assert read(OLD/'fsc-hard-005/request.json') == read(cell/'request.json')
before_binding, current_binding = read(OLD/'binding.json'), read(RUN/'binding.json')
for key in ('profile','profile_sha256','data_path','model_policy_sha256','search_selection_fingerprint'):
    assert before_binding[key] == current_binding[key], key

def metrics(base):
    report = read(base/'result.json')
    audit = read(base/'fsc-hard-005/audit.json')
    views = [s['seconds'] for s in report['latency']['observed_spans'] if s['function']=='Investigation.view']
    definitions = [s['seconds'] for s in report['latency']['observed_spans'] if s['function']=='definition_entry.verified']
    return {'MAIN':report['MAIN'], 'native_states':audit['state'],
        'native_response_published':report['checks']['native_response_published'],
        'success_criteria_met':report['success_criteria_met'], 'http_status':report['http_status'],
        'request_seconds':report['latency']['request_seconds'],
        'model_transport_seconds':report['latency']['physical_model_transport_seconds'],
        'non_model_seconds':report['latency']['non_model_request_seconds'],
        'application_prepare_seconds':report['latency']['application_prepare_seconds'],
        'view_count':len(views), 'view_seconds':sum(views), 'first_view_seconds':views[0],
        'subsequent_view_count':len(views)-1, 'subsequent_view_seconds':sum(views[1:]),
        'subsequent_view_mean_seconds':sum(views[1:])/(len(views)-1),
        'subsequent_view_max_seconds':max(views[1:]),
        'definition_verification_count':len(definitions),'definition_verification_seconds':sum(definitions),
        'model_calls':report['model_calls'], 'source_checks':report['source_checks'],
        'actual_models':report['actual_models'], 'actual_providers':report['actual_providers']}

before, current = metrics(OLD), metrics(RUN)
assert current['http_status']==502 and not current['native_response_published']
caps = ('max_tokens','max_completion_tokens','max_output_tokens')
requests = sorted((cell/'raw').glob('call-*/request.json'))
assert len(requests)==current['model_calls']==31
assert all(not any(k in read(p) for k in caps) for p in requests)
last = read(requests[-1])
raw = read(requests[-1].parent/'response.json')
error = raw['error']
assert error['code']==400
provider_detail = json.loads(error['metadata']['raw'])['error']
wire_view = json.loads(last['messages'][-1]['content'])['view']
sizes = sorted(({'field':k,'serialized_chars':len(json.dumps(v,ensure_ascii=False,separators=(',',':')))} for k,v in wire_view.items()),key=lambda x:x['serialized_chars'],reverse=True)
calls = read(cell/'calls.json')
diagnosis = {'execution_outcome':'FAILED_PROVIDER_CONTEXT_LIMIT',
    'run_attempts':1,'whole_question_retries':0,'physical_model_calls':31,
    'completed_model_calls':sum(x['status']=='completed' for x in calls),
    'failed_call':31,'provider_http_status':400,'service_http_status':502,
    'provider_error':provider_detail,'provider_reported_input_tokens':150912,
    'provider_reported_output_tokens':111233,'provider_reported_combined_limit':262144,
    'provider_reported_excess_tokens':1,
    'all31actual_payloads_omit_output_cap_fields':True,
    'interpretation':'Provider reports input+output reservation one token over its context limit. The application sent no output-cap fields. The origin of the provider output reservation is not established by this observation; do not claim the app requested an explicit111233token cap.',
    'payload_chars':{'system':len(last['messages'][0]['content']), 'user':len(last['messages'][-1]['content']), 'response_format':len(json.dumps(last['response_format'],ensure_ascii=False,separators=(',',':')))},
    'largest_actual_wire_view_fields':sizes[:10],
    'source_checks':current['source_checks'],
    'scope':'Post-selection factual error analysis only; no model repair, score change, output-cap change or new product request.'}
put(RUN/'failure-diagnosis.json',diagnosis)
comparison = {'baseline':before,'current':current,
    'same_question_scope_data_effective_profile_model_policy':True,
    'overall_response_speedup_percent':None,
    'reason':'Baseline completed; current failed before final answer. Different fresh model choices and read extent. Elapsed-to-failure cannot establish completed-response improvement.',
    'controlled_replay_evidence_separate':'ADR1081: identical35views736.499598113→93.717707418seconds,87.275percent decrease;0newmodelcalls.',
    'frozen_compare_tool_executed':False,
    'analysis_note':'The frozen generic percent-comparison renderer is preserved but not used for a failed request. This post-run report retains all frozen outcomes and criteria; no rescore or rerun.',
    'genos_executed':False,'legal_accuracy_scored':False}
put(RUN/'historical-comparison.json',comparison)
text = '''# MAIN105 실제 질문 관찰 — 제공자 오류로 중단

같은 공개 질문·문서 범위·데이터·유효 프로필·모델 정책으로 실제 선택 MAIN105에 새 질문을 한 번 보냈다. 31번째 모델 호출에서 제공자 HTTP400이 발생해 서비스 HTTP502/FAILED로 끝났다. 최종 답변은 발행되지 않았다. 전체 응답시간 개선율은 산출하지 않는다.

| 항목 | 이전 MAIN104 완료 실행 | 이번 MAIN105 중단 실행 |
|---|---:|---:|
'''
labels=[('request_seconds','측정 종료까지'),('model_transport_seconds','모델 통신'),('non_model_seconds','모델 밖 처리'),('view_seconds','탐색 화면 구성 합계'),('first_view_seconds','첫 화면 구성'),('subsequent_view_mean_seconds','첫 화면 이후 평균')]
text += '\n'.join(f"| {label} | {before[key]:.3f}초 | {current[key]:.3f}초 |" for key,label in labels)
text += f"\n\n모델 호출 {before['model_calls']}→{current['model_calls']}회, 화면 {before['view_count']}→{current['view_count']}회, 읽은 조문 {before['source_checks']['read_articles']}→{current['source_checks']['read_articles']}개, 근거 단위 {before['source_checks']['evidence_units']}→{current['source_checks']['evidence_units']}개다. 이번 실제 원문 불일치·권한 위반은 모두0이다. 앞선 완료 실행도 제한 답변이었고, 이번에는 답변 발행에 도달하지 못했다.\n\n"
text += '''화면 구성 비용이 낮게 관찰됐지만 새 모델의 조사량·선택·실행 시점이 달라 순수 SQL 효과를 이 표에서 계산하지 않는다. 동일 화면을 재생했던 ADR1081의35화면736.500→93.718초(87.275%)가 별도의 비교 근거다. 이번에는 초기 화면32.713초가 여전히 남았고 첫 화면 이후29회 평균은1.658초였다. 화면 구성80.792초는 비모델166.596초에 포함되며 중첩 구간을 합산하지 않는다. 앱 최초 준비2.904초는 요청 시간에서 제외했다.

## 중단 원인

제공자는 입력150,912토큰+출력111,233토큰=262,145토큰이 자신의 합산 한도262,144토큰보다1토큰 크다고 반환했다. 실제31개 전송 본문에는 출력 상한 필드가 하나도 없었다. 따라서111,233을 애플리케이션이 지정한 출력 상한으로 설명하지 않는다. 제공자가 그 출력량을 산출한 정확한 경로는 미확인이다. 마지막 user메시지는344,937자였고 누적 원문·선택지 등이 포함돼 있었다. 출력상한 설정은 변경하지 않았다.

질문 전체 재시도0회, 별도 채점 모델0회다. 성공 기준 중 답변 발행은 실패했다. DB 지연 개선과 외부 모델의 문맥 한도 오류는 구분한다. GENOS 현장 성능과 법률 정확도는 측정하지 않았다.

[구조화 비교](historical-comparison.json) · [전송·오류 진단](failure-diagnosis.json) · [실제 반환 문구](fsc-hard-005/answer.txt) · [원문·권한 감사](fsc-hard-005/audit.json)
'''
(RUN/'COMPARISON.md').write_text(text)
print(json.dumps({'outcome':diagnosis['execution_outcome'],'comparison':str((RUN/'COMPARISON.md').relative_to(ROOT)),'overall_speedup_claim':False},ensure_ascii=False))
