from contextlib import closing
import json
from pathlib import Path
import sqlite3
from .test_glossary_enrichment import setup, Fake
import pytest
from lawrag.pipeline import glossary_enrichment as e
from lawrag.pipeline.glossary_scope import build_scope, article_scope, include_article
from lawrag.pipeline.collect_moleg_knowledge import _hash_file
from lawrag.pipeline.knowledge_transfer import unpack, dictionary, inspect_package


def generation(tmp_path):
    folder = tmp_path / 'generation';folder.mkdir()
    with closing(sqlite3.connect(folder / 'store.sqlite')) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT);
          CREATE TABLE source_unit(document_id TEXT,json TEXT);
          CREATE TABLE source_block(document_id TEXT,block_id TEXT,text TEXT);''')
        db.execute('INSERT INTO document VALUES (?,?,?)', ('law', '신탁법', 'a'*64))
        db.execute('INSERT INTO source_unit VALUES (?,?)', ('law', json.dumps({'family':'kr_article','surface':'제1조'})))
        db.execute('INSERT INTO source_unit VALUES (?,?)', ('law', json.dumps({'family':'kr_article','surface':'제1-2조'})))
        db.execute('INSERT INTO source_block VALUES (?,?,?)', ('law','1','“신탁”이란 이 법에서 정한 계약을 말한다.'))
        db.commit()
    (folder/'manifest.json').write_text(json.dumps({'store_sha256':_hash_file(folder/'store.sqlite')}))
    return folder


def test_scope_limits_requests_reuses_prior_responses_and_transfers_source_evidence(setup,tmp_path):
    state,_=setup
    old=e.run(state,'global',client=Fake())
    corpus=generation(tmp_path)
    fake=Fake(fail_at=1)
    result=e.run(state,'scoped',corpus_generation=corpus,
                 reuse_snapshot=state/'completion/global/collection.sqlite',client=fake)
    assert fake.calls==0
    assert result['total_requests']==4  # Two definitions, one legal relation, one article request.
    assert result['reused_responses']==4
    assert result['scope']['counts']['document']==1
    assert result['scope']['counts']['local_definition']==1
    assert result['scope']['counts']['seed_terms']==2
    assert result['coverage']['scoped_documents']==1
    assert result['coverage']['local_definition_evidence']==1
    assert result['coverage']['official_article_links']==1
    _,packages=unpack(result['zip'],tmp_path/'restored')
    assert dictionary(packages,tmp_path/'restored.sqlite')['coverage']==result['coverage']
    with closing(sqlite3.connect(result['dictionary'])) as db:
        assert db.execute('SELECT source_text FROM scope_definition').fetchone()[0].startswith('“신탁”이란')
    assert e.run(state,'scoped',corpus_generation=corpus,client=fake)['collection_complete']


def test_article_filter_excludes_other_laws_and_unselected_articles(setup,tmp_path):
    state,_=setup
    scope=build_scope(state/'alignment.sqlite',generation(tmp_path),tmp_path/'scope')
    allowed=article_scope(scope)
    assert allowed=={('신탁법','000100')}  # Hyphenated regulation articles are not JO codes.
    def row(name,jo):return {'label':name,'fields':{'조문연계용어링크':f'/DRF/lawService.do?ID=000001&JO={jo}'}}
    assert include_article(row('신탁법','000100'),allowed)
    assert not include_article(row('다른법','000100'),allowed)
    assert not include_article(row('신탁법','000200'),allowed)


def test_no_matching_terms_cannot_fall_back_to_global_collection(setup,tmp_path):
    state,_=setup;corpus=generation(tmp_path)
    with closing(sqlite3.connect(corpus/'store.sqlite')) as db:
        db.execute("UPDATE source_block SET text='아무 관련이 없는 문장'");db.commit()
    (corpus/'manifest.json').write_text(json.dumps({'store_sha256':_hash_file(corpus/'store.sqlite')}))
    with pytest.raises(ValueError,match='do not collect globally'):
        e.run(state,'empty',corpus_generation=corpus,client=Fake())


def test_reuse_refuses_tampered_raw_response(setup,tmp_path):
    state,_=setup;e.run(state,'global',client=Fake())
    old=state/'completion/global/collection.sqlite'
    with closing(sqlite3.connect(old)) as db:
        db.execute("UPDATE request SET response_sha256='tampered' WHERE endpoint='legal_term_detail'");db.commit()
    with pytest.raises(ValueError,match='hash mismatch'):
        e.run(state,'scoped',corpus_generation=generation(tmp_path),reuse_snapshot=old,client=Fake())



def test_publish_removes_out_of_scope_article_but_preserves_raw_response(setup,tmp_path):
    from lawrag.sources.moleg_knowledge import parse_xml_page, ENDPOINTS
    import gzip
    class Extra(Fake):
        def fetch(self,endpoint,parameters):
            xml,parsed=super().fetch(endpoint,parameters)
            if endpoint=='term_articles':
                extra='<연계법령><법령명>다른법</법령명><조번호>0001</조번호><조가지번호>00</조가지번호><조문연계용어링크>/DRF/lawService.do?target=joRltLstrm&amp;ID=000002&amp;JO=000100</조문연계용어링크></연계법령>'
                xml=xml.replace('</법령용어>',extra+'</법령용어>')
                parsed=parse_xml_page(xml,ENDPOINTS[endpoint])
            return xml,parsed
    state,_=setup
    result=e.run(state,'filtered',corpus_generation=generation(tmp_path),client=Extra())
    assert result['coverage']['official_article_links']==1
    package=next(p for p in result['packages'] if inspect_package(p)[1]=='term_articles')
    _,_,artifacts,plan=inspect_package(package)
    assert plan['excluded_by_scope']==1
    assert '다른법' not in artifacts['records.jsonl'].resolved_path().read_text()
    assert '다른법' in gzip.decompress(artifacts['responses.xml.gz'].resolved_path().read_bytes()).decode()


def test_relation_only_collection_preserves_daily_edge_without_recursive_requests(setup, tmp_path):
    state, _ = setup
    corpus = generation(tmp_path)
    client = Fake()
    result = e.run(state, 'relations', corpus_generation=corpus,
                   endpoints=['legal_term_relations'], client=client)
    assert client.calls == 1
    assert result['collection_complete'] and result['collection_only']
    assert result['total_requests'] == 1
    assert result['request_endpoints'] == ['legal_term_relations']
    assert not (state / 'COMPLETED.json').exists()
    assert not (state / 'completion/relations/dictionary.sqlite').exists()
    with closing(e.connect(state / 'completion/relations/collection.sqlite')) as db:
        rows = json.loads(db.execute('SELECT records FROM request').fetchone()[0])
        assert e.relation_target(rows[0]) == 'moleg:everyday_terms:21'
    no_network = Fake(fail_at=1)
    e.run(state, 'relations', corpus_generation=corpus,
          endpoints=['legal_term_relations'], client=no_network)
    assert no_network.calls == 0
    with pytest.raises(ValueError, match='new completion snapshot'):
        e.run(state, 'relations', corpus_generation=corpus,
              endpoints=['term_articles'], client=no_network)


def test_endpoint_filter_requires_corpus_scope(setup):
    state, _ = setup
    with pytest.raises(ValueError, match='corpus scope'):
        e.run(state, 'unsafe', endpoints=['legal_term_relations'], client=Fake())
    assert not (state / 'completion/unsafe').exists()


def test_officially_missing_relation_is_empty_but_errors_still_stop(setup, tmp_path):
    from lawrag.sources.moleg_knowledge import parse_xml_page, ENDPOINTS
    class MissingRelation(Fake):
        def fetch(self, endpoint, parameters):
            assert endpoint == 'legal_term_relations'
            self.calls += 1
            xml = '<Law>일치하는 법령용어가 없습니다. 검색조건을 확인하여 주십시오.</Law>'
            return xml, parse_xml_page(xml, ENDPOINTS[endpoint])
    state, _ = setup
    result = e.run(state, 'missing-relation', corpus_generation=generation(tmp_path),
                   endpoints=['legal_term_relations'], client=MissingRelation())
    assert result['collection_complete']
    assert result['empty_responses'] == [{'endpoint': 'legal_term_relations', 'count': 1}]
    for xml in ['<Law>인증키를 확인하여 주십시오.</Law>',
                '<Law>일시적인 오류입니다.</Law>', '<error/>']:
        with pytest.raises(ValueError, match='envelope'):
            e.validate_response('legal_term_relations', {'MST': '20'}, xml, [])
