"""Synthetic title safety and real search/reader contracts, without provider calls."""
from types import SimpleNamespace as S
from copy import deepcopy
import pytest
from semantic_runtime.legal_agent.law_title_hints import hints
from semantic_runtime.legal_agent import law_candidates as lc, law_navigation as ln
from semantic_runtime.legal_agent.source_recall import SourceRecall
from test_law_grouped_navigation import session, enable, decide
from test_unit_fulltext_adaptive_read import tree
from conftest import term_glossary

def value(data,action,target=None,queries=()):
    v=decide(data,action,target)
    v.update(expected_state_version=data['state_version'],law_decisions=[],branch_decisions=[],queries=list(queries))
    return v


def catalogue():
    docs={'base':'상속세 및 증여세법','decree':'상속세 및 증여세법 시행령',
          'finance':'자본시장과 금융투자업에 관한 법률', 'startup':'중소기업창업 지원법 시행령'}
    return S(documents=docs,document_context={d:{'document_role':'body'} for d in docs},
             document_aliases={'finance':['자본시장법']})


@pytest.mark.parametrize('query,did,kind',[
    ('「상속세 및 증여세법 시행령」 제49조는?', 'decree','EXACT_TITLE'),
    ('상속세및증여세법시행령제49조', 'decree','EXACT_TITLE'),
    ('자본시장법의 내용', 'finance','REGISTERED_ALIAS'),
    ('상증세법 시행령 제49조 1항 구조', 'decree','DERIVED_ABBREVIATION'),
    ('중소기업창업 지원에 관한 시행령', 'startup','PARTIAL_TITLE')])
def test_title_offsets_and_match_provenance(query,did,kind):
    m=catalogue();v=hints(query,m,m.documents);first=v['candidates'][0]
    assert first['document_id']==did and first['match_kind']==kind
    s=first['question_span'];assert query[s['start']:s['end']]==s['text']
    for s in first['title_matches']:assert m.documents[did][s['start']:s['end']]==s['text']
    assert first['identity_confirmed']==(kind in ('EXACT_TITLE','REGISTERED_ALIAS'))
    assert not first['citation_eligible'] and not v['citation_eligible']


@pytest.mark.parametrize('question',['법 시행령은?', '제49조 제1항은?', '재무제표 제출 기한은?', '승인 방법을 알려줘'])
def test_no_spurious_title_match_for_generic_or_body_terms(question):
    m=catalogue();assert hints(question,m,m.documents)['candidates']==[]


def test_acl_filtered_before_matching_and_ambiguity_kept():
    m=catalogue();m.documents['private']='상속세 및 증여세법 시행령 내부 주석'
    m.document_context['private']={'document_role':'body'}
    v=hints('상속세 및 증여세법 시행령 내부 주석',m,['decree'])
    assert [c['document_id'] for c in v['candidates']]==['decree']
    m.documents['version2']=m.documents['decree'];m.document_context['version2']={'document_role':'body'}
    v=hints('상증세법 시행령 제49조',m,['decree','version2'],limit=1)
    assert v['total_candidates']==2 and v['omitted_candidates']==1
    assert all(not c['identity_confirmed'] for c in v['candidates'])


def test_exact_alias_does_not_change_store_or_include_annex():
    m=catalogue();before=deepcopy(m.document_aliases)
    m.document_context['decree']={'document_role':'annex'}
    assert not any(c['document_id']=='decree' for c in hints('상증세법 시행령',m,m.documents)['candidates'])
    assert m.document_aliases==before


def start(native, mode, question):
    s=native.sources;enable(s,structure_first=True,selectable_search=True,
                           investigation_control=True,completion_contract=True,batch_selected_pages=True)
    s.entry_search={'mode':mode};s.context.request['question']=question
    rec=SourceRecall(s).prepare()
    return ln.Investigation(s,question,rec,None,120,None,None),rec


def test_fulltext_can_be_first_and_then_structure_tool(session,monkeypatch):
    native,idx=session;calls=[];original=idx.law_groups_page
    def counted(*a,**kw):calls.append('body');return original(*a,**kw)
    monkeypatch.setattr(idx,'law_groups_page',counted)
    inv,rec=start(native,'FULLTEXT','승인')
    assert rec['discovery_mode']=='fulltext' and calls
    data,actions=inv.view()
    assert inv.p['window']=='search' and data['laws']
    assert {a['action'] for a in actions.values()} >= {'SEARCH_STRUCTURE','RESEARCH','SEARCH_BODY'}
    target=data['laws'][0]['structure_search_action'];d=value(data,'SEARCH_STRUCTURE',target,['제1조'])
    inv.validate(d,data,actions);inv.execute(d,data,actions)
    assert inv.p['window']=='structure'


def test_structure_then_explicit_research_uses_body_without_forced_fallback(session,monkeypatch):
    native,idx=session;original=idx.law_groups_page
    monkeypatch.setattr(idx,'law_groups_page',lambda *a,**k:pytest.fail('unselected body search'))
    inv,rec=start(native,'STRUCTURE','모의승인규정')
    assert rec['discovery_mode']=='structure'
    data,actions=inv.view();target=next(k for k,v in actions.items() if v['action']=='RESEARCH')
    d=value(data,'RESEARCH',target,['승인']);inv.validate(d,data,actions);inv.execute(d,data,actions)
    native.sources.law_search_queries=['승인'];monkeypatch.setattr(idx,'law_groups_page',original)
    following=SourceRecall(native.sources).prepare()
    resumed=ln.Investigation(native.sources,'모의승인규정',following,None,120,deepcopy(inv.p),None)
    assert following['discovery_mode']=='fulltext' and resumed.p['window']=='search'
    resumed.view()  # scoped FTS and menu contracts must both remain usable


def test_optional_mode_prompt_and_legacy_prompt_are_distinct():
    assert '반드시 먼저 거칠 필요는 없다' in ln.SELECTABLE_SYSTEM
    assert '구조 조회 실패를 전체 본문 검색으로 우회하지 않는다' not in ln.SELECTABLE_SYSTEM
    assert '구조 조회 실패를 전체 본문 검색으로 우회하지 않는다' in ln.SYSTEM

def test_folder_display_names_are_not_law_titles():
    m=catalogue();title=m.documents['decree']
    m.document_context['decree']['document_title']=title
    m.documents['decree']='external > financial_team > law > '+title
    for question,kind in [('상증세법 시행령 제49조','DERIVED_ABBREVIATION'),(title+' 제49조','EXACT_TITLE')]:
        row=hints(question,m,['decree'])['candidates'][0]
        assert row['title']==title and row['match_kind']==kind
    assert hints('financial_team',m,['decree'])['candidates']==[]
    del m.document_context['decree']['document_title']
    assert hints(title,m,['decree'])['candidates']==[]
