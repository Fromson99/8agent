"""Edit, prepare, publish and query one authenticated review-knowledge authority."""
from copy import deepcopy
from datetime import datetime, timezone
import uuid
from ..contracts import (VERSION, KINDS, REF, ID, HASH, REV, TEXT, SOURCE, COMMAND,
                         obj, array, validate, validate_definition, references, visit_graph,
                         principal, authorize, require, KnowledgeError, digest)

NONNEG = {'type': 'integer', 'minimum': 0}
BINDING = obj(generation=ID, store_sha256=HASH, unit_index_sha256={'anyOf': [HASH, {'type': 'null'}]})
ARGUMENTS = {
    'save_draft': obj(object_id={'anyOf': [ID, {'type': 'null'}]}, expected_revision=NONNEG,
                      definition={'type': 'object'}),
    'prepare_publication': obj(refs=array(REF, 128), source_binding=BINDING, review_note=TEXT),
    'publish': obj(build_id=ID, build_hash=HASH, expected_revision=NONNEG),
    'rollback': obj(build_id=ID, build_hash=HASH, expected_revision=NONNEG, reason=TEXT),
    'retire': obj(expected_revision=REV, reason=TEXT),
    'feedback': obj(target=REF, request_ref=ID, reason=TEXT),
}


def ref(record):
    return {'kind': record['definition']['kind'], 'id': record['id'],
            'revision': record['revision'], 'content_hash': record['content_hash']}


class Service:
    def __init__(self, repository, reference_port):
        self.repo, self.references = repository, reference_port

    def limit_deadline(self, deadline):
        limit = getattr(self.repo.db, 'limit_deadline', None)
        if limit is not None: limit(deadline)

    @staticmethod
    def channel_key(who): return digest([who['tenant_id'], who['team_id'], 'review'])

    @staticmethod
    def envelope(who, documents=()):
        return {'tenant_id': who['tenant_id'], 'team_id': who['team_id'],
                'actor_id': who['user_id'], 'document_ids': sorted(set(documents)),
                'recorded_at': datetime.now(timezone.utc).isoformat()}

    def record(self, namespace, key, who, revision=None):
        record = self.repo.read(namespace, key, revision)
        require(record is not None, 'KNOWLEDGE_NOT_FOUND', '항목을 찾을 수 없습니다.', 404)
        authorize(record, who)
        return record

    def definition(self, reference, who):
        validate(reference, REF)
        value = self.record('definition', reference['id'], who, reference['revision'])
        require(ref(value) == reference, 'KNOWLEDGE_INTEGRITY', '고정한 지식 버전이 다릅니다.', 409)
        # Linked private histories keep the authority's current user-level ACL.
        for target in references(value['definition']):
            if target['kind'] not in KINDS:
                resolved = self.references.resolve(target, who)
                require(resolved.get('ref') == target and set(resolved['document_ids']) <= set(who['document_ids']),
                        'KNOWLEDGE_NOT_FOUND', '기존 기록에 접근할 수 없습니다.', 404)
        return value

    def operation(self, operation_id, who):
        key = digest([who['tenant_id'], who['team_id'], who['user_id'], operation_id])
        return self.record('operation', key, who)

    def command(self, who, command):
        principal(who)
        validate(command, COMMAND)
        operation, args = command['operation'], command['arguments']
        principal(who, 'edit' if operation in ('save_draft', 'feedback') else 'publish')
        validate(args, ARGUMENTS[operation])
        key = digest([who['tenant_id'], who['team_id'], who['user_id'], command['operation_id']])
        input_hash = digest(command)
        previous = self.repo.read('operation', key)
        if previous is not None:
            authorize(previous, who)
            require(previous['input_hash'] == input_hash, 'KNOWLEDGE_IDEMPOTENCY', '같은 작업 ID에 다른 입력을 보낼 수 없습니다.', 409)
            if previous['status'] == 'FAILED':
                e = previous['error']
                raise KnowledgeError(e['code'], e['message'], e['status'])
            self._authorize_result(previous['result'], who)
            return previous['result']
        try:
            with self.repo.transaction():
                result = getattr(self, '_'+operation)(who, args)
                self.repo.append('operation', key, {**self.envelope(who, result.get('document_ids', [])),
                    'input_hash': input_hash, 'operation_id': command['operation_id'],
                    'operation': operation, 'status': 'COMPLETE', 'result': result}, 0)
            return result
        except KnowledgeError as exc:
            # A transaction rollback preserves the old published head. An unknown
            # write outcome must be reconciled, never followed by another mutation.
            if exc.status < 500:
                with self.repo.transaction():
                    if self.repo.read('operation', key) is None:
                        self.repo.append('operation', key, {**self.envelope(who), 'input_hash': input_hash,
                            'operation_id': command['operation_id'], 'operation': operation, 'status': 'FAILED',
                            'error': {'code': exc.code, 'message': str(exc), 'status': exc.status}}, 0)
            raise

    @staticmethod
    def _authorize_result(value, who):
        if isinstance(value, dict):
            if {'tenant_id', 'team_id', 'document_ids'} <= set(value): authorize(value, who)
            for child in value.values(): Service._authorize_result(child, who)
        elif isinstance(value, list):
            for child in value: Service._authorize_result(child, who)

    def _documents(self, definition, who):
        docs = {s['document_id'] for s in definition['source_refs']}
        for policy in definition['content'].get('policies', []):
            docs.update(s['document_id'] for s in policy['source_refs'])
        for dependency in references(definition):
            record = (self.definition(dependency, who) if dependency['kind'] in KINDS
                      else self.references.resolve(dependency, who))
            require(dependency['kind'] in KINDS or record.get('ref') == dependency,
                    'KNOWLEDGE_INTEGRITY', '기존 지식 참조가 다릅니다.', 409)
            docs.update(record['document_ids'])
        require(docs <= set(who['document_ids']), 'KNOWLEDGE_NOT_FOUND', '접근 가능한 근거를 선택해 주세요.', 404)
        return docs

    def _save_draft(self, who, args):
        definition = validate_definition(deepcopy(args['definition']))
        key = args['object_id']
        previous = None
        if key is None:
            require(args['expected_revision'] == 0, 'KNOWLEDGE_REVISION', '새 항목의 기준 버전은 0입니다.', 409)
            key = 'lk:'+uuid.uuid4().hex
        else:
            previous = self.record('definition', key, who)
            require(previous['definition']['kind'] == definition['kind'], 'KNOWLEDGE_KIND', '항목 종류는 변경할 수 없습니다.')
        docs = self._documents(definition, who)
        private = bool(previous and previous.get('private_owner'))
        for target in references(definition):
            private = private or target['kind'] not in KINDS or bool(self.definition(target, who).get('private_owner'))
        return self.repo.append('definition', key, {**self.envelope(who, docs),
            'lifecycle': 'DRAFT', 'definition': definition,
            'private_owner': who['user_id'] if private else None}, args['expected_revision'])

    def _bundle(self, refs, who, source_binding):
        records, graph, external = {}, {}, {}
        def read(reference, chain=()):
            require(len(records) < 128 and len(chain) <= 16, 'KNOWLEDGE_SIZE', '게시 묶음의 의존 범위가 너무 큽니다.')
            key = reference['id']
            require(key not in chain, 'KNOWLEDGE_CYCLE', '순환 의존 관계를 수정해 주세요.')
            if key in records:
                require(ref(records[key]) == reference, 'KNOWLEDGE_REVISION', '같은 항목의 두 버전을 한 묶음에 넣을 수 없습니다.', 409)
                return
            record = self.definition(reference, who)
            records[key] = record; graph[key] = []
            definition = record['definition']
            sources = definition['source_refs'] + [s for p in definition['content'].get('policies', []) for s in p['source_refs']]
            for source in sources: self.references.verify_source(source, who, source_binding)
            for target in references(definition):
                if target['kind'] in KINDS:
                    graph[key].append(target['id']); read(target, (*chain, key))
                else:
                    resolved = self.references.resolve(target, who)
                    require(resolved.get('ref') == target and set(resolved['document_ids']) <= set(who['document_ids']),
                            'KNOWLEDGE_INTEGRITY', '기존 지식의 버전 또는 권한이 다릅니다.', 409)
                    external[digest(target)] = target
        for reference in refs: read(reference)
        visit_graph(graph)
        return records, list(external.values())

    def _prepare_publication(self, who, args):
        require(bool(args['refs']), 'KNOWLEDGE_EMPTY', '게시할 항목을 선택해 주세요.')
        selected = {}
        current = self.active(who)
        if current and current['status'] == 'PUBLISHED':
            previous = self.record('release', current['release_id'], who)
            require(previous['content_hash'] == current['release_hash'], 'KNOWLEDGE_INTEGRITY', '현재 게시 버전이 다릅니다.', 409)
            selected.update({r['id']: r for r in previous['refs']})
        selected.update({r['id']: r for r in args['refs']})
        records, external = self._bundle(list(selected.values()), who, args['source_binding'])
        docs = sorted({d for r in records.values() for d in r['document_ids']})
        build = self.repo.append('release', 'kl:'+uuid.uuid4().hex, {**self.envelope(who, docs),
            'private_owner': who['user_id'] if any(r.get('private_owner') for r in records.values()) else None,
            'schema_version': VERSION, 'status': 'PREPARED', 'refs': [ref(r) for r in records.values()],
            'external_refs': external, 'source_binding': args['source_binding'], 'review_note': args['review_note'],
            'semantic_status': 'HUMAN_REVIEW_RECORDED_NOT_LEGAL_CERTIFICATION'}, 0)
        self.repo.index(build['id'], records.values())
        return build

    def _publish(self, who, args):
        build = self.record('release', args['build_id'], who)
        require(build['content_hash'] == args['build_hash'], 'KNOWLEDGE_INTEGRITY', '게시 준비 버전이 다릅니다.', 409)
        self._bundle(build['refs'], who, build['source_binding'])
        key = self.channel_key(who)
        return self.repo.append('channel', key, {**self.envelope(who, build['document_ids']),
            'schema_version': VERSION, 'release_id': build['id'], 'release_hash': build['content_hash'],
            'source_binding': build['source_binding'], 'status': 'PUBLISHED',
            'reason': args.get('reason', '검토 후 게시')}, args['expected_revision'])

    def _rollback(self, who, args): return self._publish(who, args)

    def _retire(self, who, args):
        previous = self.record('channel', self.channel_key(who), who)
        return self.repo.append('channel', previous['id'], {**self.envelope(who, previous['document_ids']),
            'schema_version': VERSION, 'release_id': None, 'release_hash': None,
            'source_binding': previous['source_binding'], 'status': 'RETIRED', 'reason': args['reason']}, args['expected_revision'])

    def _feedback(self, who, args):
        target = self.definition(args['target'], who)
        return self.repo.append('feedback', 'kf:'+uuid.uuid4().hex,
            {**self.envelope(who, target['document_ids']), **args, 'status': 'PROPOSED',
             'origin_status': 'USER_REPORTED_REQUEST_REF_NOT_VERIFIED'}, 0)

    def listing(self, who, *, namespace='definition', after='', limit=24):
        principal(who)
        require(namespace in ('definition', 'release', 'feedback'), 'KNOWLEDGE_NAMESPACE', '지원하지 않는 목록입니다.')
        require(type(limit) is int and 1 <= limit <= 50, 'KNOWLEDGE_LIMIT', '목록 크기를 확인해 주세요.')
        rows = self.repo.page(namespace, who, after, limit)
        visible = []
        for row in rows:
            try:
                authorize(row, who)
                if namespace == 'definition': self.definition(ref(row), who)
            except KnowledgeError as exc:
                if exc.status == 404: continue
                raise
            visible.append(row)
        # Opaque cursor contains no inaccessible object ID or total count.
        from base64 import urlsafe_b64encode
        cursor = urlsafe_b64encode(rows[-1]['id'].encode()).decode() if len(rows) == limit else None
        return {'items': visible, 'next_cursor': cursor, 'scope': 'AUTHORIZED_PAGE_ONLY'}

    def active(self, who):
        value = self.repo.read('channel', self.channel_key(who))
        # Binding metadata has no titles or private source text. Document ACL is
        # checked per candidate, so an unrelated restricted item cannot block all.
        return value

    def plan(self, who, query, source_binding, *, context=None, facts=None, as_of=None):
        principal(who)
        binding = self.active(who)
        empty = {'schema_version': 'review-plan-v1', 'binding': None, 'items': [], 'unresolved': [],
                 'fallback_owner': 'EXISTING_RESEARCH_EXECUTOR', 'model_calls': 0}
        if binding is None or binding['status'] != 'PUBLISHED': return empty
        safe_binding = {k: binding[k] for k in ('id', 'revision', 'content_hash', 'release_id', 'release_hash', 'source_binding')}
        empty['binding'] = safe_binding
        if source_binding != binding['source_binding']:
            return {**empty, 'unresolved': ['SOURCE_BINDING_CHANGED']}
        build = self.repo.read('release', binding['release_id'])
        require(build and build['content_hash'] == binding['release_hash'], 'KNOWLEDGE_INTEGRITY', '게시 묶음이 다릅니다.', 409)
        allowed = {digest(r) for r in build['refs']}
        candidates = self.repo.candidates(build['id'], query)
        selected = []
        for candidate in candidates:
            require(digest(ref(candidate)) in allowed, 'KNOWLEDGE_INTEGRITY', '게시 색인의 참조가 다릅니다.', 409)
            try:
                authorize(candidate, who)
                records, _ = self._bundle([ref(candidate)], who, source_binding)
            except KnowledgeError as exc:
                if exc.status == 404:
                    empty['unresolved'].append('CANDIDATE_UNAVAILABLE'); continue
                raise
            selected.extend(records.values())
        from .planning import assemble
        return assemble(empty, selected, context or {}, facts or {}, as_of=as_of)

    def revalidate(self, usage, who, source_binding):
        """Recheck pinned knowledge and current ACL before publishing a response."""
        principal(who)
        for item in usage['bindings']:
            binding = item['binding']
            if not binding or not item['items']: continue
            require(binding['source_binding'] == source_binding, 'KNOWLEDGE_SOURCE_BINDING', '응답의 원문 결속이 변경되었습니다.', 409)
            active = self.active(who)
            require(active and active['status'] == 'PUBLISHED', 'KNOWLEDGE_RETIRED', '참조 지식 사용이 중지되었습니다.', 409)
            require(binding['id'] == self.channel_key(who), 'KNOWLEDGE_NOT_FOUND', '지식 범위가 다릅니다.', 404)
            build = self.repo.read('release', binding['release_id'])
            require(build and build['content_hash'] == binding['release_hash'], 'KNOWLEDGE_INTEGRITY', '게시 버전이 변경되었습니다.', 409)
            allowed = {digest(r) for r in build['refs']}
            selected = [i['ref'] for i in item['items']]
            require(all(digest(r) in allowed for r in selected), 'KNOWLEDGE_INTEGRITY', '응답의 지식 참조가 다릅니다.', 409)
            self._bundle(selected, who, source_binding)

    def impact(self, who, reference):
        principal(who)
        record = self.definition(reference, who)
        # Exact released dependency closure only; do not claim a complete global impact scan.
        binding = self.active(who); affected = []
        if binding and binding['release_id']:
            build = self.repo.read('release', binding['release_id'])
            for r in build['refs']:
                try: value = self.definition(r, who)
                except KnowledgeError as exc:
                    if exc.status == 404: continue
                    raise
                if any(d['id'] == reference['id'] for d in references(value['definition'])):
                    affected.append({'ref': ref(value), 'title': value['definition']['title']})
        return {'ref': ref(record), 'affected': affected, 'scope': 'CURRENT_RELEASE_DIRECT_DEPENDENCIES',
                'unresolved': ['미게시 초안·다른 채널의 영향은 포함하지 않습니다.']}
