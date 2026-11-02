"""Publish three user-delegated, source-bound local Gold ontology bundles.

No generated answer or external model. Existing Workflow owns review, publication,
hash/ACL/CAS and transaction contracts. The only new tables are Agent work/events.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import subprocess
import sys
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261030-gold-ontology-publication'
WORK = ROOT / '01_DATA/ONTOLOGY_WORK/gold-local-20261030'
AGENT = 'A8_GONT_AGENT'
DID = '7bbe815ff43b6635'
ACTOR = 'codex:user-delegated-local-publication'
AUTHORIZATION = '게시 몇개 알아서 너가 해봐라'
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import connect


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def read(name):
    return json.loads((OUT / name).read_text())


def admin_connection():
    import oracledb
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
    assert info['Config']['Labels']['a8.task'] == 'legal-mapped-20261023' and info['State']['Running']
    endpoint = info['HostConfig']['PortBindings']['1521/tcp']
    assert len(endpoint) == 1 and endpoint[0]['HostIp'] == '127.0.0.1'
    password = dict(s.split('=', 1) for s in info['Config']['Env'])['ORACLE_PASSWORD']
    db = oracledb.connect(user='system', password=password,
                         dsn='127.0.0.1:' + endpoint[0]['HostPort'] + '/FREEPDB1')
    db.call_timeout = 15000
    return db


def writer_connection():
    import oracledb
    p = Path.home() / '.local/state/8-agent/gold-r12-1208/connection.json'
    assert not p.stat().st_mode & 0o077
    cfg = json.loads(p.read_text())
    assert cfg['user'].upper() == 'A8_GR12_CM1208'
    db = oracledb.connect(**cfg)
    db.call_timeout = 15000
    return db


def snapshot(cfg):
    with writer_connection() as db, db.cursor() as c:
        rows = {}
        for key in cfg.tables:
            c.execute('SELECT COUNT(*) FROM ' + cfg.physical_table(key))
            rows[key] = c.fetchone()[0]
        c.execute('SELECT OBJECT_NAME,OBJECT_ID,DATA_OBJECT_ID,STATUS FROM USER_OBJECTS ORDER BY OBJECT_NAME')
        return {'counts': rows, 'objects': [list(r) for r in c.fetchall()]}


SPECS = [
    (365, '총회의 소집', ['1388', '1389', '1390', '1391'], [
        ('ANNUAL', '정기총회 소집', '정기총회', '정기총회', '정기총회의 연간 소집 시기를 확인할 때'),
        ('EACH_PERIOD', '연 2회 이상 결산 회사의 총회', '연 2회 이상의 결산기를 정한 회사', '연 2회 이상의 결산기를 정한 회사', '복수 결산기의 총회 소집 기준을 확인할 때'),
        ('EXTRAORDINARY', '임시총회 소집', '임시총회가 필요한 경우', '임시총회는 필요있는 경우', '임시총회를 소집할 수 있는 시점을 확인할 때'),
    ]),
    (368, '총회의 결의방법과 의결권의 행사', ['1403', '1404', '1405', '1406'], [
        ('ORDINARY', '별도 정함이 없는 총회의 결의', '이 법 또는 정관에 다른 정함이 없는 총회의 결의', '이 법 또는 정관에 다른 정함이 있는 경우를 제외하고는', '다른 법정·정관상 정함의 존재를 따로 확인하면서 본항의 결의 기준을 볼 때'),
        ('PROXY', '대리인을 통한 의결권 행사', '주주가 대리인으로 하여금 의결권을 행사하게 하는 경우', '주주는 대리인으로 하여금 그 의결권을 행사하게 할 수 있다.', '대리 행사와 대리권 증명 서면 제출을 함께 확인할 때'),
        ('INTERESTED', '특별한 이해관계자의 의결권 제한', '총회의 결의에 관하여 특별한 이해관계가 있는 자', '총회의 결의에 관하여 특별한 이해관계가 있는 자', '결의에 관한 특별한 이해관계에 따른 의결권 제한을 확인할 때'),
    ]),
    (369, '의결권', ['1420', '1421', '1422', '1423'], [
        ('PER_SHARE', '1주당 의결권 수', '주식의 의결권 수를 산정할 때', '의결권은 1주마다 1개로 한다.', '1주당 의결권 수를 확인할 때; 자기주식·상호보유 및 다른 제한은 별도로 확인'),
        ('OWN_SHARES', '자기주식의 의결권 제한', '회사가 가진 자기주식', '회사가 가진 자기주식', '자기주식인지 확인하고 그 의결권 유무를 볼 때'),
        ('CROSS_HOLDING', '주식 상호보유에 따른 의결권 제한', '회사, 모회사 및 자회사 또는 자회사가 다른 회사의 발행주식의 총수의 10분의 1을 초과하는 주식을 가지고 있는 경우', '회사, 모회사 및 자회사 또는 자회사가 다른 회사의 발행주식의 총수의 10분의 1을 초과하는 주식을 가지고 있는 경우', '본항의 보유 주체·10분의 1 초과 기준·의결권 제한 대상 주식을 함께 확인할 때'),
    ]),
]


def prepare():
    entries = []
    with connect.open_store(seconds=180, max_calls=500) as (store, request, transport):
        from semantic_runtime.ontology_work import schema
        from semantic_runtime.legal_agent import ontology_scenarios as sc
        from semantic_runtime.legal_agent.ontology_compiler import content_hash
        document = request.sources.document(DID)
        for article, title, units, paths in SPECS:
            originals = []
            for n, uid in enumerate(units):
                a = {'document_id': DID, 'version': document['source_artifact_sha256'], 'unit_id': uid}
                text = store.gold_ports.source_reader(a)
                a.update(label='상법 제' + str(article) + '조' + (' 제' + str(n) + '항' if n else ''),
                         content_sha256=content_hash(text))
                originals.append({'id': 'S' + str(n), 'anchor': a, 'text': text})
            components = [{'id': 'SCOPE', 'text': originals[0]['text'] + '의 등록 원문 범위. 다른 조문·정관의 별도 정함 및 개별 사건 사실은 이 게시물에서 확정하지 않는다.',
                           'requires': [], 'basis': [{'source': 'S0', 'quote': originals[0]['text']}]}]
            compiled_paths = []
            for n, (pid, label, condition, quote, use) in enumerate(paths, 1):
                source = originals[n]
                assert quote in source['text']
                cid, rid = 'C' + str(n), 'R' + str(n)
                components.extend([
                    {'id': cid, 'text': condition, 'requires': [], 'basis': [{'source': source['id'], 'quote': quote}]},
                    {'id': rid, 'text': source['text'], 'requires': [cid], 'basis': [{'source': source['id'], 'quote': source['text']}]},
                ])
                compiled_paths.append({'id': pid, 'title': label, 'business_use': use,
                                       'conditions': [cid], 'calculations': [], 'outcomes': [rid], 'notes': ['SCOPE']})
            work = {'version': schema.VERSION, 'concept': '상법 제' + str(article) + '조 ' + title,
                    'originals': originals, 'judgments': [], 'origin': {
                        'run_id': 'gold-local-publication-20261030', 'author': ACTOR,
                        'authorization': AUTHORIZATION, 'source': 'current Oracle Gold originals',
                        'scope': 'source-bound navigation aid; no legal quality certification'}}
            proposal = {'components': components, 'paths': compiled_paths, 'unused_components': {}}
            bid = 'cb-gold20261030-commercial-' + str(article)
            package = sc.compile_package(schema.recipe_for(work, proposal, bid), originals)
            entries.append({'bundle_id': bid, 'work': work, 'proposal': proposal,
                            'preview_package_sha256': package['package_sha256']})
        value = {'authorization': AUTHORIZATION, 'actor': ACTOR, 'agent_owner': AGENT,
                 'query_release_id': request.release_id, 'mapping_sha256': store.gold_ports.mapping.file_sha256,
                 'source_sql_calls': request.sql.calls, 'external_model_calls': 0, 'entries': entries}
        assert not (OUT / 'prepared.json').exists(), 'Do not overwrite prepared source-bound input'
        write('prepared.json', value)
        write('before.json', snapshot(store.gold_ports.mapping))
        write('authorization.json', {'user_instruction': AUTHORIZATION, 'delegated_reviewer': ACTOR,
              'human_item_by_item_review': False, 'scope': 'three local source-bound sample publications',
              'external_model_calls': 0, 'prepared_sha256': connect.sha(OUT / 'prepared.json')})
        print(json.dumps({'prepared': len(entries), 'originals': 12, 'paths': 9, 'source_sql': request.sql.calls}))


def ensure_agent():
    from semantic_runtime.ontology_work.repository import ddl
    statements = ddl(AGENT, 'oracle')[:2]
    with admin_connection() as db, db.cursor() as c:
        c.execute('SELECT USERNAME FROM DBA_USERS WHERE USERNAME=:1', [AGENT])
        if c.fetchone() is None:
            c.execute('CREATE USER ' + AGENT + ' NO AUTHENTICATION DEFAULT TABLESPACE USERS QUOTA 32M ON USERS')
        for name, statement in zip(('LGL_ONT_WORK_A', 'LGL_ONT_EVT_A'), statements):
            c.execute('SELECT TABLE_NAME FROM DBA_TABLES WHERE OWNER=:1 AND TABLE_NAME=:2', [AGENT, name])
            if c.fetchone() is None:
                c.execute(statement)
            c.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ' + AGENT + '.' + name + ' TO A8_GR12_CM1208')
    write('agent-storage.json', {'owner': AGENT, 'tables': ['LGL_ONT_WORK_A', 'LGL_ONT_EVT_A'],
          'authentication': 'NONE', 'quota_bytes': 32 * 1024**2, 'ddl': statements,
          'grant_to': 'A8_GR12_CM1208', 'privileges': ['SELECT', 'INSERT', 'UPDATE', 'DELETE']})


def publish():
    prepared = read('prepared.json')
    assert read('authorization.json')['prepared_sha256'] == connect.sha(OUT / 'prepared.json')
    receipts = []
    with connect.open_store(seconds=180, max_calls=1000) as (store, request, transport):
        from semantic_runtime.ontology_work.workflow import Workflow
        from semantic_runtime.ontology_work.store import LocalFolderStore
        assert store.gold_ports.mapping.file_sha256 == prepared['mapping_sha256']
        assert request.release_id == prepared['query_release_id']
        ensure_agent()
        repo = store.gold_ports.mapping.ontology_repository(writer_connection, agent_owner=AGENT, read_only=False)
        workflow = Workflow(repo, LocalFolderStore(WORK), actor=ACTOR, source_reader=store.gold_ports.source_reader)
        for entry in prepared['entries']:
            bid = entry['bundle_id']
            old = repo.latest(bid)
            if old is None:
                row = workflow.save(entry['work'], entry['proposal'], bundle_id=bid)
            else:
                row = {'bundle_id': bid, **old}
                saved = workflow.load(bid)
                assert saved['input'] == entry['work'] and saved['proposal'] == entry['proposal'], 'existing content differs'
            preview = workflow.preview(bid)
            assert preview['package_sha256'] == entry['preview_package_sha256']
            if repo.latest(bid)['status'] == 'DRAFT':
                workflow.review(bid, row['revision'], row['work_hash'], True,
                    '사용자가 몇 건의 게시 선택·실행을 위임함. Codex가 Oracle 원문 4단위와 정확 인용·조건·효과·제한을 대조함. 개별 법률 품질의 인간 심사 인증이 아님. 요청: ' + AUTHORIZATION)
            receipt = workflow.publish(bid, row['revision'], row['work_hash'], repo.head(bid)['sequence'])
            assert receipt['active']
            receipts.append({'bundle_id': bid, **receipt, 'work_hash': row['work_hash'],
                             'revision': row['revision'], 'concept': entry['work']['concept']})
            write('publication-receipts.json', receipts)
        after = snapshot(store.gold_ports.mapping)
        before = read('before.json')
        assert after['objects'] == before['objects']
        assert {k:v for k,v in after['counts'].items() if not k.startswith('ONTL_')} == {
            k:v for k,v in before['counts'].items() if not k.startswith('ONTL_')}
        assert all(after['counts'][k] == before['counts'][k] + n for k,n in [('ONTL_POST',3),('ONTL_HEAD',3),('ONTL_ANC',12)])
        write('after.json', after)
        write('published.json', {'status': 'PUBLISHED', 'bundles': 3, 'paths': 9, 'anchors': 12,
                                'source_sql_calls': request.sql.calls, 'external_model_calls': 0})
        print(json.dumps(read('published.json')))


def verify():
    prepared = read('prepared.json')
    receipts = {r['bundle_id']: r for r in read('publication-receipts.json')}
    result = {'checks': [], 'external_model_calls': 0, 'actual_final_answer': False}
    with connect.open_store(seconds=180, max_calls=1000) as (store, request, transport):
        from semantic_runtime.ontology_work import runtime as ort
        from semantic_runtime.legal_agent import ontology_scenarios as sc
        from semantic_runtime.legal_agent.errors import ContractError
        from semantic_runtime.contracts import digest
        provider = store.gold_ports.ontology
        document = request.sources.document(DID)
        selected = {}; units = {}; fragments = []
        for entry in prepared['entries']:
            for original in entry['work']['originals']:
                a = original['anchor']; uid = a['unit_id']
                assert store.gold_ports.source_reader(a) == original['text']
                found = provider.lookup(a, {DID})
                assert len(found) == 1 and found[0]['publication_id'] == receipts[entry['bundle_id']]['publication_id']
                assert not provider.lookup(a, set()) and not provider.lookup({**a, 'version': 'not-current-version'}, {DID})
                rows = store.db.execute('SELECT block_id FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)', (DID,uid)).fetchall()
                selected[uid] = {'source_id': 'source-current', 'document_id': DID, 'offer': {'block_ids': [str(r[0]) for r in rows]}}
                units[(DID, uid)] = {}
                fragments.append(dict(original, evidence_refs=['verified-original:' + uid]))
        # The same source-arrival runtime and Oracle request port used by RAG.
        # This bounded component check does not fabricate a model/API answer.
        saves = []; events = []
        session = SimpleNamespace(scope={DID}, store=store, matcher=SimpleNamespace(units=units),
            tools=SimpleNamespace(sources={'source-current': document}),
            repo=SimpleNamespace(event=lambda *a: events.append(a)))
        inv = SimpleNamespace(s=session, policy={'ontology_enabled': True, 'ontology_context': {'mode':'DB'}},
            p={'binding': request.sql.binding, 'selected': selected}, save=lambda: saves.append(1))
        context = ort.acquire(inv, list(selected), None)
        assert len(context['snapshot']['bundles']) == 3 and not events
        assert {v['status'] for v in inv.p['ontology_database']['lookups'].values()} == {'FOUND'}
        calls = request.sql.calls
        ort.acquire(inv, list(selected), None)
        # Source unit discovery repeats; bound publication lookup does not.
        assert request.sql.calls == calls + len(selected)
        inputs = []
        for entry in prepared['entries']:
            rows = provider.lookup(entry['work']['originals'][0]['anchor'], {DID})
            package = rows[0]['context']['scenario_package']
            current = [f for f in fragments if f['anchor'] in [o['anchor'] for o in entry['work']['originals']]]
            catalog = sc.bind_current(package, current)
            assert len(catalog['paths']) == 3 and not catalog['withheld'] and not catalog['runtime_compilation']
            missing = sc.bind_current(package, current[:1])
            assert not missing['paths'] and len(missing['withheld']) == 3
            bad = deepcopy(current); bad[1]['text'] += 'changed'
            try:
                sc.bind_current(package, bad)
            except ContractError:
                pass
            else:
                raise AssertionError('changed original accepted')
            model_input = sc.selection_input(catalog, entry['work']['concept'] + ' 원문 범위 확인', [{'id':'Q1','text':entry['work']['concept']}])
            assert len(model_input['ontology_bundles'][0]['scenario_catalog']['paths']) == 3
            assert all(p['source_refs'] for p in catalog['paths'])
            inputs.append({'bundle_id': entry['bundle_id'], 'publication_id': rows[0]['publication_id'],
                           'input': model_input, 'input_sha256': digest(model_input)})
        write('assembled-inputs.json', inputs)
        write('runtime-lookups.json', inv.p['ontology_database'])
        result.update(status='PASS_LOCAL_ORACLE_PUBLICATION_AND_RUNTIME_COMPONENTS',
            publications=3, anchors=12, paths=9, sql_calls=request.sql.calls, source_arrival_events=len(saves),
            checks=['current_source_exact_text_and_hash','active_oracle_publication_lookup_12_anchors',
                    'unauthorized_scope_denied','stale_document_version_denied','source_arrival_runtime_found_3',
                    'request_publication_lookup_reused','missing_source_withheld_9_paths','changed_source_rejected',
                    'precompiled_9_paths_in_scenario_selection_input'],
            runtime_scope='real Oracle; source-arrival component and selection_input; no full native API/model inference',
            default_ontology_enabled=False)
    write('verification.json', result)
    print(json.dumps(result, ensure_ascii=False))


def withdraw():
    """Explicit operator action; keep publications/work and record each withdrawal."""
    receipts = read('publication-receipts.json')
    with connect.open_store(seconds=180, max_calls=100) as (store, request, transport):
        repo = store.gold_ports.mapping.ontology_repository(writer_connection, agent_owner=AGENT, read_only=False)
        heads = {r['bundle_id']: repo.head(r['bundle_id']) for r in receipts}
        for row in receipts:
            head = heads[row['bundle_id']]
            assert head['publication_id'] in (None, row['publication_id']), 'another publication is active; stop'
        completed = []
        for row in receipts:
            head = heads[row['bundle_id']]
            if head['publication_id'] is not None:
                repo.activate(row['bundle_id'], None, head['sequence'], ACTOR)
            completed.append({'bundle_id': row['bundle_id'], 'head': repo.head(row['bundle_id'])})
            write('withdrawal-receipts.json', completed)
    print(json.dumps({'status':'WITHDRAWN', 'publications_preserved':len(receipts)}))


def main():
    logging.disable(logging.CRITICAL)
    p = argparse.ArgumentParser(); p.add_argument('action', choices=['prepare','publish','verify','withdraw'])
    args = p.parse_args()
    try:
        globals()[args.action]()
    except BaseException:
        OUT.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%H%M%S%f')
        (OUT / ('failure-' + args.action + '-' + stamp + '.txt')).write_text(traceback.format_exc())
        raise


if __name__ == '__main__':
    main()
