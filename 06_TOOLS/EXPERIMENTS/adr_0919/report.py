"""Post-run accounting only; no model calls, product edits or inferred gold."""
from pathlib import Path
import hashlib, json, re

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0919-financial-private-bond-definition'
O = A / 'artifacts/run-001'
P = O / 'private-bond-definition'
read = lambda p: json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
def put(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
def canon(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
def unique(rows):
    return [json.loads(s) for s in sorted({canon(x) for x in rows})]

m = read(A/'실험/manifest.json')
freeze = read(A/'artifacts/design/freeze.json')
assert all(sha(R/n) == h for n, h in freeze['files'].items())
run = read(P/'result.json')
audit = read(P/'audit.json')
data = read(O/'data-audit.json')
body = read(P/'response.json')['body']
agent = body['assembly']['term_agent']
calls = read(P/'calls.json')
resource = read(A/'artifacts/resource-live.json')
plans = m['design']['retrieval_stage_plan']['stages_by_arm']['observed']
stages = []
before = []
before_occ = 0
for plan in plans:
    raw = audit['canonical_sets'][plan['stage_id']]
    after = unique(raw)
    bm, am = {canon(x): x for x in before}, {canon(x): x for x in after}
    added = [am[k] for k in sorted(am.keys()-bm.keys())]
    discarded = [bm[k] for k in sorted(bm.keys()-am.keys())]
    reason = 'Not in committed selection or final cited source IDs; not a legal irrelevance judgment.'
    stages.append({**plan, 'executed': True, 'skip_reason': None,
        'before': before, 'added': added, 'discarded': discarded, 'after': after,
        'before_count': len(before), 'added_count': len(added),
        'discarded_count': len(discarded), 'after_count': len(after),
        'occurrence_counts': {'before': before_occ, 'after': len(raw),
            'canonical_collapsed_before': before_occ-len(before),
            'canonical_collapsed_after': len(raw)-len(after)},
        'discard_receipts': [{'identity': x, 'reason': reason} for x in discarded],
        'discard_reason_counts': {reason: len(discarded)} if discarded else {},
        'gold_total': 0, 'gold_before': 0, 'gold_added': 0, 'gold_discarded': 0,
        'gold_after': 0, 'golden_recall': None, 'gold_before_identities': [],
        'gold_added_identities': [], 'discarded_gold': [], 'gold_after_identities': []})
    before, before_occ = after, len(raw)
case = {'schema_version': 'retrieval-stage-ledger-v1', 'computed_post_selection': True,
    'gold_visible_to_product': False, 'accounting_unit': 'case_id + canonical article-root coordinate',
    'arm_id': 'observed', 'case_id': 'private-bond-definition', 'gold_total': 0,
    'gold_identities': [], 'stages': stages}
ledger = {'schema_version': 'retrieval-stage-ledger-v1', 'adr_id': m['adr_id'],
    'experiment_id': m['experiment_id'], 'accounting_unit': case['accounting_unit'],
    'computed_post_selection': True, 'gold_visible_to_product': False,
    'runs': [{'run_id': 'run-001', 'arms': [{'arm_id': 'observed',
        'declared_stage_ids': [p['stage_id'] for p in plans], 'cases': [case],
        'aggregate': {'cases': 1, 'presented_total': len(before), 'gold_total': 0}}]}]}
ledger['artifact_sha256'] = hashlib.sha256(canon(ledger).encode()).hexdigest()
put(O/'retrieval-ledger.json', ledger)
findings = [
    {'kind': 'other', 'finding': 'COMPOSE changed source location 제9조 ⑧ to 제9조 제8호. The acquired original is paragraph 8, not item 8; assessed claim retained the correct circled paragraph.'},
    {'kind': 'required_issue_omission', 'finding': 'The answer derives a private-bond explanation from the definition of private placement. A direct private-bond definition was not supplied; accepted outcome is LIMITED_ANSWER/PARTIAL and the gap was preserved.'},
    {'kind': 'other', 'finding': 'Exact glossary headword 사모사채 exists with an empty definition. Selected original exact-phrase hits concern investment limits, accounting categories and inclusion under bonds, rather than an explicit definition. This is not proof no synonymous/implicit definition exists.'}]
result = {'status': 'complete', 'main_generation': 88, 'main_changed': False,
    'genos_executed': False, 'app_injected': False, 'case_count': 1,
    'question': '사모사채 정의 알려줘', 'http_status': run['http_status'],
    'answer_generated': bool(body['answer']['text']), 'answer_coverage': agent['answer_coverage'],
    'disposition': agent['accepted_outcome']['disposition'], 'stop_reason': agent['stop_reason'],
    'definition_answerability': 'General explanation from private-placement original; not a direct term-definition retrieval success.',
    'legal_accuracy': None, 'quality_certified': False, 'decision_eligible': False,
    'product_model_calls': len(calls), 'offline_evaluator_model_calls': 0,
    'request_seconds': run['request_seconds'], 'total_seconds': run['elapsed_seconds'],
    'physical_model_seconds': sum(c['elapsed_seconds'] for c in calls),
    'calls': [{k: c[k] for k in ('call', 'phase', 'elapsed_seconds')} for c in calls],
    'source_records_checked': len(audit['span_checks']),
    'source_record_mismatches': sum(not s['exact_original_match'] for s in audit['span_checks']),
    'consumer_checks': run['checks'], 'peak_process_rss_gib': run['peak_rss_kib']/1024**2,
    'resource_stop': resource['stop_reason'],
    'team_selected_document_count': data['team_selected_document_count'],
    'model_allowed_document_count': data['model_allowed_document_count'],
    'actual_models': sorted({u['model'] for u in run['usage']}),
    'actual_upstream_providers': sorted({u['upstream_provider'] for u in run['usage']}),
    'usage': {k: sum(u.get(k) or 0 for u in run['usage']) for k in ('input_tokens', 'output_tokens', 'cost_usd')},
    'findings': findings,
    'limitations': ['One user-provided query once; no approved legal gold, paired trial or accuracy percentage.',
        'External model used existing authorized 44-document intersection; all 1185 team-selected documents were not sent.',
        'Read-only post-run glossary/original scan was not added to model context. Original model output retained.',
        'Local WSL active release with instrumented physical transport; no GENOS field run or product changes.']}
put(O/'result.json', result)
m['runs'][0].update(status='complete', artifact_path=str((O/'result.json').relative_to(R)), sha256=sha(O/'result.json'))
m['results'].update(status='complete', by_arm={'observed': {'status': 'complete', 'questions': 1,
    'product_answer_successes': 1, 'legal_accuracy': None, 'answer_coverage': 'PARTIAL'}},
    comparisons=[], judge_disagreements=None,
    usage={'product_model_calls': len(calls), 'offline_evaluator_calls': 0, **result['usage']},
    latency={'private-bond-definition': run['request_seconds'], 'sample_size': 1, 'generalizable': False}, error_taxonomy=findings)
counts = {s['stage_id']: s['after_count'] for s in stages}
m['retrieval_accounting'].update(corpus_total=audit['corpus_total'],
    before_filter={'observed': counts['native_read']}, after_filter={'observed': counts['selected']},
    presented_total={'observed': counts['cited']}, presented_mean={'observed': counts['cited']},
    presented_p50={'observed': counts['cited']}, presented_p95={'observed': counts['cited']},
    golden_recall={'observed': None}, selectivity={'observed': counts['cited']/audit['corpus_total']})
m['retrieval_accounting']['stage_ledger']['sha256'] = sha(O/'retrieval-ledger.json')
heads = ['결정 요약', '문제와 변경 전 구조', '가설과 사전 판정 기준', '실험 설계', '데이터·모델·재현성', '결과', '사례별 오류 분석', '비용·지연·회수 규모', '해석', '한계와 일반화 가능 범위', '운영 결정·롤백 조건', '재현 명령']
parts = ['Proposed. 실제 답변은 생성됐지만 직접 정의 확보는 미완료이고 조문 표기 오류가 있다.',
    '사용자가 Financial team 자료로 사모사채 정의를 답할 수 있는지 요청했다. 선택 MAIN88의 일반 RAG를 그대로 관측한다.',
    '첫 호출 전 artifacts/design/criteria.json에 답변·원문 무결성·저장·예산 기준을 동결했다.',
    '사용자 질문 그대로 한 번, 사전 근거/정답 주입 없음. 새 격리 요청 상태, 단일 무거운 프로세스.',
    'design/freeze.json에 실제 선택 코드372파일·프로필·데이터·모델·실행기 지문. Qwen3.8/Parasail FP8/none/fallback 없음.',
    json.dumps(result, ensure_ascii=False, indent=2), json.dumps(findings, ensure_ascii=False, indent=2),
    'run-001/result.json의 요청/전체/모델 시간과 usage, retrieval-ledger.json의 확보→선택→인용. 원문28기록 일치; 중복 추가 호출0.',
    '사모의 원문을 바탕으로 일반 설명은 가능했다. 사모사채의 직접 정의를 찾았다고 보고하지 않는다. 미확보 사항은 사용자 후속 조사로 남겨 추가 탐색을 자동 실행하지 않았다.',
    '\n'.join(result['limitations']), '제품·선택 MAIN88·GENOS 변경 없음. 원래 답변을 수정하지 않고 표기·근거 부족을 별도 기록.',
    'prepare.py → live.py private-bond-definition → observe.py private-bond-definition → 읽기 전용 data-audit → report.py → archive.py → hash/status/validate --final/graph. 완료 실행 폴더 재사용 금지.']
meta = (A/'README.md').read_text().split('---', 2)[1]
meta = re.sub(r'(?m)^status:.*$', 'status: Proposed', meta)
(A/'README.md').write_text('---'+meta+'---\n\n# Financial team 사모사채 정의 관측\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{p}' for i, (h, p) in enumerate(zip(heads, parts), 1))+'\n')
q = m['questions'][0]
qheads = ['실행 메타', '사용자 질문 원문', '기준답변 — 채점 전용, 제품 입력 비공개', '제품 입력을 구성한 원값', '제품 모델 호출 — run·arm별 실제 원문', '중간 LLM 호출 — router/compiler/verifier/repair', '채점 호출과 반복 판정', '사례 최종 판정']
qparts = ['run-001 / observed / private-bond-definition. exact, local MAIN88, no app injection.',
    result['question'], '승인 법률 gold 없음. 제품에 정답·추가 자료 힌트 미제공.',
    'design/freeze.json, case request.json/scope.json/binding.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json',
    'case raw-runtime.tar.gz 안 raw/call-*/request.json 및 response.json, canonical/ 및 wire/ 압축 입출력. archive-manifest.json 해시·복원 방법.',
    'case call-summary.json과 audit.json. 요청 판단1회→충분성1회→답변1회.',
    '평가 모델0회. 원문 span/해시·소비자 대조와 수동 표기 검사. 법률 정답률 미측정.', json.dumps(result, ensure_ascii=False, indent=2)]
(A/'실험'/q['file']).write_text('# 사모사채 정의 실제 질의\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{p}' for i, (h, p) in enumerate(zip(qheads, qparts), 1))+'\n')
q['sha256'] = sha(A/'실험'/q['file'])
put(A/'실험/manifest.json', m)
(A/'실험/README.md').write_text(f'# 질문 인덱스\n\n- [사모사채 정의]({q["file"]})\n')
print(json.dumps({k: result[k] for k in ('product_model_calls', 'request_seconds', 'answer_coverage', 'source_record_mismatches')}, ensure_ascii=False))
