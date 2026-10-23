"""Deterministic navigation contracts; no live-model quality or speed claims."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import pytest
from jsonschema import validate
from conftest import term_glossary
from semantic_runtime.legal_agent import connected_exploration as connected
from semantic_runtime.legal_agent import completion_execution as ce
from semantic_runtime.legal_agent import completion_v5, completion_v6, completion_v7, completion_v8
from semantic_runtime.legal_agent import output_contract as oc
from test_main50_request_repair import GAP
from test_unattempted_gap_finish import Journal


def card(target, direction='INCOMING', anchor='a', read=False):
    return {'reference_id': 'ref:' + target, 'target': {'source_id': target},
            'anchor': {'source_id': anchor}, 'direction': direction, 'already_read': read}


def test_incoming_references_cannot_crowd_all_direct_links_out_of_first_menu():
    incoming = [card('reverse' + str(i)) for i in range(30)]
    outgoing = [card('direct' + str(i), 'OUTGOING') for i in range(8)]
    raw = incoming + outgoing
    before = deepcopy(raw)
    shown = connected.diverse_reference_cards(raw)
    assert len(shown) == 16 and raw == before
    assert all(row in shown for row in outgoing)
    assert shown[1] == incoming[0]


def test_bounded_menu_preserves_unread_distinct_targets_and_each_anchor():
    rows = [card('old' + str(i), 'OUTGOING', read=True) for i in range(40)]
    rows += [card('one', 'OUTGOING'), card('one', 'OUTGOING')]
    rows += [card('two' + str(i)) for i in range(30)]
    rows += [card('other', 'OUTGOING', anchor='b'), card('reverse-b', anchor='b')]
    shown = connected.diverse_reference_cards(rows)
    assert len(shown) == 16 and all(not c['already_read'] for c in shown)
    assert len({(c['target']['source_id'], c['direction']) for c in shown}) == 16
    assert {c['target']['source_id'] for c in shown[:4]} == {'one', 'two0', 'other', 'reverse-b'}
    assert connected.diverse_reference_cards([]) == []


@pytest.mark.parametrize('implementation', [completion_v5, completion_v6, completion_v7, completion_v8])
def test_new_wire_requires_locator_but_historical_gaps_and_unknowns_stay_valid(implementation):
    schema = implementation.assessment_schema([{'id': 'Q1', 'question': '모의 기준'}], [], [], [])
    raw = {'claims': [], 'issue_assessments': [{'issue_id': 'Q1', 'status': 'INSUFFICIENT', 'reason': '원문 필요'}],
           'gaps': [deepcopy(GAP)]}
    old = deepcopy(raw)
    old['gaps'][0].pop('missing_target')
    validate({**old, 'disposition': 'NEEDS_INVESTIGATION'}, schema)
    wire, decode = ce.assessment_projection(schema)
    with pytest.raises(oc.OutputContractError):
        decode(old)
    assert decode(raw)['gaps'][0]['missing_target'] == GAP['missing_target']
    for kind, action in [('MISSING_SOURCE', 'READ_SCOPE'), ('MISSING_FACT', 'REQUEST_FACT')]:
        unknown = deepcopy(raw)
        unknown['gaps'][0].update(kind=kind, missing_target='', suggested_action=action)
        assert decode(unknown)['gaps'][0]['missing_target'] == ''
    # Projection must not silently change the persistent contract.
    validate({**old, 'disposition': 'NEEDS_INVESTIGATION'}, schema)


@pytest.mark.parametrize('repair', [True, False])
def test_omitted_locator_reuses_single_repair_owner_and_persisted_terminal_state(tmp_path, repair):
    schema = completion_v8.assessment_schema([{'id': 'Q1', 'question': '모의 기준'}], [], [], [])
    wire, decode = ce.assessment_projection(schema)
    good = {'claims': [], 'issue_assessments': [{'issue_id': 'Q1', 'status': 'INSUFFICIENT', 'reason': '원문 필요'}],
            'gaps': [deepcopy(GAP)]}
    bad = deepcopy(good); bad['gaps'][0].pop('missing_target')
    inputs = {'sources': [{'id': 's', 'text': '원문'}]}
    path = tmp_path / 'journal.sqlite'
    repo = Journal(path)
    calls = []

    def invoke(payload, attempt):
        calls.append(deepcopy(payload))
        assert payload['sources'] == inputs['sources']
        return deepcopy(good if attempt and repair else bad)

    def run():
        return oc.bounded_decision(repo, 'assessment-target-contract', inputs, wire, invoke, decode)

    for repeat in range(2):
        if repair:
            assert run()['gaps'][0]['missing_target'] == GAP['missing_target']
        else:
            with pytest.raises(oc.OutputContractError):
                run()
        assert len(calls) == 2
        repo.db.close()
        if repeat == 0:
            repo = Journal(path)


@pytest.mark.parametrize('route', ['connection', 'structure', 'gap_repair'])
def test_actual_api_reads_link_or_structural_target_and_reuses_request(tmp_path, term_glossary, route):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from semantic_runtime.unit_fulltext import build, UnitFulltextIndex
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    from lawrag.core.legal_coordinate import find_coordinates
    from lawrag.pipeline.term_generation import build_generation
    from test_document_release import source
    from test_legal_agent_double_harness import wire
    from test_source_span_norm import proposal

    root = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/PIPELINE.json').is_file())
    target_text = '모의 인수 업무는 승인하여야 한다.'
    first = '제2조에 따른 적용 범위를 확인한다.' if route == 'connection' else '업무 절차를 확인한다.'
    raw = source(tmp_path / 'raw.sqlite', [('d', '모의승인규정', [
        '제1조 업무 절차: ' + first, '제2조 적용 범위: ' + target_text])])
    with sqlite3.connect(raw) as db:
        for did, uid, text in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
            unit = json.loads(text)
            coordinate = find_coordinates(unit['surface'])[0].coordinate
            unit.update(legal_coordinate=coordinate.as_dict(), coordinate_scope='body',
                        coordinate_key='body:' + coordinate.canonical_surface())
            db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',
                       (json.dumps(unit, ensure_ascii=False), did, uid))
    build_generation(raw, term_glossary, tmp_path / 'built', serving=True)
    generation = tmp_path / 'built/generation'
    build(generation, generation / 'navigation', tmp_path / 'index', workers=1)
    index = UnitFulltextIndex(tmp_path / 'index', json.loads((generation / 'navigation/manifest.json').read_text()))
    question = '모의승인규정의 적용 기준은?'

    class Transport:
        binding = {'provider': 'fixture', 'model': 'synthetic-contract', 'adapter_version': 'fixture-v1',
                   'endpoint_identity': 'no-network', 'trust_zone': 'internal', 'max_input_bytes': 500000}

        def __init__(self):
            self.calls = []
            self.choices = []
            self.link_selected = False
            self.target_bound = False
            self.assess_repairs = 0
            self.located = False

        def validate_model(self):
            return {'verified': True, 'synthetic': True}

        def send_once(self, *, body, ticket):
            view = expand_cards(json.loads(body['messages'][1]['content'])['view'])
            phase = view.get('source_stage', view['phase'])
            self.calls.append(phase)
            if phase == 'request-entry':
                from test_unified_scope_semantic_authority import wire as entry
                value = entry(question)
                value['intent']['issues'][0]['request_quote'] = question
                value['command']['queries'] = ['모의승인규정 제1조']
                value['search']['mode'] = 'STRUCTURE'
                return wire(value)
            if '-read-choice' in phase:
                read_target = any(target_text in s['text'] for s in view['sources'])
                gaps = view.get('assessment_gaps', [])
                if view['sources'] and not read_target and route == 'structure' and not self.located:
                    option = next(o for o in view['tool_options'] if o['choice'] == 'LOCATE')
                    self.located = True
                    self.choices.append('LOCATE')
                    return wire({'choice': 'LOCATE', 'target': option['target'], 'issue_id': 'Q1',
                        'missing_need': '알려진 적용 범위 조문 조회', 'relation': 'DIRECT', 'source_ref': None,
                        'structure_filter': {'coordinate': '제2조', 'title': '', 'coordinate_scope': 'body'}})
                if not view['sources'] or not read_target and (route != 'gap_repair' or gaps):
                    wanted = '제1조' if not view['sources'] else '제2조'
                    candidate = next(c for c in view['read_candidates'] if wanted in json.dumps(c, ensure_ascii=False))
                    if wanted == '제2조' and route == 'connection':
                        self.link_selected = any(c.get('read_action') == candidate['target']
                            for c in view['references']['dependency_cards'])
                        assert self.link_selected
                    if gaps:
                        self.target_bound = any(candidate['target'] in g['read_actions'] for g in view['gap_targets'])
                        assert self.target_bound
                    self.choices.append('READ')
                    return wire({'choice': 'READ', 'selections': [{'target': candidate['target'], 'issue_id': 'Q1',
                        'missing_need': '모의 적용 범위 원문 확인', 'relation': 'DIRECT', 'source_ref': None}]})
                self.choices.append('FINISH')
                return wire({'choice': 'FINISH', 'basis_refs': [s['id'] for s in view['sources']],
                    'issue_refs': ['Q1'], 'evidence_sufficient': read_target, 'reason': '확보한 원문으로 판단'})
            if phase.startswith('memory-assess'):
                found = next((o for o in view['evidence_options'] if target_text in o['text']), None)
                if found:
                    result = proposal(target_text, 'OBLIGATION', [found['id']], found['id'])
                    result.pop('disposition')
                    return wire(result)
                gap = {**GAP, 'reason': '모의승인규정 제2조 적용 범위 원문이 필요하다.',
                       'missing_target': '모의승인규정 제2조'}
                if route == 'gap_repair' and not phase.endswith('-repair'):
                    gap.pop('missing_target')
                elif route == 'gap_repair':
                    self.assess_repairs += 1
                return wire({'claims': [], 'issue_assessments': [
                    {'issue_id': 'Q1', 'status': 'INSUFFICIENT', 'reason': '적용 범위 원문 필요'}], 'gaps': [gap]})
            raise AssertionError('Unexpected phase: ' + phase)

    transport = Transport()
    profile = json.loads((root / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, answer_presentation='structured')
    app = create_app(tmp_path, generation, contracts_root=root, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile=profile, legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id': 'synthetic', 'team_id': 'risk_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = index
    with TestClient(app) as api:
        request = {'question': question, 'session_id': route, 'request_id': 'r1'}
        response = api.post('/v1/rag/ask', json=request)
        assert response.status_code == 200, response.text
        result = response.json()
        assert target_text in result['answer']['text']
        assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == 'COVERED'
        calls = len(transport.calls)
        again = api.post('/v1/rag/ask', json=request)
        assert again.status_code == 200 and again.json()['answer'] == result['answer']
        assert len(transport.calls) == calls
    # The selected profile hands newly acquired originals to ASSESS before
    # another navigation choice. Its gap then returns to the same SELECT path.
    assert transport.choices == {'connection': ['READ', 'READ'],
        'structure': ['READ', 'LOCATE', 'READ'],
        'gap_repair': ['READ', 'READ']}[route]
    assert transport.assess_repairs == (1 if route == 'gap_repair' else 0)
    app.state.pipeline.store.close()
