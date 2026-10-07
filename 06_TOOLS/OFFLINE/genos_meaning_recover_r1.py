#!/usr/bin/env python3
"""Recover the exact R2 meaning bundle without changing its pinned source bytes.

Run this FILE with python3. Spawn workers can import a real __main__ file.
Only unpublished baseline scratch directories receive recovery checkpoints.
Existing RAW, review ledgers, plans, releases and CURRENT remain native-owned.
"""
from contextlib import closing, contextmanager
import argparse
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import sys
import tempfile
import time
import types
import uuid

VERSION = 'genos-meaning-recovery-20261002-r1'
# The frozen original is filled by the handoff packager; never re-pin a field plan.
ORIGINAL_SHA256 = '057acbd941fcfa5bc71cab03a45de369a04345b035b399de4beebfb16af829db'


def log(message):
    print(time.strftime('[%Y-%m-%d %H:%M:%S] ') + 'RECOVERY ' + message, flush=True)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def read(path):
    return json.loads(Path(path).read_text())


def load_bundle(original):
    """Use the SAME original pathname for origin.json and variant code pins."""
    original = Path(original).resolve(strict=True)
    if sha(original) != ORIGINAL_SHA256:
        raise ValueError('Original R2 TXT differs; preserve it and inspect, do not change pinned hashes')
    text = original.read_text()
    code = text.split("<<'GENOS_BULK_PY'\n", 1)[1].rsplit('\nGENOS_BULK_PY', 1)[0]
    os.environ['GENOS_VARIANTS_TOOL_PATH'] = str(original)
    namespace = {'__name__': 'genos_recovery_original_bundle', '__file__': str(original)}
    exec(compile(code, str(original), 'exec'), namespace)
    return types.SimpleNamespace(**namespace), sys.modules['genos_meaning_variants']


def native_identity(module, source, glossary, output, serving, scope):
    """Evaluate the installed builder's own identity, rather than a copied formula."""
    source, glossary, output = (Path(p).resolve() for p in (source, glossary, output))
    tree = ast.parse(inspect.getsource(module.build_generation))
    assignments = [node for node in tree.body[0].body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'identity' for t in node.targets)]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Dict):
        raise ValueError('Unsupported field builder identity; no silent identity rewrite')
    reference_scope_mode = os.environ.get('GENOS_REFERENCE_SCOPE_V2', '0')
    if reference_scope_mode not in {'0', '1'}:
        raise ValueError('GENOS_REFERENCE_SCOPE_V2 must be 0 or 1')
    expression = ast.Expression(body=assignments[0].value)
    return eval(compile(expression, module.__file__, 'eval'), vars(module),
                {'source': source, 'glossary': glossary, 'output': output,
                 'serving': serving, 'scope': scope,
                 'reference_scope_v2': reference_scope_mode == '1'})


def plain_tree(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Recovery scratch must not be a symlink')
    for item in path.rglob('*'):
        if item.is_symlink():
            raise ValueError('Recovery scratch contains a symlink: ' + str(item))
        if item.is_file() and (item.name.endswith(('-wal', '-journal')) and item.stat().st_size):
            raise ValueError('Recovery scratch contains a live/unsettled SQLite sidecar')


def inventory(stage):
    result = {}
    for directory in ('links', 'generation', 'audit'):
        root = Path(stage) / directory
        for path in sorted(root.rglob('*')):
            if (path.is_file() and not path.name.startswith('.nfs')
                    and not path.is_relative_to(Path(stage) / 'generation/fulltext')):
                # Native finalization adds only navigation/fulltext bindings here.
                # TermIndex verifies the immutable remainder against its digest.
                if path == Path(stage) / 'generation/manifest.json':
                    continue
                result[str(path.relative_to(stage))] = sha(path)
    return result


def verify_stage(stage, identity):
    """Accept only complete navigation bound to the native identity and glossary."""
    from semantic_runtime.contracts import digest
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import TermIndex
    from semantic_runtime import navigation_storage
    from lawrag.pipeline import term_generation, glossary_knowledge
    stage = Path(stage)
    plain_tree(stage)
    generation = stage / 'generation'
    manifest = read(generation / 'manifest.json')
    index = read(generation / 'navigation/manifest.json')
    links = read(stage / 'links/report.json')
    if (manifest['generation_id'] != 'term-source-' + digest(identity)[:20]
            or manifest['source_store_sha256'] != identity['source_sha256']
            or identity['scope'] is not None and manifest['scope'] != identity['scope']
            or links['identity'] != {'source_sha256': identity['source_sha256'], 'glossary': identity['glossary']}
            or index['compiler_sha256'] != identity['indexer_sha256']
            or index['dictionary_sha256'] != sha(stage / 'links/links.sqlite')
            or index['term_tools_sha256'] != identity['dependencies']['term_tools.py']
            or sha(generation / 'glossary/dictionary.sqlite') != identity['glossary']['dictionary_sha256']):
        raise ValueError('Scratch source/glossary/compiler/scope identity mismatch')
    for name, expected in links['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid linkage artifact path')
        if sha(stage / 'links' / relative) != expected:
            raise ValueError('Scratch linkage artifact changed')
    knowledge = glossary_knowledge.selected_for(Path(identity['glossary']['directory']))
    legal = knowledge / 'legal.sqlite' if knowledge else Path(identity['glossary']['directory']) / 'dictionary.sqlite'
    if index['legal_sha256'] != sha(legal):
        raise ValueError('Scratch legal knowledge mismatch')
    if manifest.get('navigation') and manifest['navigation'] != {
            'path': 'navigation', 'manifest_sha256': sha(generation / 'navigation/manifest.json')}:
        raise ValueError('Scratch navigation binding mismatch')
    with closing(Store(generation)) as store:
        TermIndex(generation / 'navigation', store)
        expected_ids = set(manifest['scope']['document_version_ids'])
        actual_ids = {r[0] for r in store.db.execute('SELECT document_id FROM document')}
        if expected_ids != actual_ids or index['document_count'] != len(actual_ids):
            raise ValueError('Scratch document coverage mismatch')
    if index.get('storage'):
        navigation_storage.verify_audit(stage / 'audit/navigation',
            expected_manifest_sha256=index['storage']['audit_manifest_sha256'],
            expected_index_sha256=index['index_sha256'])
    # Validating these immutable glossary assets needs a navigation binding. Do so
    # without editing an orphan: the native glossary verifier is source-independent.
    from semantic_runtime.navigation_agent import glossary_assets
    glossary_knowledge.verify(generation / manifest['glossary']['bundle'], force=True)
    glossary = glossary_assets(generation, {})
    try:
        glossary.check_unchanged()
    finally:
        glossary.close()
    return manifest, index


class Proxy:
    def __init__(self, module, **overrides):
        self.module, self.overrides = module, overrides
    def __getattr__(self, name):
        return self.overrides[name] if name in self.overrides else getattr(self.module, name)


class Recovery:
    def __init__(self, module):
        self.module = module
        self.native = module.build_generation
        self.repair_sha = sha(__file__)
        self.active = None

    def checkpoint(self, stage, output, identity, *, origin=None):
        verify_stage(stage, identity)
        log('Checkpoint hashing completed navigation and build evidence: ' + str(stage))
        receipt = {'schema_version': VERSION, 'identity': identity, 'phase': 'navigation-complete',
                   'stage': str(stage), 'output': str(output), 'recovery_sha256': self.repair_sha,
                   'original_txt_sha256': ORIGINAL_SHA256, 'origin': origin,
                   'files': inventory(stage), 'activated': False}
        atomic(output.parent / (output.name + '-recovery-r1.json'), receipt)
        log('CHECKPOINT navigation-complete; failures will preserve this directory')
        return receipt

    def resume(self, receipt, output, identity):
        from semantic_runtime.fulltext import FulltextIndex
        from lawrag.pipeline.term_serving_bundle import verify_assets
        from lawrag.pipeline import document_release
        stage = Path(receipt['stage'])
        if (receipt['identity'] != identity or receipt['recovery_sha256'] != self.repair_sha
                or receipt['original_txt_sha256'] != ORIGINAL_SHA256 or receipt['output'] != str(output)
                or receipt['schema_version'] != VERSION or receipt['phase'] != 'navigation-complete'
                or stage.parent != output.parent or not stage.name.startswith('.' + output.name + '-')):
            raise ValueError('Recovery checkpoint identity/path changed; original artifacts preserved')
        if inventory(stage) != receipt['files']:
            raise ValueError('Recovery checkpoint payload changed; no rebuild or deletion attempted')
        manifest, index = verify_stage(stage, identity)
        generation = stage / 'generation'
        fulltext = generation / 'fulltext'
        if fulltext.exists():
            if (fulltext / 'manifest.json').is_file():
                ft = FulltextIndex(fulltext, index).manifest
                if ft['builder_sha256'] != identity['fulltext_builder_sha256']:
                    raise ValueError('Completed fulltext builder changed')
                log('REUSE verified completed fulltext')
            else:
                retained = stage / ('failed-fulltext-' + uuid.uuid4().hex)
                os.rename(fulltext, retained)
                log('Incomplete fulltext retained at ' + str(retained))
        if not fulltext.exists():
            log('RESUME from fulltext; document linking and navigation will not run again')
            ft = self.module.fulltext.build(generation / 'navigation', fulltext)
        else:
            ft = read(fulltext / 'manifest.json')
        manifest['navigation'] = {'path': 'navigation', 'manifest_sha256': sha(generation / 'navigation/manifest.json')}
        manifest['fulltext'] = {'path': 'fulltext', 'manifest_sha256': sha(fulltext / 'manifest.json'),
                                'navigation_index_sha256': ft['navigation_index_sha256']}
        # Match the native builder's JSON bytes and result contract exactly.
        atomic(generation / 'manifest.json', manifest)
        result = {'schema_version': 'term-generation-build-v1', 'identity': identity,
                  'generation': 'generation', 'manifest_sha256': sha(generation / 'manifest.json'),
                  'navigation': manifest['navigation'], 'counts': index['counts'], 'llm_calls': 0,
                  'quality_certified': False, 'activated': False}
        if index.get('storage'):
            result['navigation_audit'] = {'path': 'audit/navigation',
                'manifest_sha256': index['storage']['audit_manifest_sha256']}
        result_path = stage / 'result.json'
        if result_path.exists():
            try:
                prior = read(result_path)
            except (ValueError, UnicodeError):
                retained = stage / ('failed-result-' + uuid.uuid4().hex + '.json')
                os.rename(result_path, retained)
                log('Incomplete native result retained at ' + str(retained))
            else:
                if prior != result:
                    raise ValueError('Existing scratch result differs from verified recovery inputs')
        if not result_path.exists():
            atomic(result_path, result)
        verify_assets(generation)
        document_release._verify_navigation_audit(stage)
        if native_identity(self.module, self.active['source'], self.active['glossary'], output,
                           True, self.active['scope']) != identity:
            raise ValueError('Native inputs changed during recovery')
        if output.exists():
            raise ValueError('Build output appeared during recovery')
        os.rename(stage, output)
        log('COMPLETE baseline=' + str(output) + '; reference resolution continues through the original R2 pipeline')
        return result

    def build(self, source, glossary, output, *, serving=False, scope=None):
        output = Path(output).resolve()
        if not serving or output.name != 'baseline':
            return self.native(source, glossary, output, serving=serving, scope=scope)
        identity = native_identity(self.module, source, glossary, output, serving, scope)
        self.active = {'source': source, 'glossary': glossary, 'output': output, 'scope': scope, 'identity': identity}
        if output.exists():
            return self.native(source, glossary, output, serving=serving, scope=scope)
        receipt_path = output.parent / (output.name + '-recovery-r1.json')
        if receipt_path.exists():
            return self.resume(read(receipt_path), output, identity)
        candidates = []
        for stage in sorted(output.parent.glob('.' + output.name + '-*')):
            try:
                verify_stage(stage, identity)
                candidates.append(stage)
            except (ValueError, KeyError, OSError, sqlite3.Error) as error:
                log('PRESERVE unusable earlier scratch=' + str(stage) + ' reason=' + type(error).__name__)
        if len(candidates) > 1:
            raise ValueError('Multiple valid old scratch directories; explicit inspection required, never choose latest')
        if candidates:
            origin = candidates[0]
            before = inventory(origin)
            stage = Path(tempfile.mkdtemp(prefix='.' + output.name + '-', dir=output.parent))
            def ignore(directory, names):
                skipped = {name for name in names if name.startswith('.nfs') or name == '__pycache__'}
                if Path(directory) == origin / 'generation':
                    skipped.add('fulltext')
                return skipped
            log('COPY verified old scratch, preserving original bytes: ' + str(origin))
            for name in ('links', 'generation', 'audit'):
                if (origin / name).exists():
                    shutil.copytree(origin / name, stage / name, ignore=ignore)
            if inventory(origin) != before or inventory(stage) != before:
                raise ValueError('Old scratch changed during recovery copy; both copies preserved')
            receipt = self.checkpoint(stage, output, identity,
                                      origin={'path': str(origin), 'files': before})
            return self.resume(receipt, output, identity)
        log('No complete earlier navigation survives. Rebuilding links/navigation from existing prepared inputs; meaning jobs are preserved.')
        return self.native(source, glossary, output, serving=serving, scope=scope)

    @contextmanager
    def installed(self, release):
        module = self.module
        saved_tempfile, saved_shutil, saved_fulltext, saved_release = module.tempfile, module.shutil, module.fulltext.build, release.build_generation
        owned = set()
        def mkdtemp(*args, **kwargs):
            value = saved_tempfile.mkdtemp(*args, **kwargs)
            if self.active and Path(value).resolve().parent == self.active['output'].parent:
                owned.add(Path(value).resolve())
            return value
        def retain(path, *args, **kwargs):
            if Path(path).resolve() in owned:
                log('FAILED scratch preserved=' + str(path) + '; original traceback follows')
                return
            return saved_shutil.rmtree(path, *args, **kwargs)
        def fulltext(navigation, output, *args, **kwargs):
            if self.active:
                stage = Path(navigation).resolve().parents[1]
                if stage in owned:
                    self.checkpoint(stage, self.active['output'], self.active['identity'])
            return saved_fulltext(navigation, output, *args, **kwargs)
        fulltext.__code__ = fulltext.__code__.replace(co_filename=saved_fulltext.__code__.co_filename)
        def build(*args, **kwargs):
            return self.build(*args, **kwargs)
        build.__code__ = build.__code__.replace(co_filename=self.native.__code__.co_filename)
        module.tempfile = Proxy(saved_tempfile, mkdtemp=mkdtemp)
        module.shutil = Proxy(saved_shutil, rmtree=retain)
        module.fulltext.build = fulltext
        release.build_generation = build
        try:
            yield self
        finally:
            module.tempfile, module.shutil, module.fulltext.build, release.build_generation = saved_tempfile, saved_shutil, saved_fulltext, saved_release


def preflight():
    """Real file/spawn/PeCab check BEFORE another long native build."""
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context
    from semantic_runtime.fulltext import _search_forms
    with ProcessPoolExecutor(max_workers=2, mp_context=get_context('spawn')) as pool:
        values = list(pool.map(_search_forms, ['복구 전문 색인 점검', '문서 참조 점검']))
    if not all(values):
        raise ValueError('Real spawn/PeCab preflight produced empty output')
    log('PREFLIGHT file-based main + spawn workers + PeCab PASS; no corpus/model request used')


def main(argv=None):
    signal.signal(signal.SIGINT, signal.default_int_handler)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-txt', required=True, type=Path)
    parser.add_argument('action', choices=['check', 'baseline', 'review', 'reviewed', 'status', 'verify'])
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--run-id', default='financial-risk-success-20261001-r3')
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--shared-root', type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / '02_BACKEND'))
    bundle, variants = load_bundle(args.original_txt)
    if args.action in {'check', 'baseline', 'review', 'reviewed'}:
        preflight()
    if args.action == 'check':
        from lawrag.core.llm import load_env
        load_env()
        settings = {'batch_size': args.batch, 'workers': args.workers, 'max_tokens':8192,
                    'timeout':120, 'max_request_chars':105000, 'split_retries':2, 'index_reserve_hours':12}
        context = bundle.fork(variants.prepared(args.data_root, args.run_id), settings, create=False)
        if context is None:
            raise ValueError('Original bulk fork is missing; recovery will not create a different review protocol')
        log('CHECK exact original R2 pins, prepared source, internal model profile and bulk origin PASS')
        return 0
    from lawrag.pipeline import term_generation, document_release
    adapter = Recovery(term_generation)
    native_args = [args.action, '--data-root', str(args.data_root), '--run-id', args.run_id,
                   '--batch', str(args.batch), '--workers', str(args.workers)]
    if args.shared_root:
        native_args += ['--shared-root', str(args.shared_root)]
    with adapter.installed(document_release):
        status = bundle.main(native_args)
    if args.action == 'status':
        parent = Path(args.data_root).resolve() / 'TERM_RELEASES' / args.run_id / (args.run_id + '-bulk-r2') / 'meaning-variants'
        for mode in ('off', 'on'):
            receipt = parent / mode / 'baseline-recovery-r1.json'
            log(mode + ' recovery_checkpoint=' + str(receipt.exists()))
            for stage in sorted((parent / mode).glob('.baseline-*')):
                log(mode + ' retained_scratch=' + str(stage) + ' navigation_manifest=' + str((stage/'generation/navigation/manifest.json').is_file()))
    return status


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
    log('FINISHED status=' + str(exit_code) + '; no activation')
    raise SystemExit(exit_code)
