"""Synthetic RAW/transport contracts; no GENOS or model endpoint calls."""
import importlib.util
import json
from pathlib import Path
import zipfile
import fitz
import pytest
from lawrag.pipeline import team_raw as teams, raw_preprocess as prep, genos_build as build
from semantic_runtime.contracts import sha

def put(p, raw):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw.encode() if isinstance(raw, str) else raw)
    return p

def pdf(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(); doc.new_page(); doc.save(p); doc.close()
    return p

def test_order_zip_xml_pdf_and_resume(tmp_path, monkeypatch):
    root = tmp_path / 'RAW/external/new_team/분류'
    root.mkdir(parents=True)
    xml = '<법령><기본정보><법령명_한글>테스트</법령명_한글></기본정보><조문><조문단위 조문키="0001001"><조문번호>1</조문번호><조문여부>조문</조문여부><조문내용>제1조 테스트 내용</조문내용></조문단위></조문></법령>'
    with zipfile.ZipFile(root / '묶음.zip', 'w') as z:
        z.writestr('묶음/법령.xml', xml)
        z.writestr('묶음/규정.docx', b'fake native')
        z.writestr('묶음/서식.hwp', b'fake hwp')
    called = []
    def fake(source, work):
        assert (root / '묶음/법령.xml.md').exists()  # phase barrier
        called.append(source)
        result = pdf(work / 'source.pdf')
        return result, {'status': 'CONVERTED'}
    monkeypatch.setattr(prep, 'convert', fake)
    prep.run(build.ROOT, tmp_path, tmp_path / 'LOGS/run', execute=True)
    # Only the format without a structure-reading parser is converted.
    assert [s.suffix for s in called] == ['.hwp']
    plan, report = teams.collect(tmp_path, emit=lambda _: None)
    assert report['ok'] and len(plan['files']) == 3
    selected = {Path(r['path']).suffix: r for r in plan['files']}
    assert set(selected) == {'.xml', '.docx', '.pdf'}       # the HWP yields to its PDF
    assert not selected['.xml']['pdf_references'] and not selected['.docx']['pdf_references']
    assert [r['format'] for r in selected['.pdf']['representations'] if r['format'] == '.hwp']
    assert all(build.document_metadata(r)['team'] == 'new_team' for r in plan['files'])
    prep.run(build.ROOT, tmp_path, tmp_path / 'LOGS/run', execute=True)
    assert len(called) == 1

def test_off_and_check_never_convert_or_require_env(tmp_path, monkeypatch):
    p = put(tmp_path / 'RAW/internal/risk_team/규정.docx', 'original')
    monkeypatch.setattr(prep, 'convert', lambda *a: pytest.fail('must not call conversion'))
    prep.run(build.ROOT, tmp_path, tmp_path / 'logs', execute=False)
    prep.run(build.ROOT, tmp_path, tmp_path / 'logs', execute=True, pdf=False)
    assert not p.with_suffix('.pdf').exists()

def test_original_and_pdf_tamper_rejected(tmp_path, monkeypatch):
    p = put(tmp_path / 'RAW/internal/risk_team/a.docx', 'original')
    ref = pdf(p.with_suffix('.pdf'))
    build.atomic(tmp_path / 'CATALOG/RAW_DERIVATIVES.json', {'files': {
        str(ref.relative_to(tmp_path)): {'origin': str(p.relative_to(tmp_path)), 'origin_sha256': sha(p), 'sha256': sha(ref), 'kind': 'native_rendered_pdf'}}})
    put(p, 'changed')
    with pytest.raises(ValueError, match='changed'):
        teams.collect(tmp_path)

def test_migration_preserves_hierarchy_security_and_originals(tmp_path):
    p = put(tmp_path / 'PACKAGES/EXTERNAL/sample/RAW/law/상법/별표서식/별표.xml', '<법령/>')
    q = put(tmp_path / 'RAW/internal/1. 내규/규정.docx', 'internal')
    scope = tmp_path / 'CATALOG/SCOPES/scope.json'
    build.atomic(scope, {'documents': [{'name': '상법', 'files': [{'path': str(p.relative_to(tmp_path)),
        'sha256': sha(p), 'source': 'external', 'external_source': 'law', 'kind': 'law',
        'role': 'attachment', 'security_class': 'public', 'export_allowed': True}]}]})
    build.atomic(tmp_path / 'CATALOG/BUILD_SCOPE.json', {'path': str(scope.relative_to(tmp_path)), 'sha256': sha(scope)})
    assert teams.migrate(tmp_path)['status'] == 'PLANNED'
    assert not (tmp_path / 'CATALOG/TEAM_LAYOUT.json').exists()
    teams.migrate(tmp_path, apply=True)
    assert (tmp_path / 'RAW/external/risk_team/law/상법/별표서식/별표.xml').read_bytes() == p.read_bytes()
    assert (tmp_path / 'RAW/internal/risk_team/1. 내규/규정.docx').read_bytes() == q.read_bytes()
    assert teams.migrate(tmp_path, apply=True)['status'] == 'REUSED'
    plan, report = teams.collect(tmp_path, only_internal=True)
    assert report['ok'] and len(plan['files']) == 1
    assert plan['files'][0]['source_metadata']['export_allowed'] is False
    assert teams.rollback(tmp_path, apply=True)['status'] == 'ROLLED_BACK'
    assert not (tmp_path / 'CATALOG/TEAM_LAYOUT.json').exists()
    assert (tmp_path / 'RAW/internal/risk_team/1. 내규/규정.docx').exists()

def test_filter_does_not_touch_other_team_or_internal(tmp_path):
    put(tmp_path / 'RAW/external/third_team/a.docx', 'test')
    p = tmp_path / 'RAW/internal/risk_team/private.docx'
    p.parent.mkdir(parents=True); p.symlink_to('/does/not/exist')
    assert len(list(teams.inputs(tmp_path, exclude_internal=True, teams=['third_team']))) == 1

def test_pending_request_is_not_resubmitted(tmp_path, monkeypatch):
    source = put(tmp_path / 'RAW/internal/risk_team/a.hwp', 'native')
    import hashlib
    key = sha(source) + '-' + hashlib.sha256(str(source).encode()).hexdigest()[:12]
    build.atomic(tmp_path / 'logs' / key / 'conversion.json', {'status': 'PENDING'})
    monkeypatch.setattr(prep, 'convert', lambda *a: pytest.fail('must not resubmit'))
    with pytest.raises(ValueError, match='pending'):
        prep.run(build.ROOT, tmp_path, tmp_path / 'logs', execute=True)

@pytest.mark.parametrize('api_code,make_pdf,expected', [(0, True, 'CONVERTED'), (1, True, 'PDF_WITH_API_WARNING'), (0, False, 'FAILED')])
def test_converter_contract_requires_real_pdf(tmp_path, monkeypatch, api_code, make_pdf, expected):
    import httpx
    shared = tmp_path / 'shared'; shared.mkdir()
    monkeypatch.setenv('GENOS_PDF_CONVERTER_SHARED_ROOT', str(shared))
    monkeypatch.setenv('GENOS_PDF_CONVERTER_REMOTE_ROOT', '/remote/shared')
    monkeypatch.setenv('GENOS_PDF_CONVERTER_URL', 'http://preprocessor-187:8080/run')
    original_client = httpx.Client
    def handler(request):
        body = json.loads(request.content)
        assert all(v == 0 for v in body['params'].values())
        rel = Path(body['file_path']).relative_to('/remote/shared')
        staged = shared / rel
        assert staged.read_text() == 'native'
        if make_pdf:
            pdf(staged.with_suffix('.pdf'))
        return httpx.Response(200, json={'code': api_code, 'data': ['ignored parsed text']})
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original_client(transport=httpx.MockTransport(handler), **kw))
    source = put(tmp_path / 'a.docx', 'native')
    work = tmp_path / 'work'; work.mkdir()
    if make_pdf:
        output, evidence = prep.convert(source, work)
        assert prep.pdf_check(output) == 1 and evidence['status'] == expected
    else:
        with pytest.raises(ValueError, match='no valid'):
            prep.convert(source, work)
    assert json.loads((work / 'conversion.json').read_text())['status'] == expected
    assert source.read_text() == 'native'

def test_cli_team_preparation_is_connected(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('team_cli', build.ROOT / '06_TOOLS/COMMANDS/genos_data_stages.py')
    cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
    from lawrag.pipeline import genos_stages
    monkeypatch.setattr(genos_stages, 'offline_data_root', lambda _: tmp_path)
    build.atomic(tmp_path / 'CATALOG/TEAM_LAYOUT.json', {'schema_version': teams.VERSION, 'files': {}})
    p = put(tmp_path / 'RAW/internal/risk_team/a.hwp', 'native')
    assert cli.main(['--run-id', 'test', '--stage', 'raw', '--execute', '--pdf-conversion', 'off']) == 0
    assert not p.with_suffix('.pdf').exists()
    results = list((tmp_path / 'LOGS/test').glob('result-*.json'))
    assert json.loads(results[0].read_text())['preparation']['pdf_statuses']['DISABLED'] == 1

def test_changed_registered_input_is_checked_before_conversion(tmp_path, monkeypatch):
    p = put(tmp_path / 'RAW/external/risk_team/a.docx', 'original')
    build.atomic(tmp_path / 'CATALOG/TEAM_LAYOUT.json', {'schema_version': teams.VERSION, 'files': {
        str(p.relative_to(tmp_path)): {'sha256': sha(p)}}})
    put(p, 'changed')
    monkeypatch.setattr(prep, 'convert', lambda *a: pytest.fail('must validate before sending'))
    with pytest.raises(ValueError, match='before preparation'):
        prep.run(build.ROOT, tmp_path, tmp_path / 'logs', execute=True)
