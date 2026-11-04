"""Closed ingress and durable run identity; user text cannot select Python code."""
from datetime import date
import hashlib
import json
import re

WORKFLOW_ID = 'risk_team_compare_workflow'
PREFIX = re.compile(r'^\s*대사\s*[:：]\s*')
FIELDS = {'workflow_id', 'workflow_version', 'question', 'q', 'user_id', 'team_id',
          'session_id', 'request_id', 'document_ids', 'as_of', 'use_llm',
          'input', 'return_to', 'public_question', 'memory', 'ad_session_id', 'ad_channel'}


class WorkflowError(ValueError):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.http_status = code, status


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def route(body):
    question = body.get('question', body.get('q', ''))
    marked = isinstance(question, str) and PREFIX.match(question)
    selected = body.get('workflow_id')
    if selected and isinstance(question,str) and re.match(r'^\s*(내규|외규)\s*[:：]',question):
        raise WorkflowError('WORKFLOW_ROUTE_CONFLICT', '단일 규정 조회 접두어와 workflow_id가 충돌합니다.')
    if marked and selected not in (None, WORKFLOW_ID):
        raise WorkflowError('WORKFLOW_ROUTE_CONFLICT', '대사 접두어와 workflow_id가 다릅니다.')
    return WORKFLOW_ID if marked else selected


def identity(value):
    if not isinstance(value, dict):
        raise WorkflowError('WORKFLOW_IDENTITY_REQUIRED', '실행 주체를 확인할 수 없습니다.', 403)
    for key in ('user_id', 'team_id'):
        if not isinstance(value.get(key), str) or not value[key].strip() or len(value[key]) > 256:
            raise WorkflowError('WORKFLOW_IDENTITY_REQUIRED', '안정적인 사용자·팀 식별자가 필요합니다.', 403)
    if not isinstance(value.get('document_ids'), list):
        raise WorkflowError('WORKFLOW_SCOPE_REQUIRED', '허용 문서 범위가 필요합니다.', 403)
    return {k: value[k] for k in ('user_id', 'team_id')} | {'document_ids': sorted(set(value['document_ids']))}


def request(body, principal, normalizer=None):
    if set(body) - FIELDS:
        raise WorkflowError('WORKFLOW_INPUT', '지원하지 않는 워크플로우 입력입니다.')
    principal = identity(principal)
    for key in ('user_id', 'team_id'):
        if key in body and body[key] != principal[key]:
            raise WorkflowError('WORKFLOW_PRINCIPAL', '인증된 실행 주체와 입력이 다릅니다.', 403)
    extra=normalizer(body,principal) if normalizer else {}
    if normalizer is None and "input" in body:raise WorkflowError("WORKFLOW_INPUT","이 워크플로우는 input을 지원하지 않습니다.")
    selected = route(body)
    if 'question' in body and 'q' in body and body['question']!=body['q']:
        raise WorkflowError('WORKFLOW_INPUT','question과 q가 다릅니다.')
    question = body.get('question', body.get('q', '' if normalizer else None))
    if not isinstance(question, str) or (not question.strip() and normalizer is None):
        raise WorkflowError('WORKFLOW_INPUT', '대사할 질문을 입력해 주세요.')
    question = PREFIX.sub('', question, count=1).strip()
    if not question and normalizer is None:
        raise WorkflowError('WORKFLOW_INPUT', '대사할 질문을 입력해 주세요.')
    for key in ('session_id', 'request_id'):
        if not isinstance(body.get(key), str) or not body[key].strip() or len(body[key]) > 256:
            raise WorkflowError('WORKFLOW_INPUT', key+'가 필요합니다.')
    use_llm = body.get('use_llm', True)
    if type(use_llm) is not bool:
        raise WorkflowError('WORKFLOW_INPUT', 'use_llm은 boolean이어야 합니다.')
    documents = body.get('document_ids', principal['document_ids'])
    if not isinstance(documents, list) or not documents or any(not isinstance(d, str) for d in documents):
        raise WorkflowError('WORKFLOW_SCOPE_REQUIRED', '문서 범위가 비어 있거나 잘못되었습니다.', 403)
    if set(documents) - set(principal['document_ids']):
        raise WorkflowError('WORKFLOW_SCOPE_DENIED', '허용 문서 범위를 벗어났습니다.', 403)
    as_of = body.get('as_of')
    if as_of is not None:
        try:
            if not isinstance(as_of, str) or date.fromisoformat(as_of).isoformat() != as_of:
                raise ValueError()
        except ValueError as exc:
            raise WorkflowError('WORKFLOW_INPUT', 'as_of는 YYYY-MM-DD 형식이어야 합니다.') from exc
    return_to = body.get('return_to')
    if return_to is not None and (not isinstance(return_to, dict) or set(return_to) != {'parent_run', 'step', 'call_id'}
                                 or any(not isinstance(v, str) or not v or len(v) > 256 for v in return_to.values())):
        raise WorkflowError('WORKFLOW_RETURN', '호출·복귀 위치가 잘못되었습니다.')
    if body.get('workflow_version') is not None and (not isinstance(body['workflow_version'],str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',body['workflow_version'])):
        raise WorkflowError('WORKFLOW_INPUT','워크플로우 버전 형식이 잘못되었습니다.')
    return {'workflow_id': selected, 'workflow_version': body.get('workflow_version'),
            'question': question, 'principal': {k: principal[k] for k in ('user_id','team_id')},
            'session_id': body['session_id'], 'request_id': body['request_id'],
            'document_ids': sorted(set(documents)), 'as_of': as_of, 'use_llm': use_llm, 'return_to': return_to, **extra}
