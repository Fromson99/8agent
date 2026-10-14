"""Preserve exact probe evidence and report answer emission, without semantic grading."""
from pathlib import Path
import gzip
import hashlib
import json
import sqlite3
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / sys.argv[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def ro(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def fence(value):
    return '```json\n' + json.dumps(value, ensure_ascii=False, indent=2) + '\n```'


frozen = read(ADR / 'artifacts/design/frozen.json')
m = read(ADR / '실험/manifest.json')
for path, expected in frozen['bindings'].items():
    assert sha(ROOT / path) == expected, path
nav = ro(ROOT / frozen['release']['data_path'] / 'navigation/navigation.sqlite')
sources = {row['id']: json.loads(row['json']) for row in nav.execute('SELECT id,json FROM source')}
nav.close()
grant = read(ROOT / frozen['release']['code_root'] / '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
scope = set(grant['public_document_ids'])


def identities(ids):
    return [json.loads(item) for item in sorted({canon({'doc_id': sources[s]['document_id'], 'node': int(sources[s]['unit_id'])})
        for s in ids if s in sources and str(sources[s]['unit_id']).isdigit()})]


def offered(value):
    ids = set()
    def walk(item):
        if isinstance(item, dict):
            if item.get('source_id') in sources and isinstance(item.get('text'), str) and item['text']:
                ids.add(item['source_id'])
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return ids


def source_label(sid):
    value = sources.get(sid, {})
    return {'source_id': sid, 'document_id': value.get('document_id'), 'document_name': value.get('document_name'),
            'heading': value.get('heading'), 'article_unit_id': value.get('unit_id')}


corpus = identities(s for s, value in sources.items() if value['document_id'] in scope)
rows, ledger_runs, question_refs = [], [], []
for number, case in enumerate(frozen['cases'], 1):
    run = case['run_id']
    directory = ADR / 'artifacts' / run
    result = read(directory / 'result.json')
    assert result['model_calls'] <= frozen['max_calls_per_run']
    events, stages, acquired_ids = [], [], set()
    journals = list((directory / 'runtime').rglob('journal.sqlite'))
    assert len(journals) <= 1
    if journals:
        db = ro(journals[0])
        events = [{'seq': row['seq'], 'kind': row['kind'], 'payload': json.loads(row['payload_json'])}
            for row in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq')]
        stages = [{'entity_id': row['entity_id'], 'payload': json.loads(row['payload_json'])}
            for row in db.execute("SELECT entity_id,payload_json FROM entity_version WHERE kind='case_stage' ORDER BY created_seq")]
        acquired_ids = {row[0] for row in db.execute('SELECT DISTINCT source_id FROM evidence_unit')}
        db.close()
    latest = {stage['entity_id'].removeprefix('case:'): stage['payload'] for stage in stages}
    recalls = [stage['payload'] for stage in stages if stage['entity_id'] == 'case:RECALL']
    recalled = identities(s for value in recalls for s in value.get('selected_for_read', []))
    acquired = identities(acquired_ids)
    presented_ids, calls = set(), []
    for call in sorted((directory / 'provider').glob('call-*')):
        request_file = call / 'request.json'
        if request_file.exists():
            request = read(request_file)
            assert request['model'] == frozen['model']
            assert request['provider'] == read(ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['provider_routing']
            assert request['reasoning'] == {'effort': 'none'}
            for message in request.get('messages', []):
                try:
                    presented_ids.update(offered(json.loads(message.get('content', ''))))
                except (ValueError, TypeError):
                    pass
        calls.append({'call': call.name, 'files': {path.name: {'path': str(path.relative_to(ROOT)),
            'sha256': sha(path), 'bytes': path.stat().st_size} for path in sorted(call.glob('*.json'))}})
    assert len(calls) == result['model_calls']
    presented = identities(presented_ids)
    output = result.get('output') or {}
    meta = output.get('assembly', {}).get('term_agent', {})
    answer = output.get('answer') or {}
    text = answer.get('text') or ''
    answer_ids = list(dict.fromkeys(s for claim in answer.get('claims', []) for s in claim.get('source_ids', [])))
    final_ids = latest.get('SELECT', {}).get('final_ids', [])
    trace = {'run_id': run, 'case_id': case['case_id'], 'journal_present': bool(journals),
        'directories': [event for event in events if event['kind'] == 'LAW_FULLTEXT_DIRECTORY'],
        'decisions': [event for event in events if event['kind'] in ('LAW_SELECTION_DECISION', 'LAW_BRANCH_DECISION',
            'UNIT_READ_CHOICE', 'LAW_DECISION_REJECTED', 'LAW_DECISION_RETRY', 'INVESTIGATION_BOUNDED_STOP')],
        'selected_originals': [source_label(s) for s in final_ids],
        'answer_sources': [source_label(s) for s in answer_ids], 'latest_stage_keys': list(latest)}
    put(directory / 'navigation-trace.json', trace)
    row = {'run_id': run, 'case_id': case['case_id'], 'topic_reference': case['topic_reference'],
        'question': case['question'], 'http_status': result['http_status'], 'seconds': result['seconds'],
        'model_calls': result['model_calls'], 'answer_emitted': result['http_status'] == 200 and bool(text.strip()),
        'answer_cited': result['http_status'] == 200 and bool(text.strip()) and bool(answer_ids),
        'answer_text': text, 'answer_sources': trace['answer_sources'], 'answer_status': output.get('answer_status'),
        'answer_coverage': meta.get('answer_coverage'), 'stop_reason': meta.get('stop_reason'),
        'gaps': meta.get('gaps'), 'issue_assessments': meta.get('issue_assessments'),
        'error': output.get('detail') or output.get('error') or result.get('exception'),
        'acquired_roots': len(acquired), 'presented_roots': len(presented),
        'presented_document_ids_authorized': all(sources[s]['document_id'] in scope for s in presented_ids),
        'active_pointer_unchanged': result['pointer_before'] == result['pointer_after'] == frozen['bindings']['01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'],
        'execution_binding': result.get('execution_binding'),
        'usage': {key: sum(item.get(key, 0) or 0 for item in result['usage'])
            for key in ('input_tokens', 'output_tokens', 'cost_usd', 'seconds')}}
    assert row['active_pointer_unchanged'] and row['presented_document_ids_authorized']
    put(directory / 'diagnostic.json', row)
    rows.append(row)
    before, ledger = [], []
    reasons = ['Approved immutable public source catalogue',
        'Request rejected before recall' if not journals else 'Not in the executed initial recall candidates',
        'No original READ in this run', 'No source text in any actual provider input in this run']
    for index, after in enumerate([corpus, recalled, acquired, presented]):
        plan = m['design']['retrieval_stage_plan']['stages_by_arm']['baseline'][index]
        bm, am = {canon(value): value for value in before}, {canon(value): value for value in after}
        added = [am[key] for key in sorted(am.keys() - bm.keys())]
        discarded = [bm[key] for key in sorted(bm.keys() - am.keys())]
        ledger.append({**plan, 'executed': True, 'skip_reason': None,
            'before': before, 'added': added, 'discarded': discarded, 'after': after,
            'before_count': len(before), 'added_count': len(added), 'discarded_count': len(discarded), 'after_count': len(after),
            'occurrence_counts': {'before': len(before), 'after': len(after), 'canonical_collapsed_before': 0, 'canonical_collapsed_after': 0},
            'discard_receipts': [{'identity': value, 'reason': reasons[index]} for value in discarded],
            'discard_reason_counts': {reasons[index]: len(discarded)} if discarded else {},
            'gold_total': 0, 'gold_before': 0, 'gold_added': 0, 'gold_discarded': 0, 'gold_after': 0,
            'golden_recall': None, 'gold_before_identities': [], 'gold_added_identities': [],
            'discarded_gold': [], 'gold_after_identities': []})
        before = after
    ledger_case = {'schema_version': 'retrieval-stage-ledger-v1', 'computed_post_selection': True,
        'gold_visible_to_product': False, 'accounting_unit': 'case_id + canonical article-root coordinate',
        'arm_id': 'baseline', 'case_id': case['case_id'], 'gold_total': 0, 'gold_identities': [], 'stages': ledger}
    # The ADR validator requires every manifest case in each run. The frozen
    # plan schedules only one case per process: other cases are explicitly
    # skipped, never claimed as executed or counted as additional requests.
    covered_cases = [ledger_case]
    for other in frozen['cases']:
        if other['case_id'] == case['case_id']:
            continue
        skipped_stages = []
        for stage in ledger:
            skipped = {**stage, 'executed': False,
                'skip_reason': 'Not scheduled in this independent-case run; pre-frozen execution is ' + other['run_id'],
                'before': [], 'added': [], 'discarded': [], 'after': [],
                'before_count': 0, 'added_count': 0, 'discarded_count': 0, 'after_count': 0,
                'occurrence_counts': {'before': 0, 'after': 0, 'canonical_collapsed_before': 0, 'canonical_collapsed_after': 0},
                'discard_receipts': [], 'discard_reason_counts': {}}
            skipped_stages.append(skipped)
        covered_cases.append({**ledger_case, 'case_id': other['case_id'], 'stages': skipped_stages})
    covered_cases.sort(key=lambda value: value['case_id'])
    ledger_runs.append({'run_id': run, 'arms': [{'arm_id': 'baseline',
        'declared_stage_ids': ['catalogue', 'recall', 'acquired', 'presented'], 'cases': covered_cases,
        'aggregate': {'cases': len(covered_cases), 'executed_cases': 1,
                      'skipped_cases': len(covered_cases) - 1, 'presented_total': len(presented), 'gold_total': 0}}]})
    next(item for item in m['runs'] if item['id'] == run).update(status='complete', sha256=sha(directory / 'result.json'))
    stage_table = [{key: stage[key] for key in ('stage_id', 'before_count', 'added_count', 'discarded_count', 'after_count')} for stage in ledger]
    question = ADR / '실험' / f"질문-{number:03d}-{case['case_id']}.md"
    question.write_text('\n\n'.join([
        '# ' + case['case_id'], '## 1. 실행 메타', f"{run} / baseline / local MAIN45 / fresh state / Qwen3.8 Parasail FP8 reasoning none",
        '## 2. 사용자 질문 원문', case['question'], frozen['question_origin'],
        '주제 대응: ' + case['topic_reference'] + ' — 원본 질문과 동일 입력이라는 뜻이 아니다.',
        '## 3. 기준답변 — 채점 전용, 제품 입력 비공개', '법률 정답·gold 좌표·risk_cm 마킹과 근거 후보를 제품 입력에 제공하지 않았다. 정답 채점은 수행하지 않았다.',
        '## 4. 제품 입력을 구성한 원값', 'request.json, profile.json, health.json 및 frozen.json에 실제 입력·binding을 보존한다. source text 원값은 각 provider request 원본에서 확인한다.',
        '### 회수·탈락 단계 원장 — run·arm별', fence(stage_table),
        '전체 exact 좌표·탈락 이유는 artifacts/retrieval-ledger.json.gz에 있다. catalogue는 승인된 원문 집합이며 요청 거절이면 실제 회수·제시 집합은 빈 집합이다. 후속 확장에 의한 added를 보존했다. gold가 없어 회수율은 미측정이다.',
        '## 5. 제품 모델 호출 — run·arm별 실제 원문', fence(calls),
        '## 6. 중간 LLM 호출 — router/compiler/verifier/repair', '위 provider 원본에 모든 실제 중간 호출·schema·output·usage가 연결돼 있다. 모델0회이면 provider 입력은 없으며 response.json에 호출 전 실패가 보존돼 있다.',
        '## 7. 채점 호출과 반복 판정', '채점0회·각 주제1회·단일 arm. paired delta와 법률 정답률은 산출하지 않았다.',
        '## 8. 사례 최종 판정', fence(row)]) + '\n')
    question_refs.append({'case_id': case['case_id'], 'run_id': run, 'file': question.name})

ledger = {'schema_version': 'retrieval-stage-ledger-v1', 'adr_id': m['adr_id'], 'experiment_id': m['experiment_id'],
    'accounting_unit': 'case_id + canonical article-root coordinate', 'computed_post_selection': True,
    'gold_visible_to_product': False, 'runs': ledger_runs,
    'audit': {'gold': 'No legal gold or semantic correctness grading.',
        'acquired': 'Initial deterministic previews and later original/context READs are recorded; acquisition is not legal adoption.',
        'presented': 'Text-bearing source IDs observed in exact physical provider requests.',
        'stages': 'Aggregate trace sets per request, not a fabricated chronology; request rejection yields empty downstream sets.'}}
ledger['artifact_sha256'] = hashlib.sha256(canon(ledger).encode()).hexdigest()
ledger_path = ADR / 'artifacts/retrieval-ledger.json.gz'
with gzip.open(ledger_path, 'wt', encoding='utf-8', compresslevel=9) as stream:
    stream.write(canon(ledger))
first = rows[0]
m['retrieval_accounting'].update(corpus_total=len(corpus), before_filter=len(corpus),
    after_filter=sum(case['stages'][1]['after_count'] for case in ledger_runs[0]['arms'][0]['cases']),
    presented_total=first['presented_roots'], presented_mean=first['presented_roots'] / len(frozen['cases']),
    presented_p50=0, presented_p95=first['presented_roots'], golden_recall=None,
    selectivity=first['presented_roots'] / len(frozen['cases']) / len(corpus))
m['retrieval_accounting']['stage_ledger']['sha256'] = sha(ledger_path)
summary = {'cases': rows, 'total': len(rows), 'legal_correctness_graded': False,
    'original_risk_cm_externally_transmitted': False, 'genos_executed': False,
    'answer_emitted_count': sum(row['answer_emitted'] for row in rows),
    'cited_answer_count': sum(row['answer_cited'] for row in rows),
    'request_success_count': sum(row['http_status'] == 200 for row in rows),
    'partial_answer_count': sum(row['answer_coverage'] == 'PARTIAL' for row in rows),
    'main_unchanged': all(row['active_pointer_unchanged'] for row in rows),
    'model_calls': sum(row['model_calls'] for row in rows), 'paired_delta': None,
    'paired_reason': 'Single unchanged arm, different public topics; no baseline/candidate comparison.',
    'usage': {key: sum(row['usage'][key] for row in rows) for key in ('input_tokens', 'output_tokens', 'cost_usd', 'seconds')},
    'latency': {'request_p50': statistics.median(row['seconds'] for row in rows),
                'request_p95': max(row['seconds'] for row in rows), 'n': len(rows)}}
put(ADR / 'artifacts/summary.json', summary)
m['results'].update(status='complete', by_arm={'baseline': {'total_count': len(rows), 'correct_count': None,
    'correctness_reason': 'Question-only synthetic public topics; no approved reference answers or semantic evaluator.',
    'answer_emitted_count': summary['answer_emitted_count'], 'cited_answer_count': summary['cited_answer_count'],
    'request_success_count': summary['request_success_count']}}, comparisons=[], judge_disagreements=0,
    usage=summary['usage'], latency=summary['latency'],
    error_taxonomy=[{'case_id': row['case_id'], 'type': 'other', 'reason': row['error']} for row in rows if row['error']])
put(ADR / '실험/manifest.json', m)

# Only closed isolated experiment databases are archived; all original bytes are recoverable.
archives = []
for case in frozen['cases']:
    directory = ADR / 'artifacts' / case['run_id'] / 'runtime'
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or '.sqlite' not in path.name or path.name.endswith('.gz'):
            continue
        raw = path.read_bytes()
        target = path.with_name(path.name + '.gz')
        assert not target.exists()
        with gzip.open(target, 'wb', compresslevel=9) as stream:
            stream.write(raw)
        assert gzip.decompress(target.read_bytes()) == raw
        archives.append({'path': str(path.relative_to(ROOT)), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
            'raw_bytes': len(raw), 'archive_path': str(target.relative_to(ROOT)), 'archive_sha256': sha(target),
            'archive_bytes': target.stat().st_size, 'verified_lossless': True,
            'restore': 'Decompress each database and its archived WAL/SHM/journal sidecars to recorded filenames in a separate inspection directory before opening SQLite; never overwrite serving state.'})
        path.unlink()
put(ADR / 'artifacts/runtime-archives.json', archives)
table = '| 주제 대응 | HTTP | 답변 | 인용 | 시간(초) | 모델 호출 | 답변 범위 |\n|---|---:|---|---|---:|---:|---|\n'
table += '\n'.join(f"| {row['topic_reference']} | {row['http_status']} | {'생성' if row['answer_emitted'] else '미생성'} | {'있음' if row['answer_cited'] else '없음'} | {row['seconds']:.3f} | {row['model_calls']} | {row['answer_coverage'] or '-'} |" for row in rows)
front = (ADR / 'README.md').read_text().split('---', 2)[1]
sections = {
    '1. 결정 요약': f"공개 합성 주제3건에서 답변 {summary['answer_emitted_count']}/3, 인용 포함 {summary['cited_answer_count']}/3, 실제 모델 {summary['model_calls']}회. 이 수치는 원본 risk_cm 정답률이 아니다. Proposed·in_sample·decision_eligible=false이며 MAIN은 그대로다.",
    '2. 문제와 변경 전 구조': '사용자는 risk_cm 등록 뒤 모델 답변 생성 확인을 요청했다. 내부 질문의 외부 반출 허용값을 변경하지 않고 세 개 일반 공개 규정 주제로 새 입력을 만들었다. service.service가 선택 릴리스·원문·코드 해시를 검증한 뒤 실제 RAG_ASK 경로를 사용한다. ADR0685는 외규 접두어 origin 분류에서 HTTP422/모델0회로 실패했으며, 후속 ADR0686은 그 결과를 보고 승인 공개 document_ids 경로를 별도로 동결한 실행이다.',
    '3. 가설과 사전 판정 기준': frozen['hypothesis'] + '\n\n' + frozen['criteria'] + '\n\n' + frozen['success_criteria'] + '\n\n' + frozen['failure_criteria'] + '\n\n' + frozen['regression_limits'] + '\n\n' + frozen['cost_latency_limits'],
    '4. 실험 설계': '단일 baseline arm·3개 주제 각1회·독립 새 프로세스/빈 runtime. 제품 구현·prompt·검색 정책 변경은 없다. 기존 전송의 schema adaptation과 메시지를 공통 ExperimentClient에 그대로 전달해 exact payload를 저장했다. 부모 ADR0681/session 완료 arm의 read-only 관찰이므로 구현 후보 snapshot은 해당되지 않는다. 결과를 본 뒤 수정한 입력은 새 ADR에 남겼다.',
    '5. 데이터·모델·재현성': f"{m['dataset']['name']} / {m['dataset']['version']}; 공개 질문만 외부 전송. 내부 원본 질문·사진·annotations·정답 후보·evidence index를 제품 입력에 넣지 않았다. 공개 승인145문서, {frozen['release']['data_path']}, session-runtime-v6-20261007-r1/generation45. Qwen3.8 qwen/qwen3.8-27b·OpenRouter Parasail FP8·reasoning effort none·fallback 없음. 코드/프로필/데이터/스키마/검색 정책 지문과 실제 health binding은 frozen.json 및 각 health.json/result.json에 결속했다. 최신 법적 효력·정답률 인증은 아니다.",
    '6. 결과': table + '\n\n답변 전체와 원문 출처·질문별 문제·실제 binding은 [실험 인덱스](실험/README.md) 및 artifacts/summary.json에 연결한다. HTTP200, 답변 생성, 인용, PARTIAL을 별도 집계했다. 정답 수/정답률·paired delta·judge 불일치 평가는 정답 승인 전이므로 수행하지 않았다.',
    '7. 사례별 오류 분석': '\n\n'.join(row['case_id'] + ': ' + (str(row['error']) if row['error'] else '실제 답변·인용·coverage·gap을 보존했다. 법률 의미 정답 판정은 미실시.') for row in rows),
    '8. 비용·지연·회수 규모': f"실제 모델 {summary['model_calls']}회, 입력 {summary['usage']['input_tokens']} / 출력 {summary['usage']['output_tokens']} tokens, USD {summary['usage']['cost_usd']:.6f}; 요청 p50 {summary['latency']['request_p50']:.3f}초 / 표본3개 p95(max) {summary['latency']['request_p95']:.3f}초. judge0회. 공개 원문 catalogue {len(corpus)} article-root. exact 회수·원문확보·모델 제시와 탈락 이유는 retrieval-ledger.json.gz. 표본별 제시 수는 질문별 표에 있다. gold가 없어 golden recall은 미측정. 원문 세대는 공유하며 닫힌 실험 SQLite는 무손실 압축·hash·복원 방법으로 보존했다.",
    '9. 해석': '모델이 답변을 생성하는지와 그 답변이 올바른지는 별도다. 공개 주제를 더 명확한 범위로 작성했으므로 원본 질문의 모호성·내규 의존성 또는 전체105문항의 품질 결론으로 확대하지 않는다. 실행 실패는 실패로 보존하며 다른 경로 성공이 이전 실패를 없애지 않는다.',
    '10. 한계와 일반화 가능 범위': '\n\n'.join(frozen['limitations']) + '\n\n동시에 실행한3개 요청의 시간에는 로컬 자원 경쟁도 포함된다. 독립적인 단일 요청 속도 인증이 아니다.',
    '11. 운영 결정·롤백 조건': '작업 제품 코드·선택 릴리스·MAIN45·원문 세대·질문 은행·반출 권한·GENOS 배포는 변경하지 않았다. 실험 runtime만 격리 경로에 썼다. 답변·판정을 golden 정답 또는 제품 Wiki로 승격하지 않았다. 동작 수정이나 추가 재실행은 새 ADR에서 기준을 사전 동결한다.',
    '12. 재현 명령': f"WSL /home/jin/8-AGENT의 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_{m['adr_id'].split('-')[1]}/run_probe.py run-001 (run-002,run-003 동일)이 동결된 실제 요청이다. 기존 run 폴더를 덮어쓰지 않으며 추가 실험은 새 ADR에 남긴다. 완료 검사는 stable runner adr_structure.py hash / validate --final / graph를 사용한다.",
}
(ADR / 'README.md').write_text('---' + front + '---\n\n# ' + m['adr_id'] + ': risk_cm 공개 주제 답변 관찰\n\n' +
    '\n\n'.join('## ' + key + '\n\n' + value for key, value in sections.items()) + '\n')
(ADR / '실험/README.md').write_text('# 공개 합성 질문·실행 인덱스\n\n' + table + '\n\n' +
    '\n'.join(f"- [{case['case_id']}]({case['file']}) — {case['run_id']}" for case in question_refs) +
    '\n\n원본 risk_cm 질문으로 실행한 결과가 아니며, 정답률은 채점하지 않았다. 각 파일에서 최종 답변 전체·원문 출처·exact provider 호출 경로와 hash를 확인할 수 있다.\n')
index = ROOT / '04_EXPERIMENTS/ADR/README.md'
link = '[' + m['adr_id'] + ' risk_cm 공개 주제 답변 관찰](' + ADR.name + '/README.md)'
if link not in index.read_text():
    index.write_text(index.read_text() + '\n- ' + link + f" — 공개 합성3건 답변{summary['answer_emitted_count']}/3, 모델{summary['model_calls']}회; MAIN 불변.\n")
files = [path for path in (ADR / 'artifacts').rglob('*') if path.is_file() and path != ADR / 'artifacts/manifest.json']
files += list((ROOT / '06_TOOLS/EXPERIMENTS' / ('adr_' + m['adr_id'].split('-')[1])).glob('*.py'))
finalizer = Path(__file__).resolve()
if finalizer not in files:
    files.append(finalizer)
put(ADR / 'artifacts/manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': m['adr_id'],
    'files': [{'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size} for path in sorted(files)]})
print(json.dumps({key: value for key, value in summary.items() if key != 'cases'}, ensure_ascii=False))
