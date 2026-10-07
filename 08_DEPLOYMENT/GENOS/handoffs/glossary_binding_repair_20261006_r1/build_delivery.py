"""Restore exact verified compact reader in a new cumulative, immutable handoff."""
from pathlib import Path
import ast
import hashlib
import json
import zipfile

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_GLOSSARY_BINDING_REPAIR_20261006_R1'
PARENT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/relation_reading_20261006_r2'
REFERENCE = ROOT / '08_DEPLOYMENT/GENOS/handoffs/reference_build_20261003_r1/GENOS_REFERENCE_BUILD_20261003_R1.zip'
DEPLOY = ROOT / '09_ARTIFACTS/DELIVERIES/glossary_binding_repair_20261006_r1'
COMPILER = '02_BACKEND/semantic_runtime/full_glossary.py'
COMPACT = 'e03dab542ab0e1c9d129336308ddcdd0ab7a0ee1246fc29614f4efa12a8b4406'
LEGACY = 'ba2c6ced8da72307934e627a7a7508fb29da45e35d09fc3e0a116884a0a5d058'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    archive = OUT / (NAME + '.zip')
    if archive.exists() or DEPLOY.exists():
        raise FileExistsError('Preserve completed delivery; use a new revision')
    parent_zip = PARENT / 'GENOS_RELATION_READING_20261006_R2.zip'
    if sha(parent_zip.read_bytes()) != '78e4bbb83768b47d30628b5542070b75b11672c73d8967a07141be3c40a83ff7':
        raise ValueError('Parent ZIP changed')
    with zipfile.ZipFile(parent_zip) as z:
        parent = json.loads(z.read('CODE_MANIFEST.json'))
        payload = {r['path']: z.read(r['path']) for r in parent['files']}
        assert all(sha(payload[r['path']]) == r['sha256'] for r in parent['files'])
    with zipfile.ZipFile(REFERENCE) as z:
        compact = z.read(COMPILER)
    assert sha(compact) == COMPACT and sha(payload[COMPILER]) == LEGACY
    old = dict(payload)
    payload[COMPILER] = compact
    config = json.loads(payload['00_SYSTEM/PIPELINE.json'])
    touched = []
    for entry in config['engines'].values():
        name = entry['manifest']
        raw = payload.get(name)
        if raw is None:
            continue
        engine = json.loads(raw)
        if COMPILER not in engine['files']:
            continue
        assert engine['files'][COMPILER] == LEGACY
        engine['files'][COMPILER] = COMPACT
        payload[name] = encoded(engine)
        entry['sha256'] = sha(payload[name])
        touched.append(name)
    payload['00_SYSTEM/PIPELINE.json'] = encoded(config)
    rows = []
    for row in parent['files']:
        name = row['path']
        rows.append({**row, 'sha256': sha(payload[name]), 'bytes': len(payload[name]),
                     'allowed_predecessors': sorted({row['sha256'], *row.get('allowed_predecessors', [])})})
    manifest = {**parent, 'id': NAME, 'parent_code_zip_sha256': sha(parent_zip.read_bytes()),
                'scope': 'Restore exact reference R1 compact glossary reader; preserve relation R2 and AD R2; update only compiler-dependent engine pins',
                'files': rows, 'requires_rebuilt_generation': False,
                'expected_cache_compiler_sha256': COMPACT,
                'repaired_runtime_files': [COMPILER]}
    raw_manifest = encoded(manifest)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted({**payload, 'CODE_MANIFEST.json': raw_manifest}.items()):
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            if name.endswith('.py'):
                ast.parse(raw, feature_version=(3, 11))
            z.writestr(name, raw)
    script = (PARENT / 'GENOS_RELATION_READING_20261006_R2_APPLY.txt').read_text()
    script = script.replace('GENOS_RELATION_READING_20261006_R2', NAME)
    script = script.replace('relation-reading-r2-logs', 'glossary-binding-repair-r1-logs')
    script = script.replace('RELATION_READING_R2_EXIT', 'GLOSSARY_BINDING_REPAIR_EXIT')
    script = script.replace(sha(parent_zip.read_bytes()), sha(archive.read_bytes()))
    script = script.replace("'GENOS_AUTO_WARMUP':'0'", "'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'")
    script = script.replace("mode in ('verify','gate') and arg", "mode in ('check','apply','verify','gate') and arg")
    preflight = '''def cache_preflight(generation):
 source=json.loads((generation/'manifest.json').read_text())
 binding=source['glossary']
 cache=(generation/binding['cache']).resolve(strict=True);cache.relative_to(generation)
 receipt_path=(cache/binding['cache_receipt']).resolve(strict=True);receipt_path.relative_to(cache)
 if sha(receipt_path)!=binding['cache_receipt_sha256']:raise ValueError('Existing cache receipt hash mismatch; preserved')
 receipt=json.loads(receipt_path.read_text())
 if receipt['binding']['compiler_sha256']!=manifest['expected_cache_compiler_sha256']:
  raise ValueError('Cache requires another compiler; no code or data changed')
 bundle=(generation/binding['bundle']).resolve(strict=True);bundle.relative_to(generation)
 if sha(bundle/'manifest.json')!=binding['manifest_sha256'] or receipt['binding']['manifest_sha256']!=binding['manifest_sha256']:
  raise ValueError('Existing glossary manifest binding mismatch; preserved')
 print('EXISTING_CACHE_REPAIR_TARGET PASS',receipt['binding']['compiler_sha256'],flush=True)
'''
    assert script.count("if mode in ('check','apply'):") == 1
    script = script.replace("if mode in ('check','apply'):", preflight + "if mode in ('check','apply'):\n generation=selected();cache_preflight(generation)")
    needle = "if mode=='apply':pins(True)"
    assert script.count(needle) == 1
    script = script.replace(needle, "if mode=='apply':\n   pins(True)\n   cache_preflight(generation)\n   print('COMPACT_COMPILER_RESTORED',sha(root/'02_BACKEND/semantic_runtime/full_glossary.py'),flush=True)")
    needle = "pins(True);generation=selected();loader_check(generation)"
    assert script.count(needle) == 1
    script = script.replace(needle, "pins(True);generation=selected();cache_preflight(generation);loader_check(generation)")
    needle = " else:\n  subprocess.run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py')"
    assert script.count(needle) == 1
    script = script.replace(needle, "  subprocess.run([sys.executable,'-c',\"from lawrag.pipeline.term_serving_bundle import verify_assets; import sys; assert verify_assets(sys.argv[1])['verified'] is True; print('VERIFY_ASSETS PASS')\",str(generation)],cwd=root,env=env,check=True)\n else:\n  subprocess.run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py')")
    (OUT / (NAME + '_APPLY.txt')).write_text(script)
    (OUT / 'CODE_MANIFEST.json').write_bytes(raw_manifest)
    complete = ROOT / '09_ARTIFACTS/DELIVERIES/relation_reading_20261006_r2'
    for row in parent['required_files']:
        assert sha((complete / row['path']).read_bytes()) == row['sha256']
    for name, raw in {**{r['path']: (complete/r['path']).read_bytes() for r in parent['required_files']}, **payload}.items():
        target = DEPLOY / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    record = {'version': NAME, 'parent_zip_sha256': sha(parent_zip.read_bytes()),
              'code_zip_sha256': sha(archive.read_bytes()), 'code_manifest_sha256': sha(raw_manifest),
              'apply_txt_sha256': sha(script.encode()), 'deployment_checkout': str(DEPLOY),
              'runtime_change': COMPILER, 'restored_compiler_sha256': COMPACT,
              'engine_manifests_changed': touched, 'other_parent_source_bytes_preserved': True,
              'code_files': len(rows), 'required_files': len(parent['required_files']),
              'photo_generation': '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation',
              'genos_deployed': False, 'field_generation_gate': 'NOT_RUN', 'field_revision': None,
              'main_promotion': False, 'external_model_calls': 0}
    (OUT / 'HANDOFF.json').write_bytes(encoded(record))
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
