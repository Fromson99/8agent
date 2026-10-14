from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0718/repaired/snapshot';L=C/'02_BACKEND/semantic_runtime/legal_agent'
p=L/'request_repair.py';s=p.read_text();s=s.replace("            if code == 'MISSING_COORDINATE' and len(docs) == 1 and len(coordinates) == 1:","""            indexed_complete=False
            if len(docs)==1 and len(coordinates)==1:
                did=next(iter(docs))
                # A missing index entry is not source absence if the stored tree
                # lacks coordinate bindings. Partial/legacy trees stay unknown.
                nodes=[(key,u) for key,u in session.matcher.units.items() if key[0]==did
                       and (u.get('family')=='kr_article' or bool(coordinates[0].coordinate.chain))]
                indexed_complete=bool(nodes) and all(
                    u.get('coordinate_scope') is not None
                    and session.matcher.stored_coordinates.get(key) is not None
                    and u.get('coordinate_binding',{}).get('mode')!='unresolved' for key,u in nodes)
            if code == 'MISSING_COORDINATE' and len(docs) == 1 and len(coordinates) == 1 and indexed_complete:""")
p.write_text(s)
p=L/'completion_execution.py';s=p.read_text().replace("        modern=rr.enabled(self.s.sources.profile)\n        contract=cc.version(self.s.sources.profile)","        profile=getattr(self.s.sources,'profile',{})\n        modern=rr.enabled(profile)\n        contract=cc.version(profile)");p.write_text(s)
p=L/'request_entry.py';s=p.read_text().replace('scoped=enabled(session.sources.profile)','scoped=enabled(repo.executor.model.pipeline.term_agent.profile)');p.write_text(s)
p=C/'05_TESTS/CONTRACTS/test_main50_request_repair.py';s=p.read_text().replace('from test_unit_fulltext_adaptive_read import tree,session,hit','from test_unit_fulltext_adaptive_read import tree as legacy_tree,session,hit\nfrom lawrag.pipeline.term_generation import build_generation\nfrom lawrag.core.legal_coordinate import find_coordinates\nfrom semantic_runtime.unit_fulltext import build,UnitFulltextIndex\nimport sqlite3')
pos=s.index('\ndef modern(')
s=s[:pos]+'''
@pytest.fixture
def tree(tmp_path,term_glossary):
    legacy_tree.__wrapped__(tmp_path,term_glossary)
    raw=tmp_path/'raw.sqlite'
    with sqlite3.connect(raw) as db:
        for did,uid,text in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
            u=json.loads(text)
            if u['family']=='kr_article':
                coordinate=find_coordinates(u['surface'])[0].coordinate
                u.update(legal_coordinate=coordinate.as_dict(),coordinate_scope='body',coordinate_key='body:'+coordinate.canonical_surface())
                db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',(json.dumps(u,ensure_ascii=False),did,uid))
    build_generation(raw,term_glossary,tmp_path/'bound',serving=True)
    gen=tmp_path/'bound/generation';idx=tmp_path/'bound-index'
    build(gen,gen/'navigation',idx,workers=1)
    return gen,UnitFulltextIndex(idx,json.loads((gen/'navigation/manifest.json').read_text()))

'''+s[pos:]
s+='''

def test_partial_coordinate_index_cannot_prove_absence(session):
    native,_=session;m=native.sources.matcher
    key=next(k for k,u in m.units.items() if k[0]=='d' and u.get('family')=='kr_article')
    old=m.units[key];m.units={**m.units,key:{**old,'coordinate_scope':None}}
    target=rr.bind_gap({**GAP,'missing_target':'모의승인규정 제99조'},native.sources)
    assert target['target_binding']['absence_proven'] is False


def test_memory_peak_is_observed_within_request_not_final_rss(monkeypatch):
    from semantic_runtime import execution_metrics as em
    values=iter([100,700,200,150]);monkeypatch.setattr(em,'resident_bytes',lambda:next(values))
    m=em.Metrics();m.sample_memory();m.sample_memory();v=m.snapshot()['memory']
    assert v['start_bytes']==100 and v['peak_observed_bytes']==700 and v['latest_bytes']==150
    assert v['exclusive_request_allocation'] is False
'''
p.write_text(s)
