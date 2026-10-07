"""Native DOCX contract; forbid local Docling imports, no model calls."""
import builtins
import ast
import io
import json
from pathlib import Path
import zipfile
import os
import subprocess

import pytest
from docx import Document
from lawrag.core.parse_adapter import parse_docx, result_to_dump, result_from_dump
from lawrag.core.structure import synthpdf


def test_no_docling_merged_cells_images_and_cache(tmp_path, monkeypatch):
    doc = Document()
    doc.add_heading('제1장 총칙', 1)
    doc.add_paragraph('제1조(목적) 원문')
    table = doc.add_table(rows=3, cols=3)
    table.cell(0, 0).merge(table.cell(0, 1)).text = '가로 병합'
    table.cell(1, 0).merge(table.cell(2, 0)).text = '세로 병합'
    doc.add_paragraph('표 뒤 문단')
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (10, 10)).save(image, format='PNG')
    image.seek(0)
    doc.add_picture(image)
    path = tmp_path / 'native.docx'
    doc.save(path)
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == 'docling' or name.startswith('docling.'):
            raise AssertionError('Docling must never be imported')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    parsed = parse_docx(path)
    assert parsed.elements[0].meta['level'] == 1
    t = next(e.table for e in parsed.elements if e.is_table)
    assert t.cell_at(0, 0).col_span == 2
    assert t.cell_at(1, 0).row_span == 2
    assert len(parsed.images) == 1
    assert synthpdf.paginate(parsed.elements).startswith(b'%PDF')
    # Existing synthetic-PDF cache remains the same public contract.
    dump = result_to_dump(parsed)
    assert 'docx-ooxml-native-v1' in dump['parser']


def test_corrupt_input_is_not_accepted(tmp_path):
    path = tmp_path / 'bad.docx'
    path.write_bytes(b'not a zip')
    with pytest.raises(zipfile.BadZipFile):
        parse_docx(path)


def test_field_txt_apply_idempotent_and_rollback(tmp_path):
    root = Path(__file__).resolve().parents[2]
    txt = root / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_DOCX_NATIVE_R1_UTF8.txt'
    subprocess.run(['bash', '-n', str(txt)], check=True)
    embedded = txt.read_text().split("<<'GENOS_DOCX_NATIVE_PY'\n", 1)[1].rsplit('GENOS_DOCX_NATIVE_PY', 1)[0]
    tree = ast.parse(embedded)
    value = next(n.value.args[0].value for n in tree.body
                 if isinstance(n, ast.Assign) and n.targets[0].id == 'PAYLOAD')
    payload = json.loads(value)
    assert payload['module'] == (root / '02_BACKEND/lawrag/core/docx_native.py').read_text()
    core = tmp_path / 'checkout/02_BACKEND/lawrag/core'
    core.mkdir(parents=True)
    adapter = core / 'parse_adapter.py'
    original = '# unrelated field changes preserved\n' + payload['old'] + '\n'
    adapter.write_text(original)
    data = tmp_path / 'data'
    env = {**os.environ, 'GENOS_DATA_ROOT': str(data)}
    checkout = tmp_path / 'checkout'
    def run(*args):
        return subprocess.run(['bash', str(txt), *args], cwd=checkout, env=env,
                              capture_output=True, text=True, check=True).stdout
    assert 'DOCX_NATIVE_APPLIED' in run()
    assert 'unrelated field changes' in adapter.read_text()
    assert payload['replacement'] in adapter.read_text()
    assert 'ALREADY_APPLIED' in run()
    receipt = next(checkout.glob('TRANSFER/BACKUPS/docx-native-r1/*/receipt.json'))
    assert 'ROLLBACK_PASS' in run('--rollback', str(receipt))
    assert adapter.read_text() == original
    assert not (core / 'docx_native.py').exists()
