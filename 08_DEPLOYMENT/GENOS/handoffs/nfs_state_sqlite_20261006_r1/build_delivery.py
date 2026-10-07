"""Build a storage-only patch against the previously delivered request-input R2."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

R = Path.cwd()
O = Path(__file__).resolve().parent
NAME = 'GENOS_NFS_STATE_SQLITE_20261006_R1'
PARENT = R / '08_DEPLOYMENT/GENOS/handoffs/request_input_20261006_r2'
BASE = PARENT / 'GENOS_V6_REQUEST_INPUT_20261006_R2.zip'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
changed = json.loads((O / 'WORKING_PIN_RECEIPT.json').read_text())['changed_source']
helper = '02_BACKEND/semantic_runtime/state_sqlite.py'
payload = {f: (R / f).read_bytes() for f in changed + [helper]}
with zipfile.ZipFile(BASE) as z:
    base_inventory = {r['path']: r for r in json.loads(z.read('CODE_MANIFEST.json'))['files']}
    cfg = json.loads(z.read('00_SYSTEM/PIPELINE.json'))
    original_cfg = z.read('00_SYSTEM/PIPELINE.json').decode()
    required = {}
    manifests = []
    for name, e in cfg['engines'].items():
        m = json.loads(z.read(e['manifest']))
        if not set(changed) & set(m['files']): continue
        for f in changed:
            if f in m['files']: m['files'][f] = sha(payload[f])
        m['files'][helper] = sha(payload[helper])
        m['files'] = dict(sorted(m['files'].items()))
        raw = (json.dumps(m, ensure_ascii=False, indent=2) + '\n').encode()
        payload[e['manifest']] = raw
        original_cfg = original_cfg.replace('"' + e['sha256'] + '"', '"' + sha(raw) + '"')
        manifests.append(e['manifest'])
        for f, digest in m['files'].items():
            if f not in payload and f not in changed and f != helper: required[f] = digest
    old = 'local durable disk; single writer service; explicit new generation migration'
    new = json.loads((R / '00_SYSTEM/PIPELINE.json').read_text())['shortcut_v4']['storage_contract']
    assert old in original_cfg
    payload['00_SYSTEM/PIPELINE.json'] = original_cfg.replace(old, new).encode()
    installer = '06_TOOLS/OFFLINE/genos_code_replace.py'
    payload[installer] = z.read(installer)
    required = {f: h for f, h in required.items() if f not in payload}
    rows = []
    for f, raw in sorted(payload.items()):
        old = base_inventory.get(f)
        rows.append({'path': f, 'sha256': sha(raw), 'bytes': len(raw),
                     'allowed_predecessors': [old['sha256']] if old else [],
                     'allow_missing_predecessor': old is None})
    inventory = {'format': '8agent-code/1', 'id': NAME,
                 'parent_code_zip_sha256': sha(BASE.read_bytes()),
                 'scope': 'shortcut/AD SQLite NFS rollback journaling; preserve R2 compact reader and all data',
                 'files': rows, 'required_files': [{'path': f, 'sha256': h} for f, h in sorted(required.items())]}
    # Preserve unchanged code pins, including the previously delivered compact glossary reader.
    for f, h in required.items(): assert sha(z.read(f)) == h, f
archive = O / (NAME + '.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for f, raw in sorted(payload.items()): z.writestr(f, raw)
    z.writestr('CODE_MANIFEST.json', json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
with zipfile.ZipFile(archive) as z:
    assert not any(Path(f).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'} for f in z.namelist())
(O / 'CODE_MANIFEST.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
script = (PARENT / 'GENOS_V6_REQUEST_INPUT_20261006_R2_APPLY.txt').read_text()
script = script.replace('GENOS_V6_REQUEST_INPUT_20261006_R2', NAME)
script = script.replace('request-input-logs', 'nfs-state-sqlite-logs').replace('REQUEST_INPUT_EXIT', 'NFS_STATE_SQLITE_EXIT')
script = re.sub(r"if sha\(archive\)!='[0-9a-f]{64}'", "if sha(archive)!='" + sha(archive.read_bytes()) + "'", script)
script = script.replace("elif mode in ('verify','gate'):", '''elif mode=='state-check':
 pins(True)
 import tempfile
 sys.path.insert(0,str(root/'02_BACKEND'))
 from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
 from semantic_runtime.legal_agent.shortcut_cases import ShortcutCases
 from semantic_runtime.ad_store import Store
 from semantic_runtime.ad_backend import Backend
 from semantic_runtime.state_sqlite import filesystem
 runtime=Path(os.environ.get('GENOS_RUNTIME_DIR','/nfs-root/diamo/8-agent/runtime'))
 if not runtime.is_absolute() or not runtime.is_dir():raise ValueError('Existing absolute runtime directory required')
 state=Path(os.environ.get('GENOS_STATE_DIR') or runtime)
 if not state.is_absolute() or not state.is_dir():raise ValueError('Existing absolute state directory required')
 probe=Path(tempfile.mkdtemp(prefix='.nfs-state-check-',dir=state))/'cases-v4.sqlite'
 cases=ShortcutCases(probe,None,None)
 try:
  expected='delete' if filesystem(probe) in ('nfs','nfs4','cifs','smb3') else (os.environ.get('GENOS_MEMORY_JOURNAL_MODE') or 'WAL').lower()
  assert cases.db.execute('PRAGMA journal_mode').fetchone()[0]==expected
  assert cases.db.execute('PRAGMA synchronous').fetchone()[0]==2
 finally:cases.close()
 store=Store(probe)
 try:
  Backend(store,'storage-check')
  with store.transaction():store.db.execute("INSERT INTO sw_scope VALUES('probe','test','test','storage-check',NULL)")
  assert store.db.execute('PRAGMA journal_mode').fetchone()[0]==expected
  assert store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 finally:store.close()
 print('SQLITE_STATE_CHECK PASS',probe,'FILESYSTEM='+filesystem(probe),'JOURNAL='+expected,'FIELD_DURABILITY=NOT_CERTIFIED',flush=True)
elif mode in ('verify','gate'):''')
script = script.replace('Modes: check apply verify gate rollback', 'Modes: check apply verify state-check gate rollback')
(O / (NAME + '_APPLY.txt')).write_text(script)
handoff = {'zip_sha256': sha(archive.read_bytes()), 'code_manifest_sha256': sha((O / 'CODE_MANIFEST.json').read_bytes()),
           'apply_txt_sha256': sha((O / (NAME + '_APPLY.txt')).read_bytes()), 'parent_zip_sha256': sha(BASE.read_bytes()),
           'changed_runtime': changed, 'new_runtime': helper, 'engine_manifests': manifests,
           'required_files': len(required), 'code_files': len(payload),
           'preserved_compact_reader_sha256': required['02_BACKEND/semantic_runtime/full_glossary.py'],
           'active_release_changed': False, 'genos_deployed': False, 'field_revision': None, 'field_commit': None}
(O / 'HANDOFF.json').write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + '\n')
print('Storage patch built:', len(payload), 'files;', len(required), 'pinned unchanged dependencies')
