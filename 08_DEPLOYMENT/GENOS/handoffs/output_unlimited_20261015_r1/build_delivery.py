"""Bind the requested GENOS output policy to sealed length-recovery inventories."""
import ast, base64, gzip, hashlib, importlib.util, json, subprocess, zlib
from copy import deepcopy
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
NAME = 'GENOS_OUTPUT_UNLIMITED_20261015_R1'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def main():
    assert not (OUT/(NAME+'.zip')).exists(), 'Preserve sealed deliveries'
    sources = json.loads((OUT/'WORKING_PREIMAGE.json').read_bytes())
    original = {n: (OUT/'preimage'/n).read_bytes() for n in sources}
    assert all(sha(original[n]) == digest for n, digest in sources.items())
    current = {n: (ROOT/n).read_bytes() for n in sources}
    for n, raw in current.items(): ast.parse(raw, filename=n, feature_version=(3, 10))
    installer = load('output_policy_installer', OUT/'apply_patch.py')
    transform = load('output_policy_transform', OUT.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
    parent = load('output_policy_parent', OUT.with_name('tool_availability_20261014_r1')/'build_delivery.py')
    folders = ('tool_availability_20261014_r1', 'tool_recovery_20261014_r1',
               'length_recovery_20261015_r2', 'fact_reason_20261015_r1')
    transitions = {f: json.loads(gzip.decompress((OUT.with_name(f)/'PATCH_SPEC.json.gz').read_bytes())) for f in folders}
    spec = {'revision': NAME, 'signatures': {}, 'blobs': {}, 'engine_additions': {}}
    variants = {}; cache = {}; seen = set()

    def advance(payload, manifest, transition):
        key = installer.signature(payload, manifest, transition)
        state = transition['signatures'].get(key)
        if state is None: return None
        updates = {n: base64.b64decode(transition['blobs'][r['after_sha256']]) for n, r in state['patches'].items()}
        after = transform.repin(payload, updates, transition.get('engine_additions', {}))
        assert installer.signature(after, manifest, transition) == state['output_signature']
        mf = deepcopy(manifest)
        installer.rebind(mf, {n: (sha(payload[n]), sha(raw)) for n, raw in after.items() if n in payload and raw != payload[n]})
        mf['files'] = [{'path': n, 'sha256': sha(raw), 'bytes': len(raw)} for n, raw in sorted(after.items())]
        return after, mf

    def include(label, payload, manifest):
        key = installer.signature(payload, manifest, spec)
        if key in seen: return
        seen.add(key); updates = {}
        for n, target in current.items():
            before = sha(payload[n]); identity = n, before
            if identity not in cache:
                raw = transform.transform(payload[n], original[n], target, n)
                ast.parse(raw, filename=n, feature_version=(3, 10)); cache[identity] = raw
            raw = cache[identity]; updates[n] = raw
            variants.setdefault(n, {})[before] = sha(raw)
            spec['blobs'][sha(raw)] = base64.b64encode(raw).decode()
        after = transform.repin(payload, updates, {})
        installer.verify_bindings(after)
        spec['signatures'][key] = {'label': label, 'output_signature': installer.signature(after, manifest, spec),
            'patches': {n: {'before_sha256': sha(payload[n]), 'after_sha256': sha(raw)} for n, raw in updates.items()}}
        if len(seen) % 100 == 0: print('Verified inventories:', len(seen), flush=True)

    def include_length_outputs(label, payload, manifest):
        state = advance(payload, manifest, transitions['length_recovery_20261015_r2'])
        if state is None: return
        payload, manifest = state; label += '/length-recovery-r2'
        include(label, payload, manifest)
        state = advance(payload, manifest, transitions['fact_reason_20261015_r1'])
        if state is not None: include(label+'/fact-reason-r1', *state)

    for label, payload, manifest, budget in parent.predecessors():
        spec['budget_policy'] = budget
        # Length R1/R2 itself is cumulative. Operators may apply it directly
        # or after either older tool patch; all approved paths must be covered.
        include_length_outputs(label, payload, manifest)
        for folder in folders[:2]:
            state = advance(payload, manifest, transitions[folder])
            if state is None: continue
            payload, manifest = state; label += '/'+folder
            include_length_outputs(label, payload, manifest)
    assert seen and all(variants.values())
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec), mtime=0))
    for n, raw in current.items():
        path = OUT/'payload'/n; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    binding = {'revision': NAME, 'source_files': {n: sha(raw) for n, raw in current.items()},
        'preimage_files': sources, 'field_variants': variants, 'known_predecessors': len(seen),
        'verified_predecessor_spec_sha256': {f: sha((OUT.with_name(f)/'PATCH_SPEC.json.gz').read_bytes()) for f in folders},
        'prerequisite': 'LENGTH_RECOVERY R1 or R2; optional FACT_REASON R1 preserved',
        'scope': 'GENOS RAG and AD output length only; model server owns its limits',
        'preserved': ['field display/shortcut/wiki policy', 'time and total call budgets', 'data generation', 'failure/permission/hash/publication checks'],
        'local_main_promoted': False, 'genos_field_status': 'NOT_VERIFIED'}
    (OUT/'SOURCE_BINDING.json').write_bytes(encoded(binding))
    bundle = encoded({'code': base64.b64encode((OUT/'apply_patch.py').read_bytes()).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    prior = OUT.with_name('fact_reason_20261015_r1')/'GENOS_FACT_REASON_20261015_R1_RUN.txt'
    header = prior.read_text().split('python3 - "$@"', 1)[0].replace('fact-reason-r1', 'output-unlimited-r1').replace('FACT_REASON', 'OUTPUT_UNLIMITED')
    launcher = ('import base64,hashlib,json,os,sys,types,zlib\n'
        f'raw=zlib.decompress(base64.b64decode({packed!r}))\n'
        f'assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
        "bundle=json.loads(raw);module=types.ModuleType('output_unlimited_installer')\n"
        "exec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\n"
        "raise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
    run = OUT/(NAME+'_RUN.txt'); run.write_text(header+'python3 - "$@" <<\'OUTPUT_UNLIMITED_PY\'\n'+launcher+'OUTPUT_UNLIMITED_PY\n')
    subprocess.run(['bash', '-n', str(run)], check=True)
    print(json.dumps({'known_predecessors': len(seen), 'source_files': len(sources), 'field_variant_counts': {n: len(v) for n, v in variants.items()}, 'run_bytes': run.stat().st_size}), flush=True)


if __name__ == '__main__': main()
