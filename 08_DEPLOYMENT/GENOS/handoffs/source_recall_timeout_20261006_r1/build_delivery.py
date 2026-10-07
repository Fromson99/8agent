"""Build a cumulative source-recall patch from the exact delivered R2/NFS bytes."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import zipfile

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
DEPLOY = ROOT/'09_ARTIFACTS/DELIVERIES/source_recall_timeout_20261006_r1'
NAME = 'GENOS_SOURCE_RECALL_TIMEOUT_20261006_R1'
PARENT = ROOT/'08_DEPLOYMENT/GENOS/handoffs/request_input_20261006_r2'
BASE = PARENT/'GENOS_V6_REQUEST_INPUT_20261006_R2.zip'
NFS = ROOT/'08_DEPLOYMENT/GENOS/handoffs/nfs_state_sqlite_20261006_r1/GENOS_NFS_STATE_SQLITE_20261006_R1.zip'
CHANGED = ['02_BACKEND/semantic_runtime/legal_agent/source_recall.py',
           '02_BACKEND/semantic_runtime/legal_agent/source_recall_global.py']
sha = lambda raw: hashlib.sha256(raw).hexdigest()
def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

with zipfile.ZipFile(BASE) as z:
    base_manifest = json.loads(z.read('CODE_MANIFEST.json'))
    base = {r['path']: z.read(r['path']) for r in base_manifest['files']}
    assert all(sha(base[r['path']]) == r['sha256'] for r in base_manifest['files'])
with zipfile.ZipFile(NFS) as z:
    nfs_manifest = json.loads(z.read('CODE_MANIFEST.json'))
    nfs = {r['path']: z.read(r['path']) for r in nfs_manifest['files']}
    assert all(sha(nfs[r['path']]) == r['sha256'] for r in nfs_manifest['files'])
prior = {**base, **nfs}
if not (OUT/'BASELINE_COMMIT.json').exists():
    for name, raw in sorted(prior.items()):
        target = DEPLOY/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    subprocess.run(['git', '-C', str(DEPLOY), 'add', '-f', '--', *sorted(prior)], check=True)
    # Preserve the delivered frozen bytes, including historical blank EOF lines.
    subprocess.run(['git', '-C', str(DEPLOY), '-c', 'core.whitespace=-blank-at-eof',
                    'diff', '--cached', '--check'], check=True)
    subprocess.run(['git', '-C', str(DEPLOY), 'commit', '-qm',
                    'Record previously delivered GENOS request-input R2 and NFS SQLite baseline'], check=True)
    write_json(OUT/'BASELINE_COMMIT.json', {'commit': subprocess.check_output(
        ['git','-C',str(DEPLOY),'rev-parse','HEAD'],text=True).strip(),
        'base_zip_sha256':sha(BASE.read_bytes()),'nfs_zip_sha256':sha(NFS.read_bytes())})

payload = {name:(ROOT/name).read_bytes() for name in CHANGED}
for name in CHANGED:
    old = prior[name].decode()
    expected = old.replace('ContractError, BudgetExhausted, DeadlineExceeded','ContractError, BudgetExhausted')
    expected = expected.replace("'wall_seconds': 120, ", '').replace(", 'wall_seconds':180", '')
    expected = expected.replace('        self.s.context.remaining()\n',
        '        # Source acquisition has no independent timer; the request owns its deadline.\n        self.s.context.remaining()\n')
    expected = expected.replace("        if time.monotonic() - self.start >= POLICY['wall_seconds']:\n            raise DeadlineExceeded('source recall policy time limit')\n",'')
    assert payload[name] == expected.encode(), 'Unexpected additional source changes: '+name
# Keep the previously delivered NFS change in this standalone cumulative patch.
payload.update({name:raw for name,raw in nfs.items() if name.startswith('02_BACKEND/semantic_runtime/')})
installer = '06_TOOLS/OFFLINE/genos_code_replace.py'
payload[installer] = prior[installer]
cfg_raw = prior['00_SYSTEM/PIPELINE.json'].decode()
cfg = json.loads(cfg_raw)
required = {}
manifests = []
for entry in cfg['engines'].values():
    name = entry['manifest']
    m = json.loads(prior[name])
    if not set(payload) & set(m['files']):
        continue
    for source in set(payload) & set(m['files']):
        m['files'][source] = sha(payload[source])
    raw = (json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode()
    payload[name] = raw
    cfg_raw = cfg_raw.replace('"'+entry['sha256']+'"','"'+sha(raw)+'"')
    manifests.append(name)
    required.update(m['files'])
payload['00_SYSTEM/PIPELINE.json'] = cfg_raw.encode()
required = {name:digest for name,digest in required.items() if name not in payload}
assert all(sha(prior[name]) == digest for name,digest in required.items())
rows = []
for name,raw in sorted(payload.items()):
    predecessors = sorted({sha(snapshot[name]) for snapshot in (base,prior) if name in snapshot})
    rows.append({'path':name,'sha256':sha(raw),'bytes':len(raw),
                 'allowed_predecessors':predecessors,'allow_missing_predecessor':name not in base})
manifest = {'format':'8agent-code/1','id':NAME,
    'parent_code_zip_sha256':sha(NFS.read_bytes()),
    'scope':'Remove source recall 120/180-second timers; retain request deadline; preserve NFS SQLite and compact reader',
    'files':rows,'required_files':[{'path':name,'sha256':digest} for name,digest in sorted(required.items())]}
archive = OUT/(NAME+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name,raw in sorted(payload.items()):
        assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
        z.writestr(name,raw)
    z.writestr('CODE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
write_json(OUT/'CODE_MANIFEST.json',manifest)
script = (PARENT/'GENOS_V6_REQUEST_INPUT_20261006_R2_APPLY.txt').read_text()
script = script.replace('GENOS_V6_REQUEST_INPUT_20261006_R2',NAME)
script = script.replace('request-input-logs','source-recall-timeout-logs').replace('REQUEST_INPUT_EXIT','SOURCE_RECALL_TIMEOUT_EXIT')
script = re.sub(r"if sha\(archive\)!='[0-9a-f]{64}'", "if sha(archive)!='"+sha(archive.read_bytes())+"'",script)
(OUT/(NAME+'_APPLY.txt')).write_text(script)
for name,raw in payload.items():
    target = DEPLOY/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(raw)
# Re-pin only the two changed sources in the user's working code; preserve all other edits.
working_before = OUT/'before-working'
working_receipt = []
working_cfg = (ROOT/'00_SYSTEM/PIPELINE.json').read_text()
for entry in json.loads(working_cfg)['engines'].values():
    path = ROOT/entry['manifest']
    old = path.read_bytes()
    m = json.loads(old)
    if not set(CHANGED) & set(m['files']):
        continue
    if not (working_before/entry['manifest']).exists():
        (working_before/entry['manifest']).parent.mkdir(parents=True,exist_ok=True)
        (working_before/entry['manifest']).write_bytes(old)
    for name in set(CHANGED) & set(m['files']):
        m['files'][name] = sha(payload[name])
    new = (json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode()
    path.write_bytes(new)
    working_cfg = working_cfg.replace('"'+entry['sha256']+'"','"'+sha(new)+'"')
    working_receipt.append({'manifest':entry['manifest'],'before':sha(old),'after':sha(new)})
if not (working_before/'00_SYSTEM/PIPELINE.json').exists():
    (working_before/'00_SYSTEM').mkdir(parents=True,exist_ok=True)
    (working_before/'00_SYSTEM/PIPELINE.json').write_bytes((ROOT/'00_SYSTEM/PIPELINE.json').read_bytes())
(ROOT/'00_SYSTEM/PIPELINE.json').write_text(working_cfg)
write_json(OUT/'WORKING_PIN_RECEIPT.json',working_receipt)
write_json(OUT/'HANDOFF.json',{
    'code_zip_sha256':sha(archive.read_bytes()),'code_manifest_sha256':sha((OUT/'CODE_MANIFEST.json').read_bytes()),
    'apply_txt_sha256':sha((OUT/(NAME+'_APPLY.txt')).read_bytes()),
    'deployment_checkout':str(DEPLOY),'changed_source':CHANGED,
    'code_files':len(payload),'required_files':len(required),
    'compact_reader_sha256':required['02_BACKEND/semantic_runtime/full_glossary.py'],
    'generation_candidate':'/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation',
    'generation_manifest_sha256':None,'field_commit':None,'field_revision':None,
    'genos_deployed':False,'routing_changed':False,'whole_request_deadline_removed':False})
print('Built',len(payload),'files;',len(required),'unchanged pins;',archive.name)
