"""Enumerate every sealed predecessor branch; preserve R1 source and decisions."""
import ast
import base64
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
PRIOR = OUT.with_name('fact_reason_20261015_r1')
NAME = 'GENOS_FACT_REASON_20261015_R2'
SOURCE = '02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'
FIELD = '7e3b5d20b21d33cd6e667896fdd023a9842b1c2d82dbef81892438e0b92b9686'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda v: (json.dumps(v, ensure_ascii=False, indent=2) + '\n').encode()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sealed_spec(folder):
    path = OUT.with_name(folder)
    manifest = json.loads((path / 'CODE_MANIFEST.json').read_bytes())
    raw = (path / 'PATCH_SPEC.json.gz').read_bytes()
    row = next(r for r in manifest['files'] if r['path'] == 'PATCH_SPEC.json.gz')
    assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
    return json.loads(gzip.decompress(raw)), sha(raw)


def main():
    assert not (OUT / (NAME + '.zip')).exists(), 'Preserve sealed delivery'
    old, old_hash = sealed_spec(PRIOR.name)
    spec = deepcopy(old)
    spec['revision'] = NAME
    source = (PRIOR / 'payload' / SOURCE).read_bytes()
    before_source = (PRIOR / 'preimage' / SOURCE).read_bytes()
    assert set(spec['blobs']) == {sha(source)}
    assert base64.b64decode(spec['blobs'][sha(source)]) == source
    installer = load('fact_r2_installer', OUT / 'apply_patch.py')
    transform = load('fact_r2_transform', OUT.with_name('ad_request_logs_20261013_r1') / 'build_delivery.py')
    parent = load('fact_r2_predecessors', OUT.with_name('tool_availability_20261014_r1') / 'build_delivery.py')
    transitions = {}
    source_specs = {}
    for folder in ('tool_availability_20261014_r1', 'tool_recovery_20261014_r1', 'length_recovery_20261015_r2'):
        transitions[folder], source_specs[folder] = sealed_spec(folder)
    visited = set()
    covered_edges = {name: set() for name in transitions}
    records = []
    fixtures = []

    def manifest_after(before, after, manifest):
        result = deepcopy(manifest)
        installer.rebind(result, {n: (sha(before[n]), sha(raw)) for n, raw in after.items()
                                 if n in before and raw != before[n]})
        result['files'] = [{'path': n, 'sha256': sha(raw), 'bytes': len(raw)} for n, raw in sorted(after.items())]
        return result

    def visit(label, payload, manifest):
        key = installer.signature(payload, manifest, spec)
        if key in visited:
            return
        visited.add(key)
        installer.verify_bindings(payload)
        assert sha(payload[SOURCE]) == sha(before_source), label
        after = transform.repin(payload, {SOURCE: source}, {})
        installer.verify_bindings(after)
        output = installer.signature(after, manifest, spec)
        allowed = {SOURCE, '00_SYSTEM/PIPELINE.json'} | {
            row['manifest'] for row in json.loads(payload['00_SYSTEM/PIPELINE.json'])['engines'].values()}
        assert {n for n in after if after[n] != payload[n]} <= allowed
        entry = {'label': label, 'output_signature': output,
                 'patches': {SOURCE: {'before_sha256': sha(before_source), 'after_sha256': sha(source)}}}
        if key in old['signatures']:
            assert old['signatures'][key]['output_signature'] == output
            assert old['signatures'][key]['patches'] == entry['patches']
        else:
            spec['signatures'][key] = entry
        records.append({'input_signature': key, 'output_signature': output,
                        'retained_r1': key in old['signatures'], 'label': label})
        if key == FIELD:
            # Reconstruct code bytes, not unknown field metadata. The screenshot
            # establishes this normalized inventory; generation/budget are tested separately.
            path = OUT / 'fixtures' / 'field-signature-predecessor.zip'
            path.parent.mkdir(exist_ok=True)
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                z.writestr('CODE_MANIFEST.json', encoded(manifest))
                for name, raw in sorted(payload.items()):
                    z.writestr(name, raw)
            fixtures.append({'kind': 'field_signature', 'path': str(path.relative_to(OUT)),
                             'sha256': sha(path.read_bytes()), 'inventory_sha256': key,
                             'label': label, 'field_metadata_reconstructed': True})
        # Every outgoing edge starts from this same predecessor. Never mutate
        # payload/manifest between siblings as the original linear loop did.
        for folder, transition in transitions.items():
            state = transition['signatures'].get(key)
            if state is None:
                continue
            covered_edges[folder].add(key)
            updates = {}
            for name, row in state['patches'].items():
                assert (sha(payload[name]) if name in payload else None) == row['before_sha256']
                raw = base64.b64decode(transition['blobs'][row['after_sha256']], validate=True)
                assert sha(raw) == row['after_sha256']
                updates[name] = raw
            child = transform.repin(payload, updates, transition.get('engine_additions', {}))
            assert installer.signature(child, manifest, transition) == state['output_signature']
            child_manifest = manifest_after(payload, child, manifest)
            visit(label + '/' + folder, child, child_manifest)
        if len(visited) % 250 == 0:
            print('Verified predecessor states:', len(visited), flush=True)

    for label, payload, manifest, budget in parent.predecessors():
        assert budget == spec['budget_policy']
        visit(label, payload, manifest)
    assert visited == set(spec['signatures'])
    assert len(visited) == 2310 and len(visited - set(old['signatures'])) == 660
    assert all(spec['signatures'][k] == v for k, v in old['signatures'].items())
    assert FIELD in visited and len(fixtures) == 1
    coverage = {}
    for folder, transition in transitions.items():
        assert covered_edges[folder] == set(transition['signatures']), folder
        outputs = {r['output_signature'] for r in transition['signatures'].values()}
        assert outputs <= visited
        coverage[folder] = {'inputs': len(covered_edges[folder]), 'outputs': len(outputs), 'missing_outputs': 0}
    old_fixture_dir = OUT.with_name('length_recovery_20261014_r1')
    fixture = json.loads((old_fixture_dir / 'FIXTURES.json').read_bytes())[0]
    raw = (old_fixture_dir / fixture['path']).read_bytes()
    assert sha(raw) == fixture['sha256']
    with zipfile.ZipFile(old_fixture_dir / fixture['path']) as z:
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        payload = {r['path']: z.read(r['path']) for r in manifest['files']}
    fixtures.append({'kind': 'schema_r3', 'path': '../' + old_fixture_dir.name + '/' + fixture['path'],
                     'sha256': fixture['sha256'], 'inventory_sha256': installer.signature(payload, manifest, spec)})
    for folder, raw in [('payload', source), ('preimage', before_source)]:
        path = OUT / folder / SOURCE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (OUT / 'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec), mtime=0))
    (OUT / 'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(encoded(records), mtime=0))
    (OUT / 'FIXTURES.json').write_bytes(encoded(fixtures))
    binding = {'revision': NAME, 'parent': old['revision'], 'parent_patch_spec_sha256': old_hash,
               'source_files': {SOURCE: sha(source)}, 'preimage_files': {SOURCE: sha(before_source)},
               'field_variants': {SOURCE: {sha(before_source): sha(source)}},
               'known_predecessors': len(visited), 'added_predecessors': 660,
               'original_1650_entries_unchanged': True, 'product_blob_identical_to_r1': True,
               'transition_specs_sha256': source_specs, 'transition_coverage': coverage,
               'field_inventory_sha256': FIELD, 'field_inventory_supported': True,
               'local_main_changed': False, 'genos_field_status': 'NOT_VERIFIED'}
    (OUT / 'SOURCE_BINDING.json').write_bytes(encoded(binding))
    bundle = encoded({'code': base64.b64encode((OUT / 'apply_patch.py').read_bytes()).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    header = (PRIOR / 'GENOS_FACT_REASON_20261015_R1_RUN.txt').read_text().split('python3 - "$@"', 1)[0]
    header = header.replace('fact-reason-r1', 'fact-reason-r2')
    py = ('import base64,hashlib,json,os,sys,types,zlib\n'
          f'raw=zlib.decompress(base64.b64decode({packed!r}))\n'
          f'assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
          "bundle=json.loads(raw);module=types.ModuleType('fact_reason_r2_installer')\n"
          "exec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\n"
          "raise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
    run = OUT / (NAME + '_RUN.txt')
    run.write_text(header + 'python3 - "$@" <<\'FACT_REASON_R2_PY\'\n' + py + 'FACT_REASON_R2_PY\n')
    subprocess.run(['bash', '-n', str(run)], check=True)
    print(json.dumps(binding, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
