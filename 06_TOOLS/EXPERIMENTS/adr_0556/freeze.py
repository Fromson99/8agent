"""Reuse immutable ADR0555 runtime bytes; authorize a fresh scoped model run."""
from pathlib import Path
import datetime, hashlib, json, os, shutil

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0556-pecab-qwen-authorized-routing'
OLD = R / '04_EXPERIMENTS/ADR/ADR-0555-pecab-only-catalogue-routing'
C = R / '02_BACKEND/lawrag/research/candidates/adr_0556/catalogue-router'

def read(p):
    return json.loads(p.read_text())

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        while chunk := f.read(8388608):
            h.update(chunk)
    return h.hexdigest()

def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def main():
    assert not (A / 'artifacts/frozen-design.json').exists()
    old = read(OLD / 'artifacts/frozen-design.json')
    fixture = read(A / 'product-cases.json')
    roots = {}
    paths = []
    for arm, previous in old['runtime_roots'].items():
        target = A / 'artifacts/sealed-runtime' / arm
        # Hard links are only for already immutable assets; neither run edits them.
        shutil.copytree(R / previous, target, copy_function=os.link,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        roots[arm] = str(target.relative_to(R))
        for name, expected in old['file_hashes'].items():
            if name.startswith(previous + '/'):
                p = target / Path(name).relative_to(previous)
                assert sha(p) == expected, name
                paths.append(p)
    policy = A / 'artifacts/scoped-model-policy.json'
    grant = dict(old['export_authorization'])
    grant.update(experiment_policy_path=str(policy.relative_to(R)),
                 policy_sha256=sha(policy),
                 basis='Same public sources and two immutable ADR0555 runtimes; fresh user-authorized scoped Qwen run with common authorization hook')
    assert set(grant['scope_document_ids']) == set(fixture['public_scope_document_ids'])
    assert grant['source_authorization_sha256'] == sha(R / '08_DEPLOYMENT/CONFIG/legal-source-export.json')
    gen = R / fixture['generation']
    assert grant['source_store_sha256'] == sha(gen / 'store.sqlite')
    assert grant['generation_id'] == read(gen / 'manifest.json')['generation_id']
    for doc in grant['document_provenance']:
        assert sha(R / '01_DATA/RAW' / doc['raw_relative_path']) == doc['raw_sha256']
    write(A / 'artifacts/export-rebinding.json', grant)
    rev = read(C / 'candidate.json')['revisions'][-1]
    transport = next(x['frozen_path'] for x in rev['files']
                     if x['frozen_path'].endswith('/experiment_client.py'))
    m = read(A / '실험/manifest.json')
    runner = Path(__file__).with_name('run_probe.py')
    m['design']['code_isolation']['candidates'] = [{
        'candidate_id': 'catalogue-router', 'experiment_id': m['experiment_id'],
        'arm_id': 'catalogue-router', 'run_ids': ['run-001'],
        'manifest_path': str((C / 'candidate.json').relative_to(R)),
        'manifest_sha256': sha(C / 'candidate.json'),
        'revision_id': rev['revision_id'], 'revision_sha256': rev['revision_sha256'],
        'runner_path': str(runner.relative_to(R)), 'runner_sha256': sha(runner)}]
    m['dataset'].update(frozen_source=str((A / 'product-cases.json').relative_to(R)),
                        sha256=sha(A / 'product-cases.json'))
    paths += [A / 'PLAN.md', A / 'product-cases.json', policy,
              A / 'artifacts/export-rebinding.json', C / 'candidate.json',
              R / '08_DEPLOYMENT/CONFIG/legal-source-export.json',
              R / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
              OLD / 'artifacts/frozen-design.json']
    paths += list(Path(__file__).parent.glob('*.py'))
    paths += [R / x['frozen_path'] for x in rev['files']]
    paths += [gen / x for x in ('manifest.json', 'navigation/manifest.json', 'fulltext/manifest.json')]
    paths += [R / x for x in old['historical_paths'].values()]
    design = {**old, 'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'runtime_roots': roots, 'transport_path': transport,
              'scope_authorization': read(policy)['authorization'],
              'export_authorization': grant, 'design': m['design'], 'runs': m['runs'],
              'file_hashes': {str(p.relative_to(R)): sha(p) for p in paths},
              'grader_only_hashes': {str((A / 'gold-cases.json').relative_to(R)): sha(A / 'gold-cases.json')},
              'runtime_derivation': {'source_design_path': str((OLD / 'artifacts/frozen-design.json').relative_to(R)),
                                     'source_design_sha256': sha(OLD / 'artifacts/frozen-design.json'),
                                     'runtime_bytes_changed': False,
                                     'common_change': 'Bind validate_authorization(context) before each external gateway send',
                                     'mutable_main_pointers_used': False}}
    write(A / 'artifacts/frozen-design.json', design)
    m['llm_policy']['experiment_override'] = {
        'schema_version': 'user-authorized-openrouter-product-v2',
        'policy_path': str(policy.relative_to(R)), 'policy_sha256': sha(policy),
        'frozen_design_path': str((A / 'artifacts/frozen-design.json').relative_to(R)),
        'frozen_design_sha256': sha(A / 'artifacts/frozen-design.json')}
    write(A / '실험/manifest.json', m)
    print('Frozen', len(paths), 'files; unchanged immutable runtimes; no MAIN pointer pin; zero model calls')

if __name__ == '__main__':
    main()
