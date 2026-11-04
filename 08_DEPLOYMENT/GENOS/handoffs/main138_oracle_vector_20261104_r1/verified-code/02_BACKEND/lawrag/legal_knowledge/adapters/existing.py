"""Adapters borrow current authorities; no compiler, source or case-store copies."""
from hashlib import sha256
from ..contracts import KnowledgeError, require


class ExistingReferences:
    def __init__(self, source_store, *, wiki_repository=None, concept_resolver=None):
        self.store, self.wiki, self.concepts = source_store, wiki_repository, concept_resolver

    def resolve(self, ref, principal):
        if ref['kind'] in ('CONCEPT', 'DEFINITION'):
            require(self.concepts is not None, 'KNOWLEDGE_CAPABILITY', '용어·정의 조회 연결이 필요합니다.', 503)
            return self.concepts(ref, principal)
        require(self.wiki is not None, 'KNOWLEDGE_CAPABILITY', '기존 위키·사건 조회 연결이 필요합니다.', 503)
        # The existing authority performs lifecycle, evidence and ACL validation.
        if ref['kind'] == 'SHORTCUT':
            from ..shortcut import execution_ref
            return execution_ref(self.wiki, ref, principal)
        require(ref['kind'] == 'WIKI', 'KNOWLEDGE_REFERENCE', '지원하지 않는 참조입니다.')
        from semantic_runtime.legal_agent.corrected_memory import MemoryError
        try: value = self.wiki.current(ref['id'], ref['revision'], principal)
        except MemoryError as exc:
            raise KnowledgeError('KNOWLEDGE_NOT_FOUND', '기존 위키가 철회되었거나 현재 권한·판본에 맞지 않습니다.', 404) from exc
        require(value['hash'] == ref['content_hash'], 'KNOWLEDGE_INTEGRITY', '위키 버전 해시가 다릅니다.', 409)
        return {'ref': ref, 'document_ids': value['documents'], 'role': 'DISCOVERY_ONLY_NOT_LEGAL_EVIDENCE'}

    def verify_source(self, ref, principal, source_binding):
        require(ref['document_id'] in principal['document_ids'], 'KNOWLEDGE_NOT_FOUND', '근거에 접근할 수 없습니다.', 404)
        require(self.store.manifest['generation_id'] == source_binding['generation']
                and self.store.manifest['store_sha256'] == source_binding['store_sha256'],
                'KNOWLEDGE_SOURCE_BINDING', '원문 세대가 변경되었습니다.', 409)
        require(ref['version'] == ref['document_id'], 'KNOWLEDGE_SOURCE_VERSION', '문서 판본 ID가 다릅니다.', 409)
        self.store.check_unchanged()
        source = self.store.source(ref['document_id'], ref['locator'])
        require(sha256(source['text'].encode()).hexdigest() == ref['content_hash'],
                'KNOWLEDGE_SOURCE_HASH', '원문 위치·본문 해시가 다릅니다.', 409)
