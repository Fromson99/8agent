"""Repackage sealed R1 product bytes with a bounded schema collision repair."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import zlib

OUT = Path(__file__).resolve().parent
PRIOR = OUT.with_name('length_recovery_20261014_r1')
ROOT = OUT.parents[3]
NAME = 'GENOS_LENGTH_RECOVERY_20261015_R2'
SOURCE_COMMIT = '9b2b55f93320bc5a39732d8ae58ee3d92a2c0106'
SCHEMAS = ('00_SYSTEM/SCHEMAS/pipeline-v1.schema.json',
           '00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    assert not (OUT / (NAME + '.zip')).exists(), 'sealed delivery must not be overwritten'
    spec = json.loads(gzip.decompress((PRIOR / 'PATCH_SPEC.json.gz').read_bytes()))
    source = json.loads((PRIOR / 'SOURCE_BINDING.json').read_bytes())
    parent_manifest = json.loads((PRIOR / 'CODE_MANIFEST.json').read_bytes())
    for name in ('apply_patch.py', 'PATCH_SPEC.json.gz', 'SOURCE_BINDING.json'):
        row = next(r for r in parent_manifest['files'] if r['path'] == name)
        assert sha((PRIOR / name).read_bytes()) == row['sha256'], name
    spec['revision'] = NAME
    rules = {}
    evidence = []
    for name in SCHEMAS:
        historical = subprocess.run(['git', 'show', SOURCE_COMMIT + ':' + name],
                                    cwd=ROOT, capture_output=True, check=True).stdout
        target = (PRIOR / 'payload' / name).read_bytes()
        assert sha(target) == source['source_files'][name]
        for raw, origin in ((historical, {'git_commit': SOURCE_COMMIT, 'path': name}),
                            (target, {'sealed_delivery': 'GENOS_LENGTH_RECOVERY_20261014_R1', 'path': name})):
            json.loads(raw)
            digest = sha(raw)
            record = rules.setdefault(name, {}).setdefault(digest, {'bytes': len(raw), 'evidence': []})
            record['evidence'].append(origin)
            path = OUT / 'known-preimages' / digest
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(raw)
            evidence.append({'path': name, 'sha256': digest, 'bytes': len(raw), 'origin': origin})
    spec['unrecorded_schema_preimages'] = rules
    (OUT / 'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec), mtime=0))
    (OUT / 'SOURCE_BINDING.json').write_bytes(encoded({
        'revision': NAME, 'parent': 'GENOS_LENGTH_RECOVERY_20261014_R1',
        'parent_patch_spec_sha256': sha((PRIOR / 'PATCH_SPEC.json.gz').read_bytes()),
        'parent_source_binding_sha256': sha((PRIOR / 'SOURCE_BINDING.json').read_bytes()),
        'source_files': source['source_files'], 'field_variants': source['field_variants'],
        'known_predecessors': len(spec['signatures']), 'product_blobs_unchanged': True,
        'input_and_output_signatures_unchanged': True,
        'prerequisite': source['prerequisite'], 'schema_preimages': evidence,
        'field_status': 'NOT_VERIFIED',
    }))
    bundle = encoded({'code': base64.b64encode((OUT / 'apply_patch.py').read_bytes()).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    header = (PRIOR / 'GENOS_LENGTH_RECOVERY_20261014_R1_RUN.txt').read_text().split('python3 - "$@"', 1)[0]
    header = header.replace('length-recovery-r1', 'length-recovery-r2')
    header = header.replace('20261014_R1', '20261015_R2')
    launcher = ('import base64,hashlib,json,os,sys,types,zlib\n'
                f'raw=zlib.decompress(base64.b64decode({packed!r}))\n'
                f'assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
                "bundle=json.loads(raw);module=types.ModuleType('length_recovery_installer')\n"
                "exec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\n"
                "raise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
    run = OUT / (NAME + '_RUN.txt')
    run.write_text(header + 'python3 - "$@" <<\'LENGTH_RECOVERY_PY\'\n' + launcher + 'LENGTH_RECOVERY_PY\n')
    subprocess.run(['bash', '-n', str(run)], check=True)
    print(json.dumps({'revision': NAME, 'known_inventories': len(spec['signatures']),
                      'schema_rules': {n: len(v) for n, v in rules.items()}, 'run_bytes': run.stat().st_size}))


if __name__ == '__main__':
    main()
