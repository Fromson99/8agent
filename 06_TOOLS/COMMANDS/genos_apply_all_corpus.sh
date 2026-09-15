#!/usr/bin/env bash
# Put this script and the patch ZIP in DEV/TRANSFER. No unzip command needed.
set -euo pipefail
umask 077
GENOS_SCHEMA_BUILD_ATTACHMENT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
GENOS_SCHEMA_BUILD_INSTALL_ONLY=0
if [[ "${1:-}" == "--install-only" ]]; then
  GENOS_SCHEMA_BUILD_INSTALL_ONLY=1
  shift
fi
GENOS_SCHEMA_BUILD_DETECTED_ROOT="$(python3 - "$GENOS_SCHEMA_BUILD_ATTACHMENT_DIR" <<'PY'
from pathlib import Path
import os, sys
configured = os.environ.get('GENOS_SCHEMA_BUILD_ROOT')
candidates = [Path(configured)] if configured else [Path.cwd(), *Path.cwd().parents,
    Path(sys.argv[1]), *Path(sys.argv[1]).parents, Path('/home/genos/DEV'), Path('/workspace')]
for p in candidates:
    if (p/'00_SYSTEM/WORKSPACE.json').is_file() and (p/'02_BACKEND/semantic_runtime/genos.py').is_file():
        print(p.resolve())
        break
else:
    raise SystemExit('코드 폴더를 찾지 못했습니다. GENOS_SCHEMA_BUILD_ROOT=/home/genos/DEV 를 지정하세요.')
PY
)"
python3 - "$GENOS_SCHEMA_BUILD_DETECTED_ROOT" "$GENOS_SCHEMA_BUILD_ATTACHMENT_DIR/genos-all-corpus-20260909.zip" <<'PY'
from pathlib import Path, PurePosixPath
import hashlib, json, os, shutil, sys, tempfile, zipfile

EXPECTED_ZIP_SHA = '88fee4772e62c52f09dcc0d2ddaccf5ac1002f481ca18a59b7d81eb9778636c1'
root, archive_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
digest = lambda b: hashlib.sha256(b).hexdigest()
if not archive_path.is_file() or digest(archive_path.read_bytes()) != EXPECTED_ZIP_SHA:
    raise SystemExit('ZIP 누락/해시 불일치: 메일 첨부 ZIP을 스크립트와 같은 폴더에 두세요.')
with zipfile.ZipFile(archive_path) as archive:
    manifest = json.loads(archive.read('patch-manifest.json'))
    if manifest.get('format') != 'genos-schema-build-patch-v1':
        raise SystemExit('지원하지 않는 패치 형식')
    files = manifest['files']
    if set(archive.namelist()) != set(files) | {'patch-manifest.json'} or len(archive.namelist()) != len(files)+1:
        raise SystemExit('ZIP 파일 목록 불일치')
    updates = []
    for name, record in files.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or (name != 'service.py' and rel.parts[0] not in {'00_SYSTEM','02_BACKEND','06_TOOLS','07_DOCS'}):
            raise SystemExit('안전하지 않은 패치 경로')
        target = root.joinpath(*rel.parts)
        for part in [target, *target.parents]:
            if part == root:
                break
            if part.is_symlink():
                raise SystemExit('심볼릭 링크 대상은 패치하지 않습니다: '+name)
        content = archive.read(name)
        if digest(content) != record['sha256']:
            raise SystemExit('패치 파일 해시 불일치: '+name)
        if target.exists():
            if not target.is_file():
                raise SystemExit('파일이 아닌 패치 대상: '+name)
            old_hash = digest(target.read_bytes())
            if old_hash == record['sha256']:
                continue
            if old_hash not in record['previous_sha256']:
                raise SystemExit('현장 수정 발견, 덮어쓰지 않았습니다: '+name)
        elif record['previous_sha256'] and not record.get('allow_missing', False):
            raise SystemExit('기존 필수 코드가 없습니다: '+name)
        updates.append((name, target, content))
    if updates:
        backup_base = root/'runtime/patch-backups'
        backup_base.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix='genos-schema-build-', dir=backup_base))
        done = []
        try:
            for name, target, content in updates:
                saved = backup/name
                existed = target.exists()
                if existed:
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(prefix='.genos-schema-build-', dir=target.parent)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(content)
                    os.chmod(temporary, 0o644)
                    os.replace(temporary, target)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                done.append((target, saved, existed))
            (backup/'receipt.json').write_text(json.dumps({'zip_sha256': EXPECTED_ZIP_SHA,
                'updated': [n for n,_,_ in updates], 'new_files': [str(t.relative_to(root)) for t,_,e in done if not e]}, indent=2))
        except Exception:
            for target, saved, existed in reversed(done):
                if existed:
                    shutil.copy2(saved, target)
                else:
                    target.unlink()
            raise
        print('패치 적용:', len(updates), '개 / 기존 파일 백업:', backup)
    else:
        print('이미 같은 패치가 적용되어 있습니다.')
print('URL·인증키·genos.py·데이터·Git은 변경하지 않았습니다.')
PY
printf '설치 완료. 입력 점검: cd %q && bash 06_TOOLS/COMMANDS/genos_build_all.sh --run-id full-001 --check-only\n' "$GENOS_SCHEMA_BUILD_DETECTED_ROOT"
