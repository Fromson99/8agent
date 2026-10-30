"""Build a Dataiku-only client from sealed R2, retaining checkpoint identity bytes."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.with_name('existing_nfs_transfer_20261029_r2')
PACKAGE = 'DATAIKU_EXISTING_NFS_CLIENT_20261030_R3.zip'
NOTEBOOK = 'DATAIKU_EXISTING_NFS_RUN_R3.txt'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def build():
    assert not (HERE / 'SEALED.json').exists(), 'Preserve sealed delivery'
    basezip = BASE / 'DATAIKU_EXISTING_NFS_CLIENT_20261029_R2.zip'
    assert sha(basezip.read_bytes()) == '42d54f39a3ebac42ba2df3838a8c67317e2e32951da5cfceb7db1259304ac503'
    with zipfile.ZipFile(basezip) as z:
        old = {n: z.read(n) for n in z.namelist()}
    assert all(sha(old[n]) == h for n, h in json.loads(old['PACKAGE_FILES.json']).items())
    files = dict(old)
    key = 'client/02_BACKEND/semantic_runtime/oracle_dp_io.py'
    text = files[key].decode()
    text = replace_once(text, '    for row in rows:\n        keybinds =',
        "    batch_size = getattr(sql.client, 'source_clob_batch_size', 1)\n"
        "    if batch_size != 1:\n"
        "        from .oracle_dp_batched_read import complete_rows\n"
        "        return complete_rows(sql, kind, rows, batch_size=batch_size)\n"
        "    for row in rows:\n        keybinds =")
    files[key] = text.encode()
    helper = 'client/02_BACKEND/semantic_runtime/oracle_dp_batched_read.py'
    files[helper] = (HERE / 'oracle_dp_batched_read.py').read_bytes()
    text = files['existing_client.py'].decode()
    text = replace_once(text, "CLIENT_REVISION = 'existing-nfs-20261029-r2'",
                        "CLIENT_REVISION = 'existing-nfs-20261030-r3'")
    text = replace_once(text, "def run(action='check'):", "def run(action='check', *, clob_batch_size=32):")
    text = replace_once(text, "    import dataiku\n", "    import dataiku\n"
                        "    if type(clob_batch_size) is not int or clob_batch_size not in (1, 32):\n"
                        "        raise ValueError('CLOB_BATCH_SIZE: use 1 or 32')\n")
    text = replace_once(text, '                    result = full.import_generation(BudgetClient(oracle, store), local,',
                        "                    budget = BudgetClient(oracle, store)\n"
                        "                    budget.source_clob_batch_size = clob_batch_size\n"
                        "                    print('CLOB_READ_BATCH_SIZE=' + str(clob_batch_size), flush=True)\n"
                        '                    result = full.import_generation(budget, local,')
    text = replace_once(text, "        archive = local / ('saved-' + field + '.zip')",
                        "        blob_hash = store.value[field]['sha256']\n"
                        "        if not isinstance(blob_hash, str) or len(blob_hash) != 64 or any(c not in '0123456789abcdef' for c in blob_hash):\n"
                        "            raise ValueError('NFS_RECEIPT_HASH')\n"
                        "        archive = local / ('saved-' + field + '-' + blob_hash + '.zip')")
    files['existing_client.py'] = text.encode()
    pins = json.loads(files['client/CODE_PINS.json'])
    pins['files'][helper[len('client/'):]] = sha(files[helper])
    for n in pins['files']:
        pins['files'][n] = sha(files['client/' + n])
    files['client/CODE_PINS.json'] = (json.dumps(pins, sort_keys=True, indent=2) + '\n').encode()
    files['PACKAGE_FILES.json'] = (json.dumps({n: sha(b) for n, b in files.items()
        if n != 'PACKAGE_FILES.json'}, sort_keys=True, indent=2) + '\n').encode()
    for path in ('client/02_BACKEND/lawrag/pipeline/oracle_full_package.py',
                 'client/02_BACKEND/lawrag/pipeline/oracle_migration.py',
                 'client/managed_job.py', 'client/physical_mapping.yaml', 'COMPUTE_CODE_SHA256.txt'):
        assert files[path] == old[path], path
    with zipfile.ZipFile(HERE / PACKAGE, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            if name.endswith('.py'):
                ast.parse(raw, feature_version=(3, 9))
            item = zipfile.ZipInfo(name, (2026, 10, 30, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            z.writestr(item, raw)
    notebook = (BASE / 'DATAIKU_EXISTING_NFS_RUN_R2.txt').read_text()
    notebook = notebook.replace(basezip.name, PACKAGE).replace(sha(basezip.read_bytes()), sha((HERE / PACKAGE).read_bytes()))
    notebook = re.sub(r'PACKAGE_BYTES = \d+', 'PACKAGE_BYTES = ' + str((HERE / PACKAGE).stat().st_size), notebook)
    notebook = replace_once(notebook, "LANDING_ID = 'ehA8dpVm'", "CLOB_BATCH_READS = 32  # 1이면 기존 직렬 조회로 같은 체크포인트에서 재개\nLANDING_ID = 'ehA8dpVm'")
    notebook = replace_once(notebook, "    'existing_client': 'existing_client.py',",
        "    'semantic_runtime.oracle_dp_io': 'client/02_BACKEND/semantic_runtime/oracle_dp_io.py',\n"
        "    'semantic_runtime.oracle_dp_batched_read': 'client/02_BACKEND/semantic_runtime/oracle_dp_batched_read.py',\n"
        "    'existing_client': 'existing_client.py',")
    notebook = notebook.replace('R1 코드가 커널에 남아 있습니다. Kernel > Restart 후 이 R2 셀만 실행하세요.',
                                '이전 코드가 커널에 남아 있습니다. 적재 종료를 확인한 뒤 Kernel > Restart 후 이 R3 셀만 실행하세요.')
    notebook = replace_once(notebook, 'NFS_RESULT = existing_client.run(ACTION)',
                            'NFS_RESULT = existing_client.run(ACTION, clob_batch_size=CLOB_BATCH_READS)')
    notebook = notebook.replace('# Restart the kernel when changing from R1; never run cached old modules.',
        '# R2 적재가 끝나거나 PAUSED인 것을 확인한 뒤 커널을 재시작하여 R3를 읽습니다.')
    ast.parse(notebook, feature_version=(3, 9))
    (HERE / NOTEBOOK).write_text(notebook)
    changed = [n for n, raw in files.items() if raw != old.get(n)]
    assert set(changed) == {key, helper, 'existing_client.py', 'client/CODE_PINS.json', 'PACKAGE_FILES.json'}
    report = dict(base_zip_sha256=sha(basezip.read_bytes()), changed_files=changed,
                  preserved_files=len(files)-len(changed), checkpoint_directory='oracle-import-r2',
                  checkpoint_identity_code_sha256=sha(files['client/02_BACKEND/lawrag/pipeline/oracle_full_package.py']),
                  main_changed=False, server_changed=False, field_verified=False,
                  files={n: dict(sha256=sha((HERE/n).read_bytes()), bytes=(HERE/n).stat().st_size)
                         for n in (PACKAGE, NOTEBOOK)})
    (HERE/'BUILD.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    (HERE/'CODE_MANIFEST.json').write_text(json.dumps({n: sha(b) for n,b in files.items()}, sort_keys=True, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    build()
