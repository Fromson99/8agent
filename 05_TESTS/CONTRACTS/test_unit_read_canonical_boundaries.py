"""Opt-in regression for real navigation source grouping, with synthetic originals."""
import json
import sqlite3
import pytest
from test_unit_fulltext_adaptive_read import unit_fts, ur, SourceRecall
from test_document_release import source
from test_bounded_source_main import settings
from test_legal_agent_v5 import app_for
from test_unified_legal_agent import ScriptedTransport
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.legal_agent.errors import ContractError


@pytest.fixture
def grouped(tmp_path, term_glossary):
    raw = source(tmp_path/'raw.sqlite', [('chap','모의장규정',
        ['제1장 승인','제1조 승인 규칙','① 긴급 승인 예외']),
        ('blob','모의독립본문',['구조 정보가 없는 독립 원문'])])
    with sqlite3.connect(raw) as db:
        db.execute("DELETE FROM source_unit WHERE document_id='chap'")
        for uid,parent,family,label,span in [
            ('0',None,'kr_장','제1장',[0,3]),
            ('1','0','kr_article','제1조',[1,3]),
            ('2','1','circled','①',[2,3])]:
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',
                ('chap',uid,parent,json.dumps({'family':family,'surface':label,'title':'','span':span},ensure_ascii=False)))
        db.execute("UPDATE source_block SET unit_id=NULL WHERE document_id='blob'")
        db.execute("DELETE FROM source_unit WHERE document_id='blob'")
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    gen=tmp_path/'built/generation';path=tmp_path/'index'
    unit_fts.build(gen,gen/'navigation',path,workers=1)
    index=unit_fts.UnitFulltextIndex(path,json.loads((gen/'navigation/manifest.json').read_text()))
    app=app_for(tmp_path,gen,ScriptedTransport(),settings())
    p=app.state.pipeline;p.term_agent.unit_fulltext=index
    request={'question':'승인','document_ids':['chap','blob'],'use_llm':False}
    try:
        with p.term_agent.open_session(request,query=p.plan('승인',['chap','blob']),runtime=tmp_path/'runtime') as session:
            yield session.sources,index
    finally:p.store.close()


def first_hit(index,word):
    with index.connect() as db:
        return index.rank_units(db,[word])[0]


def chapter_hit(s):
    source=next(v for v in s.tools.sources.values() if v['document_id']=='chap' and str(v['unit_id'])=='0')
    return {'key':source['id']+'#unit:0','source_id':source['id'],'document_id':'chap',
        'unit_id':'0','article_unit_id':'0','document_name':source['document_name'],'heading':source['heading'],'match_paths':[]}


def test_chapter_heading_can_be_read_but_expansion_across_articles_is_unoffered(grouped):
    s,index=grouped;hit=chapter_hit(s)
    offered,blocked=ur.offer_plan(s,hit)
    assert [o['id'] for o in offered]==['exact:0']
    assert blocked==[{'unit_id':'0','extent':'subtree','reason':'subtree_crosses_canonical_source_boundary','outside_block_ids':['1','2']}]
    result=ur.read(s,hit,offered[0],action_state={'count':0,'chars':0})
    assert result['complete'] and result['text']=='제1장 승인'
    assert not result['offer']['article_complete']


def test_unoffered_chapter_subtree_still_fails_closed(grouped):
    s,index=grouped;hit=chapter_hit(s);offer=ur.offers(s,hit)[0]
    with pytest.raises(ContractError,match='unoffered'):
        ur.read(s,hit,{**offer,'id':'subtree:0','extent':'subtree','block_ids':['0','1','2']},action_state={'count':0,'chars':0})


def test_block_only_source_reads_with_no_invented_structure(grouped):
    s,index=grouped;hit=first_hit(index,'독립')
    assert str(hit['unit_id'])=='None' and str(hit['article_unit_id'])=='None'
    offered,blocked=ur.offer_plan(s,hit)
    assert len(offered)==1 and not blocked and offered[0]['reader_target']=='source'
    result=ur.read(s,hit,offered[0],action_state={'count':0,'chars':0})
    assert result['complete'] and result['text']=='구조 정보가 없는 독립 원문'
    assert {e['source_id'] for e in result['evidence']}=={hit['source_id']}


def test_recall_records_unavailable_expansion_without_aborting_other_hits(grouped):
    s,index=grouped;head=chapter_hit(s);body=first_hit(index,'긴급')
    recall=SourceRecall(s)
    recall.discover=lambda:([head['source_id'],body['source_id']],{'discovery_mode':'fulltext','routes':{},'unit_hits':[head,body]})
    record=recall.prepare()
    assert len(record['unit_reads'])==2
    assert record['unit_reads'][0]['unavailable_read_options']
    assert 'subtree:1' in {o['id'] for o in record['unit_reads'][1]['offers']}
    assert len(record['selection_complete'])==2
