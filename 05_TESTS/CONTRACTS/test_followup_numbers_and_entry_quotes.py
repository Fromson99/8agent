"""2026-11-12 사용자: 읽었지만 근거로 안 쓴 원문은 이유와 함께 다 보여주고, 미확인 조문도 다 보여주되(워크플로우 설정),
"1, 3번 더 읽어줘"처럼 번호로 이어서 읽게. 첫 단계 인용은 따옴표·공백 차이만 맞추고(ADR-1518 RISK-EDGE-001/014),
위임받은 하위 규정·법령명 없는 시행령 조문·"용어(약칭)" 약칭도 읽게 (ADR-1518 RISK-EDGE-010/011/018/020)."""
import importlib.util
import pathlib

from semantic_runtime.legal_agent import declared_names as dn
from semantic_runtime.legal_agent import guided_answer as g
from semantic_runtime.legal_agent import guided_navigation as gn
from semantic_runtime.legal_agent import memory_methods as mm
from semantic_runtime.legal_agent import request_entry as re_

WORKFLOW = pathlib.Path(g.__file__).resolve().parents[3]/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
QUESTION = '외규: 당사(종투사 아님)에는 "정상" 콜론 3,000억원과 "요주의"로 분류된 환매조건부매수(RP) 200억원이 있습니다.'


def workflow():
    spec = importlib.util.spec_from_file_location('genos_rag_chat_followup', WORKFLOW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quote_marks_and_spacing_only_map_to_the_question_span():
    assert re_.exact_span('정상 콜론 3,000억원', QUESTION) == '"정상" 콜론 3,000억원'
    assert re_.exact_span('요주의로 분류된 환매조건부매수(RP) 200억원', QUESTION) == '"요주의"로 분류된 환매조건부매수(RP) 200억원'
    assert re_.exact_span('당사(종투사 아님)', QUESTION) == '당사(종투사 아님)'
    assert re_.exact_span('정상 콜론 5,000억원', QUESTION) is None          # a different number is not a copy
    assert re_.exact_span('원', QUESTION) == '원'                            # a literal copy stays as before
    assert re_.exact_span('정상1', '"정상" 1과 정상 1') is None                  # two places once marks/spaces drop: no guess
    assert re_.exact_span('', QUESTION) is None


def test_entry_guidance_names_the_part_for_legal_users():
    text = re_.entry_guidance('fact quote outside current request: 회수의문으로 분류된 자산')
    assert "'회수의문으로 분류된 자산'" in text and '원문 조사를 시작하지 않았습니다' in text and 'quote' not in text
    assert '모델' not in re_.entry_guidance('other failure')


def test_terms_a_read_article_hands_to_a_lower_rule():
    text = ('① 법 제15조제2항에서 "대통령령으로 정하는 금액"이란 금융위원회가 정하여 고시하는 단일거래금액이 '
            '자기자본의 100분의 5에 해당하는 금액 또는 50억원 중 적은 금액을 말한다. ② 이 조는 시행일부터 적용한다.')
    assert gn.delegated_terms(text) == ['단일거래금액', '자기자본']
    assert gn.delegated_terms('자본적정성 비율은 금융위원회가 정하여 고시하는 바에 따라 산정한다.') == ['자본적정성']
    assert gn.delegated_terms('이 조는 공포한 날부터 시행한다.') == []


def sources():
    return [{'source_id': 's1', 'document_id': 'd1', 'document_name': 'external > 상법', 'heading': '제340조의2'},
            {'source_id': 's2', 'document_id': 'd1', 'document_name': 'external > 상법', 'heading': '제434조'},
            {'source_id': 's3', 'document_id': 'd2', 'document_name': 'external > 조세특례제한법', 'heading': '제16조의2'},
            {'source_id': 's4', 'document_id': 'd2', 'document_name': 'external > 조세특례제한법', 'heading': '제16조의3'}]


def test_followup_block_numbers_unused_originals_then_unread_connections():
    options = [{'id': 'S1', 'source_id': 's1'}, {'id': 'S2', 'source_id': 's2'}, {'id': 'S3', 'source_id': 's3'}]
    value = {'unused_notes': [{'original_ref': 'S1', 'reason': '부여 근거 조문으로 인용만 됐고 과세 요건은 조특법에 있어서'},
                              {'original_ref': 'S3', 'reason': '근거로 쓴 조문에 단 메모'}]}
    result = {'claims': [{'source_ids': ['s3'], 'span_receipts': [{'source_id': 's3'}]}],
              'guided_reply': {'unread_connections': [{'unread_id': 'U1', 'target_label': '제16조의4', 'document_id': 'd2',
                                                       'source_id': 's9', 'unit_id': '7'}]}}
    out = g.followup_block(value, options, sources(), [sources()[3]], result)
    assert [(r['no'], r['source_id'], r['reason_origin']) for r in out['unused_sources']] == [
        (1, 's1', 'MODEL_NOTE'), (2, 's2', 'SYSTEM_RULE'), (3, 's4', 'SYSTEM_RULE')]
    assert out['unused_sources'][0]['reason'].startswith('부여 근거') and out['unused_sources'][2]['reason'] == g.WITHHELD_REASON
    assert out['unused_sources'][1]['reason'] == g.NO_NOTE_REASON and out['unused_notes_on_cited'] == ['S3']
    assert [(r['no'], r['kind']) for r in out['followup_reads']] == [(1, 'READ_NOT_USED'), (2, 'READ_NOT_USED'), (3, 'READ_NOT_USED'), (4, 'UNREAD_CONNECTION')]
    assert result['guided_reply']['unread_connections'][0]['no'] == 4
    assert out['followup_reads'][3]['identity'] == {'document_id': 'd2', 'source_id': 's9', 'unit_id': '7'}


def test_answer_body_says_how_to_continue_by_number():
    reply = {'unread_connections': [{'target_label': 'x'}], 'unread_connection_total': 3,
             'unused_sources': [{'no': 1}], 'followup_reads': [{'no': 1}]}
    line = g.unread_paragraphs(reply)[0]
    assert line.startswith('확인하지 않은 연결 조문 3건') and '근거로 쓰지 않은 원문 1건' in line and '번호로 말씀하시면' in line
    assert g.unread_paragraphs({'unused_sources': [{'no': 1}], 'followup_reads': [{'no': 1}]})[0].startswith('읽었지만')
    assert '미확인 조문' in g.unread_paragraphs({'unread_connections': [{}], 'unread_connection_total': 2})[0]


def test_numbered_follow_up_reads_the_chosen_locations():
    reply = {'followup_reads': [{'no': 1, 'read_id': 'Fa', 'kind': 'READ_NOT_USED', 'label': '상법 · 제340조의2',
                                 'identity': {'document_id': 'd1', 'source_id': 's1'}},
                                {'no': 2, 'read_id': 'Fb', 'kind': 'UNREAD_CONNECTION', 'label': '제16조의4',
                                 'identity': {'document_id': 'd2', 'source_id': 's9', 'unit_id': '7'}}]}
    parts = {'ASSESS': {'payload': {'guided_reply': reply}}}
    reads = gn.continuation_reads(parts, ['Fb'])
    assert reads == [reply['followup_reads'][1]]
    offer = gn.continuation(parts, '2번 더 읽어줘', ['Fb'])
    assert offer['requested_reads'] == ['제16조의4']
    context = {'goals': [{'id': 'G1', 'previous_response': {'guidance': {'numbered_reads': [{'read_id': 'Fa', 'no': 1, 'label': 'x'}]}}}]}
    assert mm.proposed_reads(context, 'G1') == ['Fa']


class Index:
    def rank_page(self, db, terms, allowed, *, cursor=None, limit=16):
        if terms != ['NCR']:
            return {'items': []}
        return {'items': [{'document_id': 'd5', 'source_id': 's5', 'unit_id': '1',
                           'text': '4. 순자본비율(NCR) 위험값을 활용하여 성과보수를 산정하는 경우'},
                          {'document_id': 'd6', 'source_id': 's6', 'unit_id': '2', 'text': '규제자본 요구량(예, NCR 표준방법)'}]}


def test_paren_abbreviation_from_the_corpus():
    pairs = dn.paren_abbreviations(Index(), None, {'s5': {'document_id': 'd5'}}, ['d5', 'd6'], ['ABCP 매입보장약정 NCR 위험액'])
    assert [(a, t) for a, t, _ in pairs] == [('NCR', '순자본비율')]
    assert dn.paren_abbreviations(Index(), None, {}, [], ['순자본비율 위험액']) == []


def body():
    reply = {'unused_sources': [{'no': 1, 'source_id': 'a2', 'reason': '정의만 확인했고 기준은 다른 조문에 있어서'}],
             'unread_connections': [{'no': 2, 'unread_id': 'U1', 'from_label': '제1조', 'target_label': '제9조', 'reason': '필요 없어서',
                                     'relation_text': '인용한 조문', 'used_as_evidence': False, 'text': ''}],
             'unread_connection_total': 1, 'questions': []}
    return {'answer': {'claims': [{'source_ids': ['a1']}]},
            'assembly': {'context': [{'id': 'a1', 'document_name': 'external > financial_team > law > 상법', 'text': '근거 원문'},
                                     {'id': 'a2', 'document_name': 'external > financial_team > law > 상법', 'text': '안 쓴 원문'}],
                         'term_agent': {'guided_reply': reply}}}


def test_unused_cards_show_number_reason_and_text(monkeypatch):
    module = workflow()
    monkeypatch.delenv('GENOS_UNUSED_SOURCE_CARDS', raising=False)
    html = module._unused_cards(body())
    assert '근거로 쓰지 않은 원문 · 1건' in html and '1. 상법' in html and '쓰지 않은 이유: 정의만 확인했고' in html
    assert '안 쓴 원문' in html and '근거 원문' not in html
    monkeypatch.setenv('GENOS_UNUSED_SOURCE_CARDS', 'off')
    assert module._unused_cards(body()) == ''


def test_unread_card_has_its_number_and_how_to_read_it(monkeypatch):
    module = workflow()
    monkeypatch.setattr(module, '_guided_reply_text', lambda _body: '답변')
    html = module._unread_cards(body())
    assert '2. 제9조' in html and '“2번 더 읽어줘”' in html


def test_menu_title_read_needs_a_new_distinctive_word():
    reads = [{'id': 'L1', 'origin': 'LOCATION', 'label': '상법 · 제340조의2 주식매수선택권', 'matched_terms': ['주식매수선택권']},
             {'id': 'L2', 'origin': 'LOCATION', 'label': '상법 · 제1조', 'matched_terms': ['이익']},
             {'id': 'L3', 'origin': 'LOCATION', 'label': '규정 · 제14조', 'matched_terms': ['상장주선인'], 'vector_rank': 2},
             {'id': 'L4', 'origin': 'LOCATION', 'label': '상법 · 제5조', 'matched_terms': ['주식매수선택권'], 'form': True}]
    assert [r['id'] for r in g.menu_title_reads({'next_reads': []}, reads)] == ['L1']
    assert g.menu_title_reads({'next_reads': []}, reads, covered={'주식매수선택권'}) == []
    assert g.menu_title_reads({'next_reads': ['L1']}, reads) == []
