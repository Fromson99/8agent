"""Synthetic contracts for glossary v1. No providers or retrieval-quality evaluation."""
import json
from pathlib import Path
import sqlite3

import pytest

from lawrag.pipeline import glossary_v1 as v1


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False))


@pytest.fixture
def inputs(tmp_path):
    catalogue=tmp_path/'alignment.sqlite'
    with sqlite3.connect(catalogue) as db:
        db.execute('CREATE TABLE terms(id TEXT PRIMARY KEY,payload TEXT)')
        for ident,label,note in [('investment','투자',''),('trust','신탁',''),('fund','투자신탁',''),
                                 ('bond_a','채권','청구할 권리'),('bond_b','채권','발행하는 증권'),
                                 ('refund','환불',''),('return','반품','')]:
            db.execute('INSERT INTO terms VALUES (?,?)',(ident,json.dumps({'label':label,'fields':{'비고':note}})))
    external=tmp_path/'external'
    for name in ('econedu','nts'):
        (external/name).mkdir(parents=True)
        rows=([{'id':'econ:etf','source':'econedu','term':'ETF(상장지수펀드)','definition':'표제어 원문 설명'},
               {'id':'econ:fund','source':'econedu','term':'투자신탁','definition':'교육 설명'}] if name=='econedu' else
              [{'id':'nts:a','source':'nts','term':'별도용어','definition':'설명'}])
        (external/name/'entries.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    corpus=tmp_path/'corpus';corpus.mkdir()
    with sqlite3.connect(corpus/'store.sqlite') as db:
        db.executescript('''CREATE TABLE document(document_id TEXT,name TEXT);
          CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT);
          CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);''')
        db.execute('INSERT INTO document VALUES (?,?)',('doc','합성 규정'))
        for i,text in enumerate(('투자신탁의 조건이다.','채권을 확인한다.','상장지수펀드의 설명이다.','반품을 처리한다.')):
            db.execute('INSERT INTO source_block VALUES (?,?,?,?,?)',('doc',str(i),'article',text,'synthetic-hash'))
        db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',('doc','article',None,json.dumps({'title':'제1조 합성 조문','family':'kr_조'})))
    with sqlite3.connect(corpus/'links.sqlite') as db:
        db.execute('CREATE TABLE edge(source TEXT,target TEXT,kind TEXT,provenance TEXT)')
        db.execute('INSERT INTO edge VALUES (?,?,?,?)',('refund','return','RELATED','synthetic-relation-proof'))
    store_hash=v1.sha(corpus/'store.sqlite')
    dump(corpus/'manifest.json',{'store_sha256':store_hash,'term_links':{'enabled':True,'path':'links.sqlite',
         'sha256':v1.sha(corpus/'links.sqlite'),'source_store_sha256':store_hash}})
    return catalogue,external,corpus,tmp_path/'output'


def compile_glossary(inputs,**kwargs):
    v1.build(*inputs,emit=lambda *a,**k:None,**kwargs)
    return v1.Glossary(inputs[-1])


def test_build_longest_original_offsets_and_unmatched(inputs):
    g=compile_glossary(inputs)
    try:
        result=g.query('투자 신탁을 안해지했고 신탁은?')
        assert [m['surface'] for m in result['mentions']]==['투자 신탁','신탁']
        assert {s['surface'] for s in result['suppressed']}=={'투자','신탁'}
        assert result['mentions'][0]['status']=='CHOICE_REQUIRED'
        assert result['mentions'][0]['choice_count']==2
        assert result['mentions'][0]['classification']=='CORPUS_PRESENT'
        assert result['unmatched']==[{'start':7,'end':12,'text':'안해지했고'}]
        assert [r['text'] for r in result['language_tokens']]==['을','은']
        assert g.query('신탁업')['mentions']==[]
        assert g.query('투자신탁')['mentions'][0]['surface']=='투자신탁'
    finally:g.close()


def test_homonyms_not_merged_and_choice_bound_to_question(inputs):
    g=compile_glossary(inputs)
    try:
        q=g.query('채권은?'); m=q['mentions'][0]
        assert m['status']=='CHOICE_REQUIRED' and m['choice_count']==2
        assert {o['description'] for o in m['choices']}=={'청구할 권리','발행하는 증권'}
        choices={'query_id':q['query_id'],'choices':{m['id']:m['choices'][0]['id']}}
        selected=g.query('채권은?',selections=choices)
        result=g.articles(selected)
        assert result['mentions'][0]['status']=='SELECTED'
        hit=result['mentions'][0]['hits'][0]
        assert hit['ancestors'][0]['title']=='제1조 합성 조문'
        assert hit['sense_applicability']=='UNREVIEWED'
        assert g.articles(g.query('채권은?'))['mentions'][0]['hits']==[]
        with pytest.raises(ValueError,match='bound'):g.query('채권을?',selections=choices)
        choices['choices'][m['id']]='entry:made-up'
        with pytest.raises(ValueError,match='not a candidate'):g.query('채권은?',selections=choices)
    finally:g.close()


def test_reviewed_group_does_not_duplicate_sources_and_alias_can_route(inputs,tmp_path):
    review=tmp_path/'review.json'
    dump(review,{'meanings':[{'id':'fund','label':'투자신탁','description':'합성 검토 의미',
         'entry_ids':['fund','econ:fund'],'evidence':'합성 단위 테스트 검토 기록'}],
         'aliases':[{'surface':'시험별칭','meaning_id':'fund','evidence':'합성 명시적 별칭'}]})
    g=compile_glossary(inputs,review=review)
    try:
        q=g.query('투자신탁을');assert q['mentions'][0]['status']=='RESOLVED'
        assert q['mentions'][0]['choice_count']==1
        assert len(q['mentions'][0]['selected']['source_entries'])==2
        q=g.articles(g.query('시험별칭'))
        assert q['mentions'][0]['hits'][0]['text']=='투자신탁의 조건이다.'
        assert q['mentions'][0]['classification']=='GENERAL_IN_THIS_CORPUS'
    finally:g.close()


def test_source_label_parts_and_optional_related_expansion(inputs):
    g=compile_glossary(inputs)
    try:
        q=g.articles(g.query('ETF를'))
        assert q['mentions'][0]['selected']['via']==['SOURCE_LABEL_PART']
        assert q['mentions'][0]['hits'][0]['text']=='상장지수펀드의 설명이다.'
        q=g.query('환불');m=q['mentions'][0]
        assert m['selected']['label']=='환불'
        assert g.articles(q)['mentions'][0]['hits']==[]
        opt=next(c for c in m['choices'] if c['kind']=='official_relation_candidate')
        assert opt['via'][0]['kind']=='RELATED'
        chosen=g.query('환불',selections={'query_id':q['query_id'],'choices':{m['id']:opt['id']}})
        assert g.articles(chosen)['mentions'][0]['hits'][0]['text']=='반품을 처리한다.'
    finally:g.close()


def test_unknown_filter_tamper_and_no_overwrite(inputs):
    g=compile_glossary(inputs)
    try:
        with pytest.raises(ValueError,match='Unknown document'):g.articles(g.query('신탁'),documents=['absent'])
        assert g.articles(g.query('신탁'),documents=[])['mentions'][0]['hits']==[]
        with pytest.raises(ValueError,match='already exists'):v1.build(*inputs)
        with (inputs[2]/'store.sqlite').open('ab') as f:f.write(b'drift')
        with pytest.raises(ValueError,match='Corpus changed'):g.articles(g.query('신탁'))
    finally:g.close()
    with (inputs[-1]/'dictionary.sqlite').open('ab') as f:f.write(b'drift')
    with pytest.raises(ValueError,match='hash mismatch'):v1.Glossary(inputs[-1])


def test_truncation_and_repeated_mentions_have_distinct_choices(inputs):
    g=compile_glossary(inputs)
    try:
        q=g.query('채권과 채권',choice_limit=1)
        assert len(q['mentions'])==2
        assert all(m['choices_truncated'] and m['choice_count']==2 for m in q['mentions'])
        assert q['mentions'][0]['id']!=q['mentions'][1]['id']
        chosen={'query_id':q['query_id'],'choices':{q['mentions'][0]['id']:'entry:bond_a'}}
        q=g.query('채권과 채권',selections=chosen)
        assert [m['status'] for m in q['mentions']]==['SELECTED','CHOICE_REQUIRED']
    finally:g.close()


def test_cli_build_match_status(inputs,capsys):
    from lawrag.pipeline.glossary_alignment import main
    catalogue,external,corpus,output=inputs
    args=['--v1-dir',str(output)]
    assert main(['v1-build',*args,'--state-dir',str(catalogue.parent),'--external-dir',str(external),'--corpus-generation',str(corpus)])==0
    assert json.loads(capsys.readouterr().out)['counts']['entry']==10
    assert main(['v1-status',*args])==0
    assert json.loads(capsys.readouterr().out)['status']=='draft'
    assert main(['v1-match',*args,'--question','ETF를'])==0
    assert json.loads(capsys.readouterr().out)['mentions'][0]['hits']


def test_reviewed_meaning_reaches_all_member_labels(inputs,tmp_path):
    review=tmp_path/'different-label-review.json'
    dump(review,{'meanings':[{'id':'reviewed','label':'공통 의미','description':'서로 다른 표제어의 합성 검토',
        'entry_ids':['refund','return'],'evidence':'합성 단위 테스트의 명시적 검토'}]})
    g=compile_glossary(inputs,review=review)
    try:
        q=g.articles(g.query('환불'))
        assert q['mentions'][0]['status']=='RESOLVED'
        assert set(q['mentions'][0]['selected']['source_entries'])=={'refund','return'}
        assert q['mentions'][0]['hits'][0]['text']=='반품을 처리한다.'
    finally:g.close()


def test_missing_completion_definition_does_not_replace_other_sources(inputs,tmp_path):
    completion=tmp_path/'completion.sqlite'
    records=[{'label':'채권','source_id':'specific','definition':'특정 출처의 설명','source':'특정 판본'}]
    with sqlite3.connect(completion) as db:
        db.execute('CREATE TABLE request(id TEXT,status TEXT,endpoint TEXT,records TEXT,response_sha256 TEXT)')
        db.execute('INSERT INTO request VALUES (?,?,?,?,?)',('r1','complete','legal_term_detail',json.dumps(records),'source-hash'))
        db.execute('INSERT INTO request VALUES (?,?,?,?,?)',('r2','pending','legal_term_detail','[]',None))
    g=compile_glossary(inputs,completion=completion)
    try:
        descriptions={o['description'] for o in g.query('채권')['mentions'][0]['choices']}
        assert descriptions=={'특정 출처의 설명','청구할 권리','발행하는 증권'}
        assert g.report['identity']['completed_definitions']['requests']==1
    finally:g.close()
