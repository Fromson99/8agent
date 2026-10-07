"""Previously observed paragraph/root entries share one actual parent group."""
import pytest
from test_batch_reference_navigation import connected
from test_law_grouped_navigation import prepared,reader,decide,cards
from semantic_runtime.legal_agent import law_navigation as ln,law_candidates as lc,unit_reading as ur,unit_relations as rel

def fixture(connected):
    s,_=connected;rec=prepared(s);sid=next(sid for sid,x in s.tools.sources.items() if x['document_id']=='d')
    hit=rel.hit_for(s,sid,'1')
    rec['unit_hits']=[hit];rec['unit_reads']=ur.acquire_batch(s,[hit],rec['read_state'])
    inv=ln.Investigation(s,'긴급 승인 예외',rec,reader,60,None,None)
    gid=lc.token(s,'B',[sid,lc.parent_offer(s,hit)['id']])
    assert inv.p['groups'][gid]['hit']['unit_id']=='1' and inv.p['groups'][gid]['offer']['id']=='subtree:0'
    return inv,sid,gid

def choose(inv,sid):
    data,actions=inv.view();action=next(a for a in actions.values() if a['action']=='READ_ARTICLES' and a['identity']['source_id']==sid)
    law=next(l for l in data['laws'] if l['document_id']==action['identity']['document_id'])
    value=decide(data,'READ_ARTICLES',action['id']);value['law_decisions']=[{'law_id':law['id'],'status':'INVESTIGATE','reason':'항 적중의 상위 조 전체를 조사','issue_refs':['Q1'],'basis_refs':[]}]
    inv.validate(value,data,actions);inv.execute(value,data,actions)
    return inv.view()

def test_root_read_reuses_existing_paragraph_parent_group(connected):
    inv,sid,gid=fixture(connected);data,_=choose(inv,sid)
    assert inv.p['groups'][gid]['hit']['unit_id']=='1'
    assert inv.p['selected'][gid]['offer']['id']=='subtree:0' and inv.p['selected'][gid]['complete']
    assert any(p['source_id']==sid for p in data['sources'])
    assert not inv.active_records()

def test_collision_read_contains_header_and_all_sibling_originals(connected):
    inv,sid,gid=fixture(connected);choose(inv,sid)
    record=inv.p['selected'][gid];texts='\n'.join(e['text'] for e in record['evidence'])
    assert '제1조 승인' in texts and '긴급 승인은 허용한다.' in texts and '일반 승인은 제한한다.' in texts
    assert inv.p['action_chain']['steps'][-1]['reason']=='실제 원문과 쟁점 확인'
