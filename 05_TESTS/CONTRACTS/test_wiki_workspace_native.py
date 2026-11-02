"""Workspace publications through the real native API with a synthetic provider."""
from copy import deepcopy
import ast
import inspect
import json
import os
from pathlib import Path
import sqlite3

import pytest

from conftest import term_glossary
from test_wiki_workspace import env, ws, seed, published, pin


@pytest.mark.parametrize('mode', ['active', 'withdraw_during_assess', 'withdraw_on_replay'])
def test_workspace_native_api_delivery_and_revocation(env, ws, tmp_path, term_glossary, monkeypatch, mode):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root/'06_TOOLS/EXPERIMENTS/adr_1188'))
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT', os.environ.get('WORKFLOW_TEST_CODE_ROOT', str(root)))
    monkeypatch.setenv('GENOS_AUTO_WARMUP', '0'); monkeypatch.setenv('AD_WORKER_ENABLED', '0')
    from semantic_runtime import app as app_module
    from semantic_runtime.ontology_work import runtime, assembly_compiler
    from semantic_runtime.legal_agent.ontology_compiler import content_hash
    real_create = app_module.create_app; delivered = []; saved = {}
    statement = '이 확인 업무는 서면 승인 후 시행한다.'

    def withdraw():
        if saved.get('withdrawn'): return
        sid = saved['item'].sid
        ws.apply(change_id='native-withdraw', expected=pin(ws, sid), operations=[
            {'op': 'RETRACT', 'target': sid, 'value': {'reason': '합성 동시 철회 검사'}}])
        saved['withdrawn'] = True

    def create(*args, **kwargs):
        with sqlite3.connect(tmp_path/'raw.sqlite') as db:
            version = db.execute("SELECT source_artifact_sha256 FROM document WHERE document_id='d'").fetchone()[0]
            text = db.execute("SELECT text FROM source_block WHERE document_id='d' AND unit_id='1'").fetchone()[0]
        env.source.update(id='S1', anchor={'document_id': 'd', 'version': version, 'unit_id': '1',
                          'content_sha256': content_hash(text), 'label': '가상 규정 제2조'}, text=text)
        for w in (env.w, ws):
            w.document_ids = frozenset(['d']); w.source_reader = lambda a: text if a == env.source['anchor'] else None
        saved['item'] = seed(env, ws, text=statement)
        saved['draft'], saved['stage'], _ = published(env, ws, saved['item'])
        def no_runtime_compile(*args, **kwargs): raise AssertionError('RAG must not compile a stored package')
        monkeypatch.setattr(assembly_compiler, 'compile_package', no_runtime_compile)
        kwargs['legal_agent_profile']['candidate_navigation'].update(
            ontology_enabled=True, ontology_direct_assessment=True, ontology_context={'mode': 'DB'})
        transport = kwargs['legal_agent_transport']; send = transport.send_once
        def send_once(*, body, ticket):
            from api_fixture_integrated import decode
            view = decode(json.loads(body['messages'][1]['content'])['view'])
            response = send(body=body, ticket=ticket)
            if view.get('source_stage', '').startswith('memory-assess'):
                catalogs = [c['payload']['assembly_catalog'] for c in view.get('ontology_bundles', [])
                            if c.get('payload', {}).get('assembly_catalog')]
                assert len(catalogs) == 1 and catalogs[0]['paths'][0]['body'] == statement
                assert catalogs[0]['paths'][0]['source_refs']
                delivered.append(deepcopy(catalogs[0]))
                if mode == 'withdraw_during_assess': withdraw()
            return response
        transport.send_once = send_once
        return real_create(*args, **kwargs)
    monkeypatch.setattr(app_module, 'create_app', create)
    monkeypatch.setattr(runtime, 'repository', lambda: env.repo)
    import need_continuity_fixture as fixture
    original_change = fixture.change_review
    def change_review(head):
        value = deepcopy(head)
        if not value.get('change_from'): value['change_from'] = {'version': 0, 'finding': ''}
        value['review_purposes'] = value.get('review_purposes') or []
        return original_change(value)
    monkeypatch.setattr(fixture, 'change_review', change_review)
    tree = ast.parse(inspect.getsource(fixture.run_api)); fn = tree.body[0]; fn.name = 'setup'
    end = next(i for i, node in enumerate(fn.body) if isinstance(node, ast.With)
        and any(isinstance(item.context_expr, ast.Call) and isinstance(item.context_expr.func, ast.Name)
                and item.context_expr.func.id == 'TestClient' for item in node.items))
    fn.body = fn.body[:end] + ast.parse('return app, transport, question').body
    namespace = dict(vars(fixture)); exec(compile(ast.fix_missing_locations(tree), fixture.__file__, 'exec'), namespace)
    app, transport, question = namespace['setup'](tmp_path, term_glossary, 'goal_control', monkeypatch)
    from fastapi.testclient import TestClient
    try:
        with TestClient(app) as api:
            request = {'question': question, 'session_id': 'workspace-native', 'request_id': mode}
            response = api.post('/v1/rag/ask', json=request)
            calls = list(transport.calls)
            assert delivered
            if mode == 'withdraw_during_assess':
                assert response.status_code != 200, response.text
                assert env.repo.head(saved['draft']['bundle_id'])['publication_id'] is None
            else:
                assert response.status_code == 200, response.text
                result = response.json()
                assert statement in result['answer']['text']
                if mode == 'withdraw_on_replay': withdraw()
                again = api.post('/v1/rag/ask', json=request)
                if mode == 'withdraw_on_replay': assert again.status_code != 200, again.text
                else: assert again.status_code == 200 and again.json()['answer'] == result['answer']
                assert transport.calls == calls
    finally:
        app.state.pipeline.store.close()


def test_workspace_streamlit_profile_free_write_and_reload(env, ws, monkeypatch):
    runtime_path = Path(__file__).resolve().parents[2]/'90_RUNTIME/streamlit-knowledge-design/python'
    if runtime_path.exists(): monkeypatch.syspath_prepend(str(runtime_path))
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    from semantic_runtime.ontology_work import ui, wiki_ui
    monkeypatch.setattr(ui, 'actor', lambda: 'reviewer')
    monkeypatch.setattr(wiki_ui, 'workspace_workflow', lambda **kwargs: ws)
    def forbidden(**kwargs): raise AssertionError('free workspace must not require profile/glossary')
    monkeypatch.setattr(wiki_ui, 'domain_workflow', forbidden)
    app = AppTest.from_string('from semantic_runtime.ontology_work.ui import render\nrender()').run()
    assert not app.exception and not app.error
    next(x for x in app.text_input if x.label == '항목 이름').set_value('아직 분류하지 않은 기록')
    next(x for x in app.text_area if x.label == '기록·설명').set_value('추가 확인이 필요한 기록')
    next(x for x in app.button if x.label == '기록 저장').click().run()
    assert not app.exception and not app.error
    assert ws.list_items()['items'][0]['title'] == '아직 분류하지 않은 기록'
    app.run()
    assert not app.exception and not app.error
    assert len(ws.list_items()['items']) == 1


def test_workspace_streamlit_compile_review_activate(env, ws, monkeypatch):
    from test_wiki_workspace import projection_generator
    from test_domain_profile_workflow import Glossary
    from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
    from semantic_runtime.ontology_work.glossary_binding import GlossaryBinding
    runtime_path = Path(__file__).resolve().parents[2]/'90_RUNTIME/streamlit-knowledge-design/python'
    if runtime_path.exists(): monkeypatch.syspath_prepend(str(runtime_path))
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    from semantic_runtime.ontology_work import ui, wiki_ui
    item = seed(env, ws); calls = []
    ws.generate = projection_generator(env, item, calls)
    def factory(**kwargs):
        w = DomainWorkflow(env.repo, env.w.store, actor=env.w.actor, source_reader=env.w.source_reader,
            generate=None, namespace=env.w.namespace, source_snapshot=env.w.source_snapshot,
            acl_ref=env.w.acl_ref, document_ids=env.w.document_ids,
            glossary=GlossaryBinding(Glossary(), snapshot=env.w.source_snapshot), producer_binding=env.w.producer_binding)
        w.can_publish_workspace = True
        return w
    monkeypatch.setattr(ui, 'actor', lambda: 'reviewer')
    monkeypatch.setattr(wiki_ui, 'workspace_workflow', lambda **kwargs: ws)
    monkeypatch.setattr(wiki_ui, 'domain_workflow', factory)
    app = AppTest.from_string('from semantic_runtime.ontology_work.ui import render\nrender()').run()
    next(x for x in app.checkbox if x.label == '재사용 준비·승인·게시 열기').check().run()
    next(x for x in app.multiselect if x.label == '재사용할 문장').set_value([item.sid])
    next(x for x in app.text_input if x.label == '재사용 목적').set_value('합성 UI 검토')
    def click(label):
        next(x for x in app.button if x.label == label).click().run()
        assert not app.exception and not app.error
    click('선택 문장 컴파일')
    assert len(calls) == 3
    next(x for x in app.text_input if x.label == '검토 의견').set_value('원문·조건 확인')
    next(x for x in app.checkbox if x.label == '원문·포함 범위·미확인 내용을 검토했습니다.').check().run()
    click('재사용 묶음 승인')
    click('소비 검증 후 게시 활성화')
    assert env.repo.lookup(env.source['anchor'], {'fictional'})
    app.run()
    assert not app.exception and not app.error and len(calls) == 3


def test_workspace_streamlit_navigation_and_views_preserve_meaning(env, ws, monkeypatch):
    runtime_path = Path(__file__).resolve().parents[2]/'90_RUNTIME/streamlit-knowledge-design/python'
    if runtime_path.exists(): monkeypatch.syspath_prepend(str(runtime_path))
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    from semantic_runtime.ontology_work import ui, wiki_ui
    a = seed(env, ws, 'layout-a'); b = seed(env, ws, 'layout-b')
    meanings = {sid: ws.item(sid)['work_hash'] for sid in (a.sid, b.sid)}
    monkeypatch.setattr(ui, 'actor', lambda: 'reviewer')
    monkeypatch.setattr(wiki_ui, 'workspace_workflow', lambda **kwargs: ws)
    app = AppTest.from_string('from semantic_runtime.ontology_work.ui import render\nrender()').run()
    next(x for x in app.selectbox if x.label == '내용 보기').set_value(a.eid).run()
    next(x for x in app.selectbox if x.label == '연결할 항목').set_value(b.eid)
    next(x for x in app.text_input if x.label == '연결 설명').set_value('비교 기록')
    def click(label):
        next(x for x in app.button if x.label == label).click().run()
        assert not app.exception and not app.error
    click('탐색 연결 추가')
    assert ws.item(a.eid)['content']['navigation_links'][0]['target'] == b.eid
    click('비교 기록 → 자유 항목 layout-b')
    assert next(x for x in app.selectbox if x.label == '내용 보기').value == b.eid
    next(x for x in app.text_input if x.label == '새 주제 보기 이름').set_value('비교 모음')
    click('이 항목으로 주제 보기 만들기')
    next(x for x in app.multiselect if x.label == '비교 모음 · 포함 항목').set_value([a.eid, b.eid])
    # The seeded helper also creates two independent views.
    target = next(x for x in app.button if x.label == '보기 구성 저장' and
                  x.key.endswith(next(r['bundle_id'] for r in ws.list_items(kind='VIEW')['items'] if r['title'] == '비교 모음')))
    target.click().run()
    assert not app.exception and not app.error
    view = next(r for r in ws.list_items(kind='VIEW')['items'] if r['title'] == '비교 모음')
    assert ws.item(view['bundle_id'])['content']['member_refs'] == [a.eid, b.eid]
    assert {sid: ws.item(sid)['work_hash'] for sid in meanings} == meanings
