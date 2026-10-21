"""Read code inventory only; helper functions and sealed reference are embedded by build_delivery."""
import os
import platform
import re
import signal
import stat
import subprocess
import sys
from datetime import datetime, timezone


def read_code(root, name):
    # Do not read datasets, credentials, arbitrary absolute paths, or symlinks.
    p = PurePosixPath(name)
    allowed_roots = {'00_SYSTEM', '02_BACKEND', '03_FRONTEND', '05_TESTS', '06_TOOLS', '07_DOCS', '08_DEPLOYMENT', 'service'}
    if (len(p.parts) > 1 and p.parts[0] not in allowed_roots) or any(x.startswith('.') for x in p.parts):
        raise ValueError('NON_CODE_PATH_REFUSED: ' + name)
    if p.suffix.lower() not in {'.py', '.json', '.md', '.txt', '.html', '.css', '.sh', '.toml', '.yaml', '.yml', '.sql', '.ini'}:
        raise ValueError('NON_CODE_SUFFIX_REFUSED: ' + name)
    target = path_at(root, name)
    with target.open('rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16 * 1024 * 1024:
            raise ValueError('FILE_TYPE_OR_SIZE_REFUSED: ' + name)
        raw = handle.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('FILE_SIZE_REFUSED: ' + name)
    return raw


def deadline(_signum, _frame):
    raise TimeoutError('DIAGNOSTIC_DEADLINE_180_SECONDS')


def diagnose():
    output = Path(sys.argv[1])
    configured = Path(os.environ.get('GENOS_DEV_ROOT') or os.environ.get('GENOS_DEV') or str(Path.home() / 'DEV')).expanduser()
    report = {'schema_version': 'genos-code-inventory-diagnosis-v1', 'revision': DIAG_VERSION,
              'started_at': datetime.now(timezone.utc).isoformat(), 'complete': False,
              'configured_root': str(configured), 'python_executable': sys.executable,
              'python_version': platform.python_version(), 'reference_sha256': REFERENCE_SHA256,
              'code_modified': False, 'model_calls': 0, 'network_calls': 0,
              'generation_checked': False, 'serving_revision_checked': False,
              'files': [], 'issues': [], 'status': 'STARTED'}
    exit_code = 3
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(180)
    try:
        root = configured.resolve(strict=True)
        report['resolved_root'] = str(root)
        print('CHECKOUT_RESOLVED=' + str(root), flush=True)
        manifest_raw = read_code(root, 'CODE_MANIFEST.json')
        manifest = json.loads(manifest_raw)
        if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), list):
            raise ValueError('INVALID_CODE_MANIFEST_STRUCTURE')
        if len(manifest['files']) > 10000:
            raise ValueError('INVENTORY_SIZE_LIMIT')
        report['manifest_sha256'] = sha(manifest_raw)
        report['revisions'] = {}
        for key, value in manifest.items():
            if key in {'revision', 'schema_version'} and isinstance(value, str):
                report['revisions'][key] = value
            elif isinstance(value, dict) and isinstance(value.get('revision'), str):
                report['revisions'][key] = value['revision']
        print('REVISIONS=' + json.dumps(report['revisions'], ensure_ascii=False), flush=True)
        try:
            commit = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', 'HEAD'],
                                    capture_output=True, text=True, timeout=5, check=False)
            candidate = commit.stdout.strip()
            report['git_commit'] = candidate if commit.returncode == 0 and re.fullmatch(r'[0-9a-f]{40,64}', candidate) else None
        except (OSError, subprocess.TimeoutExpired):
            report['git_commit'] = None
        payload, names, total_bytes = {}, set(), 0
        for row in manifest['files']:
            if not isinstance(row, dict) or not isinstance(row.get('path'), str):
                raise ValueError('INVALID_INVENTORY_ROW')
            name = row['path']
            if name in names:
                raise ValueError('DUPLICATE_INVENTORY_PATH: ' + name)
            names.add(name)
            item = {'path': name, 'expected_sha256': row.get('sha256'), 'expected_bytes': row.get('bytes')}
            report['files'].append(item)
            try:
                raw = read_code(root, name)
            except (OSError, ValueError) as exc:
                item.update(status='READ_FAILED', error_type=type(exc).__name__)
                report['issues'].append({'kind': 'READ_FAILED', 'path': name, 'error_type': type(exc).__name__})
                continue
            total_bytes += len(raw)
            if total_bytes > 256 * 1024 * 1024:
                raise ValueError('TOTAL_CODE_SIZE_LIMIT')
            item.update(actual_sha256=sha(raw), actual_bytes=len(raw))
            item['status'] = 'MATCH' if item['actual_sha256'] == item['expected_sha256'] and len(raw) == item['expected_bytes'] else 'DRIFT'
            if item['status'] == 'DRIFT':
                report['issues'].append({'kind': 'CHECKOUT_DRIFT', 'path': name})
            payload[name] = raw
        report['inventory_files'] = len(names)
        if report['issues']:
            report['status'] = 'CHECKOUT_DRIFT_OR_UNREADABLE'
        else:
            try:
                report['engine_bindings'] = {'status': 'PASS', 'engines': verify_bindings(payload)}
            except (ValueError, KeyError, TypeError) as exc:
                report['engine_bindings'] = {'status': 'FAIL', 'error_type': type(exc).__name__}
                report['issues'].append({'kind': 'ENGINE_BINDING_FAILED'})
            state_key = signature(payload, manifest, REFERENCE)
            report['normalized_inventory_sha256'] = state_key
            report['manifest_files_sha256'] = sha(json.dumps({r['path']: r['sha256'] for r in manifest['files']}, sort_keys=True, separators=(',', ':')).encode())
            before_label = REFERENCE['inputs'].get(state_key)
            after_label = REFERENCE['outputs'].get(state_key)
            report['fact_reason_r1'] = {'supported_predecessor': before_label is not None,
                                      'recognized_output': after_label is not None,
                                      'matching_label': before_label or after_label,
                                      'known_predecessors': len(REFERENCE['inputs'])}
            report['status'] = ('ENGINE_BINDING_FAILED' if report['issues'] else
                                'KNOWN_PREDECESSOR' if before_label else
                                'KNOWN_FACT_REASON_OUTPUT' if after_label else 'UNSUPPORTED_INVENTORY')
        # Refuse a mixed snapshot if any manifest/code bytes changed while reading.
        changed = sha(read_code(root, 'CODE_MANIFEST.json')) != report['manifest_sha256']
        for name, raw in payload.items():
            try:
                changed = sha(read_code(root, name)) != sha(raw) or changed
            except (OSError, ValueError):
                changed = True
        if changed:
            report['status'] = 'CHECKOUT_CHANGED_DURING_DIAGNOSIS'
            report['issues'].append({'kind': 'UNSTABLE_SNAPSHOT'})
        report['complete'] = True
        exit_code = 0 if report['status'] in {'KNOWN_PREDECESSOR', 'KNOWN_FACT_REASON_OUTPUT'} else 2
    except (OSError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        report['status'] = 'DIAGNOSTIC_INCOMPLETE'
        # Keep bounded technical context; never include source text or JSON snippets.
        report['failure'] = {'type': type(exc).__name__}
        if isinstance(exc, OSError):
            report['failure']['errno'] = exc.errno
        elif not isinstance(exc, json.JSONDecodeError):
            report['failure']['detail'] = str(exc)[:500]
    finally:
        signal.alarm(0)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['exit_code'] = exit_code
        (output / 'DIAGNOSIS.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        summary = '\n'.join([
            'STATUS=' + report['status'], 'COMPLETE=' + str(report['complete']),
            'CHECKOUT=' + report.get('resolved_root', str(configured)),
            'CODE_MANIFEST_SHA256=' + report.get('manifest_sha256', 'UNAVAILABLE'),
            'INVENTORY_SHA256=' + report.get('normalized_inventory_sha256', 'UNAVAILABLE'),
            'REVISIONS=' + json.dumps(report.get('revisions', {}), ensure_ascii=False),
            'ISSUES=' + str(len(report['issues'])), 'CODE_MODIFIED=false',
            '진단 결과이며 설치 또는 배포 성공을 의미하지 않습니다.',
            'REPORT=' + str(output / 'DIAGNOSIS.json'),
        ]) + '\n'
        (output / 'SUMMARY.txt').write_text(summary, encoding='utf-8')
        print(summary, flush=True)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(diagnose())
