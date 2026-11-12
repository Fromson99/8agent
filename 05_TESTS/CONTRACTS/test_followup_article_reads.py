"""Field 2026-11-11 (MAIN205): 제8-14조 cites 제6-5조·제6-7조 of the same rule, and they were never read.

The first turn did not follow the citation, the follow-up "제6-5조·제6-7조 본문 읽어줘" did not reach the stored
structure, the answer repeated one article three times, and ADR-1496 ended a rewrite failure with HTTP 500.
"""
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace as S

import pytest
from fastapi.testclient import TestClient

from lawrag.core.legal_coordinate import find_coordinates
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime import unit_fulltext
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import guided_answer as g, guided_navigation as gn
from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.shortcut_store import selected_store
from semantic_runtime.navigation_match import SurfaceIndex, norm
from test_document_release import source
from test_guided_answer import ISSUES, SOURCES, execution, value
from test_guided_continue_bounds import BROAD, find, fill
from test_guided_followup_reads import Scripted, calls
from test_legal_agent_double_harness import ROOT, wire
from test_memory_runtime_v2 import command, fit

TITLE = '인수위험관리준칙(20251205)'
P1 = (TITLE + ' 제8-15조(사후관리) 제2항은 리스크관리부서가 매분기 「별첨6」에 따른 PF 사업장 평가 등급을 위험관리집행위원회에 보고하도록 규정하고, '
      '제4항은 PF 사업성평가 \'부실우려 등급\' 사업장 중 연체 발생 사업장의 채권에 대해 연체기간 3개월 도래 시 경공매 착수·6개월 내 완료를 의무화합니다. '
      '그러나 이 조문은 등급 하락 자체를 충당금 적립의 직접적 요건으로 명시하지 않습니다.')
P2 = (TITLE + ' 제8-15조(사후관리) 제2항은 리스크관리부서가 매분기 「별첨6」에 따른 PF 사업장 평가 등급을 위험관리집행위원회에 보고하도록 규정하고, '
      '제4항은 PF 사업성평가 \'부실우려 등급\' 사업장 중 연체 발생 사업장의 채권에 대해 연체기간 3개월 도래 시 경공매 착수·6개월 내 완료를 의무화합니다. '
      '제7항은 제1항 내지 제5항 이외의 사항은 동준칙 제7-7조 제3항을 준용한다고 규정합니다. '
      '그러나 이 조문은 등급 하락 자체를 충당금 적립의 직접적 요건으로 명시하지 않습니다.')
P3 = P2.replace('그러나 이 조문은 등급 하락 자체를 충당금 적립의 직접적 요건으로 명시하지 않습니다.',
                '그러나 이 조문 자체에는 등급 하락을 충당금 적립의 직접적 요건으로 명시하는 규정은 없습니다.')


def point(text, *refs):
    return {'issue_refs': ['Q1'], 'evidence_refs': list(refs) or ['S1'], 'text': text}


def test_field_repeated_paragraphs_become_one():
    rows, dropped = g.collapse_repeats([point(P1, 'S1'), point(P2, 'S2'), point(P3, 'S3')])
    assert [r['text'] for r in rows] == [P3] and len(dropped) == 2
    assert rows[0]['evidence_refs'] == ['S3', 'S1', 'S2'] or set(rows[0]['evidence_refs']) == {'S1', 'S2', 'S3'}


@pytest.mark.parametrize('other', [
    '연체기간 6개월 도래 시 경공매에 착수하여야 합니다.',          # another value
    '연체기간 3개월 도래 시 경공매에 착수하지 않을 수 있습니다.',   # negated
])
def test_a_different_value_or_negation_is_not_a_repeat(other):
    text = '연체기간 3개월 도래 시 경공매에 착수하여야 합니다.'
    rows, dropped = g.collapse_repeats([point(text), point(other)])
    assert len(rows) == 2 and not dropped


def test_may_and_must_are_not_repeats():
    a, b = '부서장은 위원회에 보고할 수 있습니다.', '부서장은 위원회에 보고하여야 합니다.'
    assert len(g.collapse_repeats([point(a), point(b)])[0]) == 2


def test_merged_points_keep_a_new_version_and_drop_the_kept_older_one():
    previous = [{'point_id': 'P1', 'text': P1, 'issue_refs': ['Q1'], 'evidence_refs': ['S1']}]
    value_ = {'kept_points': ['P1'], 'answer_points': [point(P2, 'S2')], 'open_questions': []}
    assert [r['text'] for r in g.merged_points(value_, previous)] == [P2]


def test_range_members_lists_hyphen_articles():
    assert gn.range_members('제2-10조', '제2-13조') == ['제2-11조', '제2-12조']
    assert gn.range_members('제6-5조', '제6-4조') is None
    assert gn.phrase_gap(' 내지 ') == 'RANGE'


def rule_matcher(*locators):
    names = SurfaceIndex()
    names.add(TITLE, 'rule')
    coords, units, sources = {}, {}, {}
    for locator in locators:
        key = 'rule', locator
        coords[key] = find_coordinates(locator)[0].coordinate
        units[key] = {'coordinate_scope': 'body', 'surface': locator}
        sources['rule' + locator] = {'document_id': 'rule', 'unit_id': locator, 'document_name': TITLE}
    return S(document_names=names, structures=SurfaceIndex(), documents={'rule': TITLE}, title_keys={norm(title) for title in [TITLE]},
             stored_coordinates=coords, units=units, sources=sources, _unit_sources=lambda did, uid: [did + uid])


def test_scan_reads_hyphen_citations_with_their_link_kind():
    text = '① 부동산 PF 자산의 관리 및 평가에 대하여는 제6-5조와 제6-7조를 준용한다.'
    matcher = rule_matcher('제8-14조', '제6-5조', '제6-7조')
    source_row = {'document_id': 'rule', 'unit_id': '제8-14조'}
    inv = S(s=S(matcher=matcher, scope={'rule'}, tools=S(sources={'s': source_row}),
                store=S(source=lambda did, bid: {'text': text})), p={})
    out = gn.scan_read_originals(inv, {'s': {'b1'}})
    assert set(out['cited']) == {('rule', '제6-5조'), ('rule', '제6-7조')}
    assert out['contexts'][('rule', '제6-5조')][0]['link'] == 'APPLY'
    assert out['contexts'][('rule', '제6-7조')][0]['link'] == 'APPLY'
    assert out['phrases'][0]['members'] == [('rule', '제6-5조'), ('rule', '제6-7조')]


def named_session():
    matcher = rule_matcher('제6-5조', '제6-7조', '제8-14조')
    return S(s=S(matcher=matcher, scope={'rule'}, tools=S(sources=dict(matcher.sources))))


def test_second_number_of_a_question_uses_the_same_document():
    question = TITLE + ' 제6-5조 또는 제6-7조에 충당금 적립 기준이 포함되어 있는지 알고 계신가요?'
    answer = {'answer_points': [], 'open_questions': [{'uncertainty': '', 'question': question}]}
    rows, notes = g.named_article_reads(named_session(), answer, [], [])
    assert [r['identity']['source_id'] for r in rows] == ['rule제6-5조', 'rule제6-7조']
    assert [n['status'] for n in notes] == ['READ_SCHEDULED', 'READ_SCHEDULED']


def test_all_bare_numbers_of_one_explanation_are_read():
    session = named_session()
    text = TITLE + ' 제8-14조는 자산의 평가에 대해 제6-5조와 제6-7조를 준용한다고 규정합니다.'
    answer = {'answer_points': [{'issue_refs': ['Q1'], 'evidence_refs': ['E'], 'text': text}], 'open_questions': []}
    options = [{'id': 'E', 'source_id': 'rule제8-14조', 'document_id': 'rule'}]
    rows, _ = g.named_article_reads(session, answer, [], [{'source_id': 'rule제8-14조', 'document_name': TITLE}], options)
    assert {r['identity']['source_id'] for r in rows} == {'rule제6-5조', 'rule제6-7조'}


PARTS = {'ASSESS': {'payload': {'claims': [{'text': '제6-5조를 준용합니다.', 'span_receipts': [{'document_id': 'rule'}]},
                                            {'text': '다른 설명', 'span_receipts': [{'document_id': 'other'}]}]}}}


def test_followup_request_lists_the_documents_of_the_previous_answer():
    ask = gn.followup_articles(PARTS, '제6-5조 읽어줘')
    assert [d['document_id'] for d in ask['documents']] == ['rule', 'other']
    assert gn.followup_articles(PARTS, '계속 찾아줘') is None
    assert gn.followup_articles({}, '제6-5조 읽어줘') is None


def navigator(text, matcher, documents=None):
    events = []
    ask = {'utterance': text, 'documents': documents or [{'document_id': 'rule', 'text': ''}]}
    session = S(matcher=matcher, scope={'rule', 'other'}, tools=S(sources=dict(matcher.sources)), followup_articles=ask,
                profile={}, repo=S(event=lambda k, v: events.append((k, v))))
    return S(s=session, p={}), events


@pytest.fixture
def known(monkeypatch):
    monkeypatch.setattr(gn, 'enabled', lambda profile: True)
    monkeypatch.setattr(gn, '_known_reads', lambda inv: {})


def test_user_numbers_resolve_in_the_previous_document(known):
    inv, events = navigator('제6-5조·제6-7조 본문 읽어줘', rule_matcher('제6-5조', '제6-7조'))
    rows = gn.add_user_named_articles(inv)
    assert [r['identity']['source_id'] for r in rows] == ['rule제6-5조', 'rule제6-7조']
    assert [r['identity']['source_id'] for r in inv.s.continuation_reads] == ['rule제6-5조', 'rule제6-7조']
    assert [n['status'] for n in inv.p['cited_read_notes']] == ['READ_SCHEDULED', 'READ_SCHEDULED']
    assert events[0][0] == 'FOLLOWUP_ARTICLES_RESOLVED'
    assert gn.add_user_named_articles(inv) == []  # once per request


def test_missing_number_is_reported_not_guessed(known):
    inv, _ = navigator('제6-9조 읽어줘', rule_matcher('제6-5조'))
    assert gn.add_user_named_articles(inv) == []
    assert inv.p['cited_read_notes'] == [{'mention': '제6-9조', 'status': 'NOT_IN_DOCUMENT'}]
    assert not getattr(inv.s, 'continuation_reads', None)


def test_another_rule_named_by_the_user_is_not_this_documents_article(known):
    inv, _ = navigator('투자위험관리준칙 제6-5조 읽어줘', rule_matcher('제6-5조'))
    assert gn.add_user_named_articles(inv) == []
    assert 'cited_read_notes' not in inv.p


def test_same_rule_word_still_means_this_document(known):
    inv, _ = navigator('그 준칙 제6-5조 읽어줘', rule_matcher('제6-5조'))
    assert [r['identity']['source_id'] for r in gn.add_user_named_articles(inv)] == ['rule제6-5조']


def test_number_in_two_documents_needs_the_previous_answer_to_tell_them_apart(known):
    matcher = rule_matcher('제6-5조')
    matcher.documents['other'] = '다른준칙'
    key = 'other', '제6-5조'
    matcher.stored_coordinates[key] = find_coordinates('제6-5조')[0].coordinate
    matcher.units[key] = {'coordinate_scope': 'body', 'surface': '제6-5조'}
    matcher.sources['other제6-5조'] = {'document_id': 'other', 'unit_id': '제6-5조', 'document_name': '다른준칙'}
    both = [{'document_id': 'rule', 'text': ''}, {'document_id': 'other', 'text': ''}]
    inv, _ = navigator('제6-5조 읽어줘', matcher, both)
    assert gn.add_user_named_articles(inv) == []
    assert inv.p['cited_read_notes'][0]['status'] == 'DOCUMENT_AMBIGUOUS'
    told = [{'document_id': 'rule', 'text': ''}, {'document_id': 'other', 'text': '제6-5조를 준용합니다.'}]
    inv, _ = navigator('제6-5조 읽어줘', matcher, told)
    assert [r['identity']['source_id'] for r in gn.add_user_named_articles(inv)] == ['other제6-5조']


def invoke_sequence(e, replies):
    queue = list(replies)
    def invoke(prompt, data, schema, phase):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return deepcopy(item)
    e.invoke = invoke


def test_a_rewrite_that_fails_returns_the_verified_draft():
    e, _ = execution()
    invoke_sequence(e, [value(open=False), ProposalError('cut off')])
    first = g.assess(e, deepcopy(SOURCES), ISSUES, 'q', [])
    second = g.assess(e, deepcopy(SOURCES) + [{**deepcopy(SOURCES[0]), 'source_id': 'source:2'}], ISSUES, 'q', [])
    assert second['claims'] == first['claims']
    assert second['guided_reply']['rewrite_interrupted'] is True
    assert second['guided_reply']['interruption'] == {'kind': 'MODEL_OUTPUT_INVALID', 'stage': 'ASSESS', 'returned': 'PREVIOUS_DRAFT'}


def test_without_a_draft_only_delivered_originals_are_shown():
    e, _ = execution()
    e.answer_delivered_sources = {'source:1'}
    invoke_sequence(e, [ProposalError('cut off')])
    result = g.assess(e, deepcopy(SOURCES) + [{**deepcopy(SOURCES[0]), 'source_id': 'source:2'}], ISSUES, 'q', [])
    assert [r['source_id'] for r in result['source_excerpt_reply']['sources']] == ['source:1']


@pytest.fixture
def hyphen_tree(tmp_path, term_glossary):
    texts = ['제6-5조 자산의 평가', '① 자산은 매분기 평가하고 충당금을 적립한다.',
             '제6-7조 손실 처리', '① 손실은 즉시 보고하고 충당금을 조정한다.',
             '제6-9조 별도 기준', '① 별도 기준은 위원회가 정한다.',
             '제8-14조 긴급 승인 자산', '① 긴급 승인 예외 자산의 평가에 대하여는 제6-5조와 제6-7조를 준용한다.']
    raw = source(tmp_path / 'raw.sqlite', [('d', '모의인수준칙', texts), ('other', '다른규정', ['별도 원문'])])
    nodes = [('0', None, '제6-5조', 0, 2, '제6-5조'), ('1', '0', '①', 1, 2, '제6-5조제1항'),
             ('2', None, '제6-7조', 2, 4, '제6-7조'), ('3', '2', '①', 3, 4, '제6-7조제1항'),
             ('4', None, '제6-9조', 4, 6, '제6-9조'), ('5', '4', '①', 5, 6, '제6-9조제1항'),
             ('6', None, '제8-14조', 6, 8, '제8-14조'), ('7', '6', '①', 7, 8, '제8-14조제1항')]
    with sqlite3.connect(raw) as db:
        db.execute("DELETE FROM source_unit WHERE document_id='d'")
        for uid, parent, surface, lo, hi, locator in nodes:
            coordinate = find_coordinates(locator)[0].coordinate
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)', ('d', uid, parent, json.dumps({
                'family': 'kr_article' if parent is None else 'circled', 'surface': surface, 'title': '', 'span': [lo, hi],
                'legal_coordinate': coordinate.as_dict(), 'coordinate_scope': 'body',
                'coordinate_key': 'body:' + coordinate.canonical_surface()}, ensure_ascii=False)))
    build_generation(raw, term_glossary, tmp_path / 'built', serving=True)
    gen = tmp_path / 'built/generation'; idx = tmp_path / 'unit-index'
    unit_fulltext.build(gen, gen / 'navigation', idx, workers=1)
    return gen, unit_fulltext.UnitFulltextIndex(idx, json.loads((gen / 'navigation/manifest.json').read_text()))


class Writer(Scripted):
    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        schema = body['response_format']['json_schema']['schema']
        if 'open_questions' in schema.get('properties', {}):
            self.log.append({'turn': self.turn, 'phase': 'answer', 'view': deepcopy(view), 'schema': schema})
            originals = view.get('originals', [])
            citing = next(o['id'] for o in originals if '준용' in o['text'])
            value_ = {'open_questions': [], 'answer_points': [{'issue_refs': find(schema, 'issue_refs')['items']['enum'][:1],
                      'evidence_refs': [citing], 'text': '부동산 PF 자산의 평가에는 다른 조문이 준용됩니다.'}]}
            for name in ('next_reads', 'kept_points'):
                if name in schema['properties']:
                    value_[name] = []
            return wire(value_)
        if view.get('phase') == 'investigate' and schema.get('anyOf') and all('choice' in r.get('properties', {}) for r in schema['anyOf']):
            self.log.append({'turn': self.turn, 'phase': 'investigate', 'view': deepcopy(view), 'schema': schema})
            options = {}
            for branch in schema.get('anyOf', []):
                options.setdefault(branch['properties']['choice'].get('const'), []).append(branch)
            citing_read = '준용' in json.dumps(view.get('sources') or [], ensure_ascii=False)
            if not citing_read and 'READ' in options and view.get('read_candidates'):
                choice = fill(options['READ'][0])
                target = next((r['target'] for r in view['read_candidates'] if '제8-14조' in json.dumps(r, ensure_ascii=False)), view['read_candidates'][0]['target'])
                return wire({**choice, 'selections': [{**choice['selections'][0], 'target': target}]})
            locate = [b for b in options.get('SEARCH', []) if 'structure_filter' in b['properties']]
            if not citing_read and locate:
                return wire({**fill(locate[0]), 'structure_filter': {'coordinate': '제8-14조', 'title': '', 'coordinate_scope': 'body'}})
            if 'ANSWER' in options:
                choice = fill(options['ANSWER'][0])
                if 'basis_refs' in options['ANSWER'][0]['properties']:
                    choice['basis_refs'] = list(options['ANSWER'][0]['properties']['basis_refs']['items']['enum'])
                return wire(choice)
            return wire(fill((options.get('FOLLOW') or next(iter(options.values())))[0]))
        return super().send_once(body=body, ticket=ticket)


def ask(tree, tmp_path, navigation, followup=None):
    gen, idx = tree
    plan = {'relation': 'CONTINUE', 'actions': {}}
    transport = Writer(BROAD, 'authorized', plan); runtime = tmp_path / 'runtime'
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    profile['candidate_navigation'].update(navigation)
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    responses = []
    with TestClient(app) as api:
        request = {'session_id': 's', 'request_id': '1', 'question': BROAD}
        responses.append(api.post('/v1/rag/ask', json=request))
        assert responses[0].status_code == 200, responses[0].text
        if followup:
            db = connect(selected_store(runtime))
            row = db.execute('SELECT id,state FROM goal ORDER BY ordinal DESC LIMIT 1').fetchone()
            transport.target = row['id']; transport.task = json.loads(row['state'])['task']; db.close()
            transport.turn = 2
            responses.append(api.post('/v1/rag/ask', json={**request, 'request_id': '2', 'question': followup}))
            assert responses[1].status_code == 200, responses[1].text
    return transport, responses


def texts_of(transport, turn):
    return [o['text'] for r in calls(transport, turn, 'answer') for o in r['view']['originals']]


def test_first_turn_reads_the_articles_its_evidence_applies(hyphen_tree, tmp_path):
    transport, _ = ask(hyphen_tree, tmp_path, {'guided_action_limit': 6, 'guided_answer_read_rounds': 6, 'guided_answer_brief_rounds': True})
    last = [o['text'] for o in calls(transport, 1, 'answer')[-1]['view']['originals']]
    assert any('매분기 평가' in t for t in last) and any('즉시 보고' in t for t in last)


def test_second_turn_reads_named_numbers_before_the_first_decision(hyphen_tree, tmp_path):
    transport, _ = ask(hyphen_tree, tmp_path, {'guided_action_limit': 6, 'guided_answer_read_rounds': 0, 'guided_answer_brief_rounds': False},
                       followup='제6-9조 본문 읽어줘')
    # Nothing links to 제6-9조: only the number the user gave can reach it.
    assert not any('별도 기준은' in t for t in texts_of(transport, 1))
    first = calls(transport, 2, 'investigate')[0]
    assert [n['status'] for n in first['view']['cited_read_results']] == ['READ_SCHEDULED']
    assert '별도 기준은' in json.dumps(first['view'], ensure_ascii=False)
    assert any('별도 기준은' in t for t in texts_of(transport, 2))


def test_second_turn_with_a_number_no_document_has_reports_it(hyphen_tree, tmp_path):
    transport, _ = ask(hyphen_tree, tmp_path, {'guided_action_limit': 6, 'guided_answer_read_rounds': 0, 'guided_answer_brief_rounds': False},
                       followup='제9-9조 본문 읽어줘')
    first = calls(transport, 2, 'investigate')[0]
    assert first['view']['cited_read_results'] == [{'mention': '제9-9조', 'status': 'NOT_IN_DOCUMENT'}]
