"""Source definition boundaries and cross-provider occurrence connections."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import pytest
from .test_glossary_assembly import assembly_inputs,setup
from .test_glossary_review import Fake
from lawrag.pipeline import glossary_assembly as a,glossary_definitions as d,glossary_review as r


def source_store():
    db=sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
        CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT);''')
    for did in ['A','B']:
        db.execute('INSERT INTO document VALUES (?,?,?)',(did,did+'법',did*64))
        db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',(did,'1',None,json.dumps({'family':'kr_article','surface':'제2조'})))
    return db


def test_scopes_homonyms_offsets_and_references_are_preserved():
    with closing(source_store()) as src,closing(sqlite3.connect(':memory:')) as out:
        a.tables(out)
        texts=[('A','1','이 조에서 “공통어”란 「다른법」 제3조에 따른 자산을 말한다. 다만, 예외가 있다.'),
               ('B','1','“공통어”란 부채를 말한다.'),
               ('B','2','이 법에서 “미완성어”란 다음 각 호의 어느 하나에 해당하는 것:')]
        src.executemany('INSERT INTO source_block VALUES (?,?,?,?)',[(x,y,'1',t) for x,y,t in texts])
        d.add(out,src,'c'*64)
        out.row_factory=sqlite3.Row
        rows=[dict(x) for x in out.execute('SELECT * FROM corpus_definition ORDER BY document_id,block_id')]
        assert len(rows)==3 and rows[0]['id']!=rows[1]['id']
        for row in rows:
            entry=out.execute('SELECT * FROM entry WHERE id=?',(row['id'],)).fetchone()
            assert row['source_text'][row['term_start']:row['term_end']]==entry['label']
            assert row['source_text'][row['definition_start']:row['definition_end']]==entry['definition']
            assert hashlib.sha256(row['source_text'].encode()).hexdigest()==row['source_text_sha256']
        assert rows[0]['scope_status']=='EXPLICIT_SCOPE_HINT'
        assert json.loads(rows[0]['scope_hint'])[0]['kind']=='조'
        assert rows[1]['scope_status']=='UNRESOLVED'
        assert rows[2]['definition_status']=='CONTINUATION_REQUIRED'
        assert json.loads(rows[0]['reference_hints'])[0]['resolution']=='UNREVIEWED'
        assert '다만' in rows[0]['source_text']
        assert json.loads(rows[0]['location'])[0]['surface']=='제2조'
        assert out.execute('SELECT count(*) FROM meaning').fetchone()[0]==0


def test_finance_term_without_moleg_gets_occurrence_and_local_definition_links(assembly_inputs,tmp_path):
    collection,external,corpus,output=assembly_inputs
    # This fixture changes the bound corpus before selecting a fresh collection scope.
    from lawrag.pipeline import glossary_enrichment as enrichment
    with sqlite3.connect(corpus/'store.sqlite') as db:
        db.execute("INSERT INTO source_block VALUES ('law','3','마진콜은 본문에 등장한다.','1')")
        db.execute("INSERT INTO source_block VALUES ('law','4','이 조에서 “PF대출”이란 특정 사업을 위한 대출을 말한다.','1')")
    (corpus/'manifest.json').write_text(json.dumps({'store_sha256':a.v1.sha(corpus/'store.sqlite')}))
    enrichment.run(collection.parents[2],'newscope',corpus_generation=corpus,endpoints=['legal_term_relations'],plan_only=True)
    collection=collection.parents[1]/'newscope/collection.sqlite'
    with (external/'econedu/entries.jsonl').open('a') as f:
        for term in ['마진콜','PF대출']:
            f.write(json.dumps({'id':'econedu:'+term,'source':'econedu','term':term,'definition':'금융 사전 설명'},ensure_ascii=False)+'\n')
    a.build(collection,external,corpus,output,emit=lambda *a,**k:None)
    with sqlite3.connect(output/'dictionary.sqlite') as db:
        assert db.execute("SELECT status FROM review_queue WHERE entry_id='econedu:마진콜'").fetchone()[0]=='CORPUS_LINKED'
        assert db.execute("SELECT count(*) FROM entry_corpus_link WHERE entry_id='econedu:마진콜'").fetchone()[0]==1
        assert db.execute("SELECT count(*) FROM entry_definition_link WHERE entry_id='econedu:PF대출'").fetchone()[0]==1
        assert db.execute("SELECT count(*) FROM external_candidate WHERE external_id='econedu:마진콜'").fetchone()[0]==0
        assert db.execute("SELECT basis FROM external_candidate WHERE external_id='econedu:PF대출'").fetchone()[0]=='LOCAL_DEFINITION_LABEL'
    assert a.inspect(output,'PF대출')['corpus_definitions'][0]['document_name']=='신탁법'
    assert a.inspect(output,'마진콜')['corpus_occurrences']


def test_sample_run_compile_e2e_is_bounded_and_keeps_definitions(assembly_inputs,tmp_path):
    a.build(*assembly_inputs,emit=lambda *a,**k:None)
    state=tmp_path/'sample';plan=r.prepare(assembly_inputs[-1],state,sample_jobs=1)
    assert plan['total_jobs']==1 and plan['deferred']['OUTSIDE_SAMPLE']>0
    provider=Fake();r.run(state,max_jobs=10,provider=provider)
    assert provider.calls==1
    output=tmp_path/'sample-compiled';report=r.compile_proposals(state,output)
    assert report['counts']['corpus_definitions']==a.inspect(assembly_inputs[-1])['counts']['corpus_definitions']
    assert report['llm_review']['identity']['sample_jobs']==1
    assert not report['canonical_approval']
    with sqlite3.connect(state/'review.sqlite') as db:
        context=json.loads(db.execute('SELECT input_json FROM job').fetchone()[0])
        assert context['target']['source']=='corpus_definition'
        assert all(x['kind'] in {'SOURCE_DESCRIPTION','SOURCE_DEFINITION','CORPUS_DEFINITION','DEFINITION_CONTEXT'} for x in context['evidence'])


def test_ancestry_cycle_fails_instead_of_inventing_scope():
    with pytest.raises(ValueError,match='Cyclic'):
        d.location_for('1',{'1':('2','{}'),'2':('1','{}')})
