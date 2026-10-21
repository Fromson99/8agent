"""Bounded source acquisition before LLM selection; no answer or relevance verdict."""
import json
import re
import time
from collections import defaultdict, deque

from ..fulltext import question_terms
from ..contracts import digest
from .. import observability as obs
from .repository import encoded, text_hash
from .errors import ContractError, BudgetExhausted

SCOPED_POLICY = {'query_top_k': 64, 'seed_limit': 96, 'reference_seeds': 32,
          'source_limit': 160, 'action_limit': 512, 'source_char_limit': 640000,
          'packet_chars': 50000}


POLICY = {**SCOPED_POLICY, 'source_limit':288, 'action_limit':1024, 'source_char_limit':1600000}
log = obs.get_logger('legal_agent.source_recall')

def query_variants(question):
    """Unmodified fallback query; never infer intent from parentheses or a line."""
    return [question.strip()] if question.strip() else []



def focused_queries(question, plan):
    """Execute the model's search terms without inventing numeric/topic variants."""
    return list(dict.fromkeys(plan['queries'] or query_variants(question)))


def unresolved_coordinate_candidates(frame, locator, matcher, scope):
    """Exploration only: never resolve or approve a relation from its bare number."""
    from lawrag.core.legal_coordinate import find_coordinates
    kind = re.search(r'(시행령|시행규칙)\s*제\s*\d', frame)
    coords = [c.coordinate for c in find_coordinates(locator) if c.coordinate.unit == '조']
    if not kind or not coords:
        return []
    keys = {c.key() for c in coords}
    index = getattr(matcher, '_source_recall_coordinate_index_v1', None)
    if index is None:
        index = defaultdict(list)
        for (did, uid), coord in ((row for d in sorted(scope) if matcher.documents.get(d,'').endswith(kind.group(1)) for row in matcher.stored_coordinates.for_document(d)) if hasattr(matcher.stored_coordinates,'for_document') else matcher.stored_coordinates.items()):
            name = matcher.documents.get(did, '')
            if not coord: continue
            for suffix in ('시행령','시행규칙'):
                if name.endswith(suffix): index[(suffix,coord.key())].append((did,uid))
        matcher._source_recall_coordinate_index_v1 = index
    matches = []
    for key in keys:
        for did, uid in index.get((kind.group(1),key),[]):
            if did in scope: matches.extend(matcher._unit_sources(did,uid))
    return sorted(set(matches))


def preserve_source_choices(branches, allowed, limit):
    chosen = list(dict.fromkeys(sid for branch in branches for sid in branch))
    if len(chosen)>limit or any(sid not in allowed for sid in chosen):
        raise ContractError('source union cannot silently drop or escape a branch selection')
    if any(not set(branch).issubset(chosen) for branch in branches):
        raise ContractError('source union lost a parent choice')
    return chosen


def spans_complete(source, evidence):
    """Canonical ID presence or an initial page is not complete source acquisition."""
    ranges = defaultdict(list)
    for e in evidence:
        if e['source_id'] == source['id']:
            for p in e['spans']:
                ranges[p['block_id']].append((p['start_cp'], p['end_cp']))
    for b in source['blocks']:
        end = 0
        for a, z in sorted(ranges[b['block_id']]):
            if a > end:
                break
            end = max(end, z)
        if end < len(b['text']):
            return False
    return True


def evidence_packets(question, evidence, limit=50000):
    """Lossless bounded inputs. Preparing these is NOT a successful model call."""
    packets = []
    current = {'question': question, 'evidence': [], 'delivery_status': 'PREPARED_NOT_SENT'}
    for e in evidence:
        item = {k: e[k] for k in ('evidence_id', 'source_id', 'document_id', 'unit_id',
                'generation_id', 'source_artifact_hash', 'text_hash', 'metadata')}
        item['text'] = '\n'.join(p['text'] for p in e['spans'])
        if text_hash(item['text']) != e['text_hash']:
            raise ContractError('packet source text hash mismatch')
        trial = {**current, 'evidence': current['evidence'] + [item]}
        if len(encoded(trial)) > limit:
            if not current['evidence']:
                raise ContractError('individual exact evidence exceeds packet limit')
            packets.append(current)
            current = {**current, 'evidence': []}
        current['evidence'].append(item)
        if len(encoded(current)) > limit:
            raise ContractError('individual exact evidence exceeds packet limit')
    if current['evidence']:
        packets.append(current)
    return packets


class SourceRecall:
    def __init__(self, sources):
        self.s = sources
        scope = set(sources.scope)
        catalogue=sources.matcher.sources
        self.allowed = (catalogue.ids_for_documents(scope) if hasattr(catalogue,'ids_for_documents') else
                        {sid for sid, source in catalogue.items() if source['document_id'] in scope})
        self.scores = defaultdict(float)
        self.routes = defaultdict(list)
        self.limits = []
        self.start = time.monotonic()

    def check_time(self):
        # Source acquisition has no independent timer; the request owns its deadline.
        self.s.context.remaining()

    def add(self, sid, score, route):
        if sid not in self.allowed:
            return
        self.scores[sid] += score
        if route not in self.routes[sid]:
            self.routes[sid].append(route)

    def _scoped_discover(self):
        q = self.s.context.request['question']
        query_receipts = []
        plan = getattr(self.s, 'recall_query_plan', {'queries': [], 'law_names': []})
        queries = focused_queries(q, plan)
        matched = getattr(self.s, 'question_matches', None) or self.s.matcher.starts(q, self.s.scope)
        named = {d['id'] for d in matched['documents']}
        named.update(did for did, name in self.s.matcher.documents.items() if did in self.s.scope and name in plan['law_names'])
        focus_documents = named.copy()
        protected, scoped_lists = [], []
        for variant in queries:
            self.check_time()
            terms = question_terms(variant)
            if not terms:
                continue
            if not self.s.capabilities.get('fulltext'):
                self.limits.append({'kind': 'fulltext_unavailable'})
                break
            ids = self.s.matcher.fulltext.rank(self.s.matcher.fulltext_db, terms, self.allowed)
            # Project every returned location, including candidates not retained
            # for READ. No source body lookup or additional search is performed.
            calls = getattr(self.s.matcher.fulltext, 'calls', None)
            hits = calls[-1]['hits'] if calls else []
            if hits:
                from .unit_reading import unit_label
                locations = [{'document_id': h['document_id'],
                    'document_name': h['document_name'], 'location': unit_label(self.s, h)}
                    for h in hits]
            else:
                locations = [{'document_id': self.s.tools.sources[sid]['document_id'],
                    'document_name': self.s.tools.sources[sid]['document_name'],
                    'location': self.s.tools.sources[sid].get('heading', '')} for sid in ids]
            self.s.repo.event('SOURCE_FULLTEXT_RESULTS', {'query': variant,
                'locations': locations, 'returned_count': len(locations)})
            obs.event(log,'source_recall.query.finished',run_id=self.s.context.run_id,
                      query=variant,selected_count=min(len(ids),SCOPED_POLICY['query_top_k']))
            protected.extend(ids[:4])
            scoped_receipts = []
            for did in sorted(focus_documents):
                within = [sid for sid in ids if self.s.tools.sources[sid]['document_id'] == did]
                scoped_lists.append(within[:8])
                for i, sid in enumerate(within[:32]):
                    self.add(sid, 1/(60+i+1), {'kind':'document_fulltext','query':variant,'document_id':did,'rank':i+1})
                scoped_receipts.append({'document_id':did,'kept_source_ids':within[:32]})
            for i, sid in enumerate(ids[:SCOPED_POLICY['query_top_k']]):
                self.add(sid, 1 / (60+i+1), {'kind': 'fulltext', 'query': variant, 'rank': i+1})
            query_receipts.append({'query': variant, 'terms': terms, 'ranked_source_ids': ids,
                                   'kept_source_ids': ids[:SCOPED_POLICY['query_top_k']], 'document_projections':scoped_receipts})
        # Resolve composite coordinates inside named documents before loose title matches.
        from lawrag.core.legal_coordinate import find_coordinates
        normalize = lambda value: re.sub(r'\s+', '', value)
        explicit = []
        match_records = []
        for variant in queries:
            found = (matched if variant == q else self.s.matcher.starts(variant, self.s.scope))
            named = {d['id'] for d in found['documents']}
            if not named:
                named = {did for did, name in self.s.matcher.documents.items()
                         if did in self.s.scope and name in plan['law_names']}
            exact = {normalize(c.coordinate.canonical_surface()) for c in find_coordinates(variant)}
            paired = []
            if named and exact:
                for (did, uid), coord in ((row for d in sorted(named) for row in self.s.matcher.stored_coordinates.for_document(d)) if hasattr(self.s.matcher.stored_coordinates,'for_document') else self.s.matcher.stored_coordinates.items()):
                    if did in named and coord and normalize(coord.canonical_surface()) in exact:
                        paired.extend(self.s.matcher._unit_sources(did, uid))
            for sid in dict.fromkeys(paired):
                self.add(sid, 1.0, {'kind': 'exact_law_coordinate', 'query': variant})
                explicit.append(sid)
            for row in found['structures']:
                if paired or row['kind'] != 'TITLE':
                    continue
                if max((len(x['text']) for x in row['question_spans']), default=0) < 4:
                    continue
                for sid in self.s.matcher._unit_sources(row['document_id'], row['unit_id']):
                    self.add(sid, .01, {'kind': 'structure_title', 'match': row})
            match_records.append(found)
        matches = {'query_plan': plan, 'query_matches': match_records}
        ordered = sorted(self.scores, key=lambda sid: (-self.scores[sid], sid))
        scoped = list(dict.fromkeys(ids[i] for i in range(8) for ids in scoped_lists if len(ids)>i))[:72]
        seeds = list(dict.fromkeys([*explicit, *scoped, *protected, *ordered]))[:SCOPED_POLICY['seed_limit']]
        related = []
        anchors = deque((sid, 0) for sid in dict.fromkeys([*explicit, *ordered[:SCOPED_POLICY['reference_seeds']]]))
        if getattr(self.s, 'batch_reference_navigation', False):
            anchors.clear()  # Related originals are read only after grouped choices.
        scanned = set()
        references, ambiguous = [], []
        while anchors and len(scanned) < 96:
            anchor, depth = anchors.popleft()
            if anchor in scanned: continue
            scanned.add(anchor)
            self.check_time()
            if anchor not in self.allowed:
                continue
            rows = self.s.tools.db.execute('''SELECT DISTINCT r.json FROM reference r
                JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id=? ORDER BY r.id''', (anchor,))
            for row in rows:
                ref = json.loads(row[0])
                origin = self.s.tools.sources.get(ref['source_id'])
                if not origin or ref['source_id'] not in self.allowed:
                    continue
                frame, expected = ref.get('source_text'), ref.get('source_text_sha256')
                if not frame or not expected:
                    continue
                raw = self.s.store.source(origin['document_id'], ref['block_id'])
                if text_hash(frame) != expected or frame not in raw['text']:
                    raise ContractError('reference source witness mismatch')
                outgoing = ref['source_id'] == anchor
                targets = ref.get('target_source_ids', []) if outgoing else [ref['source_id']]
                if outgoing and not targets:
                    candidates = unresolved_coordinate_candidates(frame, ref.get('locator',''), self.s.matcher, self.s.scope)
                    if len(candidates)>16:
                        self.limits.append({'kind':'ambiguous_reference_limit','reference_id':ref['id'],'omitted_count':len(candidates)-16})
                    for sid in candidates[:16]:
                        self.add(sid, 0.01, {'kind':'ambiguous_coordinate_candidate','anchor':anchor,'reference_id':ref['id'],'witness_sha256':expected,'locator':ref.get('locator'),'canonical_approval':False})
                        ambiguous.append(sid)
                for sid in targets:
                    if sid == anchor or sid not in self.allowed:
                        continue
                    route = {'kind': 'reference', 'anchor': anchor, 'reference_id': ref['id'],
                             'direction': 'outgoing' if outgoing else 'incoming',
                             'witness_sha256': expected, 'resolution': ref.get('resolution')}
                    self.add(sid, .01, route)
                    related.append(sid)
                    references.append({**route, 'source_id': sid, 'depth': depth+1})
                    if depth == 0 and sid not in scanned:
                        anchors.append((sid, 1))
        # Keep lexical seeds and expand verified references without declaring legal applicability.
        related = sorted(set(related)-set(seeds), key=lambda sid: (self.s.tools.sources[sid]['document_id'] not in focus_documents, -self.scores[sid], sid))
        ambiguous = list(dict.fromkeys(ambiguous))
        if len(ambiguous)>32:
            self.limits.append({'kind':'ambiguous_request_limit','omitted_count':len(ambiguous)-32})
        selected = list(dict.fromkeys(seeds+ambiguous[:32]+related))[:SCOPED_POLICY['source_limit']]
        if len(self.scores) > len(selected):
            self.limits.append({'kind': 'source_limit', 'omitted_count': len(self.scores)-len(selected)})
        return selected, {'queries': query_receipts, 'matches': matches, 'references': references,
                          'discovered': sorted(self.scores), 'selected_for_read': selected,
                          'routes': dict(self.routes),'focus_documents':sorted(focus_documents),'ambiguous_reference_candidates':ambiguous}

    def discover(self):
        from .law_candidates import enabled, discover
        if enabled(self.s):
            return discover(self)
        if getattr(self.s.repo, 'VERSION', 5) == 6 or getattr(self.s.matcher, 'unit_fulltext', None) is not None:
            self.s.batch_reference_navigation = True
        if getattr(self.s.matcher,'unit_fulltext',None) is None:
            return self._discover_articles()
        from .unit_reading import discover
        return discover(self, self._discover_articles)

    def _discover_articles(self):
        from .structure_query import resolve
        from . import query_scope as qs, structure_selection as ss
        selected_sets = (qs.active(self.s) or {}).get('selections', [])
        route = ss.route(selected_sets, self.s.matcher, self.s.scope) if selected_sets else getattr(self.s, 'structure_query_route', None)
        if route is None:
            route = resolve(self.s.context.request['question'], self.s.matcher, self.s.scope)
        route = qs.filter_route(self.s, route)
        if route['status'] == 'MATCH' and not getattr(self.s, 'force_fulltext_recall', False):
            selected = route['source_ids']
            if set(selected) - self.allowed:
                raise ContractError('structural originals outside request scope')
            routes = {sid: [{'kind': 'exact_law_coordinate',
                            'query': self.s.context.request['question'], 'branch': 'structure'}]
                      for sid in selected}
            return selected, {'discovery_mode': 'structure', 'structure_query': route,
                'discovered': selected, 'selected_for_read': selected, 'routes': routes,
                'queries': [], 'parent_selections_preserved': True}
        from .source_recall_global import SourceRecall as GlobalRecall
        started = time.monotonic()
        obs.event(log, 'source_recall.discover.started', run_id=self.s.context.run_id)
        global_recall = GlobalRecall(self.s)
        global_selected, global_receipt = global_recall.discover()
        obs.event(log, 'source_recall.global.finished', run_id=self.s.context.run_id,
                  selected_count=len(global_selected), duration_ms=int((time.monotonic()-started)*1000))
        scoped_selected, scoped_receipt = self._scoped_discover()
        obs.event(log, 'source_recall.scoped.finished', run_id=self.s.context.run_id,
                  selected_count=len(scoped_selected), duration_ms=int((time.monotonic()-started)*1000))
        structural = route['source_ids'] if route['status'] == 'MATCH' else []
        selected = preserve_source_choices([structural,global_selected,scoped_selected],self.allowed,POLICY['source_limit'])
        scoped_limits = self.limits
        self.limits = [{'kind':'branch_limits','branch':name,'limits':limits}
                       for name,limits in [('global',global_recall.limits),('scoped',scoped_limits)]] if global_recall.limits or scoped_limits else []
        routes = defaultdict(list)
        for name,receipt in [('global',global_receipt),('scoped',scoped_receipt)]:
            for sid, values in receipt['routes'].items():
                routes[sid].extend({**value,'branch':name} for value in values)
        for sid in structural:
            routes[sid].append({'kind': 'exact_law_coordinate', 'query': self.s.context.request['question'], 'branch': 'structure'})
        return selected, {'discovery_mode': 'fulltext', 'structure_query': route,
            'discovered':sorted(set(structural)|set(global_receipt['discovered'])|set(scoped_receipt['discovered'])),
            'selected_for_read':selected,'routes':dict(routes),
            'queries':global_receipt['queries']+scoped_receipt['queries'],
            'branches':{'global':global_receipt,'scoped':scoped_receipt},
            'parent_selections_preserved':True}

    def prepare(self):
        from .law_candidates import enabled, prepare
        if enabled(self.s):
            return prepare(self)
        # Article FTS and unit FTS share the same structural READ contract.
        # Reference-only candidates are acquired after a typed group decision.
        from .query_scope import active
        if (getattr(self.s.matcher, 'unit_fulltext', None) is None and
                getattr(self.s.repo, 'VERSION', 5) != 6 and not (active(self.s) or {}).get('selections')):
            return self._legacy_prepare()
        self.s.batch_reference_navigation = True
        from .unit_reading import prepare
        return prepare(self)

    def _legacy_prepare(self):
        self.s.repo.event('SOURCE_RECALL_STARTED', {'policy': POLICY, 'policy_hash': digest(POLICY)})
        selected, discovery = self.discover()
        obs.event(log, 'source_recall.read.started', run_id=self.s.context.run_id,
                  selected_count=len(selected))
        queue = deque()
        for sid in selected:
            source = self.s.tools.sources[sid]
            target = self.s.handle('P', {'document_id': source['document_id'],
                                       'unit_id': source['unit_id'], 'source_id': sid})
            queue.append((sid, target, None))
        actions, chars = [], 0
        last_progress = time.monotonic()
        while queue:
            try:
                self.check_time()
                if (len(actions) >= POLICY['action_limit'] or
                        chars + self.s.profile['max_read_chars'] > POLICY['source_char_limit']):
                    raise BudgetExhausted('source recall action/character limit')
                sid, target, cursor = queue.popleft()
                action = {'tool': 'read', 'args': {'target': target, 'extent': 'article', 'cursor': cursor},
                          'reason': '시스템 정책: 검색 후보와 명시 참조의 정확 원문 확보',
                          'question_refs': [], 'expected_information': '조건·예외를 포함한 원문 전체, 법적 적용 판단은 별도'}
                # The existing reader enforces exact spans, current scope, generation and hashes.
                result = self.s.execute(action, 'source-recall-'+str(len(actions)+1), actor='SYSTEM_POLICY')
                chars += result.get('budget', {}).get('new_read_chars', 0)
                actions.append({'source_id': sid, 'action': action, 'result': result})
                if len(actions) == 1 or len(actions) % 10 == 0 or time.monotonic()-last_progress >= 5:
                    obs.event(log, 'source_recall.read.progress', run_id=self.s.context.run_id,
                              read_actions=len(actions), queued=len(queue), source_chars=chars,
                              duration_ms=int((time.monotonic()-self.start)*1000))
                    last_progress = time.monotonic()
                if result.get('next_cursor'):
                    queue.append((sid, target, result['next_cursor']))
                if result['status'] in ('ERROR', 'NOT_EXECUTED', 'DENIED'):
                    self.limits.append({'kind': 'read_failure', 'source_id': sid, 'reason': result.get('server_reason')})
            except (BudgetExhausted, DeadlineExceeded) as exc:
                self.limits.append({'kind': type(exc).__name__, 'reason': str(exc)})
                break
        evidence = self.s.repo.evidence()
        for e in evidence:
            self.s.source.verify(e)
        complete = [sid for sid in selected if spans_complete(self.s.tools.sources[sid], evidence)]
        packets = evidence_packets(self.s.context.request['question'], evidence, POLICY['packet_chars'])
        packet_evidence = [e for p in packets for e in p['evidence']]
        if {e['evidence_id'] for e in packet_evidence} != {e['evidence_id'] for e in evidence}:
            raise ContractError('source recall packet lost evidence')
        result = {**discovery, 'policy': POLICY, 'actions': actions, 'read_complete': complete,
                  'read_partial': sorted(({e['source_id'] for e in evidence} & set(selected)
                                          if discovery.get('discovery_mode') == 'structure'
                                          else {e['source_id'] for e in evidence})-set(complete)),
                  'prepared_complete': complete,
                  'source_chars': chars, 'packets': packets, 'limits': self.limits,
                  'actual_model_presented': [], 'seconds': time.monotonic()-self.start}
        self.s.repo.event('SOURCE_RECALL_FINISHED', {k: result[k] for k in
            ('read_complete', 'read_partial', 'prepared_complete', 'source_chars', 'limits', 'seconds')})
        obs.event(log, 'source_recall.finished', run_id=self.s.context.run_id,
                  read_actions=len(actions), read_complete_count=len(complete),
                  read_partial_count=len(result['read_partial']), source_chars=chars,
                  duration_ms=int(result['seconds']*1000))
        return result
