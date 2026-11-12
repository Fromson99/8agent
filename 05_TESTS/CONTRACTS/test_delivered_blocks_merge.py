"""ADR-1504 RISK-CM-062/076/103: delivered_blocks re-read every block and re-merged all spans of the
source for each block, and every connection menu repeated it (up to 1,761 s CPU in one question).
The rule is unchanged: a block is delivered when the merged delivered spans cover its whole text."""
import random
from types import SimpleNamespace as S

import pytest

from semantic_runtime.legal_agent import unit_relations as rel
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.evidence_inventory import covers, intervals


TEXTS = {str(i): ('가나다라마바사아자차' * (1 + i % 3))[: 5 + i * 3] for i in range(12)}


class Store:
    def __init__(self):
        self.reads = 0

    def source(self, did, bid):
        self.reads += 1
        return {'text': TEXTS[str(bid)]}


def session(store):
    sources = {'s1': {'document_id': 'd', 'blocks': [{'block_id': b} for b in TEXTS]}}
    return S(tools=S(sources=sources), scope={'d'}, store=store)


def span(bid, lo, hi):
    return {'block_id': bid, 'start_cp': lo, 'end_cp': hi, 'text': TEXTS[bid][lo:hi]}


def former(spans):
    """The per-block rule before ADR-1504 (covers(expected(...)) for each block)."""
    out = set()
    for bid in {str(p['block_id']) for p in spans}:
        expected = [{'block_id': bid, 'start_cp': 0, 'end_cp': len(TEXTS[bid])}]
        if covers(expected, spans):
            out.add(bid)
    return out


@pytest.mark.parametrize('seed', range(40))
def test_same_blocks_as_the_former_per_block_rule(seed):
    rng = random.Random(seed)
    spans = []
    for _ in range(rng.randint(1, 30)):
        bid = rng.choice(list(TEXTS))
        n = len(TEXTS[bid])
        lo = rng.randint(0, n); hi = rng.randint(lo, n)
        spans.append(span(bid, lo, hi))
        if rng.random() < 0.3:
            spans.append(span(bid, 0, n))
    store = Store()
    got = rel.delivered_blocks(session(store), {'s1': spans})
    assert got == {'s1': former(spans)}
    assert store.reads == len({p['block_id'] for p in spans}), 'each block read once'


def test_split_spans_that_together_cover_a_block_count_as_delivered():
    bid = '5'; n = len(TEXTS[bid])
    got = rel.delivered_blocks(session(Store()), {'s1': [span(bid, 0, 4), span(bid, 4, n)]})
    assert got == {'s1': {bid}}
    got = rel.delivered_blocks(session(Store()), {'s1': [span(bid, 0, 4), span(bid, 5, n)]})
    assert got == {'s1': set()}


def test_changed_text_or_bad_range_is_still_rejected():
    with pytest.raises(ContractError):
        rel.delivered_blocks(session(Store()), {'s1': [{**span('3', 0, 4), 'text': '다른 글'}]})
    with pytest.raises(ContractError):
        rel.delivered_blocks(session(Store()), {'s1': [{'block_id': '3', 'start_cp': 4, 'end_cp': 2, 'text': ''}]})
    with pytest.raises(ContractError):
        rel.delivered_blocks(session(Store()), {'s1': [{**span('3', 0, 2), 'block_id': 'x'}]})


def test_merged_intervals_are_the_former_merge():
    spans = [span('7', 0, 3), span('7', 2, 9), span('7', 12, 14)]
    assert intervals(spans) == {'7': [[0, 9], [12, 14]]}
