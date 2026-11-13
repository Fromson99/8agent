"""r13·r14 (user 2026-11-13): the 대사 table and the "아직 확인하지 못한 내용" line, as a legal reader sees them.

1. ADR-1524 위험관리위원회: 9 table rows were followed by 34 "외규만 — 짝 미정" rows, each with its full read text
   (about 130,000 visible characters). The 외규만 rows now sit in one folded section under the table; the articles
   whose title holds the question's subject word come first and are named above the fold. Every row stays.
2. Field photo: a requested article read only in part was shown as "요청한 구조 선택 중 아직 원문 전체를 전달하지
   못한 항목: external > financial_team > law > …" followed by "이 내용이 담긴 문서나 조문을 알고 계시면 알려
   주세요." The document is named without its storage path, and a part the system has not read yet is offered to
   be read on, not asked of the user.
"""
import re
from types import SimpleNamespace


def source(ident, side, heading, quote):
    return {'selection_id': ident, 'selection_ids': [ident], 'side': side, 'document_id': 'D-' + side + heading,
            'generation_id': 'G', 'source_artifact_hash': 'H', 'label': ident, 'document_name': '위험관리규정' if side == 'internal' else '지배구조법',
            'coordinate_label': heading, 'quote': quote}


def row(label, internal, external, placement=None, words=()):
    value = {'concept_id': None, 'request_issue_id': None, 'label': label, 'definition': '설명', 'scope_reason': '',
             'internal': internal, 'external': external, 'observations': [], 'unresolved': [],
             'opinions': [{'verdict_label': '부합', 'difference': '', 'reason': '이유', 'relation_label': '직접 연결'}]}
    if placement:
        value.update(placement=placement, question_words=list(words))
    return value


def test_the_table_opens_to_its_summary_and_items_and_unrelated_externals_are_set_aside_at_the_bottom():
    """r14 (user photo): "대사표" opens to a summary built from the rows and to the items, each item opens to its
    table; an unpaired external whose title holds a question word stays a numbered "외규만" item, the rest go to
    the bottom in the ordinary answer's unused-source form (title, why, read original marked as not evidence)."""
    from workflow.risk_team_compare_workflow import concept_report as cr
    rows = [row('위원회 구성', [source('I1', 'internal', '내규 제5조', '내규 원문')],
                [source('X1', 'external', '법 제16조', '외규 원문')]),
            row('외규만 — 지배구조법 제21조 위험관리위원회', [], [source('X2', 'external', '법 제21조', '제21조 원문')],
                'UNPAIRED', ['위험관리위원회']),
            row('외규만 — 자본시장법 제4조 증권', [], [source('X3', 'external', '법 제4조', '제4조 원문')], 'UNPAIRED'),
            row('외규만 — 자본시장법 제8조 금융투자업자', [], [source('X4', 'external', '법 제8조', '제8조 원문')], 'UNPAIRED')]
    rows[0]['opinions'][0]['difference'] = '내규는 위원 3인 이상을 정한다. 외규는 과반수 사외이사를 요구한다.'
    for r in rows[1:]:
        r['opinions'] = [{'verdict_label': '짝 미정 — 비교하지 않음', 'difference': '', 'relation_label': '외규에만 있음(짝 미정)',
                          'reason': '표에 짝 지어 넣지 못한 이유: 대사표 행 묶기에서 어느 항목에도 묶지 않음.'}]
    table = {'question': '위험관리위원회의 구성과 운영에 관한 외부규정과 내부규정을 비교해줘', 'as_of': '2026-11-13',
             'unresolved': [], 'rows': rows,
             'side_answers': {'internal': [{'question': '위험관리위원회 찾아줘', 'answer': '내규 답', 'purpose': 'QUESTION'},
                                           {'question': '외규 대응 찾아줘', 'answer': '이어 찾은 답', 'purpose': 'FOLLOWUP'}],
                              'external': [{'question': '위험관리위원회 찾아줘', 'answer': '외규 답', 'purpose': 'QUESTION'}]}}
    html = cr.render(table)
    groups = re.findall(r'<details data-genos-compare-(?:table|unused).*?\n</div>\n</details>(?=\n\n|$)', html, flags=re.S)
    assert len(groups) == 2, groups
    table_group, aside = groups
    titles = re.findall(r'<summary[^>]*>(.*?)</summary>', table_group)
    assert titles == ['대사표 · 2개 항목', '1. 위원회 구성 · 부합', '2. 외규만 — 지배구조법 제21조 위험관리위원회 · 짝 미정 — 비교하지 않음'], titles
    assert 'open' not in ''.join(re.findall(r'<details[^>]*>', html)) and '\n\n' not in table_group
    # Each side's ordinary answer first, in plain view; the 대사's own follow-up read folded at the end.
    assert html.index('내규에서 찾은 내용') < html.index('내규 답') < html.index('외규에서 찾은 내용') < html.index(table_group)
    assert html.index('이어 찾은 답') > html.index(aside) and '대사 중 이어서 찾은 내용 · 1건' in html
    # Inside the 대사표, before the items: the summary (count, each item's verdict, both sides' articles, first sentence).
    head = table_group[:table_group.index('data-genos-compare-item')]
    assert '<p><strong>요약</strong></p>' in head and '내규·외규를 2개 항목으로 나눠 대조했습니다: 부합 1, 짝 미정 1.' in head
    assert '외규 원문 2건은 맨 아래' in head and '내규 위험관리규정 내규 제5조 / 외규 지배구조법 법 제16조' in head
    assert '내규는 위원 3인 이상을 정한다.' in head and '과반수 사외이사' not in head
    for quote in ('내규 원문', '외규 원문', '제21조 원문', '과반수 사외이사'):
        assert quote in table_group[len(head):], quote
    titles = re.findall(r'<summary[^>]*>(.*?)</summary>', aside)
    assert titles == ['읽었지만 대사표에 넣지 않은 외규 원문 · 2건', '1. 자본시장법 제4조 증권', '2. 자본시장법 제8조 금융투자업자'], titles
    for quote in ('제4조 원문', '제8조 원문'):
        assert quote in aside and html.count(quote) == 1
    assert '대사표에 넣지 않은 이유: 대사표 행 묶기에서 어느 항목에도 묶지 않음' in aside and '읽은 원문 (대사 근거 아님)' in aside


def test_a_stopped_comparison_also_lists_its_items_before_the_folds():
    from workflow.risk_team_compare_workflow import concept_report as cr
    table = {'question': '질문', 'as_of': None, 'unresolved': [],
             'final_answer': [{'text': '멈추기 전까지의 답입니다.', 'internal': [source('I1', 'internal', '내규 제5조', '내규 원문')],
                               'external': []}],
             'rows': [row('위원회 구성', [source('I1', 'internal', '내규 제5조', '내규 원문')], [])]}
    html = cr.render(table)
    part = html[html.index('항목별 대사표 — 멈추기 전까지 확인한 내용 · 1개 항목'):]
    assert part.index('내규·외규를 1개 항목으로 나눠 대조했습니다') < part.index('data-genos-compare-item')
    assert '1. 위원회 구성 · 부합' in part


def test_a_local_raw_folder_does_not_show_in_the_document_name():
    from workflow.risk_team_compare_workflow import concept_report as cr
    assert cr.document_name('RAW > internal > risk_team > 위험관리기준시행세칙 > photo-20261020-r2 > 위험관리기준시행세칙') == '위험관리기준시행세칙'
    assert cr.document_name('external > financial_team > law > 금융투자업규정') == '금융투자업규정'


def test_only_the_subject_words_of_the_question_mark_an_article_related():
    from workflow.risk_team_compare_workflow import concept_report as cr
    assert cr.question_words('위험관리위원회의 구성과 운영에 관한 외부규정과 내부규정을 비교해줘') == {'위험관리위원회'}
    assert cr.question_words('건전성비율(순자본비율 등) 관련 외부규정과 내부규정을 비교해줘') == {'건전성비율', '순자본비율'}
    assert cr.question_words('유동성비율 관련한 외부규정과 내부 규정은 어떻게 되나요?') == {'유동성비율'}


def test_a_part_not_read_yet_names_the_document_without_its_storage_path(monkeypatch):
    from semantic_runtime.legal_agent import structure_selection as ss, structure_query
    matcher = SimpleNamespace(documents={'d': 'external > financial_team > law > 금융회사의 지배구조에 관한 법률 시행령'})
    monkeypatch.setattr(structure_query, 'node_label', lambda m, did, uid: {'coordinate': {'u2': '제6조제2항', 'u3': '제6조제3항'}[uid]})
    values = ss.selection_limitations(matcher, [
        {'document_id': 'd', 'remaining_unit_ids': ['u2', 'u3'], 'membership_gaps': [{'n': 9, 'unit': '항'}]}])
    assert values[0] == ('금융회사의 지배구조에 관한 법률 시행령 제6조제2항, 제6조제3항 — 요청하신 범위에 들어 있지만 '
                         '아직 원문 전체를 읽지 못한 부분입니다')
    assert values[1].startswith('금융회사의 지배구조에 관한 법률 시행령 9항 — 저장된 조문 목록에서 찾지 못한 번호입니다')
    assert all('>' not in v and 'financial_team' not in v for v in values)


def guided(execution_limits=(), known_shortages=()):
    from semantic_runtime.contracts import digest
    from semantic_runtime.legal_agent import guided_answer as ga
    assessment = {'claims': [{'claim_id': 'C1', 'text': '위험관리위원회는 이사회 안에 둡니다.'}],
                  'guided_reply': {'schema_version': ga.VERSION, 'questions': [], 'needs_guidance': True,
                                   'execution_limits': list(execution_limits), 'known_shortages': list(known_shortages)}}
    return ga.render(assessment, {'assessment_hash': digest(assessment)})


def test_a_part_not_read_yet_is_offered_to_read_on_not_asked_of_the_user():
    text = guided(execution_limits=['시행령 제6조제2항 — 요청하신 범위에 들어 있지만 아직 원문 전체를 읽지 못한 부분입니다'])
    assert '아직 확인하지 못한 내용: 시행령 제6조제2항' in text
    assert '이어서 확인해 달라고 하시면 남은 부분을 계속 읽겠습니다.' in text and '알고 계시면' not in text
    # A source the answer could not find is still something the user may know.
    text = guided(known_shortages=[{'missing_target': '위원회 운영 세부 준칙'}])
    assert '이 내용이 담긴 문서나 조문을 알고 계시면 알려 주세요.' in text and '이어서 확인해 달라고' not in text
