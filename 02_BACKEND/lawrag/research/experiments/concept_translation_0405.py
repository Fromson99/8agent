"""Explicit frozen glossary translate CLI injection; no production discovery."""
import hashlib
import importlib.util
import json
import runpy
import sys
from lawrag.platform.paths import repository_root
ROOT=repository_root()
BINDING=ROOT / '04_EXPERIMENTS/ADR/ADR-0405-glossary-korean-translation-db/artifacts/runner-binding.json'
EXPECTED='57114bb31c8f0b86f65d9e40f9282a98f6ad80296c3fdaecb06f539329e6d19f'

def load():
    if hashlib.sha256(BINDING.read_bytes()).hexdigest()!=EXPECTED:
        raise ValueError('Runner binding hash changed')
    binding=json.loads(BINDING.read_text())
    for item in binding['files']:
        if hashlib.sha256((ROOT/item['frozen_path']).read_bytes()).hexdigest()!=item['snapshot_sha256']:
            raise ValueError('Frozen revision changed')
    f=next(x for x in binding['files'] if x['frozen_path'].endswith('/concept_translation.py'))
    name='lawrag.pipeline.concept_translation'
    spec=importlib.util.spec_from_file_location(name,ROOT/f['frozen_path'])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module,binding

if __name__=='__main__':
    module,binding=load()
    cli=next(x for x in binding['files'] if x['frozen_path'].endswith('/06_TOOLS/pipeline.py'))
    sys.argv[0]=str(ROOT/cli['frozen_path'])
    runpy.run_path(sys.argv[0],run_name='__main__')
