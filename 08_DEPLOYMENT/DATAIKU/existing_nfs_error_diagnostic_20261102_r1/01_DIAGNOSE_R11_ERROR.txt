"""Same-kernel R11 error/receipt diagnosis; no API, DB, write or loader import."""
import json
import math
from pathlib import Path
import re
import sys
import time

DIAG_JOB_DIR = ''  # 보통 비워둡니다. 커널에 남아 있는 R11 경로를 먼저 확인합니다.
CODE = re.compile(r'(?<![A-Z0-9_])(?:ORA|PLS)-[0-9]{5}(?![0-9])')
TEXT_LIMIT = 1024 * 1024
JSON_LIMIT = 16 * 1024 * 1024


def error_codes(exc):
    try:
        text = str(exc)
    except Exception:
        return [], True
    truncated = len(text) > TEXT_LIMIT
    if truncated:
        text = text[:TEXT_LIMIT//2] + '\n' + text[-TEXT_LIMIT//2:]
    found = []
    for match in CODE.finditer(text):
        code = match.group()
        if code not in found:
            found.append(code)
        if len(found) >= 16:
            return found, True
    return found, truncated


def error_chain(exc):
    pending = [exc] if isinstance(exc, BaseException) else []
    seen = set()
    result = []
    while pending and len(result) < 8:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current)); result.append(current)
        # from None hides display but normally retains __context__ in memory.
        for child in (current.__cause__, current.__context__):
            if isinstance(child, BaseException):
                pending.append(child)
    return result


def paths_from_chain(chain):
    result = []
    for exc in chain:
        tb = exc.__traceback__
        for _ in range(64):
            if tb is None:
                break
            frame = tb.tb_frame
            if Path(frame.f_code.co_filename).name in (
                'existing_client.py', 'oracle_full_package.py',
                'oracle_deferred_import.py', 'oracle_dp_io.py'):
                local = frame.f_locals
                for key in ('logs', 'attempt', 'directory', 'local', 'folder', 'receipt'):
                    value = local.get(key)
                    if isinstance(value, (str, Path)):
                        result.append(Path(value))
            tb = tb.tb_next
    return result


def find_job(chain, explicit=''):
    candidates = [Path(explicit)] if explicit else paths_from_chain(chain)
    found = {}
    for path in candidates[:128]:
        if path.name == 'full-state.json':
            path = path.parent
        for folder in (path, path/'oracle-import-r2'):
            try:
                if (folder/'full-state.json').is_file():
                    found[str(folder.resolve())] = folder
            except OSError:
                pass
    return next(iter(found.values())) if len(found) == 1 else None


def read_json(path, limit=JSON_LIMIT):
    try:
        with path.open('rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            return {}, 'SIZE_LIMIT'
        value = json.loads(raw)
        return (value, '') if isinstance(value, dict) else ({}, 'FORMAT')
    except (OSError, ValueError, UnicodeError) as exc:
        return {}, type(exc).__name__


def tail_event(path):
    try:
        with path.open('rb') as stream:
            stream.seek(0, 2); size = stream.tell()
            stream.seek(max(0, size-128*1024)); raw = stream.read(128*1024)
        if size > 128*1024:
            raw = raw.partition(b'\n')[2]
        for line in reversed(raw.splitlines()):
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    return value
            except (ValueError, UnicodeError):
                pass
    except OSError:
        pass
    return {}


def token(value):
    return value if isinstance(value, str) and re.fullmatch('[A-Za-z0-9_.:-]{1,80}', value) else 'UNKNOWN'


def count(value):
    return str(value) if type(value) is int and value >= 0 else '?'


def report(exc, explicit='', now=None):
    chain = error_chain(exc)
    lines = ['[R11 오류 진단] DB/API 호출0 · 파일변경0 · 재개/임베딩0']
    codes = []
    for i, current in enumerate(chain, 1):
        found, cut = error_codes(current)
        codes.extend(c for c in found if c not in codes)
        lines.append('E'+str(i)+' '+token(type(current).__name__)+': '+(', '.join(found) or 'ORA/PLS 코드 없음')+(' [텍스트 검사 한도 도달]' if cut else ''))
    if not chain:
        lines.append('E0 원래 예외 없음: 다른 셀 오류/커널 재시작 시 메모리 원인 확인 불가')
    cause = [c for c in codes if c not in ('ORA-12801', 'ORA-06512')]
    lines.append('원인 확인 후보: '+(', '.join(cause) or '상세 코드 미확보 — 원인 확정 불가'))
    job = find_job(chain, explicit)
    if job is None:
        lines.append('기존 작업 경로 미확인/복수: 기록이 없거나 적재가 0행이라는 뜻은 아님')
    else:
        state, err = read_json(job/'full-state.json')
        latest, _ = read_json(job/'progress-latest.json', 128*1024)
        event = tail_event(job/'deferred_load.jsonl')
        deferred = state.get('deferred', {})
        if not isinstance(deferred, dict): deferred = {}
        lines.append('저장 상태: '+token(state.get('status'))+(' / 읽기오류='+err if err else ''))
        lines.append('적재 완료 기록: '+str(deferred.get('load_finished') is True))
        lines.append('마지막 확정 커서: '+count(deferred.get('loaded_query_batches'))+' (1~20행 단위, 행수 아님)')
        lines.append('이번 실행 성공응답: '+count(latest.get('write_rows_this_run'))+'행 / '+count(latest.get('write_requests_this_run'))+'요청')
        lines.append('마지막 단계: '+token(latest.get('phase')))
        lines.append('마지막 요청: '+token(event.get('status'))+' / 번호 '+count(event.get('call')))
        ec, _ = error_codes(RuntimeError(str(event.get('error', ''))))
        lines.append('요청 기록 코드: '+(', '.join(ec) or '없음'))
        end = state.get('deadline'); now = time.time() if now is None else now
        if type(end) in (int, float) and math.isfinite(end):
            lines.append('기존 기한 잔여: '+str(round((end-now)/3600, 1))+'시간 (기한 초기화 안 함)')
    lines.append('중단 상태의 완료시간은 계산하지 않습니다. 마지막 실패 묶음의 DB 반영 여부는 미확인입니다.')
    lines.append('이 화면만 캡처하세요. R11/R12 재실행·커널 재시작·로그 삭제는 아직 하지 마세요.')
    return lines


def main():
    # Capture BEFORE any SDK import or new failing notebook operation.
    exc = getattr(sys, 'last_exc', None) or getattr(sys, 'last_value', None)
    try:
        lines = report(exc, DIAG_JOB_DIR)
    except Exception as failure:
        lines = ['[R11 오류 진단] 진단만 실패: '+token(type(failure).__name__),
                 'DB/API 호출·파일변경·적재 재개는 하지 않았습니다. 기존 오류 화면을 보존하세요.']
    for line in lines[:24]:
        print(line)


if __name__ == '__main__':
    main()
