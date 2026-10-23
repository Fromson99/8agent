from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import connection_scope as cs, unit_relations as rel
from semantic_runtime.legal_agent.errors import ContractError
from test_batch_reference_navigation import connected, initial
from conftest import term_glossary


def test_prefix_clipping_cannot_hide_verified_delegation_endpoints():
    rows=[{'reference_id':f'{i:02d}','already_read':False,'anchor_delegation_wording_hint':i in (8,15),
           'witness_source_order':i} for i in range(20)]
    group={'key':'target','connections':rows};data={'status':'COMPLETE','groups':[group]}
    before=deepcopy(data)
    result=cs.visible_connections(data,5,True)
    ids=[c['reference_id'] for g in result for c in g['connections']]
    assert ids[:2]==['08','15'] and len(ids)==5 and data==before
    assert [c['reference_id'] for g in cs.visible_connections(data,5,False) for c in g['connections']]==['00','01','02','03','04']


def test_priority_does_not_reread_acquired_target_or_claim_necessity():
    result=cs.visible_connections({'status':'PARTIAL','groups':[{'key':'a','connections':[
        {'reference_id':'read','already_read':True,'anchor_delegation_wording_hint':True},
        {'reference_id':'unread','already_read':False,'anchor_delegation_wording_hint':True}]}]},1,True)
    assert result[0]['connections'][0]['reference_id']=='unread'
    assert 'obligation' not in result[0]['connections'][0]
    assert cs.visible_connections({'status':'FAILED','groups':[]},5,True)==[]


def test_preview_scans_before_prioritizing_instead_of_stopping_at_six_edges(monkeypatch):
    seen=[]
    monkeypatch.setattr(cs,'bound',lambda *a:__import__('contextlib').nullcontext())
    monkeypatch.setattr(rel,'catalog',lambda *a,**kw:(seen.append(kw) or [],[],[],[]))
    inv=S(policy={'delegation_frontier':True},p={'binding':{}},s=S(scope=['doc']),read_records=lambda:{})
    cs.preview(inv,{'members':[{'source_id':'s'}]})
    assert seen[0]['max_connections'] is None
    inv.policy['delegation_frontier']=False;cs.preview(inv,{'members':[{'source_id':'s'}]})
    assert seen[1]['max_connections']==6


@pytest.mark.parametrize('connected',['① 세칙으로 정하는 승인 항목은 「모의승인규정」 제1조제1항에 따른다.'],indirect=True)
def test_endpoint_quote_is_verified_anchor_not_borrowed_from_incoming_witness(connected):
    s,_=connected;rec,sid=initial(s)
    s.profile.setdefault('candidate_navigation',{}).update(delegation_frontier=True)
    groups,*_=rel.catalog(s,[sid],{'root':rec['unit_reads'][0]},set())
    g=next(g for g in groups if g['target']['document_id']=='detail');edge=g['connections'][0]
    # Incoming witness has delegation wording; the anchor itself does not.
    assert '세칙으로 정하는' in edge['witness']
    assert not edge['anchor_delegation_wording_hint']
    assert all(b in {str(x['block_id']) for x in s.tools.sources[sid]['blocks']} for b in edge['anchor_head_block_ids'])
    assert '세칙으로 정하는' not in edge['anchor_endpoint_quote']


def test_generation_notes_are_bounded_without_truncating_sources_or_claim_text():
    from semantic_runtime.legal_agent.completion_execution import bounded_judgment_notes
    from semantic_runtime.legal_agent.minimal_output import Projection
    from jsonschema import validate,ValidationError
    schema={'type':'object','properties':{'reason':{'type':'string'},'quote':{'type':'string'},
        'text':{'type':'string'},'explanation':{'type':'string','maxLength':200}},'required':['reason','quote','text','explanation']}
    changed=bounded_judgment_notes(schema);wire=Projection(changed).wire
    assert 'maxLength' not in schema['properties']['reason']
    assert wire['properties']['reason']['maxLength']==600
    assert wire['properties']['explanation']['maxLength']==200
    assert 'maxLength' not in wire['properties']['quote'] and 'maxLength' not in wire['properties']['text']
    good={'reason':'짧은 판단','quote':'원문'*1000,'text':'판단'*1000,'explanation':'근거'};validate(good,changed)
    with pytest.raises(ValidationError):validate({**good,'reason':'반복'*301},changed)


@pytest.mark.parametrize('tail,anchor,expected',[
    ('에서 "세칙으로 정하는 항목"이란 다음 각 호를 말한다.','세칙으로 정하는 항목',True),
    ('에서 “세칙으로 정하는 항목”이란 다음 각 호를 말한다.','세칙으로 정하는 항목',True),
    ('의 세칙으로 정하는 항목에 따른다.','세칙으로 정하는 항목',False),
    (' 및 제8조에서 "세칙으로 정하는 항목"이란 다음 각 호를 말한다.','세칙으로 정하는 항목',False),
    ('에서 "세칙으로 정하는 다른 항목"이란 다음 각 호를 말한다.','세칙으로 정하는 항목',False),
    ('에서 "세칙으로 정하는 항목"이란 다음 각 호를 말한다.','세칙으로 정하는 다른 항목',False),
])
def test_exact_definition_attribution(tail,anchor,expected):
    from semantic_runtime.legal_agent.delegated_content import definition_wording
    mention='규정 제7조';text=mention+tail
    ref={'source_text':text,'mention_start':0,'mention_end':len(mention),'mention_text':mention}
    hit=definition_wording(ref,anchor)
    assert bool(hit)==expected
    if hit:assert text[hit['witness_start']:hit['witness_end']]==hit['quote']
    assert definition_wording({**ref,'mention_start':1},anchor) is None


def test_definition_beats_low_ordinal_mere_citations_to_same_delegation():
    citations=[{'reference_id':f'cite{i}','already_read':False,'anchor_delegation_wording_hint':True,
                'witness_source_order':0} for i in range(8)]
    definitions=[{'reference_id':f'define{i}','already_read':False,'anchor_delegation_wording_hint':True,
                  'witness_source_order':i,'defines_anchor_wording':{'quote':'세칙으로 정하는 항목'}} for i in (3,5)]
    result=cs.visible_connections({'status':'PARTIAL','groups':[{'key':'k','connections':citations+definitions}]},5,True)
    assert [c['reference_id'] for g in result for c in g['connections']][:2]==['define3','define5']


@pytest.mark.parametrize('count',[1,2])
def test_assessment_identity_count_bounds_repeated_rows_on_wire(count):
    from semantic_runtime.legal_agent.completion_execution import bounded_judgment_notes
    from semantic_runtime.legal_agent.minimal_output import Projection
    from semantic_runtime.legal_agent.completion_contracts import obj
    from jsonschema import validate,ValidationError
    ids=[f'Q{n}' for n in range(count)]
    row=obj({'issue_id':{'enum':ids},'status':{'enum':['COVERED','PARTIAL']},'reason':{'type':'string'}})
    schema=obj({'issue_assessments':{'type':'array','items':row}})
    bounded=bounded_judgment_notes(schema);codec=Projection(bounded)
    good={'issue_assessments':[{'issue_id':i,'status':'PARTIAL','reason':'현재 원문과 남은 미확인'} for i in ids]}
    validate(codec.project(good),codec.wire)
    with pytest.raises(ValidationError):validate({**good,'issue_assessments':good['issue_assessments']+[good['issue_assessments'][0]]},bounded)
    assert codec.wire['properties']['issue_assessments']['maxItems']==count
