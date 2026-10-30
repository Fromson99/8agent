"""MAIN106 exact output contract, synthetic original data, native HTTP."""
import ast,inspect,json,sqlite3
from copy import deepcopy
import pytest
from conftest import term_glossary
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_context as oc,compact_model_input as minimal
from test_ontology_context import inv,bundle,configure,plans,direct_scope,original,connected,definition_source

@pytest.mark.parametrize('need_more',[False,True])
def test_main106_native_direct_and_gap(tmp_path,term_glossary,monkeypatch,need_more):
    import test_read_judgment_api as parent
    from semantic_runtime.legal_agent import navigation_input
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    from test_legal_agent_double_harness import wire
    from test_source_span_norm import proposal
    from test_main50_request_repair import GAP
    stage=[''];project=minimal.project;expand=navigation_input.expand_cards
    def capture(view,schema=None):
        stage[0]=view.get('source_stage','');return project(view,schema)
    def unpack(raw):
        view=expand(raw);view.setdefault('sources',[]);view.setdefault('phase',stage[0]);view.setdefault('source_stage',stage[0])
        if isinstance(view.get('tool_options'),dict):view['tool_options']=[dict(o,choice=k) for k,rows in view['tool_options'].items() for o in rows]
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
            if phase!='memory-assess':return super().send_once(body=body,ticket=ticket)
            self.calls.append(phase);self.views.append(deepcopy(view))
            assert view['ontology_bundles'][0]['status']=='COMPLETE'
            options=view['evidence_options'];known={o['id'] for o in options}
            assert all(ref in known for p in view['ontology_bundles'][0]['payload']['provisions'] for ref in p['source_refs'])
            found=next((o for o in options if target_text in o['text']),None)
            if found:
                value=proposal(target_text,'OBLIGATION',[found['id']],found['id']);value.pop('disposition')
            else:
                assert need_more
                loc=next((o['target'] for o in view.get('locator_options',[]) if '제2조' in json.dumps(o,ensure_ascii=False)),'')
                value={'claims':[],'issue_assessments':[{'issue_id':'Q1','status':'INSUFFICIENT','reason':'제2조 적용 기준 원문 필요'}],'gaps':[{**GAP,'reason':'적용 기준을 정하는 제2조 원문이 필요하다.','missing_target':loc}]}
            used=set(value['claims'][0]['evidence_refs']) if value['claims'] else set();ctx=view['read_judgments']
            value['read_judgment_review']={'judgments':[{'id':h['id'],'disposition':'USE' if used.intersection(h['available_evidence_refs']) else 'NOT_USED',
                'claim_refs':['C1'] if used.intersection(h['available_evidence_refs']) else [],'basis_refs':list(used.intersection(h['available_evidence_refs'])),'reason':'현재 원문과 답변의 근거 범위 확인'} for h in ctx['judgments']],
                'needs':[{'id':n['id'],'status':'NOT_NEEDED','reason':'현재 판단에 반영','material':False,'basis_refs':[]} for n in ctx['needs']], 'conflicts':[]}
            return wire(value)
    t=Transport();profile=json.loads((root/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile['candidate_navigation'].update(ontology_direct_assessment=True,ontology_context={'mode':'A1','snapshot':snapshot,'snapshot_sha256':digest(snapshot)})
    profile.update(model_binding=t.binding,answer_presentation='structured')
    app=create_app(tmp_path,generation,contracts_root=root,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=index
    try:
        with TestClient(app) as api:
            request={'question':question,'session_id':'direct','request_id':'r1'}
            response=api.post('/v1/rag/ask',json=request);assert response.status_code==200,response.text
            result=response.json();assert target_text in result['answer']['text']
            before=len(t.calls);again=api.post('/v1/rag/ask',json=request)
            assert again.status_code==200 and again.json()['answer']==result['answer'] and len(t.calls)==before
        assert t.calls.index('memory-assess')==2,t.calls
        assert t.calls.count('memory-assess')==(2 if need_more else 1),t.calls
        assert 'FINISH' not in t.choices
        print('MAIN106_DIRECT_HTTP',need_more,t.calls)
    finally:app.state.pipeline.store.close()
