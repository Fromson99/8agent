"""Merge immutable AD R2 and relation R1 handoffs; never rewrite working code."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
HANDOFFS = ROOT / '08_DEPLOYMENT/GENOS/handoffs'
NAME = 'GENOS_RELATION_READING_20261006_R2'
DEPLOY = ROOT / '09_ARTIFACTS/DELIVERIES/relation_reading_20261006_r2'
PARENTS = [HANDOFFS / value for value in (
    'request_input_20261006_r2/GENOS_V6_REQUEST_INPUT_20261006_R2.zip',
    'nfs_state_sqlite_20261006_r1/GENOS_NFS_STATE_SQLITE_20261006_R1.zip',
    'source_recall_timeout_20261006_r1/GENOS_SOURCE_RECALL_TIMEOUT_20261006_R1.zip',
    'source_recall_timeout_20261006_r2/GENOS_SOURCE_RECALL_TIMEOUT_20261006_R2.zip',
    'ad_language_20261006_r1/GENOS_AD_LANGUAGE_20261006_R1.zip',
    'ad_language_20261006_r2/GENOS_AD_LANGUAGE_20261006_R2.zip')]
RELATION = HANDOFFS / 'relation_reading_20261006_r1/GENOS_RELATION_READING_20261006_R1.zip'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def contents(path):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('CODE_MANIFEST.json'))
        result = {row['path']: archive.read(row['path']) for row in manifest['files']}
        assert all(sha(result[row['path']]) == row['sha256'] for row in manifest['files'])
        return manifest, result


snapshots = []; prior = {}; parents = []
for path in PARENTS:
    manifest, files = contents(path)
    prior = {**prior, **files}
    snapshots.append(prior)
    parents.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path.read_bytes())})
ad_manifest, ad = contents(PARENTS[-1])
relation_manifest, relation = contents(RELATION)
# Preserve all AD R2 bytes, including the newer ad_store. Both packages already
# contain exactly the same merged workflow (AD tables + READ log summaries).
workflow = '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
assert ad[workflow] == relation[workflow]
payload = {**relation, **ad}
config = json.loads(ad['00_SYSTEM/PIPELINE.json'])
helper = '02_BACKEND/semantic_runtime/legal_agent/relation_read_policy.py'
required = {row['path']: row['sha256'] for row in ad_manifest['required_files']}
for entry in config['engines'].values():
    name = entry['manifest']
    manifest = json.loads(prior[name])
    for source in manifest['files']:
        if source in payload:
            manifest['files'][source] = sha(payload[source])
    if '02_BACKEND/semantic_runtime/legal_agent/unit_relations.py' in manifest['files']:
        manifest['files'][helper] = sha(payload[helper])
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    if raw != prior[name] or name in payload:
        payload[name] = raw
    entry['sha256'] = sha(raw)
    required.update(manifest['files'])
payload['00_SYSTEM/PIPELINE.json'] = (json.dumps(config, ensure_ascii=False, indent=2) + '\n').encode()
required = {path: digest for path, digest in required.items() if path not in payload}
merged = {**prior, **payload}
assert all(sha(merged[path]) == digest for path, digest in required.items())
# Also recognize the known relation R1 installation, before/after AD R2.
snapshots += [{**snapshots[3], **relation}, {**snapshots[3], **relation, **ad}]
rows = [{'path': path, 'sha256': sha(raw), 'bytes': len(raw),
         'allowed_predecessors': sorted({sha(s[path]) for s in snapshots if path in s}),
         'allow_missing_predecessor': path not in snapshots[0]}
        for path, raw in sorted(payload.items())]
manifest = {'format': '8agent-code/1', 'id': NAME,
    'scope': 'Merge AD language R2 and relation reading R1; preserve AD model/context/table/store, typed directional reading and aggregated workflow logs',
    'parents': parents + [{'path': str(RELATION.relative_to(ROOT)), 'sha256': sha(RELATION.read_bytes())}],
    'files': rows,
    'required_files': [{'path': path, 'sha256': digest} for path, digest in sorted(required.items())]}
manifest_raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
archive = OUT / (NAME + '.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path, raw in sorted(payload.items()):
        assert Path(path).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
        z.writestr(path, raw)
    z.writestr('CODE_MANIFEST.json', manifest_raw)
(OUT / 'CODE_MANIFEST.json').write_bytes(manifest_raw)
script = (RELATION.parent / 'GENOS_RELATION_READING_20261006_R1_APPLY.txt').read_text()
script = script.replace('GENOS_RELATION_READING_20261006_R1', NAME)
script = script.replace('relation-reading-r1-logs', 'relation-reading-r2-logs')
script = script.replace('SOURCE_RECALL_TIMEOUT_EXIT', 'RELATION_READING_R2_EXIT')
script = re.sub(r"if sha\(archive\)!='[0-9a-f]{64}'", "if sha(archive)!='" + sha(archive.read_bytes()) + "'", script)
(OUT / (NAME + '_APPLY.txt')).write_text(script)
(OUT / (NAME + '_WORKFLOW_PYTHON.txt')).write_bytes(payload[workflow])
for path, raw in merged.items():
    target = DEPLOY / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
handoff = {'version': NAME, 'code_zip_sha256': sha(archive.read_bytes()),
    'code_manifest_sha256': sha(manifest_raw), 'deployment_checkout': str(DEPLOY),
    'apply_txt_sha256': sha((OUT / (NAME + '_APPLY.txt')).read_bytes()),
    'code_files': len(payload), 'required_files': len(required),
    'compact_reader_sha256': sha(merged['02_BACKEND/semantic_runtime/full_glossary.py']),
    'ad_r2_files_preserved': [path for path in ad if not '/ENGINES/' in path and path != '00_SYSTEM/PIPELINE.json'],
    'relation_r1_source_preserved': [path for path in relation if path.startswith('02_BACKEND/semantic_runtime/legal_agent/')],
    'policy_revision': 'relation-reading-policy-20261006-r1',
    'display_revision': 'reasoner-display-read-summary-20261006-r1',
    'generation_absolute_path': None, 'generation_manifest_sha256': None,
    'field_commit': None, 'field_revision': None, 'genos_deployed': False,
    'field_workflow_editor_updated': False, 'main_promotion': False,
    'external_model_calls': 0, 'validation_kind': 'Compatibility packaging and synthetic contracts; no experiment'}
(OUT / 'HANDOFF.json').write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + '\n')
print('Built', NAME, len(payload), 'files;', len(required), 'dependency pins; ZIP SHA256', sha(archive.read_bytes()))
