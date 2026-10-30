"""MAIN106 exact output contract, synthetic original data, native HTTP."""
import ast,inspect,json,sqlite3
from copy import deepcopy
import pytest
from conftest import term_glossary
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_context as oc,compact_model_input as minimal
from test_ontology_context import inv,bundle,configure,plans,direct_scope,original,connected,definition_source

@pytest.mark.parametrize('mode',['normal','no_match','repair','conditional'])
def test_native_scenario_choice_and_publication(tmp_path,term_glossary,monkeypatch,mode):
    need_more=False
    import test_read_judgment_api as parent
    from semantic_runtime.legal_agent import navigation_input
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    from test_legal_agent_double_harness import wire
    from test_source_span_norm import proposal
    from test_main50_request_repair import GAP
    canonical=[{}];stage=[''];project=minimal.project;expand=navigation_input.expand_cards
    def capture(view,schema=None):
        stage[0]=view.get('source_stage','');canonical[0]=expand(deepcopy(view));return project(view,schema)
    def unpack(raw):
        view=expand(raw);view.setdefault('sources',[]);view.setdefault('phase',stage[0]);view.setdefault('source_stage',stage[0])
        if isinstance(view.get('tool_options'),dict):view['tool_options']=[dict(o,choice=k) for k,rows in view['tool_options'].items() for o in rows]
        def restore_empty(target,source):
            if isinstance(target,dict) and isinstance(source,dict):
                for k,v in source.items():
                    if k not in target and v in ([],{}):target[k]=deepcopy(v)
                    elif k in target:restore_empty(target[k],v)
            elif isinstance(target,list) and isinstance(source,list) and len(target)==len(source):
                for x,y in zip(target,source):restore_empty(x,y)
        restore_empty(view,canonical[0])
        ctx=view.setdefault('read_judgments',{})
        for key in ('current_originals','required','judgments','needs','conflicts','previous_final_review'):ctx.setdefault(key,[])
        for row in ctx['judgments']:row.setdefault('available_evidence_refs',[])
        return view
    monkeypatch.setattr(minimal,'project',capture);monkeypatch.setattr(navigation_input,'expand_cards',unpack)
    tree=ast.parse(inspect.getsource(parent.test_read_judgment_api_retains_decisions_and_reuses_request));fn=tree.body[0]
    fn.decorator_list=[];fn.name='_setup';end=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.ClassDef) and n.name=='Transport')
    fn.body=fn.body[:end+1]+ast.parse('return root,generation,index,question,target_text,Transport').body
    ns=dict(vars(parent));exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),parent.__file__,'exec'),ns)
    root,generation,index,question,target_text,Parent=ns['_setup'](tmp_path,term_glossary,'normal',monkeypatch)
    provisions=[]
    with sqlite3.connect(tmp_path/'raw.sqlite') as db:
        version=db.execute("SELECT source_artifact_sha256 FROM document WHERE document_id='d'").fetchone()[0]
        for uid in (['0'] if need_more else ['0','1']):
            text=db.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',('d',uid)).fetchone()[0]
            provisions.append((uid,text))
    bundle_value={'schema_version':'ontology-bundle-v0','bundle_id':'cb-direct-native','revision':1,'status':'APPROVED',
      'concept':{'label':'합성 승인 기준','glossary_ref':None,'kind':'NEW_CONCEPT_CANDIDATE'},
      'provisions':[{'anchor':{'document_id':'d','version':version,'unit_id':uid,'content_sha256':oc.compiler.content_hash(text),'label':'합성 제'+str(int(uid)+1)+'조'},'role':'SCOPE','value':None,'note':''} for uid,text in provisions],
      'relations':[],'review_notes':[],'evidence_judgments':[],
      'proposed_by':{'model':None,'run_id':'synthetic','at':'2026-10-27T00:00:00Z'},'history':[]}
    snapshot={'schema_version':'ontology-snapshot-v0','bundles':[bundle_value]}
    class Transport(Parent):
        def send_once(self,*,body,ticket):
            view=unpack(json.loads(body['messages'][1]['content'])['view']);phase=view['source_stage']
            if phase not in ('memory-assess','memory-assess-repair'):return super().send_once(body=body,ticket=ticket)
            self.calls.append(phase);self.views.append(deepcopy(view))
            catalog=view['ontology_bundles'][0]['scenario_catalog']
            assert catalog['paths'][0]['body']==package['paths'][0]['body']
            paths=[] if mode=='no_match' else ['PATH1']
            if mode=='repair' and phase=='memory-assess':paths=['UNKNOWN']
            value={'choices':[{'issue_id':'Q1','path_ids':paths,'status':'NO_MATCH' if mode=='no_match' else 'CONDITIONAL' if mode=='conditional' else 'GENERAL_RULE','reason':'선택된 업무의 사전 경로', 'missing_facts':['대상 거래 여부'] if mode=='conditional' else []}]}
            return wire(value)
    t=Transport();profile=json.loads((root/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile['candidate_navigation'].update(ontology_direct_assessment=True,ontology_context={'mode':'A1','snapshot':snapshot,'snapshot_sha256':digest(snapshot)})
    from semantic_runtime.legal_agent import ontology_scenarios as sc
    from test_scenarios import fixture
    recipe,_,_=fixture();recipe['bundle_id']=bundle_value['bundle_id']
    originals=[{'id':'P1','anchor':bundle_value['provisions'][0]['anchor'],'text':provisions[0][1]}]
    for component in recipe['components']:component['basis']=[{'source':'P1','quote':provisions[0][1]}]
    recipe['components'][1]['text']='사전 조립된 합성 승인 경로의 결과'
    package=sc.compile_package(recipe,originals)
    profile['candidate_navigation']['ontology_context']['scenario_package']=package
    monkeypatch.setattr(sc,'compile_package',lambda *a,**k:(_ for _ in ()).throw(AssertionError('compiler invoked during request')))
    profile.update(model_binding=t.binding,answer_presentation='grounded-narrative-v1')
    app=create_app(tmp_path,generation,contracts_root=root,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=index
    try:
        with TestClient(app) as api:
            request={'question':question,'session_id':'direct','request_id':'r1'}
            response=api.post('/v1/rag/ask',json=request);assert response.status_code==200,response.text
            result=response.json();assert result['answer']['text']
            if mode!='no_match':assert package['paths'][0]['body'] in result['answer']['text']
            assert not any('compose' in phase for phase in t.calls),t.calls
            before=len(t.calls);again=api.post('/v1/rag/ask',json=request)
            assert again.status_code==200 and again.json()['answer']==result['answer'] and len(t.calls)==before
        assert t.calls.index('memory-assess')==2,t.calls
        assert t.calls.count('memory-assess')==1,t.calls
        assert t.calls.count('memory-assess-repair')==(1 if mode=='repair' else 0),t.calls
        assert 'FINISH' not in t.choices
        print('SCENARIO_NATIVE_HTTP',mode,t.calls)
    finally:app.state.pipeline.store.close()
