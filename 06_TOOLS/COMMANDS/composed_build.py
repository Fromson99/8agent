#!/usr/bin/env python3
"""Compose the maintained glossary review and document-authoring units.

Structures all selected documents, then reviews a combined glossary draft and
produces a verified integrated serving candidate. Explicit activation is separate; feedback stays proposed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / '06_TOOLS/pipeline.py'
sys.path.insert(0, str(ROOT / '02_BACKEND'))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', required=True, help='Document stage run ID; reuse it to resume')
    p.add_argument('--max-review-jobs', type=int, default=100,
                   help='Maximum glossary model jobs per invocation (1..1000)')
    p.add_argument('--retry-review-failed', action='store_true')
    p.add_argument('--exclude-internal', action='store_true')
    p.add_argument('--glossary-dir', type=Path, help='Explicit previously reviewed glossary; completion receipt required')
    p.add_argument('--glossary-corpus-policy', choices=['append', 'replace'], default='append',
                   help='How the selected glossary document evidence is combined with this run')
    p.add_argument(
        '--reference-review-state', type=Path,
        help=('Explicit completed reference-resolution state to apply to the serving candidate; '
              'omission keeps the deterministic-only navigation index'))
    p.add_argument('--reference-model-profile', type=Path,
                   help='Model profile for automatic reference resolution and approval in the final release build')
    p.add_argument('--max-reference-cases', type=int, default=10000)
    p.add_argument('--reference-batch-size', type=int, default=8)
    p.add_argument('--base-generation', action='append', default=[], help='Explicit existing source generation to retain')
    p.add_argument('--exclude-document', action='append', default=[], help='Explicit old document-version ID to omit from the integrated generation')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--check-only', action='store_true')
    return p


def run(argv=None, *, call=None):
    args, rest = parser().parse_known_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.run_id):
        parser().error('--run-id must be 1..80 letters, numbers, dots, underscores or hyphens')
    if not 1 <= args.max_review_jobs <= 1000:
        parser().error('--max-review-jobs must be 1..1000')
    if args.reference_model_profile and args.reference_review_state:
        parser().error('select --reference-model-profile or --reference-review-state')
    if not 1 <= args.max_reference_cases <= 10000 or not 1 <= args.reference_batch_size <= 32:
        parser().error('invalid reference case or batch limit')
    # The old ZIP route cannot consume a v3 glossary. Keep it under an
    # explicitly named compatibility command instead of silently mixing them.
    owned = {'--knowledge-zip', '--publish', '--stage', '--glossary-dir',
             '--reference-review-state', '--reference-model-profile', '--max-reference-cases', '--reference-batch-size',
             '--run-id', '--execute', '--check-only', '--max-review-jobs',
             '--retry-review-failed', '--input-root', '--external-root',
             '--build-dir', '--data-root', '--source', '--resume', '--glossary-corpus-policy'}
    if any(token.split('=', 1)[0] in owned for token in rest):
        parser().error('ZIP/--publish are retired; use document-release activate after build-all')
    def invoke(command):
        if call is not None:
            return call(command)
        process = subprocess.Popen(command)
        try:
            return process.wait()
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise


    def unit(*parts):
        command = [sys.executable, '-B', str(PIPELINE), *parts]
        print('단위 실행: ' + ' '.join(command[3:]), flush=True)
        return invoke(command)

    from lawrag.pipeline import glossary_review
    # Structure must complete before any glossary model work. The release unit
    # collects all selected document definitions and reviews one combined draft.
    stage = ['build-data-stages', '--run-id', args.run_id, '--stage', 'structure',
             '--execute' if args.execute else '--check-only']
    if args.exclude_internal:
        stage.append('--exclude-internal')
    code = unit(*stage, *rest)
    if code:
        return code
    if args.glossary_dir:
        selected = args.glossary_dir.resolve()
        code = unit('document-release', 'verify-glossary', '--glossary-dir', str(selected))
    else:
        selected = glossary_review.configured_paths()['glossary']
        code = unit('glossary', 'knowledge', 'check')
    if code or not args.execute:
        return code

    release = ['document-release', 'build', '--run-id', args.run_id, '--glossary-dir', str(selected),
               '--max-review-jobs', str(args.max_review_jobs)]
    if args.glossary_corpus_policy != 'append':
        release += ['--glossary-corpus-policy', args.glossary_corpus_policy]
    if args.reference_review_state:
        release += ['--reference-review-state', str(args.reference_review_state.resolve())]
    if args.reference_model_profile:
        release += ['--reference-model-profile', str(args.reference_model_profile.resolve())]
    if args.max_reference_cases != 10000:
        release += ['--max-reference-cases', str(args.max_reference_cases)]
    if args.reference_batch_size != 8:
        release += ['--reference-batch-size', str(args.reference_batch_size)]
    for base in args.base_generation:
        release += ['--base-generation', base]
    for did in args.exclude_document:
        release += ['--exclude-document', did]
    if args.retry_review_failed:
        release.append('--retry-review-failed')
    return unit(*release)


if __name__ == '__main__':
    raise SystemExit(run())
