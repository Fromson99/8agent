"""Recorded search locations reach the question writer, without becoming evidence."""
from copy import deepcopy
import pytest
from jsonschema import validate
from semantic_runtime.legal_agent import guided_answer as answer, guided_navigation as nav
from semantic_runtime.legal_agent import completion_contracts as cc, decision_projection as dp
from test_guided_answer import execution, value, ISSUES, SOURCES
from test_unit_fulltext_adaptive_read import tree, session
from test_investigation_completion_adr0678 import inv_for


def selection():
    menu={'previous_searches':[['의무보유 기간']], 'search_queries':['의무보유 기간'],
        'direct_search_scope':{'document_id':'doc1','label':'모의규정'},
        'read_candidates':[{'target':'T2','document':'모의규정','document_id':'doc1',
            'path':'제2조','preview':'미리보기는 답변 근거가 아님'}]}
    return {'issues':ISSUES,'investigation_state':{'guidance_view':nav.research_view(menu)},
        'reference_navigation':{'groups':[{'anchor':{'document_name':'모의규정','heading':'제1조'},
            'target':{'document_name':'모의규정','heading':'제2조'},'direction':'OUTGOING',
            'connections':[{'already_read':False,'witness':'제2조에 따른다'}]}]},
        'investigation_chain':{'steps':[{'action':'SEARCH_BODY','queries':['의무보유 기간'],
            'status':'APPLIED','outcome':{'new_reads':[]}}]}}


def test_final_wire_retains_queries_connection_endpoints_and_actual_read_state():
    s=selection();before=deepcopy(s);e,calls=execution()
    result=answer.assess(e,SOURCES,ISSUES,'질문',[],selection=s)
    wire=answer.wire_input(calls[0][1]);ctx=wire['research_guidance']
    assert ctx['menu_search_queries']==['의무보유 기간']
    assert ctx['available_read_candidates'][0]['path']=='제2조'
    assert 'preview' not in ctx['available_read_candidates'][0]
    assert ctx['connections']==s['reference_navigation']['groups']
    assert ctx['source_locations'][0]['heading']=='제1조'
    assert wire['investigation_chain']==s['investigation_chain']
    assert wire['originals']==[{'id':o['id'],'text':o['text']} for o in cc.evidence_options(SOURCES)]
    assert s==before and len(calls)==1
    answer.assess(e,SOURCES,ISSUES,'질문',[],selection=s)
    assert len(calls)==1 and result['guided_reply']['needs_guidance']


@pytest.mark.parametrize('already_read',[False,True])
def test_connection_read_state_is_not_overridden_by_available_read_option(already_read):
    s=selection();s['reference_navigation']['groups'][0]['connections'][0]['already_read']=already_read
    context=answer.research_context(s,SOURCES)
    assert context['connections'][0]['connections'][0]['already_read'] is already_read
    assert 'status' not in context['available_read_candidates'][0]


@pytest.mark.parametrize('lookup',[
    {'document_id':'doc1','queries':['확인문구'],'offset':0,'total':0,'failure':None},
    {'document_id':'doc1','queries':['확인문구'],'offset':0,'total':2,'failure':{'code':'AMBIGUOUS_COORDINATE'}},
    {},
])
def test_zero_results_failed_lookup_and_unknown_remain_distinct(lookup):
    s=selection();s['structure_catalogue']=lookup
    context=answer.research_context(s,[])
    assert context['structure_lookup']==lookup
    assert context['source_locations']==[]
    assert 'missing_source' not in context


def test_source_question_names_locations_and_remains_unresolved():
    v=value();v['open_questions']=[{'issue_refs':['Q1'],'kind':'SOURCE',
        'uncertainty':'모의규정 제1조에서 연결된 모의규정 제2조는 아직 본문을 읽지 않았습니다.',
        'question':'모의규정 제2조를 이어서 읽어볼까요?'}]
    result=answer.materialize(v,ISSUES,cc.evidence_options(SOURCES),SOURCES)
    rendered=cc.compose(result,answer.plan(result))
    assert v['open_questions'][0]['question'] in rendered['text']
    assert result['gaps'][0]['kind']=='MISSING_SOURCE'
    assert result['gaps'][0]['suggested_action']=='RESEARCH'
    assert result['answer_coverage']=='PARTIAL'


def test_actual_selector_snapshot_and_source_pause_reach_final_without_extra_model(session):
    native,_=session;inv=inv_for(native);inv.modern=True
    native.profile['answer_presentation']=answer.VERSION
    inv.policy.update(guided_loop=True,minimal_input=True)
    native.profile['candidate_navigation']=inv.policy;inv.s.repo.VERSION=6
    data,actions=inv.view();seen=[]
    def invoke(prompt,payload,schema,phase,timeout):
        seen.append(deepcopy(payload))
        response={'choice':'ASK_USER','questions':[{'issue_refs':[data['issues'][0]['id']],
            'kind':'SOURCE','uncertainty':'이번 검색 후보의 본문은 아직 확인하지 않았습니다.',
            'question':'후보의 본문을 이어서 읽어볼까요?'}]}
        validate(response,schema);return response
    inv.invoke=invoke
    with pytest.raises(nav.Pause):dp.choose_read(inv,data,actions,'source-law-navigation-1')
    selected=inv.bounded_result('USER_GUIDANCE_REQUIRED')
    assert selected['investigation_state']['guidance_view']==nav.research_view(seen[0])
    assert selected['investigation_state']['guidance_view']['available_read_candidates']
    e,calls=execution()
    result=answer.assess(e,[],data['issues'],'질문',[],selection=selected)
    assert calls==[] and len(seen)==1
    assert '이어서 읽어볼까요?' in cc.compose(result,answer.plan(result))['text']
    assert result['gaps'][0]['kind']=='MISSING_SOURCE'
