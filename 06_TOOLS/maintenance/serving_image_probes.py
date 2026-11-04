"""Actual serving consumers for check_serving_image_imports.py (no pytest)."""
import asyncio
import hashlib
import importlib
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(name):
    if name == 'deny-selfcheck':
        denied = []
        for module in ('sqlglot', 'pyarrow', 'emoji', 'pytest', 'anthropic'):
            try:
                importlib.import_module(module)
            except ModuleNotFoundError as exc:
                assert exc.name == module and 'A8_IMAGE_IMPORT_DENIED' in str(exc)
                denied.append(module)
            else:
                raise AssertionError('unlisted package was imported: ' + module)
        return {'denied': denied, 'unlisted_imports_succeeded': 0}
    if name.startswith('ping-'):
        os.environ['DP'] = name.removeprefix('ping-')
        import service
        result = asyncio.run(service.service({}, {'API_TYPE': 'PING'}))
        assert result.get('status') == 200 or result.get('ok') is True, result
        return result
    if name == 'http-readiness':
        app = load('image_probe_http', '08_DEPLOYMENT/GENOS/stream_app.py')
        import httpx
        async def check():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url='http://test') as client:
                rows = []
                for path in ('/', '/health'):
                    response = await client.get(path)
                    assert response.status_code == 200
                    rows.append({'path': path, 'status': response.status_code, 'body': response.json()})
                response = await client.post('/stream', json={'API_TYPE': 'SSE_CHECK'})
                assert response.status_code == 200 and '"sse_ready":true' in response.text
                rows.append({'path': '/stream', 'status': response.status_code, 'sse_ready': True})
                return rows
        return asyncio.run(check())
    if name == 'serving-modules':
        names = ['app', 'pipeline', 'provider', 'genos', 'oracle_query_service', 'oracle_query_native',
                 'oracle_silver_reads', 'oracle_agent_records', 'oracle_record_sqlite', 'term_morph',
                 'fulltext', 'oracle_query_glossary', 'legal_agent.law_navigation']
        for module in names:
            importlib.import_module('semantic_runtime.'+module)
        return {'modules': names}
    if name == 'genos-client':
        from semantic_runtime import genos, provider
        transport = genos.Endpoint('https://genos.invalid/v1', 'fixture')
        client = provider.Haiku(ROOT, ROOT/'09_ARTIFACTS/AUDITS/20261104-a8-image-allowlist/provider-unused',
                               backend='genos', trust_zone='internal')
        from semantic_runtime.provider import _structured_genos_value
        response = _structured_genos_value({'choices': [{'finish_reason': 'stop', 'message': {'content': '{"value":1}'}}]})
        assert response == {'value': 1} and client.backend == 'genos'
        import httpx
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))) as http:
            assert http.post(transport.url('/chat/completions'), json={}).json() == response
        return {'backend': client.backend, 'http_mock': 'PASS', 'model_calls': 0}
    if name == 'ords-client':
        from semantic_runtime.oracle_ords import create_client, RestClient
        client = create_client(schema='fixture', auth_key='fixture', base_url='https://ords.invalid/ords')
        assert isinstance(client, RestClient)
        return {'transport': type(client).__name__, 'network_calls': 0}
    if name == 'sqlite-original':
        from semantic_runtime.storage import Store
        from semantic_runtime import document_browser
        pointer = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
        release = json.loads((ROOT/pointer['manifest_path']).read_text())
        generation = ROOT/release['data_path']
        cases = json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-1314-oracle-root-local-reuse/artifacts/design/query-cases.json').read_text())
        store = Store(generation)
        try:
            did, bid = cases['document_id'], cases['source_blocks'][0]
            row = store.source(did, bid)
            assert row['document_id'] == did and row['text']
            page = document_browser.read(store, did, limit=2)
            store.check_unchanged()
            return {'original_sha256': hashlib.sha256(row['text'].encode()).hexdigest(),
                    'document_page': bool(page), 'writes': 0}
        finally:
            store.close()
    if name == 'tokenize':
        from semantic_runtime.term_morph import tokenize
        result = tokenize('상법상 이사회 의결권과 주주총회 승인')
        assert result
        return {'tokens': [v.form for v in result]}
    if name == 'kiwi-candidate':
        # Alternative feasibility only; never changes the serving tokenizer
        # or reads an existing PeCab index with a different analyzer.
        from kiwipiepy import Kiwi
        kiwi = Kiwi(num_workers=1)
        rows = []
        for text in ('상법상 이사회 의결권과 주주총회 승인', '각 호의 자기주식 처분 한도', '승인 완료 😀'):
            tokens = kiwi.tokenize(text)
            assert tokens and all(0 <= t.start < t.start + t.len <= len(text) for t in tokens)
            rows.append({'text': text, 'tokens': [{'form': t.form, 'tag': t.tag, 'start': t.start, 'len': t.len} for t in tokens]})
        return {'version': importlib.metadata.version('kiwipiepy'),
                'model_version': importlib.metadata.version('kiwipiepy-model'), 'rows': rows,
                'production_tokenizer_changed': False, 'index_compatibility_tested': False}
    if name == 'pecab-emoji':
        # Inspect this actual PeCab module independently: the first pyarrow
        # import otherwise prevents reaching its second required dependency.
        # No missing package is stubbed, allowed or installed for this probe.
        dist = importlib.metadata.distribution('pecab')
        assert dist.version == '1.0.8'
        path = dist.locate_file('pecab/_utils/_emojis.py')
        spec = importlib.util.spec_from_file_location('pecab_emoji_probe', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {'emoji': module.get_emoji('😀')}
    if name == 'rag-search':
        pointer = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
        release = json.loads((ROOT/pointer['manifest_path']).read_text())
        with tempfile.TemporaryDirectory(prefix='a8-image-rag-') as temporary:
            os.environ['GENOS_GENERATION'] = str((ROOT/release['data_path']).resolve())
            os.environ['GENOS_RUNTIME_DIR'] = temporary
            import service
            result = asyncio.run(service.service({}, {'API_TYPE': 'RAG_SEARCH', 'q': '이사회 의결권', 'limit': 2}))
            assert result.get('status') == 200, result
            return {'status': result['status'], 'body_keys': sorted(result.get('body', {}))}
    if name == 'fulltext-phrases':
        from semantic_runtime.fulltext import question_terms
        from semantic_runtime.oracle_query_fulltext import query_phrases
        terms = question_terms('상법상 이사회 의결권과 주주총회 승인')
        phrases = query_phrases(terms)
        assert phrases
        return {'terms': terms, 'phrases': phrases}
    if name == 'oracle-read':
        return oracle_read()
    raise ValueError('unknown probe ' + name)


def oracle_read():
    import oracledb
    from semantic_runtime.oracle_query_db import Connection
    from semantic_runtime.oracle_query_catalog import ROW, LOOKUP_ENCODING, lookup_key
    credential = Path.home()/'.local/state/8-agent/gold-r12-1208/readonly-connection.json'
    assert not credential.stat().st_mode & 0o077
    config = json.loads(credential.read_text())
    assert config['dsn'].startswith('127.0.0.1:')
    value = '목록제한😀' * 1000
    calls = []
    with oracledb.connect(**config) as remote:
        remote.call_timeout = 15000
        class SQL:
            def query(self, sql, binds, *, limit):
                assert sql.startswith('SELECT ')
                calls.append(sql)
                with remote.cursor() as cursor:
                    types = {'CLOB': oracledb.DB_TYPE_CLOB, 'NUMBER': oracledb.DB_TYPE_NUMBER, 'VARCHAR2': oracledb.DB_TYPE_VARCHAR}
                    cursor.setinputsizes(**{n: types[t] for n, v, t in binds})
                    cursor.execute(sql, {n: v for n, v, t in binds})
                    return [dict(zip([c[0] for c in cursor.description],
                                     [v.read() if hasattr(v, 'read') else v for v in row])) for row in cursor.fetchmany(limit)]
        def select(allowed):
            columns = {n: {'type': 'text', 'max_bytes': len(value.encode()), 'has_null': False, 'has_empty': False} for n in ('id', 'json')}
            table = {'asset': 'fixture', 'table': 'source', 'lookup_encoding': LOOKUP_ENCODING, 'columns': columns}
            request = NS(sql=SQL(), release_id='release', sources=NS(allowed=allowed), records=NS(manifest={'tables': {'source.rows': table}}))
            port = Connection(request, 'fixture')
            view = port._view
            def fixture(name, number):
                text, binds = view(name, number)
                rows = "(SELECT 'release' RELEASE_ID,'source.rows' KIND,'allowed' DOCUMENT_ID,'row' ROW_ID,:a8_fixture_key LOOKUP_ID,:a8_fixture_value VALUE_JSON FROM DUAL)"
                return text.replace(ROW, rows), binds + [('a8_fixture_key', lookup_key(value), 'VARCHAR2'),
                    ('a8_fixture_value', json.dumps({'id': value, 'json': value}, ensure_ascii=False), 'CLOB')]
            port._view = fixture
            return [tuple(row) for row in port.execute('SELECT json FROM source WHERE id=?', [value])]
        assert select({'allowed'}) == [(value,)]
        assert select({'denied'}) == []
        return {'oracle_version': remote.version, 'selects': len(calls), 'unicode_exact': True, 'acl_denied': True, 'writes': 0}
