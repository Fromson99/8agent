"""Incomplete review is publishable; source integrity is still mandatory."""
import asyncio
from copy import deepcopy
import json
import sqlite3

import jsonschema
import pytest

import test_internal_concept_comparison as fixture
from test_legal_agent_double_harness import wire
from test_research_resolution_consumers import load
from workflow.risk_team_compare_workflow import task_board as tb
from workflow.risk_team_compare_workflow.report import literal

tree = fixture.tree


def item(field='obligation'):
    side = {'status':'PARTIAL','text':'확보 원문 확인','citations':[],
            'dependencies':[],'scope_sufficient':False,'missing':'추가 검토 필요'}
    return {'field':field,'internal':deepcopy(side),'external':deepcopy(side),
            'content_status':'UNKNOWN','difference':'','next_tasks':[]}


@pytest.mark.parametrize('fields', [[], ['obligation'], ['obligation','exceptions']])
def test_valid_subset_keeps_missing_fields_unjudged(fields):
    value = {'items':[item(f) for f in fields]}
    before = deepcopy(value)
    jsonschema.validate(value, tb.REVIEW)
    tb.checked(value, [], ['obligation','exceptions'], {})
    assert value == before


@pytest.mark.parametrize('defect', ['duplicate','unknown','quote','wrong_side','locator'])
def test_partial_review_still_rejects_integrity_errors(defect):
    source = {'evidence_id':'E','side':'internal','spans':[{'text':'확보 원문'}]}
    row = item()
    value = {'items':[row]}
    if defect == 'duplicate': value['items'].append(deepcopy(row))
    if defect == 'unknown': row['field'] = 'unknown'
    if defect == 'quote': row['internal']['citations'] = [{'evidence':'E','quote':'없는 원문'}]
    if defect == 'wrong_side': row['external']['citations'] = [{'evidence':'E','quote':'확보 원문'}]
    if defect == 'locator':
        row['next_tasks'] = [{'side':'external','operation':'read_node','locator_id':'unknown','anchor_ids':[]}]
    with pytest.raises(ValueError):
        tb.checked(value, [source], ['obligation','exceptions'], {})


class OmittedFields(fixture.Transport):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        result = super().send_once(body=body, ticket=ticket)
        stage = view.get('source_stage')
        if stage not in ('workflow-concepts','workflow-items'): return result
        value = json.loads(result['body_json']['choices'][0]['message']['content'])
        if stage == 'workflow-concepts':
            for concept in value['concepts']:
                concept['requested_fields'] = ['obligation','exceptions']
        else:
            for row in value['items']: row['next_tasks'] = []
            if self.mode == 'some':
                value['items'] = [row for row in value['items'] if row['field'] == 'obligation']
            elif self.mode == 'all':
                value['items'] = []
                for update in value['evidence_updates']:
                    update.update(disposition='UNRESOLVED',reason='항목별 검토 미완료')
        return wire(value)


@pytest.mark.parametrize('mode', ['none','some','all'])
def test_service_publishes_incomplete_review_once_with_sources_and_saved_result(tmp_path, tree, mode):
    app, _ = fixture.application(tmp_path, tree)
    transport = OmittedFields(mode)
    app.state.pipeline.term_agent.transport = transport
    service = load('partial_items_service_' + mode, 'service.py')
    service._APP = app
    service._BINDING = {'mode':'isolated-contract-test'}
    request = {'API_TYPE':'RAG_ASK', **fixture.fixture.prior.BODY}
    result = asyncio.run(service.service({}, request))
    assert result['status'] == 200, result
    value = result['body']
    reviews = [v for stage,v in transport.views if stage == 'workflow-items']
    assert len(reviews) == 1
    assert not reviews[0].get('repair')
    items = {r['field']:r for r in value['comparison_items']['items']}
    assert set(items) == {'obligation','exceptions'}
    if mode != 'none':
        assert value['status'] == 'partial'
        assert value['item_review_omissions']
        assert items['exceptions']['content_status'] == 'UNKNOWN'
        assert not items['exceptions']['internal']['citations']
        assert '추가 확인' in value['answer']['text']
        assert '미완료' not in value['answer']['text']
    if mode == 'some':
        assert items['obligation']['internal']['citations']
        assert items['obligation']['external']['citations']
    if mode == 'all':
        assert value['unreviewed_sources']
        assert '함께 확인한 원문' in value['answer']['text']
        bundle = value['assembly']['term_agent']['source_bundle']['sources']
        ids = {e['evidence_id'] for e in value['unreviewed_sources']}
        from html import escape
        assert any(c['side'] == 'external' and c['selection_id'] in ids and escape(c['excerpt']).replace('\n','<br>') in value['answer']['text'] for c in bundle)
        assert '연결 외규 원문 미확보' not in value['answer']['text']
    journal = app.state.workflow_runtime.root / value['run_id'] / 'journal.sqlite'
    with sqlite3.connect(journal) as db:
        state = json.loads(db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0])
        deadline = db.execute('SELECT deadline_at FROM run').fetchone()[0]
        budget = db.execute('SELECT * FROM budget').fetchall()
    if mode != 'none':
        missing = [r for r in state['task_board']['rows'].values() if r['field'] == 'exceptions']
        assert all(r['current'] is None and not r['revisions'] for r in missing)
    calls = len(transport.views)
    duplicate = asyncio.run(service.service({}, request))
    saved = asyncio.run(service.service({}, {'API_TYPE':'WORKFLOW_STATUS',
        'session_id':request['session_id'],'run_id':value['run_id']}))
    assert duplicate['body']['answer'] == saved['body']['answer'] == value['answer']
    assert len(transport.views) == calls
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT deadline_at FROM run').fetchone()[0] == deadline
        assert db.execute('SELECT * FROM budget').fetchall() == budget


@pytest.mark.parametrize('mode', ['some','all'])
def test_resume_after_partial_commit_does_not_repeat_review_or_reset_deadline(tmp_path, tree, monkeypatch, mode):
    import importlib
    from fastapi.testclient import TestClient
    app, _ = fixture.application(tmp_path, tree)
    transport = OmittedFields(mode)
    app.state.pipeline.term_agent.transport = transport
    definition = app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow', None, 'risk_team')
    owner = importlib.import_module(definition.entrypoint.__module__.rsplit('.',1)[0] + '.task_board')
    original = owner.review
    calls = []
    def stop(ctx, state):
        result = original(ctx, state)
        calls.append(sum(stage == 'workflow-items' for stage,_ in transport.views))
        if len(calls) == 1: raise KeyboardInterrupt('after incomplete review commit')
        return result
    monkeypatch.setattr(owner, 'review', stop)
    with pytest.raises(KeyboardInterrupt):
        app.state.workflow_runtime.execute(
            {**fixture.fixture.prior.BODY,'workflow_id':'risk_team_compare_workflow'},
            fixture.fixture.prior.prior._base.PRINCIPAL)
    journal = next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        revision = db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        deadline = db.execute('SELECT deadline_at FROM run').fetchone()[0]
    with TestClient(app) as client:
        response = client.post('/v1/workflows/resume', json={
            'run_id':journal.parent.name,'session_id':'s','expected_revision':revision})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'partial'
    assert response.json()['item_review_omissions']
    assert calls == [1,1]
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT deadline_at FROM run').fetchone()[0] == deadline
