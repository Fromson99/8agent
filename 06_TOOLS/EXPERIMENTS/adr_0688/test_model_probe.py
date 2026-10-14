"""Supplemental frozen synthetic navigation probe; no actual corporate data."""
from contextlib import closing
from pathlib import Path
import copy, hashlib, json, os, sqlite3, time
import pytest
from semantic_runtime import unit_fulltext as ufts
from semantic_runtime.legal_agent import law_candidates as lc, law_navigation as ln
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent import unit_reading as ur
from semantic_runtime.contracts import digest
from lawrag.core.legal_coordinate import find_coordinates
from lawrag.pipeline.term_generation import build_generation
from test_document_release import source
from test_legal_agent_v5 import app_for
from test_bounded_source_main import settings
from test_unified_legal_agent import ScriptedTransport
from test_law_grouped_navigation import reader, decide

R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0688-followup-structure-observability-recovery'

def put(p, value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

@pytest.fixture
def synthetic_session(tmp_path, term_glossary):
    texts=[f'제{i}조의 모의 후보 검토 자료이다. 실제 법률 내용이 아니다.' for i in range(1,13)]
    texts[5]='금융투자업의 모의 종류는 모의매매업과 모의중개업이다. 실제 법률 내용이 아니다.'
    raw=source(tmp_path/'raw.sqlite',[('d','모의공개금융법',texts)])
    with sqlite3.connect(raw) as db:
        for uid,text in db.execute('SELECT unit_id,json FROM source_unit').fetchall():
            unit=json.loads(text); coordinate=find_coordinates(unit['surface'])[0].coordinate
            unit.update(title='금융투자업' if uid=='5' else '모의후보',legal_coordinate=coordinate.as_dict(),
                        coordinate_scope='body',coordinate_key='body:'+coordinate.canonical_surface())
            db.execute('UPDATE source_unit SET json=? WHERE unit_id=?',(json.dumps(unit,ensure_ascii=False),uid))
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    gen=tmp_path/'built/generation';idxroot=tmp_path/'unit-index'
    ufts.build(gen,gen/'navigation',idxroot,workers=1)
    idx=ufts.UnitFulltextIndex(idxroot,json.loads((gen/'navigation/manifest.json').read_text()))
    app=app_for(tmp_path,gen,ScriptedTransport(),{**settings(),'page_size':10,'max_read_chars':4000})
    p=app.state.pipeline;p.term_agent.unit_fulltext=idx
    request={'question':'모의 후보 검토','document_ids':['d'],'use_llm':False}
    try:
        with p.term_agent.open_session(request,query=p.plan(request['question'],['d']),runtime=tmp_path/'runtime') as s:
            yield s, gen
    finally:
        p.store.close()

def test_probe(synthetic_session):
    if not os.environ.get('ADR688_PROBE_CASE'):
        pytest.skip('Real calls only from the frozen probe orchestrator')
    native, gen=synthetic_session;s=native.sources
    criteria=json.loads((A/'artifacts/design/criteria.json').read_text())
    case=next(c for c in criteria['model_probe']['cases'] if c['id']==os.environ['ADR688_PROBE_CASE'])
    arm=os.environ['ADR688_PROBE_ARM'];out=A/'artifacts/run-001/probe'/case['id']/arm
    assert not (out/'result.json').exists(),'Never overwrite a completed probe'
    s.profile['candidate_navigation']={**lc.DEFAULT_POLICY,'mode':'law-first-v1',
        'article_page_size':1,'investigation_control':True,'completion_contract':True}
    record=SourceRecall(s).prepare()
    inv=ln.Investigation(s,case['question'],record,reader,120,None,None)
    data, actions=inv.view()
    # Current state setup is synthetic and identical between arms. It is not a
    # gold hint or an automatic tool decision attributed to the model.
    setup=[]
    if case['scenario']=='three-pages':
        for kind in ('OPEN_LAW','NEXT_ARTICLES','NEXT_ARTICLES'):
            target=next(k for k,a in actions.items() if a['action']==kind)
            d=decide(data,kind,target);d.update(law_decisions=[],branch_decisions=[],expected_state_version=data['state_version'])
            inv.validate(d,data,actions);inv.execute(d,data,actions);setup.append(d)
            data,actions=inv.view()
    elif case['scenario']=='missing':
        target=data['laws'][0]['structure_search_action']
        d=decide(data,'SEARCH_STRUCTURE',target);d.update(law_decisions=[],branch_decisions=[],
            expected_state_version=data['state_version'],queries=[],
            structure_filter={'coordinate':'제999조','title':'','coordinate_scope':'body'})
        inv.validate(d,data,actions);inv.execute(d,data,actions);setup.append(d)
        data,actions=inv.view()
    from lawrag.research.experiment_client import ExperimentClient
    client=ExperimentClient(R,out/'model',max_calls=3,max_output_tokens=4096,max_repairs=0)
    result={'case':case['id'],'arm':arm,'synthetic':True,'setup_actions':setup,'steps':[],
        'legal_semantic_grading':False,'served_code':str(Path(ln.__file__).resolve()),
        'source_manifest_sha256':hashlib.sha256((gen/'manifest.json').read_bytes()).hexdigest()}
    system=ln.SYSTEM+'\ncompletion_contract가 있으면 READ/VIEW의 law_decisions와 branch_decisions는 빈 배열이다. 현재 제공된 도구를 선택해서 원문을 확보한다.'
    started=time.monotonic()
    for turn in range(3):
        offered={k:copy.deepcopy(v) for k,v in actions.items()}
        wire=inv.model_view(data);schema=ln.decision_schema(data,actions,{b['id'] for b in data['branches']})
        put(out/f'turn-{turn+1}-offered.json',{'view':wire,'schema':schema,'actions':offered})
        try:
            decision=client.generate(system,wire,schema,phase='navigation-'+str(turn+1))
            inv.validate(decision,data,actions)
            step={'decision':decision,'valid':True,'action_count':len(actions)}
            inv.execute(decision,data,actions);data,actions=inv.view()
            step['lookup']=copy.deepcopy(inv.p.get('structure_page'))
            step['delivered']=[{k:p[k] for k in ('document_id','heading','spans','scope_id')} for p in data.get('sources',[])]
            result['steps'].append(step)
            if data.get('sources') or decision['next_action'] in ('FINISH','PENDING','RESEARCH'):
                break
        except Exception as exc:
            result['steps'].append({'valid':False,'error_type':type(exc).__name__,'error':str(exc)})
            break
    result.update(calls=client.calls,usage=client.usage,elapsed_seconds=time.monotonic()-started,
        original_delivered=bool(data.get('sources')),structure_recovery=data.get('structure_recovery',[]))
    put(out/'result.json',result)
    print(json.dumps({'case':case['id'],'arm':arm,'calls':client.calls,'original_delivered':result['original_delivered'],
                      'valid':all(s['valid'] for s in result['steps'])},ensure_ascii=False))
