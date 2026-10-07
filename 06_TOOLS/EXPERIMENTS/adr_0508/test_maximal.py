import pytest
from semantic_runtime.navigation_match import ReverseMatcher, SurfaceIndex
from semantic_runtime.legal_agent.errors import ProposalError
from test_legal_agent_double_harness import generation
from test_legal_agent_v5 import session, decision, plan
from test_tool_exploration_v3 import tool

def matcher():
    m=ReverseMatcher.__new__(ReverseMatcher)
    m.document_names=SurfaceIndex();m.structures=SurfaceIndex();m.units={}
    for did,title in [('a','가법 시행령'),('b','나법 시행령')]:
        m.document_names.add(title,did)
        for uid,parent,label in [('49',None,'제49조'),('49.1','49','제1항'),('50',None,'제50조'),('50.1','50','제1항')]:
            m.units[did,uid]={'parent':parent}
            m.structures.add(label,{'document_id':did,'unit_id':uid,'kind':'LOCATOR','family':'body'})
    return m

def run(q):
    m=matcher();return m.maximal_structures(q,{'a','b'},m.document_names.match(q))

@pytest.mark.parametrize('q',['가법 시행령 제49조 제1항','「가법 시행령」 제 49 조 제 1 항'])
def test_maximal_named_chain_has_one_deepest_node(q):
    structures,mentions=run(q)
    assert [(r['document_id'],r['unit_id']) for r in structures.values()]==[('a','49.1')]
    assert len(mentions)==1 and '가법 시행령' in mentions[0]['text']
    assert mentions[0]['resolution']=='RESOLVED'

def test_each_reference_uses_its_own_title():
    structures,mentions=run('가법 시행령 제49조 제1항과 나법 시행령 제50조 제1항')
    assert {(r['document_id'],r['unit_id']) for r in structures.values()}=={('a','49.1'),('b','50.1')}

@pytest.mark.parametrize('q',['제49조 제1항','미등록법 시행령 제49조 제1항','제1항','가법 시행령 제49조 제99항'])
def test_unresolved_never_expands_partial_coordinates(q):
    structures,mentions=run(q)
    assert not structures and mentions and mentions[0]['resolution']!='RESOLVED'

def test_action_may_use_background_alongside_answer_demand(tmp_path,generation):
    with session(tmp_path,generation,question='승인 요건은?\n(업무 문맥: 승인 절차)') as s:
        v=s.view('investigate')
        q=[x['id'] for x in s.context.pieces]
        assert len(q)==2
        p={'demands':[{'question_refs':[q[0]],'requirement':'승인 요건을 확인한다','given_facts':[],'missing_fact':None}],'context_refs':[q[1]],'change_reason':'최초 질문의 요구를 구분한다'}
        p=s.prepare_plan(p)
        a=tool('search',target=s.sources.root,query='승인',mode='literal',cursor=None)
        a['question_refs']=q
        d={'intent':'CONTINUE','actions':[a],'source_selection':None}
        s.validate_intent(v,d,p)
        a['question_refs']=[q[1]]
        with pytest.raises(ProposalError):s.validate_intent(v,d,p)

def test_context_default_is_100000():
    from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE,profile
    assert profile(DEFAULT_PROFILE)['max_context_chars']==100000
