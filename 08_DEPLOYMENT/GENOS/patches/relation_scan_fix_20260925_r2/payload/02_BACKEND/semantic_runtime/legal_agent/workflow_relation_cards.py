"""Read-only adapters over pinned indexes. No route registration or legal inference."""
import json
from collections import Counter
import logging
import sqlite3
import time
from ..contracts import digest
from .. import observability as obs
from .repository import text_hash
from .errors import ContractError

CODES = {'140301':'SYNONYM', '140302':'ANTONYM', '140303':'BROADER_TERM',
         '140304':'NARROWER_TERM', '140305':'RELATED_TERM'}
relation_log = obs.get_logger('relation_scan')


def notice(anchor, family, key, **values):
    return {'relation_id': 'REL'+digest([anchor, family, key])[:28], 'family': family,
        'source_evidence': [anchor] if anchor.startswith('E') else [], 'anchor': anchor,
        'direction': 'outgoing', 'predicate': 'UNKNOWN', 'role_status': 'HINT',
        'resolution': 'RESOLVED', 'targets': [], 'witness_spans': [], 'witness_verified': False,
        'scope_status': 'UNREVIEWED', 'canonical_approval': False, 'auto_eligible': False,
        'completion_required': False, **values}


class RelationCards:
    def __init__(self, sources):
        self.s = sources

    def target(self, sid, uid=None, blocks=None, path=None):
        s = self.s.tools.sources.get(sid)
        if not s or s['document_id'] not in self.s.scope:
            return None
        canonical = {b['block_id'] for b in s['blocks']}
        if blocks and not set(blocks) <= canonical:
            raise ContractError('relation target block outside canonical source')
        if uid is not None and (s['document_id'], str(uid)) not in self.s.matcher.units:
            return None
        if uid is not None and not blocks:
            lo,hi=self.s.matcher.units[(s['document_id'],str(uid))]['span']
            blocks=[b['block_id'] for b in s['blocks'] if lo<=int(b['block_id'])<hi]
            if not blocks: return None
        return {'document_id': s['document_id'], 'source_id': sid,
                'unit_id': str(uid) if uid is not None else s.get('unit_id'),
                'block_ids': blocks or None, 'unit_path': path or []}

    def references(self, anchor, direction='both'):
        e = self.s.repo.evidence(anchor)
        counts_by_source = {}
        for row in self.s.tools.db.execute('''SELECT DISTINCT r.json FROM reference r
            JOIN reference_end x ON x.reference_id=r.id WHERE x.source_id=? ORDER BY r.id''', (e['source_id'],)):
            r = json.loads(row[0]); outgoing = r['source_id']==e['source_id']
            flow = 'outgoing' if outgoing else 'incoming'
            if direction not in ('both', flow): continue
            source = self.s.tools.sources.get(r['source_id'])
            if not source or source['document_id'] not in self.s.scope:
                yield notice(anchor, 'reference', r['id'], direction=flow, resolution='SCOPE_RESTRICTED',
                    guidance_code='RESTRICTED_RELATION', completion_required=False)
                continue
            raw = self.s.store.source(source['document_id'], r['block_id'])
            frame = r.get('source_text'); expected = r.get('source_text_sha256')
            verified = bool(frame and expected)
            if verified and (text_hash(frame)!=expected or frame not in raw['text']):
                raise ContractError('reference witness hash/text mismatch')
            start = raw['text'].find(frame) if verified else -1
            # Repeated frame cannot provide a unique coordinate.
            verified = verified and raw['text'].find(frame, start+1)<0
            a, b = r.get('mention_start'), r.get('mention_end')
            mention_ok = verified and type(a) is int and type(b) is int and 0<=a<b<=len(frame)
            spans = []
            if verified:
                spans = [{'document_id': source['document_id'], 'block_id': r['block_id'],
                    'start_cp': start, 'end_cp': start+len(frame), 'text': frame,
                    'block_hash': text_hash(raw['text']), 'span_hash': text_hash(frame)}]
            origins = r.get('origins', [])
            official = 'official_delegation_lawgokr' in origins
            if outgoing and mention_ok:
                if not any(p['block_id']==r['block_id'] and p['start_cp']<start+b and start+a<p['end_cp'] for p in e['spans']):
                    continue
            elif outgoing and not any(p['block_id']==r['block_id'] for p in e['spans']):
                continue
            if not outgoing and r.get('target_block_ids') and not set(r['target_block_ids']) & {p['block_id'] for p in e['spans']}:
                continue
            ids = r.get('target_source_ids', []) if outgoing else [r['source_id']]
            targets = []
            for sid in ids:
                t = self.target(sid, r.get('target_unit_id' if outgoing else 'source_unit_id'),
                    r.get('target_block_ids' if outgoing else 'source_block_ids'),
                    r.get('target_unit_path' if outgoing else 'source_unit_path'))
                if t: targets.append(t)
            predicate = 'DELEGATES_TO' if official else 'ANNEX_REFERENCE' if 'raw_explicit_annex_hint' in origins else r.get('reference_role') or 'UNKNOWN'
            if r['source_id'] not in counts_by_source:
                query_started = time.monotonic()
                try:
                    counts = Counter()
                    for witness in self.s.tools.db.execute('''SELECT r.json FROM reference_end x
                        JOIN reference r ON r.id=x.reference_id WHERE x.source_id=?''', (r['source_id'],)):
                        item = json.loads(witness[0])
                        if item.get('source_id') == r['source_id']:
                            counts[(item.get('block_id'), item.get('source_text_sha256'))] += 1
                    counts_by_source[r['source_id']] = counts
                except sqlite3.OperationalError as exc:
                    now = time.monotonic()
                    scan_deadline = getattr(self.s, '_relation_scan_deadline', None)
                    interrupted = str(exc).lower() == 'interrupted'
                    failure_kind = ('REQUEST_DEADLINE' if interrupted and now >= self.s.context.deadline
                                    and (scan_deadline is None or self.s.context.deadline <= scan_deadline)
                                    else 'RELATION_SCAN_TIMEOUT' if interrupted and scan_deadline is not None and now >= scan_deadline
                                    else 'SQL_INTERRUPTED_UNKNOWN' if interrupted else 'SQL_OPERATIONAL_ERROR')
                    obs.event(relation_log, 'relation.query.interrupted' if interrupted else 'relation.query.failed', level=logging.ERROR,
                              step='reference_witness_count', failure_kind=failure_kind,
                              duration_ms=int((now-query_started)*1000),
                              scan_elapsed_ms=int((now-getattr(self.s, '_relation_scan_started', query_started))*1000),
                              scan_limit_ms=self.s.profile['relation_scan_seconds']*1000,
                              remaining_ms=max(0, int((min(scan_deadline or self.s.context.deadline, self.s.context.deadline)-now)*1000)),
                              error_type='OperationalError')
                    raise
                query_ms = int((time.monotonic()-query_started)*1000)
                if query_ms >= 100:
                    obs.event(relation_log, 'relation.query.slow', level=logging.WARNING,
                              step='reference_witness_count', duration_ms=query_ms,
                              scan_limit_ms=self.s.profile['relation_scan_seconds']*1000)
            count = counts_by_source[r['source_id']][(r['block_id'], expected)] if expected is not None else 0
            ambiguous = count != 1
            unique = len(ids)==len(targets)==1 and r.get('resolution') not in (None, 'UNRESOLVED')
            yield notice(anchor, 'reference', [r['id'], flow], reference_id=r['id'],
                predicate=predicate, reference_role=r.get('reference_role'),
                reference_role_basis=r.get('reference_role_basis'), origins=origins,
                direction=flow, targets=targets, witness_spans=spans, witness_verified=verified,
                mention_span={'start_cp':start+a,'end_cp':start+b} if mention_ok else None,
                role_status='AMBIGUOUS' if ambiguous else 'HINT' if predicate!='UNKNOWN' else 'UNKNOWN',
                resolution='SCOPE_RESTRICTED_OR_MISSING' if len(targets)!=len(ids) else r.get('resolution') or 'UNKNOWN',
                unresolved=not unique, from_source=r['source_id'], from_unit=r.get('source_unit_id'),
                completion_required=outgoing,
                auto_eligible=bool(targets),
                guidance_code='VERIFY_SOURCE_TARGET_SCOPE' if verified else 'WITNESS_NOT_VERIFIED')

    def terms(self, anchor):
        if anchor.startswith('T'):
            return [self.s.resolve(anchor, 'T')['term_id']]
        e = self.s.repo.evidence(anchor)
        # occurrence is a source-level link. Only terms actually present in this READ seed relations.
        return [r[0] for r in self.s.tools.db.execute('SELECT term_id FROM occurrence WHERE source_id=? ORDER BY term_id', (e['source_id'],))
                if self.s.tools.terms.get(r[0], {}).get('label') and self.s.tools.terms[r[0]]['label'] in e['text']]

    def definitions(self, anchor):
        tids = self.terms(anchor)
        labels = {self.s.tools.terms[t]['label'] for t in tids}
        if anchor.startswith('E'): labels.add('')
        for row in self.s.tools.db.execute('SELECT json FROM definition ORDER BY id'):
            d = json.loads(row[0]); source = self.s.tools.sources.get(d['source_id'])
            if not source or source['document_id'] not in self.s.scope: continue
            if d['key'] not in labels and not (anchor.startswith('E') and d['key'] in self.s.repo.evidence(anchor)['text']): continue
            yield notice(anchor, 'definition', d['id'], predicate='DEFINITION_LABEL_CANDIDATE',
                definition_id=d['id'], label=d['key'], scope_status=d.get('scope_status') or 'UNKNOWN',
                scope_hint=d.get('scope_hint'), targets=[self.target(d['source_id'])],
                guidance_code='VERIFY_DEFINITION_SCOPE')

    def term_relations(self, anchor):
        tids = set(self.terms(anchor)); seen = set()
        for tid in sorted(tids):
            for edge in self.s.tools.edges.get(tid, []):
                if edge['id'] in seen: continue
                seen.add(edge['id']); outgoing = edge['source']==tid
                other = edge['target'] if outgoing else edge['source']
                yield notice(anchor, 'term', edge['id'], predicate=CODES.get(edge.get('code'),edge.get('code') or 'UNKNOWN'),
                    relation_code=edge.get('code'), direction='outgoing' if outgoing else 'incoming',
                    subject=edge['source'], target_term=edge['target'], anchor_term=tid, neighbour_term=other, term_label=self.s.tools.terms[other]['label'],
                    source_status=edge.get('status'), guidance_code='TERM_NAVIGATION_HINT')

    def occurrences(self, anchor):
        for tid in self.terms(anchor):
            for row in self.s.tools.db.execute('SELECT source_id FROM occurrence WHERE term_id=? ORDER BY source_id', (tid,)):
                t = self.target(row[0])
                if t is None: continue
                yield notice(anchor, 'occurrence', [tid,row[0]], predicate='TERM_OCCURS_IN',
                    subject=tid, term_label=self.s.tools.terms[tid]['label'], targets=[t],
                    guidance_code='OCCURRENCE_NOT_APPLICABILITY')

    def structure(self, anchor):
        e = self.s.repo.evidence(anchor); did = e['document_id']
        uids = set()
        for span in e['spans']:
            uid = self.s.store.source(did,span['block_id'])['unit_id']
            if uid is not None: uids.add(str(uid))
        for uid in sorted(uids):
            unit = self.s.matcher.units.get((did, uid))
            if not unit: continue
            for (d,u), other in sorted(self.s.matcher.units.items()):
                if d!=did or u==uid: continue
                pred = 'PARENT' if u==unit['parent'] else 'CHILD' if other['parent']==uid else 'SIBLING' if other['parent']==unit['parent'] else None
                if pred:
                    yield notice(anchor, 'structure', [uid,u], predicate=pred,
                        targets=[{'document_id':did, 'unit_id':u, 'source_id':None, 'block_ids':None,'unit_path':[]}],
                        guidance_code='STRUCTURAL_CONTEXT_NOT_LEGAL_EFFECT')

    def concept_allowed(self,c):
        if c.get('source')!='dictionary': return True
        db=self.s.glossary.dbs['dictionary']
        row=db.execute('SELECT source FROM entry WHERE id=?',(c['node_id'],)).fetchone()
        if not row: return False
        if row['source']!='corpus_definition': return True
        scope=db.execute('SELECT document_id FROM corpus_definition WHERE id=?',(c['node_id'],)).fetchone()
        return bool(scope and scope[0] in self.s.scope)

    def concept_relations(self,anchor,c):
        if not self.concept_allowed(c):
            yield notice(anchor,'knowledge',['restricted',c['id']],resolution='SCOPE_RESTRICTED',guidance_code='RESTRICTED_DEFINITION')
            return
        offset=0
        while True:
            page=self.s.glossary.inspect(c['id'],limit=12,offset=offset)
            for r in page.get('relations',[]):
                neighbour=r.get('neighbour')
                allowed=not neighbour or self.concept_allowed(neighbour)
                yield notice(anchor,'knowledge',[c['id'],r.get('id') or digest(r)],
                    predicate=r.get('predicate') or 'UNKNOWN', direction=str(r.get('direction','UNKNOWN')).lower(),
                    source_status=r.get('status'),origin=r.get('origin'),
                    resolution='SCOPE_RESTRICTED' if not allowed else r.get('navigation_status') or 'UNKNOWN',
                    via_concept=c,neighbour_concept=neighbour if allowed else None,
                    guidance_code='SOURCE_KNOWLEDGE_UNAPPROVED')
            for d in page.get('definitions',[]):
                yield notice(anchor,'knowledge',['definition',c['id'],digest(d)],predicate='SOURCE_DEFINITION',
                    definition=d,via_concept=c,guidance_code='SOURCE_DEFINITION_NOT_LOCAL_APPLICABILITY')
            offset=page.get('next_offset')
            if offset is None: break
        db=self.s.glossary.dbs['dictionary']
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if c.get('source')=='dictionary' and {'sense_assertion','sense_candidate'}<=tables:
            for row in db.execute("""SELECT DISTINCT a.*,l.entry_id AS left_entry,r.entry_id AS right_entry
                FROM sense_assertion a JOIN sense_candidate l ON l.id=a.source JOIN sense_candidate r ON r.id=a.target
                WHERE l.entry_id=? OR r.entry_id=? ORDER BY a.id""",(c['node_id'],c['node_id'])):
                other=row['right_entry'] if row['left_entry']==c['node_id'] else row['left_entry']
                neighbour=self.s.glossary.card('dictionary',other)
                if not self.concept_allowed(neighbour):
                    yield notice(anchor,'knowledge',['sense',row['id']],resolution='SCOPE_RESTRICTED',guidance_code='RESTRICTED_SENSE')
                    continue
                yield notice(anchor,'knowledge',['sense',row['id']],predicate=row['value'],
                    axis=row['axis'],direction='outgoing' if row['left_entry']==c['node_id'] else 'incoming',
                    source_status=row['status'],scope_key=row['scope_key'],
                    evidence_reference_hash=digest(json.loads(row['evidence_json'])),
                    via_concept=c,neighbour_concept=neighbour,guidance_code='LEXICAL_OBSERVATION_NOT_APPROVED')

    def knowledge(self, anchor):
        if getattr(self.s.glossary,'connections',None) is None:
            yield notice(anchor,'knowledge','capability',resolution='CAPABILITY_UNAVAILABLE',role_status='UNKNOWN',guidance_code='KNOWLEDGE_READER_UNAVAILABLE')
            return
        if anchor.startswith('K'):
            cid=self.s.resolve(anchor,'K')['concept_id']
            source,node=self.s.glossary.known[cid]
            yield from self.concept_relations(anchor,self.s.glossary.card(source,node))
            return
        seen=set()
        for tid in self.terms(anchor):
            label=self.s.tools.terms[tid]['label']
            if not 2<=len(label)<=120: continue
            offset=0
            while True:
                page=self.s.glossary.lookup(label,limit=12,offset=offset)
                for c in page['concepts']:
                    if not self.concept_allowed(c): continue
                    yield notice(anchor,'knowledge',[tid,c['id']],predicate='LABEL_CONCEPT_CANDIDATE',
                        subject=tid,neighbour_concept=c,guidance_code='SHARED_LABEL_NOT_SAME_MEANING')
                    if c['id'] not in seen:
                        seen.add(c['id'])
                        yield from self.concept_relations(anchor,c)
                offset=page.get('next_offset')
                if offset is None: break
