"""Scoped glossary construction contracts, with synthetic source responses."""
from contextlib import closing
import json
import sqlite3
from pathlib import Path
import pytest

from .test_glossary_scope import setup, generation, Fake
from lawrag.pipeline import glossary_enrichment as e
from lawrag.pipeline import glossary_assembly as a
from lawrag.pipeline import glossary_v1 as v1
from lawrag.pipeline.collect_moleg_knowledge import _hash_file


@pytest.fixture
def assembly_inputs(setup,tmp_path):
    state,_=setup
    with sqlite3.connect(state/'alignment.sqlite') as db:
        row=json.loads(db.execute("SELECT payload FROM terms WHERE id='moleg:knowledge_terms:20'").fetchone()[0])
        row.update(source_id='21',label='채권',fields={'용어간관계링크':'/DRF/lawService.do?target=lstrmRlt&MST=21'})
        db.execute('INSERT INTO terms VALUES (?,?,?,?,?,?)',('moleg:knowledge_terms:21','moleg-knowledge-knowledge-terms','채권',1,'fixture21',json.dumps(row)))
    corpus=generation(tmp_path)
    with sqlite3.connect(corpus/'store.sqlite') as db:
        db.execute('ALTER TABLE source_block ADD COLUMN unit_id TEXT')
        db.execute('ALTER TABLE source_unit ADD COLUMN unit_id TEXT')
        db.execute('ALTER TABLE source_unit ADD COLUMN parent_id TEXT')
        db.execute("UPDATE source_unit SET unit_id=CAST(rowid AS TEXT)")
        db.execute("UPDATE source_block SET unit_id='1'")
        db.execute("INSERT INTO source_block VALUES ('law','2','채권은 별도 항목이다.','article')")
    (corpus/'manifest.json').write_text(json.dumps({'store_sha256':_hash_file(corpus/'store.sqlite')}))
    e.run(state,'partial',corpus_generation=corpus,endpoints=['legal_term_relations'],plan_only=True)
    collection=state/'completion/partial/collection.sqlite'
    # Collect the explicit seed used by the source-relation assertions.
    with closing(e.connect(collection)) as db:
        original=db.execute("SELECT id FROM request WHERE parameters=?",(json.dumps({'MST':'21'}),)).fetchone()[0]
        db.execute("UPDATE request SET status='complete',records='[]' WHERE id=?",(original,));db.commit()
        e.collect(db,Fake(),max_requests=1,emit=lambda *a,**k:None)
        db.execute("UPDATE request SET status='pending',records=NULL WHERE id=?",(original,));db.commit()
    external=tmp_path/'external'
    for source,rows in [('econedu',[('trust','신탁'),('daily','수탁'),('gap','미연결어')]),('nts',[('trust','신탁')])]:
        folder=external/source;folder.mkdir(parents=True)
        with (folder/'entries.jsonl').open('w') as stream:
            for ident,term in rows:
                stream.write(json.dumps({'id':source+':'+ident,'source':source,'term':term,'definition':source+'의 서로 다른 설명'},ensure_ascii=False)+'\n')
    return collection,external,corpus,tmp_path/'assembled'


def test_partial_scope_relations_finance_candidates_and_no_automatic_meaning_merge(assembly_inputs):
    result=a.build(*assembly_inputs,emit=lambda *a,**k:None)
    assert result['collection']['states']=={'complete':1,'pending':1}
    assert result['collection']['complete'] is False
    assert result['counts']['official_relation']==1
    assert result['counts']['meaning']==result['counts']['membership']==0
    assert not result['runtime_promoted'] and not result['canonical_approval']
    with sqlite3.connect(assembly_inputs[-1]/'dictionary.sqlite') as db:
        assert db.execute("SELECT 1 FROM entry WHERE id='moleg:everyday_terms:30'").fetchone() is None
        assert db.execute("SELECT corpus_class FROM classification WHERE entry_id='econedu:daily'").fetchone()[0]=='GENERAL_IN_THIS_CORPUS'
        assert db.execute("SELECT corpus_class FROM classification WHERE entry_id='econedu:trust'").fetchone()[0]=='CORPUS_PRESENT'
        assert db.execute("SELECT status FROM review_queue WHERE entry_id='econedu:gap'").fetchone()[0]=='WAITING_FOR_RELATIONS'
    detail=a.inspect(assembly_inputs[-1],'수탁')
    assert detail['candidates'][0]['legal_entry_id']=='moleg:knowledge_terms:20'
    assert detail['candidates'][0]['matched_entry_id']=='moleg:everyday_terms:21'
    assert detail['candidates'][0]['relation_code']=='140303'  # Preserve broader, never promote to synonym.
    assert detail['candidates'][0]['status']=='MEANING_REVIEW'


def test_new_collection_progress_rebuilds_a_new_version_and_preserves_previous(assembly_inputs,tmp_path):
    collection,external,corpus,output=assembly_inputs
    old=a.build(*assembly_inputs,emit=lambda *a,**k:None)
    with closing(e.connect(collection)) as db:
        e.collect(db,Fake(),emit=lambda *a,**k:None)
    new_output=tmp_path/'next'
    new=a.build(collection,external,corpus,new_output,emit=lambda *a,**k:None)
    assert new['collection']['complete'] and not old['collection']['complete']
    assert new['identity']['collection_content_sha256'] != old['identity']['collection_content_sha256']
    assert a.inspect(output)['dictionary_sha256']==old['dictionary_sha256']
    with sqlite3.connect(new_output/'dictionary.sqlite') as db:
        assert db.execute("SELECT status FROM review_queue WHERE entry_id='econedu:gap'").fetchone()[0]=='UNLINKED_REVIEW'
    with pytest.raises(ValueError,match='already exists'):a.build(*assembly_inputs)


@pytest.mark.parametrize('tamper',['response','scope','plan','corpus'])
def test_rejects_wrong_or_tampered_source(assembly_inputs,tamper):
    collection,external,corpus,output=assembly_inputs
    if tamper=='response':
        with sqlite3.connect(collection) as db:db.execute("UPDATE request SET response_sha256='bad' WHERE status='complete'")
    elif tamper=='scope':
        with sqlite3.connect(collection.parent/'scope.sqlite') as db:db.execute('DELETE FROM occurrence')
    elif tamper=='plan':
        with sqlite3.connect(collection) as db:db.execute("DELETE FROM request WHERE status='pending'")
    else:
        with sqlite3.connect(corpus/'store.sqlite') as db:db.execute("UPDATE source_block SET text='changed'")
    with pytest.raises(ValueError):a.build(*assembly_inputs,emit=lambda *a,**k:None)
    assert not output.exists()


def test_build_freezes_live_progress_before_scanning(assembly_inputs):
    collection,external,corpus,output=assembly_inputs
    def emit(message,**kwargs):
        if 'froze' in message:
            with closing(e.connect(collection)) as db:e.collect(db,Fake(),emit=lambda *a,**k:None)
    result=a.build(*assembly_inputs,emit=emit)
    assert result['collection']['states']=={'complete':1,'pending':1}
    with sqlite3.connect(collection) as db:
        assert db.execute("SELECT count(*) FROM request WHERE status='complete'").fetchone()[0]==2


def test_cli_build_and_inspect_dispatch(assembly_inputs,capsys):
    collection,external,corpus,output=assembly_inputs
    assert a.main(['--relations-db',str(collection),'--external-dir',str(external),'--corpus-generation',str(corpus),'--output',str(output)])==0
    capsys.readouterr()
    assert a.main(['--output',str(output),'--inspect','--term','신탁'])==0
    result=json.loads(capsys.readouterr().out)
    assert len([e for e in result['entries'] if e['source'] in {'econedu','nts'}])==2


def test_definitions_translations_and_navigation_are_not_collapsed(assembly_inputs,tmp_path):
    import gzip,hashlib
    from lawrag.sources.moleg_knowledge import ENDPOINTS,parse_xml_page
    records=[]
    for ident,code,text in [('11','011402','권리의 이전에 관한 설명'),('12','011403','trust'),
                            ('13','011405','안내 링크'),('14','999999','미분류 자료')]:
        records.append(f'<법령용어><법령용어일련번호>{ident}</법령용어일련번호><법령용어명_한글>신탁</법령용어명_한글><법령용어코드>{code}</법령용어코드><법령용어정의>{text}</법령용어정의></법령용어>')
    raw=('<LsTrmService>'+''.join(records)+'</LsTrmService>').encode()
    params={'trmSeqs':'11,12,13,14'}
    parsed=parse_xml_page(raw.decode(),ENDPOINTS['legal_term_detail'])
    normalized=[dict(r,_request=params,_request_id='details') for r in parsed.records]
    path=tmp_path/'details.sqlite'
    with closing(e.connect(path)) as db:
        db.execute('INSERT INTO request(id,endpoint,parameters,status,response,response_sha256,records) VALUES (?,?,?,?,?,?,?)',
            ('details','legal_term_detail',json.dumps(params),'complete',gzip.compress(raw),hashlib.sha256(raw).hexdigest(),json.dumps(normalized)))
        db.commit()
    result=a.build(*assembly_inputs,definitions=[path],emit=lambda *a,**k:None)
    assert result['counts']['definition_content_types']=={'EXPLANATION':1,'TRANSLATION':1,'NAVIGATION':1,'UNTYPED_SOURCE_CONTENT':1}
    detail=a.inspect(assembly_inputs[-1],'신탁')
    assert any(r['match_kind']=='SOURCE_ID' for r in detail['definitions'])
    assert any(r['match_kind']=='LABEL_CANDIDATE' for r in detail['definitions'])
    assert result['counts']['meaning']==0


def test_catalogue_classification_independent_of_source_and_official_relation(assembly_inputs):
    a.build(*assembly_inputs,emit=lambda *a,**k:None)
    daily=a.inspect(assembly_inputs[-1],'수탁')
    assert daily['entries'] and all(e['term_class']=='EVERYDAY_TERM' for e in daily['entries'])
    legal=a.inspect(assembly_inputs[-1],'신탁')
    assert any(e['source']=='econedu' and e['term_class']=='LEGAL_TERM' for e in legal['entries'])
    assert legal['official_relations']
    assert all('source_term_class' in r and 'target_term_class' in r for r in legal['official_relations'])
    assert legal['article_connections']['official_api_links']=='NOT_COMPILED_IN_THIS_DRAFT'
    assert legal['article_connections']['corpus_literal_occurrences']>0
