"""Selection/delivery isolation across every structural level and resume."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import connection_scope as cs, unit_relations as rel, structure_selection as ss
from semantic_runtime.legal_agent.errors import ContractError
from lawrag.core.structure.viewer import annotate_coordinate_scopes
from semantic_runtime.inherited_navigation import _derive_bindings
from test_batch_reference_navigation import connected, initial
from conftest import term_glossary


def fixture(monkeypatch):
    rows=[(0,None,'kr_편','제1편',11),(1,0,'kr_장','제1장',11),
        (2,1,'kr_절','제1절',11),(3,2,'kr_관','제1관',11),
        (4,3,'kr_article','제92조',10),(5,4,'circled','②',10),
        (6,5,'dot_number:1','1.',9),(7,6,'hangul_dot','가.',8),
        (8,6,'hangul_dot','나.',9),(9,5,'dot_number:1','2.',10),
        (10,3,'kr_article','제97조',11)]
    nodes=[dict(id=i,parent=p,family=f,surface=t,title='',block=i,span=[i,hi]) for i,p,f,t,hi in rows]
    annotate_coordinate_scopes(nodes,'law')
    raw={('d',str(n['id'])):{**n,'parent':str(n['parent']) if n['parent'] is not None else None,'raw_structure':deepcopy(n)} for n in nodes}
    units,coords=_derive_bindings(raw)
    matcher=S(units=units,stored_coordinates=coords,documents={'d':'모의법'},sources={})
    originals={str(n['id']):n['surface']+' 원문' for n in nodes}
    session=S(scope=['d'],matcher=matcher,store=S(source=lambda d,b:{'text':originals[str(b)]}),tools=S(sources={}),repo=S(event=lambda *a:None))
    inv=S(s=session,modern=True,policy={'selected_connection_scope':True},p={'binding':{'generation':'test'},'selected':{},'groups':{}},save=lambda:None)
    monkeypatch.setattr(cs.inventory,'scope_path',lambda s,h,o:'모의법 '+str(coords['d',o['unit_id']]))
    monkeypatch.setattr(cs.ur,'blocks',lambda s,d,u,e:[str(i) for i in range(*units[d,u]['span'])])
    def add(gid,sid,uid,blocks,context=()):
        spans=[{'block_id':str(b),'start_cp':0,'end_cp':len(originals[str(b)]),'text':originals[str(b)]} for b in [*context,*blocks]]
        offer={'unit_id':str(uid),'extent':'subtree','block_ids':list(map(str,blocks))}
        inv.p['selected'][gid]={'source_id':sid,'document_id':'d','offer':offer}
        inv.p['groups'][gid]={'status':'READ','hit':{}}
        session.tools.sources[sid]={'document_id':'d','blocks':[{'block_id':str(b)} for b in blocks]}
        return {'id':'E'+gid,'branch_id':gid,'source_id':sid,'document_id':'d','scope_id':digest(offer),'spans':spans}
    return inv,add


@pytest.mark.parametrize('uid,unit,n,path',[
    (0,'편',1,[]),(1,'장',1,[{'unit':'편','n':1}]),
    (2,'절',1,[{'unit':'편','n':1},{'unit':'장','n':1}]),
    (3,'관',1,[{'unit':'편','n':1},{'unit':'장','n':1},{'unit':'절','n':1}]),
    (4,'조',92,[]),(5,'항',2,[{'unit':'조','n':92}]),
    (6,'호',1,[{'unit':'조','n':92},{'unit':'항','n':2}]),
    (7,'목','가',[{'unit':'조','n':92},{'unit':'항','n':2},{'unit':'호','n':1}])])
def test_all_levels_use_stored_selection_and_only_delivered_members(monkeypatch,uid,unit,n,path):
    inv,add=fixture(monkeypatch)
    selection={'coordinate_scope':'body','groups':[{'parent_path':path,'unit':unit,
        'include':[{'kind':'SINGLE','value':{'n':n}}],'exclude':[]}]}
    record=ss.resolve(selection,inv.s.matcher,'d',['d'])
    assert record['unit_ids']==[str(uid)]
    inv.p['structure_selections']={'chosen':record}
    pages=[add('a','article92',4,list(range(4,10)),context=[0,1,2,3]),add('b','article97',10,[10])]
    options=cs.candidates(inv,{'sources':pages})
    scope=next(s for s,_ in options if s['structural_selection'].get('selection_id')=='chosen')
    selected={p['block_id'] for m in scope['members'] for p in m['spans']}
    expected=set(cs.ur.blocks(inv.s,'d',str(uid),'subtree')) & set(map(str,range(4,11)))
    assert selected==expected
    assert len(scope['members'])==(2 if uid<=3 else 1)
    assert scope['structural_selection']['delivered_only']


def test_union_exclusion_and_context_are_not_reintroduced(monkeypatch):
    inv,add=fixture(monkeypatch)
    selection={'coordinate_scope':'body','groups':[{'parent_path':[{'unit':'조','n':92},{'unit':'항','n':2}],
        'unit':'호','include':[{'kind':'ALL'}],'exclude':[{'kind':'SINGLE','value':{'n':2}}]}]}
    record=ss.resolve(selection,inv.s.matcher,'d',['d']);inv.p['structure_selections']={'set':record}
    page=add('a','s',4,list(range(4,10)),context=[0,1])
    scope=cs.candidates(inv,{'sources':[page]})[-1][0]
    assert {s['block_id'] for m in scope['members'] for s in m['spans']}=={'6','7','8'}
    assert scope['structural_selection']['excluded_unit_ids']==['9']
    inv.p['structure_selections']['set']['unit_ids'].append('9')
    with pytest.raises(ContractError,match='hash'):cs.candidates(inv,{'sources':[page]})


def test_new_reads_invalidate_frontier_but_keep_originals_and_replay(monkeypatch):
    inv,add=fixture(monkeypatch);page=add('a','s',6,[6],context=[4,5]);data={'sources':[page]}
    scope=cs.candidates(inv,data)[0][0]
    assert [s['block_id'] for s in scope['members'][0]['spans']]==['6']
    before=deepcopy(inv.p['selected']);cs.accept(inv,scope,data,'활용할 범위')
    assert cs.current(inv)['scope']==scope and inv.p['selected']==before
    add('b','other',10,[10]);assert cs.current(inv) is None
    cs.accept(inv,scope,{'sources':[]},'이전 범위 재개',replay=True)
    assert cs.current(inv)['scope']==scope and set(inv.p['selected'])=={'a','b'}
    with cs.bound(inv.s,scope):assert set(inv.s.connection_scope_spans)=={'s'}
    assert not hasattr(inv.s,'connection_scope_spans')
    corrupt=deepcopy(scope);corrupt['members'][0]['spans'][0]['end_cp']+=1
    with pytest.raises(ContractError):cs.accept(inv,corrupt,{},'변조',replay=True)
    inv.s.scope=[]
    with pytest.raises(ContractError):cs.current(inv)


def test_catalog_uses_selected_witness_not_other_read_source(connected):
    s,_=connected;rec,sid=initial(s)
    s.profile.setdefault('candidate_navigation',{})['investigation_control']=True
    source=next(v for v in s.tools.sources.values() if v['document_id']=='detail')
    hit=rel.hit_for(s,source['id'],'2')
    from semantic_runtime.legal_agent import unit_reading as ur
    chosen=ur.read(s,hit,next(o for o in ur.offers(s,hit) if o['id']=='subtree:2'),action_state={'count':0,'chars':0})
    selected={'a':rec['unit_reads'][0],'b':chosen}
    spans=[p for e in chosen['evidence'] for p in e['spans']]
    scope={'members':[{'source_id':source['id'],'spans':spans}]}
    before=deepcopy(selected)
    with cs.bound(s,scope):
        groups,statuses,_,_=rel.catalog(s,[source['id']],selected,set())
        assert not groups  # Reference is in paragraph introduction, not item1.
        assert statuses[0]['status']=='NO_VERIFIED_LINKS_IN_CURRENT_SCOPE_AND_INDEX'
        with pytest.raises(ContractError):rel.catalog(s,[sid],selected,set())
    assert selected==before


def test_broader_incoming_endpoint_does_not_masquerade_as_selected_item_link(connected):
    s,_=connected;rec,sid=initial(s)
    s.profile.setdefault('candidate_navigation',{})['investigation_control']=True
    from semantic_runtime.legal_agent import unit_reading as ur
    hit=rel.hit_for(s,sid,'2')
    chosen=ur.read(s,hit,next(o for o in ur.offers(s,hit) if o['id']=='subtree:2'),action_state={'count':0,'chars':0})
    spans=[p for e in chosen['evidence'] for p in e['spans']]
    with cs.bound(s,{'members':[{'source_id':sid,'spans':spans}]}):
        groups,statuses,_,_=rel.catalog(s,[sid],{'selected':chosen},set())
        assert not groups and statuses[0]['broader_incoming_not_in_selected_scope']>0
