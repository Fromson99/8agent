"""Request-bound read-only tool handlers; all locations originate in stored data."""
import json
import sqlite3
import time
from ..contracts import digest
from ..folder_navigation import normalized
from ..fulltext import question_terms
from . import tools_protocol as protocol
from .errors import ContractError, ProposalError, DeadlineExceeded
from .repository import encoded
from .source_tools import SourceSession
from .. import observability as obs

log = obs.get_logger('sources_prepare')


class ExplorationTools:
    def __init__(self, store, tools, glossary, matcher, repo, context, profile):
        with obs.step(log, 'sources.reader'):
            self.source = SourceSession(store, tools, glossary, matcher, repo, context, profile)
        self.store, self.tools, self.glossary, self.matcher = store, tools, glossary, matcher
        self.repo, self.context, self.profile = repo, context, profile
        self.scope = list(context.query['scope']['document_version_ids'])
        with obs.step(log, 'sources.folders', document_count=len(self.scope)):
            self.folders = {d: (matcher.document_catalogue[d].get('navigation_folder') or '미분류').strip('/') for d in self.scope}
        with obs.step(log, 'sources.root_handle'):
            self.root = self.handle('R', {'documents': self.scope})
        self.handlers = {name: getattr(self, name) for name in protocol.REGISTRY}
        self.capabilities = {name: True for name in self.handlers}
        self.capabilities['fulltext'] = getattr(matcher, 'fulltext', None) is not None
        if getattr(matcher, 'fulltext_db', None) is not None:
            matcher.fulltext_db.set_progress_handler(lambda: int(time.monotonic() >= context.deadline), 1000)
        checked = 0
        with obs.step(log, 'sources.structure_validate', unit_count=len(matcher.units),
                      document_count=len(self.scope)):
            for (did, uid), unit in matcher.units.items():
                if did in self.scope:
                    self.ancestors(did, uid)  # fail closed on missing parents / cycles
                    if not isinstance(unit.get('span'), list) or len(unit['span']) != 2:
                        raise ContractError('stored structure span missing')
                    checked += 1
        obs.event(log, 'sources.structure_ready', checked_count=checked)

    def handle(self, kind, identity):
        raw = encoded(identity)
        row = self.repo.db.execute('SELECT handle FROM navigation_handle WHERE kind=? AND identity_json=? AND binding_hash=?',
                                   (kind, raw, self.context.binding_hash)).fetchone()
        if row:
            return row[0]
        ident = kind+str(self.repo.db.execute('SELECT count(*) FROM navigation_handle WHERE kind=?', (kind,)).fetchone()[0]+1)
        self.repo.db.execute('INSERT INTO navigation_handle VALUES(?,?,?,?)', (ident, kind, raw, self.context.binding_hash))
        return ident

    def resolve(self, ident, kinds='RFDUPELT'):
        if not isinstance(ident, str) or not ident or ident[0] not in kinds:
            raise ProposalError('wrong handle type; expected '+kinds)
        if ident.startswith('E'):
            e = self.repo.evidence(ident)
            if e['document_id'] not in self.scope:
                raise ProposalError('evidence outside request scope')
            return {'document_id': e['document_id'], 'unit_id': e['unit_id'], 'source_id': e['source_id'], 'evidence_id': ident}
        row = self.repo.db.execute('SELECT * FROM navigation_handle WHERE handle=?', (ident,)).fetchone()
        if not row or row['binding_hash'] != self.context.binding_hash:
            raise ProposalError('unknown or cross-request handle')
        value = json.loads(row['identity_json'])
        if value.get('document_id') and value['document_id'] not in self.scope:
            raise ProposalError('handle outside request scope')
        if set(value.get('documents', []))-set(self.scope):
            raise ProposalError('scope outside request corpus')
        return value

    def ancestors(self, did, uid):
        chain, seen = [], set()
        while uid is not None:
            key = (did, str(uid))
            if key in seen or key not in self.matcher.units:
                raise ContractError('missing/cyclic stored parent')
            seen.add(key)
            chain.append(str(uid))
            uid = self.matcher.units[key]['parent']
        return list(reversed(chain))

    def location(self, target):
        n = self.resolve(target, 'RFDUPE')
        did = n.get('document_id')
        if not did:
            if n.get('folder'):
                chain = self.folder_chain(n['folder'])
                return {'scope_root': self.root, 'focus': target, 'parent': chain[-2] if len(chain)>1 else self.root,
                        'breadcrumb': [self.root]+chain}
            return {'scope_root': self.root, 'focus': target}
        uid = n.get('unit_id')
        path = self.ancestors(did, uid) if uid is not None else []
        document = self.handle('D', {'document_id': did})
        folders = self.folder_chain(self.folders[did])
        parent = self.handle('U', {'document_id': did, 'unit_id': path[-2]}) if len(path)>1 else document if path else folders[-1] if folders else self.root
        return {'scope_root': self.root, 'document': document, 'focus': target, 'parent': parent,
                'breadcrumb': [self.root]+folders+[document]+[self.handle('U', {'document_id': did, 'unit_id': u}) for u in path]}

    def folder_chain(self, folder):
        out = []
        for i in range(1, len(folder.split('/'))+1):
            prefix = '/'.join(folder.split('/')[:i])
            docs = sorted(d for d,p in self.folders.items() if p==prefix or p.startswith(prefix+'/'))
            out.append(self.handle('F', {'documents': docs, 'folder': prefix}))
        return out

    def node_card(self, did, uid, *, source_id=None, route=None):
        n = {'document_id': did, 'unit_id': str(uid) if uid is not None else None}
        if source_id:
            n['source_id'] = source_id
        target = self.handle('P' if source_id else 'U', n)
        if route:
            self.repo.db.execute('INSERT OR IGNORE INTO candidate_route VALUES(?,?)', (target, route))
        unit = self.matcher.units.get((did, str(uid)), {})
        return {'target': target, 'document_name': self.matcher.documents[did],
                'title': unit.get('title', ''), 'coordinate': unit.get('coordinate_key'),
                'surface': unit.get('surface'), 'branch': unit.get('coordinate_scope'),
                **self.location(target), 'content_read': False, 'citation_eligible': False,
                'routes': [{'route':r[0], 'decision':self.decision(r[0])} for r in self.repo.db.execute('SELECT route FROM candidate_route WHERE candidate=?', (target,))],
                'candidate_decision': self.decision(target),
                'read_action': {'tool': 'read', 'args': {'target': target, 'extent': 'subtree', 'cursor': None}, 'reason': '원문 확인'}}

    def decision(self, ident):
        try: return self.repo.head('intent', ident)['payload']['decision']
        except ProposalError: return 'ACTIVE'

    def docs_bounds(self, target):
        n = self.resolve(target, 'RFDU')
        docs = n.get('documents', [n['document_id']] if 'document_id' in n else [])
        bounds = self.matcher.units[(n['document_id'], n['unit_id'])]['span'] if n.get('unit_id') else None
        return docs, bounds

    def sources_in(self, target):
        docs, bounds = self.docs_bounds(target)
        ids = [sid for sid, s in self.matcher.sources.items() if s['document_id'] in docs]
        if bounds:
            lo, hi = bounds
            ids = [sid for sid in ids if any(lo <= int(b['block_id']) < hi for b in self.tools.sources[sid]['blocks'])]
        return ids

    def page(self, items, offset):
        size = self.profile['page_size']
        return items[offset:offset+size], offset+size if offset+size < len(items) else None

    def validate_action(self, action, offered=None):
        protocol.validate('ToolAction', action)
        args = action['args']
        handles = [args[k] for k in ('target', 'evidence') if k in args]+args.get('terms', [])
        for ident in handles:
            self.resolve(ident)
            if offered is not None and ident not in offered:
                raise ProposalError('handle was not offered in this view: '+ident)
        if 'target' in args:
            kinds = 'DUPE' if action['tool']=='read' else 'RFDUPE' if action['tool']=='browse' else 'RFDU'
            self.resolve(args['target'], kinds)
        if 'evidence' in args: self.resolve(args['evidence'], 'E')
        for t in args.get('terms', []): self.resolve(t, 'T')
        if action['tool'] == 'search' and args['mode'] == 'fulltext' and not self.capabilities['fulltext']:
            raise ProposalError('fulltext unavailable; choose literal/title or term tools')
        self.source.cursor_position(action)

    def execute(self, action, action_id):
        args_hash = digest({k:action[k] for k in ('tool','args')})
        old = self.repo.db.execute('SELECT * FROM action_receipt WHERE action_id=?', (action_id,)).fetchone()
        if old:
            if old['args_hash'] != args_hash:
                raise ProposalError('action ID reused with different arguments')
            return json.loads(old['result_json'])
        self.context.remaining()
        self.repo.reserve_tool()
        started = time.monotonic()
        evidence, next_position, extra = [], None, {}
        try:
            self.validate_action(action)
            key, offset = self.source.cursor_position(action)
            cached = None
            if action['tool']=='read':
                request_key = digest({'action': {k: action[k] for k in ('tool','args')}, 'binding': self.context.binding_hash})
                cached = self.repo.db.execute("SELECT result_json FROM observation WHERE request_key=? AND status IN ('OK','PARTIAL','REUSED') ORDER BY created_seq LIMIT 1", (request_key,)).fetchone()
            if cached:
                previous = json.loads(cached[0])
                items = previous['items']; evidence = [self.repo.evidence(e) for e in previous['evidence_ids']]
                extra = {k:v for k,v in previous.items() if k in ('coverage','coverage_key','resolved_location')}
                extra.update(status='REUSED', next_cursor=previous['next_cursor'])
            else:
                items, next_position, evidence, extra = self.handlers[action['tool']](action['args'], offset)
            status = extra.pop('status', 'OK' if items else 'EMPTY')
            error = None
        except ProposalError as exc:
            key = digest(action)
            items, status = [], 'DENIED'
            error = {'code': exc.code, 'explanation': str(exc), 'retryable': True}
        except sqlite3.OperationalError as exc:
            if time.monotonic() >= self.context.deadline:
                raise DeadlineExceeded('source tool deadline exceeded') from exc
            key, items, status = digest(action), [], 'ERROR'
            error = {'code': 'SOURCE_QUERY_ERROR', 'explanation': 'source query failed', 'retryable': True}
        result = {'action_id': action_id, 'tool': action['tool'], 'args_hash': args_hash, 'status': status,
                  'items': items, 'evidence_ids': [e['evidence_id'] for e in evidence],
                  'next_cursor': self.source.cursor(key, next_position) if next_position is not None else None,
                  'coverage': {'complete': next_position is None and status == 'OK',
                               'meaning': 'this operation only; not proof of regulatory absence'},
                  'error': error, 'budget': {'action_reserved': True, 'duration_ms': int((time.monotonic()-started)*1000)},
                  'target_binding': self.context.binding_hash, 'scope_root': self.root,
                  'provenance': {k:v for k,v in self.context.binding.items() if k in ('generation_id','store_sha256','index_sha256','glossary','domain_sha256','profile_sha256')}, **extra}
        result = self.repo.record_observation(action, result, evidence, verify=self.source.verify)
        with self.repo.transaction():
            if result.get('coverage_key'):
                self.repo.db.executemany('INSERT OR IGNORE INTO read_coverage VALUES(?,?)',
                    [(result['coverage_key'], e['evidence_id']) for e in evidence])
            self.repo.db.execute('INSERT INTO action_receipt VALUES(?,?,?)', (action_id, args_hash, encoded(result)))
        return result

    def browse(self, args, offset):
        target = args['target']; n = self.resolve(target, 'RFDUPE')
        relation, view = args['relation'], args['view']
        if relation == 'root':
            target, n = self.root, self.resolve(self.root)
        elif relation in ('document', 'parent'):
            loc = self.location(target)
            if relation not in loc:
                raise ProposalError('target has no '+relation)
            target = loc[relation]; n = self.resolve(target)
        depth = args['depth']
        if depth > self.profile['browse_depth_limit'] or (view != 'tree' and depth != 1):
            raise ProposalError('invalid browse depth')
        if 'documents' in n:
            if not n['documents']:
                return [], None, [], {'resolved_location': self.location(target)}
            if view == 'neighbors':
                raise ProposalError('collection has no neighbors')
            rows = self.source.navigator.catalogue(n['documents'], limit=500)['documents']
            # Catalogue pages are bounded; explicitly collect remaining pages.
            while len(rows) < len(n['documents']):
                more = self.source.navigator.catalogue(n['documents'], offset=len(rows), limit=500)['documents']
                if not more: break
                rows.extend(more)
            prefix = n.get('folder', '')
            folders, items = {}, []
            for d in rows:
                folder = (d.get('navigation_folder') or '미분류').strip('/')
                remaining = folder[len(prefix):].strip('/') if prefix else folder
                if view in ('children', 'tree') and remaining:
                    name = '/'.join(filter(None, (prefix, remaining.split('/')[0])))
                    folders.setdefault(name, []).append(d['id'])
                else:
                    handle = self.handle('D', {'document_id': d['id']})
                    items.append({'target': handle, 'name': d['name'], 'folder': folder, **self.location(handle),
                                  'content_read': False, 'citation_eligible': False})
            items = [{'target': self.handle('F', {'documents': sorted(ds), 'folder': name}), 'name': name,
                      'scope_root': self.root, 'content_read': False, 'citation_eligible': False} for name, ds in sorted(folders.items())]+items
            if view=='tree':
                expanded = []
                for item in items:
                    expanded.append({**item, 'depth': 1, **self.location(item['target'])})
                    if depth>1:
                        child_offset = 0
                        while child_offset is not None:
                            children, child_offset, _, _ = self.browse({**args, 'target':item['target'], 'relation':'self', 'depth':depth-1}, child_offset)
                            expanded.extend({**child, 'depth':child.get('depth',1)+1} for child in children)
                items = expanded
        else:
            did, focus = n['document_id'], n.get('unit_id')
            parent = self.matcher.units[(did, focus)]['parent'] if focus is not None else None
            items = []
            for (d, uid), unit in sorted(self.matcher.units.items(), key=lambda kv: (kv[1].get('span', [0])[0], kv[0])):
                if d != did: continue
                chain = self.ancestors(did, uid)
                relative = len(chain)-(chain.index(focus)+1 if focus in chain else 0)
                within = focus is None or (focus in chain and uid != focus)
                if view == 'neighbors':
                    include = focus is not None and unit['parent'] == parent and uid != focus
                elif view == 'children':
                    include = unit['parent'] == focus
                elif view == 'tree':
                    include = within and relative <= depth
                else:
                    include = within and (unit.get('family') in ('편', '장', '절', '관', '조') or
                                           unit.get('family', '').startswith(('article', 'chapter', 'section', 'kr_article', 'kr_chapter', 'kr_part', 'kr_section', 'kr_subsection')) or
                                           unit['parent'] is None)
                if include:
                    items.append({**self.node_card(did, uid), 'depth': relative, 'family': unit.get('family')})
        page, next_pos = self.page(items, offset)
        return page, next_pos, [], {'resolved_location': self.location(target)}

    def search(self, args, offset):
        docs, bounds = self.docs_bounds(args['target']); query = args['query']; mode = args['mode']
        route = self.handle('L', {'kind': 'search', 'query': query, 'target': args['target'], 'mode': mode})
        items, terms = [], []
        if mode == 'fulltext':
            terms = question_terms(query)
            ids = self.matcher.fulltext.rank(self.matcher.fulltext_db, terms, set(self.sources_in(args['target'])))
            for sid in ids:
                s = self.tools.sources[sid]
                if bounds:
                    block_text = ' '.join(b['text'] for b in s['blocks'] if bounds[0] <= int(b['block_id']) < bounds[1])
                    if not set(terms).intersection(question_terms(block_text)): continue
                    n = self.resolve(args['target']); items.append(self.node_card(n['document_id'], n['unit_id'], route=route))
                else:
                    items.append(self.node_card(s['document_id'], s.get('unit_id'), source_id=sid, route=route))
        elif mode == 'title':
            q = normalized(query)
            if not bounds:
                for did in docs:
                    if q in normalized(self.matcher.documents[did]):
                        d = self.handle('D', {'document_id': did})
                        items.append({'target': d, 'title': self.matcher.documents[did], **self.location(d), 'content_read': False})
            for (did, uid), u in self.matcher.units.items():
                if did in docs and (not bounds or bounds[0] <= u['span'][0] < bounds[1]) and q in normalized(u.get('title', '')):
                    items.append(self.node_card(did, uid, route=route))
        else:
            marks = ','.join('?' for _ in docs)
            for r in self.store.db.execute('SELECT document_id,block_id,unit_id,text FROM source_block WHERE document_id IN ('+marks+') ORDER BY document_id,CAST(block_id AS INTEGER)', docs):
                if bounds and not bounds[0] <= int(r['block_id']) < bounds[1]: continue
                if normalized(query) in normalized(r['text']):
                    items.append(self.node_card(r['document_id'], str(r['unit_id']), route=route))
        items = list({i['target']: i for i in items}.values())
        page, next_pos = self.page(items, offset)
        receipt = {'mode': mode, 'query': query, 'query_terms': terms, 'searched_target': args['target'],
                   'document_ids': docs, 'bounds': bounds, 'total_status': 'exact', 'total': len(items)}
        if mode == 'fulltext':
            receipt.update(tokenizer=self.matcher.fulltext.manifest['tokenizer'], ranking=self.matcher.fulltext.manifest['ranking'])
        return page, next_pos, [], {'search_receipt': receipt}

    def locate(self, args, offset):
        docs, bounds = self.docs_bounds(args['target'])
        found = self.matcher.starts(args['locator'], docs)
        named = {d['id'] for d in found['documents']}
        q = normalized(args['locator']); hits = {(r['document_id'], r['unit_id']) for r in found['structures'] if r['kind'] == 'LOCATOR'}
        from lawrag.core.legal_coordinate import find_coordinates
        coordinates = {normalized(c.coordinate.canonical_surface()) for c in find_coordinates(args['locator'])}
        if coordinates:
            hits = {key for key,c in getattr(self.matcher,'stored_coordinates',{}).items()
                    if c and key[0] in docs and normalized(c.canonical_surface()) in coordinates}
        for (did, uid), u in self.matcher.units.items():
            if not coordinates and did in docs and q in (normalized(u.get('coordinate_key') or ''), normalized(u.get('surface') or '')):
                hits.add((did, uid))
        items = []
        for did, uid in sorted(hits):
            u = self.matcher.units[(did, uid)]
            branch = u.get('coordinate_scope', 'unknown')
            if named and did not in named: continue
            if bounds and not bounds[0] <= u['span'][0] < bounds[1]: continue
            if args['branch'] != 'any' and not str(branch).startswith(args['branch']): continue
            items.append(self.node_card(did, uid))
        if not items and named and not coordinates and args['branch'] == 'any':
            items = [{'target': self.handle('D', {'document_id': did}), 'name': self.matcher.documents[did], 'content_read': False} for did in sorted(named)]
        page, next_pos = self.page(items, offset)
        return page, next_pos, [], {'status': 'OK' if len(items)==1 else 'UNRESOLVED' if items else 'EMPTY'}

    def match_terms(self, args, offset):
        docs, _ = self.docs_bounds(args['target'])
        rows = self.matcher.starts(args['text'], docs)['terms']
        if args['strategy'] == 'direct': rows = [r for r in rows if not r.get('bridged_from')]
        if args['strategy'] == 'bridge':
            rows = []
            for hit in self.matcher.body.match(args['text']):
                for everyday in self.matcher.index_labels.get(hit['key'], []):
                    if everyday.startswith(self.matcher.EVERYDAY_PREFIX):
                        for tid, code in self.matcher._bridge(everyday, docs):
                            rows.append({'id': tid, 'question_spans': [{k: hit[k] for k in ('start','end','text')}],
                                         'bridged_from': [{'everyday_term_id': everyday, 'relation_code': code}]})
        items = []
        for row in rows:
            routes = [self.handle('L', {'kind': 'term', 'term_id': row['id'], 'target': args['target'],
                       'matched_text': args['text'], 'spans': row['question_spans'], **b}) for b in row.get('bridged_from', [])]
            t = self.handle('T', {'term_id': row['id'], 'routes': routes, 'target': args['target']})
            term = self.tools.terms[row['id']]
            items.append({'term': t, 'label': term['label'], 'source': term.get('source'),
                          'question_spans': row['question_spans'], 'routes': routes,
                          'bridge': row.get('bridged_from', []), 'content_read': False})
        page, next_pos = self.page(items, offset)
        return page, next_pos, [], {}

    def term_occurrences(self, args, offset):
        allowed = set(self.sources_in(args['target'])); sets, routes_by_term = [], []
        for t in args['terms']:
            n = self.resolve(t, 'T')
            sets.append({r[0] for r in self.tools.db.execute('SELECT source_id FROM occurrence WHERE term_id=?', (n['term_id'],))} & allowed)
            routes_by_term.append(n['routes'] or [self.handle('L', {'kind': 'direct_term', 'term': t, 'target': args['target']})])
        ids = set.intersection(*sets) if args['match']=='all' else set.union(*sets)
        items = []
        for sid in sorted(ids):
            s = self.tools.sources[sid]; card = None
            routes = [r for found, routes in zip(sets, routes_by_term) if sid in found for r in routes]
            for route in routes:
                card = self.node_card(s['document_id'], s.get('unit_id'), source_id=sid, route=route)
            items.append({**card, 'terms': args['terms'], 'occurrence_extent': 'source'})
        page, next_pos = self.page(items, offset)
        return page, next_pos, [], {}

    def lookup_definition(self, args, offset):
        allowed = set(self.sources_in(args['target'])); items = []
        for row in self.tools.db.execute('SELECT json FROM definition ORDER BY id'):
            d = json.loads(row[0])
            if d['source_id'] in allowed and normalized(args['query']) in normalized(d['key']):
                s = self.tools.sources[d['source_id']]
                items.append({**self.node_card(s['document_id'], s.get('unit_id'), source_id=d['source_id']),
                              'term': d['key'], 'scope_status': d.get('scope_status')})
        local_count = len(items)
        if offset < local_count:
            page, nxt = self.page(items, offset)
            return page, nxt if nxt is not None else local_count, [], {'definition_kind': 'document'}
        if not 2 <= len(args['query'].strip()) <= 120: return [], None, [], {}
        page = self.glossary.lookup(args['query'], limit=min(12, self.profile['page_size']), offset=offset-local_count)
        return [{**c, 'navigation_hint_only': True, 'citation_eligible': False} for c in page['concepts']], (local_count+page['next_offset'] if page['next_offset'] is not None else None), [], {}

    def follow_reference(self, args, offset):
        from ..term_references import reference_targets
        e = self.repo.evidence(args['evidence']); items = []
        self.resolve(args['evidence'], 'E')
        has_candidates = bool(self.tools.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reference_candidate'").fetchone())
        for row in self.tools.db.execute('SELECT DISTINCT r.json FROM reference r JOIN reference_end x ON x.reference_id=r.id WHERE x.source_id=? ORDER BY r.id', (e['source_id'],)):
            r = json.loads(row[0]); outgoing = r['source_id'] == e['source_id']
            if r['source_id'] not in self.tools.sources or self.tools.sources[r['source_id']]['document_id'] not in self.scope:
                continue
            direction = 'outgoing' if outgoing else 'incoming'
            if args['direction'] not in ('both', direction): continue
            targets = reference_targets(r) if outgoing else [{
                'source_id': r['source_id'], 'unit_id': r.get('source_unit_id'),
                'unit_path': r.get('source_unit_path', []), 'block_ids': r.get('source_block_ids', []),
                'target_level': r.get('source_level')}]
            route = self.handle('L', {'kind': 'reference', 'reference_id': r.get('id'), 'direction': direction, 'evidence': args['evidence']})
            cards = []
            for target in targets:
                sid = target['source_id']
                if sid not in self.tools.sources: continue
                s = self.tools.sources[sid]
                if s['document_id'] not in self.scope: continue
                uid = target.get('unit_id')
                cards.append({**self.node_card(s['document_id'], uid or s.get('unit_id'),
                                               source_id=None if uid else sid, route=route),
                              'target_unit_path': target.get('unit_path', []),
                              'target_block_ids': target.get('block_ids', [])})
            candidates = []
            if outgoing and has_candidates:
                rows = self.tools.db.execute('''SELECT candidate_id,source_id,unit_id,unit_path,block_ids,target_level,basis
                    FROM reference_candidate WHERE reference_id=? ORDER BY ordinal,candidate_id''', (r['id'],))
                for candidate_id, sid, uid, unit_path, block_ids, level, basis in rows:
                    if sid not in self.tools.sources or self.tools.sources[sid]['document_id'] not in self.scope:
                        continue
                    source = self.tools.sources[sid]
                    candidates.append({**self.node_card(source['document_id'], uid or source.get('unit_id'),
                                                        source_id=None if uid else sid, route=route),
                                       'candidate_id': candidate_id, 'basis': basis, 'target_level': level,
                                       'target_unit_path': json.loads(unit_path or '[]'),
                                       'target_block_ids': json.loads(block_ids or '[]'),
                                       'content_read': False, 'citation_eligible': False})
            witness_read = outgoing and any(s['block_id']==r.get('block_id') and (r.get('source_text') or '\0') in s['text'] for s in e['spans'])
            items.append({'route': route, 'direction': direction, 'targets': cards, 'resolution': r.get('resolution'),
                          'resolution_state': r.get('resolution_state'), 'candidates': candidates,
                          'gap_kind': r.get('reason') if r.get('resolution_state') == 'DATA_GAP' else None,
                          'witness': r.get('source_text'), 'witness_read': witness_read, 'content_read': False,
                          'unresolved': not cards or len(cards) != len(targets)})
        page, next_pos = self.page(items, offset)
        return page, next_pos, [], {'status': 'UNRESOLVED' if any(i['unresolved'] for i in page) else 'OK' if page else 'EMPTY'}

    def read(self, args, offset):
        n = self.resolve(args['target'], 'DUPE')
        if 'evidence_id' in n:
            if args['extent'] != 'exact' or args['cursor']:
                raise ProposalError('E rehydration requires exact extent and no cursor')
            e = self.repo.evidence(n['evidence_id'])
            return [{'evidence': e['evidence_id'], 'text': e['text'], **self.location(args['target'])}], None, [e], {'status': 'REUSED'}
        did, uid, sid = n['document_id'], n.get('unit_id'), n.get('source_id')
        if args['extent']=='article':
            ids = self.matcher._unit_sources(did, uid) if uid is not None else []
            if len(ids) != 1: raise ProposalError('article does not resolve to one source')
            sid = ids[0]
        blocks = None
        if uid is None and sid is None:
            blocks = [r[0] for r in self.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)', (did,))]
        elif args['extent']=='exact' and uid is not None and not sid:
            blocks = [r[0] for r in self.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)', (did, uid))]
        node = {'document_id': did, 'unit_id': uid, 'source_id': sid, **({'block_ids': blocks} if blocks is not None else {})}
        evidence, nxt = self.source._read(node, offset)
        key = digest({'node': node, 'extent': args['extent']})
        # record_observation will persist evidence; union calculation includes this page.
        previous = [self.repo.evidence(r[0]) for r in self.repo.db.execute('SELECT evidence_id FROM read_coverage WHERE target_hash=?', (key,))]
        all_e = previous+evidence
        if blocks is None:
            if sid: blocks = [b['block_id'] for b in self.tools.sources[sid]['blocks']]
            else:
                lo, hi = self.matcher.units[(did, uid)]['span']
                blocks = [r[0] for r in self.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<?', (did,lo,hi))]
        complete = True
        for block in blocks:
            end = 0
            for start, stop in sorted((s['start_cp'],s['end_cp']) for e in all_e for s in e['spans'] if e['document_id']==did and s['block_id']==block):
                if start > end: break
                end = max(end, stop)
            if end < len(self.store.source(did, block)['text']): complete = False
        # Coverage links are installed after durable evidence storage by caller.
        return [{'evidence': e['evidence_id'], 'text': '\n'.join(s['text'] for s in e['spans']),
                 'text_hash': e['text_hash'], **self.location(args['target']), 'content_read': True} for e in evidence], nxt, evidence, {
                     'status': 'OK' if complete else 'PARTIAL', 'coverage_key': key,
                     'coverage': {'complete': complete, 'requested_extent': args['extent'], 'basis': 'union_of_exact_spans', 'truncated': nxt is not None}}

    def inspect(self, args, offset):
        section = args['section']
        if section == 'history':
            items = [{k:o.get(k) for k in ('observation_id','action','status','evidence_ids','next_cursor','error')}
                     for o in self.repo.observations(self.profile['max_tool_actions'])]
        elif section == 'budget': items = [self.repo.budget()]
        elif section == 'candidates':
            items = [{'target': r[0], 'identity': json.loads(r[1]), 'decision': self.decision(r[0])} for r in self.repo.db.execute("SELECT handle,identity_json FROM navigation_handle WHERE kind IN ('P','U','D','T','L')")]
        elif section == 'evidence':
            items = [{'evidence': e['evidence_id'], 'heading': e['metadata'].get('heading'), 'read_action': {
                'tool': 'read', 'args': {'target': e['evidence_id'], 'extent': 'exact', 'cursor': None}, 'reason': '원문 재제시'}} for e in self.repo.evidence()]
        else: items = self.repo.heads('intent' if section=='questions' else 'review')
        page, nxt = self.page(items, offset)
        return page, nxt, [], {}
