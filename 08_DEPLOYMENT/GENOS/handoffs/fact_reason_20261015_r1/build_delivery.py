"""Bind a one-line display patch to existing sealed field inventories."""
import ast
import base64
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zlib

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
NAME = 'GENOS_FACT_REASON_20261015_R1'
SOURCE = '02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'
OLD = 'b3fbe5f16b6322654b363e1487a38a0026bd6762aa70ca4bb89cb62d4cb2db08'
NEW = 'df86acfa871bbadc3d2fabdab6f8d1f9874a8e18a2b1cc6a84909914ca2e3fa9'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    assert not (OUT / (NAME + '.zip')).exists(), 'Preserve sealed delivery'
    current = (ROOT / SOURCE).read_bytes()
    assert sha(current) == NEW
    baseline = ROOT / '08_DEPLOYMENT/RELEASES/length-recovery-20261015-r1/code' / SOURCE
    previous = baseline.read_bytes()
    assert sha(previous) == OLD
    assert previous.replace('추가 사실 확인이 필요합니다'.encode(),
        '해당 사안에 적용할 결론을 하나로 확정하려면 추가 사실 정보가 필요합니다'.encode(), 1) == current
    ast.parse(current, feature_version=(3, 10))
    installer = load('fact_reason_installer', OUT / 'apply_patch.py')
    transform = load('fact_reason_repin', OUT.with_name('ad_request_logs_20261013_r1') / 'build_delivery.py')
    parent = load('fact_reason_parent', OUT.with_name('tool_availability_20261014_r1') / 'build_delivery.py')
    transitions = []
    for folder in ('tool_availability_20261014_r1', 'tool_recovery_20261014_r1', 'length_recovery_20261015_r2'):
        path = OUT.with_name(folder) / 'PATCH_SPEC.json.gz'
        transitions.append((folder, json.loads(gzip.decompress(path.read_bytes()))))
    spec = {'revision': NAME, 'signatures': {}, 'blobs': {NEW: base64.b64encode(current).decode()},
            'engine_additions': {}}
    seen = set()
    sources = {}

    def manifest_after(before, after, manifest):
        value = deepcopy(manifest)
        installer.rebind(value, {n: (sha(before[n]), sha(raw)) for n, raw in after.items()
                                if n in before and raw != before[n]})
        value['files'] = [{'path': n, 'sha256': sha(raw), 'bytes': len(raw)} for n, raw in sorted(after.items())]
        return value

    def include(label, payload, manifest):
        key = installer.signature(payload, manifest, spec)
        if key in seen:
            return
        seen.add(key)
        assert sha(payload[SOURCE]) == OLD, label
        installer.verify_bindings(payload)
        after = transform.repin(payload, {SOURCE: current}, {})
        installer.verify_bindings(after)
        allowed = {SOURCE, '00_SYSTEM/PIPELINE.json'} | {
            row['manifest'] for row in json.loads(payload['00_SYSTEM/PIPELINE.json'])['engines'].values()}
        changed = {n for n in after if after[n] != payload[n]}
        assert changed <= allowed and SOURCE in changed
        spec['signatures'][key] = {'label': label,
            'output_signature': installer.signature(after, manifest, spec),
            'patches': {SOURCE: {'before_sha256': OLD, 'after_sha256': NEW}}}
        if len(seen) % 200 == 0:
            print('Verified code inventories:', len(seen), flush=True)

    for label, payload, manifest, budget in parent.predecessors():
        spec['budget_policy'] = budget
        include(label, payload, manifest)
        for folder, transition in transitions:
            key = installer.signature(payload, manifest, transition)
            state = transition['signatures'].get(key)
            if state is None:
                continue
            updates = {n: base64.b64decode(transition['blobs'][row['after_sha256']])
                       for n, row in state['patches'].items()}
            after = transform.repin(payload, updates, transition.get('engine_additions', {}))
            assert installer.signature(after, manifest, transition) == state['output_signature']
            manifest = manifest_after(payload, after, manifest)
            payload = after
            label += '/' + folder
            include(label, payload, manifest)
    for folder, _ in transitions:
        sources[folder] = sha((OUT.with_name(folder) / 'PATCH_SPEC.json.gz').read_bytes())
    (OUT / 'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec), mtime=0))
    for folder, raw in (('payload', current), ('preimage', previous)):
        path = OUT / folder / SOURCE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    binding = {'revision': NAME, 'source_files': {SOURCE: NEW}, 'preimage_files': {SOURCE: OLD},
        'source_change': 'One deterministic MISSING_FACT display string', 'source_change_lines': 1,
        'known_predecessors': len(seen), 'verified_predecessor_spec_sha256': sources,
        'field_variants': {SOURCE: {OLD: NEW}}, 'existing_field_settings_preserved': True,
        'local_main_promoted': False, 'genos_field_status': 'NOT_VERIFIED'}
    (OUT / 'SOURCE_BINDING.json').write_bytes(encoded(binding))
    bundle = encoded({'code': base64.b64encode((OUT / 'apply_patch.py').read_bytes()).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    prior = OUT.with_name('length_recovery_20261015_r2')
    header = (prior / 'GENOS_LENGTH_RECOVERY_20261015_R2_RUN.txt').read_text().split('python3 - "$@"', 1)[0]
    header = header.replace('length-recovery-r2', 'fact-reason-r1').replace('LENGTH_RECOVERY', 'FACT_REASON')
    header = header.replace('8-agent-focused-rules-', '8-agent-fact-reason-')
    launcher = ('import base64,hashlib,json,os,sys,types,zlib\n'
        f'raw=zlib.decompress(base64.b64decode({packed!r}))\n'
        f'assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
        "bundle=json.loads(raw);module=types.ModuleType('fact_reason_installer')\n"
        "exec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\n"
        "raise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
    run = OUT / (NAME + '_RUN.txt')
    run.write_text(header + 'python3 - "$@" <<\'FACT_REASON_PY\'\n' + launcher + 'FACT_REASON_PY\n')
    subprocess.run(['bash', '-n', str(run)], check=True)
    print(json.dumps({'known_predecessors': len(seen), 'source_files': 1,
                      'source_sha256': NEW, 'run_bytes': run.stat().st_size}))


if __name__ == '__main__':
    main()
