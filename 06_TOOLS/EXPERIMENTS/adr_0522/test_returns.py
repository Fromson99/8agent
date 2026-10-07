import json,sqlite3
from types import SimpleNamespace
from test_contract import db_new,add,article,frame,navigator,roots

def fixture(*,multi=False):
 db=db_new();frame(db,'d',[['kr_article'],['circled'],['dot']])
 add(db,'a',1,'제2조제1항제10호를 준용한다.')
 article(db,'b','d','모의규정','제2조','u2',[('200','제2조'),('201','① 정의'),('210','10. 범위'),('239','39. 제4조를 준용한다.')],[('u21','u2',[1],'①',['201'],'circled'),('u210','u21',[10],'10.',['210'],'dot'),('u239','u21',[39],'39.',['239'],'dot')])
 add(db,'c',3,'제2조를 준용하며 제5조를 적용한다.')
 add(db,'d',4,'별도 근거');add(db,'e',5,'제2조부터 제4조까지 준용한다.' if multi else '종료');add(db,'f',6,'제5조를 준용한다.')
 return navigator(db)

def test_reciprocal_return_cannot_widen_item_scope():
 nav=fixture();g=nav.walk(roots(nav,'a'))
 assert set(g['source_ids'])=={'a','b','c','e','f'}
 assert all(s['extent']['block_ids']==['210'] for s in g['states'] if s['extent']['source_id']=='b')
 assert any(e.get('suppressed_return_source_ids') for e in g['edges'])

def test_independent_whole_article_root_and_owners_remain_valid():
 nav=fixture();rs=roots(nav,'a','c');g=nav.walk(rs)
 assert g['owners']['d']==[rs[1]['root_id']]
 assert g['owners']['b']==sorted(r['root_id'] for r in rs)
 from semantic_runtime.legal_agent.source_selection import removal_preview
 preview=removal_preview(g,rs[0]['root_id'],['scope'])
 assert not any(e['source_id']=='b' and e['block_ids']==['210'] for e in preview['exclusive_extents'])

def test_range_reference_other_endpoints_continue():
 nav=fixture(multi=True);g=nav.walk(roots(nav,'a'))
 assert {'c','d','e','f'}<=set(g['source_ids'])
 # C independently cites the whole B article, so this genuinely different path
 # is retained. The same E->B range edge itself must suppress its return target.
 assert any(e.get('suppressed_return_source_ids')==['b'] for e in g['edges'])

def test_read_relation_cards_use_the_same_return_guard():
 from semantic_runtime.legal_agent.workflow_relation_cards import RelationCards
 nav=fixture();incoming=next(e for e in nav.neighbors(nav.extent('b',['210']),'incoming') if e['targets'][0]['source_id']=='c')
 def ev(sid,blocks):return {'source_id':sid,'spans':[{'block_id':b['block_id'],'start_cp':0,'end_cp':len(b['text'])} for b in nav.sources[sid]['blocks'] if b['block_id'] in blocks]}
 evidence={'prior':ev('b',['210']),'current':ev('c',['300'])};db=sqlite3.connect(':memory:');db.execute('CREATE TABLE event(kind TEXT,payload_json TEXT,seq INTEGER)')
 origin={'route_class':'DB_REFERENCE','reference_id':incoming['reference_id'],'direction':'incoming','anchor_evidence':'prior','target_extent':nav.extent('c')}
 fake=SimpleNamespace(repo=SimpleNamespace(db=db,evidence=lambda eid:evidence[eid]),tools=SimpleNamespace(db=nav.db,sources=nav.sources),scope={'d'},context=SimpleNamespace(binding_hash=nav.binding),read_origin=lambda _:origin)
 notices=list(RelationCards(fake).references('current'))
 assert any(n.get('suppressed_return_source_ids')==['b'] and not n['targets'] for n in notices)
 assert any(t['source_id']=='e' for n in notices for t in n['targets'])
