from copy import deepcopy
import gzip
import json
from pathlib import Path
import pytest
from semantic_runtime.legal_agent import need_continuity as nc
from semantic_runtime.legal_agent.output_contract import OutputContractError

raw_root = next(Path(__file__).resolve().parents[3].glob('04_EXPERIMENTS/ADR/ADR-1372*/artifacts/public-live/B03-12-reka/raw'))

@pytest.mark.parametrize('origin,expected', [('RESEARCH', ['SCOPE_USE_UNSUPPORTED_RANGE', 'NEED_CLAIM_LINK']),
                                              ('SOURCE_GOAL', ['SCOPE_USE_UNSUPPORTED_RANGE'])])
def test_dependent_need_reported_for_semantic_review_only(origin, expected):
    with gzip.open(raw_root/'call-008/response.json.gz','rt') as stream:
        raw = json.loads(json.load(stream)['choices'][0]['message']['content'])
    before = deepcopy(raw)
    ctx = {'needs': [dict(n, origin=origin) for n in raw['read_judgment_review']['needs']]}
    with pytest.raises(OutputContractError) as rejected:
        nc._validate_assigned_uses(raw, ctx)
    assert [i['code'] for i in rejected.value.issues] == expected
    if len(expected) == 2:
        detail = rejected.value.issues[1]
        assert detail['path'] == '/read_judgment_review/needs/1'
        assert detail['expected_constraint']['basis_refs'] == ['S5','S7']
        assert detail['expected_constraint']['claim_evidence_refs'] == ['S4','S6']
    assert raw == before == rejected.value.proposal
