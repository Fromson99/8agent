#!/usr/bin/env bash
set -euo pipefail
umask 077
GENOS_COMPAT_ATTACHMENTS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
python3 - "$GENOS_COMPAT_ATTACHMENTS/genos-external-only-20260910.zip" "${GENOS_SCHEMA_BUILD_ROOT:-/home/genos/DEV}" "$@" <<'PY'
from pathlib import Path, PurePosixPath
import ast, fcntl, hashlib, json, os, shutil, sys, tempfile, zipfile

EXPECTED = '1cfe9b10666ea8d55ba8fbe2e8ffb73f66b4e6c12bfd4355462e22ed7ddcf442'
archive_path, root = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
if sys.argv[3:] not in ([], ['--check-only'], ['--install-only']):
    raise SystemExit('옵션: --check-only 또는 --install-only')
check_only = sys.argv[3:] == ['--check-only']
sha = lambda b: hashlib.sha256(b).hexdigest()
if not (root/'00_SYSTEM/WORKSPACE.json').is_file() or not (root/'02_BACKEND').is_dir():
    raise SystemExit('코드 루트가 아닙니다: '+str(root))
if not archive_path.is_file() or sha(archive_path.read_bytes()) != EXPECTED:
    raise SystemExit('첨부 ZIP 누락/해시 불일치. 이번 메일의 ZIP과 Bash를 같은 폴더에 두세요.')

def target_path(name):
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or '\\' in name or not rel.parts:
        raise ValueError('unsafe path: '+name)
    if name != 'service.py' and rel.parts[0] not in {'00_SYSTEM','02_BACKEND','06_TOOLS','07_DOCS'}:
        raise ValueError('outside code patch scope: '+name)
    target = root.joinpath(*rel.parts)
    for part in [target, *target.parents]:
        if part == root: break
        if part.is_symlink(): raise ValueError('symlink target: '+name)
    return target

# Directory descriptor lock avoids creating or following an installer lock symlink.
directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
try:
    fcntl.flock(directory_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('다른 호환 패치 설치가 실행 중입니다.')
with zipfile.ZipFile(archive_path) as z:
    manifest = json.loads(z.read('patch-manifest.json'))
    if manifest.get('format') != 'genos-latest-compatible-v1': raise SystemExit('패치 형식 오류')
    files = manifest['files']
    if set(z.namelist()) != set(files)|{'patch-manifest.json'} or len(z.namelist()) != len(files)+1:
        raise SystemExit('ZIP 목록 불일치')
    updates, preserved, conflicts, overlay, before = [], {}, [], {}, {}
    for name, entry in files.items():
        try:
            target = target_path(name)
            content = z.read(name)
            if sha(content) != entry['sha256']: raise ValueError('ZIP member hash mismatch')
            if name.endswith('.py'): ast.parse(content, filename=name, feature_version=(3,11))
            if name.endswith('.json'): json.loads(content)
            overlay[name] = content
            if target.exists():
                if not target.is_file(): raise ValueError('target is not a file')
                old = target.read_bytes(); fingerprint = sha(old)
                before[name] = fingerprint
                if entry.get('preserve_existing'):
                    preserved[name] = fingerprint
                    overlay[name] = old
                    continue
                if fingerprint == entry['sha256']: continue
                known = set(entry['previous_sha256'])|{entry['sha256']}
                if fingerprint not in known and sha(old.replace(b'\r\n',b'\n')) not in known:
                    raise ValueError('알 수 없는 파일 버전, 보존함; SHA256='+fingerprint)
            else:
                before[name] = None
            updates.append((name,target,content))
        except Exception as exc:
            conflicts.append({'path': name, 'error': str(exc)})

    def read(name):
        return overlay[name] if name in overlay else target_path(name).read_bytes()

    if not conflicts:
        try:
            pipeline = json.loads(read('00_SYSTEM/PIPELINE.json'))
            for binding in pipeline['engines'].values():
                name = binding['manifest']
                if not name.startswith('02_BACKEND/ENGINES/semantic_runtime/'): continue
                raw = read(name)
                if sha(raw) != binding['sha256']: raise ValueError('engine registry mismatch: '+name)
                for dependency, expected in json.loads(raw)['files'].items():
                    if sha(read(dependency)) != expected: raise ValueError('engine code hash mismatch: '+dependency)
            required_schemas = {c['schema_path']:c['schema_sha256'] for c in pipeline['contracts'].values() if 'schema_path' in c}
            legal = json.loads(read('00_SYSTEM/LEGAL_SCHEMA.json'))['normative_schema']
            required_schemas[legal['path']] = legal['sha256']
            for name, expected in required_schemas.items():
                if sha(read(name)) != expected: raise ValueError('schema mismatch: '+name)
        except Exception as exc:
            conflicts.append({'path':'dependency/registry validation','error':str(exc)})
    if conflicts:
        print('설치 전 검사 실패. 코드 파일은 하나도 변경하지 않았습니다.')
        print(json.dumps({'conflicts':conflicts},ensure_ascii=False,indent=2))
        raise SystemExit(1)
    print('검사 통과: 최신 메일 버전 + 전체 빌드 + 엔진/스키마 해시')
    print('현장 genos.py 유지:', json.dumps(preserved,ensure_ascii=False))
    if check_only:
        print('CHECK ONLY: 설치 예정',len(updates),'개, 코드 변경/모델 호출 없음')
        raise SystemExit(0)
    if updates:
        backup_base = root/'runtime/patch-backups'
        for part in [backup_base,*backup_base.parents]:
            if part == root: break
            if part.is_symlink(): raise SystemExit('백업 경로가 symlink입니다. 변경하지 않았습니다.')
        backup_base.mkdir(parents=True,exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix='genos-compatible-',dir=backup_base))
        done = []
        try:
            # Detect edits since preflight before changing any target.
            for name,expected in before.items():
                target=target_path(name)
                actual=sha(target.read_bytes()) if target.is_file() else None
                if actual!=expected: raise ValueError('파일이 검사 후 변경됨: '+name)
            for name,target,content in updates:
                saved=backup/name; existed=target.exists()
                if existed:
                    saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
                target.parent.mkdir(parents=True,exist_ok=True)
                fd,temporary=tempfile.mkstemp(prefix='.genos-compatible-',dir=target.parent)
                try:
                    with os.fdopen(fd,'wb') as stream:
                        stream.write(content);stream.flush();os.fsync(stream.fileno())
                    os.chmod(temporary,0o644);os.replace(temporary,target)
                    done.append((target,saved,existed))
                finally:
                    Path(temporary).unlink(missing_ok=True)
            for name,entry in files.items():
                if not entry.get('preserve_existing') and sha((root/name).read_bytes()) != entry['sha256']:
                    raise ValueError('post-install verification failed: '+name)
            receipt={'zip_sha256':EXPECTED,'base_mail_id':manifest['base_mail_id'],
                     'updated':[n for n,_,_ in updates],'before':before,'preserved':preserved,
                     'status':'INSTALLED','models_called':False}
            (backup/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
        except BaseException:
            for target,saved,existed in reversed(done):
                if existed: shutil.copy2(saved,target)
                else: target.unlink(missing_ok=True)
            print('설치 실패: 적용한 코드 변경은 복구했습니다. 백업:',backup)
            raise
        print('설치 완료:',len(updates),'개 / 백업:',backup)
    else:
        print('이미 같은 호환 패치입니다. 변경 없음.')
print('환경변수·원본·Git·서비스 CURRENT는 변경하지 않았습니다. 모델 호출 없음.')
print('다음: cd '+str(root)+' && bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id external-001 --exclude-internal --check-only')
PY

