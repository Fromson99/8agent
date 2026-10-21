"""Prospectively frozen finite lifecycle states; not a legal-answer holdout."""
from itertools import product
import pytest
from test_authority import WHO,BODY,review_body,service,generation
from semantic_runtime.basis_links.resolver import snapshot,targets

CASES=list(product(('BASIS','IMPLEMENTS','RELATED'),('PROPOSED','APPROVED','REJECTED','REVOKED'),('CURRENT_BASIS','HISTORICAL_ORIGIN')))

@pytest.mark.parametrize('kind,state,perspective',CASES)
def test_frozen_review_state_matrix(service,kind,state,perspective):
    proposed=service.propose(WHO,{**BODY,'kind':kind,'perspective':perspective})
    if state!='PROPOSED':
        action={'APPROVED':'approve','REJECTED':'reject','REVOKED':'revoke'}[state]
        if state=='REVOKED':
            service.review(WHO,review_body(proposed,request_id='a'))
            proposed=service.list(WHO)['items'][0]
        service.review(WHO,review_body(proposed,action,'r'))
    view=service.view(WHO)
    assert view['items'][0]['link']['status']==state
    snap=snapshot(service,WHO,['inside']);reads=targets(service,WHO,snap)
    eligible=state=='APPROVED' and kind!='RELATED' and perspective=='CURRENT_BASIS'
    assert bool(reads)==eligible
    assert not service.list({**WHO,'team_id':'unrelated'})['items']
    assert not service.list({**WHO,'document_ids':['inside']})['items']
    assert service.view(WHO)['snapshot_hash']==view['snapshot_hash']
