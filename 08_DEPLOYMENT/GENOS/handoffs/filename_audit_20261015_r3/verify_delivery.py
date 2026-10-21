"""Execute the sealed R3 using an immutable synthetic document-generation DB."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_FILENAME_AUDIT_20261015_R3'
spec = importlib.util.spec_from_file_location('delivery_tests', HERE / 'test_filename_audit.py')
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
audit = t.audit


def main():
    logs, checks = [], []
    examples = json.loads((HERE / 'EXAMPLE_INPUTS.json').read_text())['rows']
    with tempfile.TemporaryDirectory(prefix='filename-audit-r3-') as d:
        root = Path(d); code = root / 'workspace'; transfer = code / 'TRANSFER'; transfer.mkdir(parents=True)
        alias = root / 'DEV'; alias.symlink_to(code, target_is_directory=True)
        reports = transfer / 'FILENAME_AUDIT_RESULTS'
        bundle = transfer / NAME
        with zipfile.ZipFile(HERE / (NAME + '.zip')) as z:
            assert not any(Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
            z.extractall(bundle)
        for line in (bundle / 'SHA256SUMS.txt').read_text().splitlines():
            expected, relative = line.split('  ', 1)
            assert audit.sha(bundle / relative) == expected
        manifest = json.loads((bundle / 'CODE_MANIFEST.json').read_text())
        for item in manifest['required_files']:
            assert audit.sha(bundle / item['path']) == item['sha256'] == audit.sha(ROOT / item['source'])
        checks.append('final ZIP code matches workspace hashes; JS excluded; configurable JSON is a separate input')
        gen = t.fixture(root, [])
        db = sqlite3.connect(gen / 'store.sqlite')
        for r in examples:
            meta = {'source_category': 'internal', 'relative_path': r['path']}
            db.execute('INSERT INTO document VALUES(?,?,?,?)', (r['document_id'], r['filename'], 'a' * 64, json.dumps({'document_metadata': meta})))
            db.execute('INSERT INTO source_block VALUES(?)', (r['document_id'],))
        db.commit(); db.close()
        mpath = gen / 'manifest.json'; m = json.loads(mpath.read_text()); m['store_sha256'] = audit.sha(gen / 'store.sqlite')
        mpath.write_text(json.dumps(m))
        (code / '00_SYSTEM').mkdir(); (code / 'service.py').write_text('# preserved code\n')
        audit.write_json(code / '00_SYSTEM/GENOS_SERVING_PATHS.json', {'schema_version': 'genos-serving-paths-v1',
            'selection': 'operator-fixed', 'generation': str(gen), 'runtime': str(root / 'runtime'), 'generation_manifest_sha256': audit.sha(mpath)})
        snapshot = {str(p): audit.sha(p) for base in (gen, code) for p in base.rglob('*') if p.is_file() and not p.is_relative_to(transfer)}
        env = {**os.environ, 'PATH': str(ROOT / '.venv/bin') + ':' + os.environ['PATH'],
            'GENOS_DATA_ROOT': '/missing/stale', 'GENOS_GENERATION': '/missing/stale'}
        def run(label, txt, args, expected=0, cwd=None):
            command = ['bash', str(txt), *args]
            r = subprocess.run(command, cwd=cwd or transfer, env=env, capture_output=True, text=True)
            logs.append({'label': label, 'command': command, 'exit': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
            assert r.returncode == expected, (label, r.stdout, r.stderr)
            checks.append(label)
            return r
        def value(out): return json.loads((out / 'AUDIT.json').read_text())
        def pin(rows, title, stamp):
            family = [r for r in rows if r['title_key'] == audit.name_key(title)]
            assert [r['date'] for r in family if r['status'] == 'LATEST'] == [stamp]
        txt = bundle / (NAME + '_RUN.txt')
        config = bundle / 'FILENAME_EXCEPTIONS.json'; config_bytes = config.read_bytes()
        run('sealed TXT contract tests', txt, ['check'])
        run('default compare inside DEV/TRANSFER with sidecar exceptions', txt, ['compare', '--root', str(alias)])
        out = next(reports.iterdir()); first = value(out); rows = first['rows']
        assert first['summary']['status'] == 'COMPLETE'
        assert first['summary']['counts_by_location'] == {'OLDER': 2, 'LATEST': 10, 'EXCLUDED': 5, 'KEEP': 2}
        assert first['summary']['retained_locations'] == 12
        for title, stamp in [('대차업무준칙', '2026-05-04'), ('삼성POP골든랩 관리준칙', '2023-05'),
                ('인덱스북', '2026-05-29'), ('주식운용준칙', '2021-07-23'), ('투자리스크관리준칙', '2016-01-11')]: pin(rows, title, stamp)
        assert len({r['title_key'] for r in rows if 'futures-options-attachments' in r.get('exception_ids', [])}) == 3
        assert sum(r['status'] == 'KEEP' for r in rows) == 2
        assert first['summary']['binding']['exceptions']['sha256'] == audit.sha(config)
        assert (out / 'APPLIED_EXCEPTIONS.json').exists() and (out / 'EXCEPTION_CHANGES.csv').exists()
        checks.append('all named rules reflected in actual HTML/CSV/JSON; synthetic 19 inputs retain 12; month precision preserved')
        standalone = reports / 'standalone'
        run('standalone TXT uses its adjacent exceptions document', HERE / (NAME + '_RUN.txt'), ['compare', '--root', str(alias), '--output', str(standalone)])
        assert (standalone / 'RETAINED_INTERNAL.csv').read_bytes() == (out / 'RETAINED_INTERNAL.csv').read_bytes()
        run('repeat comparison preserves existing results', txt, ['compare', '--root', str(alias)])
        assert value(out) == first
        disabled = reports / 'disabled'
        run('disable all exceptions', txt, ['compare', '--root', str(alias), '--no-exceptions', '--output', str(disabled)])
        baseline = reports / 'r2-baseline'
        r2 = HERE.parent / 'filename_audit_20261015_r2/GENOS_FILENAME_AUDIT_20261015_R2_RUN.txt'
        run('sealed R2 baseline for disable-contract comparison', r2, ['compare', '--root', str(alias), '--output', str(baseline)])
        projection = lambda data: [{k: r[k] for k in ('filename', 'path', 'title', 'date', 'status', 'physical_exclusion_candidate')} for r in data['rows']]
        assert projection(value(disabled)) == projection(value(baseline))
        checks.append('no-exceptions reproduces sealed R2 filename decisions without any hidden document exceptions')
        run('existing output cannot be overwritten', txt, ['compare', '--root', str(alias), '--output', str(out)], 1)
        updated = json.loads(config_bytes)
        next(r for r in updated['rules'] if r['id'] == 'index-book-20260529')['date'] = '2020-01-01'
        config.write_text(json.dumps(updated, ensure_ascii=False))
        edit_out = reports / 'edited'
        run('editing the one JSON file changes only requested selection', txt, ['compare', '--root', str(alias), '--output', str(edit_out)])
        pin(value(edit_out)['rows'], '인덱스북', '2020-01-01')
        config.write_bytes(config_bytes)
        run('explicit missing exceptions file fails', txt, ['compare', '--root', str(alias), '--exceptions', str(root / 'missing.json')], 1)
        config.write_text('{}')
        run('invalid sidecar fails without silent fallback', txt, ['compare', '--root', str(alias)], 1)
        run('no-exceptions works despite invalid sidecar', txt, ['compare', '--root', str(alias), '--no-exceptions'])
        config.write_bytes(config_bytes)
        raw = root / 'raw'; raw.mkdir()
        for r in examples:
            if r['filename'] == '주식운용준칙_20210723.docx': continue
            target = raw / r['path']; target.parent.mkdir(parents=True, exist_ok=True); target.touch()
        missing = reports / 'missing-target'
        run('RAW compare reports missing selected target and protects singleton family', txt, ['compare', '--raw-root', str(raw), '--output', str(missing)])
        events = json.loads((missing / 'EXCEPTION_RESULTS.json').read_text())
        assert next(e for e in events if e['rule_id'] == 'equity-management-20210723')['status'] == 'TARGET_NOT_FOUND'
        assert next(r for r in value(missing)['rows'] if r['title'] == '주식운용준칙')['status'] == 'REVIEW'
        original = mpath.read_bytes(); mpath.write_text('{}')
        run('manifest mismatch remains a failure', txt, ['compare', '--root', str(alias)], 1)
        mpath.write_bytes(original)
        run('input directory output forbidden', txt, ['compare', '--root', str(alias), '--output', str(gen / 'report')], 1)
        run('arbitrary code directory output forbidden', txt, ['compare', '--root', str(alias), '--output', str(code / '02_BACKEND/report')], 1)
        assert not (gen / 'report').exists() and not (code / '02_BACKEND').exists()
        external = root / 'external-TRANSFER'; external.mkdir()
        run('external TRANSFER still supported', txt, ['compare', '--root', str(alias)], cwd=external)
        assert snapshot == {str(p): audit.sha(p) for base in (gen, code) for p in base.rglob('*') if p.is_file() and not p.is_relative_to(transfer)}
        checks.append('all original generation and DEV bytes preserved')
        db = sqlite3.connect(gen / 'store.sqlite'); db.execute("UPDATE document SET json='broken'"); db.commit(); db.close()
        failed = reports / 'corrupt'
        run('corrupt input cannot publish a completed report', txt, ['compare', '--root', str(alias), '--output', str(failed)], 1)
        assert json.loads((failed / 'RUN_STATUS.json').read_text())['status'] == 'FAILED' and not (failed / 'COMPARE.html').exists()
        run('apply action absent', txt, ['apply'], 2)
        exits = [p for base in (transfer, external) for p in (base / 'FILENAME_AUDIT_RUNS').glob('*/exit_status.txt')]
        assert len(exits) == len(logs)
        checks.append('all actual commands retain logs and exit status')
    previous = json.loads((HERE / 'PREVIOUS_HANDOFFS.json').read_text())
    for name, hashes in previous.items():
        folder = HERE.parent / name
        assert hashes == {str(p.relative_to(folder)): audit.sha(p) for p in folder.rglob('*') if p.is_file()}
    checks.append('R1 and R2 artifacts preserved byte for byte')
    validation = {'status': 'PASS', 'contract_tests': unittest.defaultTestLoader.loadTestsFromModule(t).countTestCases(),
        'actual_txt_commands': len(logs), 'checks': checks, 'scanner_sha256': audit.sha(ROOT / '06_TOOLS/OFFLINE/genos_filename_audit.py'),
        'exceptions_sha256': audit.sha(HERE / 'FILENAME_EXCEPTIONS.json'), 'code_manifest_sha256': audit.sha(HERE / 'CODE_MANIFEST.json'),
        'synthetic_inputs': 19, 'synthetic_retained': 12, 'field_inventory_result': 'NOT_AVAILABLE', 'field_genos_execution': 'NOT_RUN',
        'rag_applied': False, 'environment': 'WSL local synthetic generation; repository venv via python3',
        'limits': ['monthly revision has no invented day', 'exact title aliases only', 'singleton means one input filename in known parent folder',
                   'specified missing targets remain REVIEW', 'generation metadata only; no RAG activation']}
    (HERE / 'VALIDATION.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n')
    with gzip.open(HERE / 'TEST_TRANSCRIPT.json.gz', 'wt', encoding='utf-8') as f: json.dump(logs, f, ensure_ascii=False)
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
