"""Manage task definition candidates; this command never activates a release."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from lawrag.platform.workspace import load_layout
from semantic_runtime import task_policy as policy
from semantic_runtime.contracts import sha, write


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, help='default: runtime/semantic/task-harness/definitions.sqlite')
    sub = parser.add_subparsers(dest='command', required=True)
    template = sub.add_parser('template', help='write an unreviewed JSON definition')
    template.add_argument('--output', required=True, type=Path)
    propose = sub.add_parser('propose')
    propose.add_argument('--file', required=True, type=Path)
    review = sub.add_parser('review', help='record explicit operator review; no activation')
    review.add_argument('--id', default='definition_scope')
    review.add_argument('--version', type=int, required=True)
    review.add_argument('--reviewer', required=True)
    review.add_argument('--reason', required=True)
    publish = sub.add_parser('publish', help='copy reviewed definitions to a new immutable DB')
    publish.add_argument('--id', default='definition_scope')
    publish.add_argument('--version', type=int, required=True)
    publish.add_argument('--definition-sha256', required=True)
    publish.add_argument('--review-sha256', required=True)
    publish.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    layout = load_layout()
    db_path = args.db or layout.path('runtime')/'semantic/task-harness/definitions.sqlite'
    if args.command == 'template':
        write(args.output, policy.DEFAULT)
        result = {'path': str(args.output), 'status': 'PROPOSED'}
    elif args.command == 'propose':
        result = policy.propose_definition(db_path, json.loads(args.file.read_text(encoding='utf-8')))
    elif args.command == 'review':
        result = policy.review_definition(db_path, args.id, args.version, args.reviewer, args.reason)
    else:
        binding = {'id': args.id, 'version': args.version, 'definition_sha256': args.definition_sha256,
                   'review_sha256': args.review_sha256, 'sha256': sha(db_path)}
        policy.load_definition(db_path, binding)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive reservation prevents replacement of an existing generation's DB.
        with args.output.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(args.output)) as target:
                    source.backup(target)
            binding['sha256'] = sha(args.output)
            policy.load_definition(args.output, binding)
        except Exception:
            args.output.unlink()
            raise
        result = {**binding, 'path': str(args.output), 'status': 'PUBLISHED_NOT_ACTIVE'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
