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


@pytest.mark.parametrize('route', ['connection', 'context', 'chain', 'narrow', 'whole', 'batch'])
def test_small_connection_api_original_delivery_and_request_reuse(tmp_path, term_glossary, route, monkeypatch):
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
    first = '제2조에 따른 적용 범위를 확인한다.' if route in ('connection','chain') else '업무 절차를 확인한다.'
    if route=='context':first=' '.join(f'제{i}조에 따른 기준을 확인한다.' for i in range(2,11))
    if route=='batch':first='제2조 및 제3조에 따른 적용 범위를 확인한다.'
    nested = route in ('narrow', 'whole')
    texts = (['제1조 업무 절차', '① 제2조에 따른 적용 범위를 확인한다.',
        '② 제3조에 따른 별도 업무를 확인한다.', '제2조 적용 범위: '+target_text,
        '제3조 별도 업무: 다른 업무의 절차.'] if nested else [
        '제1조 업무 절차: ' + first, '제2조 적용 범위: ' + ('제3조에 따른 승인 기준을 확인한다.' if route=='chain' else '참고 절차 2.' if route=='context' else target_text),
        *(['제3조 승인 기준: '+target_text] if route=='chain' else []),
        *(['제3조 별도 기준: 함께 확인할 원문.'] if route=='batch' else []),
        *([f'제{i}조 참고 사항: '+(target_text if i==10 else f'참고 절차 {i}.') for i in range(3,11)] if route=='context' else [])])
    raw = source(tmp_path / 'raw.sqlite', [('d', '모의승인규정', texts)])
    with sqlite3.connect(raw) as db:
        if nested:
            from lawrag.core.structure.viewer import annotate_coordinate_scopes
            nodes=[{'id':i,'parent':parent,'family':family,'surface':surface,'title':'', 'block':i,'span':[i,hi]}
                for i,parent,family,surface,hi in [(0,None,'kr_article','제1조',3),
                    (1,0,'circled','①',2),(2,0,'circled','②',3),
                    (3,None,'kr_article','제2조',4),(4,None,'kr_article','제3조',5)]]
            annotate_coordinate_scopes(nodes,'law')
            db.execute('DELETE FROM source_unit')
            for node in nodes:
                db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d',str(node['id']),
                    str(node['parent']) if node['parent'] is not None else None,json.dumps(node,ensure_ascii=False)))
        else:
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
            self.reference_calls = 0

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
                if view['sources'] and not read_target and route not in ('batch','missing','failure','chain'):
                    wanted='제3조' if route=='chain' and any('제3조에 따른 승인 기준' in s['text'] for s in view['sources']) else '제10조' if route=='context' else '제2조'
                    cards=view['references']['dependency_cards']
                    candidates=[c for c in cards if c.get('read_action') and wanted in c['target']['heading']]
                    if candidates:
                        if route=='context':assert len(cards)==9
                        if nested:
                            headings={c['target']['heading'].split()[0] for c in cards}
                            assert headings==({'제2조'} if route=='narrow' else {'제2조','제3조'})
                        c=candidates[0];self.choices.append('READ_LINK')
                        return wire({'choice':'READ','selections':[{'target':c['read_action'],'issue_id':'Q1',
                            'missing_need':'필요한 연결 원문 확인','relation':'DEPENDENCY','source_ref':view['sources'][0]['id']}]})
                if route=='batch' and self.link_selected and not read_target:
                    cards=[c for c in view['references']['dependency_cards'] if c.get('read_action')]
                    assert len(cards)==2
                    self.choices.append('READ_BATCH')
                    return wire({'choice':'READ','selections':[{'target':c['read_action'],'issue_id':'Q1',
                        'missing_need':'같은 선택 범위의 두 연결 원문 확인','relation':'DEPENDENCY',
                        'source_ref':view['sources'][0]['id']} for c in cards]})
                if view['sources'] and not read_target and (not self.link_selected or route=='chain'):
                    anchor = '제2조' if route=='chain' and self.link_selected else '제1조'
                    options=[o for o in view['tool_options'] if o['choice']=='FOLLOW_CONNECTION' and anchor in o['label']]
                    if not self.link_selected:
                        assert not view['references']['dependency_cards']
                        assert all(c['connection_preview']['status']=='NOT_SELECTED' for c in view['connection_scope_choices'])
                    if nested:
                        uid='1' if route=='narrow' else '0'
                        option=next(o for o in options if o['selected_scope']['structural_selection']['unit_id']==uid)
                        assert any('별도 업무' in s['text'] for s in view['sources'])
                    else:
                        option=options[0]
                    self.link_selected=True
                    self.choices.append('FOLLOW_CONNECTION')
                    return wire({'choice':'FOLLOW_CONNECTION','target':option['target'],'issue_id':'Q1',
                        'missing_need':'선택한 범위의 연결 확인','relation':'DEPENDENCY',
                        'source_ref':next(s['id'] for s in view['sources'] if anchor in s['heading'])})
                if view['sources'] and not read_target and route in ('missing', 'failure') and self.link_selected and not self.located:
                    option = next(o for o in view['tool_options'] if o['choice'] == 'LOCATE')
                    if route=='failure':
                        assert view['references']['absence_proven'] is False
                        assert any(c['connection_preview']['status']=='FAILED' for c in view['connection_scope_choices'])
                        assert not any(o['choice']=='FOLLOW_CONNECTION' and '제1조' in o['label'] for o in view['tool_options'])
                    else:
                        assert view['references']['absence_proven'] is False
                    self.located = True
                    self.choices.append('LOCATE')
                    return wire({'choice': 'LOCATE', 'target': option['target'], 'issue_id': 'Q1',
                        'missing_need': '알려진 적용 범위 조문 조회', 'relation': 'DIRECT', 'source_ref': None,
                        'structure_filter': {'coordinate': '제2조', 'title': '', 'coordinate_scope': 'body'}})
                if not view['sources'] or not read_target and self.located:
                    wanted = '제1조' if not view['sources'] else '제2조'
                    candidate = next(c for c in view['read_candidates'] if c.get('coordinate')==wanted)
                    if gaps:
                        self.target_bound = any(candidate['target'] in g['read_actions'] for g in view['gap_targets'])
                        assert self.target_bound
                    self.choices.append('READ')
                    return wire({'choice': 'READ', 'selections': [{'target': candidate['target'], 'issue_id': 'Q1',
                        'missing_need': '모의 적용 범위 원문 확인', 'relation': 'DIRECT', 'source_ref': None}]})
                self.choices.append('FINISH')
                if route=='batch':
                    assert any('함께 확인할 원문' in s['text'] for s in view['sources'])
                return wire({'choice': 'FINISH', 'basis_refs': [s['id'] for s in view['sources']],
                    'issue_refs': ['Q1'], 'evidence_sufficient': read_target, 'reason': '확보한 원문으로 판단'})
            if phase.startswith('source-reference-law-'):raise AssertionError('Nested reference model must not run')
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

    if route=='failure':
        from semantic_runtime.legal_agent import unit_relations
        def fail(*a,**kw):raise TimeoutError('synthetic connection store timeout')
        monkeypatch.setattr(unit_relations,'catalog',fail)
    transport = Transport()
    profile = json.loads((root / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    assert profile['candidate_navigation']['small_connection_context'] is False
    profile['candidate_navigation'].update(read_judgment=False,selected_connection_scope=True,small_connection_context=True,answer_first=False,answer_progress_control=False)
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
    assert transport.reference_calls == 0
    expected = (['READ','FOLLOW_CONNECTION','FOLLOW_CONNECTION','FINISH'] if route=='chain' else
        ['READ','FOLLOW_CONNECTION','READ_LINK','FINISH'] if route=='context' else
        ['READ','FOLLOW_CONNECTION','FINISH'])
    assert transport.choices == expected
    app.state.pipeline.store.close()
