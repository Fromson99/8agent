"""Read-only audit and closure for ADR-1416..1421; no model calls, failures preserved.

Usage: close_adr.py ADR-1416-guided-continue-connection-qwen
"""
import sys, json, hashlib, gzip, sqlite3, statistics
from pathlib import Path
ROOT = Path('/home/jin/8-AGENT')
NAME = sys.argv[1]
ADR = ROOT/'04_EXPERIMENTS/ADR'/NAME; ART = ADR/'artifacts'; DES = ART/'design'; RUN = ART/'run-001'
sys.path.insert(0, str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_raw_json


def read(p):
    p = Path(p)
    with (gzip.open(p, 'rt') if p.suffix == '.gz' else p.open()) as f: v = json.load(f)
    if isinstance(v, dict) and set(v) == {'raw_json'}: return read(ROOT/v['raw_json']['path'] if not Path(v['raw_json']['path']).is_absolute() else v['raw_json']['path'])
    return v


def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def put(p, v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')


ADR_ID = NAME[:8]
REVIEWS = {
 'ADR-1416': {
  ('charter-natural-continue', 1): (False, '433조만 읽고 결의 수치는 확인한 원문에 없다고 밝힌 뒤 368조를 이어서 읽을지 물음. 434조 미확보.', 'early_answer_without_connection_lookup'),
  ('charter-natural-continue', 2): (False, '"어 계속 찾아줘"가 기존 조사 연결 판단 거절로 CLARIFY. 조사 0회.', 'naive_continue_not_resumed'),
  ('charter-433-continue', 1): (False, '433조만 설명하고 구체 의결요건을 함께 확인할지 물음. 434조 미확보.', 'early_answer_without_connection_lookup'),
  ('charter-433-continue', 2): (None, 'memory-resolve 호출이 HTTP200 이후 응답 미완료로 179.9초 기한 종료(UNKNOWN)→API504. 판정 불가. 동결 규칙에 따라 이후 셀(후보 arm) 미실행.', 'provider_unknown')},
 'ADR-1417': {
  ('charter-natural-continue', 1): (False, '433조 READ 직후 연결 조회 없이 ANSWER. 결의 수치 누락인데 미확인 표시 없이 COVERED. MAIN157보다 부족 표시가 약함.', 'early_answer_without_connection_lookup'),
  ('charter-natural-continue', 2): (None, 'memory-resolve 진행 중 호스트 스왑 증가가 128MiB 기준 초과(exit125). 운영자가 같은 시각 패키지 ZIP을 생성한 병행 작업과 겹침. 결과 불명.', 'resource_stop_operator_concurrency'),
  ('charter-433-continue', 1): (False, '433조 READ 후 연결 조회 없이 ANSWER, 수치 누락·COVERED. 이 셀은 앞 셀의 자원 중단 뒤에 연쇄 실행기가 자원 중단 파일을 확인하지 않아 동결 중지 규칙을 어기고 실행됨(프로토콜 이탈, 판정 제외).', 'protocol_deviation'),
  ('charter-433-continue', 2): (None, 'memory-resolve 진행 중 자원 가드 중단(exit125). 운영자가 회귀 검사를 동시에 실행. 결과 불명·판정 제외.', 'resource_stop_operator_concurrency')},
 'ADR-1418': {
  ('charter-natural-continue', 1): (True, '433조 READ→메뉴에서 ANSWER 제외(연결 첫 조회 필수)→FOLLOW→작은 연결목록 자동 읽기로 434·363조 확보→ANSWER. 434조 원문의 3분의 2·3분의 1 두 수치와 분모를 그대로 답함.', None),
  ('charter-natural-continue', 2): (True, '"어 계속 찾아줘"→RESEARCH_CONTINUE·SELECT 재개→SEARCH/READ로 435조 확보→종류주주총회 요건까지 추가. 같은 goal·목적 유지.', None),
  ('charter-433-continue', 1): (True, '같은 경로로 434조 확보, 두 수치 정확히 답함.', None),
  ('charter-433-continue', 2): (None, 'memory-resolve 호출이 응답 미완료로 182.0초 기한 종료(UNKNOWN)→API504. MAIN157과 같은 단계의 공급자 무응답. 판정 불가.', 'provider_unknown')},
 'ADR-1421': {
  ('charter-natural-unread', 1): (True, '433조 READ→FOLLOW 한 번에 363조(정방향)·434조(구체화 쌍)와 같은 절 435조(절 제목 핵심어 일치)를 모델 호출 없이 자동 확보→ANSWER. 434조 두 수치(3분의 2·3분의 1)와 435조 종류주주총회 요건 정확. 답변 끝에 "같은 절(제5절 정관의 변경)에 있는 제436조(준용규정): 지금은 정관변경이 아닌 분할·합병·주식교환·주식이전으로 인한 손해에 대한 준용 규정이므로 읽을 필요가 없다고 판단했습니다. 필요하면 말씀해 주세요." 표시(모델 이유). 실제 응답으로 GENOS 화면 미확인 조문 카드1·원문 펼침, text hash 일치.', None),
  ('charter-natural-unread', 2): (True, '"확인하지 않은 연결 조문도 읽어줘"→조사 재개·436조 READ 후 준용 대상(분할·합병·주식교환·주식이전)과 435조 요건 적용을 설명. 남은 미확인 연결 0건.', None)},
 'ADR-1420': {
  ('charter-natural-continue', 1): (True, '433조 READ→FOLLOW 한 번에 정방향 363조와 역방향 구체화 434조를 모델 호출 없이 자동 확보→ANSWER. 434조 원문의 3분의 2·3분의 1 두 수치 정확. 같은 절 목록에 435조가 미열람으로 제시됐지만 읽지도 미확인 표시도 하지 않음(판정 기준 밖 관찰).', None),
  ('charter-natural-continue', 2): (True, '"어 계속 찾아줘"→RESEARCH_CONTINUE·SELECT 재개→435조 READ로 종류주주총회 요건 추가. 360조의3도 추가로 읽었으나 답변에 불필요한 조회.', None),
  ('charter-434-landing', 1): (True, '434조 READ→FOLLOW→정방향 구체화(433조①) 자동 확보→두 수치 정확. 434조를 빌려 쓰는 조문은 차용21·준용6 개수만 제공되고 본문은 읽지 않음.', None),
  ('exception-542-4-landing', 1): (None, '두 번째 모델 호출 직후 자원 가드 중단(앱 적재 뒤 기준 스왑 증가129MiB, 가용 RAM 약9GB, 진행 중 호출 없음, 운영자 병행 작업 없음). 실모델 판정 불가. 같은 경로는 실제 데이터 무모델 각본 실행에서 542조의4→363조①(예외) 자동 확보로 확인.', 'resource_stop_page_cache')},
 'ADR-1419': {
  ('charter-natural-continue', 1): (None, '첫 모델 호출(request-entry) 정상 응답 직후 자원 가드가 호스트 스왑 증가 130MiB(기준128MiB)로 중단(exit125). 앱 적재로 RSS2.7GB, 백그라운드 Oracle/neo4j 유휴 페이지 스왑아웃. 진행 중 호출 없음. 운영자 병행 작업 없음.', 'resource_stop_app_load'),
  ('charter-natural-continue', 2): (None, '선행 중단으로 미실행.', 'not_executed'),
  ('charter-434-landing', 1): (None, '동결 중지 규칙으로 미실행(실행기 가드가 차단, 모델0).', 'not_executed'),
  ('exception-542-4-landing', 1): (None, '동결 중지 규칙으로 미실행(실행기 가드가 차단, 모델0).', 'not_executed')}}[ADR_ID]
MAIN = {'ADR-1416': 157, 'ADR-1417': 158, 'ADR-1418': 159, 'ADR-1419': 160, 'ADR-1420': 160, 'ADR-1421': 161}[ADR_ID]

baseline = read(DES/'baseline.json'); data = ROOT/baseline['release']['data_path']
source = sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro', uri=True)
meta = read(data/'manifest.json'); assert sha(data/'store.sqlite') == meta['store_sha256']
cells = [d for d in sorted((ART/'public-live').iterdir()) if (d/'calls.json').exists()]
unit_cache = {}; block_cache = {}; versions = {}


def original(did, bid):
    key = (did, str(bid))
    if key not in block_cache:
        block_cache[key] = source.execute('SELECT unit_id,text,source_artifact_sha256 FROM source_block WHERE document_id=? AND block_id=?', key).fetchone()
    return block_cache[key]


def article(did, bid):
    if did not in unit_cache:
        unit_cache[did] = {str(u): (None if p is None else str(p), json.loads(v)) for u, p, v in source.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?', (did,))}
    b = original(did, bid)
    if b is None: return None
    uid = str(b[0]); seen = set(); units = unit_cache[did]
    while uid in units and uid not in seen:
        seen.add(uid); parent, v = units[uid]
        if v.get('family') == 'kr_article': return [did, uid, (v.get('surface') or '')]
        uid = parent
    return None


def strings(v):
    if isinstance(v, str): yield v
    elif isinstance(v, dict):
        for x in v.values(): yield from strings(x)
    elif isinstance(v, list):
        for x in v: yield from strings(x)


audits = []
for d in cells:
    binding = read(d/'binding.json'); C = Path(binding['code_root'])
    sys.path[:0] = [str(C/'02_BACKEND')]
    for k in [k for k in sys.modules if k.startswith('semantic_runtime')]: del sys.modules[k]
    from semantic_runtime.legal_agent import journal_storage
    from semantic_runtime.legal_agent.local_gemma import provider_request
    sys.path.remove(str(C/'02_BACKEND'))
    calls = read(d/'calls.json'); raws = [read(p) for p in sorted((d/'raw').glob('call-*/request.json.gz'))]
    allowed = set(binding['scope']); acquired = {}; presented = {}
    a = {'cell': d.name, 'source_checks': 0, 'delivered_checks': 0, 'source_mismatches': [], 'acl_violations': [], 'wire_mismatches': [], 'attempts': 0, 'reserved': 0}

    def verify(did, s, where):
        if did not in allowed: a['acl_violations'].append({'where': where, 'document_id': did}); return
        b = original(did, s['block_id'])
        if b is None or b[1][s['start_cp']:s['end_cp']] != s['text']:
            a['source_mismatches'].append({'where': where, 'document_id': did, 'block_id': s['block_id']}); return
        root = article(did, s['block_id'])
        if root: (acquired if where == 'acquired' else presented)[root[0]+':'+root[1]] = root[2]
    reserved = {}
    for jp in sorted((d/'runtime').rglob('*.sqlite')):
        try:
            db = journal_storage.connect(jp.as_uri()+'?mode=ro', uri=True); tables = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.OperationalError:
            # A process stopped by the resource guard leaves a hot journal. Read a
            # recovered copy; the original runtime files stay untouched.
            import shutil, tempfile
            tmp = Path(tempfile.mkdtemp(dir=str(ART))); copy = tmp/jp.name
            for suffix in ('', '-wal', '-shm', '-journal'):
                if Path(str(jp)+suffix).exists(): shutil.copyfile(str(jp)+suffix, str(copy)+suffix)
            db = journal_storage.connect(str(copy)); tables = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            a.setdefault('recovered_journal_copies', []).append(str(jp.relative_to(ROOT)))
        if {'evidence_unit', 'evidence_span'} <= tables:
            for x in db.execute('SELECT u.document_id,s.block_id,s.start_cp,s.end_cp,s.text FROM evidence_unit u JOIN evidence_span s ON s.evidence_id=u.evidence_id'):
                verify(x['document_id'], dict(x), 'acquired'); a['source_checks'] += 1
        if 'model_attempt' in tables:
            for x in db.execute('SELECT * FROM model_attempt ORDER BY created_seq'):
                a['attempts'] += 1; out = provider_request(json.loads(x['request_json'])); out['usage'] = {'include': True}
                if out not in raws: a['wire_mismatches'].append(x['attempt_id'])
        if {'event', 'budget'} <= tables and {'kind', 'payload_json'} <= {x[1] for x in db.execute('PRAGMA table_info(event)')}:
            amounts = [dict(x) for x in db.execute('SELECT * FROM budget')]
            for x in db.execute("SELECT payload_json FROM event WHERE kind='REQUEST_BUDGET_BOUND'"):
                key = json.loads(x[0])['request_key']; reserved[key] = max(reserved.get(key, 0), *[b.get('model_reserved', 0) for b in amounts])
        db.close()
    for leftover in ART.glob('tmp*'):
        if leftover.is_dir():
            import shutil; shutil.rmtree(leftover)
    wire_texts = [t for p in raws for m in p.get('messages', []) for t in strings((lambda c: (json.loads(c) if c.strip().startswith(('{', '[')) else c))(m.get('content', '')))]

    def walk(v):
        if isinstance(v, dict):
            if v.get('document_id') and isinstance(v.get('spans'), list):
                for s in v['spans']:
                    if isinstance(s, dict) and all(k in s for k in ('block_id', 'start_cp', 'end_cp', 'text')) and s['text'] and any(s['text'] in t for t in wire_texts):
                        verify(v['document_id'], s, 'wire'); a['delivered_checks'] += 1
            for x in v.values(): walk(x)
        elif isinstance(v, list):
            for x in v: walk(x)
    for p in sorted((d/'canonical').glob('[0-9][0-9][0-9].json.gz')): walk(read(p)['view'])
    a.update(acquired_articles=acquired, presented_articles=presented, physical_calls=len(calls), unknown=sum(c['status'] == 'unknown' for c in calls),
             reported_cost_usd=sum((c.get('usage') or {}).get('cost', 0) or 0 for c in calls), reported_tokens=sum((c.get('usage') or {}).get('total_tokens', 0) or 0 for c in calls),
             model_seconds=sum(c.get('seconds', 0) or 0 for c in calls), reserved=sum(reserved.values()),
             output_caps=[k for p in raws for k in ('max_tokens', 'max_output_tokens', 'max_completion_tokens') if k in p],
             resource_stop=read(d/'resource-stop.json')['reason'] if (d/'resource-stop.json').exists() else None,
             resource_final=(d/'resource-final.json').exists())
    # A process killed by the resource guard cannot journal the in-flight attempt; compare budget with that known gap.
    a['budget_matches'] = a['reserved'] == a['attempts'] and a['attempts'] in (len(calls), len(calls)-1 if a['resource_stop'] else len(calls))
    put(d/'audit.json', a); audits.append(a)
source.close()
put(ART/'source-wire-audit.json', {'cells': audits, 'model_calls': 0, 'counting': 'Original spans compared byte-for-byte; delivery requires literal text in the actual outbound request; ACL against the cell scope.'})

rows = []; calls_all = []
cases_frozen = read(DES/'live-cases.json')
for d in cells:
    case_id = d.name.rsplit('-', 1)[0]
    r = read(d/'result.json') if (d/'result.json').exists() else {'case_id': case_id, 'turns': [],
        'unexecuted_steps': [x['number'] for x in next(c for c in cases_frozen if c['id'] == case_id)['steps']]}
    calls = read(d/'calls.json'); calls_all.extend(calls); a = next(x for x in audits if x['cell'] == d.name)
    for t in r['turns']:
        n = t['step']['number']; ok, why, tax = REVIEWS[(r['case_id'], n)]
        ans = d/('turn-%d' % n)/'public-answer.txt'
        rows.append({'case_id': r['case_id'], 'arm': read(d/'binding.json')['arm'], 'turn': n, 'question': t['step']['question'], 'http_status': t['http_status'], 'status': t['status'], 'method': t['method'],
                     'executed': t['executed'], 'physical_calls': t['physical_calls'], 'seconds': t['request_seconds'], 'unknown': t['unknown'], 'claims': t['claims'],
                     'answer': ans.read_text() if ans.exists() else None, 'semantic_pass': ok, 'review': why, 'taxonomy': tax,
                     'duplicate': t.get('duplicate')})
    for n in r.get('unexecuted_steps', []):
        if any(x['case_id'] == r['case_id'] and x['turn'] == n for x in rows): continue
        ok, why, tax = REVIEWS[(r['case_id'], n)]
        rows.append({'case_id': r['case_id'], 'arm': read(d/'binding.json')['arm'], 'turn': n, 'question': None, 'http_status': None, 'status': 'NOT_COMPLETED', 'semantic_pass': ok, 'review': why, 'taxonomy': tax, 'answer': None, 'physical_calls': len(calls) if not r['turns'] and n == 1 else 0})
    assert not a['source_mismatches'] and not a['acl_violations'] and not a['wire_mismatches'] and not a['output_caps'], a
for c in cases_frozen:
    if any(x['case_id'] == c['id'] for x in rows):continue
    for step in c['steps']:
        ok, why, tax = REVIEWS[(c['id'], step['number'])]
        rows.append({'case_id': c['id'], 'arm': 'candidate', 'turn': step['number'], 'question': step['question'], 'http_status': None, 'status': 'NOT_EXECUTED', 'semantic_pass': ok, 'review': why, 'taxonomy': tax, 'answer': None})
for row in rows:
    if row['semantic_pass']:
        assert row['answer'] and all(x in row['answer'] for x in ('3분의 2', '3분의 1')), row['case_id']
put(ART/'direct-review.json', rows)
judged = [r for r in rows if r['semantic_pass'] is not None and r['taxonomy'] != 'protocol_deviation']
result = {'state': 'CLOSED_WITH_RECORDED_STOPS', 'main_generation': MAIN, 'release_id': baseline['pointer']['release_id'], 'turns': rows,
          'judged_turns': len(judged), 'passed_turns': sum(bool(r['semantic_pass']) for r in judged),
          'physical_calls': len(calls_all), 'unknown': sum(c['status'] == 'unknown' for c in calls_all), 'started_without_outcome': sum(c['status'] == 'started' for c in calls_all),
          'reported_cost_usd': sum((c.get('usage') or {}).get('cost', 0) or 0 for c in calls_all),
          'reported_prompt_tokens': sum((c.get('usage') or {}).get('prompt_tokens', 0) or 0 for c in calls_all),
          'reported_completion_tokens': sum((c.get('usage') or {}).get('completion_tokens', 0) or 0 for c in calls_all),
          'source_checks': sum(a['source_checks'] for a in audits), 'delivered_checks': sum(a['delivered_checks'] for a in audits),
          'source_acl_wire_mismatches': 0, 'output_caps': 0, 'budgets_match': all(a['budget_matches'] for a in audits),
          'duplicate_extra_model_calls': sum((r.get('duplicate') or {}).get('extra_model_calls', 0) for r in rows),
          'latency_seconds': {'per_turn': [r.get('seconds') for r in rows], 'median': statistics.median([r['seconds'] for r in rows if r.get('seconds')]) if any(r.get('seconds') for r in rows) else None, 'p95': None, 'p95_reason': 'two questions, single runs'},
          'quality_certified': False, 'judge_calls': 0, 'scope': 'One run per formulation; not a repeatability rate or general legal accuracy.'}
put(ART/'result.json', result)
RUN.mkdir(exist_ok=True)
put(RUN/'result.json', {'result_path': str((ART/'result.json').relative_to(ROOT)), 'sha256': sha(ART/'result.json')})

# retrieval stage ledger (article roots per cell)
sys.path.insert(0, str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder, identity_canonicalizer, grade_capture, build_run_artifact, build_experiment_artifact, deterministic_sha256
m = read(ADR/'실험/manifest.json'); captures = []; counts = {}; acq = {}; arms_run = sorted({read(d/'binding.json')['arm'] for d in cells})
# ADR-1416 froze both arms in run-001; its candidate cells were stopped by the frozen rule and are recorded as unexecuted.
if ADR_ID == 'ADR-1416': arms_run = ['baseline', 'candidate']
for q in m['questions']:
    for arm in arms_run:
        a = next((x for x in audits if x['cell'] == q['case_id']+'-'+arm), None)
        rec = StageLedgerRecorder(q['case_id'], arm, identity_canonicalizer)
        if a:
            pair = lambda k: (k.split(':')[0], int(k.split(':')[1]))
            acquired = sorted(pair(k) for k in a['acquired_articles']); presented = sorted(pair(k) for k in a['presented_articles'])
            rec.record_stage('source', 'source', acquired); rec.record_stage('acquired', 'retrieve', acquired, parent_stage_ids=('source',))
            rec.record_stage('present', 'present', presented, parent_stage_ids=('acquired',), discard_reasons={x: 'Not observed in actual outbound input' for x in set(acquired)-set(presented)})
        else:
            for sid, kind, parents in [('source', 'source', ()), ('acquired', 'retrieve', ('source',)), ('present', 'present', ('acquired',))]:
                rec.record_stage(sid, kind, [], parent_stage_ids=parents, executed=False, skip_reason='Cell not executed: frozen stop rule after an earlier UNKNOWN')
            acquired = []; presented = []
        captures.append(grade_capture(rec.capture(), [])); acq.setdefault(arm, []).append(len(acquired)); counts.setdefault(arm, []).append(len(presented))
ledger = build_experiment_artifact(ADR_ID, m['experiment_id'], [build_run_artifact('run-001', captures, {arm: ['source', 'acquired', 'present'] for arm in arms_run})])
ledger['artifact_sha256'] = deterministic_sha256({k: v for k, v in ledger.items() if k != 'artifact_sha256'})
lp = ART/'retrieval-stage-ledger.json.gz'
if not lp.exists(): write_raw_json(lp, ledger)
src = sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro', uri=True); scope_docs = sorted({did for d in cells for did in read(d/'binding.json')['scope']})
corpus = sum(1 for did in scope_docs for (raw,) in src.execute('SELECT json FROM source_unit WHERE document_id=?', (did,)) if json.loads(raw).get('family') == 'kr_article'); src.close()
m['retrieval_accounting'] = {'changed': ADR_ID != 'ADR-1416', 'corpus_total': corpus, 'before_filter': {arm: sum(acq[arm]) for arm in arms_run}, 'after_filter': {arm: sum(acq[arm]) for arm in arms_run},
    'presented_total': {arm: sum(counts[arm]) for arm in arms_run}, 'presented_mean': {arm: statistics.mean(counts[arm]) for arm in arms_run}, 'presented_p50': {arm: statistics.median(counts[arm]) for arm in arms_run},
    'presented_p95': {arm: sorted(counts[arm])[min(len(counts[arm])-1, max(0, round((len(counts[arm])-1)*.95)))] for arm in arms_run}, 'golden_recall': {arm: None for arm in arms_run}, 'selectivity': {arm: statistics.mean(counts[arm])/corpus for arm in arms_run},
    'not_applicable_reason': 'Article roots acquired/presented per cell; no independent gold recall or corpus denominator.',
    'stage_ledger': {'mode': 'measured', 'schema_version': 'retrieval-stage-ledger-v1', 'accounting_unit': 'case_id + canonical article-root coordinate', 'summary_run_id': 'run-001', 'artifact_path': str(lp.relative_to(ROOT)), 'sha256': sha(lp), 'not_applicable_reason': None}}
m['runs'][0].update(arm_ids=arms_run, status='complete', artifact_path=str((RUN/'result.json').relative_to(ROOT)), sha256=sha(RUN/'result.json'))
by_arm = {arm: {'correct': sum(bool(r['semantic_pass']) for r in judged if r['arm'] == arm), 'total': sum(r['arm'] == arm for r in judged), 'decision_eligible': False,
                'scope': 'turn-level direct review against the registered 434 original; one run per formulation'} for arm in arms_run}
for arm in by_arm: by_arm[arm]['accuracy'] = by_arm[arm]['correct']/by_arm[arm]['total'] if by_arm[arm]['total'] else None
m['results'].update(status='complete', by_arm=by_arm, comparisons=[], judge_disagreements=0,
    usage={k: result[k] for k in ('physical_calls', 'reported_cost_usd', 'reported_prompt_tokens', 'reported_completion_tokens', 'unknown')}, latency=result['latency_seconds'],
    error_taxonomy=[{'type': r['taxonomy'], 'case_id': r['case_id'], 'turn': r['turn']} for r in rows if r['taxonomy']])
for q in m['questions']:
    p = ADR/'실험'/q['file']; own = [r for r in rows if r['case_id'] == q['case_id']]
    p.write_text(p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\n'+json.dumps(own, ensure_ascii=False, indent=2)+'\n'); q['sha256'] = sha(p)
for c in m['design']['code_isolation'].get('candidates', []):
    runner = ROOT/c['runner_path']
    if c.get('runner_sha256') != sha(runner):
        c.setdefault('runner_revisions', []).append({'sha256': c['runner_sha256'], 'superseded_by': sha(runner), 'reason': 'pre-call runner guard fixes recorded in preparation-issues.json and freeze-live supersessions'})
        c['runner_sha256'] = sha(runner)
put(ADR/'실험/manifest.json', m)
summary = {'ADR-1421': 'MAIN161: 일반 질문 1턴에서 433·434 쌍과 같은 절 435조를 모델 호출 없이 함께 확보해 결의 수치와 종류주주총회 요건까지 답함. 읽지 않은 같은 절 436조는 출발 조문·이유와 함께 "읽을 필요가 없다고 판단했습니다. 필요하면 말씀해 주세요"로 안내되고, 2턴 요청으로 436조를 읽음.',
           'ADR-1416': 'MAIN157 기준: 두 질문 모두 433조만 읽고 결의 수치를 묻는 질문으로 끝남. "어 계속 찾아줘"는 CLARIFY(조사0). 433 질문 2턴은 공급자 UNKNOWN으로 중단되어 후보 arm은 동결 규칙에 따라 미실행.',
           'ADR-1417': 'MAIN158: 1턴 두 질문 모두 433조 READ 후 연결 조회 없이 ANSWER·수치 누락(개선 없음). 2턴은 운영자 병행 작업과 겹친 자원 가드 중단, 두 번째 셀은 중지 규칙 위반 실행(판정 제외).',
           'ADR-1420': 'MAIN160: 433 착지·434 착지 모두 FOLLOW 한 번에 쌍 조문을 모델 호출 없이 확보해 결의 수치 정확, 434를 빌려 쓰는 27건은 개수만. 일반 질문 1턴은 같은 절 435조를 읽지 않았고 "계속"에서 435조를 추가. 예외 조문 착지 셀은 자원 가드 중단.',
           'ADR-1419': 'MAIN160: 첫 셀 첫 모델 호출 직후 앱 적재 단계 스왑 증가(130MiB)로 자원 가드 중단. 판정 0건, 나머지 셀은 동결 규칙으로 미실행. 재실행은 ADR-1420.',
           'ADR-1418': 'MAIN159: 두 질문 모두 1턴에서 FOLLOW→연결 자동 읽기로 434조 확보·두 결의 수치 정확. 일반 질문 2턴 "어 계속 찾아줘"는 RESEARCH_CONTINUE로 같은 조사를 이어 435조 요건 추가. 433 질문 2턴은 공급자 UNKNOWN.'}[ADR_ID]
lines = [summary, '', f"MAIN{MAIN} {baseline['pointer']['release_id']} / 실제 root service / 로컬 SQLite 원문 / Qwen3.8 Parasail FP8 none / 출력 상한 없음. GENOS 현장 재현 아님.", '']
for r in rows:
    lines += [f"[{r['case_id']} / {r['arm']} / {r['turn']}턴] HTTP {r.get('http_status')} {r.get('status')} {r.get('method') or ''} 호출 {r.get('physical_calls')} {('%.1f초' % r['seconds']) if r.get('seconds') else ''}",
              '질문: '+str(r.get('question')), '답변: '+str(r.get('answer')), '판정: '+('통과' if r['semantic_pass'] else '판정불가' if r['semantic_pass'] is None else '미통과')+' — '+r['review'], '']
lines += [f"물리 {result['physical_calls']}회 / UNKNOWN {result['unknown']} / 결과불명 진행중 {result['started_without_outcome']} / 보고비용 ${result['reported_cost_usd']:.6f}",
          f"원문검사 {result['source_checks']} / 전달검사 {result['delivered_checks']} / 원문·ACL·wire 불일치0 / 출력상한0 / 예산일치 {result['budgets_match']} / 중복요청 추가호출 {result['duplicate_extra_model_calls']}",
          '각 질문 1회 실행. 반복 안정성·일반 법률 품질 인증 아님. 준비 이력은 preparation-issues.json.']
(ART/'실제_Qwen_결과.txt').write_text('\n'.join(lines)+'\n')
front = (ADR/'README.md').read_text().split('---', 2)[1]
crit = read(DES/'criteria.json')
headings = ['결정 요약', '문제와 변경 전 구조', '가설과 사전 판정 기준', '실험 설계', '데이터·모델·재현성', '결과', '사례별 오류 분석', '비용·지연·회수 규모', '해석', '한계와 일반화 가능 범위', '운영 결정·롤백 조건', '재현 명령']
values = [summary,
  '가이드 대화에서 답변이 "이어서 읽어볼까요?"로 끝나고, 사용자의 "어 계속 찾아줘"를 같은 조사의 재개로 해석할 명령이 없었다. 연결 조문(434→433①)은 존재하지만 가이드 모드는 종료 전 연결 조회를 요구하지 않았다.',
  json.dumps(crit, ensure_ascii=False),
  '정관 변경 결의요건 일반 질문과 433 명시 질문 각 1회, 각 2턴(질문→"어 계속 찾아줘"). 새 세션·격리 runtime. 기준답변은 제품 입력에 넣지 않음.',
  'actual root service, 선택 릴리스 코드만 로드(로드 모듈 바이트를 arm 인벤토리와 대조), Qwen3.8 Parasail FP8/none, 출력 상한 없음. 원시 요청·응답·canonical 입력은 artifacts/public-live.',
  json.dumps({k: v for k, v in result.items() if k != 'turns'}, ensure_ascii=False, indent=2),
  '\n'.join(f"{r['case_id']} {r['turn']}턴: {r['review']}" for r in rows),
  f"물리 {result['physical_calls']}회, 보고비용 ${result['reported_cost_usd']:.6f}. 회수 단계 원장은 retrieval-stage-ledger.json.gz, 조문 확보·전달은 source-wire-audit.json.",
  {'ADR-1421': '같은 절 핵심어 자동 읽기가 1턴 435조 확보로 이어졌고, 미확인 연결 안내 문장과 화면 카드가 실제 응답에서 동작. 질문 1개·1회이며 다른 절·법령에서의 핵심어 규칙 적합성은 미검증.', 'ADR-1420': '인용 역할 기반 자동 읽기로 착지 위치와 관계없이 같은 원칙·구체화 묶음이 모였다. 번호 인용이 없는 같은 절 조문(435)은 제목을 받고도 1턴에서 모델이 읽지 않았다.', 'ADR-1419': '측정 기준 위반으로 판정 불가. 측정 시작점을 앱 적재 뒤로 옮긴 ADR-1420에서 재실행.', 'ADR-1416': '기준 동작 재현. 후보 비교는 후속 ADR에서 수행.', 'ADR-1417': 'MAIN158의 계속 명령·자동 읽기는 1턴에 연결 조회가 없으면 발동하지 않음. 후속 MAIN159에서 가이드 답변 전 연결 첫 조회를 요구.', 'ADR-1418': '연결 첫 조회 요구와 작은 목록 자동 읽기가 434조 확보로 이어졌고, 계속 명령이 실제 Qwen에서 SELECT 재개로 동작. 433 질문의 2턴 결과는 공급자 UNKNOWN으로 미확인.'}[ADR_ID],
  '질문 2개·각 1회, 같은 상법 조문군. 다른 법령·내규·다단계 연결·반복 실행 안정성 미검증. memory-resolve 단계의 공급자 공백 UNKNOWN은 MAIN157부터 반복되며 이 수정의 범위 밖.',
  f"사용자 지시 반영(USER_DIRECTED_CUTOVER, quality_certified=false). 원복은 rag_main_promotion.py rollback --confirm-main. 현장 GENOS 배포는 별도.",
  f".venv/bin/python 06_TOOLS/EXPERIMENTS/adr_{ADR_ID[4:]}/live.py <case> <arm>; 감사·마감: .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1418/close_adr.py {NAME}. 결과: [실제 Qwen 결과](artifacts/실제_Qwen_결과.txt), [질문별 기록](실험/README.md)."]
title = front.split('title:', 1)[1].split('\n', 1)[0].strip() if 'title:' in front else NAME
(ADR/'README.md').write_text('---'+front+'---\n\n# '+title.strip('"\'')+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i, (h, v) in enumerate(zip(headings, values), 1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 Qwen 멀티턴 질문\n\n'+summary+'\n\n| 질문 | 턴 | 결과 |\n|---|---:|---|\n'+'\n'.join(f"| [{r['case_id']}]({next(q['file'] for q in m['questions'] if q['case_id']==r['case_id'])}) | {r['turn']} | {'통과' if r['semantic_pass'] else '판정불가' if r['semantic_pass'] is None else '미통과'} |" for r in rows)+'\n')
put(ART/'FINAL_VALIDATION.json', {'main': MAIN, 'source_store_unchanged': True, 'source_acl_wire_mismatches': 0, 'budgets_match': result['budgets_match'], 'judged_turns': result['judged_turns'], 'passed_turns': result['passed_turns'], 'quality_certified': False})
paths = {p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p != ART/'manifest.json'}
paths.update(Path(__file__).parent.glob('*.py')); paths.update((ROOT/'06_TOOLS/EXPERIMENTS'/('adr_'+ADR_ID[4:])).glob('*.py'))
put(ART/'manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': ADR_ID, 'files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p), 'bytes': p.stat().st_size, 'description': 'Actual Qwen multi-turn evidence; failures and stops retained', 'contains_raw_prompts_and_outputs': p.suffix == '.gz'} for p in sorted(paths)]})
print(summary); print('calls', result['physical_calls'], 'cost', round(result['reported_cost_usd'], 6), 'judged', result['judged_turns'], 'passed', result['passed_turns'], 'budgets', result['budgets_match'])
