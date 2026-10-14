"""Post-run source trace and exact canonical set accounting, without grading."""
from pathlib import Path
import gzip, hashlib, json, sqlite3, statistics, tempfile

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0684-venture-option-tax-navigation-local-probe'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
def put(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
class ArchivedConnection(sqlite3.Connection):
    def close(self):
        super().close()
        temporary = getattr(self, '_temporary', None)
        if temporary is not None:
            temporary.cleanup()

def ro(p):
    temporary = None
    if p.name.endswith('.sqlite.gz'):
        temporary = tempfile.TemporaryDirectory(prefix='adr0684-restored-')
        original = Path(temporary.name) / p.name.removesuffix('.gz')
        original.write_bytes(gzip.decompress(p.read_bytes()))
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = p.with_name(p.name.removesuffix('.gz') + suffix + '.gz')
            if sidecar.exists():
                original.with_name(original.name + suffix).write_bytes(gzip.decompress(sidecar.read_bytes()))
        p = original
    db = sqlite3.connect(p.resolve().as_uri() + '?mode=ro', uri=True, factory=ArchivedConnection)
    db._temporary = temporary
    db.row_factory = sqlite3.Row
    return db
def fence(v): return '```json\n' + json.dumps(v, ensure_ascii=False, indent=2) + '\n```'

frozen = read(ADR / 'artifacts/design/frozen.json')
m = read(ADR / '실험/manifest.json')
nav = ro(ROOT / frozen['release']['data_path'] / 'navigation/navigation.sqlite')
sources = {x['id']: json.loads(x['json']) for x in nav.execute('SELECT id,json FROM source')}
nav.close()
scope = set(read(ROOT / frozen['release']['code_root'] / '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
def identities(ids):
    return [json.loads(x) for x in sorted({canon({'doc_id': sources[s]['document_id'], 'node': int(sources[s]['unit_id'])})
        for s in ids if s in sources and str(sources[s]['unit_id']).isdigit()})]
def offered(v):
    ids = set()
    def walk(x):
        if isinstance(x, dict):
            if x.get('source_id') in sources and isinstance(x.get('text'), str) and x['text']:
                ids.add(x['source_id'])
            for value in x.values(): walk(value)
        elif isinstance(x, list):
            for value in x: walk(value)
    walk(v)
    return ids
def source_label(sid):
    source = sources.get(sid, {})
    return {'source_id': sid, 'document_id': source.get('document_id'),
            'document_name': source.get('document_name'), 'heading': source.get('heading'),
            'article_unit_id': source.get('unit_id')}

corpus = identities(s for s, v in sources.items() if v['document_id'] in scope)
rows, ledger_runs, transcripts, stage_tables = [], [], {}, {}
for run in frozen['runs']:
    directory = ADR / 'artifacts' / run
    result = read(directory / 'result.json')
    journals = list((directory / 'runtime').rglob('journal.sqlite')) or list((directory / 'runtime').rglob('journal.sqlite.gz'))
    assert len(journals) == 1
    db = ro(journals[0])
    events = [{'seq': x['seq'], 'kind': x['kind'], 'payload': json.loads(x['payload_json'])}
              for x in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq')]
    stages = [{'entity_id': x['entity_id'], 'payload': json.loads(x['payload_json'])}
              for x in db.execute("SELECT entity_id,payload_json FROM entity_version WHERE kind='case_stage' ORDER BY created_seq")]
    acquired_ids = {x[0] for x in db.execute('SELECT DISTINCT source_id FROM evidence_unit')}
    db.close()
    latest = {x['entity_id'].removeprefix('case:'): x['payload'] for x in stages}
    recalls = [x['payload'] for x in stages if x['entity_id'] == 'case:RECALL']
    recalled = identities(s for value in recalls for s in value.get('selected_for_read', []))
    acquired = identities(acquired_ids)
    presented_ids = set()
    calls = []
    for call in sorted((directory / 'provider').glob('call-*')):
        request_file = call / 'request.json'
        if request_file.exists():
            request = read(request_file)
            for message in request.get('body', request).get('messages', []):
                try: presented_ids.update(offered(json.loads(message.get('content', ''))))
                except (ValueError, TypeError): pass
        calls.append({'call': call.name, 'files': {p.name: {'path': str(p.relative_to(ROOT)),
            'sha256': sha(p), 'bytes': p.stat().st_size} for p in sorted(call.glob('*.json'))}})
    presented = identities(presented_ids)
    directories = [x for x in events if x['kind'] == 'LAW_FULLTEXT_DIRECTORY']
    decisions = [x for x in events if x['kind'] in ('LAW_SELECTION_DECISION', 'LAW_BRANCH_DECISION',
        'UNIT_READ_CHOICE', 'LAW_DECISION_REJECTED', 'LAW_DECISION_RETRY', 'INVESTIGATION_BOUNDED_STOP')]
    # UNIT_READ_CHOICE is an explicit model tool choice. Initial recall can
    # also acquire a tax-law preview; keep that separate from model navigation.
    read_choices = [x for x in decisions if x['kind'] == 'UNIT_READ_CHOICE']
    explicit_laws = list(dict.fromkeys(x['payload'].get('document_name') for x in read_choices))
    selection = latest.get('SELECT', {})
    final_ids = selection.get('final_ids', [])
    output = result.get('output') or {}
    meta = output.get('assembly', {}).get('term_agent', {})
    claims = (output.get('answer') or {}).get('claims', [])
    answer_ids = list(dict.fromkeys(s for claim in claims for s in claim.get('source_ids', [])))
    tax_reads = [x for x in read_choices if '조세특례제한법' in x['payload'].get('document_name', '')]
    venture_reads = [x for x in read_choices if '벤처기업' in x['payload'].get('document_name', '')]
    trace = {'run_id': run, 'directories': directories, 'decisions': decisions,
        'selected_originals': [source_label(s) for s in final_ids],
        'answer_sources': [source_label(s) for s in answer_ids],
        'latest_stage_keys': list(latest), 'native_binding': latest.get('READ', {}).get('binding')}
    put(directory / 'navigation-trace.json', trace)
    row = {'run_id': run, 'http_status': result['http_status'], 'seconds': result['seconds'],
        'model_calls': result['model_calls'], 'first_law_order': [x.get('name') for x in directories[0]['payload']['laws']] if directories else [],
        'explicit_read_laws': explicit_laws, 'tax_model_read_count': len(tax_reads),
        'venture_model_read_count': len(venture_reads), 'tax_navigation_reproduced': bool(tax_reads),
        'tax_preview_sources': [source_label(s) for s in sorted(acquired_ids) if '조세특례제한법' in sources.get(s, {}).get('document_name', '')],
        'final_selected_sources': [source_label(s) for s in final_ids], 'answer_sources': trace['answer_sources'],
        'answer_text': (output.get('answer') or {}).get('text'),
        'answer_status': output.get('answer_status'), 'error': output.get('detail') or output.get('error') or result.get('exception'),
        'answer_coverage': meta.get('answer_coverage'), 'stop_reason': meta.get('stop_reason'),
        'gaps': meta.get('gaps'), 'issue_assessments': meta.get('issue_assessments'),
        'active_pointer_unchanged': result['pointer_before'] == result['pointer_after'] == frozen['bindings']['01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'],
        'acquired_roots': len(acquired), 'presented_roots': len(presented),
        'presented_document_ids_authorized': all(sources[s]['document_id'] in scope for s in presented_ids),
        'usage': {k: sum(x.get(k, 0) or 0 for x in result['usage']) for k in ('input_tokens', 'output_tokens', 'cost_usd', 'seconds')}}
    rows.append(row)
    put(directory / 'diagnostic.json', row)
    transcripts[run] = calls
    before, ledger = [], []
    reasons = ['Approved immutable source catalogue', 'Not in the executed initial recall candidates',
               'No original READ in this run', 'No source text in any actual provider input in this run']
    for i, after in enumerate([corpus, recalled, acquired, presented]):
        plan = m['design']['retrieval_stage_plan']['stages_by_arm']['baseline'][i]
        bm, am = {canon(x): x for x in before}, {canon(x): x for x in after}
        added = [am[k] for k in sorted(am.keys() - bm.keys())]
        discarded = [bm[k] for k in sorted(bm.keys() - am.keys())]
        ledger.append({**plan, 'executed': True, 'skip_reason': None,
            'before': before, 'added': added, 'discarded': discarded, 'after': after,
            'before_count': len(before), 'added_count': len(added), 'discarded_count': len(discarded), 'after_count': len(after),
            'occurrence_counts': {'before': len(before), 'after': len(after), 'canonical_collapsed_before': 0, 'canonical_collapsed_after': 0},
            'discard_receipts': [{'identity': x, 'reason': reasons[i]} for x in discarded],
            'discard_reason_counts': {reasons[i]: len(discarded)} if discarded else {},
            'gold_total': 0, 'gold_before': 0, 'gold_added': 0, 'gold_discarded': 0, 'gold_after': 0,
            'golden_recall': None, 'gold_before_identities': [], 'gold_added_identities': [],
            'discarded_gold': [], 'gold_after_identities': []})
        before = after
    case = {'schema_version': 'retrieval-stage-ledger-v1', 'computed_post_selection': True,
        'gold_visible_to_product': False, 'accounting_unit': 'case_id + canonical article-root coordinate',
        'arm_id': 'baseline', 'case_id': 'venture-option-exercise', 'gold_total': 0, 'gold_identities': [], 'stages': ledger}
    ledger_runs.append({'run_id': run, 'arms': [{'arm_id': 'baseline',
        'declared_stage_ids': ['catalogue', 'recall', 'acquired', 'presented'], 'cases': [case],
        'aggregate': {'cases': 1, 'presented_total': len(presented), 'gold_total': 0}}]})
    stage_tables[run] = [{k: stage[k] for k in ('stage_id', 'before_count', 'added_count', 'discarded_count', 'after_count')} for stage in ledger]
    mrun = next(x for x in m['runs'] if x['id'] == run)
    mrun.update(status='complete', sha256=sha(directory / 'result.json'))

ledger = {'schema_version': 'retrieval-stage-ledger-v1', 'adr_id': m['adr_id'], 'experiment_id': m['experiment_id'],
    'accounting_unit': 'case_id + canonical article-root coordinate', 'computed_post_selection': True,
    'gold_visible_to_product': False, 'runs': ledger_runs,
    'audit': {'gold': 'No legal gold was provided; this is source-navigation reproduction, not legal accuracy grading',
              'acquired': 'Includes deterministic initial recall previews and context reads; does not imply legal adoption',
              'presented': 'Actual text-bearing source IDs in exact physical provider requests, including context ancestors',
              'stages': 'Aggregate trace sets across the whole run; expansion can add roots after initial recall'}}
ledger['artifact_sha256'] = hashlib.sha256(canon(ledger).encode()).hexdigest()
ledger_path = ADR / 'artifacts/retrieval-ledger.json.gz'
with gzip.open(ledger_path, 'wt', encoding='utf-8', compresslevel=9) as stream:
    stream.write(canon(ledger))
presented_total = rows[0]['presented_roots']
m['retrieval_accounting'].update(corpus_total=len(corpus), before_filter=len(corpus),
    after_filter=ledger_runs[0]['arms'][0]['cases'][0]['stages'][1]['after_count'],
    presented_total=presented_total, presented_mean=presented_total, presented_p50=presented_total,
    presented_p95=presented_total, golden_recall=None, selectivity=presented_total / len(corpus))
m['retrieval_accounting']['stage_ledger']['sha256'] = sha(ledger_path)
summary = {'question': frozen['question'], 'runs': rows, 'legal_correctness_graded': False,
    'tax_candidate_first_count': sum(bool(x['first_law_order']) and '조세특례제한법' in x['first_law_order'][0] for x in rows),
    'tax_model_navigation_count': sum(x['tax_navigation_reproduced'] for x in rows),
    'venture_model_navigation_count': sum(x['venture_model_read_count'] > 0 for x in rows),
    'request_success_count': sum(x['http_status'] == 200 for x in rows),
    'partial_answer_count': sum(x['answer_coverage'] == 'PARTIAL' for x in rows),
    'main_unchanged': all(x['active_pointer_unchanged'] for x in rows),
    'paired_delta': None, 'paired_reason': 'Single unchanged arm; repetitions are not a baseline/candidate comparison',
    'usage': {k: sum(x['usage'][k] for x in rows) for k in ('input_tokens', 'output_tokens', 'cost_usd', 'seconds')},
    'latency': {'request_p50': statistics.median(x['seconds'] for x in rows),
                'request_p95': max(x['seconds'] for x in rows), 'n': 2}, 'genos_executed': False}
put(ADR / 'artifacts/summary.json', summary)
m['results'].update(status='complete', by_arm={'baseline': {'total_count': 2, 'correct_count': None,
    'correctness_reason': 'No semantic evaluator or legal gold', 'request_success_count': summary['request_success_count'],
    'tax_candidate_first_count': summary['tax_candidate_first_count'], 'tax_model_navigation_count': summary['tax_model_navigation_count']}},
    comparisons=[], judge_disagreements=0, usage=summary['usage'], latency=summary['latency'], error_taxonomy=[])
put(ADR / '실험/manifest.json', m)
question = ADR / '실험/질문-001-venture-option-exercise.md'
question.write_text('\n\n'.join(['# venture-option-exercise', '## 1. 실행 메타',
    'run-001, run-002 / baseline unchanged MAIN45 / independent fresh state / public source / Qwen3.8 Parasail FP8 reasoning none',
    '## 2. 사용자 질문 원문', frozen['question'], frozen['question_origin'],
    '## 3. 기준답변 — 채점 전용, 제품 입력 비공개', '법률 정답·gold 좌표를 사용하지 않았다. 모델에는 질문과 승인 원문만 전달했다.',
    '## 4. 제품 입력을 구성한 원값', '각 run의 request.json, profile.json, health.json과 frozen.json에 입력·실행 binding을 보존한다. 전체 원문 입력은 아래 provider request 원본을 참조한다.',
    '### 회수·탈락 단계 원장 — run·arm별', fence(stage_tables), '전체 exact 좌표와 탈락 이유: artifacts/retrieval-ledger.json.gz. 후속 확장과 초기 미열람 preview를 구분하며 gold가 없어 recall은 미측정이다.',
    '## 5. 제품 모델 호출 — run·arm별 실제 원문', fence(transcripts),
    '## 6. 중간 LLM 호출 — router/compiler/verifier/repair', '위 각 provider 원본에 모든 중간 호출·출력·schema·usage가 포함된다. navigation-trace.json의 event seq로 법령 선택·READ·거절·재조사 이유를 대조한다.',
    '## 7. 채점 호출과 반복 판정', '채점 호출 0회. 두 반복은 별도 새 프로세스와 새 runtime이다. 후보 노출, 원문 확보, 모델 READ, 최종 채택은 별도 지표다. 모델 비교·paired delta는 없다.',
    '## 8. 사례 최종 판정', fence(summary)]) + '\n')
print(json.dumps({k: v for k, v in summary.items() if k not in ('runs', 'usage')}, ensure_ascii=False))
