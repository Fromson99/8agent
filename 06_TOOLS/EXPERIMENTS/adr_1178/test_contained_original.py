from types import SimpleNamespace as NS
from copy import deepcopy
from pathlib import Path
import json,gzip,sqlite3
import pytest
from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.legal_agent import source_goal_control as sg,unit_reading
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.source_tools import SourceSession
from semantic_runtime.structure_navigation import stored_coordinate
from common import ROOT,ART,put

def fixture(monkeypatch):
    units={('d','9'):{'parent':None,'coordinate_scope':'body'},('d','14'):{'parent':'9','coordinate_scope':'body'}}
    coords={('d','9'):find_coordinates('제9조')[0].coordinate,('d','14'):find_coordinates('제9조제14항')[0].coordinate}
    spans=[{'block_id':str(i),'start_cp':0,'end_cp':2,'text':'원문'} for i in range(4)]
    e={'source_id':'s','document_id':'d','spans':spans};events=[];verified=[]
    def verify(x):
        if any(p['text']!='원문' for p in x['spans']):raise ContractError('evidence exact-span mismatch')
        verified.append(x)
    inv=NS(s=NS(scope={'d'},matcher=NS(units=units,stored_coordinates=coords,sources={'s':{'document_id':'d','unit_id':'9'}}),store=NS(source=lambda did,b:{'text':'원문'}),source=NS(verify=verify),repo=NS(event=lambda k,v:events.append((k,v)))),p={'read_plans':{'r':{'status':'ACQUIRED','targets':[{'source_id':'s','document_id':'d','unit_id':'9'}],'completed':{'t':'g'}}},'selected':{'g':{'document_id':'d','source_id':'s','evidence':[e]}}})
    goal={'goal_id':'SG1','document_id':'d','coordinate':'제9조제14항','coordinate_scope':'body','status':'REQUIRED','arrivals':[],'routes':['LOOKUP']}
    monkeypatch.setattr(unit_reading,'blocks',lambda s,d,u,e:[str(i) for i in range(4)])
    return inv,goal,events,verified

def test_full_ancestor_receipt_fulfills_child_and_resume_does_not_repeat(monkeypatch):
    inv,g,events,verified=fixture(monkeypatch);sg.refresh(inv,[g]);assert g['status']=='ACQUIRED' and g['arrivals']==['g'] and g['routes']==['LOOKUP'];assert events[-1][0]=='SOURCE_GOAL_CONTAINED_ORIGINAL';sg.refresh(inv,[g]);assert len(verified)==1 and len(events)==1

@pytest.mark.parametrize('damage',['missing_block','partial','other_document','other_scope','sibling','ambiguous','incomplete_plan','wrong_batch','unresolved_coordinate'])
def test_invalid_ancestor_receipt_cannot_fulfill_child(monkeypatch,damage):
    inv,g,events,verified=fixture(monkeypatch);m=inv.s.matcher;r=inv.p['selected']['g'];p=inv.p['read_plans']['r']
    if damage=='missing_block':r['evidence'][0]['spans'].pop()
    if damage=='partial':r['evidence'][0]['spans'][0]['end_cp']=1
    if damage=='other_document':r['document_id']='other'
    if damage=='other_scope':m.units[('d','9')]['coordinate_scope']='addendum'
    if damage=='sibling':m.units[('d','14')]['parent']=None
    if damage=='ambiguous':m.units[('d','copy')]=deepcopy(m.units[('d','14')]);m.stored_coordinates[('d','copy')]=m.stored_coordinates[('d','14')]
    if damage=='incomplete_plan':p['status']='PARTIAL'
    if damage=='wrong_batch':r['source_id']='other-source'
    if damage=='unresolved_coordinate':m.units[('d','14')]['coordinate_binding']={'mode':'unresolved'}
    sg.refresh(inv,[g]);assert g['status']=='REQUIRED' and g['arrivals']==[] and not events

@pytest.mark.parametrize('damage',['hash','scope','cycle'])
def test_integrity_faults_block_ancestor_arrival(monkeypatch,damage):
    inv,g,events,verified=fixture(monkeypatch)
    if damage=='hash':inv.p['selected']['g']['evidence'][0]['spans'][0]['text']='변조'
    if damage=='scope':inv.s.scope=set()
    if damage=='cycle':inv.s.matcher.units[('d','9')]['parent']='14'
    with pytest.raises(ContractError):sg.refresh(inv,[g])
    assert g['status']=='REQUIRED' and not events

@pytest.mark.parametrize('damage',[None,'missing_child_block','hash'])
def test_saved007_full_ancestor_with_actual_source_verifier(damage):
    P=ROOT/'04_EXPERIMENTS/ADR/ADR-1177-response-recovery-followup/artifacts/live/cm-007';D=ROOT/'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation';state=json.loads((P/'investigation-state.json').read_text());view=json.load(gzip.open(P/'canonical/007.json.gz','rt'))['view'];goal=deepcopy(next(g for g in view['source_goal_context']['goals'] if g['goal_id']=='SG3'));assert goal['status']=='REQUIRED'
    did=goal['document_id'];db=sqlite3.connect((D/'store.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;nav=sqlite3.connect((D/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
    raw_units={str(row['unit_id']):json.loads(row['json']) for row in db.execute('select unit_id,json from source_unit where document_id=?',(did,))};units={(did,uid):{**raw,'parent':str(raw['parent']) if raw.get('parent') is not None else None,'raw_structure':raw} for uid,raw in raw_units.items()};coords={k:stored_coordinate(units,*k) for k in units};sources={}
    for record in state['selected'].values():
        if record['document_id']==did:sources[record['source_id']]=json.loads(nav.execute('select json from source where id=?',(record['source_id'],)).fetchone()[0])
    def source(d,b):return dict(db.execute('select * from source_block where document_id=? and block_id=?',(d,str(b))).fetchone())
    store=NS(db=db,source=source,sources=lambda d,bs:[source(d,b) for b in bs]);verifier=SourceSession.__new__(SourceSession);verifier.store=store;verifier.tools=NS(sources=sources);verifier.scope={did};verifier.context=NS(query={'generation_id':json.loads((D/'manifest.json').read_text())['generation_id']})
    events=[];inv=NS(p=state,s=NS(scope={did},store=store,source=verifier,matcher=NS(units=units,stored_coordinates=coords,sources=sources),repo=NS(event=lambda k,v:events.append((k,v)))))
    if damage:
        for record in state['selected'].values():
            if record['document_id']!=did:continue
            for e in record['evidence']:
                if damage=='missing_child_block':e['spans']=[s for s in e['spans'] if s['block_id']!='186']
                else:
                    for span in e['spans']:
                        if span['block_id']=='186':span['span_hash']='bad'
    if damage=='hash':
        with pytest.raises(ContractError,match='exact-span'):sg.refresh(inv,[goal])
    else:
        sg.refresh(inv,[goal]);assert (goal['status']=='ACQUIRED')==(damage is None)
    if damage is None:
        assert events and goal['routes']==['LOOKUP'];put(ART/'saved007-contained-original.json',{'source':str(P.relative_to(ROOT)),'original_goal':view['source_goal_context']['goals'][-1],'verified_goal':goal,'actual_source_verifier':True,'expected_blocks':unit_reading.blocks(inv.s,did,'169','subtree'),'note':'Stored span [186,190) uses exclusive end; goal contains4blocks. Earlier observation also checked adjacent block190, which is not needed.','new_model_calls':0,'new_tool_actions':0,'old_live_result_changed':False})
    db.close();nav.close()
