"""Explicit, hash-checked research runner for the ADR-0531 storage candidate."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / '00_SYSTEM/WORKSPACE.json').is_file())


def frozen_revision(candidate):
    manifest = json.loads((candidate / 'candidate.json').read_text())
    revision = manifest['revisions'][-1]
    for row in revision['files']:
        path = ROOT / row['frozen_path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['snapshot_sha256']:
            raise SystemExit('frozen candidate drift: ' + str(path))
    return candidate / 'revisions' / revision['revision_id'] / 'snapshot'


def load_candidate():
    source = frozen_revision(ROOT / '02_BACKEND/lawrag/research/candidates/adr_0530/repaired')
    candidate = frozen_revision(ROOT / '02_BACKEND/lawrag/research/candidates/adr_0531/overlay')
    sys.path.insert(0, str(source / '02_BACKEND'))
    path = candidate / '02_BACKEND/lawrag/pipeline/reference_resolution.py'
    spec = importlib.util.spec_from_file_location('adr0531_research_overlay', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['build', 'probe'])
    parser.add_argument('--generation', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    module = load_candidate()
    if args.action == 'build':
        if args.output is None:
            parser.error('build requires --output')
        result = module.rebuild_research_overlay(args.generation, args.output)
    else:
        with module.closing(module.open_research_overlay(args.generation)) as db:
            result = {'source': db.execute('SELECT count(*) FROM source').fetchone()[0],
                      'reference': db.execute('SELECT count(*) FROM reference').fetchone()[0]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
