"""Bound two-part synthetic input and test-only Oracle names; no production cutover."""
import hashlib
import io
import json
from pathlib import Path
from oneclick_config import ROOT, target, validate

PREFIX = 'TST_B003_LGL_'
ARCHIVE = 'gold-dev-sample.zip'


def check(params, project):
    validate(params)
    if not isinstance(project, str) or not project:
        raise ValueError('CURRENT_DATAIKU_PROJECT_REQUIRED')
    if params['TARGET_MODE'] != 'GOLD' or params['TABLE_PREFIX'] != PREFIX or params.get('TABLE_NAMES'):
        raise ValueError('TEST_TABLE_NAMES_REQUIRED: '+PREFIX+' 전용입니다.')
    if params['EXPECTED_ARCHIVE'] != ARCHIVE or params['EXPECTED_PARTS'] != 2:
        raise ValueError('TWO_PART_SAMPLE_REQUIRED')
    if not params.get('DEVELOPMENT_ONLY'):
        raise ValueError('DEVELOPMENT_ONLY_REQUIRED')
    return target(params)


def sample_files():
    manifest = json.loads((ROOT/'sample/manifest.json').read_text())
    result = {}
    for name, expected in manifest['files'].items():
        raw = (ROOT/'sample'/name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('BUNDLED_SAMPLE_HASH:'+name)
        result[name] = raw
    return result


def verify_sample(folder, allow_missing=False):
    expected = sample_files()
    actual = {p.lstrip('/') for p in folder.list_paths_in_partition()}
    if actual - set(expected):
        raise ValueError('TEST_INPUT_EXTRA_FILES: 예시 전용 폴더에 다른 자료가 있습니다.')
    if not allow_missing and actual != set(expected):
        raise ValueError('TEST_INPUT_MISSING_PART_OR_CHECKSUM')
    for name in actual:
        with folder.get_download_stream(name) as stream:
            raw = stream.read(len(expected[name])+1)
        if raw != expected[name]:
            raise ValueError('TEST_INPUT_HASH:'+name)
    return expected, actual


def seed_sample(folder):
    expected, present = verify_sample(folder, allow_missing=True)
    for name, raw in expected.items():
        if name not in present:
            folder.upload_stream(name, io.BytesIO(raw))
    verify_sample(folder)


def probe(folder, label):
    """Write/read/list only our probe; unknown write result is never auto-retried."""
    import uuid
    path = '_connection_checks/'+uuid.uuid4().hex+'.txt'
    raw = ('Gold development test '+label).encode()
    try:
        folder.list_paths_in_partition()
        folder.upload_stream(path, io.BytesIO(raw))
        with folder.get_download_stream(path) as stream:
            if stream.read(len(raw)+1) != raw:
                raise ValueError('READBACK_MISMATCH')
    except Exception as exc:
        raise RuntimeError('STORAGE_CHECK_FAILED:'+label+
            ' — 연결의 실제 버킷·namespace·권한을 확인하세요. Oracle 적재 전 중단했습니다.') from exc


def location(folder, connection):
    info = folder.get_info(sensitive_info=False)
    if info['type'] == 'S3':
        access = info['accessInfo']
        bucket, root = access.get('bucket'), access.get('root')
        if not bucket or not root:
            raise ValueError('EFFECTIVE_S3_LOCATION_REQUIRED')
        return (connection, bucket, root.rstrip('/')+'/')
    if info['type'] == 'Filesystem' and info.get('path'):
        return (connection, '', str(Path(info['path']).resolve()).rstrip('/')+'/')
    raise ValueError('SUPPORTED_STORAGE_LOCATION_REQUIRED')


def check_disjoint(locations):
    for i, (label, loc) in enumerate(locations):
        for other, ref in locations[:i]:
            if loc[:2] == ref[:2] and (loc[2].startswith(ref[2]) or ref[2].startswith(loc[2])):
                raise ValueError('FOLDER_LOCATION_OVERLAP:'+other+':'+label)
