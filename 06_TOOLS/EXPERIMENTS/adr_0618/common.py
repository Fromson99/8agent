"""Research-only preparation and binding helpers, never serving defaults."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0618-unified-cm-guidance-two-failures'
DESIGN = ADR / 'artifacts/design'
RUN = ADR / 'artifacts/run-001'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk := f.read(8 * 1024 * 1024): h.update(chunk)
    return h.hexdigest()

def read(path): return json.loads(Path(path).read_text())

def put(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')

def verify(all_files=False):
    b = read(DESIGN / 'source-binding.json')
    p = read(ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    a = read(ROOT / '08_DEPLOYMENT/CONFIG/legal-source-export.json')
    g = read(ROOT / b['generation'] / 'manifest.json')
    assert a['enabled'] and sha(ROOT / '08_DEPLOYMENT/CONFIG/legal-source-export.json') == b['source_authorization_sha256']
    assert sha(ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json') == b['policy_sha256']
    assert p['model'] == b['model'] and p['endpoint'] == b['destination']
    assert b['public_questions_only'] and not b['private_documents_allowed']
    assert g['generation_id'] == b['generation_id'] and g['store_sha256'] == b['source_store_sha256']
    assert g['export_allowed'] is False
    assert any(set(b['scope_document_ids']) <= set(x['document_version_ids']) for x in a['bindings'])
    if all_files:
        assert sha(ROOT / b['generation'] / 'store.sqlite') == b['source_store_sha256']
    return b

def check_payload(value, allowed):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('document_id', 'document_version_id') and isinstance(child, str): assert child in allowed
            if key in ('document_ids', 'document_version_ids') and isinstance(child, list): assert set(child) <= allowed
            check_payload(child, allowed)
    elif isinstance(value, list):
        for child in value: check_payload(child, allowed)

def candidate(arm):
    path = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0618' / ('unified-' + arm) / 'candidate.json'
    c = read(path); revision = c['revisions'][-1]
    roots = []
    for row in revision['files']:
        f = ROOT / row['frozen_path']; assert sha(f) == row['snapshot_sha256']
        roots.append(Path(str(f).split('/snapshot/', 1)[0]) / 'snapshot')
    assert len(set(roots)) == 1
    return path, c, revision, roots[0]

def verify_freeze():
    for path, digest in read(DESIGN / 'freeze.json').items(): assert sha(ROOT / path) == digest, path
