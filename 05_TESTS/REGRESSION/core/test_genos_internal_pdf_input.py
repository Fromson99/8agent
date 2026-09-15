"""Staged CLI input selection and structure reuse; synthetic PDFs and transport only."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from lawrag.core import ingest, parse_adapter
from lawrag.pipeline import genos_build as build, genos_corpus as corpus, genos_stages as stages
from .test_genos_build import XML
from .test_ingest_glossary_linking import glossary
from .test_recipe_runtime import isolated_env, regional_document, regional_provider


def put(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def cli(monkeypatch, data):
    path = build.ROOT / '06_TOOLS/COMMANDS/genos_data_stages.py'
    spec = importlib.util.spec_from_file_location('internal_pdf_stages_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(stages, 'offline_data_root', lambda root: data)
    return module


def test_pdf_input_preserves_external_raw_and_excludes_originals(tmp_path):
    raw, pdf = tmp_path / 'RAW', tmp_path / 'PDF/internal'
    original = put(raw / 'internal/team/rule.xml', XML)
    selected = put(pdf / 'team/rule.PDF', 'synthetic PDF inventory bytes')
    put(pdf / 'team/rule.xml', XML)
    put(pdf / 'team/source.zip', 'synthetic archive')
    external = put(raw / 'law/law.xml', XML.replace('가상규정', '외규'))
    before = original.read_bytes()
    plan, report = corpus.collect(raw, internal_pdf_root=pdf, skip_invalid=True, emit=lambda s: None)
    assert report['ok']
    assert {row['path'] for row in plan['files']} == {str(selected), str(external)}
    row = next(r for r in plan['files'] if r['source'] == 'internal')
    assert row['relative'] == 'internal/team/rule.PDF' and row['kind'] == 'internal'
    assert row['input_collection'] == 'PDF/internal'
    assert row['sha256'] == build.sha(selected)
    assert plan['input_roots'] == {'external': str(raw), 'internal': str(pdf)}
    assert len([r for r in report['excluded'] if r['reason'] == 'non_pdf_internal']) == 2
    assert original.read_bytes() == before


@pytest.mark.parametrize('problem', ['missing', 'symlink', 'empty_pdf'])
def test_invalid_pdf_input_never_falls_back_to_raw(tmp_path, problem):
    raw, pdf = tmp_path / 'RAW', tmp_path / 'PDF/internal'
    put(raw / 'internal/original.xml', XML)
    if problem == 'symlink':
        pdf.parent.mkdir(parents=True)
        pdf.symlink_to(raw / 'internal', target_is_directory=True)
    elif problem == 'empty_pdf':
        put(pdf / 'empty.pdf', '')
    plan, report = corpus.collect(raw, internal_pdf_root=pdf, skip_invalid=True, emit=lambda s: None)
    assert not report['ok'] and report['errors'] and not plan['files']


def test_exclude_internal_does_not_inspect_pdf_tree(tmp_path, monkeypatch):
    raw, pdf = tmp_path / 'RAW', tmp_path / 'PDF/internal'
    put(raw / 'law/law.xml', XML)
    pdf.parent.mkdir(parents=True)
    pdf.symlink_to(tmp_path / 'missing-private-input', target_is_directory=True)
    original = Path.is_symlink
    def guard(path):
        assert path != pdf
        return original(path)
    monkeypatch.setattr(Path, 'is_symlink', guard)
    plan, report = corpus.collect(raw, internal_pdf_root=pdf, exclude_internal=True,
                                  skip_invalid=True, emit=lambda s: None)
    assert report['ok'] and len(plan['files']) == 1
    assert plan['input_roots']['internal'] is None


@pytest.mark.parametrize('problem', ['missing_pdf_root', 'empty_pdf_root', 'empty_pdf'])
def test_cli_input_failure_has_nonzero_exit(tmp_path, monkeypatch, problem):
    data = tmp_path / '01_DATA'
    put(data / 'RAW/internal/old.xml', XML)
    if problem != 'missing_pdf_root':
        (data / 'PDF/internal').mkdir(parents=True)
    if problem == 'empty_pdf':
        put(data / 'PDF/internal/bad.pdf', '')
    module = cli(monkeypatch, data)
    assert module.main(['--run-id', 'input-check', '--check-only']) == 2
    result = json.loads(next((data / 'LOGS/input-check').glob('result-*.json')).read_text())
    assert not result['ok'] and result['selected'] == 0


def test_cli_pdf_only_structure_vlm_and_cache_reuse(tmp_path, monkeypatch, glossary, capsys):
    data = tmp_path / '01_DATA'
    generated, blocks = regional_document(tmp_path)
    source = data / 'PDF/internal/team/rule.pdf'
    source.parent.mkdir(parents=True)
    shutil.copyfile(generated, source)
    model_requests = regional_provider(monkeypatch)
    parsed = parse_adapter.ParseResult(str(source), 'synthetic', 'synthetic', True,
        elements=[parse_adapter.Element(b.idx, 'text', b.text, page=b.page,
                  bbox=b.bbox, bbox_origin=b.bbox_origin) for b in blocks])
    parses = []
    def parse(pdf, *args):
        assert pdf.read_bytes() == source.read_bytes()
        parses.append(pdf)
        return parsed
    monkeypatch.setattr(ingest, 'parse_cached', parse)
    monkeypatch.setattr(stages, 'prepare_provider', lambda *a: pytest.fail('semantic/embed provider called'))
    module = cli(monkeypatch, data)
    args = ['--run-id', 'pdf-structure', '--stage', 'structure', '--execute',
            '--glossary-dir', str(glossary)]
    assert module.main(args) == 0, capsys.readouterr()
    assert len(parses) == 1 and model_requests
    calls = len(model_requests)
    structures = list((data / 'STRUCTURE').glob('*/structure/*/result.json'))
    assert len(structures) == 1
    saved = json.loads(structures[0].read_text())
    assert saved['document_metadata']['input_collection'] == 'PDF/internal'
    assert saved['recipe_review']['status'] in {'visual_approved', 'visual_sampled'}
    assert [b['text'] for b in saved['blocks']] == [b.text for b in blocks]
    assert module.main(args) == 0, capsys.readouterr()
    assert len(parses) == 1 and len(model_requests) == calls
    assert not (data / 'RAW').exists()
    assert not (data / 'LLM').exists() and not (data / 'VECTOR').exists()
    assert list((data / 'LEXICON/LINKS').glob('*/links.sqlite'))
