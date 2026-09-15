#!/usr/bin/env python3
"""Compose the maintained glossary review and document-authoring units.

This produces offline DRAFT authoring data. Graph/RAG activation and the
feedback loop are separate, currently unconnected MAIN stages.
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
    # The old ZIP route cannot consume a v3 glossary. Keep it under an
    # explicitly named compatibility command instead of silently mixing them.
    owned = {'--knowledge-zip', '--publish', '--stage', '--glossary-dir',
             '--run-id', '--execute', '--check-only', '--max-review-jobs',
             '--retry-review-failed', '--input-root', '--external-root',
             '--build-dir', '--data-root', '--source', '--resume'}
    if any(token.split('=', 1)[0] in owned for token in rest):
        parser().error('Use build-all-legacy for ZIP/--publish; composed stage options are owned by build-all')
    invoke = call or subprocess.call

    def unit(*parts):
        command = [sys.executable, '-B', str(PIPELINE), *parts]
        print('단위 실행: ' + ' '.join(command[3:]), flush=True)
        return invoke(command)

    from lawrag.pipeline import glossary_review, glossary_linking
    code = unit('glossary', 'knowledge', 'check')
    if code:
        return code
    paths = glossary_review.configured_paths()
    if args.execute:
        review = ['glossary', 'review', 'complete', '--max-jobs', str(args.max_review_jobs)]
        if args.retry_review_failed:
            review.append('--retry-failed')
        code = unit(*review)
        if code:
            # Exit 3 means bounded review work remains. Never let the document
            # unit consume the older unreviewed draft in this case.
            return code
        from lawrag.pipeline import genos_stages
        data = genos_stages.offline_data_root(ROOT)
        selected = glossary_linking.configured(ROOT, data)
        if selected != paths['output']:
            raise ValueError('Completed glossary selection does not match configured review output')
        stage = ['build-data-stages', '--run-id', args.run_id, '--stage', 'all',
                 '--glossary-dir', str(selected), '--execute']
    else:
        if not paths['state'].exists():
            code = unit('glossary', 'review', 'prepare')
            if code:
                return code
        code = unit('glossary', 'review', 'status')
        if code:
            return code
        stage = ['build-data-stages', '--run-id', args.run_id, '--check-only']
    if args.exclude_internal:
        stage.append('--exclude-internal')
    return unit(*stage, *rest)


if __name__ == '__main__':
    raise SystemExit(run())
