"""Scoped metadata discovery and exact original spans. Reads do not need issues."""
import json
import sqlite3
import time
from ..contracts import digest
from ..folder_navigation import FolderNavigator, normalized
from . import protocol
from .errors import ContractError, DeadlineExceeded, ProposalError
from .repository import encoded, text_hash
from .. import observability as obs

log = obs.get_logger('source_reader')


class SourceSession:
    def __init__(self, store, tools, glossary, matcher, repo, context, profile):
        self.store, self.tools, self.glossary, self.matcher = store, tools, glossary, matcher
        self.repo, self.context, self.profile = repo, context, profile
        self.scope = context.query['scope']['document_version_ids']
        self._progress_read_locations = set()
        with obs.step(log, 'sources.navigator'):
            self.navigator = FolderNavigator(matcher, store)
        with obs.step(log, 'sources.sqlite_callbacks'):
            self.store.db.create_function('legal_normalized', 1, normalized, deterministic=True)
            self.store.db.set_progress_handler(lambda: int(time.monotonic() >= context.deadline), 1000)
            self.tools.request_deadline = context.deadline
            self.tools.db.set_progress_handler(lambda: int(time.monotonic() >= context.deadline), 1000)

    def handle(self, kind, identity):
        ident = kind+digest({'run': self.context.run_id, 'binding': self.context.binding_hash, 'kind': kind, 'identity': identity})[:24]
        self.repo.navigation_save('navigation_handle',
                             (ident, kind, encoded(identity), self.context.binding_hash))
        return ident

    def resolve(self, handle, kind):
        row = self.repo.navigation_row('navigation_handle', handle)
        if not row or row['kind'] != kind or row['binding_hash'] != self.context.binding_hash:
            raise ProposalError('unknown or cross-request navigation handle')
        identity = json.loads(row['identity_json'])
        did = identity if kind == 'D' else identity['document_id']
        if did not in self.scope:
            raise ProposalError('navigation outside request scope')
        return identity

    def cursor_position(self, action):
        base = {'tool': action['tool'], 'args': {k: v for k, v in action['args'].items() if k != 'cursor'}}
        key = digest(base)
        cursor = action['args'].get('cursor')
        if not cursor:
            return key, 0
        row = self.repo.navigation_row('navigation_cursor', cursor)
        if not row or row['operation_hash'] != key or row['binding_hash'] != self.context.binding_hash:
            raise ProposalError('cursor belongs to another operation, scope or request')
        return key, json.loads(row['position_json'])

    def cursor(self, key, position):
        token = 'P'+digest({'run': self.context.run_id, 'operation': key, 'position': position})[:28]
        self.repo.navigation_save('navigation_cursor',
                             (token, key, encoded(position), self.context.binding_hash))
        return token

    def node(self, did, uid=None, source_id=None):
        return self.handle('U', {'document_id': did, 'unit_id': uid, 'source_id': source_id})

    def source_card(self, sid):
        source = self.tools.sources[sid]
        if source['document_id'] not in self.scope:
            raise ProposalError('source outside request scope')
        return {'node': self.node(source['document_id'], source.get('unit_id'), sid),
                'document': self.handle('D', source['document_id']), 'document_name': source['document_name'],
                'heading': source.get('heading', ''), 'content_read': False}

    def reference_source_card(self, sid, unit_id=None, unit_path=None, block_ids=None):
        """참조 양 끝의 정확한 마디를 읽는 카드. 구조가 없을 때만 조 전체로 후퇴한다."""
        card = self.source_card(sid)
        if unit_id is not None:
            source = self.tools.sources[sid]
            card['node'] = self.node(source['document_id'], unit_id, None)
            card['read_extent'] = 'REFERENCE_PROVISION_SUBTREE'
            card['unit_path'] = unit_path or []
            card['block_ids'] = block_ids or []
        else:
            card['read_extent'] = 'REFERENCE_ARTICLE_FALLBACK'
        return card

    def verify(self, evidence):
        e = evidence
        if e['document_id'] not in self.scope or e['generation_id'] != self.context.query['generation_id']:
            raise ContractError('evidence scope/generation mismatch')
        source = self.tools.sources.get(e['source_id'])
        if not source or source['document_id'] != e['document_id']:
            raise ContractError('evidence source mismatch')
        block_ids = {b['block_id'] for b in source['blocks']}
        if any(span['block_id'] not in block_ids for span in e['spans']):
            raise ContractError('evidence block outside canonical source')
        raw_blocks = self.store.sources(e['document_id'], [span['block_id'] for span in e['spans']])
        for span, raw in zip(e['spans'], raw_blocks):
            if span['block_id'] not in block_ids:
                raise ContractError('evidence block outside canonical source')
            if (raw['source_artifact_sha256'] != e['source_artifact_hash'] or
                text_hash(raw['text']) != span['block_hash'] or
                not 0 <= span['start_cp'] < span['end_cp'] <= len(raw['text']) or
                raw['text'][span['start_cp']:span['end_cp']] != span['text'] or
                text_hash(span['text']) != span['span_hash']):
                raise ContractError('evidence exact-span mismatch')
        if text_hash('\n'.join(s['text'] for s in e['spans'])) != e['text_hash']:
            raise ContractError('evidence text hash mismatch')

    def _read(self, node, offset):
        did, uid, sid = node['document_id'], node['unit_id'], node['source_id']
        progress_key = (did, uid, sid, tuple(node.get('block_ids') or []))
        if did in self.scope and progress_key not in self._progress_read_locations:
            self._progress_read_locations.add(progress_key)
            source = self.tools.sources.get(sid) or {}
            if source.get('document_id') != did:
                source = {}
            labels=[]; current=str(uid) if uid is not None else None; seen=set()
            while current is not None:
                if current in seen: raise ContractError('read label parent cycle')
                seen.add(current);u=self.matcher.units.get((did,current),{})
                labels.append(u.get('surface') or u.get('title') or current)
                current=u.get('parent')
            heading=node.get('read_label') or ' '.join(reversed(labels)) or source.get('heading') or '문서 본문'
            self._progress_labels = getattr(self,'_progress_labels',{})
            self._progress_labels[progress_key]=heading
            obs.event(log, 'source.read.started', run_id=self.context.run_id,
                      document_id=did, document_name=source.get('document_name') or self.matcher.documents.get(did),
                      heading=heading)
        position = offset if isinstance(offset, dict) else {'block': 0, 'char': 0}
        block_offset, char_offset = position['block'], position['char']
        page_size = self.profile['page_size']
        segments = node.get('read_segments')
        if segments is not None:
            chosen = segments[block_offset:block_offset+page_size+1]
            rows = self.store.sources(did, [p['block_id'] for p in chosen])
            for p, row in zip(chosen, rows):
                if not 0 <= p['start_cp'] < p['end_cp'] <= len(row['text']):
                    raise ContractError('read segment outside original block')
        elif node.get('block_ids') is not None:
            ids = node['block_ids']
            rows = self.store.sources(did, ids[block_offset:block_offset+page_size+1])
        elif sid:
            source = self.tools.sources.get(sid)
            if not source or source['document_id'] != did:
                raise ProposalError('unknown source handle')
            ids = sorted({b['block_id'] for b in source['blocks']}, key=int)
            rows = self.store.sources(did, ids[block_offset:block_offset+page_size+1])
        else:
            unit = self.matcher.units.get((did, str(uid)))
            if unit is None:
                raise ProposalError('unknown stored node')
            lo, hi = unit['span']
            rows = [dict(r) for r in self.store.db.execute(
                'SELECT * FROM source_block WHERE document_id=? AND CAST(block_id AS INTEGER)>=? '
                'AND CAST(block_id AS INTEGER)<? ORDER BY CAST(block_id AS INTEGER) LIMIT ? OFFSET ?',
                (did, lo, hi, page_size+1, block_offset))]
        remaining = self.profile['max_read_chars']
        fragments, next_position = {}, None
        for n, row in enumerate(rows[:page_size]):
            text = row['text']
            floor = chosen[n]['start_cp'] if segments is not None else 0
            stop = chosen[n]['end_cp'] if segments is not None else len(text)
            start = max(floor, char_offset if n == 0 else 0)
            end = min(stop, start+remaining)
            if end > start:
                source_ids = [s for s in self.matcher._unit_sources(did, str(row['unit_id']))
                              if s in self.tools.sources and row['block_id'] in {b['block_id'] for b in self.tools.sources[s]['blocks']}]
                if sid:
                    source_ids = [sid]
                if len(source_ids) != 1:
                    raise ContractError('source block does not resolve to one canonical source')
                span = {'block_id': row['block_id'], 'start_cp': start, 'end_cp': end, 'text': text[start:end],
                        'block_hash': text_hash(text), 'span_hash': text_hash(text[start:end])}
                fragments.setdefault(source_ids[0], []).append(span)
                remaining -= end-start
            if end < stop:
                next_position = {'block': block_offset+n, 'char': end}
                break
            if n+1 < len(rows):
                next_position = {'block': block_offset+n+1, 'char': 0}
            else:
                next_position = None
            if remaining <= 0:
                break
        evidence = []
        for source_id, spans in fragments.items():
            s = self.tools.sources[source_id]
            meta = json.loads(self.store.db.execute('SELECT json FROM document WHERE document_id=?', (did,)).fetchone()[0])
            role = meta.get('evidence_role', 'reference')
            role = role if role in ('normative', 'interpretive', 'reference') else 'reference'
            e = {'source_id': source_id, 'document_id': did, 'unit_id': s.get('unit_id'),
                 'generation_id': self.context.query['generation_id'], 'source_artifact_hash': s['source_artifact_sha256'],
                 'text_hash': text_hash('\n'.join(p['text'] for p in spans)), 'role': role, 'temporal_status': 'unknown',
                 'metadata': {'document_name': s['document_name'], 'heading': s.get('heading', ''),
                              'read_location':getattr(self,'_progress_labels',{}).get(progress_key,s.get('heading','')),
                              'source_store_sha256': self.store.manifest['store_sha256']}, 'spans': spans}
            e['evidence_id'] = 'E'+digest(e)[:28]
            evidence.append(e)
        return evidence, next_position

    def execute(self, action):
        protocol.validate('ToolAction', action)
        self.context.remaining()
        self.repo.reserve_tool()
        key, offset = self.cursor_position(action)
        name, args = action['tool'], action['args']
        size = self.profile['page_size']
        items, evidence, next_position, status = [], [], None, 'OK'
        try:
            if name == 'list_documents':
                value = self.navigator.catalogue(self.scope, title_query=args['query'], offset=offset, limit=size)
                items = [{'document': self.handle('D', d['id']), 'name': d['name'], 'category': d['category'],
                          'folder': d.get('navigation_folder'), 'content_read': False} for d in value['documents']]
                next_position = value['next_offset']
            elif name in ('list_structure', 'locate_provision'):
                did = self.resolve(args['document'], 'D')
                units = [(u, v) for (d, u), v in self.matcher.units.items() if d == did]
                if name == 'locate_provision':
                    q = normalized(args['coordinate'])
                    units = [(u, v) for u, v in units if q in (normalized(v.get('coordinate_key') or ''), normalized(v.get('surface') or ''))]
                units.sort(key=lambda x: (x[1].get('span', [0])[0], x[0]))
                items = [{'node': self.node(did, u), 'title': v.get('title', ''), 'surface': v.get('surface', ''),
                          'coordinate': v.get('coordinate_key'), 'content_read': False} for u, v in units[offset:offset+size]]
                next_position = offset+size if offset+size < len(units) else None
                if name == 'locate_provision' and len(units) != 1:
                    status = 'UNRESOLVED' if units else 'NOT_FOUND'
            elif name == 'read_node':
                evidence, next_position = self._read(self.resolve(args['node'], 'U'), offset)
                items = [{'evidence_id': e['evidence_id'], 'text': '\n'.join(s['text'] for s in e['spans']),
                          'text_hash': e['text_hash'], 'source_id': e['source_id'], 'content_read': True} for e in evidence]
            elif name in ('search_text', 'search_subtree'):
                docs = [self.resolve(args['document'], 'D')] if name == 'search_text' and args['document'] else list(self.scope)
                bounds, bounds_args = '', []
                if name == 'search_subtree':
                    n = self.resolve(args['node'], 'U')
                    docs = [n['document_id']]
                    if n['unit_id'] is None:
                        raise ProposalError('subtree requires a stored structural node')
                    lo, hi = self.matcher.units[(docs[0], str(n['unit_id']))]['span']
                    bounds, bounds_args = ' AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<?', [lo, hi]
                marks = ','.join('?' for _ in docs)
                rows = self.store.db.execute('SELECT document_id,block_id,unit_id FROM source_block WHERE document_id IN ('+marks+
                    ') AND instr(legal_normalized(text),?)>0'+bounds+' ORDER BY document_id,CAST(block_id AS INTEGER) LIMIT ? OFFSET ?',
                    (*docs, normalized(args['query']), *bounds_args, size+1, offset)).fetchall()
                next_position = offset+size if len(rows) > size else None
                for row in rows[:size]:
                    ids = self.matcher._unit_sources(row['document_id'], str(row['unit_id']))
                    items.append({'document': self.handle('D', row['document_id']),
                                  'node': self.node(row['document_id'], row['unit_id'], ids[0] if len(ids) == 1 else None),
                                  'block_id': row['block_id'], 'content_read': False})
            elif name == 'lookup_definition':
                marks = ','.join('?' for _ in self.scope)
                local_count = self.tools.db.execute('SELECT count(*) FROM definition WHERE document_id IN ('+marks+
                    ') AND instr(json_extract(json,\'$.key\'),?)>0', (*self.scope, args['query'])).fetchone()[0]
                if offset < local_count:
                    rows = self.tools.db.execute('SELECT json FROM definition WHERE document_id IN ('+marks+
                        ') AND instr(json_extract(json,\'$.key\'),?)>0 ORDER BY id LIMIT ? OFFSET ?',
                        (*self.scope, args['query'], size, offset)).fetchall()
                    for row in rows:
                        d = json.loads(row[0])
                        items.append({**self.source_card(d['source_id']), 'term': d['key'], 'scope_status': d.get('scope_status')})
                    next_position = offset+len(rows)
                elif 2 <= len(args['query'].strip()) <= 120:
                    page = self.glossary.lookup(args['query'], limit=min(12, size), offset=offset-local_count)
                    items = [{**card, 'navigation_hint_only': True, 'content_read': False} for card in page['concepts']]
                    next_position = local_count+page['next_offset'] if page['next_offset'] is not None else None
            elif name == 'follow_reference':
                from ..term_references import reference_targets
                e = self.repo.evidence(args['evidence_id'])
                rows = self.tools.db.execute('SELECT r.json FROM reference r JOIN reference_end x ON x.reference_id=r.id WHERE x.source_id=? ORDER BY r.id', (e['source_id'],)).fetchall()
                refs = []
                for row in rows:
                    r = json.loads(row[0])
                    outgoing = r['source_id'] == e['source_id']
                    if outgoing != (args['direction'] == 'outgoing'):
                        continue
                    targets = reference_targets(r) if outgoing else [{
                        'source_id': r['source_id'], 'unit_id': r.get('source_unit_id'),
                        'unit_path': r.get('source_unit_path', []), 'block_ids': r.get('source_block_ids', [])}]
                    allowed = [target for target in targets if target['source_id'] in self.tools.sources
                               and self.tools.sources[target['source_id']]['document_id'] in self.scope]
                    refs.append({'reference_id': r.get('id'), 'direction': args['direction'],
                                 'locator': r.get('locator'), 'resolution': r.get('resolution'),
                                 'reference_role': r.get('reference_role', 'CITES'),
                                 'reference_role_basis': r.get('reference_role_basis'),
                                 'witness': {'block_id': r.get('block_id'), 'text': r.get('source_text'),
                                             'text_sha256': r.get('source_text_sha256')},
                                 'targets': [self.reference_source_card(
                                     target['source_id'], target.get('unit_id'), target.get('unit_path', []),
                                     target.get('block_ids', [])) for target in allowed],
                                 'unresolved': not allowed or len(allowed) != len(targets), 'content_read': False})
                items = refs[offset:offset+size]
                next_position = offset+size if offset+size < len(refs) else None
                if any(r['unresolved'] for r in items):
                    status = 'UNRESOLVED'
            elif name == 'inspect_work':
                items = self.repo.heads()
            if not items:
                status = 'NOT_FOUND'
            if next_position is not None and name == 'read_node':
                status = 'TRUNCATED'
            self.context.remaining()
        except sqlite3.OperationalError as exc:
            if time.monotonic() >= self.context.deadline:
                raise DeadlineExceeded('source query deadline exceeded') from exc
            status, items, evidence = 'ERROR', [], []
        result = {'status': status, 'items': items, 'evidence_ids': [e['evidence_id'] for e in evidence],
                  'next_cursor': self.cursor(key, next_position) if next_position is not None else None,
                  'coverage': {'document_ids': list(self.scope), 'complete': next_position is None and status not in ('ERROR','UNRESOLVED'),
                               'meaning': 'this operation only; not proof of regulatory absence'},
                  'error_code': 'SOURCE_QUERY_ERROR' if status == 'ERROR' else None}
        return self.repo.record_observation(action, result, evidence, verify=self.verify)
