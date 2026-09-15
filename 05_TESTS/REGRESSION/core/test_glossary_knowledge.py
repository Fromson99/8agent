"""Source preservation, relocation and actual authoring consumption; no real models."""
import json
import shutil
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest
from lawrag.pipeline import glossary_knowledge as k, glossary_v1 as v1
from .test_ingest_glossary_linking import glossary
from .test_genos_build import setup, Fake
from lawrag.pipeline import genos_build


@pytest.fixture
def knowledge(tmp_path, monkeypatch, glossary):
    source=tmp_path/'source';source.mkdir()
    with sqlite3.connect(source/'graph.sqlite') as db:
        db.executescript('''CREATE TABLE node(source TEXT,id TEXT,payload TEXT,PRIMARY KEY(source,id));
          CREATE TABLE term_surface(entry_id TEXT,normalized TEXT);
          CREATE TABLE label(source TEXT,node_id TEXT,value TEXT,normalized TEXT,hanja TEXT,language TEXT);
          CREATE TABLE edge(id TEXT PRIMARY KEY,source TEXT,subject TEXT,predicate TEXT,target TEXT,payload TEXT);''')
        for src in ('fibo','wikidata','nlsh'):
            db.execute('INSERT INTO node VALUES (?,?,?)',(src,'one',json.dumps({'definitions':['Original institution definition']})))
            db.execute('INSERT INTO label VALUES (?,?,?,?,?,?)',(src,'one','기관','기관','','ko'))
            db.execute('INSERT INTO edge VALUES (?,?,?,?,?,?)',(src+'1',src,'one','source_predicate','unresolved-neighbour','{"original":true}'))
            db.execute('INSERT INTO edge VALUES (?,?,?,?,?,?)',(src+'2',src,'unresolved-neighbour','reverse_predicate','one','{}'))
    with sqlite3.connect(source/'translations.sqlite') as db:
        db.execute('CREATE TABLE unit(id TEXT,source TEXT,node_id TEXT,kind TEXT,original TEXT,original_sha256 TEXT,translation_ko TEXT,status TEXT,needs_review INTEGER,origin_locator TEXT)')
        db.execute('INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?)',('u1','fibo','one','LABEL','Institution','hash','기관','TRANSLATED',1,'source-label'))
    with sqlite3.connect(source/'identity.sqlite') as db:
        db.execute('CREATE TABLE concept_mapping(id TEXT,entry_id TEXT,source TEXT,node_id TEXT,status TEXT,reason TEXT,path_count INTEGER)')
        db.execute('INSERT INTO concept_mapping VALUES (?,?,?,?,?,?,?)',('m1','econedu:기관','fibo','one','UNREVIEWED','requires-review',1))
        db.execute('CREATE TABLE official_relation(id TEXT,source_id TEXT,target_id TEXT,code TEXT,label TEXT,payload TEXT)')
        db.execute('INSERT INTO official_relation VALUES (?,?,?,?,?,?)',('o1','econedu:기관','nts:기관','140305','연관어','{}'))
    with sqlite3.connect(source/'legal.sqlite') as db:
        db.execute('CREATE TABLE edge(id TEXT,source_id TEXT,target_id TEXT,code TEXT,status TEXT,reason TEXT)')
        db.execute('INSERT INTO edge VALUES (?,?,?,?,?,?)',('l1','econedu:기관','nts:기관','140305','HELD','conflict'))
    layout=SimpleNamespace(root=tmp_path,inspection_path=lambda root_id,layout_version:tmp_path)
    monkeypatch.setattr(k,'load_layout',lambda *a:layout)
    rows=[{'root_id':'data','path':'source/'+p.name,'destination':p.name,'sha256':k.sha(p)} for p in sorted(source.glob('*.sqlite'))]
    config=tmp_path/'inputs.json';config.write_text(json.dumps({'dictionary_sha256':v1.sha(glossary/'dictionary.sqlite'),'sources':rows}))
    output=tmp_path/'knowledge'
    k.build(config,output)
    return output


def test_complete_source_preservation_and_relocated_lookup(knowledge,tmp_path):
    moved=tmp_path/'moved';shutil.copytree(knowledge,moved)
    with closing(k.Knowledge(moved)) as view:
        result=view.context('기관',['econedu:기관'])
        assert {r['source'] for r in result['concepts']}=={'fibo','wikidata','nlsh'}
        assert result['concept_mappings'][0]['status']=='UNREVIEWED'
        assert result['legal_relations'][0]['status']=='HELD'
        assert result['official_relations'][0]['id']=='o1'
        first=view.node('fibo','one',limit=1)
        second=view.node('fibo','one',limit=1,offset=first['next_offset'])
        assert first['relations_total']==2
        assert {r['id'] for r in first['relations']+second['relations']}=={'fibo1','fibo2'}
        assert first['source_payload']['definitions']==['Original institution definition']
        assert first['translations'][0]['needs_review']==1
        assert first['canonical_approval'] is False
    with (moved/'graph.sqlite').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):k.binding(moved)


@pytest.mark.parametrize('mode',['single','staged'])
def test_source_graph_and_translation_reach_actual_authoring(setup,glossary,knowledge,monkeypatch,mode):
    monkeypatch.setattr(k,'selected_for',lambda directory:knowledge)
    from .test_genos_staged import StagedFake
    args,raw,out=setup;args.glossary_dir=glossary;args.extraction_mode=mode
    provider=StagedFake if mode=='staged' else Fake
    assert genos_build.execute(args,provider_factory=provider,emit=lambda *a:None)['ok']
    received=[match['definitions']['knowledge'] for call in Fake.instances[-1].calls
              for match in call.get('source',{}).get('dictionary_lookup',{}).get('matches',[])
              if 'knowledge' in match['definitions']]
    assert received
    assert any({n['source'] for n in r['concepts']}=={'fibo','wikidata','nlsh'} for r in received)
    assert any(r['official_relations'] and r['legal_relations'] for r in received)
    with sqlite3.connect(out/'glossary-linked/links.sqlite') as db:
        assert db.execute('SELECT count(DISTINCT source) FROM knowledge_catalogue_link').fetchone()[0]==3
    args.resume=True
    genos_build.execute(args,provider_factory=provider,emit=lambda *a:None)
    assert not Fake.instances[-1].calls
