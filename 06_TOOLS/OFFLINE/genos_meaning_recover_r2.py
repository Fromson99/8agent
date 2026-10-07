#!/usr/bin/env python3
"""Resume frozen R2 plans across verified checkout aliases; keep R1 artifacts.

Only path spellings for the SAME inode and SHA-256 may differ. Original plans
are never rewritten. The original pipeline still checks every pinned input.
"""
from contextlib import contextmanager
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

_spec = importlib.util.spec_from_file_location(
    'genos_meaning_recovery_r1_base', Path(__file__).with_name('genos_meaning_recover_r1.py'))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
VERSION = 'genos-meaning-recovery-20261002-r2'


class PlanProbed(Exception):
    """Exit the native build after its exact plan is checked, before construction."""


def physical_pins(pins):
    result = {}
    for name, expected in pins.items():
        path = Path(name).resolve(strict=True)
        if not path.is_file() or base.sha(path) != expected:
            raise ValueError('Pinned input changed; plan preserved: ' + name)
        stat = path.stat()
        identity = stat.st_dev, stat.st_ino
        if identity in result and result[identity] != expected:
            raise ValueError('Conflicting hashes for a checkout alias; plan preserved')
        result[identity] = expected
    return result


class PlanGuard:
    def __init__(self, variants, *, probe=False):
        self.variants, self.probe = variants, probe
        self.native = variants.immutable
        self.native_verify = variants.verify_pins

    def verify_pins(self, pins):
        """Allow a stored symlink only for an exact currently loaded code file.

        Data paths keep the native plain-path restriction. This handles imported
        code filenames from a logical checkout as well as bind-mount aliases.
        """
        allowed = None
        for name, expected in pins.items():
            try:
                self.native_verify({name: expected})
            except ValueError:
                path = Path(name)
                if not any(item.is_symlink() for item in (path, *path.parents)):
                    raise
                resolved = path.resolve(strict=True)
                stat = resolved.stat()
                if allowed is None:
                    allowed = set()
                    for code in self.variants.code_pins():
                        file = Path(code).resolve(strict=True)
                        info = file.stat()
                        allowed.add((info.st_dev, info.st_ino, file.suffix))
                if ((stat.st_dev, stat.st_ino, path.suffix) not in allowed
                        or not resolved.is_file() or base.sha(resolved) != expected):
                    raise

    def immutable(self, path, value):
        path = Path(path)
        if path.name != 'plan.json' or path.parent.name not in ('off', 'on'):
            return self.native(path, value)
        if path.exists():
            before = base.sha(path)
            old = base.read(path)
            metadata = lambda plan: {key: val for key, val in plan.items() if key != 'pins'}
            if metadata(old) != metadata(value):
                fields = sorted(key for key in set(old) | set(value)
                                if key != 'pins' and old.get(key) != value.get(key))
                raise ValueError('Frozen variant settings differ; plan preserved: ' + ','.join(fields))
            self.verify_pins(old['pins'])
            if physical_pins(old['pins']) != physical_pins(value['pins']):
                raise ValueError('Frozen plan file identities differ; same bytes in a different copy '
                                 'are not checkout aliases; plan preserved: ' + str(path))
            if old['pins'] != value['pins']:
                event = {'schema_version': VERSION, 'event': 'verified-plan-path-aliases',
                         'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                         'plan': str(path), 'plan_sha256': before,
                         'runner_sha256': base.sha(__file__),
                         'base_runner_sha256': base.sha(base.__file__),
                         'original_txt_sha256': base.ORIGINAL_SHA256,
                         'stored_pins': old['pins'], 'runtime_pins': dict(value['pins']),
                         'same_inode_and_sha256': True, 'activated': False}
                if not self.probe:
                    journal = path.parent / 'plan-alias-recovery-r2.jsonl'
                    fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'a') as handle:
                        handle.write(json.dumps(event, ensure_ascii=False) + '\n')
                        handle.flush()
                        os.fsync(handle.fileno())
                # Preserve the dictionary object shared by native final verification.
                value['pins'].clear()
                value['pins'].update(old['pins'])
                base.log('PLAN ALIASES verified same inode + SHA-256; original plan bytes preserved: ' + str(path))
            if base.sha(path) != before:
                raise ValueError('Frozen plan changed during alias verification; stopped')
        if self.probe:
            raise PlanProbed()
        return self.native(path, value)

    @contextmanager
    def installed(self):
        self.variants.immutable = self.immutable
        self.variants.verify_pins = self.verify_pins
        try:
            yield self
        finally:
            self.variants.immutable = self.native
            self.variants.verify_pins = self.native_verify


def check_plans(variants, context):
    for mode in ('off', 'on'):
        plan = context['parent'] / 'meaning-variants' / mode / 'plan.json'
        if not plan.is_file():
            continue
        candidate = {**context, 'pins': dict(context['pins'])}
        report = context['parent'] / 'review/bulk-status.json'
        if mode == 'on' and report.exists():
            candidate['pins'][str(report)] = base.sha(report)
        with PlanGuard(variants, probe=True).installed():
            try:
                variants.build_variant(candidate, mode)
            except PlanProbed:
                base.log('CHECK existing ' + mode + ' frozen plan PASS; no build/model call')


def main(argv=None):
    signal.signal(signal.SIGINT, signal.default_int_handler)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'baseline', 'review', 'reviewed', 'status', 'verify'])
    parser.add_argument('--original-txt', required=True, type=Path)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--run-id', default='financial-risk-success-20261001-r3')
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--shared-root', type=Path)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '02_BACKEND'))
    bundle, variants = base.load_bundle(args.original_txt)
    if args.action in {'check', 'baseline', 'review', 'reviewed'}:
        base.preflight()
    if args.action == 'check':
        from lawrag.core.llm import load_env
        load_env()
        settings = {'batch_size': args.batch, 'workers': args.workers, 'max_tokens': 8192,
                    'timeout': 120, 'max_request_chars': 105000, 'split_retries': 2, 'index_reserve_hours': 12}
        context = bundle.fork(variants.prepared(args.data_root, args.run_id), settings, create=False)
        if context is None:
            raise ValueError('Original bulk fork is missing; no replacement review protocol')
        check_plans(variants, context)
        base.log('CHECK original R2 pins, internal profile, bulk origin and existing variant plans PASS')
        return 0
    from lawrag.pipeline import term_generation, document_release
    native_args = [args.action, '--data-root', str(args.data_root), '--run-id', args.run_id,
                   '--batch', str(args.batch), '--workers', str(args.workers)]
    if args.shared_root:
        native_args += ['--shared-root', str(args.shared_root)]
    # Keep the exact R1 checkpoint version and fingerprint for existing resumes.
    with base.Recovery(term_generation).installed(document_release), PlanGuard(variants).installed():
        status = bundle.main(native_args)
    if args.action == 'status':
        parent = args.data_root.resolve() / 'TERM_RELEASES' / args.run_id / (args.run_id + '-bulk-r2') / 'meaning-variants'
        for mode in ('off', 'on'):
            base.log(mode + ' recovery_checkpoint=' + str((parent / mode / 'baseline-recovery-r1.json').is_file()))
            for stage in sorted((parent / mode).glob('.baseline-*')):
                base.log(mode + ' retained_scratch=' + str(stage) + ' navigation_manifest=' + str((stage / 'generation/navigation/manifest.json').is_file()))
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
    base.log('R2 FINISHED status=' + str(exit_code) + '; no activation')
    raise SystemExit(exit_code)
