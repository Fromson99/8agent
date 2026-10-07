"""Record the committed checkout and one selected generation after verification."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

import apply as installer
import gate


def main():
    root = Path(sys.argv[1]).expanduser().resolve(strict=True)
    spec = json.loads((installer.PATCH / 'PATCH_MANIFEST.json').read_bytes())
    changes = installer.prepare(root, spec)
    if any((root / name).read_bytes() != raw for name, raw in changes.items()):
        raise ValueError('patch not fully applied to this checkout')
    state = root / 'TRANSFER' / installer.PATCH_ID
    archive = state / 'applied-code.zip'
    code = gate.compare_zip_to_checkout(archive, root)
    print('CODE_CHECK PASS', json.dumps(code), flush=True)
    path = root / '06_TOOLS/COMMANDS/genos_generation_e2e.py'
    module_spec = importlib.util.spec_from_file_location('deployed_generation_selection', path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    gen = module.operator_generation(root).resolve(strict=True)
    raw = (gen / 'manifest.json').read_bytes()
    print('SELECTED_GENERATION', gen, flush=True)
    gate.check_generation(root, gen)
    if (gen / 'manifest.json').read_bytes() != raw or module.operator_generation(root).resolve(strict=True) != gen:
        raise ValueError('selected generation changed during verification')
    if gate.compare_zip_to_checkout(archive, root) != code:
        raise ValueError('deployment code changed during verification')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    receipt = {'patch': installer.PATCH_ID, 'status': 'PRE_DEPLOY_GATE_PASS', 'time': stamp,
               'code_root': str(root), 'push_checkout': str(root), 'commit': code['commit'],
               'applied_code_zip_sha256': code['code_zip_sha256'],
               'applied_code_manifest_sha256': code['code_manifest_sha256'],
               'runtime_files': {name: installer.sha((root / name).read_bytes()) for name in spec['files']},
               'generation': str(gen), 'generation_id': json.loads(raw).get('generation_id'),
               'generation_manifest_sha256': installer.sha(raw),
               'code_serving_revisions': {'risk_team': None, 'financial_team': None},
               'onsite_workflow_verified': False}
    target = state / ('gate-' + stamp + '.json')
    installer.atomic(target, installer.dump(receipt))
    installer.atomic(state / 'VERIFIED_CHECKOUT.json', installer.dump(receipt))
    print('GENOS_RELEASE_GATE PASS', json.dumps(receipt, ensure_ascii=False), flush=True)
    print('RECEIPT', target, flush=True)


if __name__ == '__main__':
    main()
