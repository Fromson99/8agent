"""Candidate contracts; no model calls or effect measurements."""
import json
from copy import deepcopy
import pytest
from conftest import term_glossary

from test_legal_agent_double_harness import generation
from test_legal_agent_v5 import session, drafted, review
from test_bounded_source_selection import record
from semantic_runtime.legal_agent import model_presentation as p, source_selection
from semantic_runtime.legal_agent.numbered_references import NumberedReferences
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.gateway import WIRE_PROJECTION
from test_tool_exploration_v3 import read


def evidence(ident='E1', document='d', version='v'):
    return {'evidence':ident,'document_id':document,'source_artifact_hash':version,
        'generation_id':'g','document_name':'모의 규정','text':'조건. 단, 예외。',
        'coordinate_label':'제1조 > 제2항','spans':[{'block_id':'1',
            'block_hash':'h','start_cp':0,'end_cp':10,'text':'조건. 단, 예외。'}]}


def test_shared_text_retains_original_evidence_choices_and_mapping():
    view={'exact_evidence':[evidence(),evidence('E2')]};before=deepcopy(view)
    wire=p.project(view,'compose')
    assert len(wire['bodies'])==1 and len(wire['documents'])==1
    assert len(wire['exact_evidence'])==2
    assert len(p.mapping(view,wire))==2 and view==before


@pytest.mark.parametrize('second',[evidence('E2','other'),evidence('E2',version='other')])
def test_identical_text_from_other_origin_is_separate(second):
    wire=p.project({'exact_evidence':[evidence(),second]},'compose')
    assert len(wire['bodies'])==2 and len(wire['documents'])==2


def test_unknown_origin_and_nonbody_context_are_preserved():
    first=evidence();first.pop('document_id')
    second=deepcopy(first);second['evidence']='E2'
    first['spans'].append({'block_id':'2','start_cp':0,'end_cp':2,'text':'추가'})
    view={'exact_evidence':[first,second]};wire=p.project(view,'compose')
    assert len(wire['documents'])==2 and len(wire['bodies'])==3
    assert any(b['text']=='추가' for b in wire['bodies'].values())
    p.mapping(view,wire)


def test_status_projection_preserves_definition_once():
    d={'id':'O1','requirement':'예외도 설명','question_refs':['Q1']}
    wire=p.project({'question_plan':{'demands':[d]},'answer_obligations':[{**d,'status':'OPEN'}]},'review')
    assert wire['question_plan']['demands']==[d]
    assert wire['answer_obligations']==[{'id':'O1','status':'OPEN'}]


def test_selected_only_compose_ignores_later_unselected_read(tmp_path,generation):
    from semantic_runtime.legal_agent import relation_views
    if 'selected-only' not in relation_views.__file__:
        pytest.skip('filler removal belongs to selected-only arm')
    with session(tmp_path,generation) as s:
        drafted(s)
        selected=set(s.packed['evidence_ids'])
        # A later observation of an existing approved source with its own E ID.
        extra=deepcopy(s.work.evidence(next(iter(selected))))
        extra['evidence_id']='Eextra'
        s.work.record_observation({'tool':'read_node','args':{},'reason':'synthetic later read'},
            {'tool':'read_node','status':'OK','items':[],'evidence_ids':['Eextra']},[extra],verify=lambda value:None)
        assert set(e['evidence_id'] for e in s.work.evidence())-selected
        v=s.view('compose',required=s.packed['evidence_ids'])
        assert {e['evidence'] for e in v['exact_evidence']}==selected


def test_group_before_limit_keeps_distinct_direction():
    r=record()
    r['routes']['1']=[{'kind':'reference','anchor':'0','reference_id':'ref'+str(i),
        'direction':'outgoing' if i<4 else 'incoming','resolution':'EXACT','branch':'global'} for i in range(5)]
    calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(data)
        return {'issues':[],'choices':[{'id':'C002','reason':'준용 조문'}] if len(calls)==1 else []}
    out=source_selection.select_sources('승인',r,invoke,remaining_seconds=60)
    assert len(out['paths']['1']['links'])==5
    assert len(calls[0]['candidates']['rows'][1][4])==2
    assert len(calls[1]['selected_original_excerpts'][0]['via_references'])==2


@pytest.mark.parametrize('phase,name',[('compose','Draft'),('review','ReviewDecision')])
def test_actual_gateway_and_journal_accept_same_projection_and_reject_tamper(tmp_path,generation,phase,name):
    with session(tmp_path,generation) as s:
        drafted(s)
        v=review(s)[0] if phase=='review' else s.view(phase,required=s.packed['evidence_ids'])
        refs=NumberedReferences(v);request=s.gateway.request(phase,v,name,references=refs)
        shown=json.loads(request['messages'][1]['content'])
        if phase=='compose':
            assert shown['view']['bodies']['B1']['text']==v['exact_evidence'][0]['text']
            assert 'spans' not in shown['view']['exact_evidence'][0]
            assert 'navigation_choices' not in shown['view']
        s.work.reserve_attempt(v,request,'valid',1,phase,numbered_references=refs,wire_projection=WIRE_PROJECTION)
        if phase=='compose':shown['view']['bodies']['B1']['text']+=' 변조'
        else:shown['view']['exact_evidence'][0]['text']+=' 변조'
        request['messages'][1]['content']=json.dumps(shown,ensure_ascii=False)
        with pytest.raises(ContractError,match='wire view differs'):
            s.work.reserve_attempt(v,request,'tamper',1,phase,numbered_references=refs,wire_projection=WIRE_PROJECTION)
