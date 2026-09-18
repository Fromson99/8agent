"""Synthetic server responses only: HTTP -> Docling structure -> term DRAFT."""
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3

import fitz
import httpx
import pytest
from docling_core.types.doc import (DoclingDocument, DocItemLabel, Size,
                                    ProvenanceItem, BoundingBox, TableCell, TableData)

from lawrag.core import genos_preprocessor as remote, parse_adapter
from lawrag.pipeline import genos_build as build, genos_stages as stages
from semantic_runtime.contracts import sha
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from test_term_source_generation import inputs


@pytest.fixture
def server(tmp_path, monkeypatch):
    shared = tmp_path / 'shared'; shared.mkdir()
    for key in ('GENOS_PREPROCESSOR_URL', 'GENOS_PREPROCESSOR_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('GENOS_PREPROCESSOR_ID', '987')
    monkeypatch.setenv('GENOS_PREPROCESSOR_REVISION', 'synthetic-docling-v1')
    monkeypatch.setenv('GENOS_PREPROCESSOR_SHARED_ROOT', str(shared))
    monkeypatch.setenv('GENOS_PREPROCESSOR_REMOTE_ROOT', '/server/shared')
    monkeypatch.setenv('GENOS_PDF_PARSER', 'preprocessor')
    monkeypatch.setenv('STRUCTURE_RECIPE_VLM', 'off')
    monkeypatch.setattr(parse_adapter, '_converter', lambda *a, **kw: pytest.fail('local Docling inference'))
    monkeypatch.setattr(parse_adapter, 'docling_version', lambda: pytest.fail('local model metadata needed'))
    doc = DoclingDocument(name='모의규정')
    doc.add_page(page_no=1, size=Size(width=595, height=842))
    def prov(y):
        return ProvenanceItem(page_no=1, charspan=(0, 1),
            bbox=BoundingBox(l=50, t=y, r=500, b=y+30, coord_origin='TOPLEFT'))
    doc.add_text(label=DocItemLabel.SECTION_HEADER, text='제1조(정의)', prov=prov(50))
    doc.add_text(label=DocItemLabel.TEXT, text='이 규정에서 “영업일”이란 토요일을 제외한 날을 말한다.', prov=prov(90))
    cells = [TableCell(text='영업일 기준', row_span=1, col_span=2,
                      start_row_offset_idx=0, end_row_offset_idx=1,
                      start_col_offset_idx=0, end_col_offset_idx=2, column_header=True),
             TableCell(text='토요일', start_row_offset_idx=1, end_row_offset_idx=2,
                       start_col_offset_idx=0, end_col_offset_idx=1),
             TableCell(text='제외', start_row_offset_idx=1, end_row_offset_idx=2,
                       start_col_offset_idx=1, end_col_offset_idx=2)]
    doc.add_table(data=TableData(num_rows=2, num_cols=2, table_cells=cells), prov=prov(150))
    state = {'body': {'code': 0, 'data': {'document': doc.model_dump(mode='json')}},
             'status': 200, 'calls': []}
    original = httpx.Client
    def handler(request):
        payload = json.loads(request.content)
        state['calls'].append((str(request.url), payload))
        assert str(request.url) == 'http://preprocessor-987:8080/run'
        assert payload['file_path'].startswith('/server/shared/')
        request_id = Path(payload['file_path']).parent.name
        assert (shared / request_id / 'source.pdf').read_bytes().startswith(b'%PDF-')
        if state.get('timeout'):
            raise httpx.ReadTimeout('sensitive server details', request=request)
        if state.get('mutate'):
            (shared / request_id / 'source.pdf').write_bytes(b'changed')
        return httpx.Response(state['status'], json=state['body'],
                              headers={'Location': 'https://example.org/redirect'})
    def factory(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, 'Client', factory)
    source = tmp_path / 'mock.pdf'
    pdf = fitz.open(); page = pdf.new_page(width=595, height=842)
    page.insert_text((50, 60), 'Synthetic document used only for transport contracts.')
    pdf.save(source); pdf.close()
    return state, source


def test_environment_id_url_override_and_missing_config(server, monkeypatch):
    assert remote.Settings.from_env().url == 'http://preprocessor-987:8080/run'
    monkeypatch.setenv('GENOS_PREPROCESSOR_URL', 'https://internal.example/selected/parser')
    assert remote.Settings.from_env().url == 'https://internal.example/selected/parser'
    monkeypatch.setenv('GENOS_PREPROCESSOR_URL', 'http://internal-service:8080')
    assert remote.Settings.from_env().url == 'http://internal-service:8080/run'
    monkeypatch.setenv('GENOS_PREPROCESSOR_URL', 'https://name:secret@internal/run')
    with pytest.raises(ValueError, match='without credentials'):
        remote.Settings.from_env()
    monkeypatch.delenv('GENOS_PREPROCESSOR_URL')
    monkeypatch.delenv('GENOS_PREPROCESSOR_ID')
    with pytest.raises(ValueError, match='GENOS_PREPROCESSOR_ID'):
        remote.Settings.from_env()


def test_pdf_parses_remotely_preserving_cells_coordinates_and_cache(server, tmp_path, monkeypatch):
    from lawrag.core.ingest import parse_cached
    state, source = server
    monkeypatch.setenv('GENOS_PREPROCESSOR_API_KEY', 'never-record-this-key')
    cache = tmp_path / 'parse.json'
    parsed = parse_cached(source, cache)
    table = next(e for e in parsed.elements if e.is_table)
    assert len(table.table.cells) == 3 and table.table.cells[0].col_span == 2
    assert table.page == 1 and table.bbox == [50, 150, 500, 180]
    assert table.bbox_origin == 'TOPLEFT'
    assert parsed.stats['parser_identity']['source_sha256'] == sha(source)
    assert parse_cached(source, cache).stats == parsed.stats
    assert len(state['calls']) == 1
    evidence = next((tmp_path / 'preprocessor').glob('*/receipt.json'))
    assert json.loads(evidence.read_text())['status'] == 'COMPLETED'
    assert all('never-record-this-key' not in p.read_text()
               for p in evidence.parent.glob('*.json'))
    # Same PDF with a changed server revision must never reuse old parsing.
    monkeypatch.setenv('GENOS_PREPROCESSOR_REVISION', 'synthetic-docling-v2')
    parse_cached(source, cache)
    assert len(state['calls']) == 2


@pytest.mark.parametrize('change,error', [
    ({'body': {'code': 1, 'errMsg': 'sensitive details', 'data': None}}, 'reported failure'),
    ({'body': {'code': 0, 'data': [{'text': 'chunk'}]}}, 'integer indices'),
    ({'body': {'code': 0, 'data': {'document': {}}}}, 'schema mismatch'),
    ({'status': 302}, 'HTTP 302'),
    ({'status': 500}, 'HTTP 500'),
    ({'timeout': True}, 'timeout failure'),
    ({'mutate': True}, 'source changed'),
])
def test_failed_remote_calls_never_fall_back_or_cache(server, tmp_path, change, error):
    from lawrag.core.ingest import parse_cached
    state, source = server; state.update(change)
    with pytest.raises(ValueError, match=error):
        parse_cached(source, tmp_path / 'parse.json')
    assert len(state['calls']) == 1 and not (tmp_path / 'parse.json').exists()
    assert list((tmp_path / 'shared').glob('*/source.pdf'))  # retained for server completion


def test_page_mismatch_rejected(server, tmp_path):
    state, source = server
    state['body']['data']['document']['pages']['2'] = copy.deepcopy(state['body']['data']['document']['pages']['1'])
    state['body']['data']['document']['pages']['2']['page_no'] = 2
    with pytest.raises(ValueError, match='page set'):
        parse_adapter.parse_pdf(source)


def test_server_only_picture_uri_uses_source_pdf_pixels(server):
    from docling_core.types.doc import ImageRef
    state, source = server
    doc = DoclingDocument.model_validate(state['body']['data']['document'])
    doc.add_picture(image=ImageRef(mimetype='image/png', dpi=144,
                                   size=Size(width=100, height=100), uri='https://unreachable.invalid/picture.png'),
                    prov=ProvenanceItem(page_no=1, charspan=(0, 0),
                        bbox=BoundingBox(l=50, t=600, r=100, b=550, coord_origin='BOTTOMLEFT')))
    state['body']['data']['document'] = doc.model_dump(mode='json')
    parsed = parse_adapter.parse_pdf(source)
    picture = next(e for e in parsed.elements if e.is_picture)
    assert picture.meta['image_source'] == 'original_pdf_crop'
    assert parsed.images[picture.index].startswith('data:image/png;base64,')
    assert len(state['calls']) == 1  # No media URL request.


class Progress:
    def document(self, *a, **kw): pass
    def emit(self, *a, **kw): pass
    def finish(self, *a, **kw): pass
    def error(self, exc): raise exc


def test_remote_pdf_to_source_term_generation_and_resume(server, inputs, tmp_path, monkeypatch):
    from lawrag.core import llm
    monkeypatch.setattr(llm, 'load_env', lambda: None)
    monkeypatch.delenv('GENOS_PDF_PARSER')  # Maintained GENOS stages default to remote.
    state, source = server
    _, glossary = inputs
    raw = tmp_path / 'raw'; raw.mkdir()
    (raw / source.name).write_bytes(source.read_bytes())
    options = build.parser().parse_args(['build', '--input-root', str(raw), '--build-dir', str(tmp_path/'out'),
                                        '--glossary-dir', str(glossary), '--execute'])
    plan = build.inventory(raw, 'internal')
    data = tmp_path / 'data'
    result = stages.execute(plan, options, data, 'remote', 'all', progress=Progress(), dependencies={'fixture': 'v1'})
    assert result['ok'] and result['activated'] is False
    assert len(state['calls']) == 1
    generated = next((data/'TERM/remote').glob('*/generation'))
    with closing(Store(generated)) as store:
        text = '\n'.join(r[0] for r in store.db.execute('SELECT text FROM source_block'))
        assert '영업일' in text and '토요일' in text
        document = json.loads(store.db.execute('SELECT json FROM document').fetchone()[0])
        assert document['parser_identity']['source_sha256'] == sha(source)
        assert document['preprocessor']['response_sha256']
        table = next(json.loads(r[0]) for r in store.db.execute('SELECT json FROM source_block')
                     if json.loads(r[0]).get('kind') == 'table')
        assert table['table']['rows'][0][0]['col_span'] == 2
        assert table['page'] == 1 and table['rect']['w'] > 0
        TermIndex(generated/'navigation', store)
    assert stages.execute(plan, options, data, 'remote', 'index', progress=Progress(), dependencies={'fixture':'v1'})['ok']
    assert len(state['calls']) == 1
    receipt = next((data/'STRUCTURE').glob('*/structure-receipt.json'))
    stages.verify_structure(receipt.parent)
    response = next(receipt.parent.glob('preprocessor/*/response.json'))
    response.write_text('{}')
    with pytest.raises(ValueError, match='파일/해시'):
        stages.verify_structure(receipt.parent)


def test_structure_without_glossary_then_index_without_parser_settings(server, inputs, tmp_path, monkeypatch):
    from lawrag.core import llm
    from lawrag.pipeline import glossary_linking
    monkeypatch.setattr(llm, 'load_env', lambda: None)
    state, source = server
    _, glossary = inputs
    monkeypatch.delenv('GENOS_PREPROCESSOR_REVISION')
    raw = tmp_path/'RAW/internal'; raw.mkdir(parents=True)
    (raw/source.name).write_bytes(source.read_bytes())
    options = build.parser().parse_args(['build','--input-root',str(raw),'--build-dir',str(tmp_path/'out')])
    plan = build.inventory(raw,'internal')
    data = tmp_path/'data'
    original = glossary_linking.project
    monkeypatch.setattr(glossary_linking, 'project', lambda *a,**k: pytest.fail('structure must not link terms'))
    result = stages.execute(plan,options,data,'independent','structure',progress=Progress(),dependencies={'fixture':'v1'})
    assert result['ok'] and len(state['calls'])==1
    monkeypatch.setattr(glossary_linking,'project',original)
    for key in ('GENOS_PREPROCESSOR_ID','GENOS_PREPROCESSOR_SHARED_ROOT','GENOS_PREPROCESSOR_REMOTE_ROOT'):
        monkeypatch.delenv(key)
    options.glossary_dir = glossary
    result = stages.execute(plan,options,data,'independent','index',progress=Progress())
    assert result['ok'] and len(state['calls'])==1
    # Input drift must never silently join the wrong document generation.
    plan['files'][0]['sha256']='0'*64
    with pytest.raises(ValueError,match='selection changed'):
        stages.execute(plan,options,data,'independent','index',progress=Progress())


def test_cli_structures_mixed_raw_internal_without_dictionary(server, tmp_path, monkeypatch):
    import importlib.util
    from lawrag.core import llm
    from lawrag.pipeline import glossary_linking
    monkeypatch.setattr(llm, 'load_env', lambda: None)
    state, source = server
    data=tmp_path/'mixed'; raw=data/'RAW/internal'; raw.mkdir(parents=True)
    (raw/'sample.pdf').write_bytes(source.read_bytes())
    (raw/'law.xml').write_text('<법령><기본정보><법령명_한글>모의규정</법령명_한글></기본정보><조문><조문단위><조문번호>1</조문번호><조문여부>조문</조문여부><조문제목>목적</조문제목><조문내용>제1조(목적) 이 규정은 모의 자료다.</조문내용></조문단위></조문></법령>')
    # Old PDF directory must not remain the input authority.
    old=data/'PDF/internal';old.mkdir(parents=True);(old/'ignored.pdf').write_bytes(b'not a pdf')
    monkeypatch.setattr(stages,'offline_data_root',lambda root:data)
    monkeypatch.setattr(glossary_linking,'configured',lambda *a:pytest.fail('unneeded glossary selection'))
    script=Path(build.ROOT)/'06_TOOLS/COMMANDS/genos_data_stages.py'
    spec=importlib.util.spec_from_file_location('mixed_data_cli',script)
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    assert cli.main(['--run-id','mixed','--stage','structure','--execute',
                     '--glossary-dir',str(tmp_path/'absent')])==0
    assert len(state['calls'])==1
    selection=json.loads((data/'LOGS/mixed/structure-selection.json').read_text())
    assert len(selection['documents'])==2


def test_status_redaction_takes_one_environment_snapshot(monkeypatch):
    from lawrag.pipeline import genos_status
    class Environment(dict):
        reads=0
        def items(self):
            self.reads+=1
            return super().items()
    env=Environment(TEST_API_KEY='sensitive-value')
    monkeypatch.setattr(genos_status.os,'environ',env)
    report=genos_status.safe({'rows':[{'text':'sensitive-value'} for _ in range(500)]})
    assert env.reads==1
    assert all(row['text']=='[REDACTED]' for row in report['rows'])


def chunks(*texts):
    return [{'text': text, 'i_chunk_on_doc': i, 'n_chunk_of_doc': len(texts),
             'i_page': 1, 'e_page': 1, 'n_page': 1, 'chunk_bboxes': None,
             'media_files': None} for i, text in enumerate(texts)]


def test_chunk_assembly_keeps_every_byte_and_does_not_invent_geometry(server, tmp_path):
    from lawrag.core.ingest import parse_cached
    state, source = server
    rows = chunks('제1장 총칙\n\n제1조(정의)\n', '같은 문장\n같은 문장\n')
    state['body']['data'] = list(reversed(rows))
    result = parse_cached(source, tmp_path/'parse.json')
    assert result.stats['requires_structure_vlm'] is True
    assert all(e.bbox is None and e.table is None for e in result.elements)
    assembled = json.loads(next((tmp_path/'preprocessor').glob('*/assembled-input.json')).read_text())
    assert assembled['full_text'] == '\n'.join(r['text'] for r in rows)
    assert assembled['chunks'] == rows
    for e in result.elements:
        lo, hi = e.meta['assembled_char_span']
        assert assembled['full_text'][lo:hi] == e.text
    assert len(state['calls']) == 1
    assert parse_cached(source, tmp_path/'parse.json').stats == result.stats


@pytest.mark.parametrize('error_kind', ['gap', 'duplicate', 'count', 'page', 'range', 'empty'])
def test_incomplete_chunks_fail_without_success_cache(server, tmp_path, error_kind):
    from lawrag.core.ingest import parse_cached
    state, source = server
    rows = chunks('제1조 목적', '제2조 정의')
    if error_kind == 'gap': rows[1]['i_chunk_on_doc'] = 2
    if error_kind == 'duplicate': rows[1]['i_chunk_on_doc'] = 0
    if error_kind == 'count': rows[0]['n_chunk_of_doc'] = 3
    if error_kind == 'page': rows[0]['i_page'] = 0
    if error_kind == 'range': rows[0]['e_page'] = 2
    if error_kind == 'empty':
        for row in rows: row['text'] = ''
    state['body']['data'] = rows
    with pytest.raises(ValueError):
        parse_cached(source, tmp_path/'parse.json')
    assert not (tmp_path/'parse.json').exists()


def test_docling_only_mode_rejects_chunks_and_changes_cache_identity(server, monkeypatch):
    state, source = server
    before = remote.Settings.from_env().identity()
    monkeypatch.setenv('GENOS_PREPROCESSOR_RESPONSE_MODE', 'docling')
    assert remote.Settings.from_env().identity() != before
    state['body']['data'] = chunks('제1조 목적')
    with pytest.raises(ValueError, match='data.document'):
        parse_adapter.parse_pdf(source)


def test_chunks_require_vlm_before_any_format_or_heuristic_admission(server, tmp_path):
    from lawrag.core.ingest import interpret_doc
    state, source = server
    state['body']['data'] = chunks('제1조 목적')
    with pytest.raises(ValueError, match='STRUCTURE_RECIPE_VLM'):
        interpret_doc(source, store=tmp_path/'store', binding_of=lambda *a:'a-format', doc_id='test')


def test_chunks_to_template_vlm_correction_final_restructure_and_index(server, inputs, tmp_path, monkeypatch):
    from lawrag.core import llm
    from lawrag.core.structure import recipe_runtime as runtime
    monkeypatch.setattr(llm, 'load_env', lambda: None)
    monkeypatch.setenv('LLM_BACKEND', 'genos')
    monkeypatch.setenv('STRUCTURE_RECIPE_VLM', 'on')
    state, source = server
    texts = ['제1장 총칙\n제1조(정의) 이 규정에서 “영업일”이란 토요일을 제외한 날을 말한다.',
             '제2조(적용) 영업일을 적용한다.']
    state['body']['data'] = chunks(*texts)
    requests = []
    class Model:
        def __init__(self, journal, images, **kw):
            self.images = images; self.calls = 0; self.model = 'synthetic-contract-only'
        def __call__(self, phase, system, data, schema, vision):
            self.calls += 1; requests.append((phase, copy.deepcopy(data)))
            assert bool(vision)==bool(self.images)
            if "opinions" in schema["properties"]:
                wrong=data['recipe']['templates']['body']['heading_rules']['kr_article']['parent_family']!='kr_장'
                return {"opinions":["Page 1: articles should be governed by the visible chapter."] if wrong else [],"summary":"Synthetic visual inspection"}
            if 'regions' in schema['properties']:
                assert len(data['source_blocks']) == 3
                return {'regions':[{'start_block':0,'template_id':'body','label':'body','reason':'synthetic'}]}
            if 'families' in schema['properties']:
                return {'families':{f:{'parent_family':'$document','heading_position':'line_start',
                    'sequence':'consecutive','reset_scope':'parent','rationale':'synthetic'} for f in data['catalog']}}
            rule = data['recipe']['templates']['body']['heading_rules']['kr_article']
            change = rule['parent_family'] != 'kr_장'
            return {'opinion_decisions':[{'opinion_id':o['id'],'decision':'accept','reason':'Source chapter governs these articles','blocks':[data['source_blocks'][0]['idx']]} for o in data['vlm_opinions']], 'verdict':'revise' if change else 'approve', 'issues':[],
                'reviewed_state_id':data['reviewed_state_id'],
                'template_changes':[{'template_id':'body','family':'kr_article',
                                     'rule':{**rule,'parent_family':'kr_장'}}] if change else []}
    monkeypatch.setattr(runtime, 'GenosCalls', Model)
    _, glossary = inputs
    raw = tmp_path/'RAW/internal'; raw.mkdir(parents=True)
    (raw/'a.pdf').write_bytes(source.read_bytes())
    options = build.parser().parse_args(['build','--input-root',str(raw),'--build-dir',str(tmp_path/'out'),
                                        '--glossary-dir',str(glossary)])
    data = tmp_path/'data'
    result = stages.execute(build.inventory(raw,'internal'), options, data, 'chunks', 'all',
                            progress=Progress(), dependencies={'fixture':'chunks-v1'})
    assert result['ok'] and len(state['calls']) == 1
    meta = next(iter(result['documents'].values()))['recipe_review']
    assert meta['status'] == 'visual_approved' and meta['coverage']['visually_reviewed_pages'] == [1]
    assert meta['coverage']['source_evidence']['spatial_fidelity'] == 'unavailable'
    # Recipe journals live next to the structure store in the existing builder.
    finals = list(data.rglob('final-template.json'))
    assert finals and json.loads(finals[0].read_text())['templates']['body']['parent_map']['kr_article'] == 'kr_장'
    assert list(data.rglob('final-restructured-tree.json'))
    reviews = [d for p,d in requests if '-llm-adjudicate' in p]
    assert len(reviews) == 2 and reviews[0]['reviewed_state_id'] != reviews[1]['reviewed_state_id']
    with closing(Store(next((data/'TERM/chunks').glob('*/generation')))) as store:
        text = '\n'.join(r[0] for r in store.db.execute('SELECT text FROM source_block'))
        assert '영업일' in text and '제2조' in text


def test_internal_pdf_limit_never_reads_external_xml(server, tmp_path, monkeypatch):
    from lawrag.pipeline import genos_corpus
    state, source = server
    raw = tmp_path/'RAW'; internal = raw/'internal'; internal.mkdir(parents=True)
    for name in ('a.pdf','b.pdf'): (internal/name).write_bytes(source.read_bytes())
    external = raw/'law'; external.mkdir(); (external/'broken.xml').write_text('not xml')
    original = Path.read_bytes
    def guarded(path):
        if external in path.parents: pytest.fail('external source read')
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',guarded)
    plan, report = genos_corpus.collect(raw, only_internal_pdf=True, limit=1, skip_invalid=True)
    assert len(plan['files']) == 1 and plan['files'][0]['path'].endswith('a.pdf')
    assert not report['errors'] and not state['calls']


def test_structured_response_wrong_source_hash_is_rejected(server):
    state,source=server
    state['body']['data'].update(schema_version='8agent-structured-pdf-v1',
                                provenance={'source_sha256':'0'*64})
    with pytest.raises(ValueError,match='source hash mismatch'):
        parse_adapter.parse_pdf(source)


@pytest.mark.parametrize('physical,reported,represented', [(1,0,1),(10,9,10),(10,8,9),(10,10,10)])
def test_legacy_attachment_n_page_is_last_zero_based_index(tmp_path, physical, reported, represented):
    from lawrag.core.genos_chunks import assemble, elements
    source=tmp_path/'source.pdf'
    with fitz.open() as pdf:
        for _ in range(physical):pdf.new_page()
        pdf.save(source)
    rows=[{'text':f'Synthetic page {i+1}', 'i_chunk_on_doc':i, 'n_chunk_of_doc':represented,
           'i_page':i+1,'e_page':i+1,'n_page':reported} for i in range(represented)]
    result=assemble(rows,source)
    assert len(result.pages)==physical and result.chunks==rows
    assert [e.page for e in elements(result)]==list(range(1,represented+1))
    assert result.page_metadata['reported_n_page']==reported
    assert result.page_metadata['pages_without_chunks']==list(range(represented+1,physical+1))
    assert result.dump()['page_count']==physical


@pytest.mark.parametrize('mode',['out_of_bounds','mixed_counts','arbitrary_count'])
def test_page_metadata_compatibility_does_not_disable_validation(server, mode):
    from lawrag.core.genos_chunks import assemble
    _,source=server
    rows=chunks('First','Second')
    for row in rows:row['n_page']=0
    if mode=='out_of_bounds':rows[1]['i_page']=rows[1]['e_page']=2
    if mode=='mixed_counts':rows[1]['n_page']=1
    if mode=='arbitrary_count':
        for row in rows:row['n_page']=9
    with pytest.raises(ValueError):assemble(rows,source)
