"""Read existing R11 receipts only; no loader, SDK, database or model calls."""
import json
import os
from pathlib import Path
import re
import tempfile

# 보통 빈 값 유지. 사진에서 확인한 기존 작업 경로만 읽습니다.
# 경로가 달라졌다면 기존 DP_MIGRATION_RECEIPT의 source 위 작업 폴더를 지정합니다.
DIAG_JOB_DIR = ''
DEFAULT_JOB = Path(tempfile.gettempdir()) / 'legal-existing-nfs-20261029-r1' / 'financial-risk-success-20261005-schema-r2' / 'oracle-import-r2'


def read_json(path, limit=2 * 1024 * 1024):
    try:
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        current = path.stat()
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if signature(before) != signature(after) or signature(after) != signature(current):
            return {}, 'CHANGED_DURING_READ'
        if len(raw) > limit:
            return {}, 'SIZE_LIMIT'
        value = json.loads(raw)
        return (value, '') if isinstance(value, dict) else ({}, 'FORMAT_ERROR')
    except (OSError, ValueError, UnicodeError) as exc:
        return {}, type(exc).__name__


def obj(value):
    return value if isinstance(value, dict) else {}


def token(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}', value) else 'UNKNOWN'


def count(value):
    return f'{value:,}' if type(value) is int and value >= 0 else '?'


def stage_status(stages, key):
    value = obj(stages.get(key))
    return token(value.get('status')) if value else 'NO_RECORD'


def report(job):
    job = Path(job).resolve()
    lines = ['[R4 테이블별 적재 기록] DB/API 0회 · 파일변경 0 · 최대 18줄']
    full, error = read_json(job / 'full-state.json', 16 * 1024 * 1024)
    if error:
        return lines + ['기존 작업 기록 읽기 실패: ' + error,
                        'DIAG_JOB_DIR 경로를 확인하세요. 기록 미확인은 적재 0행이 아닙니다.']
    stages = obj(full.get('stages'))
    deferred = obj(full.get('deferred'))
    lines.append('전체 저장 상태: ' + token(full.get('status')))
    source_load = obj(stages.get('source_load'))
    source = {}
    receipt = source_load.get('receipt')
    source_error = 'NO_RECEIPT'
    if isinstance(receipt, str) and receipt:
        path = Path(receipt).resolve()
        source_root = (job / 'source').resolve()
        if source_root in path.parents and path.name == 'state.json':
            source, source_error = read_json(path)
            version = source_load.get('dataset_version')
            if not version or obj(source.get('binding')).get('dataset_version') != version:
                source = {}
                source_error = source_error or 'VERSION_MISMATCH'
        else:
            source_error = 'RECEIPT_OUTSIDE_JOB'
    lines.append('원문3표 단계: ' + stage_status(stages, 'source_load') +
                 ' / 별도 전수검증 단계: ' + stage_status(stages, 'verify'))
    if source_error:
        lines.append('원문 상세 기록 미확인: ' + source_error)
    counts = obj(source_load.get('counts'))
    for table, kind in [('LGL_DOC_VER_S', 'document'),
                        ('LGL_DOC_UNIT_S', 'source_unit'),
                        ('LGL_DOC_BLK_S', 'block_payload')]:
        saved = obj(obj(source.get('tables')).get(kind)).get('rows')
        lines.append(table + ': 성공응답 누적 ' + count(saved) + ' / 원본 예정 ' + count(counts.get(kind)))
    parts = deferred.get('loaded_parts')
    if isinstance(parts, dict) and parts and all(type(n) is int and n >= 0 for n in parts.values()):
        lines.append('LGL_FILE_PART_S: 파일조각 성공응답 커서 합 ' + count(sum(parts.values())) + ' (완료 판정 아님)')
    else:
        lines.append('LGL_FILE_PART_S: 파일조각 기록 미확인 (0행 판정 아님)')
    done = deferred.get('load_finished')
    finished = 'YES' if done is True else 'NO' if done is False else 'NO_RECORD'
    lines.append('LGL_SRCH_ROW_S: 마지막 ACK 커서 ' + count(deferred.get('loaded_query_batches')) +
                 ' / 전체 적재 완료 기록 ' + finished)
    lines.append('  ACK 커서는 최대20행 묶음 수이며 실제 행 수가 아닙니다.')
    lines.append('LGL_SRC_PBLS_S: 검증 후 게시 단계 ' + stage_status(stages, 'assets'))
    lines.append('LGL_SRCH_PBLS_S: 검증 후 게시 단계 ' + stage_status(stages, 'query'))
    lines.append('LGL_SRCH_CHNL_S: 이 적재 작업은 활성 채널을 전환하지 않음')
    lines.append('VCTR 2표 / Gold 온톨로지: R11 적재 대상 아님 · 별도 작업 확인 필요')
    lines.append('SOURCE_STAGED=적재 응답/당시 행수 확인, 전수 내용검증 완료와 다름.')
    lines.append('NO_RECORD/빈값=완료 근거 없음. 실패나 DB 빈 테이블로 단정하지 않습니다.')
    lines.append('이 결과는 저장 기록입니다. 지금 새 INSERT가 가능한지와 Gold 구조 적합성은 미검증입니다.')
    return lines


def main():
    try:
        lines = report(DIAG_JOB_DIR or DEFAULT_JOB)
    except Exception as exc:
        lines = ['[R4] 진단 실패: ' + token(type(exc).__name__),
                 'DB/API 호출·파일변경·적재 재개는 하지 않았습니다.']
    for line in lines[:18]:
        print(line)


if __name__ == '__main__':
    main()
