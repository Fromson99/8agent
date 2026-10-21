"""Independent finite boundary census; no legal questions or external calls."""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from semantic_runtime.legal_agent import unit_relations as rel, completion_contracts as cc
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.legal_agent.errors import ProposalError
from test_batch_reference_navigation import connected, initial

def fake(rows, texts):
    return SimpleNamespace(scope=sorted({v['document_id'] for v in rows.values()}),
        tools=SimpleNamespace(sources=rows), store=SimpleNamespace(source=lambda did,bid:{'text':texts[(did,bid)]}))

def span(bid,text,lo,hi):
    return {'block_id':bid,'start_cp':lo,'end_cp':hi,'text':text[lo:hi],
        'block_hash':text_hash(text),'span_hash':text_hash(text[lo:hi]),'complete':True}

@pytest.mark.parametrize('text',['가e\u0301😀\r\n끝','① 原文\n둘째줄\tΩ'])
@pytest.mark.parametrize('kind',['split','overlap','reversed','duplicate','hole'])
def test_unicode_coverage_requires_exact_union(text,kind):
    n=len(text);at=n//2
    ranges={'split':[(0,at),(at,n)],'overlap':[(0,at+1),(at,n)],
        'reversed':[(at,n),(0,at)],'duplicate':[(0,n),(0,n)],'hole':[(0,at),(at+1,n)]}[kind]
    s=fake({'S':{'document_id':'D','blocks':[{'block_id':'0'}]}},{('D','0'):text})
    got=rel.delivered_blocks(s,{'S':[span('0',text,a,b) for a,b in ranges]})
    assert got=={'S':set() if kind=='hole' else {'0'}}

@pytest.mark.parametrize('identity',['document','source','block'])
def test_identical_text_fragments_never_cross_identity(identity):
    text='동일 원문😀';at=len(text)//2
    if identity=='block':
        rows={'S':{'document_id':'D','blocks':[{'block_id':'0'},{'block_id':'1'}]}}
        texts={('D','0'):text,('D','1'):text};spans={'S':[span('0',text,0,at),span('1',text,at,len(text))]}
    else:
        d2='E' if identity=='document' else 'D'
        rows={'S':{'document_id':'D','blocks':[{'block_id':'0'}]},'T':{'document_id':d2,'blocks':[{'block_id':'0'}]}}
        texts={('D','0'):text,(d2,'0'):text};spans={'S':[span('0',text,0,at)],'T':[span('0',text,at,len(text))]}
    assert all(not v for v in rel.delivered_blocks(fake(rows,texts),spans).values())

@pytest.mark.parametrize('version',[cc.V5,cc.V6,cc.V7,cc.V8])
def test_native_versions_preserve_unresolved_menu_across_serialized_resume(connected,version):
    s,_=connected;s.profile.setdefault('candidate_navigation',{}).update(investigation_control=True,completion_contract=True,completion_policy_version=version)
    r,_=initial(s);selected={'initial':r['unit_reads'][0]};before=deepcopy(selected);calls=[];state={}
    def invoke(*args):calls.append(1);raise ProposalError('finite invalid decision')
    def run(st):return rel.navigate('모의 승인 확인',s,selected,invoke,read_state={'count':0,'chars':0},seconds_left=lambda:120,max_context_chars=100000,state=st,max_model_batches=1)
    result=run(state);assert len(calls)==2 and result['pending'] and not result['actions']
    assert not state['decisions'] and not state['accepted'] and selected==before
    resumed=json.loads(json.dumps(state));again=run(resumed)
    assert len(calls)==2 and again['pending'] and selected==before
    assert resumed['unresolved_decision_menus']==state['unresolved_decision_menus']

@pytest.mark.parametrize('left',[0,-1,1])
def test_deadline_before_model_call_cannot_reset_or_fabricate_progress(connected,left):
    s,_=connected;s.profile.setdefault('candidate_navigation',{}).update(investigation_control=True,completion_contract=True,completion_policy_version=cc.V8)
    r,_=initial(s);selected={'initial':r['unit_reads'][0]};before=deepcopy(selected);state={};calls=[];reads={'count':0,'chars':0}
    def invoke(*args):calls.append(1);raise AssertionError('expired deadline must precede model')
    with pytest.raises(TimeoutError):
        rel.navigate('모의 승인 확인',s,selected,invoke,read_state=reads,seconds_left=lambda:left,max_context_chars=100000,state=state,max_model_batches=1)
    assert not calls and selected==before and reads=={'count':0,'chars':0}
    assert not state['decisions'] and not state['accepted'] and not state.get('unresolved_decision_menus')
