#!/usr/bin/env python3
"""Use the installed legacy or audited navigation contract, keeping R1/R2 bytes."""
from contextlib import contextmanager
import ast
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import threading
import time

_spec = importlib.util.spec_from_file_location(
    'genos_meaning_recovery_r2_base', Path(__file__).with_name('genos_meaning_recover_r2.py'))
r2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r2)
base = r2.base
VERSION = 'genos-meaning-recovery-20261002-r3'


def storage_module():
    try:
        return importlib.import_module('semantic_runtime.navigation_storage')
    except ModuleNotFoundError as error:
        if error.name != 'semantic_runtime.navigation_storage':
            raise
        return None


def required_dependencies():
    required = {
        'semantic_runtime.storage': ('Store',),
        'semantic_runtime.term_index': ('TermIndex',),
        'semantic_runtime.fulltext': ('FulltextIndex', 'build'),
        'semantic_runtime.navigation_agent': ('glossary_assets',),
        'lawrag.pipeline.glossary_knowledge': ('selected_for', 'verify'),
        'lawrag.pipeline.term_serving_bundle': ('verify_assets',),
        'lawrag.pipeline.document_release': ('_verify_navigation_audit', '_copy_reference_audit'),
        'lawrag.pipeline.term_generation': ('build_generation',),
    }
    evidence = {}
    for name, functions in required.items():
        module = importlib.import_module(name)
        for function in functions:
            if not callable(getattr(module, function, None)):
                raise RuntimeError('Missing field recovery capability: ' + name + '.' + function)
        path = str(Path(module.__file__).resolve(strict=True))
        evidence[name] = {'path': path, 'sha256': base.sha(path), 'callables': list(functions)}
    optional = storage_module()
    if optional is not None:
        for function in ('verify_audit', 'verify_build'):
            if not callable(getattr(optional, function, None)):
                raise RuntimeError('Incomplete field navigation audit module: ' + function)
        evidence[optional.__name__] = {'path': str(Path(optional.__file__).resolve()),
                                     'sha256': base.sha(optional.__file__)}
    return evidence, optional


def legacy_compatible_verifier():
    """Move ONLY R1's optional audit import into its existing storage branch.

    All native source, scope, links, TermIndex, dictionary and audit assertions
    remain identical. Missing audit support still fails for a split index.
    """
    tree = ast.parse(inspect.getsource(base.verify_stage))
    function = tree.body[0]
    imports = [node for node in function.body if isinstance(node, ast.ImportFrom)
               and node.module == 'semantic_runtime' and len(node.names) == 1
               and node.names[0].name == 'navigation_storage']
    branches = [node for node in function.body if isinstance(node, ast.If)
                and ast.dump(node.test) == ast.dump(ast.parse("index.get('storage')", mode='eval').body)]
    if len(imports) != 1 or len(branches) != 1:
        raise RuntimeError('Unsupported R1 verifier layout; no validation rewrite')
    function.body.remove(imports[0])
    branches[0].body.insert(0, imports[0])
    namespace = dict(vars(base))
    exec(compile(ast.fix_missing_locations(tree), base.__file__, 'exec'), namespace)
    return namespace['verify_stage']


@contextmanager
def phase(label):
    started = time.monotonic()
    stop = threading.Event()
    base.log(label + ' START')
    def heartbeat():
        while not stop.wait(30):
            base.log(label + ' RUNNING elapsed=' + str(round(time.monotonic() - started, 1)) + 's')
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)
        base.log(label + ' END elapsed=' + str(round(time.monotonic() - started, 1)) + 's')


def check_field(context):
    modules, storage = required_dependencies()
    indexes = []
    parent = context['parent'] / 'meaning-variants'
    for mode in ('off', 'on'):
        output = parent / mode
        builds = [output / 'baseline', output / 'serving', *sorted(output.glob('.baseline-*'))]
        for build in builds:
            path = build / 'generation/navigation/manifest.json'
            if not path.is_file():
                continue
            try:
                index = base.read(path)
            except (ValueError, UnicodeError):
                indexes.append({'path': str(path), 'format': 'unreadable-preserved'})
                continue
            split = bool(index.get('storage'))
            if split and storage is None:
                raise RuntimeError('Split navigation requires semantic_runtime.navigation_storage; '
                                   'audit validation cannot be skipped; preserved: ' + str(path))
            indexes.append({'path': str(path), 'sha256': base.sha(path),
                            'format': 'split-audit' if split else 'monolithic',
                            'schema_version': index.get('schema_version')})
    base.log('CAPABILITIES required imports/callables PASS; navigation audit module=' +
             ('present' if storage else 'absent; monolithic native verification supported'))
    return {'schema_version': VERSION, 'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'runner_sha256': base.sha(__file__), 'r2_runner_sha256': base.sha(r2.__file__),
            'r1_runner_sha256': base.sha(base.__file__), 'original_txt_sha256': base.ORIGINAL_SHA256,
            'python_executable': sys.executable, 'python_version': sys.version,
            'modules': modules, 'navigation_storage_present': storage is not None,
            'existing_indexes': indexes, 'activated': False}


@contextmanager
def compatible_field():
    original_verify, original_check = base.verify_stage, r2.check_plans
    verifier = legacy_compatible_verifier()
    def verify(stage, identity):
        with phase('verify retained navigation ' + str(stage)):
            return verifier(stage, identity)
    def check(variants, context):
        event = check_field(context)
        original_check(variants, context)
        journal = context['parent'] / 'recovery-field-capabilities-r3.jsonl'
        fd = os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
    base.verify_stage, r2.check_plans = verify, check
    try:
        yield
    finally:
        base.verify_stage, r2.check_plans = original_verify, original_check


def main(argv=None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '02_BACKEND'))
    # Check every non-optional verifier dependency even for direct worker entry.
    required_dependencies()
    with compatible_field():
        return r2.main(argv)


if __name__ == '__main__':
    try:
        exit_code = main()
    except BaseException as error:
        try:
            from semantic_runtime.genos_backend import safe
            import traceback
            print(safe(traceback.format_exc()), file=sys.stderr, flush=True)
        except ImportError:
            print(type(error).__name__ + ': recovery startup failed', file=sys.stderr, flush=True)
        exit_code = 130 if isinstance(error, KeyboardInterrupt) else 1
    base.log('R3 FINISHED status=' + str(exit_code) + '; no activation')
    raise SystemExit(exit_code)
