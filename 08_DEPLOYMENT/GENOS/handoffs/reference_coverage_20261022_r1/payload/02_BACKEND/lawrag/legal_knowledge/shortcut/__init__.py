"""Read existing execution records without copying their facts or events."""
from ..contracts import require, digest


def execution_ref(repository, reference, principal):
    value = repository.investigation(reference['id'], principal)
    require(value['revision'] == reference['revision'] and digest(value) == reference['content_hash'],
            'KNOWLEDGE_STALE', '사건 기록이 변경되었습니다.', 409)
    return {'ref': reference, 'document_ids': list(value.get('documents', [])),
            'status': value.get('status', 'UNASSESSED'), 'role': 'EXECUTION_REFERENCE_ONLY'}
