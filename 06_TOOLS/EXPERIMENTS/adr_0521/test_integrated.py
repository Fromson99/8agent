import json,sqlite3,random
from collections import deque
import pytest
from test_contract import db_new,add,navigator,roots,article,frame
from semantic_runtime.reference_exploration import ReferenceNavigator
from semantic_runtime.legal_agent.source_selection import removal_preview,review_removal,root_bundles
from conftest import term_glossary
from test_legal_agent_v5 import session
from test_tool_exploration_v3 import read,tool,delivered
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.legal_agent.errors import ProposalError


def chain():
    db=db_new();add(db,'a',1,'제2조에 따른다.');add(db,'b',2,'제3조를 준용한다.');add(db,'c',3,'제1조를 준용한다.');add(db,'d',4,'별도 근거')
    return navigator(db)

def test_shared_expansion_ownership_resume_and_root_removal():
    nav=chain();rs=roots(nav,'a','b','d');counts={};original=nav.neighbors
    def counted(e,*args,**kw):
        k=nav.state_key(e);counts[k]=counts.get(k,0)+1
        yield from original(e,*args,**kw)
    nav.neighbors=counted
    partial=nav.walk(rs,max_states=1);assert partial['status']=='PARTIAL'
    result=nav.walk(rs,checkpoint=partial)
    assert result['status']=='COMPLETE' and max(counts.values())==1
    assert result['owners']['c']==sorted([rs[0]['root_id'],rs[1]['root_id']])
    reduced=root_bundles({'roots':rs},[rs[1]['root_id']],navigator=nav)
    assert set(reduced['source_ids'])=={'a','b','c'}
    assert len(result['proofs'])<=len(result['edges'])
    damaged={**partial,'binding':'wrong'}
    with pytest.raises(ValueError):nav.walk(rs,checkpoint=damaged)

def test_removal_requires_current_impact_and_delivered_alternative():
    nav=chain();rs=roots(nav,'a','d');g=nav.walk(rs);preview=removal_preview(g,rs[0]['root_id'],['쟁점1'])
    assert 'c' in preview['exclusive_source_ids']
    with pytest.raises(ValueError):review_removal(preview,{},adopted_roots={rs[1]['root_id']},delivered_evidence=set())
    r={'preview_hash':preview['preview_hash'],'alternatives':[{'root_evidence':rs[1]['root_id'],'issue':'쟁점1','reason':'대체 원문에서 같은 쟁점 근거를 확인'}]}
    assert review_removal(preview,r,adopted_roots={rs[1]['root_id']},delivered_evidence={rs[1]['root_id']})['decision']=='REMOVE'
    assert not review_removal(preview,r,adopted_roots={rs[1]['root_id']},delivered_evidence={rs[1]['root_id']})['legal_equivalence_certified']

def test_gap_original_numbering_proof_continues_and_rejects_guess():
    db=db_new();add(db,'a',1,'제2조제9항을 준용한다.')
    article(db,'b','d','모의규정','제2조','u2',[('200','제2조'),('209','⑨ 제3조를 준용한다.'),('210','⑩ 제4조를 준용한다.')],[])
    add(db,'c',3,'끝');add(db,'d',4,'별개');nav=navigator(db);rs=roots(nav,'a')
    first=nav.walk(rs);assert first['source_ids']==['a'];gap=first['gaps'][0]
    with pytest.raises(ValueError):nav.confirm_gap(gap['reference_id'],target_source_id='d',target_blocks=['400'],reason='이름 유사',actor='MODEL')
    receipt=nav.confirm_gap(gap['reference_id'],target_source_id='b',target_blocks=['209'],reason='DB에는 마디가 없지만 원문의 ⑨를 확인',actor='MODEL')
    assert receipt['target_extent']['block_ids']==['209'] and not receipt['canonical_db_mutated']
    result=nav.walk(rs);assert set(result['source_ids'])=={'a','b','c'}
    assert any(e['route_class']=='VERIFIED_DB_GAP' for e in result['edges'])
    assert all(e['reference_id']==gap['reference_id'] for e in nav.neighbors(nav.extent('b',['209']),'incoming'))
    stored=json.loads(db.execute('SELECT json FROM reference WHERE id=?',(gap['reference_id'],)).fetchone()[0]);assert not stored['targets']

def test_gap_no_unique_original_proof_stays_pending():
    db=db_new();add(db,'a',1,'제2조제9항을 준용한다.');add(db,'b',2,'비슷한 내용만 있고 항 좌표는 없다.');nav=navigator(db)
    gap=nav.walk(roots(nav,'a'))['gaps'][0]
    with pytest.raises(ValueError):nav.confirm_gap(gap['reference_id'],target_source_id='b',target_blocks=['200'],reason='관련해 보임',actor='MODEL')
    assert nav.walk(roots(nav,'a'))['source_ids']==['a']

def test_many_roots_match_independent_bfs_on_cold_topologies():
    rng=random.Random(521)
    for trial in range(12):
        db=db_new();n=12;adj={i:set() for i in range(n)}
        for i in range(n):
            for j in range(i+1,n):
                if rng.random()<.17:adj[i].add(j);adj[j].add(i)
        for i in range(n):add(db,str(i),i+1,' '.join(f'제{j+1}조를 준용한다.' for j in sorted(adj[i])) or '끝')
        nav=navigator(db);rs=roots(nav,*map(str,range(5)));w=nav.walk(rs)
        for root in rs:
            first=int(root['extent']['source_id']);seen={first};q=deque([first])
            while q:
                for nxt in adj[q.popleft()]-seen:seen.add(nxt);q.append(nxt)
            actual={int(sid) for sid,owners in w['owners'].items() if root['root_id'] in owners}
            assert actual==seen
        assert len(w['expanded_state_ids'])==len(set(w['expanded_state_ids']))

def test_v5_root_only_selection_protects_recursive_sources(tmp_path,term_glossary):
    raw=source(tmp_path/'raw.sqlite',[('d','모의승인규정',['제2조를 준용한다.','제3조를 준용한다.','승인 조건'])]);build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    with session(tmp_path,tmp_path/'built/generation') as s:
        r=read(s);root=r['evidence_ids'][0];v=s.view('investigate');delivered(s,v)
        s.commit_selection(v,{'choices':[{'source':root,'decision':'KEEP_CORE','reason':'승인 쟁점','issues':['승인 조건']}]})
        bundle=s.build_bundle();p=bundle['reference_bundle']
        assert len(p['sources'])==3 and len(bundle['sources'])==1
        assert {x['role'] for x in p['sources']}=={'ROOT','LINKED'}
        assert not p['all_preserved_sources_model_adopted']
        linked=next(e['evidence_id'] for e in s.work.evidence() if e['evidence_id']!=root)
        v=s.view('investigate');delivered(s,v)
        with pytest.raises(ProposalError):s.commit_selection(v,{'choices':[{'source':linked,'decision':'REJECT','reason':'연결만 제거'}]})
        assert len(s.build_bundle()['reference_bundle']['sources'])==3
        from semantic_runtime.legal_agent.source_bundle import validate_current
        result={'assembly':{'term_agent':{'source_bundle':s.build_bundle()}}}
        validate_current(s.work,result,s.sources.store,allowed_documents=['d'])

def test_v5_confirm_gap_read_and_continue(tmp_path,term_glossary):
    raw=source(tmp_path/'raw.sqlite',[('d','모의승인규정',['제2조제9항을 준용한다.','⑨ 제3조를 준용한다.','승인 조건'])]);build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    with session(tmp_path,tmp_path/'built/generation') as s:
        read(s);gap=next(n for n in s.work.notices() if n.get('route_class')=='REFERENCE_GAP')
        target=gap['targets'][0]['target']
        read_result=s.sources.execute(tool('read',target=target,extent='subtree',cursor=None),'inspect-gap')
        e=read_result['evidence_ids'][0]
        assert s.sources.read_origin({'target':e})['route_class']=='REFERENCE_GAP'
        result=s.sources.execute(tool('confirm_reference_gap',relation_id=gap['relation_id'],evidence=e),'confirm-gap')
        assert result['status']=='OK',result
        assert s.sources.read_origin({'target':e})['route_class']=='VERIFIED_DB_GAP'
        assert any(s.sources.tools.sources[x['source_id']]['heading'].startswith('제3조') for x in s.work.evidence())
        assert not s.root_evidence(e)

def test_complete_generation_rebuild_preserves_store_and_independent_copy(tmp_path,term_glossary):
    from lawrag.pipeline.reference_resolution import rebuild,generation_paths
    raw=source(tmp_path/'raw.sqlite',[('d','모의승인규정',['제2조제9항을 준용한다.','⑨ 승인 조건'])]);build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    before=tmp_path/'built/generation';after=tmp_path/'rebuilt'
    old_hash=__import__('hashlib').sha256((before/'navigation/navigation.sqlite').read_bytes()).hexdigest()
    result=rebuild(before,after)
    assert __import__('hashlib').sha256((before/'navigation/navigation.sqlite').read_bytes()).hexdigest()==old_hash
    assert (before/'navigation/navigation.sqlite').stat().st_ino!=(after/'navigation/navigation.sqlite').stat().st_ino
    assert generation_paths(after)[3]['schema_version']=='term-navigation-index-v4'
    assert result['counts']['reference_candidate']>0
    with session(tmp_path,after) as s:assert read(s)['status']=='OK'

def test_adopted_root_cannot_be_removed_without_replacement(tmp_path,term_glossary):
    raw=source(tmp_path/'raw.sqlite',[('d','모의승인규정',['제2조를 준용한다.','승인 조건','대체 승인 조건'])]);build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    with session(tmp_path,tmp_path/'built/generation') as s:
        a=read(s)['evidence_ids'][0];b=read(s,locator='모의승인규정 제3조',name='replacement')['evidence_ids'][0]
        v=s.view('investigate');delivered(s,v)
        s.commit_selection(v,{'choices':[{'source':e,'decision':'KEEP_CORE','reason':'승인 조건 근거','issues':['승인']} for e in (a,b)]})
        v=s.view('investigate');delivered(s,v)
        assert any(x.get('text') for p in v['root_removal_impacts'] for x in p['exclusive_extents'])
        with pytest.raises(ProposalError):s.commit_selection(v,{'choices':[{'source':a,'decision':'REJECT','reason':'단순 축소 시도'}]})
        assert len(s.build_bundle()['reference_bundle']['sources'])==3
        v=s.view('investigate');delivered(s,v);impact=next(x for x in s.root_impacts() if x['root_id']==a)
        s.commit_selection(v,{'choices':[{'source':a,'decision':'REJECT','reason':'대체 시작점의 원문 확인','removal_review':{'preview_hash':impact['preview_hash'],'alternatives':[{'root_evidence':b,'issue':'승인','reason':'대체 원문이 승인 조건을 포함'}]}}]})
        assert len(s.build_bundle()['reference_bundle']['sources'])==1

def test_large_bundle_preserved_and_ui_script_valid(tmp_path,term_glossary):
    from test_legal_agent_v5 import app_for
    import re,subprocess
    raw=source(tmp_path/'raw.sqlite',[('d','모의승인규정',[f'제{i+1}조를 준용한다.' for i in range(1,24)]+['마지막 승인 근거'])]);build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    with session(tmp_path,tmp_path/'built/generation') as s:
        root=read(s)['evidence_ids'][0];v=s.view('investigate');delivered(s,v)
        s.commit_selection(v,{'choices':[{'source':root,'decision':'KEEP_CORE','reason':'연결 원문 전체 보호'}]})
        bundle=s.build_bundle();assert len(bundle['reference_bundle']['sources'])==24
        assert bundle['reference_bundle']['graph']['status']=='COMPLETE'
    app=app_for(tmp_path,tmp_path/'built/generation')
    try:
        html=next(route.endpoint for route in app.routes if getattr(route,'path',None)=='/rag/')()
        js='\n'.join(re.findall(r'<script[^>]*>(.*?)</script>',html,re.S));path=tmp_path/'ui.js';path.write_text(js)
        subprocess.run(['node','--check',str(path)],check=True,capture_output=True)
    finally:app.state.pipeline.store.close()

def test_numbered_root_removal_roundtrip():
    from semantic_runtime.legal_agent.numbered_references import NumberedReferences
    from semantic_runtime.legal_agent.workflow_tiers_protocol import schema
    view={'exact_evidence':[{'evidence':'Ea'},{'evidence':'Eb'}],'root_removal_impacts':[{'root_id':'Ea'}]}
    aliases=NumberedReferences(view);assert aliases.view(view)['root_removal_impacts'][0]['root_id']==1
    raw={'choices':[{'source':1,'decision':'REJECT','reason':'대체 원문 근거 확인','removal_review':{'preview_hash':'a'*64,'alternatives':[{'root_evidence':2,'issue':'승인','reason':'다른 원문에서 근거 확인'}]}}]}
    decoded=aliases.decode(raw,aliases.schema(schema('SourceSelectionDecision')),'SourceSelectionDecision')
    assert decoded['choices'][0]['removal_review']['alternatives'][0]['root_evidence']=='Eb'
