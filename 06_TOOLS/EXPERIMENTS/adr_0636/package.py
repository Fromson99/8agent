"""Rebind copied manifests to copied files, then freeze with the stable runner."""
import argparse
import subprocess
from common import ROOT, ADR, DESIGN, read, put, sha, candidate

def main(seal):
    runner = ROOT / '06_TOOLS/EXPERIMENTS/adr_0636/run.py'
    m = read(ADR / '실험/manifest.json'); cs = []
    paths = [ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', ROOT / '08_DEPLOYMENT/CONFIG/legal-source-export.json',
             ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
    for arm in ('baseline', 'guided'):
        cp = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0636' / ('v6-' + arm) / 'candidate.json'
        c = read(cp); snapshot = cp.parent / 'snapshot'
        if not c.get('revisions'):
            # The candidate registry excludes empty files; inert package markers
            # retain import semantics without changing production files.
            for f in snapshot.rglob('*'):
                if f.is_file() and f.stat().st_size == 0:
                    assert f.suffix in ('.py', '.sql')
                    f.write_text('# Empty package marker preserved in research snapshot.\n' if f.suffix == '.py' else '-- Empty SQL marker.\n')
            config = read(snapshot / '00_SYSTEM/PIPELINE.json')
            for engine in config['engines'].values():
                manifest = snapshot / engine['manifest']; value = read(manifest)
                value['files'] = {path: sha(snapshot / path) if (snapshot / path).is_file() else old
                                  for path, old in value['files'].items()}
                put(manifest, value); engine['sha256'] = sha(manifest)
            put(snapshot / '00_SYSTEM/PIPELINE.json', config)
            subprocess.run([str(ROOT / '.venv/bin/python'), str(ROOT / '06_TOOLS/run_tool.py'),
                            'adr_candidate.py', 'freeze', str(cp)], cwd=ROOT, check=True)
        subprocess.run([str(ROOT / '.venv/bin/python'), str(ROOT / '06_TOOLS/run_tool.py'),
                        'adr_candidate.py', 'validate', str(cp)], cwd=ROOT, check=True)
        cp, c, rev, snapshot = candidate(arm)
        cs.append({'candidate_id': c['candidate_id'], 'experiment_id': m['experiment_id'], 'arm_id': arm,
                   'run_ids': ['run-001'], 'manifest_path': str(cp.relative_to(ROOT)), 'manifest_sha256': sha(cp),
                   'revision_id': rev['revision_id'], 'revision_sha256': rev['revision_sha256'],
                   'runner_path': str(runner.relative_to(ROOT)), 'runner_sha256': sha(runner)})
        paths += [cp, *[ROOT / f['frozen_path'] for f in rev['files']]]
    m['design']['code_isolation'] = {'schema_version': 'adr-code-isolation-v1', 'mode': 'candidate_snapshot',
        'reason': None, 'production_paths_modified_before_decision': False, 'runtime_import_allowed': False,
        'production_registry_registered': False, 'main_wiring_unchanged': True, 'candidates': cs}
    put(ADR / '실험/manifest.json', m); put(DESIGN / 'pre-run-manifest.json', m)
    if seal:
        generation = ROOT / read(DESIGN / 'source-binding.json')['generation']
        paths += [*DESIGN.glob('*.json'), *(ROOT / '06_TOOLS/EXPERIMENTS/adr_0636').glob('*.py'),
                  generation / 'manifest.json', generation / 'store.sqlite', generation / 'navigation/manifest.json',
                  *list((generation / 'navigation').glob('*.sqlite')), generation / 'fulltext/manifest.json']
        put(DESIGN / 'freeze.json', {str(p.relative_to(ROOT)): sha(p) for p in set(paths) if p.name != 'freeze.json'})
        print('Sealed before external calls', flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--seal', action='store_true'); main(p.parse_args().seal)
