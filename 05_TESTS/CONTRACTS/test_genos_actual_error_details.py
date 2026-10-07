import builtins
import json

import pytest

from lawrag.pipeline import raw_preprocess as prep
from lawrag.pipeline.genos_progress import reason
from semantic_runtime.genos_backend import Genos, error_detail


def test_cause_types_messages_and_credential_redaction(monkeypatch):
    monkeypatch.setenv('GENOS_LLM_KEY', 'secret-fixture')
    try:
        try:
            raise FileNotFoundError('missing source.pdf secret-fixture')
        except FileNotFoundError as cause:
            raise ValueError('PDF preparation failed') from cause
    except ValueError as exc:
        detail = error_detail(exc)
        assert 'ValueError: PDF preparation failed' in detail
        assert 'FileNotFoundError: missing source.pdf' in detail
        assert 'secret-fixture' not in detail
        assert reason(exc) == detail


def test_reason_keeps_original_schema_message():
    original = "schema path graph/clauses/0: 'id' is a required property"
    value = reason(original)
    assert value.startswith(original)
    assert '필수 필드 없음' in value


def test_missing_pymupdf_is_reported_as_missing_dependency(tmp_path, monkeypatch):
    native_import = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == 'fitz':
            raise ModuleNotFoundError("No module named 'fitz'", name='fitz')
        return native_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', missing)
    with pytest.raises(ImportError, match='PyMuPDF.*ModuleNotFoundError.*fitz'):
        prep.pdf_check(tmp_path/'source.pdf')


def test_model_validation_exposes_exact_error_and_saves_it(tmp_path):
    provider = Genos(tmp_path, tmp_path/'output')
    provider.models['llm'] = 'fixture-model'
    run = tmp_path/'response'
    run.mkdir()
    provider.request = lambda *args: ({'choices': [{'message': {'content': '{broken'}}]},
                                      {'path': str(run/'receipt.json')})
    with pytest.raises(ValueError, match='response validation failed: JSONDecodeError'):
        provider.call('fixture-role', 'task', {}, {'type': 'object'})
    assert 'JSONDecodeError' in json.loads((run/'validation-error.json').read_text())['error']


def test_conversion_receipt_keeps_missing_dependency_not_generic_pdf_error(tmp_path, monkeypatch):
    import httpx
    shared = tmp_path/'shared'
    shared.mkdir()
    source = tmp_path/'source.doc'
    source.write_bytes(b'fixture-original')
    work = tmp_path/'work'
    work.mkdir()
    monkeypatch.setenv('GENOS_PDF_CONVERTER_SHARED_ROOT', str(shared))
    monkeypatch.setenv('GENOS_PDF_CONVERTER_URL', 'http://preprocessor-187:8080/run')
    original_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'code': 1})), **kw))
    def missing(path):
        raise ModuleNotFoundError("No module named 'fitz'", name='fitz')
    monkeypatch.setattr(prep, 'pdf_check', missing)
    with pytest.raises(ModuleNotFoundError, match='fitz'):
        prep.convert(source, work)
    receipt = json.loads((work/'conversion.json').read_text())
    assert receipt['error_type'] == 'ModuleNotFoundError'
    assert "No module named 'fitz'" in receipt['error']
    assert receipt['http_status'] == 200 and receipt['api_code'] == 1
