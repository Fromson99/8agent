"""Ordinary wiring tests: synthetic documents and fake onsite provider only."""
import copy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from lawrag.pipeline import genos_build as build
from semantic_runtime.storage import Store
from semantic_runtime.genos_index import SQLiteVectors

from xml.sax.saxutils import escape
EXAMPLE = json.loads((build.ROOT / '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json').read_text())
BODY = ' '.join(e['quote'] for e in EXAMPLE['payload']['evidence'])
XML = '''<법령><기본정보><법령명_한글>가상규정</법령명_한글></기본정보><조문>
<조문단위><조문번호>1</조문번호><조문여부>조문</조문여부><조문제목>테스트</조문제목>
<조문내용>제1조(테스트) BODY</조문내용></조문단위></조문></법령>'''.replace('BODY', escape(BODY))


class Fake:
    instances = []
    reject_once = False
    invalid = False
    fail_embed_after = None
    def __init__(self, *a, **kw):
        self.models = {'llm': 'fake-model', 'embed': 'fake-embed'}
        self.targets = {k: SimpleNamespace(root='http://genos.invalid/' + k + '/v1') for k in self.models}
        self.calls, self.batches = [], []
        self.instances.append(self)
    def prepare(self):
        return {'models': self.models, 'endpoints': {k: v.root for k, v in self.targets.items()}}
    def request(self, kind, path, payload, role):
        body = json.loads(payload['messages'][1]['content'])
        self.calls.append(body)
        assert 'response_format' not in payload
        if 'candidate' in body:
            rejected = self.reject_once and sum('candidate' in r for r in self.calls) == 1
            value = {'passed': not rejected, 'issues': ['synthetic missing item'] if rejected else []}
        else:
            graph = json.loads((build.ROOT / '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json').read_text())['payload']
            graph['crosswalk'] = []
            ids = body['code_extracted']['coverage_span_ids']
            evidence_span = max((s for s in body['code_extracted']['spans'] if s['source_span_id'] in ids),
                                key=lambda s: len(s['quote']))['source_span_id']
            for evidence in graph['evidence']:
                eid = evidence['id']; evidence.clear()
                evidence.update(id=eid, source_span_id='unknown' if self.invalid else evidence_span)
            value = {'graph': graph, 'coverage': [
                {'source_span_id': sid, 'disposition': 'REPRESENTED',
                 'entity_ids': [graph['evidence'][0]['id']], 'reason': 'synthetic fixture'} for sid in ids]}
        return {'model': self.models['llm'], 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 10}}, {}
    def embed(self, texts, role):
        if self.fail_embed_after is not None and len(self.batches) >= self.fail_embed_after:
            raise ValueError('synthetic embedding interruption')
        self.batches.append(texts)
        return [[1., 0.] for _ in texts], {'synthetic': True}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from lawrag.core import llm
    monkeypatch.setattr(llm, 'load_env', lambda: None)
    Fake.instances = []
    monkeypatch.setattr(Fake, 'reject_once', False)
    monkeypatch.setattr(Fake, 'invalid', False)
    monkeypatch.setattr(Fake, 'fail_embed_after', None)
    raw = tmp_path / 'raw'; raw.mkdir()
    (raw / 'one.xml').write_text(XML)
    args = build.parser().parse_args(['build', '--input-root', str(raw), '--build-dir', str(tmp_path / 'out'),
                                     '--model-revision', 'synthetic-revision', '--embed-chunk-chars', '8',
                                     '--embed-batch-size', '2', '--execute'])
    args.bindings = None
    return args, raw, tmp_path / 'out'


def run(args):
    return build.execute(args, provider_factory=Fake, emit=lambda s: None)


def test_full_schema_two_docs_review_retry_load_resume(setup, monkeypatch):
    args, raw, out = setup
    (raw / 'two.xml').write_text(XML.replace('가상', '별도'))
    monkeypatch.setattr(Fake, 'reject_once', True)
    protected = out.parent / 'protected'; protected.mkdir()
    monkeypatch.setenv('STRUCTURE_LEDGER', str(protected / 'ledger.json'))
    monkeypatch.setenv('STRUCTURE_STORE', str(protected))
    result = run(args)
    assert result['ok'] and result['counts']['document'] == 2
    assert result['counts']['bundle'] >= 2 and result['counts']['entity'] > 0
    assert any('_repair' in req for req in Fake.instances[0].calls)
    assert all(len(b) <= 2 for b in Fake.instances[0].batches)
    assert not list(protected.iterdir()) and not list(out.rglob('CURRENT*'))
    store = Store(out / 'generation')
    try:
        assert len(store.manifest['scope']['document_version_ids']) == 2
        index = SQLiteVectors(store, store.manifest['vectors'], provider=Fake.instances[0])
        assert index.search('가상 질문', set(store.manifest['scope']['document_version_ids']), 3)
    finally:
        store.close()
    args.resume = True
    assert run(args)['ok']
    assert not Fake.instances[-1].calls and not Fake.instances[-1].batches


def test_invalid_schema_never_loads_or_embeds(setup, monkeypatch):
    args, _, out = setup
    monkeypatch.setattr(Fake, 'invalid', True)
    with pytest.raises(ValueError, match='authoring incomplete'):
        run(args)
    assert not (out / 'generation').exists()
    assert not Fake.instances[-1].batches
    assert len(Fake.instances[-1].calls) == args.max_attempts


def test_embedding_resume_only_pending_batches(setup, monkeypatch):
    args, _, out = setup
    monkeypatch.setattr(Fake, 'fail_embed_after', 1)
    with pytest.raises(ValueError, match='embedding interruption'):
        run(args)
    completed = Fake.instances[0].batches[0]
    assert not (out / 'generation').exists()
    args.resume = True
    monkeypatch.setattr(Fake, 'fail_embed_after', None)
    assert run(args)['ok']
    assert not Fake.instances[-1].calls
    assert all(b != completed for b in Fake.instances[-1].batches)


@pytest.mark.parametrize('drift', ['source', 'tag', 'revision'])
def test_resume_refuses_drift(setup, drift):
    args, raw, _ = setup
    run(args); args.resume = True
    if drift == 'source':
        (raw / 'one.xml').write_text(XML.replace('가상', '변경'))
    elif drift == 'tag':
        (raw / 'one.xml.genos.json').write_text('{"name":"변경"}')
    else:
        args.model_revision = 'different'
    with pytest.raises(ValueError, match='changed'):
        run(args)
    assert len(Fake.instances) == 1


def test_unknown_tag_before_models(setup):
    args, raw, _ = setup
    (raw / 'file.pdf').write_bytes(b'fake')
    (raw / 'file.pdf.genos.json').write_text('{"doc_type":"unknown-type"}')
    with pytest.raises(Exception, match='unknown-type'):
        run(args)
    assert not Fake.instances


def test_call_budget_resumes_without_reextract(setup):
    args, _, out = setup
    args.max_calls = 1
    with pytest.raises(ValueError, match='authoring incomplete'):
        run(args)
    args.resume = True; args.max_calls = 20
    assert run(args)['ok']
    assert len(Fake.instances[-1].calls) == 1
    assert 'candidate' in Fake.instances[-1].calls[0]


def test_batch_159_not_global_cap(tmp_path):
    src = tmp_path / 's.sqlite'
    with sqlite3.connect(src) as db:
        db.execute('CREATE TABLE document(document_id,name,json)')
        db.execute('INSERT INTO document VALUES (?,?,?)', ('d', '폴더 > 문서', '{}'))
        db.execute('CREATE TABLE source_block(document_id,block_id,text)')
        db.execute('INSERT INTO source_block VALUES (?,?,?)', ('d', '0', 'a' * 159))
    fake = Fake()
    result = build.embeddings(tmp_path, src, fake, 64, 1, lambda s: None)
    assert result['rows'] == 159
    assert [len(b) for b in fake.batches] == [64, 64, 31]


def test_nested_folders_survive_entire_build(setup):
    args, raw, out = setup
    nested = raw / '영업본부/준법/업무지침'
    nested.mkdir(parents=True)
    (raw / 'one.xml').rename(nested / '고객관리규정.xml')
    (nested / '고객관리규정.xml.genos.json').write_text(
        json.dumps({'name': '고객관리규정', 'folder': '파서분류'}, ensure_ascii=False))
    assert run(args)['ok']
    expected = '영업본부 > 준법 > 업무지침 > 고객관리규정'
    meta = json.loads(next((out / 'structure').glob('*/meta.json')).read_text())
    assert meta['name'] == expected
    context = meta['document_metadata']
    assert context['folder_names'] == ['영업본부', '준법', '업무지침']
    assert context['document_title'] == '고객관리규정'
    assert context['relative_path'] == '영업본부/준법/업무지침/고객관리규정.xml'
    with sqlite3.connect(out / 'authoring-source.sqlite') as db:
        name, payload = db.execute('SELECT name,json FROM document').fetchone()
        assert name == expected and json.loads(payload)['document_metadata'] == context
        inputs = [json.loads(r[0]) for r in db.execute('SELECT input_json FROM authoring_job')]
        assert all(r['document_name'] == expected for r in inputs)
        assert all('영업본부' not in r[0] for r in db.execute('SELECT text FROM source_block'))
    assert all(expected in text for batch in Fake.instances[-1].batches for text in batch)
    assert all(r['source']['document_name'] == expected for r in Fake.instances[-1].calls)
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    with TestClient(create_app(out, out / 'generation', contracts_root=build.ROOT, provider=Fake.instances[-1])) as client:
        assert expected in client.get('/v1/rag/scopes').text


def test_default_fixed_internal_root(setup, monkeypatch):
    args, raw, out = setup
    target = out.parent / 'data/corpus/internal'
    target.parent.mkdir(parents=True)
    raw.rename(target)
    args.data_root = str(out.parent / 'data')
    args.input_root = None
    args.execute = False
    messages = []
    build.execute(args, provider_factory=Fake, emit=messages.append)
    assert json.loads(messages[-1])['input_root'] == str(target)
    assert not out.exists()


def test_flat_metadata_no_duplicate_title():
    context = build.document_metadata({'relative': '법령/규정/본문.xml', 'name': '규정', 'source': 'external'})
    assert context['display_name'] == '법령 > 규정'
    assert context['folder_names'] == ['법령', '규정']


def test_xml_title_from_header(setup):
    _, raw, _ = setup
    plan = build.inventory(raw, 'external')
    assert plan['files'][0]['name'] == '가상규정'


@pytest.mark.parametrize('extension', ['.md', '.docx'])
def test_registered_parser_and_format_used(setup, monkeypatch, extension):
    args, raw, out = setup
    (raw / 'one.xml').unlink()
    document = raw / ('rule' + extension)
    if extension == '.docx':
        from docx import Document
        doc = Document()
        doc.add_paragraph('제1조(테스트) ' + BODY)
        doc.save(document)
    else:
        document.write_text('제1조(테스트) ' + BODY)
    document.with_name(document.name + '.genos.json').write_text('{"doc_type":"금소법"}')
    from lawrag.core import router
    calls = []
    original = router.route
    def tracked(path, doc_type):
        calls.append((Path(path).suffix, doc_type))
        return original(path, doc_type)
    monkeypatch.setattr(router, 'route', tracked)
    assert run(args)['ok']
    assert calls == [(extension, '금소법')]
    meta = json.loads(next((out / 'structure').glob('*/meta.json')).read_text())
    assert meta['structured_by'].startswith('format:금소법@v')


def test_dry_run_never_calls_or_writes(setup):
    args, _, out = setup
    args.execute = False
    assert run(args)['executed'] is False
    assert not out.exists() and not Fake.instances


def test_nested_output_refused(setup):
    args, raw, _ = setup
    args.build_dir = str(raw / 'derived')
    with pytest.raises(ValueError, match='non-nested'):
        run(args)
    assert not Fake.instances


def test_internal_external_same_generation_and_http_loader(setup):
    args, _, out = setup
    external = out.parent / 'external'; external.mkdir()
    (external / 'law.xml').write_text(XML.replace('가상', '외부'))
    args.external_root = str(external)
    result = run(args)
    assert result['counts']['document'] == 2
    plan = json.loads((out / 'plan.json').read_text())
    assert {r['source'] for r in plan['files']} == {'internal', 'external'}
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    app = create_app(out, out / 'generation', contracts_root=build.ROOT, provider=Fake.instances[-1])
    assert isinstance(app.state.pipeline.vector, SQLiteVectors)
    with TestClient(app) as client:
        health = client.get('/health').json()
        assert health['vector'] == 'ENABLED' and health['counts']['entity'] > 0


def test_missing_embedding_chunk_rejected(setup):
    args, _, out = setup
    run(args)
    store = Store(out / 'generation')
    descriptor = dict(store.manifest['vectors'])
    path = store.path / descriptor['path']
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM chunk WHERE id=(SELECT min(id) FROM chunk)')
    descriptor['sha256'] = build.sha(path)
    descriptor['rows'] -= 1
    try:
        with pytest.raises(ValueError, match='coverage gap'):
            SQLiteVectors(store, descriptor)
    finally:
        store.close()
