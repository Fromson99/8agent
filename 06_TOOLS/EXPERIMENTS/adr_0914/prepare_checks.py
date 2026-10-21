from pathlib import Path
import json,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
for name,source in [('test_api.py','adr_0912/test_api.py'),('test_policy.py','adr_0912/test_policy.py'),('test_completion_boundaries.py','adr_0913/test_completion_boundaries.py')]:shutil.copy2(R/'06_TOOLS/EXPERIMENTS'/source,T/name)
p=T/'test_policy.py';s=p.read_text().replace("{'evidence_id':'e','spans'", "{'source_id':'s','document_id':'d','evidence_id':'e','spans'")
s=s.replace("    i=object.__new__(Investigation);", "    from semantic_runtime.legal_agent import investigation_diagnostics\n    monkeypatch.setattr(investigation_diagnostics,'selection_report',lambda result:{'final_ids':result['final_ids']})\n    i=object.__new__(Investigation);")
s+='''

def test_governing_context_is_atomic_with_subordinate_rule(monkeypatch):
    e=lambda ident,text:{'evidence_id':ident,'source_id':'s','document_id':'d','spans':[{'text':text}]}
    selected={'complete':True,'source_id':'s','document_id':'d','evidence':[e('child','보고한다')]}
    context={**selected,'evidence':[e('parent','승인받은 경우')]}
    state={'selected':{'g':selected},'groups':{'g':{'status':'READ'}},'contexts':{'CONTEXT:p':context}}
    session=S(scope={'d'},source=S(verify=lambda evidence:None))
    monkeypatch.setattr(inventory,'_pack',lambda s,p,records,spans:[{'source_id':k,'spans':v} for k,v in spans.items()])
    original=deepcopy(state)
    sources,evidence,omitted=inventory.acquired_originals_for(session,state,100)
    assert {p['text'] for source in sources for p in source['spans']}=={'보고한다','승인받은 경우'}
    assert {e['evidence_id'] for e in evidence}=={'child','parent'} and not omitted
    assert inventory.acquired_originals_for(session,state,5)==([],[],['child','parent'])
    assert state==original
    context['evidence'][0]['document_id']='another-authorized-doc'
    session.scope.add('another-authorized-doc')
    with pytest.raises(ContractError,match='identity'):inventory.acquired_originals_for(session,state,100)
''';p.write_text(s)
s=(R/'06_TOOLS/EXPERIMENTS/adr_0913/live.py').read_text().replace('ADR-0913-answer-first-financial-scope','ADR-0914-answer-first-context-followup').replace('adr0913-','adr0914-');(T/'live.py').write_text(s)
s=(R/'06_TOOLS/EXPERIMENTS/adr_0913/observe.py').read_text().replace('ADR-0913-answer-first-financial-scope','ADR-0914-answer-first-context-followup');(T/'observe.py').write_text(s)
s=(R/'06_TOOLS/EXPERIMENTS/adr_0912/seal.py').read_text().replace('ADR-0912-answer-first-user-followup','ADR-0914-answer-first-context-followup').replace('adr_0912','adr_0914').replace('ADR-0912','ADR-0914')
s=s.replace("for arm in ('baseline','answer-first'):","for arm in ('retained',):").replace("if arm=='answer-first':","if arm=='retained':").replace("/(arm+'-r1')","/arm").replace("'candidate_id':arm+'-r1',","'candidate_id':arm,")
s=s.replace("'evidence_inventory','completion_execution')","'evidence_inventory','completion_execution','corrected_memory')")
s=s.replace('answer-first-binding.json','retained-binding.json')
s=s.replace("str((T/'test_policy.py').relative_to(R)),", "str((T/'test_policy.py').relative_to(R)),str((T/'test_completion_boundaries.py').relative_to(R)),")
s=s.replace("'05_TESTS/CONTRACTS/test_unified_legal_agent.py',",'')
s=s.replace("'live_order':['baseline','answer-first']","'live_order':['retained']")
s=s.replace("* (R/'05_TESTS/CONTRACTS').glob('*.py'),", "*[R/n.split('::')[0] for n in tests if n.startswith('05_TESTS/')],")
(T/'seal.py').write_text(s)
