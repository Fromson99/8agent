import json
import sqlite3
import pytest
from semantic_runtime.legal_agent.procedure_memory import ProcedureMemory
from semantic_runtime.legal_agent.corrected_memory import MemoryError
from test_online import online

P={'user_id':'u','team_id':'t','document_ids':['d']}

def memory(db,request='r',principal=P,binding=None):
    db.row_factory=sqlite3.Row
    return ProcedureMemory(db,principal,binding or {'generation':'g1'},request,lambda *args:None)

def test_only_completed_procedure_can_replay(tmp_path):
    db=sqlite3.connect(tmp_path/'p.db',isolation_level=None)
    m=memory(db);m.save('select','question',{'menu':['a']},{'chosen':'a'},decision='MODEL')
    assert memory(db,'r2').lookup('select','question',{'menu':['a']})[0] is None
    m.activate()
    assert memory(db,'r3').lookup('select','question',{'menu':['a']})[0]=={'chosen':'a'}

@pytest.mark.parametrize('change',['question','menu','source','owner','scope'])
def test_changed_contract_never_replays(tmp_path,change):
    db=sqlite3.connect(tmp_path/'p.db',isolation_level=None);m=memory(db)
    m.save('select','question',{'menu':['a']},{'chosen':'a'},decision='MODEL');m.activate()
    p={**P,'user_id':'other'} if change=='owner' else {**P,'document_ids':['d','e']} if change=='scope' else P
    n=memory(db,'r2',p,{'generation':'g2'} if change=='source' else None)
    result,event=n.lookup('select','changed' if change=='question' else 'question',{'menu':['b'] if change=='menu' else ['a']})
    assert result is None
    assert event['reason'] in ('EXPECTED_INPUT_CHANGED','SOURCE_OR_CONFIGURATION_CHANGED','NO_VERIFIED_PROCEDURE')
    if change in ('owner','scope'):assert event['expected_input'] is None

def test_corrupt_decision_fails_closed(tmp_path):
    db=sqlite3.connect(tmp_path/'p.db',isolation_level=None);m=memory(db)
    m.save('select','q',{}, {'chosen':'a'},decision='MODEL');m.activate()
    db.execute("UPDATE sw_procedure_step SET output_json='{}'")
    with pytest.raises(MemoryError):memory(db,'r2').lookup('select','q',{})

def test_reference_choice_rebinds_only_identical_current_menu(tmp_path):
    db=sqlite3.connect(tmp_path/'p.db',isolation_level=None);m=memory(db)
    menu={'anchor':'d:1','witness_hash':'h1','targets':[{'id':'R1','document':'d','unit':'2','extent':'subtree'}]}
    m.save('source-reference-batch-1','q',menu,{'choices':[{'id':'R1'}]},decision='MODEL');m.activate()
    assert memory(db,'r2').lookup('source-reference-batch-1','q',menu)[0]
    changed={**menu,'targets':[{'id':'R1','document':'d','unit':'3','extent':'subtree'}]}
    assert memory(db,'r3').lookup('source-reference-batch-1','q',changed)[0] is None
    assert db.execute('SELECT count(*) FROM sw_procedure_step').fetchone()[0]==1

def test_new_session_reexecutes_tools_and_reuses_only_decisions(online):
    client,t,p,runtime=online
    q='모의승인규정 제1조의 승인 대상은?'
    def ask(n):return client.post('/v1/rag/ask',json={'question':q,'session_id':'s'+str(n),'request_id':'r'+str(n)})
    first=ask(1);assert first.status_code==200,first.text
    initial=len(t.phases)
    second=ask(2);assert second.status_code==200,second.text
    assert t.phases[initial:]==['memory-assess','memory-compose'],t.phases[initial:]
    assert not any(x.startswith('domain-choice-') for x in t.phases)
    assert first.json()['run_id']!=second.json()['run_id']
    with sqlite3.connect(runtime/'case-memory/cases-v4.sqlite') as db:
        matches=[json.loads(x[0]) for x in db.execute('SELECT payload FROM sw_procedure_event')]
        assert any(x['phase']=='observe:READ' and x['status']=='MATCH' for x in matches)
        assert any(x['phase']=='observe:RECALL' and x['status']=='MATCH' for x in matches)
        assert db.execute('SELECT count(*) FROM sw_intake').fetchone()[0]==2

def test_current_case_correction_requires_decision(online):
    from test_memory_runtime_v2 import command
    client,t,p,runtime=online
    first=client.post('/v1/rag/ask',json={'question':'모의승인규정 제1조의 승인 대상은?','session_id':'s','request_id':'r1'})
    assert first.status_code==200,first.text
    t.command=command('FACT_UPDATE',target=first.json()['goal_id'],facts=[{'name':'기간','value':'8개월'}])
    n=len(t.phases)
    second=client.post('/v1/rag/ask',json={'question':'기간을 8개월로 정정','session_id':'s','request_id':'r2'})
    assert second.status_code==200,second.text
    assert t.phases[n:n+2]==['memory-resolve','memory-command-check']
    with sqlite3.connect(runtime/'case-memory/cases-v4.sqlite') as db:
        assert any(json.loads(x[0]).get('reason')=='CURRENT_CASE_STATE_REQUIRES_DECISION'
                   for x in db.execute('SELECT payload FROM sw_procedure_event'))
