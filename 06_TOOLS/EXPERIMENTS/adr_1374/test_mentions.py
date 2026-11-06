"""Replay the actual failed raw selections and exercise both forms of the new contract."""
from copy import deepcopy
import gzip,json
from pathlib import Path
import pytest
from semantic_runtime.ontology_work import recorded_fields as rf, observations as obs
from semantic_runtime.legal_agent.errors import ContractError
ROOT=Path(__file__).resolve().parents[3]
P=next(ROOT.glob('04_EXPERIMENTS/ADR/ADR-1373*/artifacts/followup-conflict/canonical'))
def load(n):
    with gzip.open(P/n,'rt') as f:return json.load(f)
def fixture():
    original=load('001.json.gz')
    c=original['context']
    menu=rf.glossary_mentions(c['raw'],c['glossary_candidates'])
    schema=deepcopy(original['schema'])
    refs=schema['properties']['observations']['items']['properties']['glossary_refs']['items']['properties']['mention_refs']
    refs['items']={'anyOf':[{'enum':list(menu)},refs['items']]}
    key,=[k for k,x in menu.items() if x['quote']=='상법']
    return c['raw'],schema,menu,key
@pytest.mark.parametrize('n',range(1,6))
def test_all_old_errors_still_reject_with_real_option(n):
    raw,schema,menu,key=fixture();v=load(f'{n:03}-output.json.gz')
    with pytest.raises(ContractError,match=key):
        rf.restore(v,raw,schema,obs.restore_normalization,menu)
def test_selected_alias_restores_first_real_occurrence():
    raw,schema,menu,key=fixture();v=load('005-output.json.gz')
    for o in v['observations']:
        for link in o['glossary_refs']:
            link['mention_refs']=[key if r['quote']=='상법' else r for r in link['mention_refs']]
    canonical,receipt=rf.restore(v,raw,schema,obs.restore_normalization,menu)
    assert receipt['glossary_mention_choices']
    for o in canonical['observations']:
        for link in o['glossary_refs']:
            for r in link['mention_refs']:
                assert raw['index'][0]['text'][r['start']:r['end']]==r['quote']
def test_overlapping_mentions_are_distinct_and_bounded():
    raw={'index':[{'pointer':'/a','text':'aaa'}]}
    candidates={'candidates':[{'card':{'labels':[{'text':'aa'}]}}]}
    opts=rf.glossary_mentions(raw,candidates)
    assert [v['start'] for v in opts.values()]==[0,1]
    assert [v['occurrence'] for v in opts.values()]==[0,1]
    assert len(rf.glossary_mentions(raw,candidates,limit=1))==1
