"""Lossless ASSESS display references; never shorten or summarize source text.

The caller retains its canonical view, IDs, ACL and source receipts. This module
only factors exactly equal strings in the final model display. A round trip is
checked before the request can be sent.
"""
from collections import Counter
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError

VERSION = 'lossless-assessment-input-v2'
SUPPORTED_VERSIONS = ('lossless-assessment-input-v1', VERSION)
META = 'assessment_input'
REF = 'assessment_text_ref'
INSTRUCTIONS = ('일반 ASSESS의 current_facts는 현재 사실이다. 가정 검토에서는 current_case.facts와 current_case.scenario가 현재 사실과 가정이다. '
    'baseline_history와 중첩된 기존 질문·이전 판단은 원래 요구 범위와 변경 이력이며 현재 값이 아니다. '
    'assessment_text_ref는 assessment_input.texts의 같은 ID에 있는 전체 원문을 뜻한다. '
    '참조는 생략·요약이 아니며 끝의 조건·예외까지 읽는다. 같은 본문을 참조하더라도 문서·원문 ID·판본·역할은 서로 구분한다. '
    '가정 조건의 확정 계산값은 서버가 보존한다. 의미 판단과 실제 주장·근거 채택은 응답 스키마에 따라 작성한다.')


def applies(view, *, stage=None):
    return (stage or view.get('source_stage')) in ('memory-assess', 'memory-assess-repair')


def project(view, *, stage=None):
    if not applies(view, stage=stage):
        return deepcopy(view)
    if META in view or 'current_case' in view:
        raise ContractError('assessment input already projected or reserved field supplied')
    counts = Counter()

    def count(value):
        if isinstance(value, str):
            # A sharing threshold, not a text limit. Every character survives.
            if len(value) >= 80:
                counts[value] += 1
        elif isinstance(value, dict):
            if REF in value:
                raise ContractError('assessment text reference supplied before projection')
            for child in value.values():
                count(child)
        elif isinstance(value, list):
            for child in value:
                count(child)

    count(view)
    aliases = {value: 'T' + str(i) for i, value in enumerate(sorted(v for v, n in counts.items() if n > 1), 1)}

    def factor(value):
        if isinstance(value, str):
            return {REF: aliases[value]} if value in aliases else value
        if isinstance(value, dict):
            return {key: factor(child) for key, child in value.items()}
        if isinstance(value, list):
            return [factor(child) for child in value]
        return deepcopy(value)

    result = factor(view)
    moved = {}
    if 'hypothetical_scenario' in result:
        for key, destination in (('current_facts', 'facts'), ('hypothetical_scenario', 'scenario')):
            if key in result:
                moved[key] = destination
        result['current_case'] = {destination: result.pop(key) for key, destination in moved.items()}
    result[META] = {'version': VERSION, 'source_hash': digest(view), 'moved': moved,
                    'texts': [{'id': alias, 'text': value} for value, alias in aliases.items()]}
    if restore(result) != view:
        raise ContractError('assessment display lost source content')
    return result


def restore(projected):
    """Audit the exact input representation; not a model-output decoder."""
    value = deepcopy(projected)
    meta = value.pop(META, None)
    if not isinstance(meta, dict) or meta.get('version') not in SUPPORTED_VERSIONS or set(meta) != {'version', 'source_hash', 'moved', 'texts'}:
        raise ContractError('invalid assessment input receipt')
    table = {}
    for row in meta['texts']:
        if (not isinstance(row, dict) or set(row) != {'id', 'text'} or
                not isinstance(row['id'], str) or row['id'] in table or not isinstance(row['text'], str)):
            raise ContractError('invalid assessment text table')
        table[row['id']] = row['text']
    used = set()

    def expand(item):
        if isinstance(item, dict):
            if REF in item:
                if set(item) != {REF} or not isinstance(item[REF], str) or item[REF] not in table:
                    raise ContractError('unbound assessment text reference')
                used.add(item[REF])
                return table[item[REF]]
            return {key: expand(child) for key, child in item.items()}
        if isinstance(item, list):
            return [expand(child) for child in item]
        return item

    value = expand(value)
    moved = meta['moved']
    allowed = {'current_facts': 'facts', 'hypothetical_scenario': 'scenario'}
    if not isinstance(moved, dict) or any(allowed.get(key) != destination for key, destination in moved.items()):
        raise ContractError('invalid assessment current-case mapping')
    if moved:
        current = value.pop('current_case', None)
        if not isinstance(current, dict) or set(current) != set(moved.values()) or any(key in value for key in moved):
            raise ContractError('assessment current-case mapping changed')
        value.update({key: current[destination] for key, destination in moved.items()})
    if used != set(table) or digest(value) != meta['source_hash']:
        raise ContractError('assessment input content binding changed')
    return value
