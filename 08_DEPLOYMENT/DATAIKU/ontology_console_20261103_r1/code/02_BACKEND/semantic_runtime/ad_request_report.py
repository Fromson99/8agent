"""Export an AD request through the existing team request-report writer.

AD SQL remains authoritative. Only the matching workspace/channel/chat/request
is exported; an unhandled AD probe produces no duplicate legal request report.
"""
import asyncio
from contextlib import nullcontext
from datetime import datetime, timezone
import json
import os
from . import runtime_sqlite as sqlite3
import time
from .oracle_runtime_paths import Path
from . import observability as obs
from .request_summary import request_fields

log = obs.get_logger('ad-report')


def bound_request(data):
    # Match ad_gateway's body selection exactly; outer identity fields must not
    # fill missing identities in an explicitly nested request.
    fields = data.get('json') if isinstance(data.get('json'), dict) else data
    workspace = os.environ.get('TEAM_ID') or os.environ.get('AD_WORKSPACE') or 'request'
    binding = {'workspace': workspace,
               'channel': fields.get('ad_channel') or fields.get('channel') or 'genos-chat',
               'chat': str(fields.get('ad_session_id') or fields.get('chatId') or fields.get('session_id') or '')}
    # AD team authority is deployment configuration, never arbitrary chat fields.
    return {**fields, 'team_id': workspace, 'ad_report_binding': binding}


async def intercept(gateway, data, runtime, application):
    from . import request_report as reports
    fields = request_fields(data)
    request_id = obs.new_request_id(fields.get('request_id'))
    data = {**data, 'request_id': request_id}
    if isinstance(data.get('json'), dict):
        data['json'] = {**data['json'], 'request_id': request_id}
    root = os.environ.get('GENOS_SHARED_LOG_DIR', '').strip()
    started_at, started = datetime.now(timezone.utc), time.perf_counter()
    capture = reports.capture_events(request_id, detailed=True) if root else nullcontext([])
    with capture as events, obs.context(request_id=request_id, api_type='AD_PROBE'):
        obs.event(log, 'request.started', component='ad_mode')
        result = await asyncio.to_thread(gateway.intercept, data, runtime, application)
        if result is None:
            return None
        body = result.get('body') or {}
        obs.event(log, 'request.finished', component='ad_mode', http_status=result.get('status'),
                  ok=body.get('answer_status') not in ('error', 'failed'),
                  duration_ms=int((time.perf_counter()-started)*1000))
        if root:
            try:
                with reports.DeferredReport(Path(root), runtime, request_id=request_id,
                        api_type=str(fields.get('API_TYPE') or 'AD_PROBE'),
                        request=bound_request(data), events=events, component='ad_mode',
                        started_at=started_at) as report:
                    report.complete(result)
                    obs.event(log, 'request.returning', component='ad_mode',
                              duration_ms=int((time.perf_counter()-started)*1000))
            except Exception as exc:
                obs.event(log, 'shared_report.failed', level=40, error_type=type(exc).__name__)
        return result


def journal(runtime, request_id, request):
    from .legal_agent.shortcut_store import selected_store
    binding = request.get('ad_report_binding') or {}
    if set(binding) != {'workspace', 'channel', 'chat'}:
        return {'status': 'MISSING_AD_BINDING', 'kind': 'ad_mode'}
    db = None
    try:
        path = selected_store(runtime)
        db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        rows = db.execute('''SELECT o.* FROM ad_operation o JOIN ad_session s ON s.id=o.session
            WHERE s.workspace=? AND s.channel=? AND s.chat=? AND o.request=?''',
            (binding['workspace'], binding['channel'], binding['chat'], request_id)).fetchall()
        if len(rows) != 1:
            return {'status': 'NOT_FOUND' if not rows else 'AMBIGUOUS', 'kind': 'ad_mode'}
        def decode(row):
            row = dict(row)
            for key in ('input','model_output','plan','receipt','response','before_value','after_value'):
                if isinstance(row.get(key), str):
                    try: row[key] = json.loads(row[key])
                    except ValueError: pass
            return row
        operation = decode(rows[0])
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {'status': 'FOUND', 'kind': 'ad_mode', 'operation': operation}
        for table, key, order in (('ad_language_call','calls','sequence'),
                                  ('ad_change','changes','ordinal'), ('ad_error','errors','created_at')):
            result[key] = ([decode(r) for r in db.execute(
                f'SELECT * FROM {table} WHERE operation=? ORDER BY {order}', (operation['id'],))]
                if table in tables else [])
        return result
    except Exception as exc:
        # Logging must not alter the administration result or run SQL migrations.
        return {'status': 'UNAVAILABLE', 'kind': 'ad_mode', 'error_type': type(exc).__name__}
    finally:
        if db is not None: db.close()


def readable(report):
    journal = report.get('journal') or {}
    body = (report.get('result') or {}).get('body') or {}
    lines = ['GENOS AD 요청 실행 기록', 'request_id: '+str(report.get('request_id')),
             'team: '+str(report.get('team_id')), 'journal: '+str(journal.get('status')),
             'answer_status: '+str(body.get('answer_status'))]
    if report.get('process_trace_path'):
        lines.append('전체 프롬프트·응답·단계별 누적 기록: ' + report['process_trace_path'])
    for call in journal.get('calls', []):
        response = call.get('model_output') or {}
        status = response.get('status_code') if isinstance(response, dict) else None
        lines += ['', '모델 호출 '+str(call['sequence'])+' / HTTP '+str(status or '응답 receipt 참조'),
                  json.dumps({'input': call.get('input'), 'response': response,
                              'receipt': call.get('receipt'), 'plan': call.get('plan')},
                             ensure_ascii=False, indent=2)]
    lines += ['', '최종 응답', str(body.get('text') or ''), '', '변경/오류 기록',
              json.dumps({'changes': journal.get('changes', []), 'errors': journal.get('errors', [])},
                         ensure_ascii=False, indent=2)]
    return '\n'.join(lines)+'\n'
