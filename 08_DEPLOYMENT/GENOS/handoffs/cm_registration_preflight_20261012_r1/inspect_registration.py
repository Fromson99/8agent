"""Collect CM registration prerequisites; never register, patch, or call a model."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import traceback

REVISION = 'GENOS_CM_REGISTER_CHECK_20261012_R1'
FIELD_GENERATION = '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
FIELD_RUNTIME = '/nfs-root/diamo/8-agent/runtime'
PACKAGE_SHA = 'a167b8892698c314168c0c436418e42549626c12f15eff494a6903b8f1d11f5f'
CODE_FILES = [
    'CODE_MANIFEST.json', '00_SYSTEM/PIPELINE.json',
    '00_SYSTEM/GENOS_SERVING_PATHS.json', 'service.py', 'service/service.py',
    '02_BACKEND/lawrag/pipeline/shortcut_package.py',
    '02_BACKEND/lawrag/pipeline/unified_memory.py',
    '02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py',
    '02_BACKEND/semantic_runtime/legal_agent/shortcut_repository.py',
    '02_BACKEND/semantic_runtime/legal_agent/shortcut_store.py',
    '02_BACKEND/semantic_runtime/legal_agent/wiki_execution.py',
    '02_BACKEND/semantic_runtime/deployment_paths.py',
]


def fingerprint(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def git(root, *args):
    p = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True,
                       timeout=20, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    return {'exit_code': p.returncode, 'stdout': p.stdout.strip()}


def store_summary(runtime):
    base = runtime / 'case-memory'
    pointer = base / 'SHORTCUT_CURRENT.json'
    path = base / 'cases-v4.sqlite'
    result = {'pointer_exists': pointer.is_file()}
    if pointer.is_file():
        value = read(pointer)
        result['pointer_sha256'] = fingerprint(pointer)
        if value.get('schema_version') != 'shortcut-store-pointer-v1':
            raise ValueError('Unknown shortcut pointer schema')
        encoded = json.dumps(value['receipt'], ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')).encode()
        if hashlib.sha256(encoded).hexdigest() != value.get('receipt_hash'):
            raise ValueError('Shortcut pointer receipt hash differs')
        path = (base / value['path']).resolve()
        if not path.is_relative_to(base.resolve()) or path.name != 'cases-v4.sqlite':
            raise ValueError('Shortcut store path outside selected runtime')
    result.update(path=str(path), exists=path.is_file())
    if not path.is_file():
        return result
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        db.execute('PRAGMA query_only=ON')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result['user_version'] = db.execute('PRAGMA user_version').fetchone()[0]
        if {'sw_unit', 'sw_knowledge', 'sw_lifecycle'} <= tables:
            groups = {}
            for payload, status in db.execute(
                    'SELECT k.payload,l.status FROM sw_unit u '
                    'JOIN sw_knowledge k ON k.unit=u.id AND k.revision=u.head '
                    'JOIN sw_lifecycle l ON l.unit=k.unit AND l.revision=k.revision'):
                route = json.loads(payload).get('core_evidence_route', {})
                # Only aggregate registration identities; no questions, facts, or answers.
                key = json.dumps({'status': status, 'contract': route.get('contract'),
                                  'import_id': route.get('import_id'),
                                  'source_binding': route.get('source_binding')}, sort_keys=True)
                groups[key] = groups.get(key, 0) + 1
            result['head_groups'] = [{**json.loads(k), 'count': v} for k, v in groups.items()]
        if 'sw_import' in tables:
            result['import_receipts'] = []
            for (payload,) in db.execute('SELECT payload FROM sw_import'):
                v = json.loads(payload)
                result['import_receipts'].append({k: v.get(k) for k in
                    ('import_id', 'package_id', 'package_sha256', 'source_binding', 'visibility')})
    finally:
        db.close()
    return result


def inspect(root, output, package, *, offline_generation=None, offline_runtime=None):
    report = {'revision': REVISION, 'code_root': str(root),
              'python_executable': sys.executable, 'python_version': sys.version,
              'registration_performed': False, 'code_applied': False, 'model_calls': 0,
              'push_performed': False, 'field_revision_verified': False,
              'offline_validation': offline_generation is not None, 'issues': []}
    try:
        if not (root / '02_BACKEND').is_dir() or not (root / 'service.py').is_file():
            raise ValueError('Place the RUN TXT in the existing DEV/TRANSFER directory')
        report['code_files'] = {p: fingerprint(root / p) if (root / p).is_file() else None
                                for p in CODE_FILES}
        report['git_head'] = git(root, 'rev-parse', 'HEAD')
        report['git_status'] = git(root, 'status', '--porcelain', '--untracked-files=no')
        report['known_cm_runs'] = []
        for revision in ('r8', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15'):
            folder = root / 'TRANSFER' / ('cm-oneclick-' + revision)
            for name in ('STATUS.json', 'CM51_REGISTERED.json', 'DATA_VERIFIED.json'):
                p = folder / name
                if p.is_file():
                    value = read(p)
                    report['known_cm_runs'].append({'path': str(p), 'sha256': fingerprint(p),
                        **{k: value.get(k) for k in ('state', 'revision', 'generation',
                            'generation_manifest_sha256', 'runtime', 'commit', 'import_id',
                            'package_id', 'source_binding', 'verified')}})

        config_path = root / '00_SYSTEM/GENOS_SERVING_PATHS.json'
        config = read(config_path) if config_path.is_file() else None
        if offline_generation is not None:
            generation, runtime = offline_generation.resolve(), offline_runtime.resolve()
            report['selection_basis'] = 'explicit offline validation inputs'
        elif config:
            if (config.get('schema_version') != 'genos-serving-paths-v1' or
                    config.get('selection') != 'operator-fixed' or config.get('state') is not None):
                raise ValueError('Unsupported installed serving path configuration; preserved')
            generation, runtime = Path(config['generation']), Path(config['runtime'])
            report['selection_basis'] = 'installed GENOS_SERVING_PATHS.json; serving revision still unverified'
            if str(generation) != FIELD_GENERATION or str(runtime) != FIELD_RUNTIME:
                raise ValueError('Installed paths differ from the last field handoff; preserved')
        else:
            generation, runtime = Path(FIELD_GENERATION), Path(FIELD_RUNTIME)
            report['selection_basis'] = 'last field handoff and user confirmed unchanged data; selection unverified'
            report['issues'].append('NO_INSTALLED_SERVING_PATH_CONFIG')

        if not generation.is_absolute() or not runtime.is_absolute() or generation.is_symlink():
            raise ValueError('Generation/runtime path is invalid')
        report.update(generation=str(generation), runtime=str(runtime))
        for key, expected in [('GENOS_GENERATION', str(generation)), ('GENOS_RUNTIME_DIR', str(runtime))]:
            if os.environ.get(key, '').strip() and os.environ[key].strip() != expected:
                report['issues'].append(key + '_TERMINAL_ENV_DIFFERS')
        if os.environ.get('GENOS_STATE_DIR', '').strip():
            report['issues'].append('TERMINAL_STATE_OVERRIDE_PRESENT')
        manifest_path = generation / 'manifest.json'
        manifest = read(manifest_path)
        report.update(generation_id=manifest.get('generation_id'),
                      generation_manifest_sha256=fingerprint(manifest_path),
                      generation_counts=manifest.get('counts'))
        if config and offline_generation is None and report['generation_manifest_sha256'] != config.get('generation_manifest_sha256'):
            raise ValueError('Installed source manifest hash differs; preserved')
        report['shortcut_store'] = store_summary(runtime)
        print('현장 코드·원문 세대·기존 shortcut 상태 수집 완료', flush=True)

        if fingerprint(package) != PACKAGE_SHA:
            raise ValueError('Diagnostic CM package hash differs')
        # Use the actual checkout implementation. Do not import service.py,
        # instantiate ShortcutRepository, or start any serving/AD worker.
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(root / '02_BACKEND'))
        from lawrag.pipeline import shortcut_package
        from semantic_runtime.storage import Store
        from semantic_runtime.term_index import TermIndex
        from semantic_runtime.unit_fulltext import UnitFulltextIndex
        report['loaded_importer'] = str(Path(shortcut_package.__file__).resolve())
        if not Path(shortcut_package.__file__).resolve().is_relative_to((root / '02_BACKEND').resolve()):
            raise ValueError('Importer loaded outside the selected checkout')
        print('51문항·98근거 연결 검사 시작. 원문/색인 해시 검사에 시간이 걸릴 수 있습니다.', flush=True)
        store = Store(generation)
        index = fulltext = None
        try:
            index = TermIndex(generation / 'navigation', store)
            fulltext = UnitFulltextIndex(generation / 'fulltext', index.manifest)
            principal = shortcut_package.common_principal(store=store)
            binding, records = shortcut_package.resolve(read(package), store, principal)
            documents = {t['document_id'] for r in records for t in r['targets']}
            report['package_check'] = {'checked': True, 'cases': len(records),
                'source_entries': sum(len(r['targets']) for r in records),
                'documents': len(documents), 'binding': binding}
            if (len(records), report['package_check']['source_entries'], len(documents)) != (51, 98, 21):
                raise ValueError('CM case/source/document counts differ')
            if report['generation_manifest_sha256'] != fingerprint(manifest_path):
                raise ValueError('Selected manifest changed during inspection')
            store.check_unchanged()
        finally:
            for value in (fulltext, index, store):
                close = getattr(value, 'close', None)
                if close:
                    close()
        after = {p: fingerprint(root / p) if (root / p).is_file() else None for p in CODE_FILES}
        if after != report['code_files']:
            raise ValueError('Checkout changed during inspection')
        report['status'] = 'SOURCE_CONNECTION_CHECK_PASSED'
        print('51문항·98근거·21문서 연결 검사 통과. 등록·배포는 실행하지 않았습니다.', flush=True)
        return report, 0
    except Exception as exc:
        report.update(status='NEEDS_REVIEW', failed_type=type(exc).__name__, error=str(exc))
        with (output / 'ERROR.txt').open('x', encoding='utf-8') as stream:
            traceback.print_exc(file=stream)
        print('확인 중 중단되었습니다. 기존 코드·데이터·등록은 보존했습니다. ERROR.txt를 확인하세요.', flush=True)
        return report, 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--offline-generation', type=Path)
    p.add_argument('--offline-runtime', type=Path)
    a = p.parse_args()
    if bool(a.offline_generation) != bool(a.offline_runtime):
        p.error('Both offline paths are required')
    if a.offline_generation and not (a.output / '.offline-validation').is_file():
        p.error('Offline validation marker missing')
    report, code = inspect(a.root.resolve(), a.output.resolve(), a.package.resolve(),
        offline_generation=a.offline_generation, offline_runtime=a.offline_runtime)
    save(a.output / 'RESULT.json', report)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
