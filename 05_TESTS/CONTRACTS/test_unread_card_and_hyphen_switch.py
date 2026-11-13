"""미확인 조문은 화면의 접기 칸으로만, 하이픈 조문 번호는 GENOS_HYPHEN_ARTICLES로 켜고 끈다 (2026-11-11)."""
import importlib.util
import pathlib

import pytest

from semantic_runtime.legal_agent import article_surface as a, guided_answer as g, guided_navigation as gn

WORKFLOW = pathlib.Path(a.__file__).resolve().parents[3]/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'


def workflow():
    spec = importlib.util.spec_from_file_location('genos_rag_chat_under_test', WORKFLOW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(i, origin='제2-5조 주식의 처분', **more):
    return {'unread_id': 'U'+str(i), 'from_label': origin, 'target_label': '제7-%d조(미매각자산)' % i, 'target_document': '인수위험관리준칙',
            'relation': 'MUTATIS', 'relation_text': '이 조문을 준용하는 조문', 'reason': '지금은 필요 없어서', 'judged_unneeded': True,
            'used_as_evidence': False, 'text': '원문', 'section': '', 'section_level': '절', **more}


def test_answer_body_has_one_line_instead_of_the_list():
    lines = g.unread_paragraphs({'unread_connections': [row(1), row(2)], 'unread_connection_total': 5})
    assert len(lines) == 1 and '5건' in lines[0] and '미확인 조문' in lines[0] and '제7-1조' not in lines[0]
    assert g.unread_paragraphs({'unread_connections': []}) == []


def body(rows, total=None):
    reply = {'unread_connections': rows, 'unread_connection_total': total or len(rows), 'questions': []}
    return {'assembly': {'term_agent': {'guided_reply': reply}}}


def cards(monkeypatch, rows, total=None):
    module = workflow()
    monkeypatch.setattr(module, '_guided_reply_text', lambda _body: '답변')
    return module._unread_cards(body(rows, total))


def test_card_title_is_document_and_article(monkeypatch):
    html = cards(monkeypatch, [row(5)])
    assert '인수위험관리준칙 · 제7-5조(미매각자산)</summary>' in html
    assert '제2-5조 주식의 처분에 연결된' in html and '이 조문을 준용하는 조문' in html


def test_quoted_document_label_moves_to_the_title(monkeypatch):
    html = cards(monkeypatch, [row(5, target_label='「투자위험관리준칙」 제2-10조(사후관리)', target_document='')])
    assert '투자위험관리준칙 · 제2-10조(사후관리)</summary>' in html


def test_cards_are_limited_per_origin_and_in_total(monkeypatch):
    if hasattr(workflow(), '_unread_card_limit'):
        # 2026-11-12 user: every unread card by default; GENOS_UNREAD_CARD_LIMIT=N caps them.
        rows = [row(i, origin='출발'+str(i % 5)) for i in range(40)]
        monkeypatch.delenv('GENOS_UNREAD_CARD_LIMIT', raising=False)
        html = cards(monkeypatch, rows, 40)
        assert html.count('data-genos-unread="true"') == 40 and '미확인 조문 · 40건' in html and '그 밖에' not in html
        monkeypatch.setenv('GENOS_UNREAD_CARD_LIMIT', '10')
        html = cards(monkeypatch, rows, 40)
        assert html.count('data-genos-unread="true"') == 10 and '그 밖에 30건' in html
        return
    rows = [row(i, origin='출발'+str(i % 5)) for i in range(40)]
    html = cards(monkeypatch, rows, 40)
    assert html.count('data-genos-unread="true"') == 10 and '미확인 조문 · 10건' in html and '그 밖에 30건' in html
    html = cards(monkeypatch, [row(i) for i in range(9)], 9)
    assert html.count('data-genos-unread="true"') == 3 and '그 밖에 6건' in html


def test_unread_articles_closest_to_the_question_come_first():
    rows = [{'target_label': '제1조(목적)', 'text': ''}, {'target_label': '제7-5조(미매각자산 보유기한)', 'text': ''}]
    assert g.rank_unread(rows, '미매각자산 보유기한은 언제까지인가요?')[0]['target_label'].startswith('제7-5조')


def test_hyphen_articles_count_by_default(monkeypatch):
    monkeypatch.delenv('GENOS_HYPHEN_ARTICLES', raising=False)
    assert a.article_pattern().match('제7-5조') and a.article_pattern().match('제71조의2')
    assert a.branched_article_pattern().fullmatch('제7-5조')


def test_switch_off_restores_the_former_patterns(monkeypatch):
    monkeypatch.setenv('GENOS_HYPHEN_ARTICLES', 'off')
    assert not a.article_pattern().match('제7-5조') and a.article_pattern().match('제71조')
    assert not a.branched_article_pattern().fullmatch('제7-5조')
    assert not gn.cited_in_range('제7-1조 내지 제7-9조', '제7-5조')


@pytest.mark.parametrize('hyphen,reads,expected', [('on', 'off', False), ('on', 'on', True), ('off', 'on', False)])
def test_section_reads_need_their_own_switch(monkeypatch, hyphen, reads, expected):
    monkeypatch.setenv('GENOS_HYPHEN_ARTICLES', hyphen)
    monkeypatch.setenv('GENOS_HYPHEN_SECTION_READS', reads)
    assert bool(a.section_read_pattern().match('제7-5조')) is expected
    assert a.section_read_pattern().match('제71조')


def test_section_reads_are_off_by_default(monkeypatch):
    monkeypatch.delenv('GENOS_HYPHEN_SECTION_READS', raising=False)
    assert not a.section_reads_on()


def test_range_citation_with_hyphen_numbers(monkeypatch):
    monkeypatch.delenv('GENOS_HYPHEN_ARTICLES', raising=False)
    assert gn.cited_in_range('제7-1조 내지 제7-9조를 준용', '제7-5조')
    assert not gn.cited_in_range('제7-1조 내지 제7-3조를 준용', '제7-5조')
