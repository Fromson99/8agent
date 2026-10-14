#!/usr/bin/env python3
"""Join/uploaded archive -> original NFS paths -> existing NFS probe/workflow.

Only run in the GENOS DEV checkout. Standard library orchestration; no model
calls. Destination prefix is for offline snapshots/tests, not path rewriting.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import uuid
import zipfile

BASE = Path('/nfs-root/diamo')
GENERATION = BASE / '8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
RUNTIME = BASE / '8-agent/runtime'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def join_input(source, join_script):
    """Reuse the previously tested Bash joiner; verify resumed outputs too."""
    if not source.is_dir():
        if source.suffix.lower() != '.zip' or source.is_symlink() or not source.is_file():
            raise ValueError('기존 데이터 ZIP 또는 R4 .zip.parts 폴더를 지정하세요')
        checksum = Path(str(source) + '.sha256')
        if checksum.exists():
            # Check this selected ZIP only; never evaluate checksum filenames.
            expected = checksum.read_text(encoding='utf-8').split()[0]
            if not re.fullmatch(r'[0-9a-fA-F]{64}', expected) or sha(source) != expected.lower():
                raise ValueError('선택 데이터 ZIP SHA-256 불일치')
        return source
    raw = (source / 'ORIGINAL.sha256').read_text(encoding='utf-8').rstrip('\n')
    match = re.fullmatch(r'([0-9a-fA-F]{64})  (.+)', raw)
    if not match:
        raise ValueError('R4 ORIGINAL.sha256 형식이 아닙니다')
    expected, name = match.groups()
    if not name.lower().endswith('.zip') or name in ('.', '..') or any(c in name for c in '/\\\r\n'):
        raise ValueError('원본 ZIP 이름이 올바르지 않습니다')
    target = source.parent / (name.rsplit('.', 1)[0] + '_restored.zip')
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or sha(target) != expected.lower():
            raise ValueError('다른 내용의 기존 복원 ZIP은 보존합니다: ' + str(target))
        subprocess.run(['sha256sum', '-c', '--', 'PARTS.sha256'], cwd=source, check=True)
        print('JOIN_REUSED=' + str(target), flush=True)
        return target
    subprocess.run(['bash', str(join_script), str(source)], check=True)
    if sha(target) != expected.lower():
        raise ValueError('합친 ZIP의 원본 SHA-256 불일치')
    return target


def unpack(archive, base):
    """Reject unsafe ZIP members before extraction; do not run bundled code."""
    digest = sha(archive)
    base.mkdir(parents=True, exist_ok=True)
    target = base / digest
    if target.exists():
        if target.is_symlink() or json.loads((target / 'ARCHIVE.json').read_text())['sha256'] != digest:
            raise ValueError('기존 해제 폴더의 이관 기록 불일치')
        bundles = list(target.glob('*/DATA_MANIFEST.json'))
        if len(bundles) != 1:
            raise ValueError('기존 해제 폴더에 정본 DATA_MANIFEST가 없습니다')
        return bundles[0].parent, digest
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        normalized = []
        for member in z.infolist():
            p = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (p.is_absolute() or '..' in p.parts or '\\' in member.filename or not p.parts
                    or p.as_posix() != member.filename.rstrip('/')
                    or member.flag_bits & 1 or stat.S_ISLNK(mode)
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError('안전하지 않은 데이터 ZIP 항목: ' + member.filename)
            normalized.append(p.as_posix())
        if len(names) != len(set(normalized)):
            raise ValueError('데이터 ZIP에 중복 항목이 있습니다')
        manifests = [n for n in names if len(PurePosixPath(n).parts) == 2 and n.endswith('/DATA_MANIFEST.json')]
        if len(manifests) != 1 or len({PurePosixPath(n).parts[0] for n in names}) != 1:
            raise ValueError('기존 genos-rag-data 데이터 묶음 구조가 아닙니다')
        member = z.getinfo(manifests[0])
        if member.file_size > 64 * 1024 * 1024:
            raise ValueError('DATA_MANIFEST가 너무 큽니다')
        metadata = json.loads(z.read(member))
        if metadata.get('schema_version') not in ('genos-rag-data-path-preserving-v1', 'genos-rag-data-live-v2'):
            raise ValueError('지원하지 않는 데이터 ZIP 계약')
        free = shutil.disk_usage(base).free
        expanded = sum(row.file_size for row in z.infolist())
        if free < expanded + 64 * 1024 * 1024:
            raise ValueError('DEV/TRANSFER의 압축 해제 공간이 부족합니다')
        partial = Path(tempfile.mkdtemp(prefix='unpack-partial-', dir=base))
        print('UNPACK_PARTIAL=' + str(partial), flush=True)
        for member in z.infolist():
            path = partial / member.filename
            if member.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as original, path.open('xb') as output:
                    shutil.copyfileobj(original, output, 8 * 1024 * 1024)
        record(partial / 'ARCHIVE.json', {'archive': str(archive), 'sha256': digest})
        # rename refuses an existing nonempty target. No existing extraction deleted.
        partial.rename(target)
    if sha(archive) != digest:
        raise ValueError('해제 중 원본 ZIP이 변경되었습니다')
    return target / PurePosixPath(manifests[0]).parts[0], digest


def selected_bundle(bundle):
    data = json.loads((bundle / 'DATA_MANIFEST.json').read_text(encoding='utf-8'))
    if data.get('absolute_path_base') != str(BASE) or data.get('generation') != str(GENERATION) or data.get('runtime') != str(RUNTIME) or data.get('state'):
        raise ValueError('ZIP 선택 경로가 최신 확인 generation/runtime/state 미설정과 다릅니다')
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inspect', 'restore', 'deploy', 'all', 'push', 'list-local'))
    parser.add_argument('input', nargs='?', help='ZIP or .zip.parts path inside DEV or DEV/TRANSFER')
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--tools-dir', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--writers-stopped', action='store_true')
    parser.add_argument('--accept-live-archive', action='store_true')
    parser.add_argument('--team-id', help='optional team folder name for source document metadata')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--no-push', action='store_true')
    parser.add_argument('--destination-prefix', type=Path, default=Path('/'), help='offline mounted snapshot/test prefix only')
    a = parser.parse_args(argv)
    run = a.run_dir.resolve(strict=True)
    result = {'status': 'STARTED', 'mode': a.mode, 'python': sys.executable, 'version': sys.version.split()[0],
              'started_at_utc': datetime.now(timezone.utc).isoformat(), 'steps': {},
              'code_serving_revision': None, 'workflow_verified': False, 'full_rag_gate_verified': False}
    record(run / 'STATUS.json', result)
    try:
        root = a.code_root.resolve(strict=True)
        tools = a.tools_dir.resolve(strict=True)
        bundle_tool = load(tools / '06_TOOLS/COMMANDS/genos_rag_data_bundle.py', '_transfer_bundle')
        handoff = load(tools / '06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py', '_transfer_handoff')
        prefix = a.destination_prefix.absolute()
        nfs_base = prefix / BASE.relative_to('/')
        generation = prefix / GENERATION.relative_to('/')
        runtime = prefix / RUNTIME.relative_to('/')
        result.update(code_root=str(root), generation=str(generation), runtime=str(runtime), nfs_root=str(nfs_base / '8-agent'),
                      simulated_destination_prefix=str(prefix) if prefix != Path('/') else None)
        if a.mode in ('all', 'restore') and not a.writers_stopped:
            raise ValueError('대상 RAG/AD 쓰기를 정상 중지한 뒤 --writers-stopped를 지정하세요')
        if a.mode in ('inspect', 'all', 'restore'):
            name = a.input or input('DEV ZIP 또는 .zip.parts 이름: ').strip()
            source = Path(name).expanduser()
            if not source.is_absolute():
                source = root / source
                if not source.exists():
                    source = root / 'TRANSFER' / name
            # The DEV root alias is resolved above; refuse links in the data itself.
            source = bundle_tool.plain(source)
            result['phase'] = 'join_and_unpack'
            archive = join_input(source, tools / 'JOIN_TRANSFER_ZIP.txt')
            bundle, zip_sha = unpack(archive, root / 'TRANSFER/RAG_DATA_UNPACK')
            metadata = selected_bundle(bundle)
            result.update(data_zip=str(archive), data_zip_sha256=zip_sha,
                          data_manifest_sha256=sha(bundle / 'DATA_MANIFEST.json'), bundle=str(bundle),
                          generation_manifest_sha256=metadata['generation_manifest_sha256'])
            print('DATA_BUNDLE=' + str(bundle), flush=True)
            print('ARCHIVE_RESTORE_ELIGIBLE=' + str(metadata.get('archive_restore_eligible')), flush=True)
            report = bundle / 'SOURCE_CHANGES.txt'
            if report.exists():
                print('SOURCE_CHANGES_REPORT=' + str(report), flush=True)
                print(report.read_text(encoding='utf-8')[:12000], flush=True)
            if a.mode != 'inspect':
                result['phase'] = 'nfs_restore_preflight'
                mount = bundle_tool.output_mount(nfs_base.resolve(strict=True))
                result['mount'] = mount
                if prefix == Path('/') and mount.get('fs_type') not in ('nfs', 'nfs4'):
                    raise ValueError('대상 /nfs-root/diamo의 실제 NFS 마운트를 확인하세요; 로컬 폴더에는 복원하지 않습니다')
                # The existing restore routine checks every hash and every
                # destination conflict before its first copy. Do this once.
                options = SimpleNamespace(writers_stopped=True, bundle=bundle, destination_prefix=prefix,
                                          verify_only=False, accept_live_archive=a.accept_live_archive)
                result['phase'] = 'nfs_restore_preflight_and_copy'
                result['steps']['restore'] = bundle_tool.restore(options, print, run)
                record(run / 'STATUS.json', result)
        if a.mode in ('all', 'deploy'):
            result['phase'] = 'install_existing_probe_hook'
            archive = tools / 'CODE_PAYLOAD.zip'
            options = SimpleNamespace(archive=archive, zip_sha256=sha(archive), code_root=root)
            install_run = run / 'install'
            install_run.mkdir()
            result['steps']['install'] = handoff.install(options, install_run)
            record(run / 'STATUS.json', result)
            result['phase'] = 'prepare_same_checkout'
            prepare_run = run / 'prepare'
            prepare_run.mkdir()
            options = SimpleNamespace(code_root=root, nfs_base=nfs_base, generation=generation, runtime=runtime,
                                      state=None, state_unset=True, list_team_id=a.team_id, run_dir=prepare_run)
            result['steps']['prepare'] = handoff.prepare(options, prepare_run)
            result['phase'] = 'prepared_commit'
            record(run / 'STATUS.json', result)
            for name in ('WORKFLOW_PASTE_ALL.txt', 'SERVING_ENV_PATHS.txt'):
                shutil.copyfile(prepare_run / name, run / name)
                print(name + '=' + str(run / name), flush=True)
            if not a.no_push:
                result['phase'] = 'push_exact_prepared_commit'
                result['steps']['push'] = handoff.publish(SimpleNamespace(code_root=root, remote=a.remote), run)
        elif a.mode == 'push':
            result['phase'] = 'push_exact_prepared_commit'
            result['steps']['push'] = handoff.publish(SimpleNamespace(code_root=root, remote=a.remote), run)
        elif a.mode == 'list-local':
            probe = handoff.load_probe(root)
            result['steps']['list_local'] = probe.probe(code_root=root, stage='code-space', nfs_base=nfs_base, include_listing=True)
            if not result['steps']['list_local']['ok']:
                raise ValueError('코드스페이스 목록 검사 실패; STATUS.json을 확인하세요')
        result.update(status='CODE_SPACE_STAGES_PASS', phase='finished')
        record(run / 'STATUS.json', result)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='FAILED', error_type=type(exc).__name__,
                      error='실행 단계 실패; RUN.log를 확인하세요' if isinstance(exc, subprocess.CalledProcessError) else str(exc))
        record(run / 'STATUS.json', result)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
