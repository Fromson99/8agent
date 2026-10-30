"""Append-only, operator-readable request trace. Never used as model input.

The SQL journal and saved JSON remain the byte-preserving authorities. This
projection expands JSON strings and prefixes data lines so model text cannot
impersonate a stage heading. All I/O runs on existing report workers.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
import threading


def decoded(row):
    result = dict(row)
    for key, value in list(result.items()):
        if key.endswith('_json') and isinstance(value, str):
            try:
                result[key[:-5]] = json.loads(value)
                del result[key]
            except ValueError:
                pass
    return result


def text_lines(value, depth=0):
    """No content/count clipping; retain types, empty values and line breaks."""
    pad = '  ' * depth
    if isinstance(value, dict):
        if not value:
            yield pad + '{}'
        for key, item in value.items():
            label = json.dumps(str(key), ensure_ascii=False)[1:-1]
            if not isinstance(item, (dict, list)) and (not isinstance(item, str) or '\n' not in item):
                yield pad + label + ': ' + next(text_lines(item))
            else:
                yield pad + label + ':'
                yield from text_lines(item, depth + 1)
    elif isinstance(value, list):
        if not value:
            yield pad + '[]'
        for index, item in enumerate(value, 1):
            if not isinstance(item, (dict, list)) and (not isinstance(item, str) or '\n' not in item):
                yield pad + f'[{index}] ' + next(text_lines(item))
            else:
                yield pad + f'[{index}]'
                yield from text_lines(item, depth + 1)
    elif isinstance(value, str):
        # Keep multiline strings readable. Escape terminal control characters,
        # including CR, while preserving LF paragraphs and visible tabs.
        value = ''.join(ch if ch in '\n\t' or ch.isprintable()
                        else f'\\u{ord(ch):04x}' for ch in value)
        for line in value.split('\n'):
            yield pad + (line if line else '""')
    else:
        yield pad + json.dumps(value, ensure_ascii=False, default=str)


def section(label, value):
    label = ''.join(ch if ch.isprintable() else f'\\u{ord(ch):04x}' for ch in str(label))
    return '\n' + label + '\n' + '\n'.join('| ' + line for line in text_lines(value)) + '\n'


class ErrorSections:
    """Exact duplicate error bodies are references; distinct attempts remain events."""
    def __init__(self):
        self.details = {}
        self.lock = threading.RLock()

    def prepare(self, value):
        with self.lock:
            return self._prepare(value)

    def _prepare(self, value):
        additions = []
        summaries = []

        def visit(item, key=''):
            if key == 'error_record' and isinstance(item, str):
                try:
                    return visit(json.loads(item))
                except ValueError:
                    pass
            if key in ('traceback', 'async_exception') and isinstance(item, str) and item:
                digest = hashlib.sha256(item.encode()).hexdigest()
                ident = self.details.get(digest)
                if ident is None:
                    ident = 'ERR-' + str(len(self.details) + 1).zfill(4)
                    self.details[digest] = ident
                    additions.append((ident, item))
                terminal = next((line for line in reversed(item.splitlines()) if line.strip()), '')
                summaries.append({'상세 오류 번호': ident, '최종 예외': terminal[:320],
                    '원인': '모델 응답 대기 시간 초과' if any(s in terminal.lower() for s in
                        ('model transmission timed out', 'http deadline exceeded')) else '아래 오류 코드·메시지 참조'})
                return '상세 오류 ' + ident + ' 참조 (같은 traceback은 최초 한 번만 기록)'
            if isinstance(item, dict):
                if any(item.get(k) for k in ('error_code', 'error_message', 'error_type', 'retry_scheduled')):
                    summaries.append({k: (item[k][:320] if isinstance(item[k], str) else item[k]) for k in ('error_code', 'error_type', 'error_message',
                        'stage', 'phase', 'source_stage', 'attempt_id', 'duration_ms', 'retry_scheduled',
                        'retryable', 'status', 'location') if k in item})
                result = {k: visit(v, k) for k, v in item.items()}
                # A wrapper often repeats the identical diagnostics as both a
                # decoded object and an error_record string. Preserve one body.
                seen = {}
                for k, v in result.items():
                    if isinstance(v, (dict, list)) and k in ('diagnostics', 'failure_diagnostics', 'error_diagnostics', 'error_record'):
                        digest = json.dumps(v, sort_keys=True, ensure_ascii=False)
                        if digest in seen:
                            result[k] = '동일 상세: ' + seen[digest] + ' 참조'
                        else:
                            seen[digest] = k
                return result
            if isinstance(item, list):
                return [visit(v) for v in item]
            return item

        projected = visit(value)
        if summaries and isinstance(value, dict):
            context = {}
            duration = number(value.get('duration_ms'))
            if duration is not None:
                context['대기/처리 시간(초)'] = duration / 1000
            if type(value.get('retry_scheduled')) is bool:
                context['재시도 예약'] = '예' if value['retry_scheduled'] else '아니오'
            if context:
                summaries.insert(0, context)
        unique = {json.dumps(row, sort_keys=True, ensure_ascii=False): row for row in summaries}
        prefix = section('오류 요약 (상세 traceback은 오류 번호로 연결)', list(unique.values())) if unique else ''
        suffix = ''.join(section('상세 오류 ' + ident + ' / 전체 traceback · 최초 기록', text)
                         for ident, text in additions)
        return projected, prefix, suffix

    def render(self, value):
        projected, prefix, suffix = self.prepare(value)
        return prefix + section('오류·복구 기록', projected) + suffix


def message_content(value):
    if isinstance(value, str):
        try:
            expanded = json.loads(value)
            if isinstance(expanded, (dict, list)):
                from .request_report import _scrub
                return _scrub(expanded)
        except ValueError:
            pass
    return value


def request_sections(request):
    if not isinstance(request, dict):
        return section('전송 요청: 미기록', request)
    settings = section('실제 전송 설정 / 출력 스키마',
                     {k: v for k, v in request.items() if k != 'messages'})
    result = ''
    messages = request.get('messages')
    if not isinstance(messages, list):
        return settings + section('입력 메시지: 미기록', messages)
    for index, message in enumerate(messages, 1):
        if not isinstance(message, dict):
            result += section(f'입력 메시지 {index}', message)
            continue
        role = str(message.get('role', 'unknown'))
        content = message.get('content')
        expanded = message_content(content)
        result += section(f'실제 LLM 입력 메시지 {index} / 역할', role)
        if isinstance(content, str):
            result += section('전송 content SHA-256 (마스킹 후) / 문자 수', {
                'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest(),
                'chars': len(content)})
        if isinstance(expanded, dict):
            # Every key comes from this physical request, including repair
            # messages. Never substitute a saved model_view or search inventory.
            for key, value in expanded.items():
                if key == 'view' and isinstance(value, dict) and value:
                    for field, item in value.items():
                        result += section('프롬프트에 들어간 정보 · view.' + str(field), item)
                else:
                    result += section('프롬프트에 들어간 정보 · ' + str(key), value)
        else:
            result += section('프롬프트에 들어간 내용', expanded)
        extras = {k: v for k, v in message.items() if k not in ('role', 'content')}
        if extras:
            result += section('메시지 추가 필드', extras)
    return result + settings


def response_body(response):
    if not isinstance(response, dict):
        return response
    if 'body_json' in response:
        return response['body_json']
    return response.get('body', response)


def response_sections(response):
    body = response_body(response)
    if not isinstance(body, dict):
        return section('LLM 수신 응답 전체 (완료·채택 여부는 후속 검증)', response)
    result = ''
    choices = body.get('choices')
    if isinstance(choices, list):
        for index, choice in enumerate(choices, 1):
            if not isinstance(choice, dict):
                result += section(f'LLM 응답 {index}', choice)
                continue
            result += section(f'LLM 응답 {index} / 완료 상태',
                              {k: v for k, v in choice.items() if k not in ('message', 'delta')})
            for name in ('message', 'delta'):
                message = choice.get(name)
                if isinstance(message, dict):
                    for key, value in message.items():
                        result += section('LLM 응답 · ' + key,
                                          message_content(value) if key == 'content' else value)
                elif message is not None:
                    result += section('LLM 응답 · ' + name, message)
    result += section('응답 메타데이터 / 오류 / 사용량',
                      {k: v for k, v in body.items() if k != 'choices' or not isinstance(choices, list)})
    if response is not body:
        result += section('전송 응답 receipt',
                          {k: v for k, v in response.items() if k not in ('body_json', 'body')})
    return result


def number(value):
    return value if type(value) in (int, float) and value >= 0 else None


def attempt_metrics(attempt):
    receipt = attempt.get('receipt') or {}
    receipt = receipt if isinstance(receipt, dict) else {}
    body = response_body(attempt.get('response'))
    usage = (body.get('usage') if isinstance(body, dict) else None) or receipt.get('usage') or {}
    usage = usage if isinstance(usage, dict) else {}
    seconds = number(receipt.get('seconds'))
    basis = '전송 receipt.seconds'
    if seconds is None:
        try:
            seconds = (datetime.fromisoformat(attempt['finished_at']) -
                       datetime.fromisoformat(attempt['started_at'])).total_seconds()
            if seconds < 0:
                seconds = None
        except (ValueError, TypeError, KeyError):
            seconds = None
        basis = '원장 started_at → finished_at (저장 경계 포함)'
    prompt = number(usage.get('prompt_tokens', attempt.get('input_tokens')))
    completion = number(usage.get('completion_tokens', attempt.get('output_tokens')))
    total = number(usage.get('total_tokens'))
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return {'seconds': seconds, 'time_basis': basis, 'prompt_tokens': prompt,
            'completion_tokens': completion, 'total_tokens': total}


def metric_sections(metrics):
    unknown = '미제공 / 미기록 (0으로 간주하지 않음)'
    result = {'응답 소요 시간(초)': metrics['seconds'] if metrics['seconds'] is not None else unknown,
              '시간 기준': metrics['time_basis'],
              '입력 토큰': metrics['prompt_tokens'] if metrics['prompt_tokens'] is not None else unknown,
              '출력 토큰': metrics['completion_tokens'] if metrics['completion_tokens'] is not None else unknown,
              '합계 토큰': metrics['total_tokens'] if metrics['total_tokens'] is not None else unknown}
    if metrics['seconds'] and metrics['completion_tokens'] is not None:
        result['평균 출력 토큰/초 (전체 호출 시간 기준; 생성 전용 속도 아님)'] = round(
            metrics['completion_tokens'] / metrics['seconds'], 3)
    return section('답변 속도 · 토큰 사용량', result)


class ProcessTrace:
    def __init__(self, path, request_id):
        self.path, self.request_id = path, request_id
        self.lock = threading.RLock()
        self.seen = set()
        self.attempts = {}
        self.errors = ErrorSections()
        self.failed = False
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(path, flags, 0o640)
        os.fchmod(fd, 0o640)
        self.stream = os.fdopen(fd, 'a', encoding='utf-8')
        self.block('요청 전체 과정 / 시작', {
            'request_id': request_id, 'format': 'readable-process-trace-v1',
            '읽는 방법': '단계별 누적 기록. | 로 시작하는 줄은 입력·응답 데이터입니다. '
                'JSON 문자열은 필드별로 펼쳐 표시합니다. 원본 바이트는 같은 이름의 JSON 보고서/SQL 원장에 보존됩니다.',
            '순서': '수집 순서로 추가하며 실제 발생 시각과 원장 seq를 표시합니다. 늦게 수집한 기록은 뒤에 보충됩니다.',
            '범위': '기록된 서비스 단계·모델 호출·도구 결과·검증·복구·상태 전체. 인증값은 마스킹합니다.'})

    def block(self, label, value, *, key=None, stamp=None, render=None):
        from .request_report import _scrub
        from . import observability as obs
        with self.lock:
            if self.failed or (key is not None and key in self.seen):
                return
            safe = _scrub(value)
            try:
                stamp = stamp or datetime.now(timezone.utc).isoformat(timespec='milliseconds')
                heading = str(label).replace('\n', '\\n').replace('\r', '\\r')
                safe, prefix, suffix = self.errors.prepare(safe)
                body = prefix + (render(safe) if render else section('기록 내용', safe)) + suffix
                self.stream.write('\n' + '=' * 88 + '\n' + heading + '\n발생 시각: ' +
                                  str(stamp) + '\n' + '-' * 88 + '\n' + body)
                self.stream.flush()
                if key is not None:
                    self.seen.add(key)
            except (OSError, UnicodeError) as exc:
                self.failed = True
                obs.event(obs.get_logger('request-report'), 'shared_process_trace.failed', level=40,
                          request_id=self.request_id, error_type=type(exc).__name__,
                          recovery='authoritative_journal_and_json_retained')

    def service_events(self, events):
        for event in events:
            if event.get('request_id') != self.request_id:
                continue
            key = 'service:' + hashlib.sha256(json.dumps(event, sort_keys=True,
                                                        default=str).encode()).hexdigest()
            self.block('서비스 지점 · ' + str(event.get('event')), event,
                       key=key, stamp=event.get('ts'))

    def attempt(self, data, kind, *, phase=None, stamp=None, run_id=''):
        ident = str(data.get('attempt_id'))
        def render(safe):
            metadata = {k: safe.get(k) for k in ('attempt_id', 'logical_call_id', 'attempt_no',
                'view_id', 'request_hash', 'response_hash', 'started_at', 'finished_at')}
            metadata.update(phase=phase, status=kind if kind != 'ATTEMPT_FINISHED' else safe.get('status'))
            from .legal_agent.readable_log import phase_label
            source_stage = phase
            request = safe.get('request') or {}
            metadata['요청 모델'] = request.get('model') if isinstance(request, dict) else None
            for message in request.get('messages', []) if isinstance(request, dict) else []:
                expanded = message_content(message.get('content')) if isinstance(message, dict) else None
                presented = expanded.get('view', expanded) if isinstance(expanded, dict) else {}
                if isinstance(presented, dict) and presented.get('source_stage'):
                    source_stage = presented['source_stage']
            metadata.update(source_stage=source_stage, 단계=phase_label(source_stage))
            result = section('호출 식별자 / 단계 / 상태', metadata)
            if kind == 'ATTEMPT_SENT':
                result += '\n실제 전송 요청에 포함된 정보입니다. 서버 수신·답변 채택은 별도 상태입니다.\n'
                result += request_sections(safe.get('request'))
            elif kind == 'ATTEMPT_RESERVED':
                result += '\n호출 예약: 아직 전송 완료로 보지 않습니다.\n'
            else:
                metrics = attempt_metrics(safe)
                self.attempts[(run_id, ident)] = metrics
                result += metric_sections(metrics)
                result += response_sections(safe.get('response'))
                result += section('검증 전 수신 상태 / receipt', safe.get('receipt'))
            return result
        self.block('LLM · ' + kind + ' · ' + ident, data,
                   key=f'attempt:{run_id}:{ident}:{kind}', stamp=stamp, render=render)

    def journal_event(self, event, records, *, attempt=None, phase=None, run_id=''):
        seq, kind = event.get('seq'), event.get('kind')
        stamp = event.get('created_at')
        self.block(f'AGENT / 원장 #{seq} · {kind}', event,
                   key=f'event:{run_id}:{seq}', stamp=stamp)
        for index, created in enumerate(records):
            table, record = created['table'], created['record']
            if table == 'model_attempt':
                continue  # Render physical requests at SENT, results at FINISHED.
            label = ('찾은 정보 / 도구 실행 결과 (프롬프트 포함 여부는 각 LLM 입력에서 확인)'
                     if table in ('observation', 'evidence_unit', 'evidence_span')
                     else '단계 저장 기록')
            self.block(label + ' · ' + table, record,
                       key=f'record:{run_id}:{seq}:{index}:{table}', stamp=stamp)
        if attempt is not None:
            if kind == 'ATTEMPT_FINISHED' and f'attempt:{run_id}:{attempt.get("attempt_id")}:ATTEMPT_SENT' not in self.seen:
                self.block('전송 시점 미기록 · 이 호출에 저장된 요청', attempt.get('request'),
                           key=f'orphan-request:{run_id}:{attempt.get("attempt_id")}',
                           stamp=stamp, render=request_sections)
            self.attempt(attempt, kind, phase=phase, stamp=stamp, run_id=run_id)

    def poll(self, db, events, tables, run_id):
        """Read every recorded event; no UI allowlist, sample, or source cutoff."""
        columns = {table: {r[1] for r in db.execute('PRAGMA table_info("' + table.replace('"', '""') + '")')}
                   for table in sorted(tables)}
        records_by_seq = {}
        for table, names in columns.items():
            if table == 'event' or 'created_seq' not in names:
                continue
            quoted = '"' + table.replace('"', '""') + '"'
            for raw in db.execute(f'SELECT * FROM {quoted} WHERE created_seq>=? AND created_seq<=?',
                                  (events[0]['seq'], events[-1]['seq'])):
                record = decoded(raw)
                records_by_seq.setdefault(record['created_seq'], []).append({'table': table, 'record': record})
        for raw in events:
            event = decoded(raw)
            records = records_by_seq.get(event['seq'], [])
            attempt = phase = None
            if event['kind'] in ('ATTEMPT_RESERVED', 'ATTEMPT_SENT', 'ATTEMPT_FINISHED') and 'model_attempt' in tables:
                ident = (event.get('payload') or {}).get('attempt_id')
                row = db.execute('SELECT * FROM model_attempt WHERE attempt_id=?', (ident,)).fetchone()
                if row:
                    attempt = decoded(row)
                    if 'model_view' in tables:
                        view = db.execute('SELECT phase FROM model_view WHERE view_id=?', (attempt.get('view_id'),)).fetchone()
                        phase = view[0] if view else None
            self.journal_event(event, records, attempt=attempt, phase=phase, run_id=run_id)

    def finish(self, report):
        self.block('요청 입력 전체', report.get('request'), key='request', stamp=report.get('requested_at'))
        self.service_events(report.get('service_events', []))
        journal = report.get('journal') or {}
        run_id = report.get('run_id') or ''
        if journal.get('kind') == 'ad_mode':
            for call in journal.get('calls', []):
                data = {'attempt_id': 'AD:' + str(call['sequence']), 'attempt_no': call['sequence'],
                        'request': (call.get('input') or {}).get('request'),
                        'response': call.get('model_output'), 'receipt': call.get('receipt'),
                        'status': '수신 기록; AD 검증 결과 참조'}
                self.attempt(data, 'ATTEMPT_SENT', phase='AD', run_id=run_id)
                self.attempt(data, 'ATTEMPT_FINISHED', phase='AD', run_id=run_id)
                self.block('AD 해석·검증 결과', call.get('plan'), key='ad-plan:' + data['attempt_id'])
            self.block('AD 작업·변경·오류 상태 전체', {k: v for k, v in journal.items() if k != 'calls'}, key='ad-state')
        else:
            journals = [(run_id, journal)] + [(child['run_id'], child['journal'])
                                             for child in journal.get('children', [])]
            for journal_id, current in journals:
                attempts = {r['record'].get('attempt_id'): r['record']
                            for row in current.get('timeline', []) for r in row.get('created_records', [])
                            if r['table'] == 'model_attempt'}
                for row in current.get('timeline', []):
                    event = row['event']
                    attempt = attempts.get((event.get('payload') or {}).get('attempt_id'))
                    self.journal_event(event, row.get('created_records', []),
                        attempt=attempt if event.get('kind') in ('ATTEMPT_RESERVED', 'ATTEMPT_SENT', 'ATTEMPT_FINISHED') else None,
                        run_id=journal_id)
            self.block('최종 원장 상태 / 코드·데이터 binding / 예산', journal.get('state'), key='state')
        values = list(self.attempts.values())
        summary = {'종료 기록이 있는 물리 호출 수': len(values)}
        for name in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'seconds'):
            known = [v[name] for v in values if v[name] is not None]
            summary[name] = {'확인된 값 합계': round(sum(known), 6), '미기록 호출 수': len(values) - len(known)}
        summary['시간 주의'] = '호출 시간 합계는 병렬 호출 시 요청 전체 경과 시간과 다릅니다.'
        self.block('누적 모델 사용량 (실패·재시도 포함)', summary, key='usage')
        self.block('최종 서비스 응답 / 성공·실패·부분 상태', report.get('result'), key='final')
        self.block('전체 과정 기록 종료', {'journal_status': journal.get('status'),
            'delivery_confirmed': False, '기준': '서비스 반환 결과. 클라이언트 수신 완료와 구분합니다.'}, key='end')

    def close(self):
        with self.lock:
            self.stream.close()
