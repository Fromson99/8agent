"""Ordinary contracts: source grammar, evidence scope and bounded review feedback."""
import copy
import pytest
from lawrag.core.structure import recipe_visual_loop as loop, pipeline
from lawrag.core.structure.model import Block

@pytest.mark.parametrize('gap', [' ', '\t', '\u00a0'])
def test_spaced_annex_reference_keeps_source_and_rejects_false_heading(gap):
    text='제4조(지원기준) ① 실제 비용에 대해 [ 별표 1]'+gap+'에서 정한 기준으로 지원한다.'
    blocks=[Block(idx=i,text=t,page=1) for i,t in enumerate(['제1조(목적) 가','제2조(정의) 나','제3조(범위) 다',text])]
    before=copy.deepcopy([b.dump() for b in blocks])
    result=pipeline.interpret(blocks,doc='contract',llm=None,ledger=None)
    refs=[c for c in result.candidates if c.family.startswith('annex_')]
    assert refs and all(not c.activated for c in refs)
    assert all(c.guards['particle_ko']<0 for c in refs)
    assert [b.dump() for b in blocks]==before
    assert any(n.family=='kr_article' and n.block_idx==3 for n in result.nodes())

@pytest.mark.parametrize('tail',[' 지원기준',' 은행별 적용',' 이사회 업무','\n의무 사항'])
def test_genuine_annex_heading_remains(tail):
    result=pipeline.interpret([Block(idx=0,text='[별표 1]'+tail,page=1)],doc='contract',llm=None,ledger=None)
    assert any(n.family=='annex_별표' for n in result.nodes())

CAT={'a':{},'b':{}}
R={'tag':'contract','version':1,'levels':[['a'],['b']]}
DATA={'source_blocks':[{'idx':2,'text':'A'},{'idx':10,'text':'B'}],'catalog':CAT,'recipe':R}
def response(verdict,recipe=None,blocks=None):
    return {'verdict':verdict,'issues':[] if verdict=='approve' else [{'blocks':[2] if blocks is None else blocks,'reason':'evidence'}], **({'recipe':copy.deepcopy(recipe or R)} if verdict=='revise' else {})}
def caller(items, calls):
    def call(*args):
        calls.append(copy.deepcopy(args));return dict(copy.deepcopy(items[len(calls)-1]), reviewed_state_id=args[2]['reviewed_state_id'])
    return call

@pytest.mark.parametrize('verdict',['missing_rules','source_error','hold'])
def test_noop_feedback_can_explain_limitation(verdict):
    calls=[];before=copy.deepcopy(DATA)
    r=loop.request_review('review',DATA,CAT,caller([response('revise',{**R,'version':2}),response(verdict)],calls))
    assert r['verdict']==verdict and len(calls)==2
    assert calls[1][0]=='review-feedback' and calls[1][4] is True
    assert 'validation_feedback' in calls[1][2] and 'previous_review' in calls[1][2]
    assert DATA==before

def test_noop_feedback_accepts_changed_hierarchy_for_rebuild():
    calls=[];other={**R,'levels':[['b'],['a']]}
    result=loop.request_review('review',DATA,CAT,caller([response('revise'),response('revise',other)],calls))
    assert result['recipe']==other and len(calls)==2

def test_noop_feedback_never_approves_same_tree():
    calls=[]
    with pytest.raises(ValueError,match='cannot be approved'):
        loop.request_review('review',DATA,CAT,caller([response('revise'),response('approve')],calls))
    assert len(calls)==2

def test_noop_stops_after_one_feedback():
    calls=[]
    with pytest.raises(ValueError,match='review_revision_no_progress'):
        loop.request_review('review',DATA,CAT,caller([response('revise'),response('revise')],calls))
    assert len(calls)==2

def test_visited_hierarchy_also_needs_feedback():
    calls=[];other={**R,'levels':[['b'],['a']]}
    r=loop.request_review('review',DATA,CAT,caller([response('revise',other),response('hold')],calls),seen_levels={loop.digest(other['levels'])})
    assert r['verdict']=='hold' and len(calls)==2

@pytest.mark.parametrize('ids',[[],[0],[True]])
def test_source_error_requires_actual_supplied_blocks(ids):
    with pytest.raises(ValueError):
        loop.request_review('review',DATA,CAT,caller([response('source_error',blocks=ids),response('source_error',blocks=ids)],[]))

def test_valid_first_approval_remains_one_call():
    calls=[];r=loop.request_review('review',DATA,CAT,caller([response('approve')],calls))
    assert r['verdict']=='approve' and len(calls)==1

def test_provider_error_is_not_review_feedback():
    calls=[]
    def fail(*args):calls.append(1);raise TimeoutError('test')
    with pytest.raises(TimeoutError):loop.request_review('review',DATA,CAT,fail)
    assert len(calls)==1


def test_bound_approval_returns_exact_input_recipe_without_reconstruction():
    data=copy.deepcopy(DATA)
    data['recipe']['heading_candidates']=['outside','visible']
    data['source_candidates']=[{'id':'visible'}]
    before=copy.deepcopy(data);calls=[]
    def call(phase,system,request,schema,vision):
        calls.append(copy.deepcopy(request))
        assert 'recipe' not in schema['required']
        return {'verdict':'approve','issues':[], 'reviewed_state_id':request['reviewed_state_id']}
    got=loop.request_review('review',data,CAT,call)
    assert got['recipe']==before['recipe'] and got['recipe'] is not data['recipe']
    assert data==before and len(calls)==1


@pytest.mark.parametrize('bad',['recipe_change','recipe_unchanged','stale','missing_id'])
def test_invalid_approval_gets_one_feedback_without_applying_edits(bad):
    calls=[]
    def call(phase,system,request,schema,vision):
        calls.append(copy.deepcopy(request))
        out={'verdict':'approve','issues':[], 'reviewed_state_id':request['reviewed_state_id']}
        if len(calls)==1:
            if bad.startswith('recipe'):
                out['recipe']={**R,'levels':[['b'],['a']]} if bad=='recipe_change' else copy.deepcopy(R)
            elif bad=='stale':out['reviewed_state_id']='old-state'
            else:del out['reviewed_state_id']
        return out
    got=loop.request_review('review',DATA,CAT,call)
    assert got['recipe']==R and len(calls)==2
    assert calls[0]['reviewed_state_id']==calls[1]['reviewed_state_id']
    assert calls[1]['validation_feedback'] and calls[1]['invalid_review']


def test_invalid_approval_can_become_revision_but_never_auto_applied_as_approval():
    calls=[];other={**R,'levels':[['b'],['a']]}
    def call(*args):
        calls.append(args)
        return {'verdict':'approve' if len(calls)==1 else 'revise',
                'issues':[],'recipe':copy.deepcopy(other),'reviewed_state_id':args[2]['reviewed_state_id']}
    got=loop.request_review('review',DATA,CAT,call)
    assert got['verdict']=='revise' and got['recipe']==other and len(calls)==2


def test_approval_with_reported_issue_cannot_silently_clear_it_on_feedback():
    calls=[]
    def call(*args):
        calls.append(args)
        return {'verdict':'approve','issues':[{'blocks':[2],'reason':'missing heading'}] if len(calls)==1 else [],
                'reviewed_state_id':args[2]['reviewed_state_id']}
    with pytest.raises(ValueError,match='cannot be approved'):
        loop.request_review('review',DATA,CAT,call)
    assert len(calls)==2


def test_repeated_stale_approval_stops_after_two_calls():
    calls=[]
    def call(*args):
        calls.append(args);return {'verdict':'approve','issues':[],'reviewed_state_id':'stale'}
    with pytest.raises(ValueError,match='invalid_review_response'):
        loop.request_review('review',DATA,CAT,call)
    assert len(calls)==2


@pytest.mark.parametrize('field,value',[
    ('recipe',{**R,'version':2}),('tree',{'changed':True}),
    ('source_blocks',[{'idx':2,'text':'changed source'}]),('window',[7,8]),
])
def test_review_state_changes_with_every_reviewed_input(field,value):
    states=[]
    def call(*args):
        states.append(args[2]['reviewed_state_id'])
        return {'verdict':'approve','issues':[],'reviewed_state_id':states[-1]}
    loop.request_review('review',DATA,CAT,call)
    loop.request_review('review',{**DATA,field:value},CAT,call)
    assert states[0]!=states[1]


def test_stale_revision_is_rejected_before_build():
    def call(*args):
        return {'verdict':'revise','issues':[],'recipe':{**R,'levels':[['b'],['a']]},'reviewed_state_id':'stale'}
    with pytest.raises(ValueError,match='state mismatch'):
        loop.request_review('review',DATA,CAT,call)
