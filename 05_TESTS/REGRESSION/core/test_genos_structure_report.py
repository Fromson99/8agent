"""Saved PDF -> final bbox HTML -> status export, with no additional model calls."""
import copy
import json
from pathlib import Path

import pytest

from lawrag.core import ingest, parse_adapter
from lawrag.core.structure import recipe_evidence
from lawrag.core.structure.model import Block
from lawrag.pipeline import genos_build as build, genos_stages as stages
from lawrag.pipeline.genos_status import Ledger, export_report, read_report
from lawrag.pipeline.genos_structure_report import document_report
from .test_recipe_runtime import isolated_env, regional_document
from .test_recipe_warning_pass import transport


@pytest.fixture
def saved(tmp_path, monkeypatch):
    seen = transport(monkeypatch, 'hold')
    pdf, blocks = regional_document(tmp_path, 2)
    blocks.insert(0, Block(0, '모의 규정 제목', page=1, bbox=[50,10,400,30], bbox_origin='TOPLEFT'))
    blocks.append(Block(len(blocks), '좌표 없는 본문', page=2))
    for idx, b in enumerate(blocks): b.idx = idx
    parsed = parse_adapter.ParseResult(str(pdf), 'synthetic', 'synthetic', True, elements=[
        parse_adapter.Element(b.idx, 'text', b.text, page=b.page, bbox=b.bbox, bbox_origin=b.bbox_origin) for b in blocks])
    monkeypatch.setattr(ingest, 'parse_cached', lambda *a: copy.deepcopy(parsed))
    row = {'path':str(pdf), 'sha256':build.sha(pdf), 'document_id':build.sha(pdf)[:16],
           'name':'<script>모의 규정</script>', 'relative':'internal/source.pdf', 'source':'internal',
           'folder':'내규', 'doc_type':'', 'engine':'', 'kind':'internal'}
    plan = {'files':[row], 'format_assets':{}}
    folder, _ = stages.structure(row, plan, tmp_path/'data', {'synthetic':'html-contract'},30,lambda _:None)
    logs = tmp_path/'data/LOGS/one'
    ledger = Ledger(logs).start([row], 'structure')
    ledger.update(row['document_id'], 'structure', 'PASSED', output_path=str(folder))
    ledger.finish();ledger.close()
    return logs, folder, read_report(logs), seen, pdf


def test_final_payload_and_both_pages_exported_without_calls_or_cache_mutation(saved, monkeypatch):
    logs, folder, report, seen, _ = saved
    initial = stages.files_hashes(folder)
    calls = len(seen)
    paths = export_report(logs, report)
    page = next((logs/'structure-images').glob('*/index.html'))
    evidence = json.loads((page.parent/'images/evidence.json').read_text())
    stored = json.loads(next((folder/'structure').glob('*/result.json')).read_text())
    rendered = json.loads((page.parent/'images/viewer-payload.json').read_text())
    assert rendered == stored
    assert any(n.get('family') == 'unstructured_text' for n in rendered['nodes'])
    assert len(evidence['images']) == 4 and evidence['blocks_without_rectangles']
    text = page.read_text()
    assert 'accepted_with_warnings' in text and '좌표 없는 블록 1개' in text
    assert '<script>모의 규정</script>' not in text and '&lt;script&gt;' in text
    assert 'loading="lazy"' in text and 'page-2-viewer-overlay.png' in text
    assert page.relative_to(logs).as_posix() in Path(paths['html']).read_text()
    assert Path(paths['images']).is_file()
    assert len(seen) == calls and stages.files_hashes(folder) == initial
    stages.verify_structure(folder)
    monkeypatch.setattr(recipe_evidence, 'payload_images', lambda *a, **kw: pytest.fail('unnecessary render'))
    assert document_report(logs, report['documents'][0])['reused']
    export_report(logs, report)
    assert len(seen) == calls


def test_pdf_changed_cannot_be_presented_as_saved_structure(saved):
    logs, _, report, seen, pdf = saved
    calls = len(seen)
    pdf.write_bytes(pdf.read_bytes()+b'\nchanged')
    paths = export_report(logs, report)
    assert '원본 PDF 해시가 다릅니다' in Path(paths['images']).read_text()
    assert read_report(logs)['counts']['structure']['PASSED'] == 1
    assert not list((logs/'structure-images').glob('*/index.html'))
    assert len(seen) == calls


def test_cached_image_tamper_reported_without_rewriting_source(saved):
    logs, folder, report, _, _ = saved
    export_report(logs, report)
    image = next((logs/'structure-images').glob('*/images/page-1-viewer-overlay.png'))
    image.write_bytes(b'broken')
    paths = export_report(logs, report)
    assert '이미지 보고서 해시 불일치' in Path(paths['images']).read_text()
    stages.verify_structure(folder)


def test_image_failure_does_not_fail_saved_document(saved, monkeypatch):
    logs, folder, report, _, _ = saved
    def fail(*args, **kwargs): raise OSError('synthetic render failure')
    monkeypatch.setattr(recipe_evidence, 'payload_images', fail)
    paths = export_report(logs, report)
    assert 'synthetic render failure' in Path(paths['html']).read_text()
    assert read_report(logs)['counts']['structure']['PASSED'] == 1
    assert not list((logs/'structure-images').glob('.render-*'))
    stages.verify_structure(folder)


def test_pending_has_no_image_claim(tmp_path):
    ledger = Ledger(tmp_path).start([{'document_id':'pending','name':'pending','relative':'pending.pdf','source':'internal'}], 'structure')
    paths = export_report(tmp_path)
    assert '저장된 구조화 성공 결과 없음' in Path(paths['images']).read_text()
    assert not (tmp_path/'structure-images').exists()
    ledger.close()
