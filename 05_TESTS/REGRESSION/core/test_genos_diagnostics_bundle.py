"""Read-only GENOS handoff checks against a synthetic internal report."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from semantic_runtime.request_report import format_readable_report


ROOT = next(path for path in Path(__file__).resolve().parents
            if (path / '00_SYSTEM/WORKSPACE.json').is_file())
SCRIPTS = ROOT / '08_DEPLOYMENT/GENOS/diagnostics'


def _report(tmp_path):
    run_id = 'a' * 32
    directory = tmp_path / '2026-09-23'
    directory.mkdir()
    report = {
        'schema_version': 'genos-request-report-v1', 'created_at': '2026-09-23T00:00:00Z',
        'request_id': 'request-1', 'run_id': run_id, 'api_type': 'LEGAL_AGENT',
        'request': {'question': 'PRIVATE QUESTION'},
        'result': {'status': 200, 'body': {'answer': {'text': 'PRIVATE ANSWER', 'claims': [], 'unresolved': [1]}}},
        'service_events': [
            {'ts': '2026-09-23T00:00:00Z', 'event': 'model_http.failed', 'level': 'ERROR',
             'http_status': 400, 'upstream_error_type': 'BadRequestError'},
            {'ts': '2026-09-23T00:00:01Z', 'event': 'request.finished', 'level': 'INFO', 'http_status': 200}],
        'journal': {'status': 'FOUND', 'timeline': [
            {'event': {'seq': 1, 'kind': 'MODEL_SENT', 'payload': {'decision': 'INVESTIGATE'}},
             'created_records': [{'table': 'model_attempt', 'record': {
                 'attempt_id': 'attempt-1', 'attempt_no': 1, 'status': 'FAILED',
                 'request': {'model': '2366', 'max_tokens': 6400, 'stream': False,
                             'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False},
                             'response_format': {'type': 'json_schema', 'json_schema': {
                                 'name': 'Plan', 'strict': True, 'schema': {'properties': {'a': {}}}}},
                             'messages': [{'content': 'PRIVATE PROMPT'}]},
                 'response': {'status_code': 400, 'body_json': {'error': {
                     'type': 'BadRequestError', 'code': 'invalid_request',
                     'message': 'max_tokens too large'}}}}}]}],
            'state': {'run': [{'status': 'FAILED', 'phase': 'END'}]}}
    }
    path = directory / f'{run_id}-sample.json'
    path.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    return path


def _run(name, root, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), '--root', str(root), *args],
                          capture_output=True, text=True, check=True).stdout


def test_diagnostics_are_read_only_and_hide_internal_content_by_default(tmp_path):
    _report(tmp_path)
    for name in ('01_latest_status.py', '02_model_rejection.py',
                 '03_agent_flow.py', '04_shared_storage.py', '05_team_data_access.py'):
        output = _run(name, tmp_path, *(['--run-id', 'a' * 32]
                                         if name == '05_team_data_access.py' else []))
        assert 'PRIVATE QUESTION' not in output
        assert 'PRIVATE PROMPT' not in output
        assert 'PRIVATE ANSWER' not in output
    model = json.loads(_run('02_model_rejection.py', tmp_path))
    assert model['failed_attempts'][0]['http_status'] == 400
    assert model['failed_attempts'][0]['max_tokens'] == 6400
    assert 'max_tokens too large' not in json.dumps(model)
    assert 'max_tokens too large' in _run('02_model_rejection.py', tmp_path, '--show-message')
    flow = json.loads(_run('03_agent_flow.py', tmp_path))
    assert flow['event_sequence_contiguous'] is True
    assert flow['model_attempt_count'] == 1


def test_readable_report_lists_search_rejection_in_time_order_without_prompt(tmp_path):
    path = _report(tmp_path)
    report = json.loads(path.read_text(encoding='utf-8'))
    report['journal']['timeline'] = [
        {'event': {'seq': 1, 'kind': 'WORKFLOW_TURN', 'created_at': '2026-09-23T00:00:00.100Z',
                   'payload': {'decision': {'intent': 'CONTINUE', 'actions': [
                       {'tool': 'search', 'args': {'mode': 'fulltext', 'target': 'R1',
                                                   'query': '모의 문서 제목'}}]}}},
         'created_records': []},
        {'event': {'seq': 2, 'kind': 'WORKFLOW_REPAIR', 'created_at': '2026-09-23T00:00:00.200Z',
                   'payload': {'errors': [{'field': 'actions[0]', 'message': 'fulltext unavailable'}]}},
         'created_records': []},
    ]
    text = format_readable_report(report)
    assert text.index('WORKFLOW_TURN') < text.index('WORKFLOW_REPAIR')
    assert 'tool=search mode=fulltext target=R1 query=모의 문서 제목' in text
    assert 'rejected actions[0]: fulltext unavailable' in text
    assert 'PRIVATE PROMPT' not in text


def test_model_rejection_selects_latest_failure_over_newer_source_only_run(tmp_path):
    failed_path = _report(tmp_path)
    newer_id = 'b' * 32
    newer_path = failed_path.with_name(f'{newer_id}-sample.json')
    newer = json.loads(failed_path.read_text(encoding='utf-8'))
    newer['run_id'] = newer_id
    newer['service_events'] = [{'event': 'request.finished', 'http_status': 200}]
    newer['journal'] = {'status': 'FOUND', 'timeline': [], 'state': {'run': [{'status': 'COMPLETED'}]}}
    newer_path.write_text(json.dumps(newer), encoding='utf-8')
    timestamp = failed_path.stat().st_mtime_ns + 1_000_000_000
    os.utime(newer_path, ns=(timestamp, timestamp))

    selected = json.loads(_run('02_model_rejection.py', tmp_path))
    assert selected['run_id'] == 'a' * 32
    assert selected['selection'] == 'latest_model_failure'
    assert selected['failed_attempts'][0]['http_status'] == 400

    newest = json.loads(_run('02_model_rejection.py', tmp_path, '--newest'))
    assert newest['run_id'] == newer_id
    assert newest['selection'] == 'newest_report'
    assert newest['failed_attempts'] == []


def test_team_data_access_reports_effective_scope_and_read_sources(tmp_path):
    report_path = _report(tmp_path)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report['request']['team_id'] = 'risk_team'
    report['result']['body']['query'] = {
        'generation_id': 'generation-1', 'scope': {'document_version_ids': ['doc-risk']}}
    report['result']['body']['answer']['source_store_sha256'] = 'b' * 64
    report['result']['body']['retrieval'] = {'candidates': [{'document_id': 'doc-risk'}],
                                              'term_agent': {'implementation': 'legal-agent-tools-v5'}}
    report['journal']['timeline'].append({'event': {'seq': 2, 'kind': 'OBSERVATION'},
        'created_records': [
            {'table': 'observation', 'record': {'tool': 'read_node', 'status': 'OK'}},
            {'table': 'evidence_unit', 'record': {'document_id': 'doc-risk'}}]})
    report_path.write_text(json.dumps(report), encoding='utf-8')

    generation = tmp_path / 'shared' / 'term-releases' / 'run-1' / 'reviewed' / 'generation'
    generation.mkdir(parents=True)
    (generation / 'manifest.json').write_text(json.dumps({
        'schema_version': 'term-source-generation-v1', 'generation_id': 'generation-1',
        'store_sha256': 'b' * 64}), encoding='utf-8')
    with sqlite3.connect(generation / 'store.sqlite') as db:
        db.execute('CREATE TABLE document (document_id TEXT, name TEXT, json TEXT)')
        db.executemany('INSERT INTO document VALUES (?,?,?)', [
            ('doc-risk', '모의 위험관리 규정', json.dumps({'document_metadata': {'team': 'risk_team'}})),
            ('doc-other', '모의 타부서 규정', json.dumps({'document_metadata': {'team': 'other_team'}})),
        ])
    result = json.loads(_run('05_team_data_access.py', tmp_path, '--generation', str(generation)))
    assert result['request_team_id'] == 'risk_team'
    assert result['team_filter_status'] == 'FILTER_CONFIRMED_FOR_REQUEST_SCOPE'
    assert result['generation_catalogue']['store_sqlite_read'] is True
    assert result['generation_catalogue']['selected_team_document_count'] == 1
    assert result['source_text_read_document_ids'] == ['doc-risk']
    assert result['generation_catalogue']['source_text_read_documents'][0]['name'] == '모의 위험관리 규정'
    assert 'PRIVATE QUESTION' not in json.dumps(result)
