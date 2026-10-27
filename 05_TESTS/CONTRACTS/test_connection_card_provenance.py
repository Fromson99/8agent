"""Small presentation checks; no data index, provider or source loading."""
from copy import deepcopy
from contextlib import nullcontext
from types import SimpleNamespace as S

import pytest

from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import connection_scope as cs, unit_relations as rel
from semantic_runtime.legal_agent import investigation_leads as leads, law_candidates as lc
from semantic_runtime.legal_agent.errors import ContractError


def group(*refs, target='target', unit='7', blocks=('7','8'), direction='INCOMING', read=False, definition=False):
    anchor={'source_id':'anchor','document_id':'anchor-doc','document_name':'상위 규정',
            'heading':'제2조','unit_id':'2'}
    destination={'source_id':target,'document_id':target+'-doc','document_name':'연결 규정',
                 'heading':'제7조','unit_id':unit}
    origin=anchor if direction=='OUTGOING' else destination
    hit={**destination,'coordinate':'제7조 ①'}
    offer={'id':'scope','unit_id':unit,'extent':'subtree','block_ids':list(blocks)}
    return {'key':target+direction+str(blocks),'anchor':anchor,'target':destination,'direction':direction,
        'offers':{'scope':(hit,offer)},'connections':[{
            'reference_id':ref,'endpoint_scopes':['scope'],'endpoint_block_ids':list(blocks),
            'witness':'검증된 인용 '+ref,'witness_sha256':digest(ref),'witness_chars':100,
            'witness_truncated':True,'witness_document_id':origin['document_id'],
            'witness_block_id':'7' if direction=='INCOMING' else '2','source_unit_path':['인용 위치'],
            'locator':'제2조','reading_policy':{'obligation':'OPTIONAL'},'resolution':'EXACT',
            'already_read':read,'anchor_endpoint_quote':'세칙으로 정하는 기준',
            'defines_anchor_wording':{'quote':'세칙으로 정하는 기준'} if definition else None,
        } for ref in refs]}


@pytest.fixture
def inv(monkeypatch):
    monkeypatch.setattr(lc,'token',lambda s,k,v:k+digest(v)[:20])
    monkeypatch.setattr(cs.ur,'unit_label',lambda s,h:h['coordinate'])
    return S(s=S(),question='기준은?',p={'issues':[{'id':'Q1'}]},read_records=lambda:{},
        closed_reference_decisions=lambda *a:{})


@pytest.mark.parametrize('direction,owner,document,block',[
    ('INCOMING','target','target-doc','7'),('OUTGOING','anchor','anchor-doc','2')])
def test_witness_has_actual_origin_separate_from_anchor(inv,direction,owner,document,block):
    g=group('ref',direction=direction);actions={}
    card=cs.inline_cards(inv,{'id':'selected','members':[{'source_id':'anchor'}]},['E1'],[g],actions)[0]
    assert 'anchor_excerpt' not in card
    witness=card['reference_witness']
    assert (witness['belongs_to'],witness['document_id'],witness['block_id'])==(owner,document,block)
    assert witness['source_id']==g[owner]['source_id'] and witness['direction']==direction
    assert witness['text']=='검증된 인용 ref' and witness['truncated'] and witness['characters']==100
    assert card['anchor_endpoint_quote']=='세칙으로 정하는 기준'
    assert card['target_scope']=={'unit_id':'7','extent':'subtree','block_ids':['7','8']}


def test_same_extent_has_one_choice_and_keeps_every_witness(inv):
    first=group('a','b','c');second=group('d',target='other')
    original=deepcopy([first,second]);data={'status':'COMPLETE','groups':[first,second]}
    visible=cs.visible_connections(data,2,True)
    assert sum(len(g['connections']) for g in visible)==4
    actions={};cards=cs.inline_cards(inv,{'id':'selected','members':[{'source_id':'anchor'}]},['E1'],visible,actions)
    assert len(cards)==2 and len(actions)==2 and data['groups']==original
    witnesses=[cards[0]['reference_witness'],*[c['reference_witness'] for c in cards[0]['additional_reference_witnesses']]]
    assert [w['reference_id'] for w in witnesses]==['a','b','c']
    assert all(w['text']=='검증된 인용 '+w['reference_id'] for w in witnesses)


def test_two_anchor_scopes_reuse_choice_without_replacing_first_validation_binding(inv):
    actions={};a={'id':'first','members':[{'source_id':'anchor'}]};b={**a,'id':'second'}
    one=cs.inline_cards(inv,a,['E1'],[group('a')],actions)[0]
    original=deepcopy(actions)
    two=cs.inline_cards(inv,b,['E2'],[group('b')],actions)[0]
    assert one['read_action']==two['read_action'] and actions==original
    link=actions[one['read_action']]['identity']['connection']
    assert link['scope_id']=='first' and link['reference_id']=='a'
    assert two['reference_witness']['reference_id']=='b'


def test_different_authorized_extent_does_not_share_choice(inv):
    actions={};scope={'id':'selected','members':[{'source_id':'anchor'}]}
    a=cs.inline_cards(inv,scope,['E1'],[group('a',blocks=('7','8'))],actions)[0]
    b=cs.inline_cards(inv,scope,['E1'],[group('b',blocks=('7','8','9'))],actions)[0]
    assert a['read_action']!=b['read_action'] and len(actions)==2


def test_completed_definition_is_visible_and_never_offers_a_second_read(inv):
    completed=group('definition',read=True,definition=True)
    unrelated=group('citation',target='other')
    shown=cs.visible_connections({'status':'COMPLETE','groups':[unrelated,completed]},1,True)
    assert shown[0]['connections'][0]['reference_id']=='definition'
    actions={};card=cs.inline_cards(inv,{'id':'scope','members':[{'source_id':'anchor'}]},['E1'],shown,actions)[0]
    assert card['already_read'] and 'read_action' not in card and not actions
    assert card['defines_anchor_wording'] and card['applicability']=='UNDETERMINED'


def test_reused_choice_still_rejects_changed_endpoint_before_accept(inv,monkeypatch):
    g=group('ref');scope={'id':'selected','members':[{'source_id':'anchor'}]};actions={}
    card=cs.inline_cards(inv,scope,['E1'],[g],actions)[0]
    identity=actions[card['read_action']]['identity']
    monkeypatch.setattr(cs,'candidates',lambda *a:[(scope,['E1'])])
    monkeypatch.setattr(cs,'current',lambda i,**kw:{'scope':scope})
    monkeypatch.setattr(cs,'bound',lambda *a:nullcontext())
    changed=deepcopy(g);changed['connections'][0]['endpoint_block_ids']=['7','9']
    monkeypatch.setattr(rel,'catalog',lambda *a,**k:([changed],[],[],[]))
    accepted=[];monkeypatch.setattr(cs,'accept',lambda *a:accepted.append(a))
    with pytest.raises(ContractError,match='stale inline connection endpoint'):
        cs.validate_inline_read(inv,identity,{},'정확 범위')
    assert not accepted


@pytest.mark.parametrize('legacy',[False,True])
def test_lead_history_keeps_all_new_witnesses_and_accepts_legacy_cards(inv,monkeypatch,legacy):
    cards=cs.inline_cards(inv,{'id':'scope','members':[{'source_id':'anchor'}]},['E1'],[group('a','b')],{})
    if legacy:
        cards=[{'target':cards[0]['target'],'anchor':cards[0]['anchor'],'reference_id':'old',
                'anchor_excerpt':'과거 인용 원문','direction':'INCOMING','already_read':True}]
    inv.p['binding']={};inv.s.scope=['target-doc'];inv.s.context=S(query={'generation_id':'generation'})
    inv.idx=S(manifest={'index_sha256':'index'});inv.save=lambda:None
    monkeypatch.setattr(leads,'target',lambda s,identity,scope:deepcopy(identity))
    monkeypatch.setattr(leads,'export',lambda i:i.p['investigation_leads'])
    result=leads.capture(inv,{'references':{'dependency_cards':cards}})
    stored=next(iter(result['items'].values()))
    assert [o['reference_id'] for o in stored['origins']]==(['old'] if legacy else ['a','b'])
    assert stored['preview']==('과거 인용 원문' if legacy else '검증된 인용 a')


def test_compact_projection_preserves_witness_provenance_and_scopes(inv):
    from semantic_runtime.legal_agent.navigation_input import compact_cards,expand_cards
    cards=cs.inline_cards(inv,{'id':'scope','members':[{'source_id':'anchor'}]},['E1'],[group('a','b')],{})
    view={'references':{'dependency_cards':cards}}
    assert expand_cards(compact_cards(view))==view


def test_inline_limit_counts_endpoints_and_links_existing_target_originals(inv,monkeypatch):
    g=group(*(str(n) for n in range(8)),read=True,definition=True)
    scope={'id':'scope','label':'선택 원문','structural_selection':{},'members':[{'source_id':'anchor'}]}
    inv.modern=True;inv.policy={'selected_connection_scope':True,'delegation_frontier':True}
    inv.bind_reference_delivery=lambda **kwargs:None
    monkeypatch.setattr(cs,'current',lambda i,**kw:{'scope':scope})
    monkeypatch.setattr(cs,'candidates',lambda *a:[(scope,['E1'])])
    monkeypatch.setattr(cs,'preview',lambda *a,**kw:{'status':'COMPLETE','groups':[g],'connection_count':8})
    data={'sources':[{'id':'E2','source_id':'target','spans':[{'block_id':'7'}]},
        {'id':'E3','source_id':'target','spans':[{'block_id':'9'}]}],'references':{}};actions={}
    cs.offer_choices(inv,data,actions)
    assert not actions and data['connection_scope_choices'][0]['connections_complete']
    card=data['references']['dependency_cards'][0]
    assert card['target_source_refs']==['E2'] and len(card['additional_reference_witnesses'])==7
    assert data['references']['omitted_dependency_cards']==0


@pytest.mark.parametrize('blocked',[False,True])
def test_many_witnesses_use_existing_menu_without_losing_catalog_or_adding_reads(inv,monkeypatch,blocked):
    count=rel.LIMITS['witnesses_per_group']+3
    g=group(*(str(n) for n in range(count)),read=False,definition=True);before=deepcopy(g)
    scope={'id':'scope','label':'선택 원문','structural_selection':{},'members':[{'source_id':'anchor'}]}
    inv.modern=True;inv.policy={'selected_connection_scope':True,'delegation_frontier':True}
    inv.bind_reference_delivery=lambda **kwargs:None
    monkeypatch.setattr(cs,'current',lambda i,**kw:{'scope':scope})
    if blocked:
        inv.p['connection_context_blocks']={'scope':{'acquired_signature':'same','reason':'CONTEXT_LIMIT'}}
        monkeypatch.setattr(cs,'acquired_signature',lambda i:'same')
    monkeypatch.setattr(cs,'candidates',lambda *a:[(scope,['E1'])])
    monkeypatch.setattr(cs,'preview',lambda *a,**kw:{'status':'COMPLETE','groups':[g],'connection_count':count})
    data={'sources':[],'references':{}};actions={}
    cs.offer_choices(inv,data,actions)
    card=data['references']['dependency_cards'][0]
    assert len(card['additional_reference_witnesses'])+1==count
    assert not card.get('omitted_witness_count') and g==before and len(g['connections'])==count
    assert 'scope_menu_action' not in card
    assert not any(a['action']=='FOLLOW_CONNECTION' for a in actions.values())
    assert len([a for a in actions.values() if a['action']=='READ_ARTICLES'])==1
    assert data['connection_scope_choices'][0]['connections_complete']
    assert data['connection_scope_choices'][0]['connections_presented_count']==count
    # Every displayed witness remains in the source-bound lead ledger.
    inv.p['binding']={};inv.s.scope=['target-doc'];inv.s.context=S(query={'generation_id':'generation'})
    inv.idx=S(manifest={'index_sha256':'index'});inv.save=lambda:None
    monkeypatch.setattr(leads,'target',lambda s,identity,scope:deepcopy(identity))
    monkeypatch.setattr(leads,'export',lambda i:i.p['investigation_leads'])
    stored=next(iter(leads.capture(inv,data)['items'].values()))
    assert len(stored['origins'])==count
    assert g==before and len(g['connections'])==count
