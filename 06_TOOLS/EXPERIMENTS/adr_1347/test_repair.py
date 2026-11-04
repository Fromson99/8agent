from copy import deepcopy
from types import SimpleNamespace as NS
from pathlib import Path
import gzip,json
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.ontology_work import wiki_contracts as wc
from semantic_runtime.legal_agent import source_goal_control as sg, evidence_inventory as ei
from test_wiki_workspace import env,ws,compiled
from lawrag.core.legal_coordinate import find_coordinates

def change(e,raw):
    return {'operations':[
      {'op':'ADD_STATEMENT','target':'@statement_1','value':{'text':e.source['text'],'origin_refs':[raw['bundle_id']],
         'source_basis':[{'source_ref':e.source['id'],'quote':e.source['text'],'occurrence':0}],'open_items':[]}},
      {'op':'CREATE_ENTRY','target':'@entry_1','value':{'title':'원기록의 문장','body':'검토 전 기록','statement_refs':['@statement_1']}},
      {'op':'CREATE_VIEW','target':'@view_1','value':{'title':'보관 보기','member_refs':['@entry_1']}}]}

def test_model_proposal_apply_and_existing_compiler_consume_exact_sources(env,ws):
    raw=ws.import_payload(env.source['text'],event_id='typed',run_id='synthetic');wire=change(env,raw);seen=[]
    def generate(prompt,context,schema):
        assert context['proposal_contract']==wc.PROPOSAL_VERSION
        assert 'ADD_STATEMENT' in prompt and '@[A-Za-z0-9_-]' in prompt
        Draft202012Validator(schema).validate(wire);seen.append(deepcopy(context));return deepcopy(wire),{'synthetic':True}
    ws.generate=generate
    args=dict(change_id='typed',raw_ids=[raw['bundle_id']],originals=[env.source])
    proposal=ws.propose(**args);assert ws.list_items()['items']==[]
    basis=proposal['operations'][0]['value']['source_basis'][0]
    assert basis==dict(anchor=env.source['anchor'],quote=env.source['text'],start_cp=0,end_cp=len(env.source['text']))
    assert proposal['operations'][0]['value']['text']==wire['operations'][0]['value']['text']
    assert ws.propose(**args)==proposal and len(seen)==1
    applied=ws.apply(**proposal);assert ws.apply(**proposal)['reused']
    item=NS(raw=raw,sid=applied['handles']['@statement_1'])
    document,_=compiled(env,ws,item)
    assert env.w.preview(document['bundle_id'])['paths'][0]['body']==env.source['text']
    assert env.repo.head(item.sid)['publication_id'] is None

@pytest.mark.parametrize('fault',['handle','wrong_kind_field','source_id','quote','occurrence','origin','duplicate','withdraw'])
def test_typed_proposal_one_repair_preserves_original_no_early_commit(env,ws,fault):
    raw=ws.import_payload(env.source['text'],event_id=fault,run_id='synthetic');good=change(env,raw);bad=deepcopy(good)
    op=bad['operations'][0]
    if fault=='handle':op['target']='@한글 이름'
    if fault=='wrong_kind_field':op['value']['title']='문장에 없는 필드'
    if fault=='source_id':op['value']['source_basis'][0]['source_ref']='invented'
    if fault=='quote':op['value']['source_basis'][0]['quote']='원문에 없는 구절'
    if fault=='occurrence':op['value']['source_basis'][0]['occurrence']=10**12
    if fault=='origin':op['value']['origin_refs']=['not-offered']
    if fault=='duplicate':bad['operations'].append(deepcopy(op))
    if fault=='withdraw':op.update(op='RETRACT',value={'reason':'자동 철회'})
    contexts=[]
    def generate(prompt,context,schema):
        assert ws.list_items()['items']==[];contexts.append(deepcopy(context))
        return deepcopy(bad if len(contexts)==1 else good),{'call':len(contexts)}
    ws.generate=generate
    args=dict(change_id=fault,raw_ids=[raw['bundle_id']],originals=[env.source])
    proposal=ws.propose(**args);assert len(contexts)==2
    assert contexts[1]['repair']['previous']['response']==bad
    assert contexts[1]['call_budget']['maximum']==2
    assert ws.propose(**args)==proposal and len(contexts)==2
    ws.apply(**proposal);assert ws.apply(**proposal)['reused'] and len(contexts)==2

def test_repeated_bad_output_and_unknown_do_not_replay(env,ws):
    raw=ws.import_payload('보존',event_id='bad',run_id='test');seen=[]
    def bad(*args):seen.append(1);return {'operations':[{'op':'CREATE_ENTRY','target':'@한글','value':{'title':'보존'}}]},{}
    ws.generate=bad;args=dict(change_id='bad',raw_ids=[raw['bundle_id']])
    with pytest.raises(ContractError):ws.propose(**args)
    with pytest.raises(ContractError,match='INVALID'):ws.propose(**args)
    assert len(seen)==2 and ws.list_items()['items']==[]
    def unknown(*args):seen.append(1);raise TimeoutError('unknown outcome')
    ws.generate=unknown;args['change_id']='unknown'
    with pytest.raises(TimeoutError):ws.propose(**args)
    with pytest.raises(ContractError,match='UNKNOWN'):ws.propose(**args)
    assert len(seen)==3

def test_repeated_quote_occurrence_is_exact_and_canonical_reader_unchanged():
    source={'id':'original','text':'같음, 같음','anchor':{'literal':'kept'}}
    schema,expand=wc.proposal_contract({'raw':{}},[],[source])
    raw={'operations':[{'op':'ADD_STATEMENT','target':'@s','value':{'text':'의견','origin_refs':['raw'],
        'source_basis':[{'source_ref':'original','quote':'같음','occurrence':1}]}}]}
    result=expand(raw);assert result['operations'][0]['value']['source_basis'][0]=={'anchor':{'literal':'kept'},'quote':'같음','start_cp':4,'end_cp':6}
    assert raw['operations'][0]['value']['source_basis'][0]['source_ref']=='original'
    assert expand(raw)==result
    wc.validate(result,wc.CHANGE_SCHEMA)

def history_fixture(monkeypatch, *, ancestor=False):
    target='2' if ancestor else '1';coordinate='제7조제1항' if ancestor else '제7조'
    def coord(t):return find_coordinates(t)[0].coordinate
    matcher=NS(sources={'source':{'document_id':'d','unit_id':'1'}},
      units={('d','1'):{'parent':None,'coordinate_scope':'body','coordinate_binding':{'mode':'stored'}},
             ('d','2'):{'parent':1,'coordinate_scope':'body','coordinate_binding':{'mode':'stored'}}},
      stored_coordinates={('d','1'):coord('제7조'),('d','2'):coord('제7조제1항')})
    spans=[dict(block_id=str(i),start_cp=0,end_cp=len(t),text=t) for i,t in enumerate(['제7조','① 본문 전체'])]
    def record(parts,tag):return {'document_id':'d','source_id':'source','article_unit_id':'1','complete':True,'offer':{'id':tag,'unit_id':'1'},
       'evidence':[{'document_id':'d','source_id':'source','spans':deepcopy(parts)}]}
    full=record(spans,'whole');part=record(spans[:1],'own')
    state={'selected':{'B1':part},'material_history':{digest(['B1',full['offer']]):full},'read_plans':{'P':{'status':'ACQUIRED','targets':[{'source_id':'source','document_id':'d','unit_id':'1'}],'completed':{'T1':'B1'}}}}
    verified=[]
    def verify(e):
        for s in e['spans']:
            assert s in spans,'tampered original'
        verified.append(deepcopy(e))
    inv=NS(p=state,s=NS(matcher=matcher,scope={'d'},source=NS(verify=verify),repo=NS(event=lambda *a:None)))
    expected=[{k:s[k] for k in ('block_id','start_cp','end_cp')} for s in (spans[1:] if ancestor else spans)]
    goal={'goal_id':'SG1','document_id':'d','coordinate':coordinate,'coordinate_scope':'body','status':'REQUIRED','expected':expected}
    from semantic_runtime.legal_agent import structure_query,unit_reading
    monkeypatch.setattr(structure_query,'coordinate_index',lambda m:{('d',coordinate):[target]})
    monkeypatch.setattr(unit_reading,'blocks',lambda *a:['1'])
    monkeypatch.setattr(ei,'expected',lambda *a:deepcopy(expected))
    return inv,goal,full,verified

@pytest.mark.parametrize('ancestor',[False,True])
def test_source_goal_recognizes_exact_whole_history_after_ontology_own_read(monkeypatch,ancestor):
    inv,goal,full,verified=history_fixture(monkeypatch,ancestor=ancestor);before=deepcopy(inv.p)
    sg.refresh(inv,[goal]);assert goal['status']=='ACQUIRED' and goal['arrivals']==['B1']
    assert full['evidence'][0] in verified and inv.p==before
    inv.p=json.loads(json.dumps(inv.p));sg.refresh(inv,[goal]);assert inv.p==before
    assert 'judgments' not in goal and 'claims' not in goal

@pytest.mark.parametrize('fault',['missing_history','partial_history','wrong_coordinate','wrong_scope','other_plan','excluded','bad_key','foreign_document','bad_bytes'])
def test_history_cannot_complete_wrong_missing_or_tampered_source(monkeypatch,fault):
    inv,goal,full,verified=history_fixture(monkeypatch)
    if fault=='missing_history':inv.p['material_history']={}
    if fault=='partial_history':full['evidence'][0]['spans']=full['evidence'][0]['spans'][:1]
    if fault=='wrong_coordinate':goal['coordinate']='제9조'
    if fault=='wrong_scope':goal['coordinate_scope']='addendum'
    if fault=='other_plan':inv.p['read_plans']['P']['completed']={'T2':'unrelated'}
    if fault=='excluded':goal['status']='EXCLUDED';goal['exclusion']={'reason':'모델의 별도 판단'}
    if fault=='bad_key':inv.p['material_history']={'invented':full}
    if fault=='foreign_document':full['document_id']='other'
    if fault=='bad_bytes':full['evidence'][0]['spans'][1]['text']='변조'
    if fault in ('bad_key','foreign_document','bad_bytes'):
        with pytest.raises((ContractError,AssertionError)):sg.refresh(inv,[goal])
    else:
        sg.refresh(inv,[goal]);assert goal['status']==('EXCLUDED' if fault=='excluded' else 'REQUIRED')

def test_observer_preserves_second_normal_usage_and_duplicate(tmp_path):
    from observer import install
    client=install(NS(_key='never-store-secret',calls=1));path=tmp_path/'usage.json'
    first=[{'call':1,'cost':0.1}];second=first+[{'call':2,'cost':0.2}]
    client._write(path,first);client.calls=2;client._write(path,second);client._write(path,second)
    versions=list((tmp_path/'.raw-versions').glob('*.json.gz'));assert len(versions)==2
    values=[json.load(gzip.open(p,'rt')) for p in versions];assert first in values and second in values
    ref=json.loads(path.with_suffix('.raw-ref.json').read_text())['raw_json']
    assert json.load(gzip.open(ref['path'],'rt'))==second
    with pytest.raises(RuntimeError):client._write(tmp_path/'leak.json',{'bad':'never-store-secret'})
