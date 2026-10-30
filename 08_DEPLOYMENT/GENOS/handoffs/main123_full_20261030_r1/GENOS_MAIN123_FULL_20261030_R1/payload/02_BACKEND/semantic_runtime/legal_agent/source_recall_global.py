"""Bounded source acquisition before LLM selection; no answer or relevance verdict."""
import json
import re
import time
from collections import defaultdict, deque

from ..fulltext import question_terms
from ..contracts import digest
from .repository import encoded, text_hash
from .errors import ContractError, BudgetExhausted
from .. import observability as obs
log=obs.get_logger('legal_agent.source_recall')

POLICY = {'query_top_k': 64, 'seed_limit': 64, 'reference_seeds': 16,
          'source_limit': 128, 'action_limit': 384, 'source_char_limit': 480000,
          'packet_chars': 50000}


def query_variants(question):
    """Unmodified fallback query; never infer intent from parentheses or a line."""
    return [question.strip()] if question.strip() else []


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
        catalogue=sources.tools.sources
        self.allowed = (catalogue.ids_for_documents(sources.scope) if hasattr(catalogue,'ids_for_documents') else
                        {sid for sid, source in catalogue.items() if source['document_id'] in sources.scope})
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

    def discover(self):
        q = self.s.context.request['question']
        query_receipts = []
        plan = getattr(self.s, 'recall_query_plan', {'queries': [], 'law_names': []})
        queries = list(dict.fromkeys(plan['queries'] or query_variants(q)))
        protected = []
        for variant in queries:
            self.check_time()
            terms = question_terms(variant)
            if not terms:
                continue
            if not self.s.capabilities.get('fulltext'):
                self.limits.append({'kind': 'fulltext_unavailable'})
                break
            ids = self.s.matcher.fulltext.rank(self.s.matcher.fulltext_db, terms, self.allowed)
            obs.event(log,'source_recall.query.finished',run_id=self.s.context.run_id,
                      query=variant,selected_count=min(len(ids),POLICY['query_top_k']))
            protected.extend(ids[:8])
            for i, sid in enumerate(ids[:POLICY['query_top_k']]):
                self.add(sid, 1 / (60+i+1), {'kind': 'fulltext', 'query': variant, 'rank': i+1})
            query_receipts.append({'query': variant, 'terms': terms, 'ranked_source_ids': ids,
                                   'kept_source_ids': ids[:POLICY['query_top_k']]})
        # Resolve composite coordinates inside named documents before loose title matches.
        from lawrag.core.legal_coordinate import find_coordinates
        normalize = lambda value: re.sub(r'\s+', '', value)
        explicit = []
        match_records = []
        for variant in queries:
            found = (getattr(self.s, 'question_matches', None)
                     if variant == q else None) or self.s.matcher.starts(variant, self.s.scope)
            named = {d['id'] for d in found['documents']}
            if not named:
                named = {did for did, name in self.s.matcher.documents.items()
                         if did in self.s.scope and name in plan['law_names']}
            exact = {normalize(c.coordinate.canonical_surface()) for c in find_coordinates(variant)}
            paired = []
            if named and exact:
                coordinates=self.s.matcher.stored_coordinates
                rows=(row for did in sorted(named) for row in coordinates.for_document(did)) if hasattr(coordinates,'for_document') else coordinates.items()
                for (did, uid), coord in rows:
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
        seeds = list(dict.fromkeys([*explicit, *protected, *ordered]))[:POLICY['seed_limit']]
        related = []
        anchors = deque((sid, 0) for sid in dict.fromkeys([*explicit, *ordered[:POLICY['reference_seeds']]]))
        if getattr(self.s, 'batch_reference_navigation', False):
            anchors.clear()  # Related originals are read only after grouped choices.
        scanned = set()
        references = []
        while anchors and len(scanned) < 64:
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
        related = sorted(set(related)-set(seeds), key=lambda sid: (-self.scores[sid], sid))
        selected = list(dict.fromkeys(seeds+related))[:POLICY['source_limit']]
        if len(self.scores) > len(selected):
            self.limits.append({'kind': 'source_limit', 'omitted_count': len(self.scores)-len(selected)})
        return selected, {'queries': query_receipts, 'matches': matches, 'references': references,
                          'discovered': sorted(self.scores), 'selected_for_read': selected,
                          'routes': dict(self.routes)}

    def prepare(self):
        self.s.repo.event('SOURCE_RECALL_STARTED', {'policy': POLICY, 'policy_hash': digest(POLICY)})
        selected, discovery = self.discover()
        queue = deque()
        for sid in selected:
            source = self.s.tools.sources[sid]
            target = self.s.handle('P', {'document_id': source['document_id'],
                                       'unit_id': source['unit_id'], 'source_id': sid})
            queue.append((sid, target, None))
        actions, chars = [], 0
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
                  'read_partial': sorted({e['source_id'] for e in evidence}-set(complete)),
                  'prepared_complete': complete,
                  'source_chars': chars, 'packets': packets, 'limits': self.limits,
                  'actual_model_presented': [], 'seconds': time.monotonic()-self.start}
        self.s.repo.event('SOURCE_RECALL_FINISHED', {k: result[k] for k in
            ('read_complete', 'read_partial', 'prepared_complete', 'source_chars', 'limits', 'seconds')})
        return result
