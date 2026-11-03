"""Reviewed lexical hints and navigation procedures; never cached answers.

The bundle is explicitly hash bound to a source generation. No directory scanning,
model calls, canonical concept creation, or implicit approval occurs here.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from .navigation_match import SurfaceIndex, norm

VERSION = 'navigation-learning-v1'


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError('learning contract fields: ' + ','.join(fields))


def string(value, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('learning contract requires bounded nonempty text')


def strings(value, *, minimum=1, maximum=100):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError('learning contract invalid list size')
    for item in value:
        string(item)
    if len(set(value)) != len(value):
        raise ValueError('learning contract duplicate values')


def validate_item(item, kind, terms=None, documents=None, reviewed=True):
    common = {'id', 'document_version_ids'} | ({'review'} if reviewed else set())
    fields = ({'expression', 'term_id'} if kind == 'expression' else
              {'trigger_term_ids', 'required_phrases', 'excluded_phrases', 'issues',
               'steps', 'require_references'})
    if kind not in ('expression', 'recipe'):
        raise ValueError('invalid learning item kind')
    exact(item, common | fields)
    string(item['id'], 100)
    strings(item['document_version_ids'], maximum=10000)
    if documents is not None and not set(item['document_version_ids']) <= set(documents):
        raise ValueError('learning item has unknown document version')
    if reviewed:
        exact(item['review'], {'reviewer', 'reason', 'event_id', 'candidate_sha256', 'evidence'})
        for value in item['review'].values():
            string(value, 2000)
    if kind == 'expression':
        string(item['expression'], 120)
        if len(norm(item['expression'])) < 2:
            raise ValueError('expression too short')
        string(item['term_id'])
        tids = [item['term_id']]
    else:
        strings(item['trigger_term_ids'], maximum=8)
        strings(item['required_phrases'], minimum=0, maximum=8)
        strings(item['excluded_phrases'], minimum=0, maximum=8)
        if type(item['require_references']) is not bool:
            raise ValueError('require_references must be boolean')
        if not isinstance(item['issues'], list) or not 1 <= len(item['issues']) <= 6:
            raise ValueError('recipe needs 1..6 evidence issues')
        issue_ids = set()
        for issue in item['issues']:
            exact(issue, {'id', 'text'})
            if not isinstance(issue['id'], str) or not re.fullmatch(r'R[1-6]', issue['id']):
                raise ValueError('recipe issue IDs must be R1..R6')
            if issue['id'] in issue_ids:
                raise ValueError('duplicate recipe issue ID')
            issue_ids.add(issue['id']); string(issue['text'], 500)
        if not isinstance(item['steps'], list) or not 1 <= len(item['steps']) <= 8:
            raise ValueError('recipe needs 1..8 metadata steps')
        tids = list(item['trigger_term_ids'])
        for step in item['steps']:
            exact(step, {'tool', 'args'})
            a = step['args']
            if step['tool'] == 'OPEN_TERM':
                exact(a, {'term_id'}); tids.append(a['term_id'])
            elif step['tool'] == 'GRAPH':
                exact(a, {'term_id', 'hops'}); tids.append(a['term_id'])
                if type(a['hops']) is not int or not 1 <= a['hops'] <= 3:
                    raise ValueError('recipe graph hops must be 1..3')
            elif step['tool'] == 'LIST':
                exact(a, {'term_ids', 'match'})
                strings(a['term_ids'], maximum=8); tids.extend(a['term_ids'])
                if a['match'] not in ('any', 'all'):
                    raise ValueError('invalid recipe match')
            else:
                raise ValueError('recipe permits only OPEN_TERM, GRAPH, LIST')
        if not set(tids) <= set(item['trigger_term_ids']):
            raise ValueError('recipe steps must use matched trigger IDs')
    if terms is not None:
        for tid in tids:
            if tid not in terms:
                raise ValueError('learning item has unknown term ID')
            scoped = terms[tid].get('scope_document_id')
            if scoped and scoped not in item['document_version_ids']:
                raise ValueError('term meaning outside reviewed scope')


def validate_bundle(bundle, generation_id, manifest_sha256, terms, documents):
    exact(bundle, {'schema_version', 'id', 'generation_id', 'generation_manifest_sha256',
                   'expressions', 'recipes'})
    if (bundle['schema_version'] != VERSION or bundle['generation_id'] != generation_id or
            bundle['generation_manifest_sha256'] != manifest_sha256):
        raise ValueError('learning bundle generation binding mismatch')
    string(bundle['id'], 100)
    ids, mappings = set(), {}
    for kind, key in [('expression', 'expressions'), ('recipe', 'recipes')]:
        if not isinstance(bundle[key], list) or len(bundle[key]) > 10000:
            raise ValueError('invalid learning bundle size')
        for item in bundle[key]:
            validate_item(item, kind, terms, documents)
            if item['id'] in ids:
                raise ValueError('duplicate learning item ID')
            ids.add(item['id'])
            if kind == 'expression':
                identity = (norm(item['expression']), tuple(sorted(item['document_version_ids'])))
                if identity in mappings and mappings[identity] != item['term_id']:
                    raise ValueError('conflicting reviewed expression mappings')
                mappings[identity] = item['term_id']
    return bundle


class LearnedMatcher:
    def __init__(self, base, bundle=None, status=None):
        self.base, self.bundle = base, bundle
        self.status = status or {'status': 'READY', 'bundle_id': bundle['id']}
        self.expressions = SurfaceIndex()
        for item in (bundle or {}).get('expressions', []):
            self.expressions.add(item['expression'], item)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def starts(self, question, scope):
        seeds = deepcopy(self.base.starts(question, scope))
        info = {**self.status, 'matches': [], 'recipe_status': 'NO_MATCH', 'recipe': None}
        seeds['learning'] = info
        if self.bundle is None:
            return seeds
        terms = {t['id']: t for t in seeds['terms']}
        for hit in self.expressions.match(question):
            for item in hit['values']:
                # Scope is applicability, never an authorization grant. Require exact equality.
                if set(item['document_version_ids']) != set(scope):
                    continue
                span = {key: hit[key] for key in ('start', 'end', 'text')}
                terms.setdefault(item['term_id'], {'id': item['term_id'], 'question_spans': []})['question_spans'].append(span)
                info['matches'].append({'mapping_id': item['id'], 'term_id': item['term_id'], **span})
        seeds['terms'] = sorted(terms.values(), key=lambda t: t['id'])
        query = norm(question)
        recipes = [r for r in self.bundle['recipes']
                   if set(r['document_version_ids']) == set(scope)
                   and set(r['trigger_term_ids']) <= terms.keys()
                   and all(norm(p) in query for p in r['required_phrases'])
                   and not any(norm(p) in query for p in r['excluded_phrases'])]
        if len(recipes) == 1:
            info.update(recipe_status='MATCHED', recipe=recipes[0])
        elif len(recipes) > 1:
            info['recipe_status'] = 'AMBIGUOUS_FALLBACK'
        return seeds


def load_learning_bundle(binding, contracts_root, generation, terms, documents):
    exact(binding, {'path', 'sha256'})
    if Path(binding['path']).is_absolute():
        raise ValueError('learning bundle path must be relative')
    root = Path(contracts_root).resolve()
    path = (root / binding['path']).resolve(); path.relative_to(root)
    if path.stat().st_size > 16_000_000:
        raise ValueError('learning bundle too large')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding['sha256']:
        raise ValueError('learning bundle hash mismatch')
    manifest_bytes = (Path(generation) / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    return validate_bundle(json.loads(raw), manifest['generation_id'],
                           hashlib.sha256(manifest_bytes).hexdigest(), terms, documents)


def bind_learning(matcher, binding, contracts_root, generation):
    """Invalid/stale bundles disable only reuse; the baseline stays available."""
    try:
        bundle = load_learning_bundle(binding, contracts_root, generation,
                                      matcher.tools.terms, matcher.documents)
        return LearnedMatcher(matcher, bundle)
    except (ValueError, KeyError, TypeError, OSError):
        return LearnedMatcher(matcher, status={'status': 'INVALID_BINDING_FALLBACK'})
