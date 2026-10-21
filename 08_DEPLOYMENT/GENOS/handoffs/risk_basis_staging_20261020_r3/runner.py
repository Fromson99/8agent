"""One offline launcher for fixed staging and the shared HTML/import workflow."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    args = sys.argv[1:]
    action = args[0] if args else 'inspect-fixed'
    rest = args[1:]
    root = Path.home() / 'DEV'
    for i, arg in enumerate(rest):
        if arg == '--root': root = Path(rest[i+1])
        elif arg.startswith('--root='): root = Path(arg.split('=',1)[1])
    root = root.resolve(strict=True)
    manifest = json.loads((HERE/'CODE_MANIFEST.json').read_text())
    for base, files in ((root, manifest['checkout']), (HERE, manifest['files'])):
        for name, expected in files.items():
            path = base/name
            if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('CODE_GATE: '+name)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(root/'02_BACKEND'), str(root)]
    os.environ.update(LAWRAG_WORKSPACE_ROOT=str(root), LAWRAG_TOOL_WORKSPACE_ROOT=str(root),
                      SOURCE_PROVIDER_PROJECT_ROOT=str(root), PYTHONDONTWRITEBYTECODE='1')
    import lawrag.pipeline
    common = HERE/'common'
    for name in ('basis_batch_candidates','basis_batch_artifacts'):
        load('lawrag.pipeline.'+name, common/(name+'.py'))
    artifacts = sys.modules['lawrag.pipeline.basis_batch_artifacts']
    print(json.dumps({'event':'FIXED_REVIEW_CODE_GATE_PASS','checkout':str(root),
                      'checkout_files':len(manifest['checkout']),'checkout_modified':False}),flush=True)
    if action in ('inspect-fixed','stage-fixed'):
        for name in ('risk_basis_seed','risk_basis_staging','risk_basis_seed_cli'):
            load('lawrag.pipeline.'+name, HERE/(name+'.py'))
        cli = sys.modules['lawrag.pipeline.risk_basis_seed_cli']
        return cli.main(['inspect' if action=='inspect-fixed' else 'stage', *rest])
    return artifacts.main([action,*rest,'--kit',str(common)])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'event':'FIXED_REVIEW_FAILED','type':type(exc).__name__,
                          'code':getattr(exc,'code',None),'message':str(exc)},ensure_ascii=False),flush=True)
        raise SystemExit(1)
