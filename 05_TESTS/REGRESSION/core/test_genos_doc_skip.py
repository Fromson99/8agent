"""Synthetic functional tests. No real documents, model requests or LibreOffice calls."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from lawrag.pipeline import genos_batch as batch, genos_doc as doc, genos_build as build, genos_corpus as corpus
from .test_genos_build import Fake, XML, BODY, setup
from .test_genos_all_corpus import fixture_corpus, save


def test_inventory_isolates_bad_tags_and_excludes_caches(tmp_path):
    raw = fixture_corpus(tmp_path)
    save(raw / 'internal/team/sub/old.doc', 'old word')
    save(raw / 'internal/other.gul', 'unsupported')
    save(raw / 'internal/bad.pdf', 'bad')
    save(raw / 'internal/bad.pdf.genos.json', '{bad json')
    for name in ('Thumbs.db', 'desktop.ini', '~$lock.doc', 'archive.zip'):
        save(raw / 'internal' / name, 'cache')
    plan, report = corpus.collect(raw, skip_invalid=True, emit=lambda s: None)
    assert len(plan['files']) == 9
    assert len(report['errors']) == 2
    assert batch.input_summary(plan, report)['total'] == 11
    assert sum(r.get('reason') == 'system_cache' for r in report['excluded']) == 3


def test_batch_real_pipeline_skips_bad_structure_and_preserves_good(setup):
    args, raw, out = setup
    save(raw / 'bad.xml', 'malformed xml')
    plan = build.inventory(raw, 'internal')
    report = {'errors': [{'scope': 'document', 'item': 'old.gul', 'error': 'unsupported'}], 'excluded': [], 'aliases': []}
    result = batch.execute(args, plan, report, provider_factory=Fake, emit=lambda s: None)
    assert result['status'] == 'COMPLETED_WITH_SKIPS' and not result['ok']
    assert result['accounting'] == batch.accounting(1, 2)
    assert len(result['generations']) == 1
    assert Path(result['generations'][0]).is_dir()
    assert not (out / 'generation').exists()
    assert sum(len(p.calls) for p in Fake.instances) == 2
    args.resume = True
    again = batch.execute(args, plan, report, provider_factory=Fake, emit=lambda s: None)
    assert again['accounting'] == result['accounting']
    assert again['llm_calls_this_invocation'] == 0
    assert all(p.read_text() in {XML, 'malformed xml'} for p in raw.glob('*.xml'))


@pytest.mark.parametrize('failure', ['authoring', 'embedding'])
def test_failed_model_document_never_enters_catalog(setup, failure):
    args, raw, out = setup
    save(raw / 'two.xml', XML.replace('가상', '별도'))
    plan = build.inventory(raw, 'internal')
    class Selective(Fake):
        made = 0
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            type(self).made += 1
            self.invalid = failure == 'authoring' and type(self).made == 1
            self.fail_embed_after = 0 if failure == 'embedding' and type(self).made == 1 else None
    report = {'errors': [], 'excluded': [], 'aliases': []}
    result = batch.execute(args, plan, report, provider_factory=Selective, emit=lambda s: None)
    assert result['accounting'] == batch.accounting(1, 1)
    assert len(result['generations']) == 1
    failed = next(r for r in result['records'] if r['status'] == 'SKIPPED')
    assert not (out / 'documents' / failed['document_id'] / 'generation').exists()


def test_global_budget_not_multiplied_by_documents(setup):
    args, raw, _ = setup
    args.max_calls = 2
    save(raw / 'two.xml', XML.replace('가상', '별도'))
    plan = build.inventory(raw, 'internal')
    result = batch.execute(args, plan, {'errors': [], 'excluded': [], 'aliases': []}, provider_factory=Fake, emit=lambda s: None)
    assert result['llm_calls_this_invocation'] == 2
    assert result['accounting'] == batch.accounting(1, 1)
    assert result['records'][1]['stage'] == 'budget'


def test_all_skipped_and_source_errors_are_not_success(setup):
    args, raw, _ = setup
    plan = build.inventory(raw, 'internal'); plan['files'] = []
    report = {'errors': [{'scope': 'document', 'item': 'bad.gul'}, {'scope': 'source', 'item': 'law/manifest'}], 'excluded': [], 'aliases': []}
    result = batch.execute(args, plan, report, emit=lambda s: None)
    assert result['status'] == 'FAILED' and not result['ok']
    assert result['accounting'] == batch.accounting(0, 1)
    assert len(result['source_errors']) == 1
    assert not Fake.instances


def doc_row(tmp_path):
    source = tmp_path / 'old.doc'; source.write_bytes(b'synthetic DOC input')
    return {'path': str(source), 'relative': 'internal/team/old.doc', 'sha256': build.sha(source),
            'document_id': build.sha(source)[:16], 'source': 'internal', 'name': 'old', 'folder': 'team', 'doc_type': None, 'engine': ''}


def fake_converter(monkeypatch, tmp_path):
    binary = tmp_path / 'fake-soffice'; binary.write_text('synthetic converter')
    monkeypatch.setattr(doc.shutil, 'which', lambda _: str(binary))
    def run(argv, **kwargs):
        assert kwargs['timeout'] > 0 and '--headless' in argv
        assert argv[1].startswith('-env:UserInstallation=file:')
        target = Path(argv[argv.index('--outdir') + 1]) / 'source.docx'
        from docx import Document
        document = Document()
        document.add_heading('제1조(테스트)', level=1)
        document.add_paragraph(BODY)
        document.save(target)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(doc, 'subprocess', SimpleNamespace(run=run))


def test_doc_conversion_lineage_and_resume_no_reconversion(tmp_path, monkeypatch):
    row = doc_row(tmp_path)
    fake_converter(monkeypatch, tmp_path)
    converted = doc.prepare(row, tmp_path / 'conversions', emit=lambda s: None)
    assert converted['conversion']['original_sha256'] == row['sha256']
    assert converted['relative'] == row['relative']
    assert converted['sha256'] == build.sha(converted['path']) != row['sha256']
    assert build.sha(row['path']) == row['sha256']
    monkeypatch.setattr(doc.subprocess, 'run', lambda *a, **kw: pytest.fail('unexpected reconversion'))
    assert doc.prepare(row, tmp_path / 'conversions') == converted
    Path(converted['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='receipt/hash mismatch'):
        doc.prepare(row, tmp_path / 'conversions')


def test_doc_missing_converter_and_bad_output(tmp_path, monkeypatch):
    row = doc_row(tmp_path)
    monkeypatch.setattr(doc.shutil, 'which', lambda _: None)
    with pytest.raises(ValueError, match='LibreOffice'):
        doc.prepare(row, tmp_path / 'conversions')
    fake_converter(monkeypatch, tmp_path)
    monkeypatch.setattr(doc.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(ValueError, match='conversion failed'):
        doc.prepare(row, tmp_path / 'conversions')
    assert build.sha(row['path']) == row['sha256']


def test_doc_parse_uses_derived_coordinate_hash_and_original_metadata(tmp_path, monkeypatch):
    row = doc_row(tmp_path)
    row['engine'] = 'docxstyle'
    fake_converter(monkeypatch, tmp_path)
    converted = doc.prepare(row, tmp_path / 'conversions')
    out = tmp_path / 'build'; out.mkdir()
    with build.isolated(out):
        build.ingest_files({'files': [converted]}, out, lambda s: None)
        source, _ = build.source_jobs(out, {'files': [converted]})
    import sqlite3
    with sqlite3.connect(source) as db:
        did, name, fingerprint, payload = db.execute('SELECT * FROM document').fetchone()
    assert did == converted['document_id'] and fingerprint == converted['sha256']
    assert json.loads(payload)['document_metadata']['conversion']['original_sha256'] == row['sha256']
    assert 'internal > team > old' == name


def test_doc_full_build_with_fake_provider(setup, monkeypatch):
    args, raw, out = setup
    row = doc_row(raw)
    save(raw / 'old.doc.genos.json', '{"engine":"docxstyle"}')
    fake_converter(monkeypatch, out.parent)
    plan = build.inventory(raw, 'internal', selected=[Path(row['path'])])
    result = batch.execute(args, plan, {'errors': [], 'excluded': [], 'aliases': []}, provider_factory=Fake, emit=lambda s: None)
    assert result['ok'], result['records']
    assert result['accounting'] == batch.accounting(1, 0)
    assert build.sha(row['path']) == row['sha256']


def test_resume_rejects_input_change_before_models(setup):
    args, raw, _ = setup
    report = {'errors': [], 'excluded': [], 'aliases': []}
    plan = build.inventory(raw, 'internal')
    batch.execute(args, plan, report, provider_factory=Fake, emit=lambda s: None)
    args.resume = True
    save(raw / 'one.xml', XML.replace('가상', '수정'))
    with pytest.raises(ValueError, match='NEW run-id'):
        batch.execute(args, build.inventory(raw, 'internal'), report, provider_factory=Fake, emit=lambda s: None)
    assert len(Fake.instances) == 1
