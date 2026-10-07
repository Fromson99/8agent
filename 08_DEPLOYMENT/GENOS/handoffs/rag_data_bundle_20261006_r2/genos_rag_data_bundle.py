#!/usr/bin/env python3
"""Offline GENOS RAG data ZIP, retaining absolute NFS paths and source bytes.

Python standard library only. No application import or database writes.
The source/destination prefixes exist for offline mounted snapshots and tests;
logical paths in the manifest and payload are never rewritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

BASE = Path('/nfs-root/diamo')
GENERATION = BASE / '8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
RUNTIME = BASE / '8-agent/runtime'
FORMAT = 'genos-rag-data-path-preserving-v1'
SETTINGS = ('GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_RUNTIME_DIR',
            'GENOS_STATE_DIR', 'GENOS_SHARED_LOG_DIR')
CHUNK = 8 * 1024 * 1024


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def plain(path):
    """Check existing ancestors before touching a path, including broken links."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('심볼릭 링크 경로는 지원하지 않습니다: ' + str(part))
    return path


def logical(value, base=BASE):
    path = PurePosixPath(str(value))
    if not path.is_absolute() or '..' in path.parts or '\\' in str(path):
        raise ValueError('정규 절대경로가 필요합니다: ' + str(value))
    path = Path(str(path))
    if not path.is_relative_to(base) or path == base:
        raise ValueError('데이터는 /nfs-root/diamo 아래여야 합니다: ' + str(path))
    return path


def physical(prefix, path):
    return plain(prefix / path.relative_to('/'))


class Log:
    def __init__(self, path):
        self.stream = path.open('x', encoding='utf-8')

    def __call__(self, text):
        line = datetime.now(timezone.utc).isoformat() + ' ' + text
        print(line, flush=True)
        self.stream.write(line + '\n')
        self.stream.flush()


def configuration(code_root):
    result = {}
    env_file = code_root / '.env'
    if env_file.is_file():
        plain(env_file)
        # Never evaluate/source a shell file or retain unrelated credentials.
        for line in env_file.read_text(encoding='utf-8').splitlines():
            key, sep, raw = line.strip().removeprefix('export ').partition('=')
            key = key.strip()
            if sep and key in SETTINGS and key not in os.environ:
                values = shlex.split(raw, comments=True)
                if len(values) > 1 or (values and ('$' in values[0] or '`' in values[0])):
                    raise ValueError('.env 경로는 확정된 리터럴이어야 합니다: ' + key)
                result[key] = values[0] if values else ''
    result.update({key: os.environ[key] for key in SETTINGS if key in os.environ})
    return result


def selected(a, settings):
    prefix = plain(a.source_prefix)
    selected_by = '--generation' if a.generation else 'GENOS_GENERATION'
    generation = a.generation or settings.get('GENOS_GENERATION', '').strip()
    pointer = None
    if not generation and settings.get('GENOS_DATA_ROOT', '').strip():
        data_root = logical(settings['GENOS_DATA_ROOT'])
        pointer = data_root / 'generations/CURRENT.json'
        value = json.loads(physical(prefix, pointer).read_text(encoding='utf-8'))
        if value.get('schema_version') != 'genos-current-generation-v1':
            raise ValueError('CURRENT 형식 불일치')
        generation = logical(value['path'])
        if not generation.is_relative_to(data_root):
            raise ValueError('CURRENT 경로가 GENOS_DATA_ROOT 밖입니다')
        if sha(physical(prefix, generation / 'manifest.json')) != value['manifest_sha256']:
            raise ValueError('CURRENT manifest 해시 불일치')
        selected_by = 'GENOS_DATA_ROOT/CURRENT'
    if not generation:
        generation = GENERATION
        selected_by = 'documented-field-path-20261006 (not field verified)'
    generation = logical(generation)
    if generation.name != 'generation':
        raise ValueError('generation 폴더를 지정하세요')
    manifest = json.loads(physical(prefix, generation / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') not in ('term-source-generation-v1', 'term-source-generation-v2'):
        raise ValueError('서빙 generation manifest 형식 불일치')
    runtime = logical(a.runtime or settings.get('GENOS_RUNTIME_DIR', '').strip() or RUNTIME)
    state = a.state or settings.get('GENOS_STATE_DIR', '').strip()
    roots = [{'path': str(generation.parent), 'reason': 'selected generation + sibling receipts/audits'},
             {'path': str(runtime), 'reason': 'case-memory, journals, artifacts, wikis, feedback, AD state'}]
    if state:
        state = logical(state)
        roots.append({'path': str(state / 'case-memory'), 'reason': 'separate GENOS_STATE_DIR authority'})
    if pointer:
        roots.append({'path': str(pointer), 'reason': 'selected immutable CURRENT bytes'})
    if a.include_request_logs:
        logs = logical(settings.get('GENOS_SHARED_LOG_DIR', '').strip() or BASE / '8-agent/rag-request-reports')
        roots.append({'path': str(logs), 'reason': 'optional request log history'})
    roots += [{'path': str(logical(p)), 'reason': 'explicit additional RAG dependency'} for p in a.extra_path]
    for entry in roots:
        path = physical(prefix, Path(entry['path']))
        if not path.exists():
            raise ValueError('선택한 필수 데이터 경로가 없습니다: ' + entry['path'])
    memory = (Path(state) if state else runtime) / 'case-memory'
    shortcut_pointer = memory / 'SHORTCUT_CURRENT.json'
    db = memory / 'cases-v4.sqlite'
    if physical(prefix, shortcut_pointer).is_file():
        value = json.loads(physical(prefix, shortcut_pointer).read_text(encoding='utf-8'))
        if value.get('schema_version') != 'shortcut-store-pointer-v1':
            raise ValueError('SHORTCUT_CURRENT 형식 불일치')
        receipt_hash = hashlib.sha256(json.dumps(value['receipt'], ensure_ascii=False,
                                   sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if receipt_hash != value['receipt_hash']:
            raise ValueError('SHORTCUT_CURRENT receipt hash 불일치')
        raw = PurePosixPath(str(value['path']))
        if '..' in raw.parts:
            raise ValueError('SHORTCUT_CURRENT traversal 경로')
        db = logical(memory / str(raw))
        if not db.is_relative_to(memory) or db.name != 'cases-v4.sqlite' or not physical(prefix, db).is_file():
            raise ValueError('SHORTCUT_CURRENT 저장소 경로 불일치')
    # No DB yet is valid for a never-used runtime, but is explicitly recorded.
    return {'schema_version': FORMAT, 'absolute_path_base': str(BASE), 'selection': selected_by,
            'generation': str(generation), 'generation_id': manifest.get('generation_id'),
            'generation_manifest_sha256': sha(physical(prefix, generation / 'manifest.json')),
            'runtime': str(runtime), 'state': str(state) if state else None,
            'shortcut_database': str(db), 'shortcut_database_exists': physical(prefix, db).is_file(),
            'roots': roots, 'path_settings': settings,
            'excluded': ['code, .env, Python dependencies, internal model services',
                         'unselected generations and authoring RAW/STRUCTURE',
                         'request reports unless --include-request-logs',
                         'unselected upload/input roots and legacy file wiki; use --extra-path if required'],
            'deployment_verified': False, 'code_serving_revision': None,
            'python': {'executable': sys.executable, 'version': sys.version}}


def enumerate_paths(prefix, roots):
    result = {}
    def walk_error(error):
        raise error
    for row in roots:
        path = Path(row['path'])
        source = physical(prefix, path)
        paths = [source]
        # Record parent directory permissions without recursively including siblings.
        paths += [physical(prefix, parent) for parent in path.parents
                  if parent.is_relative_to(BASE) and parent != BASE]
        if source.is_dir():
            for directory, dirs, files in os.walk(source, followlinks=False, onerror=walk_error):
                paths.extend(Path(directory) / name for name in dirs + files)
        for source in paths:
            plain(source)
            data = source.lstat()
            if not (stat.S_ISREG(data.st_mode) or stat.S_ISDIR(data.st_mode)):
                raise ValueError('일반 파일/폴더가 아닙니다: ' + str(source))
            target = '/' + source.relative_to(prefix).as_posix()
            logical(target)
            if source.is_file() and source.suffix in ('.sqlite', '.sqlite3', '.db'):
                if any(Path(str(source) + ext).exists() for ext in ('-wal', '-shm', '-journal')):
                    raise ValueError('SQLite sidecar가 남아 있습니다. 작성 프로세스를 정상 종료한 뒤 재실행: ' + target)
            result[target] = {'kind': 'directory' if source.is_dir() else 'file',
                              'bytes': data.st_size if source.is_file() else 0,
                              'mode': stat.S_IMODE(data.st_mode), 'mtime_ns': data.st_mtime_ns,
                              'signature': (data.st_size, data.st_mtime_ns, data.st_ino, data.st_mode)}
    return dict(sorted(result.items()))


def code_evidence(root):
    paths = ('service.py', '02_BACKEND/semantic_runtime/legal_agent/unified_runtime.py',
             '02_BACKEND/semantic_runtime/legal_agent/unified_publication.py',
             '02_BACKEND/semantic_runtime/legal_agent/shortcut_store.py',
             '02_BACKEND/semantic_runtime/glossary.py', '02_BACKEND/lawrag/pipeline/term_serving_bundle.py')
    files = {name: sha(plain(root / name)) for name in paths if (root / name).is_file()}
    try:
        proc = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        head = proc.stdout.strip() if proc.returncode == 0 else None
    except OSError:
        head = None
    return {'operator_code_root': str(root), 'git_head': head,
            'important_file_sha256': files, 'tool_sha256': sha(Path(__file__)),
            'note': 'DEV checkout observation, not deployed container identity'}


def pack(a, log, run):
    prefix = plain(a.source_prefix)
    code_root = plain(a.code_root or Path.cwd())
    plan = selected(a, configuration(code_root))
    paths = enumerate_paths(prefix, plan['roots'])
    plan['file_count'] = sum(row['kind'] == 'file' for row in paths.values())
    plan['input_bytes'] = sum(row['bytes'] for row in paths.values())
    plan['code_evidence'] = code_evidence(code_root)
    write_json(run / 'PLAN.json', plan)
    log(f"선택: {plan['generation']} / runtime: {plan['runtime']}")
    log(f"파일 {plan['file_count']}개, {plan['input_bytes']:,} bytes / PLAN.json 저장")
    if a.plan_only:
        return {'status': 'PLAN_ONLY', 'plan': str(run / 'PLAN.json')}
    if not a.writers_stopped:
        raise ValueError('RAG 요청·AD worker 등 데이터 쓰기를 정상 종료한 뒤 --writers-stopped로 실행하세요. PLAN.json은 저장했습니다.')
    # Output nested under source would be recursively packed / change the snapshot.
    for root in plan['roots']:
        source = physical(prefix, Path(root['path']))
        if run.is_relative_to(source) or source.is_relative_to(run):
            raise ValueError('출력 폴더와 입력 데이터 경로가 겹칩니다')
    available = shutil.disk_usage(run).free
    if available < plan['input_bytes'] + 64 * 1024 * 1024:
        raise ValueError('출력 볼륨 여유 공간이 부족합니다. 압축 전 크기 이상의 공간을 준비하세요.')
    name = run.name
    temporary = run / (name + '.zip.partial')
    # Keep the large deliverable directly in DEV; the run folder holds logs only.
    output = run.parent / (name + '.zip')
    plan.update(bundle_id=name, created_utc=datetime.now(timezone.utc).isoformat(),
                writers_stopped_declared=True, files={})
    generation = Path(plan['generation'])
    generation_manifest = json.loads(physical(prefix, generation / 'manifest.json').read_text(encoding='utf-8'))
    anchors = {str(generation / 'manifest.json'): plan['generation_manifest_sha256']}
    if generation_manifest.get('store_sha256'):
        anchors[str(generation / 'store.sqlite')] = generation_manifest['store_sha256']
    for key in ('navigation', 'fulltext', 'glossary'):
        item = generation_manifest.get(key) or {}
        relative = item.get('bundle' if key == 'glossary' else 'path')
        if relative and item.get('manifest_sha256'):
            path = Path(os.path.normpath(generation / relative / Path('manifest.json')))
            if not path.is_relative_to(generation):
                raise ValueError('generation asset가 세대 밖을 참조합니다: ' + str(path))
            anchors[str(path)] = item['manifest_sha256']
    missing = set(anchors) - set(paths)
    if missing:
        raise ValueError('generation 필수 asset 누락: ' + ', '.join(sorted(missing)))
    total = 0
    last = time.monotonic()
    with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1,
                         allowZip64=True) as archive:
        for target, row in paths.items():
            source = physical(prefix, Path(target))
            relative = 'payload/' + target.lstrip('/')
            info = zipfile.ZipInfo(name + '/' + relative + ('/' if row['kind'] == 'directory' else ''))
            info.create_system = 3
            info._compresslevel = 1  # ZipInfo.open on Python 3.11 otherwise uses zlib's default.
            info.external_attr = ((stat.S_IFDIR if row['kind'] == 'directory' else stat.S_IFREG) | row['mode']) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            record = {k: row[k] for k in ('kind', 'bytes', 'mode', 'mtime_ns')}
            if row['kind'] == 'directory':
                archive.writestr(info, b'')
            else:
                digest = hashlib.sha256()
                with source.open('rb') as src, archive.open(info, 'w', force_zip64=True) as dst:
                    for chunk in iter(lambda: src.read(CHUNK), b''):
                        dst.write(chunk)
                        digest.update(chunk)
                        total += len(chunk)
                        if time.monotonic() - last >= 10:
                            log(f'ZIP 작성 {total:,}/{plan["input_bytes"]:,} bytes')
                            last = time.monotonic()
                record['sha256'] = digest.hexdigest()
                if target in anchors and record['sha256'] != anchors[target]:
                    raise ValueError('generation asset 해시 불일치: ' + target)
            plan['files'][target] = record
        if enumerate_paths(prefix, plan['roots']) != paths:
            raise ValueError('압축 중 입력 파일/폴더가 바뀌었습니다. 완성 ZIP을 발행하지 않습니다.')
        script = Path(__file__).read_bytes()
        restore_sh = b'#!/usr/bin/env bash\nset -euo pipefail\numask 077\nBUNDLE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"\nexec python3 "$BUNDLE_DIR/genos_rag_data_bundle.py" restore --bundle "$BUNDLE_DIR" "$@"\n'
        guide = ('DEV에서 이 폴더의 압축을 푼 뒤, 대상 볼륨을 /nfs-root/diamo에 마운트하고\n'
                 'RAG/AD 쓰기가 중지된 상태에서 bash RESTORE.sh --writers-stopped 실행.\n'
                 'payload/nfs-root/diamo/... 를 같은 절대경로로 복사합니다.\n'
                 '다른 내용의 기존 파일/심볼릭 링크는 덮어쓰지 않습니다. 원본 ZIP을 보존하세요.\n'
                 '환경변수, SQL 내부 문자열, manifest, CURRENT, 해시는 변경하지 않습니다.\n'
                 '같은 코드서빙 리비전/코드 root를 유지하고 워크플로우 화면에서 검증하세요.\n').encode('utf-8')
        for filename, data, mode in (('genos_rag_data_bundle.py', script, 0o644),
                                     ('RESTORE.sh', restore_sh, 0o755), ('GUIDE_UTF8.txt', guide, 0o644)):
            info = zipfile.ZipInfo(name + '/' + filename)
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, data)
        archive.writestr(name + '/DATA_MANIFEST.json', json.dumps(plan, ensure_ascii=False, indent=2).encode())
    # Exclusive publication preserves any existing output, even on a name collision.
    os.link(temporary, output)
    temporary.unlink()
    log('ZIP SHA256 계산 중')
    zip_sha = sha(output)
    output.with_suffix('.zip.sha256').write_text(zip_sha + '  ' + output.name + '\n', encoding='utf-8')
    write_json(run / 'DATA_MANIFEST.json', plan)
    log('ZIP 완료: ' + str(output))
    log('ZIP SHA256: ' + zip_sha)
    unpack = run.parent / 'RAG_DATA_UNPACK'
    log('압축 해제: python3 -m zipfile -e ' + shlex.quote(str(output)) + ' ' + shlex.quote(str(unpack)))
    log('새 대상 볼륨 마운트 후 복원: bash ' + shlex.quote(str(unpack / name / 'RESTORE.sh')) + ' --writers-stopped')
    return {'status': 'PACKED', 'zip': str(output), 'zip_sha256': zip_sha,
            'file_count': plan['file_count'], 'generation': plan['generation'],
            'field_deployment_verified': False}


def restore(a, log, run):
    if not a.writers_stopped:
        raise ValueError('대상 RAG/AD 쓰기를 중지한 뒤 --writers-stopped로 실행하세요')
    bundle = plain(a.bundle)
    prefix = plain(a.destination_prefix)
    manifest = plain(bundle / 'DATA_MANIFEST.json')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('schema_version') != FORMAT or data.get('absolute_path_base') != str(BASE):
        raise ValueError('지원하지 않는 데이터 묶음')
    files = data['files']
    prepared = []
    planned_dirs = set()
    # Validate the entire unpacked payload and all conflicts before copying.
    for target, row in files.items():
        path = logical(target)
        src = physical(bundle / 'payload', path)
        dst = physical(prefix, path)
        for parent in dst.parents:
            if parent.exists() and not parent.is_dir():
                raise ValueError('목적지 상위 경로가 폴더가 아닙니다: ' + str(parent))
        if src == dst or dst.is_relative_to(bundle):
            raise ValueError('복원 대상이 압축 해제 폴더와 겹칩니다')
        if row['kind'] == 'directory':
            if not src.is_dir() or (dst.exists() and not dst.is_dir()):
                raise ValueError('폴더 종류 불일치: ' + target)
            planned_dirs.add(path)
        elif row['kind'] == 'file':
            if dst.suffix in ('.sqlite', '.sqlite3', '.db') and any(
                    Path(str(dst) + ext).exists() for ext in ('-wal', '-shm', '-journal')):
                raise ValueError('대상 SQLite sidecar가 남아 있습니다: ' + target)
            if not src.is_file() or src.stat().st_size != row['bytes'] or sha(src) != row['sha256']:
                raise ValueError('압축 해제 데이터 해시 불일치: ' + target)
            if dst.exists() and (not dst.is_file() or sha(dst) != row['sha256']):
                raise ValueError('다른 내용의 기존 파일을 덮어쓰지 않습니다: ' + target)
        else:
            raise ValueError('지원하지 않는 파일 종류: ' + target)
        prepared.append((path, src, dst, row))
    actual = {('/' + p.relative_to(bundle / 'payload').as_posix()) for p in (bundle / 'payload').rglob('*')
              if not p.is_dir() or p.is_symlink()}
    expected = {target for target, row in files.items() if row['kind'] == 'file'}
    if actual != expected:
        raise ValueError('압축 해제 파일 목록 불일치')
    source_generation = physical(bundle / 'payload', Path(data['generation']) / 'manifest.json')
    if sha(source_generation) != data['generation_manifest_sha256']:
        raise ValueError('선택 generation manifest 불일치')
    log('전체 입력 해시와 목적지 충돌 검사 PASS')
    if a.verify_only:
        return {'status': 'RESTORE_PREFLIGHT_PASS', 'destination_prefix': str(prefix)}
    new_dirs = []
    copied = 0
    for path, src, dst, row in sorted(prepared, key=lambda r: (r[3]['kind'] != 'directory', len(r[0].parts), str(r[0]))):
        physical(prefix, path)
        if row['kind'] == 'directory':
            if not dst.exists():
                dst.mkdir(parents=True, mode=0o700)
                new_dirs.append((dst, row))
            continue
        if dst.exists():
            if not dst.is_file() or sha(dst) != row['sha256']:
                raise ValueError('복원 중 목적지 변경: ' + str(dst))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.rag-data-copy-', dir=dst.parent)
        temporary = Path(temp)
        try:
            with os.fdopen(fd, 'wb') as stream, src.open('rb') as original:
                shutil.copyfileobj(original, stream, CHUNK)
                stream.flush()
                os.fsync(stream.fileno())
            if sha(temporary) != row['sha256']:
                raise ValueError('복사 데이터 해시 불일치: ' + str(dst))
            os.chmod(temporary, row['mode'])
            os.utime(temporary, ns=(row['mtime_ns'], row['mtime_ns']))
            # link is atomic and cannot overwrite a file created after preflight.
            os.link(temporary, dst)
            copied += 1
        finally:
            temporary.unlink(missing_ok=True)
    for dst, row in reversed(new_dirs):
        os.chmod(dst, row['mode'])
        os.utime(dst, ns=(row['mtime_ns'], row['mtime_ns']))
    log(f'복원 완료: 새 파일 {copied}개 / 동일 파일은 유지')
    return {'status': 'RESTORED', 'copied_files': copied,
            'generation': data['generation'], 'runtime': data['runtime'],
            'data_manifest_sha256': sha(manifest), 'field_serving_verified': False,
            'code_evidence': data.get('code_evidence')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('pack', help='run in GENOS DEV, without changing source data')
    p.add_argument('--generation', type=Path)
    p.add_argument('--runtime', type=Path)
    p.add_argument('--state', type=Path)
    p.add_argument('--code-root', type=Path)
    p.add_argument('--source-prefix', type=Path, default=Path('/'))
    p.add_argument('--include-request-logs', action='store_true')
    p.add_argument('--extra-path', type=Path, action='append', default=[])
    p.add_argument('--plan-only', action='store_true')
    r = commands.add_parser('restore', help='copy an unpacked payload to its original absolute paths')
    r.add_argument('--bundle', type=Path, required=True)
    r.add_argument('--destination-prefix', type=Path, default=Path('/'))
    r.add_argument('--verify-only', action='store_true')
    for sub in (p, r):
        sub.add_argument('--writers-stopped', action='store_true')
        sub.add_argument('--output-dir', type=Path,
                         help='pack: ZIP directly in this folder (default: code root); restore: log folder base')
    a = parser.parse_args(argv)
    os.umask(0o077)
    default_output = (a.code_root or Path.cwd()) if a.command == 'pack' else Path.cwd() / 'TRANSFER'
    base = plain(a.output_dir or default_output)
    base.mkdir(parents=True, exist_ok=True)
    name = ('genos-rag-data-' if a.command == 'pack' else 'genos-rag-restore-') + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    run = base / name
    run.mkdir()
    log = Log(run / 'RUN.log')
    log('START ' + a.command + ' / ' + sys.executable + ' / Python ' + sys.version.split()[0])
    try:
        result = pack(a, log, run) if a.command == 'pack' else restore(a, log, run)
        write_json(run / 'STATUS.json', result)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        message = str(exc) or type(exc).__name__
        log('FAILED: ' + message)
        write_json(run / 'STATUS.json', {'status': 'FAILED', 'error': message,
                                        'source_data_modified': False if a.command == 'pack' else None,
                                        'completed': False})
        return 1
    finally:
        log.stream.close()


if __name__ == '__main__':
    raise SystemExit(main())
