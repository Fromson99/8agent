"""Photo regression: packet markers and independent graph-style disclosure blocks."""
from copy import deepcopy
from html import escape
from html.parser import HTMLParser
import re

import pytest
from markdown_it import MarkdownIt

import test_comparison_readable_report as fixture
from workflow.contracts import digest
from workflow.risk_team_compare_workflow import concept_report, finalize
from semantic_runtime.chat_adapter import views


class Disclosures(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.parents = []
        self.summaries = []

    def handle_starttag(self, tag, attrs):
        if tag == 'details':
            self.parents.append(tuple(self.stack))
            assert 'open' not in dict(attrs)
        if tag == 'summary':
            self.summaries.append(tuple(self.stack))
        if tag not in {'br', 'img', 'hr', 'input', 'meta', 'link'}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack[-1] == tag, (tag, self.stack)
        self.stack.pop()


@pytest.mark.parametrize('marker', ['(C25)', '(C42, C99)', '( C91 ; C36 )',
                                  '（C38）', '[C25](C42)[C99]', '[C25–C42]'])
def test_photo_parenthesized_packet_ids_only_change_generated_display(marker):
    state, body, by = fixture.example()
    value = state['finalization']['value']
    value['paragraphs'][0]['text'] = '승인해야 합니다'+marker+'. 조건을 확인합니다.'
    value['unresolved'] = ['예외 확인'+marker+' 필요']
    state['finalization']['value_hash'] = digest(value)
    before = deepcopy((state, by))
    result = finalize.apply(state, body, by)
    text = result['answer']['text']
    assert marker not in text
    assert '승인해야 합니다. 조건을 확인합니다.' in text
    assert '예외 확인' in text and '필요' in text
    assert '〔내규 1〕' in text and '〔외규 1〕' in text
    assert result['comparison_table']['final_answer'][0]['text'] == value['paragraphs'][0]['text']
    assert (state, by) == before


@pytest.mark.parametrize('final_answer', [True, False])
def test_disclosures_use_general_question_graph_block_structure(final_answer):
    state, body, by = fixture.example()
    table = finalize.apply(state, body, by)['comparison_table']
    if not final_answer:
        table.pop('final_answer')
    # Every literal coordinate, version boundary and quote remains inside a
    # visible cell when opened; no disclosure is nested inside another or a td.
    raw = concept_report.render(table)
    rendered = MarkdownIt('commonmark', {'html': True}).render(views()._for_markdown(raw))
    parsed = Disclosures(); parsed.feed(rendered)
    assert parsed.parents and all(parent == () for parent in parsed.parents)
    assert all(parent == ('details',) for parent in parsed.summaries)
    assert not parsed.stack
    graph = views()._judgment_graph_html({'html': '<p>그래프</p>'})
    opening = re.search(r'(<details[^>]*>\n<summary[^>]*><strong>)', graph).group(1)
    assert opening in raw
    assert len(re.findall(r'^<details\b', raw, re.M)) == len(parsed.parents)
    for source in by.values():
        assert escape(source['text'], quote=True).replace('\n', '<br>') in raw
    assert '<th>내규 출처·원문</th><th>외규 출처·원문</th><th>검토 의견</th>' in raw


def test_literal_packet_like_codes_survive_in_question_and_exact_quotes():
    state, body, by = fixture.example()
    table = finalize.apply(state, body, by)['comparison_table']
    table['question'] = '분류 (C25)와 [C99]의 차이는?'
    table['final_answer'][0]['internal'][0]['quote'] = '원문 (C25) [C99] C91 [1]'
    table['final_answer'][0]['text'] = '제품 C25, [C25A], (C25A)는 보존합니다. (C25)'
    before = deepcopy(table)
    raw = concept_report.render(table)
    assert '질문: 분류 (C25)와 [C99]의 차이는?' in raw
    assert '원문 (C25) [C99] C91 [1]</blockquote>' in raw
    assert '제품 C25, [C25A], (C25A)는 보존합니다.' in raw
    assert '보존합니다. (C25)' not in raw
    assert table == before
