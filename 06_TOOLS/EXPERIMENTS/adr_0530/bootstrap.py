"""Run the hash-checked ADR-0528 candidate in isolation."""
import hashlib
import json
import pathlib
import sys

ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
            if (p / '00_SYSTEM/WORKSPACE.json').is_file())
CANDIDATE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0530/repaired'
manifest = json.loads((CANDIDATE / 'candidate.json').read_text())
revision = manifest['revisions'][-1]
revision_path = CANDIDATE / 'revisions' / revision['revision_id']
for row in revision['files']:
    path = ROOT / row['frozen_path']
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['snapshot_sha256']:
        raise SystemExit('Frozen code drift: ' + str(path))
sys.path.insert(0, str(revision_path / 'snapshot/02_BACKEND'))

if __name__ == '__main__':
    from lawrag.pipeline.reference_resolution import main
    raise SystemExit(main(sys.argv[1:]))
