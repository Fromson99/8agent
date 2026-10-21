"""Real service and HTTP consumers; one bounded process, no model calls."""
from pathlib import Path
from types import SimpleNamespace
import asyncio, hashlib, importlib, importlib.util, json, os, sqlite3, sys, traceback
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0811-workflow-version-source-binding';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
mode=sys.argv[1];f=read(D/'freeze.json');data=read(D/'data-binding.json');did='11478916f48b00e5'
os.environ.update(AD_WORKER_ENABLED='0',TEAM_ID='risk_team',LAWRAG_WORKSPACE_ROOT=str(R),GENOS_RUNTIME_DIR=str(A/'artifacts/active-runtime'))
sys.dont_write_bytecode=True
status=1
try:
    if mode=='candidate':
        C=R/f['code_root'];sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND')]
        from semantic_runtime.app import create_app
        from semantic_runtime.team_scope import select_documents
        from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
        t=LocalGemmaTransport(C,R)
        profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=t.binding
        app=create_app(R,R/data['path'],contracts_root=C,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',runtime_root=A/'artifacts/candidate-runtime-rev005',legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:dict(user_id='jin',team_id='risk_team',document_ids=select_documents(app.state.pipeline.store,'risk_team')))
        spec=importlib.util.spec_from_file_location('latest_candidate_service',C/'service.py');actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
        actual._APP=app;actual._ad_control=lambda:SimpleNamespace(intercept=lambda *a:None,start_worker=lambda *a:None)
    else:
        sys.path[:0]=[str(R),str(R/'02_BACKEND')]
        import service
        actual=importlib.import_module('service.service');app=actual.application()
        pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');manifest=read(R/pointer['manifest_path']);C=R/manifest['code_root']
        assert manifest['data_path']==data['path'] and manifest['files']==f['serving_files']
    from fastapi.testclient import TestClient
    checks={}
    client=TestClient(app)
    listing=client.get('/v1/rag/documents',params={'team_id':'risk_team','title_query':'위험관리위원회운영준칙'})
    listing.raise_for_status();body=listing.json();assert did in json.dumps(body,ensure_ascii=False)
    checks['team_filtered_document_listing']=True
    source=client.get('/v1/rag/document/read',params={'team_id':'risk_team','doc_id':did,'limit':50})
    source.raise_for_status();assert '분기별 1회씩' in json.dumps(source.json(),ensure_ascii=False)
    checks['team_filtered_exact_source_read']=True
    store=app.state.pipeline.store
    store.selection.require_latest()
    assert store.selection.value['schema_version']=='filename-search-selection-v2'
    marks=[json.loads(r[0]).get('document_metadata', {}) for r in store.db.execute('SELECT json FROM document') if json.loads(r[0]).get('document_metadata', {}).get('is_latest') is True]
    assert len(marks)==11
    checks['latest_marks_visible_to_actual_store']=True
    denied=client.get('/v1/rag/document/read',params={'team_id':'financial_team','doc_id':did})
    checks['unrelated_team_cannot_read_target']=denied.status_code in (403,404,422)
    search=asyncio.run(actual.service({}, {'API_TYPE':'RAG_SEARCH','q':'위험관리위원회','doc_id':did,'team_id':'risk_team','limit':3}))
    checks['service_team_scoped_search']=search['status']==200
    workflow=asyncio.run(actual.service({}, {'API_TYPE':'LEGAL_AGENT','question':'대사: 위험관리위원회운영준칙 제4조 정기 개최 주기','use_llm':False,'session_id':'adr0811-active-'+mode,'request_id':'adr0811-active-'+mode}))
    assert workflow['status']==200,workflow
    value=workflow['body'];assert did in value['binding']['document_ids']
    checks['workflow_parent_contains_corrected_document']=True
    internal=value['rag_results']['internal']
    # Child receipts identify the scope; inspect the exact journal emitted by this request.
    root=app.state.workflow_runtime.root/value['run_id']
    child_scope=None
    for p in root.glob('children/internal/legal-agent/**/journal.sqlite'):
        with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
            child_scope=json.loads(db.execute('SELECT binding_json FROM run').fetchone()[0])['scope']['document_version_ids']
    checks['workflow_internal_child_contains_corrected_document']=child_scope is not None and did in child_scope
    checks['no_model_calls']=value['usage']['model_reserved']==0
    checks['workflow_version_selected']=app.state.pipeline.contracts.pipeline['workflows']['registered'][0]['version']=='1.2.0'
    checks['all_serving_hashes_match_candidate']=all(hashlib.sha256((C/n).read_bytes()).hexdigest()==h for n,h in f['serving_files'].items())
    again=asyncio.run(actual.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':value['run_id'],'session_id':value['session_id']}))
    checks['saved_result_status_consumer']=again['status']==200 and again['body']['answer']==value['answer']
    health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}))
    checks['health_selection_fingerprint']=bool(app.state.pipeline.store.selection.fingerprint)
    receipt={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'environment':'WSL local actual service and HTTP API','code_root':str(C.relative_to(R)),'data':data,'document_listing':body,'workflow_run_id':value['run_id'],'child_document_count':len(child_scope or []),'internal_evidence_count':len(internal['evidence_ids']),'health':health,'model_calls':0,'genos_deployed':False}
    (A/('artifacts/'+mode+'-consumer-v2.json')).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'mode':mode,'checks':checks,'child_count':len(child_scope or [])},ensure_ascii=False),flush=True)
    assert all(checks.values()),checks
    app.state.pipeline.store.close();status=0
except BaseException:traceback.print_exc()
finally:
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
