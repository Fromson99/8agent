"""Real tool revisions differ from the immutable reserved menu revision."""
from copy import deepcopy
import json
import pytest
from semantic_runtime.legal_agent import request_repair as rr
from semantic_runtime.legal_agent.errors import ContractError
from test_contracts import investigation


def completed():
    inv,menu,events,budget=investigation()
    snapshot=rr.no_progress_recovery(inv)
    inv.p['state_version']+=1
    inv.p['turn']+=1
    rr.finish_no_progress_recovery(inv.p,snapshot[2])
    inv.p=json.loads(json.dumps(inv.p))
    menu['read']={'action':'READ_ARTICLES','identity':{'unit':'new'}}
    return inv,menu,events,budget


def test_completed_tool_version_survives_restart_and_allows_next_new_read():
    inv,menu,events,budget=completed()
    before=deepcopy(budget)
    assert inv.p['no_progress_recovery']['completed_state_version']==2
    next_view=rr.no_progress_recovery(inv)
    assert next_view and inv.p['no_progress_recovery']['state_version']==2
    assert inv.p['no_progress_recovery']['selection_count']==2
    assert rr.no_progress_recovery(inv)==next_view
    assert len(events)==2 and budget==before


@pytest.mark.parametrize('kind',['reserved_stale','completion_rollback','forged_completion','newer_work','legacy'])
def test_revision_mismatch_never_refreshes_recovery_allowance(kind):
    inv,menu,events,budget=completed()
    if kind=='reserved_stale':
        rr.no_progress_recovery(inv)
        inv.p['state_version']+=1
    elif kind=='completion_rollback':
        inv.p['state_version']-=1
    elif kind=='forged_completion':
        inv.p['no_progress_recovery']['completed_state_version']=0
    elif kind=='newer_work':
        inv.p['state_version']+=1
    else:
        inv.p['no_progress_recovery'].pop('completed_state_version')
    before=deepcopy(inv.p)
    if kind in ('newer_work','legacy'):
        assert rr.no_progress_recovery(inv) is None
    else:
        with pytest.raises(ContractError,match='state version'):
            rr.no_progress_recovery(inv)
    assert inv.p==before
