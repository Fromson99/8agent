"""Validate source, engine and scoped authorization without a model request."""
from pathlib import Path
import json,hashlib,sys,os,asyncio,importlib.util,copy
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0954-risk-photo-forced-graph'
D=A/'artifacts/design';read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
binding=read(D/'linked-binding.json');C=R/binding['code_root']
for n,h in read(D/'freeze.json')['files'].items():assert sha(R/n)==h,n
sys.dont_write_bytecode=True
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND'),str(R)]
os.environ.update(GENOS_RESIDENT_DATA='off',GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',
                  TEAM_ID='risk_team',LAWRAG_WORKSPACE_ROOT=str(R))
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.stage_runner import StageRunner
from semantic_runtime.team_scope import select_documents
t=LocalGemmaTransport(C,R)
profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=t.binding
G=R/read(D/'baseline.json')['manifest']['data_path']
app=create_app(R,G,contracts_root=C,workspace_root=R,provider=object(),
    implementation='legal-agent-unified-v6',runtime_root=A/'artifacts/preflight-runtime',
    legal_agent_profile=profile,legal_agent_transport=t,release={'mode':'local-release'})
p=app.state.pipeline
assert StageRunner(p).verify_profile()
scope=select_documents(p.store,'risk_team')
grant=read(D/'authorization.json');assert set(scope)==set(grant['document_ids'])
receipt=t.authorize_workflow({'workflow_id':'risk_team_compare_workflow',
    'principal':{'user_id':'preflight','team_id':'risk_team'},'document_ids':scope},
    {'generation_id':p.store.manifest['generation_id'],'store_sha256':p.store.manifest['store_sha256'],
     'generation_manifest_sha256':sha(G/'manifest.json')})
assert profile['max_model_attempts']==40 and profile['wall_seconds']==1800
out={'status':'PASS','engine_and_source_hashes_verified':True,
     'scoped_authorization_verified':True,'model_calls':0,
     'allowed_document_ids':scope,'grant_sha256':receipt['grant_sha256'],
     'only_authorization_and_pin_configuration_changed':True,'main_changed':False}
spec=importlib.util.spec_from_file_location('graph_preflight_service',C/'service.py')
actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
actual._APP=app;actual._BINDING={'mode':'local-release','generation':92,'candidate_code_root':str(C)}
from seed_graph import seed
graph=read(D/'forced-graph.json')
seed_receipt=asyncio.run(seed(actual.service,graph))
(A/'artifacts/preflight-graph.json').write_text(json.dumps(seed_receipt,ensure_ascii=False,indent=2)+'\n')
repeat=asyncio.run(seed(actual.service,graph))
assert [x['link']['link_id'] for x in seed_receipt['listed']['body']['items']]==[x['link']['link_id'] for x in repeat['listed']['body']['items']]
from semantic_runtime.basis_links.resolver import snapshot,targets
with p.basis_factory() as service:
    who=app.state.basis_identity(None,{})
    counts={}
    for case,edges,expected in [('liquidity',graph['links'][:2],4),('leverage',graph['links'][2:],3)]:
        spans=[span for e in edges for end in e['internal'] for span in service.sources.endpoint(end,who,'internal')['spans']]
        snap=snapshot(service,who,['7a3907e193ec6c14'],{'7a3907e193ec6c14':spans})
        ts=targets(service,who,snap);assert len(ts)==expected,(case,len(ts))
        counts[case]={'links':len(snap['items']),'external_endpoints':len(ts)}
    # Stale revisions are rejected by the ordinary review path.
    item=seed_receipt['receipts'][0]['response']['body']
    stale={'request_id':'adr0954-preflight-stale','action':'approve','reason':'stale revision test',
           'items':[{'link_id':item['link']['link_id'],'revision':1,'view_hash':item['view_hash']}]}
    rejected=asyncio.run(actual.service({}, {'API_TYPE':'BASIS_LINKS_REVIEW','json':stale}))
    assert rejected['body']['status']=='partial' and rejected['body']['items'][0]['error_code']=='BASIS_STALE_VIEW'
    end=service.sources.endpoint(graph['links'][0]['internal'][0],who,'internal')
    tampered=copy.deepcopy(graph['links'][0]);badspan=copy.deepcopy(end['spans'][0]);badspan['text']='intentional invalid source'
    body={k:tampered[k] for k in ('internal','external','kind','reason','provenance')}
    body['internal'][0]['spans']=[badspan];body['request_id']='adr0954-preflight-bad-span'
    denied=asyncio.run(actual.service({}, {'API_TYPE':'BASIS_LINKS_PROPOSE','json':body}))
    assert denied['status']==409 and denied['body']['error_code']=='BASIS_SOURCE_HASH'
out.update(graph_seeded_via_service_api=True,duplicate_seed_same_links=True,stale_review_rejected=True,
           tampered_source_rejected=True,source_scoped_resolver=counts,model_calls=0)
(A/'artifacts/preflight.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
p.store.close()
print(json.dumps(out,ensure_ascii=False))
