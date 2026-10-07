"""Apply the relation scan logging patch to the existing GENOS Git checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

PATCH = Path(__file__).resolve().parent
MANIFEST = json.loads((PATCH / 'CODE_MANIFEST.json').read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deploy-root', type=Path, required=True)
    parser.add_argument('--rollback-from', type=Path)
    args = parser.parse_args()
    root = args.deploy_root.expanduser().resolve()
    if not (root / '.git').exists():
        raise SystemExit('ERROR: deploy root must be the existing Git checkout')
    files = MANIFEST['files']
    if args.rollback_from:
        backup = args.rollback_from.expanduser().resolve()
        for relative, hashes in files.items():
            saved = backup / relative
            target = root / relative
            if not saved.is_file() or digest(saved) != hashes['base_sha256']:
                raise SystemExit('ERROR: backup missing or invalid; no files changed: ' + relative)
            if not target.is_file() or digest(target) != hashes['new_sha256']:
                raise SystemExit('ERROR: target is not the patch version; no files changed: ' + relative)
        for relative in files:
            target = root / relative
            staged = target.with_name('.' + target.name + '.relation-scan-rollback.tmp')
            shutil.copy2(backup / relative, staged)
            os.replace(staged, target)
        sys.path.insert(0, str(root / '02_BACKEND'))
        from semantic_runtime.control import rehash_engines
        rehash_engines(root, apply=True)
        print(json.dumps({'status': 'ROLLED_BACK', 'deploy_root': str(root),
                          'backup': str(backup)}, ensure_ascii=False))
        return
    for relative, hashes in files.items():
        target = root / relative
        source = PATCH / 'payload' / relative
        if not target.is_file() or not source.is_file() or digest(source) != hashes['new_sha256']:
            raise SystemExit('ERROR: missing target/payload or payload hash mismatch: ' + relative)
        if digest(target) not in (hashes['base_sha256'], hashes['new_sha256']):
            raise SystemExit('ERROR: target version differs; no files changed: ' + relative)

    sys.path.insert(0, str(root / '02_BACKEND'))
    from semantic_runtime.control import rehash_engines
    before = rehash_engines(root)
    unrelated = set(before['changed_code']) - set(files)
    if unrelated or before['schemas']:
        raise SystemExit('ERROR: unrelated engine/schema drift; no files changed: ' + repr(sorted(unrelated)))

    backup = root / 'TRANSFER' / ('relation-scan-log-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    changed = []
    for relative, hashes in files.items():
        target = root / relative
        if digest(target) == hashes['new_sha256']:
            continue
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
        staged = target.with_name('.' + target.name + '.relation-scan-log.tmp')
        shutil.copy2(PATCH / 'payload' / relative, staged)
        os.replace(staged, target)
        changed.append(relative)
    result = rehash_engines(root, apply=True)
    after = rehash_engines(root)
    if after['changed_code'] or after['schemas']:
        raise SystemExit('ERROR: engine hashes remain inconsistent; restore from ' + str(backup))
    print(json.dumps({'status': 'APPLIED' if changed else 'ALREADY_APPLIED',
                      'deploy_root': str(root), 'backup': str(backup) if changed else None,
                      'changed_files': changed, 'engine_hashes_updated': result['applied']},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
