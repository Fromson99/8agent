"""Notebook orchestration only; reuse sealed R6 authentication and migration engines."""
import json
import shutil
import time
from pathlib import Path
import _legal19_core as core
import _legal19_io as io
import _legal19_migration as migration
import _legal19_assets as assets
import _legal19_publish as publisher


def metadata(path):
    path = Path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise io.DPError('STATE_SIZE: 상태 기록 크기를 확인하세요: ' + str(path))
    return json.loads(path.read_text())


def resources(log_dir):
    folder = Path(log_dir)
    folder.mkdir(parents=True, exist_ok=True)
    available = None
    if Path('/proc/meminfo').exists():
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                available = int(line.split()[1]) * 1024
    free = shutil.disk_usage(folder).free
    if available is not None and available < 512 * 1024 * 1024:
        raise io.DPError('RESOURCE_RAM: 가용 RAM 512MiB 미만. 다른 무거운 작업 종료 후 같은 셀을 실행하세요.')
    if free < 256 * 1024 * 1024:
        raise io.DPError('RESOURCE_DISK: 기록 폴더 여유 공간 256MiB 미만. 기존 이관 기록은 보존하세요.')
    return {'available_ram_mib': None if available is None else available // 1024**2,
            'free_log_disk_mib': free // 1024**2}


def connect(desk, expected_user):
    result = desk.run('CONNECT', 'Oracle 연결', desk.connect, connection=False)
    if desk.latest.get('CONNECT', {}).get('status') != 'PASS':
        raise io.DPError('CONNECT_FAILED: 바로 위 오류를 확인하고 인증 또는 설정 수정 후 이 셀을 다시 실행하세요.')
    rows = result['connection']
    if len(rows) != 1 or rows[0].get('LOGIN_USER') != expected_user:
        desk._binding = None
        raise io.DPError('LOGIN_USER: 예상한 ' + expected_user + ' 계정이 아닙니다. 연결 설정을 확인하세요.')
    if desk.recovery_required:
        raise io.DPError('R6_RECOVERY: 기존 쓰기 보류 기록이 있습니다. 이전 기록을 확인하며 강제로 초기화하지 않습니다.')
    print('연결 완료:', expected_user, '/ 대상 테이블 소유자 SIDDA')
    print('기록 폴더:', str(Path(desk.settings['log_dir']).resolve()))
    return result


def context(desk, source):
    desk.require_connection()
    if desk.recovery_required:
        raise io.DPError('R6_RECOVERY: 기존 쓰기 보류 기록 확인이 필요합니다.')
    resources(desk.settings['log_dir'])
    binding, manifest = migration.source_binding(source)
    binding['target_binding'] = desk.binding()
    directory = Path(desk.settings['log_dir']) / 'legal_full_migration'
    # Do not create a new budget silently after changing credentials/config/source signatures.
    for old in directory.glob('*/state.json'):
        previous = metadata(old).get('binding', {})
        if (previous.get('source_path') == binding['source_path'] and
                previous.get('dataset_version') == binding['dataset_version'] and previous != binding):
            raise io.DPError('PRIOR_BINDING: 같은 원문의 이전 이관 기록과 설정이 다릅니다. '
                             '이전 R6의 인증·PREFIX·TIMEOUT·LOG_DIR 및 원본을 확인하세요: ' + str(old))
    receipt = directory / io.digest(binding)[:24] / 'state.json'
    return binding, manifest, receipt


def source_stage(desk, source, action, seconds):
    if action not in ('check', 'run', 'verify'):
        raise io.DPError('ACTION: 지원하지 않는 단계입니다.')
    binding, _, receipt = context(desk, source)
    if action == 'verify':
        if not receipt.exists() or set(metadata(receipt).get('tables', {})) != set(io.TABLES):
            raise io.DPError('TRANSFER_FIRST: 먼저 05 원문 이관을 완료하세요.')
    if action == 'check':
        sql = io.SQL(desk.require_connection().client,
                     journal=receipt.parent / 'preflight.jsonl', binding=desk.binding(), seconds=60)
        for table, columns in [(assets.PART_TABLE, 'ASSET_SHA256,PART_NO,RAW_BYTES,PART_SHA256,DATA_B64'),
                               (assets.RELEASE_TABLE, 'RELEASE_ID,DATASET_VERSION,RELEASE_JSON,CREATED_AT')]:
            sql.query(f'SELECT {columns} FROM {table} WHERE 1=0')
    result = migration.from_notebook(desk, source=source, action=action, seconds=seconds)
    if result['status'] == 'PAUSED':
        mode = '처음부터 대조합니다' if action == 'verify' else '저장된 위치부터 이어갑니다'
        raise io.DPError('PAUSED: 이 셀에서 멈췄습니다. 같은 셀을 다시 실행하면 ' + mode +
                         '. 기록=' + result['receipt'])
    expected = {'check': 'CHECKED_NO_WRITES', 'run': 'SOURCE_COMPLETE', 'verify': 'VERIFIED'}[action]
    if result['status'] != expected:
        raise io.DPError('STATE: 예상과 다른 완료 상태입니다.')
    print('완료 상태:', result['status'])
    return result


def publish(desk, source, seconds):
    _, _, receipt = context(desk, source)
    if not receipt.exists() or metadata(receipt).get('status') != 'VERIFIED':
        raise io.DPError('VERIFY_FIRST: 먼저 06 전체 대조를 VERIFIED까지 완료하세요.')
    result = publisher.from_notebook(desk, str(receipt), source=source, seconds=seconds)
    if result['status'] == 'PAUSED':
        raise io.DPError('PAUSED: 07 셀을 다시 실행하면 검증된 자산 분할 이후부터 이어갑니다. 기록=' + result['receipt'])
    if result['status'] != 'COMPLETE':
        raise io.DPError('STATE: 자산 게시가 완료되지 않았습니다.')
    # Recover the final result after a fresh kernel without requiring an in-memory previous cell value.
    io.atomic_json(receipt.parent / 'notebook_publication.json', {
        'target_binding': desk.binding(), **result})
    return result


def summary(desk, source):
    binding, _, receipt = context(desk, source)
    if not receipt.exists() or metadata(receipt).get('status') != 'VERIFIED':
        raise io.DPError('VERIFY_FIRST: 전체 대조 결과가 필요합니다.')
    marker = receipt.parent / 'notebook_publication.json'
    if not marker.exists():
        raise io.DPError('PUBLISH_FIRST: 07 자산 게시를 실행하세요.')
    result = metadata(marker)
    if result.get('target_binding') != desk.binding():
        raise io.DPError('TARGET_BINDING: 자산 게시 연결이 다릅니다.')
    sql = io.SQL(desk.require_connection().client, journal=receipt.parent / 'summary.jsonl',
                 binding=desk.binding(), seconds=120)
    release = assets.get_release(sql, result['release_id'])
    state = metadata(receipt)
    if release['dataset_version'] != binding['dataset_version']:
        raise io.DPError('RELEASE_BINDING: 완료 버전의 원문이 다릅니다.')
    for kind, recorded in release['source_rows'].items():
        if recorded != {k: state['tables'][kind][k] for k in ('rows', 'chain')}:
            raise io.DPError('RELEASE_ROWS: 완료 버전의 원문 검증 기록이 다릅니다.')
    out = {'status': 'TRANSFER_AND_ASSETS_COMPLETE', 'dataset_version': binding['dataset_version'],
           'source_counts': state['counts'], 'asset_files': len(release['assets']),
           'DP_RELEASE_ID': result['release_id'], 'transfer_receipt': str(receipt),
           'publish_receipt': result['receipt'], 'serving_switched': False}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print('데이터 이관·자산 게시 확인 완료. 실제 Oracle 기반 RAG 서빙 전환·워크플로우 시험은 별도입니다.')
    return out


def safe(desk, callback):
    """The engines own checkpoint/retry; this wrapper only masks notebook error output."""
    try:
        return callback()
    except Exception as exc:
        message = str(exc) if isinstance(exc, (io.DPError, core.CheckError)) else type(exc).__name__
        for secret in getattr(desk, '_auth', ()):
            if secret:
                message = message.replace(secret, '[MASKED]')
        diagnostic = getattr(getattr(getattr(desk, 'check', None), 'client', None), 'diagnostic', {})
        print('중단:', message)
        if diagnostic:
            print('연결 진단:', json.dumps(diagnostic, ensure_ascii=False))
        raise RuntimeError(message) from None
