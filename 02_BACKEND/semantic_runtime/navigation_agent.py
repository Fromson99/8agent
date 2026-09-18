"""Serving adapter for the ID-driven navigation loop and pinned glossary assets.

Resources are request-local because HTTP requests run on different worker threads.
No research runner, answer data, or provider discovery participates in retrieval.
"""
import json
import os
from pathlib import Path
import threading

from .contracts import sha
from . import full_glossary
from .full_glossary import Glossary

_HASH_MEMO = {}
_HASH_LOCK = threading.Lock()
_ORIGINAL_SHA = full_glossary.sha


def memoized_sha(path):
    """SHA-256 of a pinned glossary file, recomputed only when its stat signature changes.

    The glossary bundle is ~14GB; hashing it on every HTTP request cost ~11s. The
    stat tuple (size, mtime_ns, ctime_ns, inode) is the same drift signal
    Glossary.check_unchanged already relies on inside a request.
    """
    resolved = Path(path).resolve()
    stat = os.stat(resolved)
    signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
    with _HASH_LOCK:
        cached = _HASH_MEMO.get(resolved)
        if cached is not None and cached[0] == signature:
            return cached[1]
    digest = _ORIGINAL_SHA(resolved)
    with _HASH_LOCK:
        _HASH_MEMO[resolved] = (signature, digest)
    return digest


# full_glossary.py bytes are pinned by every serving cache receipt (compiler_sha256),
# so the memo is installed from here instead of editing that module.
full_glossary.sha = memoized_sha
from .full_glossary_connections import ConnectionReader
from .navigation_loop import NavigationAgent, NavigationSession
from .navigation_match import ReverseMatcher
from .term_agent import TermAgent


def glossary_assets(generation, config):
    root = Path(generation).resolve()
    manifest = json.loads((root / 'manifest.json').read_text()) if (root / 'manifest.json').is_file() else {}
    binding = manifest.get('glossary') or config['glossary']
    paths = {}
    for key in ('bundle', 'dictionary', 'cache'):
        path = (root / binding[key]).resolve()
        path.relative_to(root)
        paths[key] = path
    # Refuse implicit cache builds in the serving process.
    receipt = paths['cache'] / binding['cache_receipt']
    receipt.resolve().relative_to(paths['cache'])
    if memoized_sha(receipt) != binding['cache_receipt_sha256']:
        raise ValueError('glossary cache receipt mismatch')
    cache_binding = json.loads(receipt.read_text())['binding']
    if cache_binding['compiler_sha256'] != memoized_sha(Path(__file__).with_name('full_glossary.py')):
        raise ValueError('glossary compiler/cache binding mismatch')
    return Glossary(paths['bundle'], paths['dictionary'], paths['cache'],
                    manifest_sha256=binding['manifest_sha256'],
                    connection_factory=ConnectionReader)


class ServingNavigationAgent(TermAgent):
    def retrieve(self, plan, use_llm=True):
        index = self.get_index()
        tools = index.tools(plan['scope']['document_version_ids'])
        glossary = None
        try:
            glossary = glossary_assets(self.pipeline.store.path, self.config)
            matcher = ReverseMatcher(self.pipeline.store.db, tools, glossary)
            binding = self.config.get('learning', {}).get('bundle')
            if binding is not None:
                from .navigation_learning import bind_learning
                matcher = bind_learning(matcher, binding, self.pipeline.contracts.root,
                                        self.pipeline.store.path)
            limits = self.config.get('limits')
            if use_llm:
                result = NavigationAgent(self.pipeline, glossary, index, matcher, limits).retrieve(plan, True)
            else:
                session = NavigationSession(matcher, tools, glossary, plan['question'],
                                            plan['scope']['document_version_ids'], limits)
                state = {'status': 'METADATA_ONLY', 'use_llm': False, 'selected_ids': [],
                         'calls': 0, 'provider_receipts': [], 'trace': [], 'failure': None,
                         'initial': session.context()['initial'], 'quality_certified': False,
                         'final': {'findings': [], 'evidence_ids': [], 'open_questions': [],
                                   'question_for_user': '', 'next_action': 'STOP'}}
                result = {'candidates': [], 'routes': {'navigation_loop': 0},
                          'vector_status': 'NOT_USED', 'generation_id': plan['generation_id'],
                          'term_agent': state}
                if hasattr(session, 'seed'):
                    state['matched_question_spans'] = [span for kind in ('terms', 'structures')
                                                      for row in session.seed[kind]
                                                      for span in row['question_spans']]
                    state['learning'] = session.learning
            glossary.check_unchanged()
            return result
        finally:
            tools.db.close()
            if glossary is not None:
                glossary.close()
