import importlib.util
import json
import os
from pathlib import Path
import sqlite3

import pytest

from lawrag.pipeline import genos_build as build, genos_corpus as corpus
from .test_genos_build import XML, BODY, Fake, setup


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


def fixture_corpus(base):
    raw = base / 'corpus'
    save(raw / 'internal/부서/내규.xml', XML)
    for source in corpus.SOURCES:
        content = XML.replace('가상규정', source + '규정')
        suffix, field, hash_field = '.xml', 'body_file', 'body_sha256'
        if source == 'prec':
            content = '<PrecService><판례내용>' + BODY + '</판례내용></PrecService>'
        if source == 'expc':
            content = '<ExpcService><회답>' + BODY + '</회답></ExpcService>'
        if source == 'fsc':
            content = '<table><tr><th>회답</th><td>' + BODY + '</td></tr></table>'
            suffix = '.html'
        if source in ('krx', 'kofia'):
            content = ('<div id="innerbody"><div class="Mjo"><a name="bon1"><strong>제1조(테스트)</strong></a>' + BODY + '</div></div>'
                       if source == 'krx' else '<div id="lawcontent"><div class="JO"><div class="article">제1조(테스트)</div><div class="hang">' + BODY + '</div></div></div>')
            suffix, field, hash_field = '.html', 'body_html_file', 'body_html_sha256'
        elif source != 'law':
            field, hash_field = 'file', 'sha256'
        path = Path(save(raw / source / ('문서' + suffix), content))
        item = {'name': source, 'label': source + ' 제목', 'kind': source, 'status': 'ok',
                field: str(path), hash_field: build.sha(path)}
        if source == 'krx':
            item['body_file'] = save(raw / source / '대체.hwp', 'alternate')
        save(raw / source / 'manifest.json', json.dumps({'items': [item], 'phase_model': source in corpus.CASE_SOURCES}))
    return raw


def test_all_seven_manifest_sources_and_internal(tmp_path):
    raw = fixture_corpus(tmp_path)
    plan, report = corpus.collect(raw, emit=lambda s: None)
    assert report['ok'] and report['unique_documents'] == 8
    assert set(report['sources']) == {*corpus.SOURCES, 'internal'}
    assert {r['source_parser'] for r in plan['files'] if r.get('source_parser')} == corpus.CASE_SOURCES
    assert any(e['reason'] == 'alternate_body_representation' for e in report['excluded'])
    assert all(r['kind'] == r.get('external_source', 'internal') for r in plan['files'])


@pytest.mark.parametrize('problem', ['missing', 'hash', 'traversal', 'symlink', 'status'])
def test_input_errors_accounted_not_silent(tmp_path, problem):
    raw = fixture_corpus(tmp_path)
    p = raw / 'law/manifest.json'; data = json.loads(p.read_text()); item = data['items'][0]
    if problem == 'missing':
        item['body_file'] = str(raw / 'law/missing.xml')
    elif problem == 'hash':
        item['body_sha256'] = '0' * 64
    elif problem == 'traversal':
        item['body_file'] = '../other.xml'
    elif problem == 'status':
        item['status'] = 'error'
    else:
        link = raw / 'law/link.xml'; link.symlink_to(raw / 'law/문서.xml'); item['body_file'] = str(link)
    p.write_text(json.dumps(data))
    _, report = corpus.collect(raw, emit=lambda s: None)
    if problem=='symlink':
        assert not report['ok'] and report['errors']
    else:
        assert report['ok'] and report['warnings']
        assert report['sources']['law']['selected']==1
    assert len(report['sources']) == 8


def test_duplicate_internal_preserves_alias_and_conflicting_authority_rejected(tmp_path):
    raw = fixture_corpus(tmp_path)
    save(raw / 'internal/다른부서/사본.xml', XML)
    plan, report = corpus.collect(raw, emit=lambda s: None)
    assert report['ok'] and len(report['aliases']) == 1
    assert next(r for r in plan['files'] if r['source'] == 'internal')['aliases']
    path = raw / 'law/문서.xml'; path.write_text(XML)
    m = raw / 'law/manifest.json'; data = json.loads(m.read_text())
    data['items'][0]['body_sha256'] = build.sha(path); m.write_text(json.dumps(data))
    _, report = corpus.collect(raw, emit=lambda s: None)
    assert not report['ok'] and any('conflicting' in r['error'] for r in report['errors'])


def test_case_full_body_and_source_fields_schema_build(setup):
    args, _, out = setup
    raw = fixture_corpus(out.parent / 'all')
    plan, report = corpus.collect(raw, emit=lambda s: None)
    # All source routes, with an XML document standing in for the manual's PDF.
    # Actual Docling installation/OCR quality is not tested by this synthetic contract.
    assert report['ok']
    result = build.execute(args, prepared_plan=plan, provider_factory=Fake, emit=lambda s: None)
    assert result['counts']['document'] == 8
    with sqlite3.connect(out / 'authoring-source.sqlite') as db:
        docs = {did: json.loads(payload) for did, payload in db.execute('SELECT document_id,json FROM document')}
        precedent = next(v for v in docs.values() if v.get('source_parser') == 'prec')
        assert precedent['source_fields']['body'] == BODY
        assert all(n['family'] == 'source_field' for n in precedent['nodes'])
        assert precedent['document_metadata']['kind'] == 'prec'
    assert any(r['source']['document_metadata'].get('external_source') == 'fsc' for r in Fake.instances[-1].calls)


def test_collects_all_structure_errors_before_models(setup):
    args, raw, out = setup
    save(raw / 'bad1.xml', 'not xml')
    save(raw / 'bad2.xml', 'also not xml')
    with pytest.raises(ValueError, match='2 document'):
        build.execute(args, provider_factory=Fake, emit=lambda s: None)
    errors = json.loads((out / 'structure-errors.json').read_text())
    assert len(errors) == 2 and all(r['traceback'] for r in errors)
    assert not Fake.instances and not (out / 'generation').exists()


def runner(monkeypatch, root):
    path = build.ROOT / '06_TOOLS/COMMANDS/genos_build_all.py'
    spec = importlib.util.spec_from_file_location('genos_all_test_runner', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', root)
    return module


def test_runner_logs_input_errors_and_masks_credentials(tmp_path, monkeypatch):
    root = tmp_path / 'DEV'; root.mkdir()
    module = runner(monkeypatch, root)
    monkeypatch.setenv('GENOS_TEST_KEY', 'do-not-leak-this-key')
    def fail(*a, **kw):
        print('visible progress')
        raise ValueError('do-not-leak-this-key synthetic error')
    monkeypatch.setattr(corpus, 'collect', fail)
    assert module.main(['--run-id', 'audit']) == 1
    log = (root / 'data/logs/audit/progress.log').read_text()
    assert 'visible progress' in log and 'Traceback' in log
    assert 'do-not-leak-this-key' not in log and '[REDACTED]' in log
    records = [json.loads(p.read_text()) for p in (root / 'data/logs/audit').glob('attempt-*.json')]
    assert records[0]['status'] == 'FAILED' and records[0]['exit_code'] == 1


def test_runner_check_only_append_and_no_provider(tmp_path, monkeypatch):
    root = tmp_path / 'DEV'; root.mkdir()
    fixture_corpus(root / 'data')
    module = runner(monkeypatch, root)
    monkeypatch.setattr(build, 'execute', lambda *a, **kw: pytest.fail('check-only called builder'))
    for _ in range(2):
        assert module.main(['--run-id', 'audit', '--check-only']) == 0
    directory = root / 'data/logs/audit'
    assert len(list(directory.glob('inventory-*.json'))) == 2
    assert len(list(directory.glob('attempt-*.json'))) == 2
    assert all(json.loads(p.read_text())['status'] == 'CHECKED' for p in directory.glob('attempt-*.json'))
    assert not (root / 'data/builds').exists()
