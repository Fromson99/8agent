"""Real service and HTTP consumers; one bounded process, no model calls."""
from pathlib import Path
from types import SimpleNamespace
import asyncio, hashlib, importlib, importlib.util, json, os, sqlite3, sys, traceback
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0830-comparison-main-confirmation';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
mode='candidate';f=read(D/'verification-binding.json');data=read(D/'data-binding.json');did='11478916f48b00e5'
assert mode in ('candidate','baseline','active'), 'unknown consumer arm'
generation=(R/data['path']).resolve()
assert hashlib.sha256((generation/'manifest.json').read_bytes()).hexdigest()==data['manifest_sha256'], 'frozen data manifest changed'
os.environ.update(AD_WORKER_ENABLED='0',TEAM_ID='risk_team',LAWRAG_WORKSPACE_ROOT=str(R),GENOS_RUNTIME_DIR=str(A/'artifacts/active-runtime'))
sys.dont_write_bytecode=True
status=1
try:
    if mode in ('candidate','baseline'):
        baseline=read(D/'baseline.json')['manifest']
        selected_files=f['serving_files'] if mode=='candidate' else baseline['files']
        C=R;selected_files={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in f['serving_files']};sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND')]
        from semantic_runtime.app import create_app
        from semantic_runtime.team_scope import select_documents
        from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
        t=LocalGemmaTransport(C,R)
        profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=t.binding
        app=create_app(R,R/data['path'],contracts_root=C,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',runtime_root=A/'artifacts/working-runtime',legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:dict(user_id='jin',team_id='risk_team',document_ids=select_documents(app.state.pipeline.store,'risk_team')))
        spec=importlib.util.spec_from_file_location('latest_candidate_service',C/'service.py');actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
        actual._APP=app;actual._ad_control=lambda:SimpleNamespace(intercept=lambda *a:None,start_worker=lambda *a:None)
    else:
        sys.path[:0]=[str(R),str(R/'02_BACKEND')]
        import service
        actual=importlib.import_module('service.service');app=actual.application()
        assert actual._BINDING['mode']=='local-release', 'active check must use local active-pointer bootstrap'
        pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');manifest=read(R/pointer['manifest_path']);C=R/manifest['code_root']
        assert manifest['data_path']==data['path'] and manifest['files']==f['serving_files']
        selected_files=f['serving_files']
    actual_generation=app.state.pipeline.store.path.resolve()
    actual_data_sha256=hashlib.sha256((actual_generation/'manifest.json').read_bytes()).hexdigest()
    assert actual_generation==generation and actual_data_sha256==data['manifest_sha256'], 'running app differs from frozen data generation'
    service_entry=Path(actual.__file__).resolve()
    entry_receipt={'path':str(service_entry.relative_to(R)),
        'sha256':hashlib.sha256(service_entry.read_bytes()).hexdigest(),
        'selected_release_entry_sha256':hashlib.sha256((C/'service.py').read_bytes()).hexdigest(),
        'app_injected':mode in ('candidate','baseline'),
        'bootstrap':'Selected-code create_app plus selected service.py ASGI dispatch; _APP is injected, so active-pointer application bootstrap is not exercised.'
            if mode in ('candidate','baseline') else 'Actual workspace service.application local active-pointer bootstrap, followed by its ASGI dispatch into the selected release.',
        'pipeline_module_path':str(Path(sys.modules[type(app.state.pipeline).__module__].__file__).resolve().relative_to(R))}
    actual_data={'path':str(actual_generation.relative_to(R)),'manifest_sha256':actual_data_sha256,
        'generation_id':app.state.pipeline.store.manifest['generation_id']}
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
    workflow=asyncio.run(actual.service({}, {'API_TYPE':'LEGAL_AGENT','question':'대사: 위험관리위원회운영준칙 제4조 정기 개최 주기','use_llm':False,'session_id':'adr0826-working-'+mode+'-'+f['revision_id'],'request_id':'adr0826-working-'+mode+'-'+f['revision_id']}))
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
    if mode=='candidate':checks['all_field_rows_status_saved']=len(value['comparison_items']['items'])==5 and all(i['content_status']=='UNKNOWN' for i in value['comparison_items']['items'])
    checks['workflow_version_selected']=app.state.pipeline.contracts.pipeline['workflows']['registered'][0]['version']==read(C/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']
    checks['all_serving_hashes_match_selected_arm']=all(hashlib.sha256((C/n).read_bytes()).hexdigest()==h for n,h in selected_files.items())
    again=asyncio.run(actual.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':value['run_id'],'session_id':value['session_id']}))
    checks['saved_result_status_consumer']=again['status']==200 and again['body']['answer']==value['answer']
    health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}))
    checks['health_selection_fingerprint']=bool(app.state.pipeline.store.selection.fingerprint)
    receipt={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'environment':'WSL local actual service and HTTP API','code_root':str(C.relative_to(R)),'data':data,'actual_data':actual_data,'entry':entry_receipt,'document_listing':body,'workflow_run_id':value['run_id'],'child_document_count':len(child_scope or []),'internal_evidence_count':len(internal['evidence_ids']),'health':health,'model_calls':0,'genos_deployed':False,'working_files':selected_files,'qualified_component_hashes_match':all(selected_files[n]==v['after'] for v in read(A/'artifacts/working-integration.json')['changes'] for n in [v['path']])}
    (A/'artifacts/working-consumer-v2.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'mode':mode,'checks':checks,'child_count':len(child_scope or [])},ensure_ascii=False),flush=True)
    assert all(checks.values()),checks
    app.state.pipeline.store.close();status=0
except BaseException:traceback.print_exc()
finally:
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
