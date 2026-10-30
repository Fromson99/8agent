"""Read projections and revision-bound operator actions for the ontology dashboard.

No publication/activation operation is exposed here. Gold transfer is an immutable
request in the existing work store; an external approved loader must apply it.
"""
from copy import deepcopy
import json
import logging

SECTIONS = ('conditions', 'calculations', 'outcomes', 'notes')
STATUS = {'INPUT': '생성 대기', 'DRAFT': '검토 대기', 'APPROVED': '내용 승인', 'REJECTED': '반려'}


def binding(document):
    return (document['bundle_id'], document['revision'], document['work_hash'], document['status'])


def project(document, previous=None):
    """Only explicit quotation, dependency and path membership become edges."""
    work = document['input']
    proposal = document.get('proposal') or {'components': [], 'paths': []}
    old = {c['id']: c for c in (previous or {}).get('proposal', {}).get('components', [])}
    nodes, edges = [], []
    for source in work['originals']:
        nodes.append({'id': 'source:' + source['id'], 'kind': '근거 원문',
                      'label': source['anchor']['label'], 'text': source['text'],
                      'data': source, 'changed': False})
    notes = {i for p in proposal['paths'] for i in p['notes']}
    for component in proposal['components']:
        cid = component['id']
        nodes.append({'id': 'component:' + cid, 'kind': '검토 요소',
                      'label': cid, 'text': component['text'], 'data': component,
                      'changed': previous is not None and old.get(cid) != component,
                      'review_note': cid in notes})
        for basis in component['basis']:
            edges.append({'from': 'source:' + basis['source'], 'to': 'component:' + cid,
                          'kind': '근거 인용', 'detail': basis['quote']})
        for dep in component['requires']:
            edges.append({'from': 'component:' + dep, 'to': 'component:' + cid,
                          'kind': '구성 의존', 'detail': '작성된 requires 관계'})
    for path in proposal['paths']:
        pid = 'path:' + path['id']
        nodes.append({'id': pid, 'kind': '업무 경로', 'label': path['title'],
                      'text': path['business_use'], 'data': path, 'changed': False})
        for section in SECTIONS:
            for cid in path[section]:
                edges.append({'from': 'component:' + cid, 'to': pid,
                              'kind': '경로 포함', 'detail': section})
    return {'nodes': nodes, 'edges': edges}


def component_diff(document, previous):
    if previous is None:
        return []
    before = {c['id']: c for c in (previous.get('proposal') or {}).get('components', [])}
    after = {c['id']: c for c in (document.get('proposal') or {}).get('components', [])}
    return [{'항목': key, '변경': '추가' if key not in before else '삭제' if key not in after else '수정',
             '이전': before.get(key, {}).get('text', '—'), '현재': after.get(key, {}).get('text', '—'),
             '근거·의존 변경': before.get(key, {}).get('basis') != after.get(key, {}).get('basis') or
                           before.get(key, {}).get('requires') != after.get(key, {}).get('requires')}
            for key in sorted(before.keys() | after.keys()) if before.get(key) != after.get(key)]


def scenario(limit, amount):
    """Synthetic UI arithmetic only. Never evaluates a legal recipe or writes it."""
    def evaluate(bound):
        if bound is None or amount is None:
            return 'UNKNOWN'
        if isinstance(bound, bool) or isinstance(amount, bool):
            return 'UNKNOWN'
        if not (0 <= bound <= 1000 and 0 <= amount <= 1000):
            return 'UNKNOWN'
        return 'TRUE' if amount <= bound else 'FALSE'
    return {'baseline': evaluate(100), 'scenario': evaluate(limit)}


class Dashboard:
    def __init__(self, workflow, *, demo=False):
        self.workflow = workflow
        self.demo = demo
        self.actor = workflow.actor

    def load(self, bid):
        d = self.workflow.load(bid)
        self.workflow.verify_sources(d['input'])
        return d

    def listing(self):
        # No global Streamlit cache: every browser identity gets fresh ACL checks.
        from semantic_runtime.legal_agent.errors import ContractError
        rows = []
        for row in self.workflow.repo.list():
            try:
                d = self.load(row['bundle_id'])
            except ContractError:
                logging.getLogger(__name__).warning('Ontology item withheld after source verification', exc_info=True)
                continue
            rows.append({**d, 'head': self.workflow.repo.head(d['bundle_id'])})
        return rows

    def previous(self, d):
        from semantic_runtime.ontology_work.repository import value
        from semantic_runtime.legal_agent.errors import ContractError
        r = self.workflow.repo
        with r.session() as c:
            row = r.execute(c, f"SELECT REV_NO,WORK_HASH_VAL FROM {r.tables['work']} WHERE BNDL_ID=:1 AND REV_NO<:2 ORDER BY REV_NO DESC",
                            (d['bundle_id'], d['revision'])).fetchone()
        if row is None:
            return None
        previous = self.workflow.store.get(value(row[1]))
        if previous['bundle_id'] != d['bundle_id']:
            raise ContractError('previous work identity mismatch')
        self.workflow.verify_sources(previous['input'])
        return {**previous, 'revision': int(row[0])}

    def events(self, bid):
        from semantic_runtime.ontology_work.repository import value
        from semantic_runtime.legal_agent.errors import ContractError
        self.load(bid)
        r = self.workflow.repo
        with r.session() as c:
            rows = r.execute(c, f"SELECT EVT_JSON_CN FROM {r.tables['event']} WHERE BNDL_ID=:1 ORDER BY REV_NO DESC,EVT_ID",
                             (bid,)).fetchmany(201)
            versions = r.execute(c, f"SELECT REV_NO,WORK_HASH_VAL FROM {r.tables['work']} WHERE BNDL_ID=:1 ORDER BY REV_NO DESC", (bid,)).fetchmany(201)
        permitted = set()
        for revision, key in versions[:200]:
            document = self.workflow.store.get(value(key))
            if document['bundle_id'] != bid:
                raise ContractError('history work identity mismatch')
            try:
                self.workflow.verify_sources(document['input'])
            except ContractError:
                continue
            permitted.add(int(revision))
        # Revision-zero activation events have no work binding; the current head
        # is shown separately. Never expose an unverified historical reason.
        items = [item for row in rows[:200] if (item := json.loads(value(row[0])))['revision'] in permitted]
        return sorted(items, key=lambda e: e['at'], reverse=True), len(rows) > 200

    def checked(self, expected):
        from semantic_runtime.legal_agent.errors import ContractError
        d = self.load(expected[0])
        if binding(d) != tuple(expected):
            raise ContractError('displayed revision changed; reload before applying')
        return d

    def review(self, expected, approve, reason):
        d = self.checked(expected)
        return self.workflow.review(d['bundle_id'], d['revision'], d['work_hash'], approve, reason)

    def save(self, expected, proposal):
        d = self.checked(expected)
        return self.workflow.save(d['input'], proposal, bundle_id=d['bundle_id'], expected_revision=d['revision'])

    def propose(self, expected):
        from semantic_runtime.legal_agent.errors import ContractError
        d = self.checked(expected)
        if d['status'] != 'INPUT':
            raise ContractError('only collected input without a draft can be generated here')
        return self.workflow.propose(d['input'], bundle_id=d['bundle_id'], expected_revision=d['revision'])

    def prepare_transfer(self, expected, model_reference, note):
        from semantic_runtime.legal_agent.errors import ContractError
        from semantic_runtime.ontology_work.schema import now
        d = self.checked(expected)
        if d['status'] != 'APPROVED' or not d.get('approval'):
            raise ContractError('exact content approval required')
        if not model_reference.strip() or not note.strip():
            raise ContractError('model reference and transfer note required')
        package = self.workflow.preview(d['bundle_id'])
        request = {'version': 'ontology-gold-transfer-request-v1', 'status': 'PREPARED_NOT_APPLIED',
                   'demo': self.demo, 'binding': list(expected), 'approval_ref': d['approval'],
                   'actor': self.actor, 'created_at': now(), 'model_reference': model_reference.strip(),
                   'model_reference_verification': 'OPERATOR_SUPPLIED_NOT_VERIFIED', 'note': note.strip(),
                   'work': deepcopy(d), 'compiled': package, 'head_at_preparation': self.workflow.repo.head(d['bundle_id']),
                   'remaining': ['모델·메타 승인 확인', '물리 테이블·컬럼 매핑', 'Dataiku SQL 적재', '원문·행수·해시 검증', '사용 판본 전환']}
        key = self.workflow.store.put(request)
        self.checked(expected)  # Do not report success if a concurrent edit won.
        return key, request
