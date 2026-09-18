"""Current source-only ingestion and complete glossary link contracts."""
import json
import sqlite3
from pathlib import Path
import pytest
from .test_genos_build import XML
from lawrag.pipeline import genos_stages

def invoke(args,raw,data,stage,run="fixture"):
    class Progress:
        def document(self,*a,**kw):pass
        def emit(self,*a,**kw):pass
        def finish(self,*a,**kw):pass
        def error(self,e):raise e
    return genos_stages.execute(build.inventory(raw,"internal",None),args,data,run,stage,
        progress=Progress(),dependencies={"fixture":"xml"})
from lawrag.pipeline import genos_build as build,genos_corpus as corpus
from lawrag.pipeline import glossary_assembly as assembly,glossary_v1 as v1,glossary_linking as linking


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from lawrag.core import llm
    monkeypatch.setattr(llm, 'load_env', lambda: None)
    raw=tmp_path/'raw';raw.mkdir();(raw/'one.xml').write_text(XML)
    out=tmp_path/'out'
    args=build.parser().parse_args(['build','--input-root',str(raw),'--build-dir',str(out),'--execute'])
    return args,raw,out


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


def test_glossary_links_resume_without_changing_structure(setup,glossary):
    args,raw,out=setup;args.glossary_dir=glossary;data=out.parent/'data'
    assert invoke(args,raw,data,'structure')['ok']
    src=next((data/'STRUCTURE').glob('*/source.sqlite'));before=v1.sha(src)
    linked,report=linking.project(src,glossary,out/'links')
    assert report['llm_calls']==0 and report['occurrences']>0
    with sqlite3.connect(linked.parent/'links.sqlite') as db:
        assert db.execute("SELECT 1 FROM catalogue_link WHERE entry_id='old-definition'").fetchone()
    from lawrag.pipeline.term_generation import build_generation
    build_generation(src,glossary,out/'indexed')
    with sqlite3.connect(out/'indexed/generation/navigation/navigation.sqlite') as db:
        assert not db.execute("SELECT 1 FROM occurrence WHERE term_id='old-definition'").fetchone()
    assert linking.project(src,glossary,out/'links')[1]==report
    assert v1.sha(src)==before
    with (out/'links/links.sqlite').open('ab') as stream:stream.write(b'drift')
    with pytest.raises(ValueError,match='hash mismatch'):linking.project(src,glossary,out/'links')


def test_phase_major_linkage_and_glossary_change_do_not_reparse(setup,glossary,monkeypatch):
    args,raw,out=setup;args.glossary_dir=glossary;data=out.parent/'data'
    assert invoke(args,raw,data,'structure')['ok']
    original_hash=v1.sha(next((data/'STRUCTURE').glob('*/source.sqlite')))
    monkeypatch.setattr(build,'ingest_files',lambda *a,**k:pytest.fail('glossary update reparsed source'))
    assert invoke(args,raw,data,'index')['ok']
    other=out.parent/'new-glossary';import shutil;shutil.copytree(glossary,other)
    with sqlite3.connect(other/'dictionary.sqlite') as db:db.execute("UPDATE entry SET definition='새 설명' WHERE source='econedu'")
    report=json.loads((other/'report.json').read_text());report['dictionary_sha256']=v1.sha(other/'dictionary.sqlite')
    (other/'report.json').write_text(json.dumps(report));args.glossary_dir=other
    assert invoke(args,raw,data,'all',run='new')['ok']
    assert v1.sha(next((data/'STRUCTURE').glob('*/source.sqlite')))==original_hash
    assert len(list((data/'TERM').glob('*/*/links/report.json')))==2


def test_longest_match_local_definition_and_full_audit(setup,glossary):
    args,raw,out=setup;data=out.parent/'data'
    assert invoke(args,raw,data,'structure')['ok']
    src=next((data/'STRUCTURE').glob('*/source.sqlite'))
    with sqlite3.connect(src) as db:
        row=db.execute('select document_id,block_id from source_block limit 1').fetchone()
        text='이 조에서 “금융투자상품”이란 투자 상품을 말한다. 금융투자상품은 포함된다.'
        db.execute('update source_block set text=? where document_id=? and block_id=?',(text,*row))
    linked,report=linking.project(src,glossary,out/'new-links')
    assert report['local_definitions']['records']==1
    with sqlite3.connect(linked.parent/'links.sqlite') as db:
        assert db.execute("select count(*) from occurrence where key='금융'").fetchone()[0]==0
        assert db.execute("select count(*) from occurrence where key='금융투자상품'").fetchone()[0]==2
