"""Operator CLI for reviewed question expressions and navigation procedures."""
import argparse
import json
from pathlib import Path

from lawrag.platform.workspace import load_layout
from semantic_runtime import learning_store
from semantic_runtime.contracts import sha
from semantic_runtime.navigation_learning import validate_item


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, help='local review DB; default: runtime/semantic/learning/review.sqlite')
    sub = parser.add_subparsers(dest='command', required=True)
    collect = sub.add_parser('collect', help='propose unmatched spans from a saved run; no approval')
    collect.add_argument('--run', type=Path, required=True)
    sub.add_parser('list', help='local operator access; contains question fragments')
    resubmit = sub.add_parser('resubmit', help='fork a rejected/revoked candidate, preserving evidence')
    resubmit.add_argument('--candidate', required=True)
    resubmit.add_argument('--reason', required=True)
    proposal = sub.add_parser('propose-recipe', help='submit a metadata-only procedure for review')
    proposal.add_argument('--file', type=Path, required=True)
    proposal.add_argument('--generation', type=Path, required=True)
    proposal.add_argument('--evidence', required=True, help='review basis, e.g. observed run hash and design reference')
    review = sub.add_parser('review')
    review.add_argument('--candidate', required=True)
    review.add_argument('--status', choices=['APPROVED', 'REJECTED', 'REVOKED'], required=True)
    review.add_argument('--reviewer', required=True)
    review.add_argument('--reason', required=True)
    review.add_argument('--term-id', help='existing registered ID, required for expression approval')
    publish = sub.add_parser('publish', help='produce immutable bundle; does not activate MAIN')
    publish.add_argument('--generation', type=Path, required=True)
    publish.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    layout = load_layout()
    ledger = args.ledger or layout.path('runtime')/'semantic/learning/review.sqlite'
    if args.command == 'collect':
        result = {'candidate_ids': learning_store.collect_run(ledger, args.run)}
    elif args.command == 'list':
        result = learning_store.candidates(ledger)
    elif args.command == 'resubmit':
        result = {'candidate_id': learning_store.resubmit(ledger, args.candidate, args.reason)}
    elif args.command == 'review':
        result = learning_store.review(ledger, args.candidate, args.status, args.reviewer,
                                       args.reason, args.term_id)
    elif args.command == 'propose-recipe':
        item = json.loads(args.file.read_text(encoding='utf-8'))
        validate_item(item, 'recipe', reviewed=False)
        manifest = json.loads((args.generation/'manifest.json').read_text())
        result = {'candidate_id': learning_store.propose(ledger, 'recipe', {
            'generation_id': manifest['generation_id'], 'source_store_sha256': manifest['store_sha256'],
            'item': item, 'evidence': args.evidence})}
    else:
        # Use the selected generation's own navigation binding; never choose "latest".
        from semantic_runtime.storage import Store
        from semantic_runtime.term_index import TermIndex
        with_store = Store(args.generation)
        try:
            manifest = with_store.manifest
            binding = manifest['navigation']
            path = (args.generation/binding['path']).resolve()
            path.relative_to(args.generation.resolve())
            if sha(path/'manifest.json') != binding['manifest_sha256']:
                raise ValueError('navigation index manifest hash mismatch')
            index = TermIndex(path, with_store)
            terms = {t['id']: t for t in index.terms}
            documents = {r[0] for r in with_store.db.execute('SELECT document_id FROM document')}
            result = learning_store.publish(ledger, args.output, manifest['generation_id'],
                sha(args.generation/'manifest.json'), manifest['store_sha256'], terms, documents)
        finally:
            with_store.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
