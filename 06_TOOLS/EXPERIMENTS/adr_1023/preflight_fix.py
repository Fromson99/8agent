from common import *
from copy import deepcopy
C=ROOT/read(ART/'stage.json')['roots']['candidate'];tests=C/'05_TESTS/CONTRACTS'
p=tests/'test_selected_connection_scope_api.py';t=p.read_text().replace("assert self.first_target not in [o['target'] for o in view['tool_options']]", "assert not any(o['choice']=='FOLLOW_CONNECTION' and o['selected_scope']['structural_selection']['unit_id']=='1' for o in view['tool_options'])").replace("'target':self.first_target,'issue_id':'Q1'", "'target':'STALE_SCOPE_NOT_OFFERED','issue_id':'Q1'");p.write_text(t)
p=tests/'test_connection_cycle_guard.py';t=p.read_text()+'''

def test_execution_boundary_rejects_repeated_scope_even_with_injected_menu(monkeypatch):
    from semantic_runtime.legal_agent import law_navigation as nav, tool_availability as availability
    inv,data=setup(monkeypatch);a,_=scopes(inv,data)
    monkeypatch.setattr(cs,'preview',lambda *a:dict(status='COMPLETE',groups=[],connection_count=0))
    cs.accept(inv,a,data,'최초 조회');cs.inspect_directory(inv,a)
    inv.completion=False;inv.control=False;inv.policy['structure_first']=False
    inv.p['catalogue']={'query_fingerprint':'q'}
    monkeypatch.setattr(availability,'require_navigation',lambda *a:None)
    action={'id':'OLD','action':'FOLLOW_CONNECTION','identity':{'connection_scope':a}}
    decision={'next_action':'FOLLOW_CONNECTION','targets':['OLD'],'law_decisions':[],
        'branch_decisions':[],'notes':'','reason':'이미 본 범위 재조회'}
    before=deepcopy(inv.p['connection_directories'])
    with pytest.raises(ProposalError,match='already inspected'):
        nav.Investigation.execute_tool(inv,decision,{'sources':[]},{'OLD':action})
    assert inv.p['connection_directories']==before
''';p.write_text(t)
p=ART/'design-freeze.json';p.rename(ART/'design-freeze-r1-preflight.json')
save(ART/'preflight-correction.json',{'reason':'Synthetic API compared ephemeral T labels across model calls. They are remapped per presentation, so compare immutable structural scope identity instead; stale output injection uses an unavailable label. Add independent execution-boundary test with exact canonical old identity. Product code unchanged.', 'live_calls':0})
