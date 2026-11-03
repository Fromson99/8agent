"""Isolated local Oracle contract: synthetic proposal, real sources and storage.

No external model/DDL. The trial namespace is never added to serving settings.
Run create, read and withdraw as separate processes, preserving every receipt.
"""
from common import *
import argparse,importlib.util,os,time,traceback
from types import SimpleNamespace
p=argparse.ArgumentParser();p.add_argument('mode',choices=['create','read','withdraw']);args=p.parse_args()
O=ART/('oracle-create-r2' if args.mode=='create' else 'oracle-'+args.mode);O.mkdir(exist_ok=False)
F=read(DES/'freeze.json');C=ROOT/F['code_root'];assert all(sha(C/n)==h for n,h in F['files'].items())
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
os.environ.update(GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',GENOS_ONTOLOGY_CODE_ROOT=str(C),LOOP_TEST_REPOSITORY_ROOT=str(ROOT))
os.environ.pop('DP',None)
gold=module('adr1292_gold',GOLD/'connect.py');baseline=gold.engine_binding()
binding={**baseline,'engine_root':str(C.relative_to(ROOT)),'engine_files':F['files'],
 'engine_release_id':'UNQUALIFIED_RESEARCH_ADR1292','engine_manifest_sha256':F['candidate_revision']['revision_sha256']}
def verified():
 assert all(sha(C/n)==h for n,h in F['files'].items())
 return binding
gold.engine_binding=verified
writer=module('adr1292_writer',ROOT/'06_TOOLS/maintenance/publish_gold_ontology_samples.py')
DID='7bbe815ff43b6635';start=time.monotonic();result={'mode':args.mode,'model_calls':0,'ddl_changes':0,'quality_certified':False}
try:
 with gold.open_store(documents=[DID],seconds=300,max_calls=5000) as (store,request,transport):
  from semantic_runtime.ontology_work import configuration as cfg,mapped_authoring, wiki_contracts as wc,runtime
  from semantic_runtime.legal_agent.ontology_compiler import content_hash
  from semantic_runtime.legal_agent.errors import ContractError
  from semantic_runtime.contracts import digest
  sys.path[:0]=[str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
  from test_domain_profile_workflow import normalized_output
  from test_wiki_workspace import seed,compiled,wire_normalization,pin
  import test_wiki_workspace as fixtures
  old_proposal=fixtures.typed_proposal
  def proposal(*a,**kw):
   value=old_proposal(*a,**kw)
   def walk(v):
    if isinstance(v,dict):
     if set(v)=={'source','quote'} and v['source']=='S1':v['source']=original['id']
     for child in v.values():walk(child)
    elif isinstance(v,list):
     for child in v:walk(child)
   walk(value);return value
  fixtures.typed_proposal=proposal
  # Preserve source metadata and bytes; choose a bounded real article.
  original=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1255-wiki-workspace-oracle-live/artifacts/design/originals.json')[2]
  assert original['anchor']['document_id']==DID
  text=store.gold_ports.source_reader(original['anchor'])
  assert text==original['text'] and content_hash(text)==original['anchor']['content_sha256']
  scope={'namespace':'ADR1292-console-contract-r2','source_snapshot':request.snapshot.dataset_version,'acl_ref':digest(['ADR1292',DID])}
  config={'version':'ontology-connection-v1','environment':'local',
   'operators':{'adr1292-test':{'document_ids':[DID],'workspace_publish':True}},
   'domain_profile':scope,'workspace_runtime_scopes':[scope],
   'work_store':{'kind':'local','path':str(ART/'oracle-work-objects')},'readiness_anchors':[original['anchor']]}
  config_path=O/'settings.json';put(config_path,config);os.environ['GENOS_RAG_ONTOLOGY_CONFIG']=str(config_path)
  # Only this test's ephemeral reader receives the private scope. Nothing is
  # written to Gold ontology_settings or production workspace_runtime_scopes.
  assert not getattr(store.gold_ports.ontology,'workspace_scopes',())
  with mapped_authoring.context(actor='adr1292-test',store=store,request=request,
      writer_connect=writer.writer_connection,agent_owner='A8_GONT_AGENT',config=config):
   assert cfg.connection_status(actor='adr1292-test')['status']=='NO_SCOPE'
   store.gold_ports.ontology.workspace_scopes=frozenset([wc.scope_key(scope)])
   w=cfg.workspace_workflow(actor='adr1292-test');domain=cfg.domain_workflow(actor='adr1292-test')
   try:
    assert domain.glossary.binding['snapshot']==request.snapshot.dataset_version
    if args.mode=='create':
     domain.glossary.check();assert read(ART/'oracle-create/result.json')['glossary_restored']==4
     result['glossary_restore_evidence']=str((ART/'oracle-create/result.json').relative_to(ROOT))
    else:
     domain.glossary.check();result['glossary_binding_verified']=True
    if args.mode=='create':
     assert cfg.connection_status(actor='adr1292-test')['status']=='EMPTY'
     profile=domain.save_profile(read(C/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json'),read(C/'00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json'))
     domain.review_profile(profile['bundle_id'],profile['revision'],profile['work_hash'],True,'격리 합성 연결 검사: 법률 품질 승인 아님')
     def generate(prompt,context,schema):return wire_normalization(normalized_output(context)),{'synthetic':'ADR1292'}
     domain.generate=generate
     env=SimpleNamespace(w=domain,repo=domain.repo,source=original,profile_id=profile['bundle_id'],profile_work_hash=profile['work_hash'])
     item=seed(env,w,'oracle-console-one',text=text)
     again=w.apply(**item.spec);assert again['reused'] is True
     draft,_=compiled(env,w,item)
     domain.review(draft['bundle_id'],draft['revision'],draft['work_hash'],True,'격리 합성 원문/저장/연결 검사, 운영 지식으로 사용하지 않음')
     stage=domain.stage_publication(draft['bundle_id'],draft['revision'],draft['work_hash'],0)
     receipt=domain.verify_publication(stage['publication_id']);domain.activate_publication(stage['publication_id'],0,receipt)
     rows=store.gold_ports.ontology.lookup(original['anchor'],{DID})
     selected=next(r for r in rows if r['publication_id']==stage['publication_id'])
     assert selected['context']['assembly_package']['paths'][0]['body']==text
     saved={'draft':draft,'stage':stage,'receipt':receipt,'statement_id':item.sid,'entry_id':item.eid,
      'publication_context':selected['context'],'scope':scope,'source':original}
     put(ART/'oracle-created.json',saved)
     assert cfg.connection_status(actor='adr1292-test')['status']=='READY'
     result.update(idempotent_write=True,compiled_approved_activated=True,original_exact=True)
    else:
     saved=read(ART/'oracle-created.json');pid=saved['stage']['publication_id'];bid=saved['draft']['bundle_id']
     assert w.item(saved['entry_id'])['kind']=='ENTRY'
     row=store.gold_ports.ontology.publication(pid,{DID})
     assert row['context']==saved['publication_context']
     refs={'assessment_basis':{'workspace_publications':[{'bundle_id':bid,'publication_id':pid,'package_sha256':row['package_sha256']}]}}
     runtime.assert_assessment(refs,{DID},store.gold_ports.ontology)
     with __import__('pytest').raises(ContractError):store.gold_ports.ontology.publication(pid,{'unauthorized'})
     if args.mode=='withdraw':
      sid=saved['statement_id'];w.apply(change_id='oracle-console-withdraw',expected=pin(w,sid),operations=[{'op':'RETRACT','target':sid,'value':{'reason':'격리 검증 종료: 시험 게시 철회'}}])
      with __import__('pytest').raises(ContractError):runtime.assert_assessment(refs,{DID},store.gold_ports.ontology)
      assert domain.repo.head(bid)['publication_id'] is None
      assert cfg.connection_status(actor='adr1292-test')['status']=='EMPTY'
      result['withdrawal_blocks_saved_answer']=True
     result.update(fresh_process_exact=True,acl_rejected=True)
   finally:domain.glossary.reader.close()
  result.update(status='PASS',source_sql_calls=request.sql.calls)
except Exception as exc:
 result.update(status='FAIL',error_type=type(exc).__name__,error=str(exc));(O/'error.txt').write_text(traceback.format_exc())
finally:
 result.update(runner_sha256=sha(__file__),seconds=time.monotonic()-start,code_unchanged=all(sha(C/n)==h for n,h in F['files'].items()),active_unchanged=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==F['pointer_sha256'])
 put(O/'result.json',result);print(json.dumps(result,ensure_ascii=False))
assert result['status']=='PASS'
