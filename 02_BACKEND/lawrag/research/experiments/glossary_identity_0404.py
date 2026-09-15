"""Explicit frozen candidate injection; no runtime registry discovery."""
import importlib.util
import json
import runpy
import sys
from lawrag.platform.paths import repository_root

ROOT = repository_root()
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0404-glossary-id-concept-linking'


def load():
    import hashlib
    binding_path = ADR / 'artifacts/runner-binding.json'
    if hashlib.sha256(binding_path.read_bytes()).hexdigest() != '8ed24bfd76250a4fa173d6b19752f7860a706b4d99ca49c6c350d10046f14ead':
        raise ValueError('Runner binding drift')
    binding = json.loads(binding_path.read_text())
    for f in binding['files']:
        path = ROOT / f['frozen_path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != f['snapshot_sha256']:
            raise ValueError('Frozen candidate hash mismatch')
    f = next(f for f in binding['files'] if f['frozen_path'].endswith('/glossary_identity.py'))
    name = 'lawrag.pipeline.glossary_identity'
    spec = importlib.util.spec_from_file_location(name, ROOT / f['frozen_path'])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module, binding


if __name__ == '__main__':
    module, binding = load()
    if sys.argv[1:2] == ['model-review']:
        from lawrag.research.experiment_client import GeminiExperimentClient
        if len(sys.argv) != 3:
            raise ValueError('model-review requires exact state directory')
        state = ROOT / sys.argv[2]
        config = json.loads((state / 'config.json').read_text())
        client = GeminiExperimentClient(ROOT, state / 'model-calls', max_calls=config['max_calls'])
        print(module.encode(module.review(state, client)))
    else:
        cli = next(f for f in binding['files'] if f['frozen_path'].endswith('/06_TOOLS/pipeline.py'))
        sys.argv[0] = str(ROOT / cli['frozen_path'])
        runpy.run_path(sys.argv[0], run_name='__main__')
