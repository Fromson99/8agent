"""File-first ingestion and glossary consumption by the actual authoring queue."""
import json
import sqlite3
from pathlib import Path
import pytest
from .test_genos_build import setup,Fake,XML
from .test_genos_four_stage import invoke
from lawrag.pipeline import genos_build as build,genos_corpus as corpus
from lawrag.pipeline import glossary_assembly as assembly,glossary_v1 as v1,glossary_linking as linking


@pytest.fixture
def glossary(tmp_path):
    folder=tmp_path/'dictionary';folder.mkdir()
    with sqlite3.connect(folder/'dictionary.sqlite') as db:
        assembly.tables(db)
        v1.add_entry(db,'econedu:기관','econedu','기관','기관에 대한 금융 사전 설명')
        v1.add_entry(db,'nts:기관','nts','기관','별도 출처의 설명; 의미 병합 금지')
        v1.add_entry(db,'econedu:상품','econedu','금융투자상품','금융투자상품의 설명')
        v1.add_entry(db,'econedu:금융','econedu','금융','금융의 설명')
        v1.add_entry(db,'old-definition','corpus_definition','기관','다른 법에서만 사용하는 정의',provenance={'document_id':'other'})
    (folder/'report.json').write_text(json.dumps({'schema_version':assembly.VERSION,
        'dictionary_sha256':v1.sha(folder/'dictionary.sqlite')}))
    return folder


def test_without_manifests_selects_one_representation_and_keeps_annexes(tmp_path):
    for source in ['law','internal']:
        folder=tmp_path/source/'v1';folder.mkdir(parents=True)
        for name in ['문서.xml','문서.pdf','문서.docx','별표.pdf']:
            (folder/name).write_text(XML+source+name)
    plan,report=corpus.collect(tmp_path,emit=lambda *a:None)
    assert report['ok']
    assert len(plan['files'])==4
    assert {Path(r['path']).name for r in plan['files']}=={'문서.xml','별표.pdf'}
    assert len([x for x in report['excluded'] if x['reason']=='alternate_body_representation'])==4
    assert plan['input_contract']=='physical-files-v1'
    # Same stem in a different version directory is a separate document.
    (tmp_path/'law/v2').mkdir();(tmp_path/'law/v2/문서.xml').write_text(XML+'v2')
    assert len(corpus.collect(tmp_path,emit=lambda *a:None)[0]['files'])==5


def test_broken_or_missing_metadata_never_hides_physical_documents(tmp_path):
    folder=tmp_path/'law';folder.mkdir();(folder/'a.xml').write_text(XML)
    (folder/'manifest.json').write_text('{broken')
    plan,report=corpus.collect(tmp_path,emit=lambda *a:None)
    assert report['ok'] and report['warnings'] and len(plan['files'])==1
    (folder/'b.pdf').write_bytes(b'new unregistered input')
    assert len(corpus.collect(tmp_path,emit=lambda *a:None)[0]['files'])==2


def test_glossary_hints_reach_model_and_resume_without_changing_structure(setup,glossary):
    args,raw,out=setup;args.glossary_dir=glossary
    result=build.execute(args,provider_factory=Fake,emit=lambda *a:None)
    assert result['ok']
    received=[c['source']['dictionary_lookup'] for c in Fake.instances[-1].calls if 'source' in c]
    assert received and any(x['matches'] for x in received)
    assert all(x['dictionary_sha256']==v1.sha(glossary/'dictionary.sqlite') for x in received)
    assert '다른 법에서만' not in json.dumps(received,ensure_ascii=False)
    assert (out/'glossary-linked/links.sqlite').is_file()
    base_hash=v1.sha(out/'authoring-source.sqlite')
    args.resume=True;build.execute(args,provider_factory=Fake,emit=lambda *a:None)
    assert not Fake.instances[-1].calls
    assert v1.sha(out/'authoring-source.sqlite')==base_hash
    with (out/'glossary-linked/links.sqlite').open('ab') as f:f.write(b'bad')
    count=len(Fake.instances)
    with pytest.raises(ValueError,match='hash mismatch'):build.execute(args,provider_factory=Fake,emit=lambda *a:None)
    assert len(Fake.instances)==count


def test_phase_major_linkage_and_glossary_change_do_not_reparse(setup,glossary,monkeypatch):
    args,raw,out=setup;args.glossary_dir=glossary;data=out.parent/'data'
    result=invoke(args,raw,data,'structure')
    assert result['ok'] and not Fake.instances
    assert next(iter(result['documents'].values()))['glossary_linkage']['jobs']>0
    original_hash=v1.sha(next((data/'STRUCTURE').glob('*/authoring-source.sqlite')))
    monkeypatch.setattr(build,'ingest_files',lambda *a,**k:pytest.fail('glossary update reparsed source'))
    assert invoke(args,raw,data,'llm')['ok']
    assert invoke(args,raw,data,'vector')['ok']
    other=out.parent/'new-glossary';import shutil;shutil.copytree(glossary,other)
    with sqlite3.connect(other/'dictionary.sqlite') as db:db.execute("UPDATE entry SET definition='새 설명' WHERE source='econedu'")
    report=json.loads((other/'report.json').read_text());report['dictionary_sha256']=v1.sha(other/'dictionary.sqlite')
    (other/'report.json').write_text(json.dumps(report));args.glossary_dir=other
    assert invoke(args,raw,data,'structure',run='new')['ok']
    assert v1.sha(next((data/'STRUCTURE').glob('*/authoring-source.sqlite')))==original_hash
    assert len(list((data/'LEXICON/LINKS').glob('*/report.json')))==2


def test_longest_match_local_definition_and_full_audit(setup,glossary):
    args,raw,out=setup
    # Use the existing source builder, then check definition linkage independent of models.
    (raw/'one.xml').write_text(XML.replace('BODY','BODY'))
    build.execute(args,provider_factory=Fake,emit=lambda *a:None)
    src=out/'authoring-source.sqlite'
    with sqlite3.connect(src) as db:
        row=db.execute('select document_id,block_id from source_block limit 1').fetchone()
        text='이 조에서 “금융투자상품”이란 투자 상품을 말한다. 금융투자상품은 포함된다.'
        db.execute('update source_block set text=? where document_id=? and block_id=?',(text,*row))
        for jid,payload in db.execute('select job_id,input_json from authoring_job').fetchall():
            value=json.loads(payload)
            for block in value['blocks']:
                if str(block['idx'])==row[1]:block['text']=text
            db.execute('update authoring_job set input_json=? where job_id=?',(json.dumps(value),jid))
    linked,report=linking.project(src,glossary,out/'new-links')
    assert report['local_definitions']['records']==1
    with sqlite3.connect(linked.parent/'links.sqlite') as db:
        assert db.execute("select count(*) from occurrence where key='금융'").fetchone()[0]==0
        assert db.execute("select count(*) from occurrence where key='금융투자상품'").fetchone()[0]==2
