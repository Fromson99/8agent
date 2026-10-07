"""Installer/launcher embedded in the reference MAIN TXT; no external models."""
import argparse
import ast
import base64
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zlib


PATCH = 'reference-main-20260929-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def atomic(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temporary = path.with_name('.' + path.name + '.reference-tmp')
    temporary.write_bytes(raw)
    temporary.chmod(mode)
    os.replace(temporary, path)


def replace_functions(raw, replacements):
    text = raw.decode('utf-8'); lines = text.splitlines(keepends=True)
    nodes = {n.name: n for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name, source in sorted(replacements.items(), key=lambda pair: nodes[pair[0]].lineno if pair[0] in nodes else -1, reverse=True):
        if name in nodes:
            node = nodes[name]
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)]) - 1
            lines[start:node.end_lineno] = [source.rstrip() + '\n']
        else:
            lines.extend(['\n\n', source.rstrip() + '\n'])
    result = ''.join(lines)
    for module in ('os', 'time', 'shutil'):
        if not any(isinstance(n, ast.Import) and any(a.name == module for a in n.names) for n in ast.parse(result).body):
            result = 'import ' + module + '\n' + result
    compile(result, '<reference patch>', 'exec')
    return result.encode()


def check_paths(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('unsafe patch member')
    if any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)):
        raise ValueError('symlink inside checkout: ' + relative)
    return path


def install(root, payload, receipt_root):
    spec = json.loads(zlib.decompress(base64.b64decode(payload)))
    if spec['patch'] != PATCH:
        raise ValueError('patch identity mismatch')
    sys.path.insert(0, str(root / '02_BACKEND'))
    from semantic_runtime.legal_agent.gateway import ModelGateway
    if not {'message_protocol', 'system', 'prompts'} <= set(inspect.signature(ModelGateway.__init__).parameters):
        raise ValueError('Existing GENOS v5 ModelGateway is required; no files applied')
    if 'term-navigation-index-v4' not in (root / '02_BACKEND/semantic_runtime/term_index.py').read_text():
        raise ValueError('Existing v4/v5 navigation reader is required; no files applied')
    import jsonschema
    jsonschema.Draft202012Validator.check_schema(json.loads(spec['files']['00_SYSTEM/SCHEMAS/reference-resolution-v1.schema.json']['text']))
    changes = {}
    for name, row in spec['files'].items():
        if Path(name).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}:
            raise ValueError('JavaScript member forbidden')
        raw = row['text'].encode()
        if sha(raw) != row['sha256']:
            raise ValueError('embedded source hash mismatch: ' + name)
        if name.endswith('.py'):
            ast.parse(raw.decode(), feature_version=(3, 11)); compile(raw, name, 'exec')
        changes[name] = raw
    for name, replacements in spec['functions'].items():
        existing = check_paths(root, name)
        if not existing.is_file():
            raise ValueError('Existing MAIN file required: ' + name)
        changes[name] = replace_functions(existing.read_bytes(), replacements)
    name = '02_BACKEND/semantic_runtime/term_references.py'
    existing = check_paths(root, name)
    changes[name] = replace_functions(existing.read_bytes(), {'reference_targets': spec['reference_targets']})
    name = '06_TOOLS/pipeline.py'
    text = check_paths(root, name).read_text()
    if 'from lawrag.pipeline.reference_resolution import main' not in text:
        nodes = ast.parse(text).body
        root_node = next(n for n in nodes if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'root' for t in n.targets))
        lines = text.splitlines(keepends=True)
        lines.insert(root_node.end_lineno, spec['pipeline_route'] + '\n')
        text = ''.join(lines)
    changes[name] = text.encode()
    # Refresh only engine pins that actually consume the changed source bytes.
    manifests = {}
    for file in (root / '02_BACKEND/ENGINES').rglob('*.json'):
        value = json.loads(file.read_text()); changed = False
        if isinstance(value.get('files'), dict):
            for name in set(value['files']) & set(changes):
                expected = sha(changes[name])
                if value['files'][name] != expected:
                    value['files'][name] = expected; changed = True
        if changed:
            name = str(file.relative_to(root))
            changes[name] = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
            manifests[name] = sha(changes[name])
    pipeline_path = root / '00_SYSTEM/PIPELINE.json'
    value = json.loads(pipeline_path.read_text()); changed = False
    for row in value.get('engines', {}).values():
        if row['manifest'] in manifests:
            row['sha256'] = manifests[row['manifest']]; changed = True
    if changed:
        changes['00_SYSTEM/PIPELINE.json'] = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    for name, raw in changes.items():
        check_paths(root, name)
        if name.endswith('.py'):
            ast.parse(raw.decode(), feature_version=(3, 11)); compile(raw, name, 'exec')
    changed_names = [name for name, raw in changes.items() if not (root / name).exists() or (root / name).read_bytes() != raw]
    if not changed_names:
        print('CODE_ALREADY_APPLIED files=' + str(len(changes)))
        return
    backup = receipt_root / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    backup.mkdir(parents=True)
    receipt = {'patch': PATCH, 'code_root': str(root), 'checkout_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
               'python': sys.version.split()[0], 'status': 'APPLYING', 'files': {}, 'code_serving_revision': None,
               'selected_generation': None, 'genos_verified': False, 'push_performed': False}
    for name in changed_names:
        target = root / name; original = target.read_bytes() if target.exists() else None
        if original is not None:
            saved = backup / 'before' / name; saved.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target, saved)
        receipt['files'][name] = {'before_sha256': sha(original) if original is not None else None,
                                  'after_sha256': sha(changes[name])}
    write_json(backup / 'receipt.json', receipt)
    try:
        for name in changed_names:
            atomic(root / name, changes[name])
        for name in changed_names:
            if sha((root / name).read_bytes()) != receipt['files'][name]['after_sha256']:
                raise ValueError('checkout file verification failed: ' + name)
        subprocess.run(['git', '-C', str(root), 'diff', '--check'], check=True)
        # Fresh process imports the APPLIED checkout, never a candidate extraction.
        subprocess.run([sys.executable, '-B', str(root / '06_TOOLS/pipeline.py'), 'reference-resolution', '--help'], check=True)
        subprocess.run([sys.executable, '-B', str(root / '06_TOOLS/pipeline.py'), 'document-release', '--help'], check=True)
        receipt['status'] = 'APPLIED_AND_IMPORT_VERIFIED'
    except BaseException:
        for name, row in receipt['files'].items():
            if row['before_sha256'] is None:
                (root / name).unlink(missing_ok=True)
            else:
                atomic(root / name, (backup / 'before' / name).read_bytes())
        receipt['status'] = 'FAILED_ROLLED_BACK'
        write_json(backup / 'receipt.json', receipt)
        raise
    write_json(backup / 'receipt.json', receipt)
    write_json(backup / 'CODE_MANIFEST.json', {'patch': PATCH, 'files': [{'path': n, 'sha256': sha((root/n).read_bytes())} for n in sorted(changes)]})
    print('CODE_APPLIED backup_receipt=' + str(backup / 'receipt.json'))


def profile(root):
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.core.llm import load_env
    from semantic_runtime.genos import from_env, advertised_model
    from semantic_runtime.legal_agent.transport import GenosTransport
    from lawrag.platform.workspace import load_layout
    load_env()
    target, configured = from_env('llm')
    model = advertised_model(target, configured)
    binding = {'provider': 'genos', 'trust_zone': 'internal', 'model': model,
               'adapter_version': 'genos-single-send-v1', 'endpoint_identity': sha(target.root.encode()),
               'max_input_bytes': 2000000}
    GenosTransport(target, binding).validate_model()
    runtime = load_layout(root).inspection_path('runtime', layout_version='v2')
    path = runtime / 'CONFIG' / ('reference-genos-' + sha(json.dumps(binding, sort_keys=True).encode())[:16] + '.json')
    value = {'schema_version': 'reference-model-profile-v1', 'model_binding': binding,
             'max_output_tokens': 4096, 'max_transport_retries': 0, 'max_schema_repairs': 0,
             'wall_seconds': 1800, 'approval_mode': 'automatic'}
    if path.exists() and json.loads(path.read_text()) != value:
        raise ValueError('Existing model profile changed; preserve it and use a new profile')
    if not path.exists():
        write_json(path, value)
    print('INTERNAL_MODEL_BOUND model=' + model + ' profile=' + str(path))
    return path, runtime


def generation(root, argument):
    if argument:
        selected = Path(argument).resolve()
    elif os.environ.get('GENOS_GENERATION'):
        selected = Path(os.environ['GENOS_GENERATION']).resolve()
    elif os.environ.get('GENOS_DATA_ROOT'):
        pointer = Path(os.environ['GENOS_DATA_ROOT']) / 'generations/CURRENT.json'
        value = json.loads(pointer.read_text())
        selected = Path(value['path']).resolve()
    else:
        raise ValueError('Supply the existing generation path: bash TXT run /actual/generation')
    if not (selected / 'manifest.json').is_file():
        raise ValueError('Selected generation manifest is missing')
    return selected


def rollback(root, receipt_file):
    receipt_file = Path(receipt_file).resolve(); receipt = json.loads(receipt_file.read_text())
    if receipt['code_root'] != str(root) or receipt['patch'] != PATCH:
        raise ValueError('Rollback receipt does not match this checkout')
    for name, row in receipt['files'].items():
        file = check_paths(root, name)
        if not file.exists() or sha(file.read_bytes()) != row['after_sha256']:
            raise ValueError('File changed since apply; preserve newer work: ' + name)
    for name, row in receipt['files'].items():
        if row['before_sha256'] is None:
            (root / name).unlink()
        else:
            raw = (receipt_file.parent / 'before' / name).read_bytes()
            if sha(raw) != row['before_sha256']:
                raise ValueError('Backup hash mismatch')
            atomic(root / name, raw)
    print('CODE_ROLLED_BACK; generated candidates and model journals preserved')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('mode', choices=['apply', 'all', 'build', 'run', 'status', 'rollback'])
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(); root = args.root.resolve()
    actual = Path(subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], text=True).strip()).resolve()
    if actual != root:
        raise ValueError('Use the actual Git root')
    os.environ['LAWRAG_WORKSPACE_ROOT'] = str(root)
    if sys.version_info < (3, 11):
        raise ValueError('GENOS codespace Python 3.11+ is required')
    receipt_root = root / '90_RUNTIME/HANDOFF' / PATCH
    receipt_root.mkdir(parents=True, exist_ok=True)
    with (receipt_root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.mode == 'rollback':
            if len(args.arguments) != 1: raise ValueError('rollback requires the apply receipt path')
            rollback(root, args.arguments[0]); return
        if args.mode == 'apply':
            install(root, args.payload.read_text(), receipt_root); return
        # Execution verifies that the payload is already applied, without rewriting it.
        spec = json.loads(zlib.decompress(base64.b64decode(args.payload.read_text())))
        for name, row in spec['files'].items():
            if sha((root / name).read_bytes()) != row['sha256']:
                raise ValueError('Run apply first; checkout source differs: ' + name)
        for name, replacements in spec['functions'].items():
            text = (root / name).read_text()
            nodes = {n.name: n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
            if any(k not in nodes or ast.get_source_segment(text, nodes[k]).strip() != v.strip() for k, v in replacements.items()):
                raise ValueError('Applied MAIN function differs; run apply first: ' + name)
        sys.path.insert(0, str(root / '02_BACKEND'))
        if args.mode in {'all', 'build'}:
            if not args.arguments: raise ValueError('Supply a run ID; reuse it only for the same pinned inputs')
            chosen, _ = profile(root)
            command = [sys.executable, '-B', str(root / '06_TOOLS/pipeline.py')]
            if args.mode == 'all':
                command += ['build-all', '--execute']
            else:
                command += ['document-release', 'build']
            command += ['--run-id', args.arguments[0], '--reference-model-profile', str(chosen), *args.arguments[1:]]
            raise SystemExit(subprocess.call(command, cwd=root))
        from lawrag.pipeline import reference_resolution as resolution
        from lawrag.pipeline.term_serving_bundle import verify_assets
        from lawrag.platform.workspace import load_layout
        from lawrag.core.llm import load_env
        load_env()
        selected = generation(root, args.arguments[0] if args.arguments else None)
        runtime = load_layout(root).inspection_path('runtime', layout_version='v2')
        manifest = json.loads((selected / 'manifest.json').read_text())
        key = sha((selected / 'manifest.json').read_bytes())[:16] + '-' + sha(Path(resolution.__file__).read_bytes())[:10]
        work = runtime / 'REFERENCE' / key; state = work / 'review'
        if args.mode == 'status':
            print(json.dumps(resolution.inspect(state), ensure_ascii=False, indent=2)); return
        chosen, _ = profile(root)
        result = resolution.advance(selected, state, chosen)
        write_json(work / 'stage-result.json', result)
        if not result['completed']:
            print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(3)
        output = work / 'candidate/generation'
        if not output.exists():
            applied = resolution.apply(state, selected, output)
            write_json(work / 'apply-result.json', applied)
        verified = verify_assets(output)
        write_json(work / 'RUN_RECEIPT.json', {'patch': PATCH, 'code_root': str(root),
                   'input_generation': str(selected), 'input_generation_manifest_sha256': sha((selected/'manifest.json').read_bytes()),
                   'output_generation': str(output), 'output_manifest_sha256': verified['manifest_sha256'],
                   'model_profile_sha256': sha(chosen.read_bytes()), 'approval_mode': 'automatic',
                   'activated': False, 'code_serving_revision': None})
        print('CANDIDATE_VERIFIED generation=' + str(output) + '; CURRENT and code-serving revision were not changed')


if __name__ == '__main__':
    main()
