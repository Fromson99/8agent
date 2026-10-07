"""Research-only v6 audit helpers; no operational activation."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0635-v6-multiturn-experience-reuse-audit'
DESIGN = ADR / 'artifacts/design'
RUN = ADR / 'artifacts/run-001'
ARMS = ('baseline', 'guided')

def read(path): return json.loads(Path(path).read_text())
def put(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n')
def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(8*1024*1024): h.update(chunk)
    return h.hexdigest()
def candidate(arm):
    path = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0635' / ('v6-'+arm) / 'candidate.json'
    value = read(path); revision = value['revisions'][-1]
    roots = set()
    for row in revision['files']:
        f = ROOT / row['frozen_path']
        assert sha(f) == row['snapshot_sha256'], str(f)
        roots.add(Path(str(f).split('/snapshot/', 1)[0])/'snapshot')
    assert len(roots) == 1
    return path, value, revision, roots.pop()
def verify_freeze():
    for path, digest in read(DESIGN/'freeze.json').items():
        assert sha(ROOT/path) == digest, path
def verify():
    b = read(DESIGN/'source-binding.json')
    assert sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json') == b['policy_sha256']
    assert sha(ROOT/'08_DEPLOYMENT/CONFIG/legal-source-export.json') == b['source_authorization_sha256']
    assert sha(ROOT/b['generation']/'manifest.json') == b['source_manifest_sha256']
    grant = read(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
    assert set(b['scope_document_ids']) == set(grant['public_document_ids'])
    assert read(ROOT/'08_DEPLOYMENT/CONFIG/legal-source-export.json')['enabled']
    return b
def check_payload(value, allowed):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('document_id','document_version_id') and isinstance(child,str):
                assert child in allowed, 'Non-public source in model payload'
            if key in ('document_ids','document_version_ids') and isinstance(child,list):
                assert set(child) <= allowed, 'Non-public scope in model payload'
            check_payload(child, allowed)
    elif isinstance(value,list):
        for child in value: check_payload(child, allowed)
