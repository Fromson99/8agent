"""Oracle scale guard: question scenarios with the shipped field profile + every reachable SQL plan.

Real local Oracle 23.26.3 (a8-legal-mapped-20261023), field-serving gold mapping tables (IDD_B003_* + Agent LGL_*_A, GUARD_MAPPING=gold default) under
isolated temporary owners (dropped afterwards), published query release, ORDS envelope replaced by an
oracledb bridge that answers like ORDS (errorCode items, offset/limit pages), scripted model only.

The fixture is about 250x smaller than the field corpus and the field row budget (10,000) is scaled
to GUARD_BUDGET rows (default 40): the request scope has ~150 originals (field ~40,000), one document
(모의승인규정) has ~250 structural units (field max 29,428), the other documents stay under the budget.
A single read that streams more rows than the budget grows with the scope/document size and is a
field-scale stop. Nothing is asserted here; run.py judges the recorded evidence.
Fixture code from 09_ARTIFACTS/AUDITS/20261106-recall-source-budget/test_recall_scope_budget_oracle.py.
"""
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import time
import traceback

import pytest

import test_unified_legal_agent as cases
from test_oracle_dp_runtime import published  # noqa: F401  (fixture)
from test_document_release import source
from lawrag.core.legal_coordinate import find_coordinates
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.oracle_development_mapping import DevelopmentMapping, PORTS, LOGICAL
from semantic_runtime.physical_mapping import _freeze, digest as mapping_digest
from semantic_runtime.oracle_dp_io import canonical, digest, file_sha

import tripwire
import sweep as sweep_module

FILLER_DOCUMENTS = int(os.environ.get('FILLER_DOCUMENTS', '3'))
FILLER_ARTICLES = int(os.environ.get('FILLER_ARTICLES', '30'))
BIG_DOC_ARTICLES = int(os.environ.get('BIG_DOC_ARTICLES', '60'))  # 제100조.. (+3 항 each) in 모의승인규정
# 2026-11-12: articles citing other articles (same document and from the filler documents), so the
# reference/reference_end rows are many (field: FOLLOW and comparison reference reads). 0 = none (default).
REFERENCES = int(os.environ.get('GUARD_REFERENCES', '0'))
FIRST_ARTICLE = 100  # many '제1..' surfaces, like the field's 2-character title groups
# Field serving mapping: gold (dev and prod since 2026-11-10). development_g19_1 = old dev names, for comparison only.
GUARD_MAPPING = os.environ.get('GUARD_MAPPING', 'gold')
EVIDENCE = Path(os.environ['GUARD_EVIDENCE'])
CODE = Path(os.environ['LOOP_TEST_CODE_ROOT'])
PARTS = os.environ.get('GUARD_PARTS', 'scenarios,sweep').split(',')
VECTOR_PROFILE = {'model': 'mesh:synthetic', 'revision': 'immutable-test', 'dimensions': 3,
                  'metric': 'COSINE', 'normalization': 'l2', 'transport': 'dataiku-llm-mesh'}
VECTOR_ENV = {'GENOS_EMBED_PROFILE_SHA256': digest(VECTOR_PROFILE), 'GENOS_BASE_URL': 'https://genos.invalid',
              'GENOS_EMBED_SERVING_ID': '19', 'GENOS_EMBED_KEY': 'fixture-only',
              'GENOS_EMBED_MODEL': 'fixture-kure', 'GENOS_EMBED_TENANT_ID': 'fixture-tenant'}
RECORDS = tripwire.Records(CODE, int(os.environ.get('GUARD_BUDGET', '40')))
TREE = ['제1조 승인 규칙', '① 다음 각 호의 승인 기준을 적용한다.', '1. 승인 원칙은 다음 목과 같다.',
        '가. 긴급 승인 예외는 허용한다.', '2. 일반 승인 예외는 허용하지 않는다.', '② 승인 후 보고한다.']
NODES = [('0', None, 'kr_article', '제1조', 0, 6, '제1조'), ('1', '0', 'circled', '①', 1, 5, '제1조제1항'),
         ('2', '1', 'dot_number:1', '1.', 2, 4, '제1조제1항제1호'), ('3', '2', 'hangul_dot', '가.', 3, 4, '제1조제1항제1호가목'),
         ('4', '1', 'dot_number:1', '2.', 4, 5, '제1조제1항제2호'), ('5', '0', 'circled', '②', 5, 6, '제1조제2항')]


@pytest.fixture
def structured_generation(tmp_path, term_glossary, monkeypatch):
    unit_transport(monkeypatch)
    numbers = list(range(FIRST_ARTICLE, BIG_DOC_ARTICLES + FIRST_ARTICLE))
    cited = lambda at, k: numbers[(at * 7 + k * 13) % len(numbers)]
    filler = [('f%02d' % i, '부록규정%02d' % i, ['부록 %d 문구.' % j + ''.join(
                   ' 모의승인규정 제%d조에 따른다.' % cited(i * FILLER_ARTICLES + j, k) for k in range(REFERENCES))
                   for j in range(FILLER_ARTICLES)])
              for i in range(FILLER_DOCUMENTS)]
    texts, nodes = list(TREE), [(*n, '') for n in NODES]
    # Articles under chapters (장), like most field laws: a small one (same-section reading applies)
    # and a large one; numbers from FIRST_ARTICLE give many '제1..' title surfaces.
    numbers = list(range(FIRST_ARTICLE, BIG_DOC_ARTICLES + FIRST_ARTICLE))
    groups = [numbers[:8], numbers[8:28], numbers[28:48], numbers[48:]]
    for chapter, title, members in zip((2, 3, 4, 5), ('긴급 승인', '일반 승인', '보고', '부칙 승인'), groups):
        if not members:
            continue
        head = len(texts); texts.append(f'제{chapter}장 {title}')
        at = len(nodes); nodes.append(None)
        for i in members:
            k = len(texts)
            refs = ''.join(f' 제{cited(i, k)}조를 준용한다.' for k in range(REFERENCES))
            texts += [f'제{i}조({title} 기준) {title} 승인 문구', f'① 제{i}조 첫째 항.{refs}', f'② 제{i}조 둘째 항.', f'③ 제{i}조 셋째 항.']
            nodes.append((str(k), str(head), 'kr_article', f'제{i}조', k, k+4, f'제{i}조', f'{title} 기준'))
            nodes += [(str(k+j), str(k), 'circled', '①②③'[j-1], k+j, k+j+1, f'제{i}조제{j}항', '') for j in (1, 2, 3)]
        nodes[at] = (str(head), None, 'kr_장', f'제{chapter}장', head, len(texts), f'제{chapter}장', f'제{chapter}장 {title}')
    raw = source(tmp_path/'raw.sqlite', [('d', '모의승인규정', texts), ('other', '다른규정', ['별도 원문']), *filler])
    with sqlite3.connect(raw) as db:
        db.execute("DELETE FROM source_unit WHERE document_id='d'")
        for uid, parent, family, surface, lo, hi, locator, title in nodes:
            coordinate = find_coordinates(locator)[0].coordinate
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)', ('d', uid, parent, json.dumps({
                'family': family, 'surface': surface, 'title': title, 'span': [lo, hi],
                'legal_coordinate': coordinate.as_dict(), 'coordinate_scope': 'body',
                'coordinate_key': 'body:'+coordinate.canonical_surface()}, ensure_ascii=False)))
    started = time.monotonic()
    build_generation(raw, term_glossary, tmp_path/'built', serving=True, storage_profile='compact-v2', fulltext_granularity='unit')
    generation = tmp_path/'built/generation'
    with sqlite3.connect(generation/'navigation/navigation.sqlite') as db:
        counts = dict(db.execute('SELECT document_id,COUNT(*) FROM source GROUP BY document_id').fetchall())
    (EVIDENCE/'generation.json').write_text(json.dumps({'source_counts': counts, 'total': sum(counts.values()),
        'build_seconds': time.monotonic()-started}, indent=1))
    return generation


def unit_transport(monkeypatch):
    """Same scripted unit-triage transport as the recall-budget fixture."""
    base_transport = cases.ScriptedTransport

    class UnitTransport(base_transport):
        def send_once(self, *, body, ticket):
            view = json.loads(body['messages'][1]['content'])['view']
            phase = view.get('source_stage', view['phase'])
            if phase == 'memory-command-check':
                self.phases.append(phase)
                data = json.loads(body['messages'][1]['content'])
                data = data.get('data', data)
                after = (view.get('transition') or data.get('transition') or {}).get('after') or {}
                return cases.wire({'valid': True, 'reason': '모의 현재 명령 대조', 'request_relation': 'NEW_TOPIC',
                                   'requested_task': after.get('task')})
            if phase in ('source-unit-triage', 'source-unit-review'):
                self.phases.append(phase)
                choices = []
                if phase == 'source-unit-triage' and view['units']:
                    unit = view['units'][0]
                    choices = [{'id': unit['id'], 'scope': unit['read_options'][0][0], 'reason': '모의 원문 확인'}]
                return cases.wire({'issues': ['승인'], 'choices': choices, 'needs_search': False})
            if phase.startswith('source-reference-batch'):
                self.phases.append(phase)
                from test_batch_reference_navigation import decision
                return cases.wire(decision(view))
            return super().send_once(body=body, ticket=ticket)
    monkeypatch.setattr(cases, 'ScriptedTransport', UnitTransport)


@pytest.fixture
def oracle(tmp_path):
    import oracledb
    oracledb.defaults.fetch_lobs = False
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
    assert info['State']['Running'] and info['Config']['Labels']['a8.task'] == 'legal-mapped-20261023'
    ep = info['HostConfig']['PortBindings']['1521/tcp']
    assert len(ep) == 1 and ep[0]['HostIp'] == '127.0.0.1'
    dsn = '127.0.0.1:' + ep[0]['HostPort'] + '/FREEPDB1'
    pw = dict(x.split('=', 1) for x in info['Config']['Env'])['ORACLE_PASSWORD']
    admin = oracledb.connect(user='system', password=pw, dsn=dsn)
    admin.call_timeout = 60000
    names = {k: 'A8_GRD_' + k + '_' + secrets.token_hex(3).upper() for k in ('S', 'A')}
    password = secrets.token_hex(24)
    evidence = {'created': [], 'dropped': [], 'statements': 0}
    conn = None
    try:
        with admin.cursor() as cur:
            for name in names.values():
                cur.execute('CREATE USER ' + name + ' IDENTIFIED BY "' + password + '" DEFAULT TABLESPACE USERS QUOTA 512M ON USERS')
                evidence['created'].append(name)
                cur.execute('GRANT CREATE SESSION,CREATE TABLE TO ' + name)
        data = json.loads((CODE/'00_SYSTEM/ORACLE/development_g19_1.json').read_text())
        if GUARD_MAPPING == 'gold':
            # 2026-11-10부터 개발계도 운영과 같은 IDD_B003_* 이름 + gold 모드(GENOS_ORACLE_GOLD_OWNER=SIDDS)로 서빙한다.
            # Gold 13표는 gold_b003_r5.json 그대로, Agent 4표는 gold 모드처럼 LGL_*_A. 소유자만 임시 계정.
            from semantic_runtime.oracle_gold_mapping import GoldMapping
            from semantic_runtime.oracle_development_mapping import AGENTS
            gold = json.loads((CODE/'00_SYSTEM/ORACLE/gold_b003_r5.json').read_text())['tables']
            tables = {key: {**table, 'owner': names['S']} for key, table in gold.items()}
            for key in AGENTS.values():
                tables[key] = {**data['tables'][key], 'owner': names['A'], 'name': 'LGL_' + key + '_A'}
            data['tables'] = tables
            GoldMapping.load(owner=names['S'])
            mapping = GoldMapping(_freeze(tables), 'isolated-owner-copy', mapping_digest(tables), profile='gold')
        else:
            for table in data['tables'].values():
                table['owner'] = names['A' if table['owner'] == 'SIDDA' else 'S']
            DevelopmentMapping.load(CODE/'00_SYSTEM/ORACLE/development_g19_1.json')
            mapping = DevelopmentMapping(_freeze(data['tables']), 'isolated-owner-copy', mapping_digest(data['tables']))
        evidence['mapping'] = mapping.profile
        with admin.cursor() as cur:
            for i, (key, table) in enumerate(data['tables'].items()):
                fields = [c['name']+' '+c['type']+(' DEFAULT '+c['default'] if c['default'] else '')+
                          (' NOT NULL' if c['required'] else '') for c in table['columns'].values()]
                fields.append('CONSTRAINT P'+str(i)+' PRIMARY KEY ('+','.join(table['columns'][c]['name'] for c in table['primary_key'])+')')
                cur.execute('CREATE TABLE '+mapping.physical_table(key)+' ('+','.join(fields)+')')
                if table['owner'] != names['S']:
                    cur.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON '+mapping.physical_table(key)+' TO '+names['S'])
        conn = oracledb.connect(user=names['S'], password=password, dsn=dsn)
        conn.call_timeout = 120000

        class Bridge:
            """ORDS-like: one statement, offset 0, limit rows, errorCode items instead of exceptions."""
            SQL_PATH = '/isolated-oracle-contract'
            schema_map = mapping

            def request(self, method, path, json):
                assert method == 'POST' and path == self.SQL_PATH
                evidence['statements'] += 1
                started, rows, error = time.monotonic(), None, None
                types = {'CLOB': oracledb.DB_TYPE_CLOB, 'VARCHAR2': oracledb.DB_TYPE_VARCHAR, 'NUMBER': oracledb.DB_TYPE_NUMBER}
                try:
                    with conn.cursor() as cur:
                        cur.setinputsizes(**{b['name']: types[b['data_type']] for b in json.get('binds', [])})
                        # A CLOB-typed value is bound as a string, as a JDBC setString would: over 32,767 bytes
                        # the database refuses it (ORA-01460). The serving code sends long CLOBs in pieces
                        # (oracle_dp_io.clob_pieces); GUARD_CLOB_AS_LOB=1 binds real LOBs instead.
                        values = {b['name']: (conn.createlob(oracledb.DB_TYPE_CLOB, b['value'])
                                              if os.environ.get('GUARD_CLOB_AS_LOB') == '1' and b['data_type'] == 'CLOB'
                                              and isinstance(b['value'], str) and len(b['value'].encode()) > 32000
                                              else b['value']) for b in json.get('binds', [])}
                        cur.execute(json['statementText'], values)
                        if cur.description is None:
                            return {'items': [{'result': cur.rowcount}]}
                        columns = [c[0] for c in cur.description]
                        fetched = cur.fetchmany(json['limit']+1)
                        rows = len(fetched)
                        return {'items': [{'resultSet': {'offset': 0, 'hasMore': len(fetched) > json['limit'],
                            'items': [dict(zip(columns, row)) for row in fetched[:json['limit']]]}}]}
                except oracledb.DatabaseError as exc:
                    err, = exc.args
                    error = str(err.message)[:400]
                    return {'items': [{'errorCode': err.code, 'errorMessage': 'hidden'}]}
                finally:
                    tripwire.bridge_record(RECORDS, json, started, rows, error)

        pending = {}

        def insert(key, values):
            pending.setdefault(key, []).append(dict(values))
            if len(pending[key]) >= 500:
                flush(key)

        def flush(key=None):
            for k in ([key] if key else list(pending)):
                rows = pending.pop(k, [])
                if not rows:
                    continue
                table = data['tables'][k]
                columns = list(rows[0])
                assert all(list(r) == columns for r in rows)
                with conn.cursor() as cur:
                    cur.setinputsizes(*[oracledb.DB_TYPE_CLOB if table['columns'][c]['type'] == 'CLOB' else None for c in columns])
                    slots = [('TO_VECTOR(:'+str(i+1)+')') if k == 'VCTR_ITEM' and c == 'EMBD_VCTR_VALU' else ':'+str(i+1)
                             for i, c in enumerate(columns)]
                    cur.executemany('INSERT INTO '+mapping.physical_table(k)+' ('+','.join(table['columns'][c]['name'] for c in columns)+
                                    ') VALUES ('+','.join(slots)+')', [[r[c] for c in columns] for r in rows])
        insert.flush = flush
        evidence['oracle_version'] = conn.version
        yield Bridge(), insert, conn, evidence
    finally:
        if conn:
            conn.close()
        with admin.cursor() as cur:
            for owner in evidence['created']:
                cur.execute('DROP USER '+owner+' CASCADE')
                evidence['dropped'].append(owner)
        admin.close()
        (EVIDENCE/'oracle.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=1))


def publish(client, insert, conn, published, tmp_path):
    remote, original, generation = published
    from lawrag.pipeline import oracle_query_publish as pub, oracle_query_navigation_publish
    from semantic_runtime import navigation_match, structure_navigation, inherited_navigation
    from semantic_runtime.oracle_dp_assets import inventory
    src = json.loads(remote.releases[original['release_id']]['body'])
    for kind, rows in remote.data.items():
        key, aliases = PORTS[kind]
        for row in rows.values():
            insert(key, {old: ('Y' if row[a] == 1 else 'N' if row[a] == 0 else None) if a == 'JSON_TEXT_ELIDED' else row[a]
                         for a, old in zip(aliases.split(), LOGICAL[key].split())})
    insert('SRC_POST', {'DOC_POST_HASH_VALU': original['release_id'], 'MNFST_HASH_VALU': src['dataset_version'],
                        'DOC_POST_IFMN_CTNT': canonical(src)})
    manifest, assets, tables = pub.describe(generation, src)
    _, inventory_assets = inventory(generation)
    value = {'schema_version': pub.SCHEMA, 'status': 'COMPLETE', 'source_release_id': original['release_id'],
             'dataset_version': src['dataset_version'], 'source_manifest': manifest,
             'search_selection': src.get('search_selection'), 'assets': assets, 'tables': tables,
             'projection': 'sqlite-logical-rows-and-fts5-positions-v1', 'metadata': pub.asset_metadata(generation, inventory_assets),
             'selection_proof': pub.selection_proof(generation, manifest), 'publisher_sha256': file_sha(pub.__file__),
             'navigation_compilers': {m.__name__: file_sha(m.__file__) for m in (oracle_query_navigation_publish, navigation_match,
                                                                                 structure_navigation, inherited_navigation)}}
    qid = digest(value)
    rows = 0
    vector_sources = []
    for relative in assets:
        for r in pub.projected_rows(generation / relative, relative, src):
            insert('SRCH_ROW', dict(zip(LOGICAL['SRCH_ROW'].split(), [qid, r['kind'], r['row_id'], r['document_id'], r['lookup_id'],
                                                                     r['owner_id'], r['target_id'], r['sha256'], canonical(r['value'])])))
            rows += 1
            if r['kind'] == 'native.source':
                vector_sources.append(r)
    insert('SRCH_POST', {'RFRN_POST_HASH_VALU': qid, 'RFRN_POST_IFMN_CTNT': canonical(value)})
    # Published initial-vector rows (as 20261106-vector-candidate-card): one 3-d item per original.
    vector_manifest = {'schema_version': 'gold-vector-manifest-preview-v1', 'query_id': qid,
        'source_release_id': original['release_id'], 'dataset_version': src['dataset_version'],
        'documents': manifest['scope']['document_version_ids'], 'profile': VECTOR_PROFILE}
    vid = digest(vector_manifest)
    for i, r in enumerate(vector_sources):
        insert('VCTR_ITEM', {'VCTR_POST_ID': vid, 'VCTR_SEG_ID': digest(i), 'DOC_ID': r['document_id'],
            'SRC_UNIT_ID': r['lookup_id'], 'VCTR_META_CTNT': '{}', 'EMBD_VCTR_VALU': canonical([1., 0., 0.])})
    insert('VCTR_POST', {'VCTR_POST_ID': vid, 'VCTR_POST_IFMN_CTNT': canonical({'manifest': vector_manifest,
        'completion': {'status': 'READY', 'count': len(vector_sources), 'profile_sha256': digest(VECTOR_PROFILE)}})})
    insert('VCTR_HEAD', {'RFRN_POST_HASH_VALU': qid, 'VCTR_POST_ID': vid, 'CHAN_NO': 1})
    insert('SRCH_CHNL', {'RFRN_CHNL_NAME': 'g19_fixture', 'RFRN_POST_HASH_VALU': qid, 'CHAN_NO': 1})
    insert.flush()
    conn.commit()
    (EVIDENCE/'release.json').write_text(json.dumps(value, ensure_ascii=False))
    generation.rename(tmp_path / 'offline-generation')  # serving must not read local source files
    return qid, rows, manifest['scope']['document_version_ids']


def scale_thresholds(monkeypatch, factor):
    """Scale the product's own chunk/group thresholds like the row budget, when the code has them."""
    import importlib
    scaled = {}
    for module, owner, name, field in [('semantic_runtime.oracle_query_matcher', 'RemoteSurface', 'GROUP_ROWS', 1000),
                                       ('semantic_runtime.oracle_query_matcher', 'Units', 'ROOT_MAX_UNITS', 4096),
                                       ('semantic_runtime.legal_agent.law_candidates', None, 'SCOPE_KEY_UNITS', 1000),
                                       ('semantic_runtime.legal_agent.law_candidates', None, 'WHOLE_DOCUMENT_UNITS', 4096),
                                       ('semantic_runtime.legal_agent.unit_reading', None, 'BLOCK_WINDOW', 5000)]:
        target = importlib.import_module(module)
        target = getattr(target, owner) if owner else target
        if hasattr(target, name):
            value = max(2, int(field * factor))
            monkeypatch.setattr(target, name, value)
            scaled[(owner + '.' if owner else '') + name] = value
    return scaled


def failures_of(runtime):
    from semantic_runtime.legal_agent import journal_storage
    found = []
    for path in Path(runtime).rglob('journal.sqlite'):
        db = journal_storage.connect(path)
        try:
            for kind, payload in db.execute('SELECT kind,payload_json FROM event ORDER BY seq'):
                if kind == 'RUN_FAILED':
                    d = json.loads(payload).get('diagnostics') or {}
                    found.append({'stage': d.get('stage'), 'error_message': d.get('error_message'), 'location': d.get('location'),
                                  'frames': [l.strip() for l in (d.get('traceback') or '').splitlines() if l.strip().startswith('File ')][-8:]})
        finally:
            db.close()
    return found


def open_store(client, documents):
    from semantic_runtime.oracle_query_request import open_request
    from semantic_runtime.oracle_query_store import Store as OracleStore
    request = open_request(client, connection_binding='scale-guard', document_ids=documents,
                           deadline=time.monotonic()+1800, channel='g19_fixture', max_calls=10000)
    if os.environ.get('GUARD_SHARED_CACHE', 'on') == 'on':
        # Same as the serving Factory: one process-wide published-row cache, pinned to this release.
        global SHARED_ROWS
        from semantic_runtime import oracle_shared_cache
        if SHARED_ROWS is None and hasattr(oracle_shared_cache, 'SharedRows'):
            SHARED_ROWS = oracle_shared_cache.SharedRows(client, 'scale-guard')
        if SHARED_ROWS is not None:
            request.sql.shared_cache = SHARED_ROWS
            request.sql.pin_shared_cache(request.release_id)
    return request, OracleStore(request)


SHARED_ROWS = None


def scenario_test_profile(client, documents, tmp_path, question):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    from test_bounded_source_main import settings
    _, store = open_store(client, documents)
    transport = cases.ScriptedTransport()
    runtime = tmp_path/('rt-'+RECORDS.scenario)
    app = create_app(runtime, None, contracts_root=CODE, data_store=store, implementation='legal-agent-unified-v6', vector=False,
                     runtime_root=runtime, legal_agent_profile={**settings(), 'max_model_attempts': 40}, legal_agent_transport=transport,
                     memory_identity=lambda req: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': sorted(documents)})
    app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['capture'] = False
    RECORDS.turn = 1
    response = TestClient(app, raise_server_exceptions=False).post('/v1/rag/ask', json={
        'question': question, 'session_id': 's', 'request_id': RECORDS.scenario})
    return [{'status_code': response.status_code, 'status': (response.json() if response.headers.get('content-type', '').startswith('application/json') else {}).get('status'),
             'body': response.text[:1500]}], failures_of(runtime), transport.phases


def scenario_guided(client, documents, tmp_path, *, question, scope, plan, turns, follow_ups=None, profile_update=None):
    """test_guided_continue_bounds.Transport over the Oracle store with the shipped field profile."""
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    import guard_transport as guided
    _, store = open_store(client, documents)
    transport = guided.Transport(question, scope, plan)
    if plan.get('queries'):
        words, original = list(plan['queries']), transport.send_once

        def send_once(*, body, ticket):
            from api_fixture_integrated import decode
            view = decode(json.loads(body['messages'][1]['content'])['view'])
            if (view.get('source_stage') or view['phase']) != 'request-entry':
                return original(body=body, ticket=ticket)
            decoded = json.loads(original(body=body, ticket=ticket)['body_json']['choices'][0]['message']['content'])
            decoded['command']['queries'] = words
            return cases.wire(decoded)
        transport.send_once = send_once
    if plan.get('report'):
        # The forced progress-report call of a stopped answer (F1): a fixed report.
        before_report = transport.send_once

        def send_once(*, body, ticket):
            from api_fixture_integrated import decode
            view = decode(json.loads(body['messages'][1]['content'])['view'])
            if (view.get('source_stage') or view['phase']) == 'memory-progress-report':
                return cases.wire({'found': '모의승인규정 제1조를 읽었습니다.', 'unclear': '판단 대조에서 멈췄습니다.',
                                   'done': [], 'missing': [], 'decisions': ['다시 확인할까요?']})
            return before_report(body=body, ticket=ticket)
        transport.send_once = send_once
    runtime = tmp_path/('rt-'+RECORDS.scenario)
    profile = json.loads((CODE/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    for key, value in (profile_update or {}).items():
        profile['candidate_navigation'][key] = value
    app = create_app(runtime, None, contracts_root=CODE, data_store=store, provider=object(), implementation='legal-agent-unified-v6',
                     vector=False, legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
                     memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': sorted(documents)})
    responses = []
    from semantic_runtime.legal_agent.journal_storage import connect
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    with TestClient(app, raise_server_exceptions=False) as api:
        request = {'session_id': 's', 'request_id': RECORDS.scenario+'-1', 'question': question}
        RECORDS.turn = 1
        r = api.post('/v1/rag/ask', json=request)
        responses.append(r)
        if r.status_code == 200:
            try:
                db = connect(selected_store(runtime))
                row = dict(db.execute('SELECT id,state FROM goal ORDER BY ordinal DESC LIMIT 1').fetchone())
                db.close()
                transport.target = row['id']; transport.task = json.loads(row['state'])['task']
            except Exception:
                pass
        for n, text in enumerate(follow_ups or [guided.CONTINUE] * (turns-1), 2):
            transport.turn = n; RECORDS.turn = n
            responses.append(api.post('/v1/rag/ask', json={**request, 'request_id': RECORDS.scenario+'-'+str(n), 'question': text}))
    out = []
    for r in responses:
        try:
            body = r.json()
        except ValueError:
            body = {}
        out.append({'status_code': r.status_code, 'status': body.get('status'), 'executed': body.get('executed'),
                    'method_id': body.get('method_id'), 'body': r.text[:1500]})
    return out, failures_of(runtime), [(x['turn'], x['phase']) for x in transport.log]


def scenario_failure(client, documents, tmp_path, monkeypatch):
    """F1 (2026-11-12): a check failure at ASSESS answers with a progress report and its failure points,
    then "1번 다시 확인해 줘" re-enters the same question. Counts the SQL of a stopped answer and its follow-up."""
    import guard_transport as guided
    from semantic_runtime.legal_agent import guided_answer
    from semantic_runtime.legal_agent.errors import ContractError
    real, calls = guided_answer.assess, []

    def assess(executor, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ContractError('guard: injected composition check failure')
        return real(executor, *args, **kwargs)
    monkeypatch.setattr(guided_answer, 'assess', assess)
    try:
        return scenario_guided(client, documents, tmp_path, question=guided.NAMED, scope='named', turns=2,
            plan={'resolve': ('RESEARCH_REENTER', 'ASSESS'), 'relation': 'REVIEW', 'report': True},
            follow_ups=['1번 다시 확인해 줘'])
    finally:
        monkeypatch.setattr(guided_answer, 'assess', real)


def test_guard(oracle, published, tmp_path, monkeypatch):
    global SHARED_ROWS
    SHARED_ROWS = None  # one process cache per Oracle fixture (owners differ per test)
    client, insert, conn, evidence = oracle
    started = time.monotonic()
    qid, rows, documents = publish(client, insert, conn, published, tmp_path)
    evidence.update(published_rows=rows, publish_seconds=time.monotonic()-started, documents=sorted(documents))
    tripwire.install(monkeypatch, RECORDS)
    scaled = scale_thresholds(monkeypatch, RECORDS.budget / 10000)
    for key, val in VECTOR_ENV.items():
        monkeypatch.setenv(key, val)
    import requests
    from types import SimpleNamespace
    embedding_calls = []

    def post(session, url, **kw):
        embedding_calls.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {'data': [{'index': i, 'embedding': [1., 0., 0.]}
                                                                       for i, _ in enumerate(kw.get('json', {}).get('input') or [0])]})
    monkeypatch.setattr(requests.Session, 'post', post)
    summary = {'scenarios': {}, 'sweep': None, 'scaled_thresholds': scaled}
    if 'sweep' in PARTS:
        RECORDS.scenario = 'sweep'
        request, _ = open_store(client, documents)
        inventory = json.loads(Path(os.environ['GUARD_INVENTORY']).read_text())
        gold = json.loads(Path(os.environ['GUARD_SHAPES']).read_text())
        runner = sweep_module.Sweep(request, RECORDS, CODE, gold_release=gold)
        t = time.monotonic()
        try:
            runner.run(inventory, profiles=tuple(os.environ.get('GUARD_PROFILES', 'fixture,fullgen').split(',')))
        except Exception:
            summary['sweep_crash'] = traceback.format_exc()[-3000:]
        (EVIDENCE/'sweep.json').write_text(json.dumps(runner.results, ensure_ascii=False) + '\n')
        summary['sweep'] = {'executions': len(runner.results), 'errors': sum(1 for r in runner.results if r['error']),
                            'seconds': time.monotonic()-t}
    if 'scenarios' in PARTS:
        import guard_transport as guided
        cont = {'resolve': ('RESEARCH_CONTINUE', 'SELECT'), 'relation': 'CONTINUE'}
        plans = [
            ('S1-test-profile', lambda: scenario_test_profile(client, documents, tmp_path, '모의승인규정 제1조의 승인 대상은?')),
            ('S2-guided-broad-continue', lambda: scenario_guided(client, documents, tmp_path, question=guided.BROAD, scope='authorized',
                plan=dict(cont), turns=3)),
            ('S3-guided-named-continue', lambda: scenario_guided(client, documents, tmp_path, question=guided.NAMED, scope='named',
                plan={**cont, 'reads': 2}, turns=2)),
            ('S4-guided-ask-then-reenter', lambda: scenario_guided(client, documents, tmp_path, question=guided.NAMED, scope='named',
                plan={'resolve': ('RESEARCH_REENTER', 'SELECT'), 'relation': 'REPEAT', 'ask': True, 'reads': 0}, turns=3)),
            ('S5-guided-assess-reentry', lambda: scenario_guided(client, documents, tmp_path, question=guided.NAMED, scope='named',
                plan={'resolve': ('RESEARCH_REENTER', 'ASSESS'), 'relation': 'REPEAT'}, turns=2)),
            ('S6-guided-action-limit', lambda: scenario_guided(client, documents, tmp_path, question=guided.BROAD, scope='authorized',
                plan={**cont, 'reads': 5}, turns=2, profile_update={'guided_action_limit': 1})),
            ('S7-guided-word-with-je-prefix', lambda: scenario_guided(client, documents, tmp_path, question='제3자 승인 예외 기준을 알려줘',
                scope='authorized', plan=dict(cont), turns=1)),
            ('S8-guided-number-without-document', lambda: scenario_guided(client, documents, tmp_path, question='제101조 승인 기준은?',
                scope='authorized', plan=dict(cont), turns=1)),
            ('S10-guided-search-word-article-number', lambda: scenario_guided(client, documents, tmp_path, question='제101조와 제1조 승인 기준은?',
                scope='authorized', plan={**cont, 'queries': ['제101조', '제1조']}, turns=1)),
            ('V1-vector-guided-broad', lambda: scenario_guided(client, documents, tmp_path, question=guided.BROAD, scope='authorized',
                plan=dict(cont), turns=2)),
            ('V2-vector-guided-named', lambda: scenario_guided(client, documents, tmp_path, question=guided.NAMED, scope='named',
                plan={**cont, 'reads': 2}, turns=2)),
            ('V3-vector-test-profile', lambda: scenario_test_profile(client, documents, tmp_path, '모의승인규정 제1조의 승인 대상은?')),
            # A document-named article left in the search words, keyword (S11) and vector initial search (V4):
            # both read the named article first (20261107 vector structure entry). A bare number (S10) names no document.
            ('S11-guided-search-word-named-article', lambda: scenario_guided(client, documents, tmp_path, question='모의승인규정 제101조 승인 기준은?',
                scope='authorized', plan={**cont, 'queries': ['모의승인규정 제101조']}, turns=1)),
            ('V4-vector-search-word-named-article', lambda: scenario_guided(client, documents, tmp_path, question='모의승인규정 제101조 승인 기준은?',
                scope='authorized', plan={**cont, 'queries': ['모의승인규정 제101조']}, turns=1)),
            # Multi-word search groups, one found together ('긴급 승인 예외') and one whose words sit in
            # different units ('보고 원칙'): the group check SQL runs (field 2026-11-11 MAIN210: it began
            # with WITH and the read-only gate refused it, READ_ONLY; every single-word scenario missed it).
            ('S12-guided-multiword-groups', lambda: scenario_guided(client, documents, tmp_path, question=guided.BROAD,
                scope='authorized', plan={**cont, 'queries': ['긴급 승인 예외', '보고 원칙']}, turns=1)),
            ('V5-vector-multiword-groups', lambda: scenario_guided(client, documents, tmp_path, question=guided.BROAD,
                scope='authorized', plan={**cont, 'queries': ['긴급 승인 예외', '보고 원칙']}, turns=1)),
            ('S9-guided-many-reads',lambda: scenario_guided(client, documents, tmp_path, question=guided.BROAD, scope='authorized',
                plan={**cont, 'reads': 6}, turns=2)),
            # Opt-in only (GUARD_SCENARIOS=...,F1): code before MAIN219 answers this stop with 500.
            ('F1-guided-check-failure-then-point', lambda: scenario_failure(client, documents, tmp_path, monkeypatch)),
        ]
        selected = os.environ.get('GUARD_SCENARIOS')
        for name, run in plans:
            if selected and name.split('-')[0] not in selected.split(','):
                continue
            if name.startswith('F') and not (selected and name.split('-')[0] in selected.split(',')):
                continue
            RECORDS.scenario = name
            monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', os.environ.get('ORACLE_GUARD_VECTOR_MODE', 'vector') if name.startswith('V') else 'keyword')
            t = time.monotonic(); sql_before = len(RECORDS.sql)
            try:
                responses, failures, phases = run()
                crash = None
            except Exception:
                responses, failures, phases, crash = [], [], [], traceback.format_exc()[-3000:]
            sent = RECORDS.sql[sql_before:]
            summary['scenarios'][name] = {'embedding_calls': len(embedding_calls), 'seconds': time.monotonic()-t, 'responses': responses, 'run_failures': failures,
                'phases': phases[-60:], 'crash': crash, 'sql_count': len(sent), 'sql_errors': [s for s in sent if s['error']],
                'max_rows_one_sql': max([s['rows'] or 0 for s in sent] or [0])}
            (EVIDENCE/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    RECORDS.scenario = None
    RECORDS.dump(EVIDENCE/'records.json')
    (EVIDENCE/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
