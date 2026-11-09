"""Item review answers one issue; an external rule named in the internal original is read first. Scripted model only."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as S

import jsonschema
import pytest
from fastapi.testclient import TestClient

from semantic_runtime import comparison_research_bridge as bridge
from workflow.adapters import projection
from workflow.risk_team_compare_workflow import concepts, retrieval, task_board as tb

HERE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('named_rule_selected_profile', HERE / '05_TESTS/CONTRACTS/test_comparison_selected_profile.py')
selected = importlib.util.module_from_spec(spec); spec.loader.exec_module(selected)
tree = selected.tree
SIDE = {'status': 'MISSING', 'text': '', 'citations': [], 'missing': '미확인'}


def review(mode, fields):
    source = {'evidence_id': 'new', 'side': 'external', 'spans': [{'text': '변경 시 책임자가 재검토한다.'}]}
    data = {'sources': [source], 'fields': {f: f for f in fields}, 'locators': {}, 'review_mode': mode, 'previous': [None] * len(fields)}
    return projection.prepare('ITEMS', data, tb.review_contract(fields, ['new'], mode == 'UPDATE'))


def item(field):
    return {'field': field, 'internal': dict(SIDE), 'external': dict(SIDE), 'content_status': 'UNKNOWN', 'difference': '', 'next_tasks': []}


def updates():
    return [{'evidence_id': 'new', 'disposition': 'UNRESOLVED', 'reason': '영향 판단 전'}]


def test_initial_review_allows_one_item_per_requested_field():
    _, wire, expand, _ = review('INITIAL', ['condition'])
    assert wire['properties']['items']['maxItems'] == 1
    assert len(expand({'evidence_updates': updates(), 'items': [item('condition')]})['items']) == 1
    _, wire, _, _ = review('INITIAL', ['condition', 'obligation'])
    assert wire['properties']['items']['maxItems'] == 2
    _, wire, _, _ = review('UPDATE', ['condition'])
    assert wire['properties']['items']['maxItems'] == 28


def test_other_issues_in_one_review_are_rejected_with_a_concrete_reason():
    _, _, expand, _ = review('INITIAL', ['condition'])
    with pytest.raises(ValueError) as error:
        expand({'evidence_updates': updates(), 'items': [item('condition'), item('condition'), item('condition')]})
    text = str(error.value)
    assert 'too many items' in text and 'condition' in text and '3 were submitted' in text


def test_duplicate_side_patch_names_the_field():
    _, _, expand, _ = review('UPDATE', ['condition'])
    patch = {'field': 'condition', 'side': 'external', **SIDE}
    with pytest.raises(ValueError) as error:
        expand({'evidence_updates': updates(), 'items': [dict(patch), dict(patch)]})
    assert 'duplicate field-side patch: field condition' in str(error.value)


def port(names, categories):
    return S(all_scope=list(names), categories=categories, session=S(names=names))


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setattr(bridge, 'document_names', lambda session, did: session.names[did])


def test_named_rule_longest_registered_name_wins(registered):
    names = {'law': ['모의법'], 'decree': ['모의법 시행령'], 'rule': ['모의 감독규정', '감독규정'], 'inside': ['모의 내규']}
    categories = {'law': 'external', 'decree': 'external', 'rule': 'external', 'inside': 'internal'}
    p = port(names, categories)
    assert bridge.preferred_documents(p, '이 지침은 「모의법 시행령」 제3조에 따른다.', 'external') == ['decree']
    assert bridge.preferred_documents(p, '모의법과 모의법 시행령을 따른다.', 'external') == ['decree', 'law']
    assert bridge.preferred_documents(p, '「모의 감독규정」 제12조', 'external') == ['rule']
    assert bridge.preferred_documents(p, '모의 내규와 모의법', 'external') == ['law']
    assert bridge.preferred_documents(p, '모의 내규와 모의법', 'internal') == ['inside']
    assert bridge.preferred_documents(p, '관계없는 문장', 'external') == []


def test_external_rule_named_in_internal_original_is_read_first(tmp_path, tree):
    app, transport = selected.application(tmp_path, tree)
    # The question does not name the external rule; only the internal original does.
    body = {**selected.BODY, 'question': '대사: 모의내규의 승인 기준을 외규와 비교해 주세요.'}
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=body)
        assert response.status_code == 200, response.text
        value = response.json()
        external = value['rag_results']['external']
        assert external['bundle']['export_mode'] == 'SOURCE_HANDOFF' and external['evidence_ids']
        assert external['investigation_return']['acquisition']['documents']['outside']['read_complete'] is True
        assert value['comparison_items']['items']


def test_rule_named_in_an_uncited_article_of_a_cited_internal_document(registered, monkeypatch):
    names = {'rule': ['모의 감독규정'], 'law': ['모의법'], 'in': ['모의 지침'], 'in2': ['다른 지침']}
    categories = {'rule': 'external', 'law': 'external', 'in': 'internal', 'in2': 'internal'}
    sources = [
        {'evidence_id': 'a1', 'document_id': 'in', 'side': 'internal', 'text': '제1조(목적) 이 지침은 「모의 감독규정」 제12조에 따른다.'},
        {'evidence_id': 'a2', 'document_id': 'in', 'side': 'internal', 'text': '제3조 회사는 비율을 유지한다.'},
        {'evidence_id': 'b1', 'document_id': 'in2', 'side': 'internal', 'text': '「모의법」에 따른다.'},
        {'evidence_id': 'x1', 'document_id': 'rule', 'side': 'external', 'text': '「모의법」을 준용한다.'}]
    monkeypatch.setattr(concepts, 'originals', lambda ctx, state: sources)
    ctx = S(rag=S(port=port(names, categories)))
    state = {'concept_plan': {'concepts': [{'internal_citations': [{'evidence': 'a2', 'quote': '회사는 비율을 유지한다.'}]}]}}
    # The purpose article of the cited document names the rule; another internal document and external text do not count.
    assert retrieval.named_external(ctx, state) == ['rule']
    state['concept_plan']['concepts'][0]['internal_citations'][0]['evidence'] = 'b1'
    assert retrieval.named_external(ctx, state) == ['law']


def test_concept_stage_note_keeps_its_timing_in_the_report(tmp_path, tree):
    app, transport = selected.application(tmp_path, tree)
    original = transport.send_once

    def noted(*, body, ticket):
        response = original(body=body, ticket=ticket)
        view = json.loads(body['messages'][1]['content'])['view']
        if view.get('source_stage') == 'workflow-concepts':
            message = response['body_json']['choices'][0]['message']
            value = json.loads(message['content']); value['unresolved'] = ['외규 원문이 아직 확보되지 않음']
            message['content'] = json.dumps(value, ensure_ascii=False)
        return response
    transport.send_once = noted
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=selected.BODY)
        assert response.status_code == 200, response.text
        notes = response.json()['unresolved']
        assert concepts.STAGE_NOTE + '외규 원문이 아직 확보되지 않음' in notes and '외규 원문이 아직 확보되지 않음' not in notes
