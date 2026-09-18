"""Native Office/PDF selection, archive merge and source navigation; synthetic only."""
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import zipfile

import pytest
from lawrag.pipeline import genos_build as build, genos_corpus as corpus, genos_stages as stages
from lawrag.pipeline import document_representations as reps
from lawrag.core import parse_adapter

ROOT = build.ROOT

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj)
    return obj

unpack = module('native_zip', '06_TOOLS/OFFLINE/genos_unpack_internal.py')

def put(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    return path

def zipfile_at(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as z:
        for name, body in files.items(): z.writestr(name, body)
    return path

def args(root, report, **kw):
    return SimpleNamespace(root=root, report=report, zip=None, layout='auto', encoding='cp949', max_bytes=1000000, apply=True, **kw)

def test_native_selection_duplicate_aliases_and_revision_preservation(tmp_path):
    internal = tmp_path/'RAW/internal'
    base = internal/'1. 상위규정/01 이사회규정'
    for name, body in [('이사회규정(170817).docx','office'),('이사회규정(170817).pdf','pdf'),
                       ('이사회규정(170817)(2).pdf','pdf'),('이사회규정(170817)(3).pdf','different-revision')]:
        put(base/name, body)
    put(internal/'3. 타부서준칙/별명.docx','office')
    plan, report = corpus.collect(tmp_path/'RAW', only_internal=True, skip_invalid=True, emit=lambda _:None)
    assert report['ok'], report['errors']
    assert len(plan['files']) == 2  # DOCX + genuinely different PDF revision
    native = next(r for r in plan['files'] if r['path'].endswith('.docx'))
    assert len(native['pdf_references']) == 2
    assert any(a['file_name']=='별명.docx' for a in native['aliases'])
    assert all(a['relative_path'].startswith('internal/') for a in native['aliases'])
    assert any('타부서준칙' in a['folder_path'] for a in native['aliases'])
    assert native['pairing_content_verified'] is False
    reps.verify_representations(native)
    put(base/'이사회규정(170817).pdf','changed')
    with pytest.raises(ValueError, match='changed'):reps.verify_representations(native)

def test_doc_pdf_primary_and_missing_pdf_is_input_error(tmp_path):
    for name in ('old.doc','old.pdf','missing.doc'):
        put(tmp_path/'internal'/name, name)
    plan, report=corpus.collect(tmp_path, only_internal=True, skip_invalid=True, emit=lambda _:None)
    assert [Path(r['path']).name for r in plan['files']] == ['old.pdf']
    assert len(report['errors']) == 1 and '주 입력 PDF 없음' in report['errors'][0]['error']
    assert any(r['format']=='.doc' for r in plan['files'][0]['representations'])
    from lawrag.pipeline.genos_doc import prepare
    with pytest.raises(ValueError, match='PDF'):prepare({'path':'old.doc','relative':'old.doc'},tmp_path)

@pytest.mark.parametrize('with_prefix', [True,False])
def test_zip_merge_preserves_tree_and_no_overwrite_idempotent(tmp_path,with_prefix):
    root=tmp_path/'internal';base='1. 상위규정/' if with_prefix else ''
    z=zipfile_at(root/'1. 상위규정.zip', {base+'01 이사회규정/rule.docx':'native',base+'빈 폴더/':''})
    pdf=put(root/'1. 상위규정/01 이사회규정/rule.pdf','reference')
    before=z.read_bytes()
    assert unpack.run(args(root,tmp_path/'one.json'))==0
    assert (pdf.parent/'rule.docx').read_text()=='native'
    assert (root/'1. 상위규정/빈 폴더').is_dir()
    assert z.read_bytes()==before and pdf.read_text()=='reference'
    assert unpack.run(args(root,tmp_path/'two.json'))==0
    assert json.loads((tmp_path/'two.json').read_text())['files'][0]['action']=='REUSE'

@pytest.mark.parametrize('collision', ['same_path','ancestor','planned_ancestor'])
def test_zip_conflicts_block_all_writes(tmp_path,collision):
    root=tmp_path/'internal';entries={'group/new.docx':'new','group/conflict.docx':'incoming'}
    if collision=='same_path':put(root/'group/conflict.docx','existing')
    if collision=='ancestor':put(root/'group','not directory')
    if collision=='planned_ancestor':entries['group']='a file'
    zipfile_at(root/'group.zip',entries)
    assert unpack.run(args(root,tmp_path/'audit.json'))==2
    assert not (root/'group/new.docx').exists()
    assert json.loads((tmp_path/'audit.json').read_text())['conflicts']

@pytest.mark.parametrize('name', ['../escape.docx','/absolute.docx','C:/evil.docx'])
def test_zip_unsafe_paths_rejected(tmp_path,name):
    root=tmp_path/'internal';zipfile_at(root/'group.zip',{name:'evil'})
    with pytest.raises(ValueError,match='unsafe'):unpack.run(args(root,tmp_path/'audit.json'))

def test_zip_hash_audit_does_not_delete_copies(tmp_path):
    root=tmp_path/'internal'
    for name,text in [('규정(170817).pdf','same'),('규정(170817)(2).pdf','same'),('규정(170817)(3).pdf','new')]:put(root/name,text)
    assert unpack.run(args(root,tmp_path/'audit.json'))==0
    result=json.loads((tmp_path/'audit.json').read_text())
    assert len(result['before']['exact_duplicates'])==1
    assert len(result['before']['similar_names_different_contents'])==1
    assert len(list(root.glob('*.pdf')))==3


def hwpx(path):
    cell='<tc header="1"><cellAddr rowAddr="0" colAddr="0"/><cellSpan rowSpan="2" colSpan="2"/><subList><p><run><t>병합 셀</t><tbl><tr><tc><cellAddr rowAddr="0" colAddr="0"/><cellSpan rowSpan="1" colSpan="1"/><subList><p><run><t>중첩 내용</t></run></p></subList></tc></tr></tbl><pic><img binaryItemIDRef="img"/></pic></run></p></subList></tc>'
    return zipfile_at(path, {
        'Contents/content.hpf':'<package><manifest><item id="a" href="section10.xml"/><item id="b" href="section2.xml"/><item id="img" href="../BinData/image1.png"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>',
        'Contents/header.xml':'<header><style id="2" name="제목"/><charPr id="5"><bold/></charPr></header>',
        'Contents/section10.xml':'<sec><p styleIDRef="2"><run charPrIDRef="5"><t>제1조(목적)</t></run></p><p><run><t>이 규정은 모의 검증에 적용한다.</t><tbl><tr>'+cell+'</tr></tbl><ctrl><footNote><subList><p><run><t>각주 한 번</t></run></p></subList></footNote></ctrl></run></p></sec>',
        'Contents/section2.xml':'<sec><p><run><t>제2조(범위)</t></run></p><p><run><t>테스트 범위이다.</t></run></p></sec>',
        'BinData/image1.png':__import__('base64').b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')})


def test_hwpx_spine_spans_nested_table_styles_images_roundtrip(tmp_path):
    parsed=parse_adapter.parse(hwpx(tmp_path/'native.hwpx'))
    assert parsed.elements[0].text=='제1조(목적)'
    assert parsed.elements[0].meta['runs'][0]['character_properties']['bold']
    assert parsed.elements[0].meta['style']['name']=='제목'
    table=next(e for e in parsed.elements if e.is_table)
    assert table.table.cells[0].row_span==2 and table.table.cells[0].col_span==2
    assert table.meta['nested_tables'][0]['parent_cell']==[0,0]
    assert table.meta['nested_tables'][0]['table']['cells'][0]['text']=='중첩 내용'
    assert sum('각주 한 번' in e.text for e in parsed.elements)==1
    assert len(parsed.images)==1
    picture=next(e for e in parsed.elements if e.is_picture)
    assert picture.meta['parent_cell']==[0,0] and picture.meta['binary_member']=='BinData/image1.png'
    back=parse_adapter.result_from_dump(parse_adapter.result_to_dump(parsed))
    assert next(e for e in back.elements if e.is_table).meta==table.meta


def test_structure_preserves_context_and_pdf_receipt_and_folder_search(tmp_path,monkeypatch):
    monkeypatch.setenv('STRUCTURE_RECIPE_VLM','off')
    raw=tmp_path/'RAW';base=raw/'internal/1. 상위규정/01 이사회규정'
    native=hwpx(base/'이사회규정.hwpx')
    put(base/'이사회규정.pdf',b'%PDF-reference-synthetic')
    put(raw/'internal/3. 타부서준칙/별도경로.hwpx',native.read_bytes())
    plan,report=corpus.collect(raw,only_internal=True,skip_invalid=True,emit=lambda _:None)
    assert report['ok'] and len(plan['files'])==1
    row=plan['files'][0]
    folder,work=stages.structure(row,plan,tmp_path/'data',{'synthetic':'native'},30,lambda _:None)
    stages.verify_structure(folder)
    payload=json.loads((folder/'structure'/row['document_id']/'result.json').read_text())
    context=payload['document_metadata']
    assert any(b.get('native_metadata',{}).get('nested_tables') for b in payload['blocks'])
    assert context['folder_names']==['internal','1. 상위규정','01 이사회규정']
    assert any(a['file_name']=='별도경로.hwpx' for a in context['aliases'])
    ref=context['pdf_references'][0]
    assert (folder/'structure'/row['document_id']/ref['stored_path']).read_bytes()==b'%PDF-reference-synthetic'
    assert ref['coordinate_alignment']=='unverified'
    from lawrag.pipeline.genos_structure_report import office_reference_report
    logs=tmp_path/'logs';logs.mkdir()
    page=office_reference_report(logs,folder,row)
    assert page['reference_only'] and '좌표' in (logs/page['href']).read_text()
    store_path,_=build.source_jobs(folder,work)
    db=sqlite3.connect(store_path);db.row_factory=sqlite3.Row
    saved=json.loads(db.execute('SELECT json FROM document').fetchone()[0])
    assert saved['document_metadata']==context
    from semantic_runtime.navigation_match import ReverseMatcher
    tdb=sqlite3.connect(':memory:');tdb.row_factory=sqlite3.Row
    tdb.execute('CREATE TABLE source(id,document_id,json)')
    lookup=sqlite3.connect(':memory:');lookup.row_factory=sqlite3.Row
    lookup.execute('CREATE TABLE label(key,source,node_id)')
    tools=SimpleNamespace(db=tdb,terms={},validate_scope=lambda x:x)
    glossary=SimpleNamespace(dbs={'lookup':lookup})
    # A metadata-only matcher still uses the actual structured store.
    matcher=ReverseMatcher(db,tools,glossary)
    result=matcher.starts('3. 타부서준칙 별도경로.hwpx',[row['document_id']])
    assert result['documents'][0]['id']==row['document_id']
    assert 'representations' not in result['documents'][0]['document_context']
    db.close();tdb.close();lookup.close()
    put(base/'이사회규정.pdf',b'changed')
    with pytest.raises(ValueError,match='changed'):
        stages.structure(row,plan,tmp_path/'data',{'synthetic':'native'},30,lambda _:None)


def test_internal_cli_ignores_external_scope_pointer(tmp_path,monkeypatch):
    cli=module('native_cli','06_TOOLS/COMMANDS/genos_data_stages.py')
    data=tmp_path/'data';put(data/'RAW/internal/doc.pdf','test')
    put(data/'CATALOG/BUILD_SCOPE.json','invalid pointer should not be read')
    monkeypatch.setattr(stages,'offline_data_root',lambda _:data)
    monkeypatch.setattr(stages,'execute',lambda *a,**kw:pytest.fail('check-only processing'))
    assert cli.main(['--only-internal','--run-id','internal-native','--check-only'])==0
    inventory=json.loads(next((data/'LOGS/internal-native').glob('inventory-*.json')).read_text())
    assert inventory['unique_documents']==1 and inventory['source_selection']['included']==['internal']


def test_docx_original_styles_and_cells_never_reparsed_from_pdf(tmp_path,monkeypatch):
    from docx import Document
    from lawrag.core import ingest
    path=tmp_path/'fixture.docx'
    doc=Document();doc.add_heading('제1조(목적)',level=1);doc.add_paragraph('모의 규정 본문이다.')
    table=doc.add_table(rows=2,cols=2);table.cell(0,0).merge(table.cell(0,1)).text='병합 제목'
    table.cell(1,0).text='구분';table.cell(1,1).text='내용';doc.save(path)
    monkeypatch.setattr(parse_adapter,'parse_pdf',lambda *a,**kw:pytest.fail('synthetic PDF must never be parsed'))
    folder=tmp_path/'structured';folder.mkdir()
    pdf=ingest.prepare_converted(folder,path.read_bytes(),'.docx')
    parsed=ingest.parse_cached(pdf,folder/'parse.json')
    assert 'docx' in parsed.parser and any(e.meta.get('level')==1 for e in parsed.elements)
    assert any(c.col_span==2 for e in parsed.elements if e.table for c in e.table.cells)
    before=[e.dump() for e in parsed.elements]
    # Cache damage rebuilds native OOXML, never the synthetic display PDF.
    (folder/'parse.json').write_text('{}')
    fresh=ingest.parse_cached(pdf,folder/'parse.json')
    assert [e.dump() for e in fresh.elements]==before


def test_zip_cp949_filename_and_symlinks(tmp_path):
    import stat
    name='규정.docx';raw=name.encode('cp949');placeholder='x'*len(raw)
    path=zipfile_at(tmp_path/'legacy.zip',{placeholder:'test'})
    path.write_bytes(path.read_bytes().replace(placeholder.encode(),raw))
    with zipfile.ZipFile(path) as z:
        assert str(unpack.member_path(z.infolist()[0],'cp949'))==name
    info=zipfile.ZipInfo('link.docx');info.external_attr=(stat.S_IFLNK|0o777)<<16
    with pytest.raises(ValueError,match='link'):unpack.member_path(info,'cp949')


def test_composed_runner_forwards_native_scope(tmp_path,monkeypatch):
    tool=module('native_composed','06_TOOLS/COMMANDS/composed_build.py')
    from lawrag.pipeline import glossary_review
    monkeypatch.setattr(glossary_review,'configured_paths',lambda:{'glossary':tmp_path/'base'})
    calls=[]
    assert tool.run(['--run-id','native','--only-internal','--execute'],call=lambda argv:calls.append(argv) or 0)==0
    assert '--only-internal' in calls[0] and '--only-internal' not in calls[-1]
