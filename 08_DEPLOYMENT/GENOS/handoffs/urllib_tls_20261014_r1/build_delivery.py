"""Bind the existing urllib transport to exact, preserved GENOS field inventories."""
import ast
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zlib

O = Path(__file__).resolve().parent
R = O.parents[3]
N = 'GENOS_URLLIB_TLS_20261014_R1'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
enc = lambda value: (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def predecessors():
    old = load('tls_prior_builder', O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
    metrics = load('tls_metrics_builder', O.with_name('model_input_metrics_20261014_r1')/'build_delivery.py')
    parents = metrics.predecessor_tools()
    folder = O.with_name('model_input_metrics_20261014_r1')
    parents['metrics'] = (load('tls_metrics_installer', folder/'apply_patch.py'),
        json.loads(gzip.decompress((folder/'PATCH_SPEC.json.gz').read_bytes())))

    def patched(before, manifest, key):
        installer, spec = parents[key]
        state = spec['signatures'][installer.signature(before, manifest, spec)]
        updates = {n: base64.b64decode(spec['blobs'][row['after_sha256']])
            for n, row in state['patches'].items()}
        after = old.repin(before, updates, spec['engine_additions'])
        assert installer.signature(after, manifest, spec) == state['output_signature']
        return after

    for label, payload, budget in old.predecessors():
        base = dict(payload)
        manifest = json.loads(base.pop('CODE_MANIFEST.json'))
        ad = patched(base, manifest, 'ad')
        success = patched(ad, manifest, 'success')
        for tag, state in [('ad', ad), ('success', success)]:
            gap = patched(state, manifest, 'gap')
            for suffix, before in [('gap', gap), ('guidance', patched(gap, manifest, 'guidance'))]:
                yield label+'/'+tag+'/'+suffix, before, manifest, budget
                yield label+'/'+tag+'/'+suffix+'/metrics', patched(before, manifest, 'metrics'), manifest, budget


def main():
    assert not (O/(N+'.zip')).exists(), 'Preserve sealed handoff'
    old = load('tls_transform', O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
    installer = load('tls_installer', O/'apply_patch.py')
    names = ['02_BACKEND/semantic_runtime/'+n for n in
             ('genos.py', 'legal_agent/transport.py', 'stdlib_http.py')]
    source = {n: (R/n).read_bytes() for n in names}
    for n, raw in source.items():
        p = O/'payload'/n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    baseline = {
        names[0]: subprocess.check_output(['git', 'show', 'HEAD:'+names[0]], cwd=R),
        names[1]: (O.with_name('model_stream_fix_20261013_r1')/'payload'/names[1]).read_bytes(),
    }
    for n, raw in baseline.items():
        p = O/'preimage'/n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    spec = {'revision': N, 'signatures': {}, 'blobs': {}, 'engine_additions': {}}
    cache, variants, bindings = {}, {}, []
    for label, before, manifest, budget in predecessors():
        updates = {}
        for n in names:
            key = n, sha(before[n]) if n in before else None
            if key not in cache:
                raw = old.transform(before[n], baseline[n], source[n], n) if n in baseline else source[n]
                if n not in baseline:
                    assert n not in before, 'Unexpected existing helper'
                ast.parse(raw, feature_version=(3, 10))
                cache[key] = raw
            updates[n] = cache[key]
            spec['blobs'][sha(cache[key])] = base64.b64encode(cache[key]).decode()
            variants.setdefault(n, {})[key[1] or 'NEW'] = sha(cache[key])
        additions = {e['manifest']: [names[2]]
            for e in json.loads(before['00_SYSTEM/PIPELINE.json'])['engines'].values()
            if set(names[:2]) & set(json.loads(before[e['manifest']])['files'])}
        assert not spec['engine_additions'] or spec['engine_additions'] == additions
        spec['engine_additions'], spec['budget_policy'] = additions, budget
        after = old.repin(before, updates, additions)
        installer.verify_bindings(after)
        key, output = installer.signature(before, manifest, spec), installer.signature(after, manifest, spec)
        patches = {n: {'before_sha256': sha(before[n]) if n in before else None,
                       'after_sha256': sha(raw)} for n, raw in updates.items()}
        assert key not in spec['signatures']
        spec['signatures'][key] = {'label': label, 'patches': patches, 'output_signature': output}
        bindings.append({'label': label, 'input_signature': key, 'output_signature': output})
    for (n, _), raw in cache.items():
        p = O/'reviewed'/n/(sha(raw)+'.py')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    (O/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(enc(spec), mtime=0))
    (O/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(enc(bindings), mtime=0))
    (O/'SOURCE_BINDING.json').write_bytes(enc({'source_files': {n: sha(raw) for n, raw in source.items()},
        'field_variants': variants, 'known_predecessors': len(spec['signatures']),
        'engine_helper_pins': len(spec['engine_additions']),
        'local_active_release_changed': False, 'genos_field_status': 'NOT_VERIFIED',
        'baseline_git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip()}))
    code = (O/'apply_patch.py').read_bytes()
    bundle = enc({'code': base64.b64encode(code).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    py = 'import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
    py += "bundle=json.loads(raw);module=types.ModuleType('urllib_tls_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n"
    prior = O.with_name('assessment_gap_action_20261013_r2')/'GENOS_ASSESSMENT_GAP_ACTION_20261013_R2_RUN.txt'
    header = prior.read_text().split('python3 - "$@"', 1)[0]
    header = header.replace('assessment-gap-action-r2', 'urllib-tls-r1').replace('ASSESSMENT_GAP_ACTION', 'URLLIB_TLS')
    (O/(N+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'URLLIB_TLS_PY\'\n'+py+'URLLIB_TLS_PY\n')
    subprocess.run(['bash', '-n', str(O/(N+'_RUN.txt'))], check=True)
    print(json.dumps({'inventories': len(spec['signatures']), 'variants': {n: len(v) for n, v in variants.items()},
        'helper_pins': len(additions), 'run_bytes': (O/(N+'_RUN.txt')).stat().st_size}), flush=True)


if __name__ == '__main__':
    main()
