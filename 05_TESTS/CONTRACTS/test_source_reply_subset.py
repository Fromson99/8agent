"""ADR-1504 cm-001: an answer call with an unknown outcome made the guided answer show only the
originals a successful call had received; the publication check compared that subset with every
acquired original and the request ended with HTTP 500. A subset of exact spans, in delivery order,
is a valid source-only reply; changed, foreign, reordered or empty rows stay rejected."""
from copy import deepcopy

import pytest

from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError


def originals():
    from test_investigation_completion_adr0678 import sources
    first = sources()
    second = deepcopy(first)
    for s in second:
        s['source_id'] = s['source_id'] + '-b'
        for span in s.get('adopted_spans') or []:
            span['source_id'] = s['source_id']
    return first + second


def assessment(rows):
    a = {'claims': [], 'gaps': [], 'disposition': 'LIMITED_ANSWER',
         'issue_assessments': [{'issue_id': 'Q1', 'status': 'INSUFFICIENT', 'reason': '미확인'}],
         'answer_coverage': 'INSUFFICIENT', 'completion_contract': cc.V8,
         'source_excerpt_reply': cc.source_excerpt_reply(rows)}
    return a


def test_delivered_subset_is_a_valid_source_reply():
    every = originals()
    assert len(every) >= 2
    a = assessment(every[:1])
    cc.verify_source_excerpt_reply(a, every)
    cc.verify_source_excerpt_reply(assessment(every), every)


@pytest.mark.parametrize('change', ['reordered', 'foreign', 'duplicate', 'empty', 'text', 'confirmed', 'claim'])
def test_subset_reply_rejects_other_shapes(change):
    every = originals()
    a = assessment(every)
    rows = a['source_excerpt_reply']['sources']
    if change == 'reordered': rows.reverse()
    elif change == 'foreign': rows[0] = {**rows[0], 'source_id': 'other-team'}
    elif change == 'duplicate': rows.append(deepcopy(rows[0]))
    elif change == 'empty': rows.clear()
    elif change == 'text': rows[0]['span_receipts'][0]['text'] += '승인 가능'
    elif change == 'confirmed': a['source_excerpt_reply']['legal_conclusion_confirmed'] = True
    elif change == 'claim': a['claims'] = [{'text': '승인 가능'}]
    if change == 'reordered' and len(rows) < 2:
        pytest.skip('one original')
    with pytest.raises(ContractError):
        cc.verify_source_excerpt_reply(a, every)
