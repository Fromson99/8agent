"""Oracle scale guard, 대사 (internal↔external comparison) under the shipped selected profile.

Same isolated dev-silver Oracle fixture and publication as test_guard_oracle.py. Documents:
모의내규 (internal) and 모의승인규정 (external) from the comparison contract fixture
(06_TOOLS/EXPERIMENTS/adr_0811 tree, used by 05_TESTS/CONTRACTS/test_comparison_selected_profile.py),
plus internal/external filler documents so the request scope exceeds the scaled row budget.
Scripted model: test_internal_concept_comparison.Transport. Nothing is asserted; evidence only.
"""
import importlib.util
import json
import os
import sqlite3
import time
import traceback
from pathlib import Path

import pytest

from test_oracle_dp_runtime import published  # noqa: F401  (fixture)
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation

import test_guard_oracle as guard
from test_guard_oracle import oracle  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[3]
FILLERS = int(os.environ.get('GUARD_COMPARISON_FILLERS', '3'))
ARTICLES = int(os.environ.get('FILLER_ARTICLES', '30'))
QUESTION = '대사: 모의내규와 모의승인규정의 승인 기준을 비교해 주세요.'


@pytest.fixture
def structured_generation(tmp_path, term_glossary):
    docs = [('inside', '모의내규', ['제1조(승인) 모의승인규정에 따라 승인 후 보고한다.']),
            ('outside', '모의승인규정', ['제1조(승인) 승인 후 보고한다.'])]
    categories = {'inside': 'internal', 'outside': 'external'}
    for i in range(FILLERS):
        for side, prefix in (('internal', 'fi'), ('external', 'fe')):
            did = f'{prefix}{i:02d}'
            docs.append((did, f'{"부속내규" if side == "internal" else "부속규정"}{i:02d}',
                         [f'제{j+1}조(보고) 부속 {j} 승인 보고 문구.' + ''.join(
                             f' 제{(j * 7 + k * 13) % ARTICLES + 1}조를 준용한다.' for k in range(guard.REFERENCES))
                          + (' 모의승인규정 제1조에 따른다.' if guard.REFERENCES else '') for j in range(ARTICLES)]))
            categories[did] = side
    raw = source(tmp_path/'raw.sqlite', docs)
    with sqlite3.connect(raw) as db:
        for did, category in categories.items():
            db.execute('UPDATE document SET json=? WHERE document_id=?', (json.dumps({
                'document_category': category, 'document_metadata': {'team': 'risk_team'},
                'workflow_version': {'verified': True, 'valid_from': '2020-01-01', 'valid_to': None}}), did))
    build_generation(raw, term_glossary, tmp_path/'built', serving=True, storage_profile='compact-v2', fulltext_granularity='unit')
    generation = tmp_path/'built/generation'
    from lawrag.pipeline.search_selection import plan, activate
    activate(plan(generation, latest=True))
    with sqlite3.connect(generation/'navigation/navigation.sqlite') as db:
        counts = dict(db.execute('SELECT document_id,COUNT(*) FROM source GROUP BY document_id').fetchall())
    (guard.EVIDENCE/'comparison-generation.json').write_text(json.dumps({'source_counts': counts, 'total': sum(counts.values())}, indent=1))
    return generation


def selected_profile():
    nodes = json.loads((guard.CODE/'00_SYSTEM/PIPELINE.json').read_text())['profiles']['legal-agent-rag-v6']['nodes']
    config = next(n['parameters']['term_agent'] for n in nodes if 'term_agent' in n.get('parameters', {}))
    return json.loads((guard.CODE/config['legal_agent']['profile']['path']).read_text())


def test_guard_comparison(oracle, published, tmp_path, monkeypatch):
    client, insert, conn, evidence = oracle
    guard.SHARED_ROWS = None
    qid, rows, documents = guard.publish(client, insert, conn, published, tmp_path)
    records = guard.RECORDS
    import tripwire
    tripwire.install(monkeypatch, records)
    guard.scale_thresholds(monkeypatch, records.budget / 10000)
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'keyword')
    duplicates = []
    if os.environ.get('GUARD_DEBUG_DUPLICATE'):
        from semantic_runtime import oracle_query_index as qi
        original_get = qi.Sources.__getitem__

        def getitem(self, sid):
            try:
                return original_get(self, sid)
            except Exception as exc:
                if 'DUPLICATE' in str(exc):
                    rows = self.request.records.page(self.kind, lookup_id=sid, limit=5)['rows']
                    duplicates.append({'sid': sid, 'kind': self.kind, 'rows': rows})
                    (guard.EVIDENCE/'duplicate.json').write_text(json.dumps(duplicates, ensure_ascii=False, indent=1)[:200000])
                raise
        monkeypatch.setattr(qi.Sources, '__getitem__', getitem)
    spec = importlib.util.spec_from_file_location('guard_concepts', ROOT/'05_TESTS/CONTRACTS/test_internal_concept_comparison.py')
    concepts = importlib.util.module_from_spec(spec); spec.loader.exec_module(concepts)
    summary_path = guard.EVIDENCE/'summary.json'
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {'scenarios': {}}
    name = 'C1-comparison-selected-profile'
    records.scenario, records.turn = name, 1
    started = time.monotonic(); before = len(records.sql)
    responses, crash = [], None
    try:
        from semantic_runtime.app import create_app
        from fastapi.testclient import TestClient
        _, store = guard.open_store(client, documents)
        manifest = json.loads((guard.CODE/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json').read_text())
        if manifest.get('comparison_flow') == 'general-questions-v1':
            # 2026-11-12: each side is an ordinary question; this script also answers the ordinary-question stages.
            spec = importlib.util.spec_from_file_location('guard_general_flow', ROOT/'05_TESTS/CONTRACTS/test_compare_general_flow.py')
            general = importlib.util.module_from_spec(spec); spec.loader.exec_module(general)
            transport = general.Both('PAIRED')
        else:
            transport = concepts.Transport()
        profile = selected_profile(); profile['model_binding'] = transport.binding
        runtime = tmp_path/'rt-comparison'
        principal = {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': sorted(documents)}
        app = create_app(runtime, None, contracts_root=guard.CODE, workspace_root=ROOT, data_store=store, provider=object(),
                         implementation='legal-agent-unified-v6', vector=False, runtime_root=runtime,
                         legal_agent_profile=profile, legal_agent_transport=transport, memory_identity=lambda _: principal)
        with TestClient(app, raise_server_exceptions=False) as api:
            r = api.post('/v1/rag/ask', json={'question': QUESTION, 'session_id': 's', 'request_id': 'c1', 'as_of': '2026-10-15'})
            try:
                body = r.json()
            except ValueError:
                body = {}
            responses.append({'status_code': r.status_code, 'status': body.get('status'), 'schema': body.get('response_schema'),
                              'body': r.text[:2000]})
        failures = guard.failures_of(runtime)
    except Exception:
        failures, crash = [], traceback.format_exc()[-3000:]
    sent = records.sql[before:]
    summary['scenarios'][name] = {'seconds': time.monotonic()-started, 'responses': responses, 'run_failures': failures,
        'phases': list(getattr(transport, 'phases', [])) if 'transport' in dir() else [], 'crash': crash, 'sql_count': len(sent), 'sql_errors': [s for s in sent if s['error']],
        'max_rows_one_sql': max([s['rows'] or 0 for s in sent] or [0])}
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    records.scenario = None
    records.dump(guard.EVIDENCE/'records.json')
