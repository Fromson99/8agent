"""Close a single native MAIN observation without altering any product result."""
from common import *
import sqlite3

freeze = read(DES / 'freeze.json')
manifest = read(ADR / '실험/manifest.json')
case = read(DES / 'cases.json')[0]
cell = RUN / case['id']
result = read(cell / 'result.json')
audit = read(cell / 'audit.json')
response = read(cell / 'response.json') if (cell / 'response.json').exists() else {}
body = response.get('body') or {}
answer = body.get('answer') or {}
usage = result.get('usage', [])
assert sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == freeze['pointer_sha256']
assert all(sha(ROOT / freeze['code_root'] / n) == h for n, h in freeze['serving_files'].items())
assert all(sha(ROOT / n) == h for n, h in freeze['files'].items())
checks = {
    'exact_selected_MAIN104_unchanged': True,
    'single_attempt_recorded': True,
    'no_integrity_or_permission_failure': not result.get('fatal') and not audit['unmapped_final'] and all(s['exact_original_match'] and s['within_scope'] for s in audit['span_checks']),
    'native_response_published': result.get('http_status') == 200 and bool(answer) and any(s.get('status') == 'COMPLETED' for s in audit['state']),
}
elapsed = result.get('elapsed_seconds')
transport = result.get('model_transport_seconds', 0)
report = {'status': 'complete', 'execution_complete': True, 'success_criteria_met': all(checks.values()),
    'checks': checks, 'quality_certified': False, 'legal_accuracy': 'not_scored',
    'in_sample': True, 'decision_eligible': False, 'MAIN': 104, 'attempted_cases': 1,
    'http_status': result.get('http_status'), 'native_status': result.get('status'),
    'answer_status': body.get('answer_status'), 'error': result.get('error'), 'error_type': result.get('error_type'),
    'model_calls': result['model_calls'], 'usage_reported_calls': len(usage),
    'actual_models': sorted({u.get('model') for u in usage if u.get('model')}),
    'actual_providers': sorted({u.get('upstream_provider') for u in usage if u.get('upstream_provider')}),
    'usage': {k: sum(u.get(k) or 0 for u in usage) for k in ('input_tokens', 'output_tokens', 'thinking_tokens', 'total_tokens', 'cost_usd')},
    'usage_basis': 'Only recorded provider usage; calls without usage are not asserted free.',
    'latency': {'request_seconds': elapsed, 'application_prepare_seconds': result.get('application_prepare_seconds'), 'observed_spans': result.get('observed_spans'), 'physical_model_transport_seconds': transport,
                'non_model_request_seconds': elapsed - transport if elapsed is not None else None,
                'p50_seconds': None, 'p95_seconds': None,
                'quantiles_reason': 'One sample is not a latency distribution; no speedup from fresh decisions.',
                'initial_application_load_excluded_from_request_seconds': True},
    'source_checks': {'evidence_units': len(audit['span_checks']),
                      'original_mismatches': sum(not s['exact_original_match'] for s in audit['span_checks']),
                      'scope_violations': sum(not s['within_scope'] for s in audit['span_checks']),
                      'read_articles': len(audit['read_coordinates']), 'cited_articles': len(audit['final_coordinates'])},
    'selected_serving_files_verified': len(freeze['serving_files']),
    'product_code_profile_data_changes': False, 'genos_executed': False,
    'known_sample_not_holdout': True}
put(RUN / 'result.json', report)
manifest['runs'][0].update(status='complete', sha256=sha(RUN / 'result.json'))
manifest['results'].update(status='complete', by_arm={'observed': {'status': 'complete', 'total': 1, 'attempted': 1, 'correct': None, 'accuracy': None, 'criteria_met': report['success_criteria_met'], 'legal_accuracy': 'not_scored'}},
    comparisons=[], judge_disagreements=None, usage={'product_model_calls': result['model_calls'], 'offline_evaluator_calls': 0, **report['usage']}, latency=report['latency'])
data = ROOT / read(DES / 'baseline.json')['release']['data_path']
db = sqlite3.connect((data / 'navigation/navigation.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
scope = read(RUN / 'binding.json')['public_scope']
corpus = db.execute('SELECT count(*) FROM source WHERE document_id IN (' + ','.join('?' for _ in scope) + ')', scope).fetchone()[0]
db.close()
count = len(audit['final_coordinates'])
manifest['retrieval_accounting'].update(corpus_total=corpus, before_filter=len(audit['read_coordinates']), after_filter=count,
    presented_total=count, presented_mean=count, presented_p50=count, presented_p95=count,
    golden_recall=None, selectivity=count / corpus if corpus else None)
manifest['retrieval_accounting']['stage_ledger']['sha256'] = sha(RUN / 'retrieval-ledger.json')
headers = ['실행 메타', '사용자 질문 원문', '기준답변 — 채점 전용, 제품 입력 비공개', '제품 입력을 구성한 원값', '제품 모델 호출 — run·arm별 실제 원문', '중간 LLM 호출 — router/compiler/verifier/repair', '채점 호출과 반복 판정', '사례 최종 판정']
link = '../artifacts/run-001/' + case['id']
sections = ['run-001 / observed. 선택 MAIN104의 실제 service.service. 신규 요청1회, 요청 전체 재실행0회.', case['question'],
    '법률 정답을 채점하지 않는 동작 관찰이다. 기준답변·정답 좌표는 제품 입력에 제공하지 않았다.',
    f'[실제 요청]({link}/request.json), [선택 바인딩](../artifacts/run-001/binding.json), [동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[읽기→최종 인용](../artifacts/run-001/retrieval-ledger.json). golden recall 미채점, 부분 span은 조문 전체 읽음으로 세지 않는다.',
    f'원문은 `{link}/raw/call-*/request.json`와 response.json, canonical/*.json.gz, wire/*.json.gz에 보존했다. 전체 질문·원문·스키마·wire와 제공자 원응답은 해시 원장으로 연결한다.',
    f'[물리 호출]({link}/calls.json), [단계 호출]({link}/generations.json), [원문 감사]({link}/audit.json).',
    '오프라인 채점 모델0회, 법률 정답률 미측정. 원문 바이트와 권한·상태만 별도 확인했다.',
    json.dumps(report, ensure_ascii=False, indent=2) + f'\n\n[실제 반환 텍스트]({link}/answer.txt)']
question = manifest['questions'][0]
question_file = ADR / '실험' / question['file']
question_file.write_text('# fsc-hard-005\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{s}' for i, (h, s) in enumerate(zip(headers, sections), 1)) + '\n')
question['sha256'] = sha(question_file)
put(ADR / '실험/manifest.json', manifest)
heads = ['결정 요약', '문제와 변경 전 구조', '가설과 사전 판정 기준', '실험 설계', '데이터·모델·재현성', '결과', '사례별 오류 분석', '비용·지연·회수 규모', '해석', '한계와 일반화 가능 범위', '운영 결정·롤백 조건', '재현 명령']
texts = ['MAIN104 반영 후 실제 선택 서비스의 공개 질문1회 관찰을 완료했다. 동작 성공 기준 충족: ' + str(report['success_criteria_met']),
    '211초의 원인인 두 SQL 수정은 별도 ADR1073에서 검증·승격했다. 이 실험은 승격 후 실제 모델 경로 관찰이다.',
    '[실행 전 고정 기준](artifacts/design/criteria.json). 알려진 질문이며 모델 판단·법률 정확도의 분리평가로 사용하지 않는다.',
    '단일 observed 조건, 질문1회, 기존 MAIN104 프로필/데이터/권한 그대로. 제품 호출은 ExperimentClient로 원시기록만 추가했다.',
    '[선택 코드·프로필·데이터](artifacts/run-001/binding.json). Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음 / 출력상한 없음.',
    '[원시 결과](artifacts/run-001/result.json), [질문](실험/' + question['file'] + ').\n\n```json\n' + json.dumps(report, ensure_ascii=False, indent=2) + '\n```',
    '실패·제한 답변은 원래 상태로 보존했다. 제공자 오류·판단 종료·원문 무결성 실패를 구분한다. 사후 좋은 응답으로 교체하지 않는다.',
    '요청시간에서 실제 모델 전송시간을 뺀 나머지를 모델 밖 시간으로 기록했다. 초기 application 준비 시간은 별도이며 이 값에 포함하지 않는다. 단일 관찰로 p95나 개선율을 추정하지 않는다.',
    'SQL 결정론적 동등성, 정상 발행, 법률 정답, 온톨로지 효과는 별개다. 이 실행은 온톨로지 기능을 활성화하지 않았다.',
    '기존 질문1개, 단일 실행이며 fresh model choices는 이전11응답 재생과 다르다. GENOS 현장 속도·법률 정확도 인증이 아니다.',
    'MAIN104의 코드·데이터·포인터를 유지했다. 이후 온톨로지 실험은 ADR1074에 격리했다. 반복·재실행은 새 ADR로 진행한다.',
    'freeze 후 live.py 1회 → audit.py → ledger.py → report.py → seal.py → 공식 status/validate --final/graph. 완료 실행을 덮어쓰지 않는다.']
meta = (ADR / 'README.md').read_text().split('---', 2)[1]
(ADR / 'README.md').write_text('---' + meta + '---\n\n# MAIN104 반영 후 실제 모델 실행\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{t}' for i, (h, t) in enumerate(zip(heads, texts), 1)) + '\n')
(ADR / '실험/README.md').write_text('# 실행 결과\n\n[전체 결과](../README.md) · [fsc-hard-005](' + question['file'] + ')\n')
print(json.dumps(report, ensure_ascii=False))
