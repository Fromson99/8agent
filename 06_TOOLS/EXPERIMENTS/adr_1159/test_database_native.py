"""MAIN106 exact output contract, synthetic original data, native HTTP."""
import ast,inspect,json,sqlite3
from copy import deepcopy
import pytest
from conftest import term_glossary
# Import before monkeypatching expand_cards, so no previous test closure survives.
from api_fixture_integrated import to_wire
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_context as oc,compact_model_input as minimal
from test_ontology_context import inv,bundle,configure,plans,direct_scope,original,connected,definition_source

@pytest.mark.parametrize('mode',['normal','multi','off','on_empty'])
def test_database_native_scenario_choice_and_publication(tmp_path,term_glossary,monkeypatch,mode):
    if mode=='normal':monkeypatch.setenv('GENOS_ONTOLOGY_CAPTURE_ENABLED','on')
    fallback=mode in ('no_match','still_insufficient','empty_catalog','twice_invalid','off','on_empty')
    need_more=fallback
    import test_native_integrated as parent
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
            cards=[c['scenario_catalog'] for c in view.get('ontology_bundles',[]) if 'scenario_catalog' in c]
            if not cards:
                assert fallback
                found=next(o for o in view['evidence_options'] if target_text in o['text'])
                value=proposal(target_text,'OBLIGATION',[found['id']],found['id']);value.pop('disposition')
                used=set(value['claims'][0]['evidence_refs']);ctx=view['read_judgments']
                value['read_judgment_review']={'judgments':[{'id':h['id'],'disposition':'USE' if used.intersection(h['available_evidence_refs']) else 'NOT_USED','claim_refs':['C1'] if used.intersection(h['available_evidence_refs']) else [],'basis_refs':list(used.intersection(h['available_evidence_refs'])),'reason':'추가 조사 원문으로 판단'} for h in ctx['judgments']], 'needs':[{'id':n['id'],'status':'NOT_NEEDED','reason':'현재 확보 원문에 반영','material':False,'basis_refs':[]} for n in ctx['needs']], 'conflicts':[]}
                from api_fixture_integrated import to_wire
                return wire(to_wire(value))
            catalog=cards[0]
            assert catalog['paths'][0]['body']==package['paths'][0]['body']
            paths=[] if mode=='no_match' else ['PATH1','PATH2'] if mode=='multi' else ['PATH1']
            if mode=='twice_invalid' or mode=='repair' and phase=='memory-assess':paths=['UNKNOWN']
            action='SEARCH' if mode=='no_match' else 'RESELECT' if mode=='still_insufficient' or mode=='reselect' and not view.get('previous_choice') else 'ANSWER'
            value={'choices':[{'issue_id':'Q1','path_ids':paths,'status':'NO_MATCH' if mode=='no_match' else 'CONDITIONAL' if mode=='conditional' else 'GENERAL_RULE','reason':'선택된 업무의 사전 경로', 'missing_facts':['대상 거래 여부'] if mode=='conditional' else [],'next_action':action,'missing_scope':['연결된 적용 기준 원문'] if action!='ANSWER' else []}]}
            from api_fixture_integrated import to_wire
            return wire(to_wire(value))
    t=Transport();profile=json.loads((root/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile['candidate_navigation'].update(ontology_enabled=True,ontology_direct_assessment=True,ontology_context={'mode':'A1','snapshot':snapshot,'snapshot_sha256':digest(snapshot)})
    from semantic_runtime.legal_agent import ontology_scenarios as sc
    from test_scenarios import fixture
    recipe,_,_=fixture();recipe['bundle_id']=bundle_value['bundle_id']
    originals=[{'id':'P1','anchor':bundle_value['provisions'][0]['anchor'],'text':provisions[0][1]}]
    for component in recipe['components']:component['basis']=[{'source':'P1','quote':provisions[0][1]}]
    recipe['components'][1]['text']='사전 조립된 합성 승인 경로의 결과'
    if mode=='multi':
        second=deepcopy(recipe['paths'][0]);second.update(id='PATH2',title='예외 검토 경로');recipe['paths'].append(second)
    if mode=='empty_catalog':
        with sqlite3.connect(tmp_path/'raw.sqlite') as db:second_text=db.execute("SELECT text FROM source_block WHERE document_id='d' AND block_id='1'").fetchone()[0]
        originals[0]['anchor']={**originals[0]['anchor'],'unit_id':'1','label':'합성 제2조','content_sha256':oc.compiler.content_hash(second_text)};originals[0]['text']=second_text
        for component in recipe['components']:component['basis']=[{'source':'P1','quote':second_text}]
    recipe['authority']=sc.APPROVED_AUTHORITY;recipe['authoring']={'approval_ref':'synthetic-contract-only'}
    package=sc.compile_package(recipe,originals)
    profile['candidate_navigation']['ontology_context']['scenario_package']=package
    from semantic_runtime.ontology_work.repository import Repository
    from semantic_runtime.ontology_work.workflow import Workflow
    from semantic_runtime.ontology_work.store import LocalFolderStore
    from semantic_runtime.ontology_work import runtime as db_runtime
    repo=Repository(lambda:sqlite3.connect(tmp_path/'ontology.sqlite'));repo.initialize()
    work={'version':'ontology-work-v1','concept':'합성 승인 기준','originals':[
        {'id':'P'+str(n+1),'anchor':provision['anchor'],'text':provisions[n][1]}
        for n,provision in enumerate(bundle_value['provisions'])], 'judgments':[], 'origin':{'run_id':'synthetic-native'}}
    w=Workflow(repo,LocalFolderStore(tmp_path/'ontology-work'),actor='native-reviewer',
        source_reader=lambda a:next((r['text'] for r in work['originals'] if r['anchor']==a),None))
    authoring_proposal={k:recipe[k] for k in ('components','paths','unused_components')}
    if mode!='on_empty':
        row=w.save(work,authoring_proposal,bundle_id=bundle_value['bundle_id'])
        w.review(row['bundle_id'],1,row['work_hash'],True,'합성 조건·경로 확인')
        w.publish(row['bundle_id'],1,row['work_hash'],0)
        package=repo.lookup(work['originals'][0]['anchor'],{'d'})[0]['context']['scenario_package']
    profile['candidate_navigation']['ontology_context']={'mode':'DB'}
    monkeypatch.setattr(db_runtime,'repository',lambda:repo)
    monkeypatch.setattr(sc,'compile_package',lambda *a,**k:(_ for _ in ()).throw(AssertionError('compiler invoked during request')))
    if mode=='off':profile['candidate_navigation']['ontology_enabled']=False
    if mode=='on_empty':assert profile['candidate_navigation']['ontology_context']=={'mode':'DB'}
    if mode in ('off','on_empty'):
        monkeypatch.setattr(oc,'resolve',lambda *a,**k:(_ for _ in ()).throw(AssertionError('disabled/empty ontology consulted originals')))
    profile.update(model_binding=t.binding,answer_presentation='structured' if fallback else 'grounded-narrative-v1')
    app=create_app(tmp_path,generation,contracts_root=root,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=index
    try:
        with TestClient(app) as api:
            request={'question':question,'session_id':'direct','request_id':'r1'}
            response=api.post('/v1/rag/ask',json=request);assert response.status_code==200,response.text
            result=response.json();assert result['answer']['text']
            if fallback:assert target_text in result['answer']['text']
            else:
                assert package['paths'][0]['body'] in result['answer']['text']
                if mode=='multi':assert package['paths'][1]['body'] in result['answer']['text']
            assert not any('compose' in phase for phase in t.calls),t.calls
            before=len(t.calls);again=api.post('/v1/rag/ask',json=request)
            assert again.status_code==200 and again.json()['answer']==result['answer'] and len(t.calls)==before
        catalogs=[v for v in t.views if any('scenario_catalog' in c for c in v.get('ontology_bundles',[]))]
        assert len(catalogs)==(0 if mode in ('empty_catalog','off','on_empty') else 2 if mode in ('repair','reselect','still_insufficient','twice_invalid') else 1),t.calls
        if fallback:
            assert 'FOLLOW_CONNECTION' in t.choices and 'READ_LINK' in t.choices,t.choices
            ordinary=[v for v in t.views if v.get('source_stage')=='memory-assess' and not any('scenario_catalog' in c for c in v.get('ontology_bundles',[]))]
            assert len(ordinary)==1,t.calls
            assert any(target_text in o['text'] for o in ordinary[0]['evidence_options'])
            if mode not in ('off','on_empty'):assert ordinary[0]['gap_history']
        else:assert 'FINISH' not in t.choices
        assert t.calls.count('memory-assess-repair')==(1 if mode in ('repair','twice_invalid') else 0),t.calls
        print('SCENARIO_NATIVE_HTTP',mode,t.calls)
    finally:app.state.pipeline.store.close()
