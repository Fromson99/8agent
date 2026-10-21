"""Offline artifacts launcher: leaves the running R3 checkout and batch untouched."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    args = sys.argv[1:]
    root = Path.home() / 'DEV'
    for i, arg in enumerate(args):
        if arg == '--root':
            root = Path(args[i + 1])
        elif arg.startswith('--root='):
            root = Path(arg.split('=', 1)[1])
    root = root.resolve(strict=True)
    spec = json.loads((HERE / 'CODE_REQUIREMENTS.json').read_text('utf-8'))
    for base, files in ((root, spec['checkout']), (HERE, spec['tool'])):
        for name, expected in files.items():
            path = base / name
            if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)) or sha(path) != expected:
                raise ValueError('CODE_GATE: verified R3 code required: ' + name)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(root / '02_BACKEND'), str(root)]
    os.environ.update(LAWRAG_WORKSPACE_ROOT=str(root), LAWRAG_TOOL_WORKSPACE_ROOT=str(root),
                      SOURCE_PROVIDER_PROJECT_ROOT=str(root), PYTHONDONTWRITEBYTECODE='1')
    module_spec = importlib.util.spec_from_file_location('_basis_batch_artifacts', HERE / 'basis_batch_artifacts.py')
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    print(json.dumps({'event': 'ARTIFACT_CODE_GATE_PASS', 'checkout': str(root),
                      'checkout_files': len(spec['checkout']), 'tool_sha256': sha(HERE / 'basis_batch_artifacts.py'),
                      'checkout_modified': False, 'model_calls': 0}), flush=True)
    return module.main([*args, '--kit', str(HERE)])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'event': 'BASIS_ARTIFACT_FAILED', 'error_type': type(exc).__name__,
                          'error_code': getattr(exc, 'code', None), 'message': str(exc)}, ensure_ascii=False), flush=True)
        traceback.print_exc()
        raise SystemExit(1)
