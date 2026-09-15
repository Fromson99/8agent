"""Explicit frozen language repair; never registry discovery."""
import hashlib,importlib.util,json,runpy,sys
from lawrag.platform.paths import repository_root
ROOT=repository_root()
BINDING=ROOT/'04_EXPERIMENTS/ADR/ADR-0406-glossary-translation-language-repair/artifacts/runner-binding.json'
EXPECTED='95c907d9707402468bcb71f5a7c1d3a8579b655f6d853ebd563b9054dfe856a8'

def load():
    if hashlib.sha256(BINDING.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('Binding changed')
    binding=json.loads(BINDING.read_text())
    for f in binding['files']:
        if hashlib.sha256((ROOT/f['frozen_path']).read_bytes()).hexdigest()!=f['snapshot_sha256']:raise ValueError('Frozen code changed')
    f=next(x for x in binding['files'] if x['frozen_path'].endswith('/concept_translation_repair.py'))
    name='lawrag.pipeline.concept_translation_repair';spec=importlib.util.spec_from_file_location(name,ROOT/f['frozen_path'])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module,binding

if __name__=='__main__':
    module,binding=load()
    cli=next(x for x in binding['files'] if x['frozen_path'].endswith('/06_TOOLS/pipeline.py'))
    sys.argv[0]=str(ROOT/cli['frozen_path']);runpy.run_path(sys.argv[0],run_name='__main__')
