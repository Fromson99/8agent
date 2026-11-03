from common import *
import shutil
DES.mkdir(parents=True,exist_ok=True)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path']);code=ROOT/release['code_root']
assert pointer['generation']==133
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
assert all(sha(code/n)==h for n,h in release['files'].items())
put(DES/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release,'source_manifest':read(ROOT/release['data_path']/'manifest.json')})
criteria={
 'hypothesis':'Selected local MAIN functions operate through native APIs; existing published ontology may preserve answer completeness with lower model work or latency than OFF on identical public questions.',
 'success':['All22 feature rows report actual evidence level separately: real data/model vs synthetic contract vs not executed.',
 'Comparison returns an internal-concept table with exact internal and external originals, citations and explicit unknowns; no source mismatch.',
 'Each ON/OFF pair uses identical code, question, corpus, model, budgets and fresh process/runtime; only ontology enable/context changes.',
 'ON actually acquires and delivers the relevant existing publication. Merely enabled=true is not an ON pass.',
 'Both arms return supported nonempty answers covering frozen required source rules, without invented conclusions or source/ACL errors.',
 'Observed efficiency improvement requires both complete pairs, no quality regression, and at least10percent lower summed end-to-end seconds OR physical model calls OR reported total tokens. Report the individual metrics and regressions, no population claim.',
 'Stored request requery adds zero physical model calls and preserves answer.'],
 'failure':['Source-only/partial responses are functional partial, not complete legal answers. One failed pair prevents aggregate improvement claim.',
 'Unknown physical model outcome or resource stop ends new external requests; no automatic rerun of terminal cells. Known nontransport API422 is recorded and remaining predeclared cells may continue.'],
 'design':{'pairs':2,'order':['ontology-365/off','ontology-365/on','ontology-369/on','ontology-369/off'],'repeats':1,
 'process':'fresh process and fresh isolated SQLite request journal per cell; no Oracle data writes; OS/Oracle caches not reset',
 'comparison':'one synthetic internal/external pair; real model; no actual private document transfer',
 'ordinary_features':'actual selected local API read-only queries plus selected-code fixture API/display checks'},
 'limits':{'per_cell_physical_calls':40,'per_cell_wall_seconds':1800,'per_model_seconds':180,'total_physical_calls':120,
 'start_available_GiB':5,'minimum_available_GiB':3,'rss_GiB':4,'max_swap_growth_MiB':128,'workspace_free_GiB':20},
 'quality':'Software probe on stored corpus, not current-law advice or statistical legal-quality certification. Manual source-based scoring; no external judge.',
 'no_changes':['selected MAIN','product code','source data','Oracle writes/DDL','existing publications','Gold configuration','GENOS deployment']}
put(DES/'criteria.json',criteria)
cases=[{'id':'ontology-365','question':'상법 제365조에 따른 정기총회, 연 2회 이상 결산기를 정한 회사의 총회, 임시총회의 소집 시기를 각각 알려주세요.','document_ids':['7bbe815ff43b6635'],'article':365,'arms':['baseline','ontology-on']},
 {'id':'ontology-369','question':'상법 제369조에 따른 1주당 의결권 수와 자기주식·주식 상호보유의 의결권 제한은 어떻게 되나요?','document_ids':['7bbe815ff43b6635'],'article':369,'arms':['baseline','ontology-on']},
 {'id':'comparison-one','question':'대사: 모의내규의 영업일 승인 기준이 모의외규와 일치하는지, 양쪽 원문을 제시하여 비교해 주세요.','document_ids':['inside','outside'],'arms':['baseline'],'synthetic':True}]
put(DES/'cases.json',cases)
put(DES/'authorization.json',{'user_instruction':'대사표와 온톨로지 on을 해서 성능 올라가는거 확인 여기까지 기본으로 추가해줘 나머진 필요없고 그리고 저것들이 실제로 로컬에서는 동작을 잘하는지 확인해봐',
 'allowed_data':'Registered public commercial-law originals and existing source-bound ontology; synthetic internal/external comparison fixture only',
 'questions':[c['question'] for c in cases],'source_documents':['7bbe815ff43b6635','inside','outside'],'model':'qwen/qwen3.8-27b','new_judge_calls':0,'total_physical_limit':120})
prepared=read(ROOT/'09_ARTIFACTS/AUDITS/20261030-gold-ontology-publication/prepared.json')
gold=[]
for entry in prepared['entries']:
 if any(entry['bundle_id'].endswith('-'+str(c.get('article'))) for c in cases):
  gold.append({'bundle_id':entry['bundle_id'],'originals':entry['work']['originals'],'paths':entry['proposal']['paths'],'not_for_product_input':True})
put(DES/'scoring-only-originals.json',gold)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source-correct completed paired answers, followed by elapsed seconds / physical calls / reported tokens',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Ontology OFF on unchanged MAIN133; also independent functional checks and one synthetic comparison','controls':'Exact same selected code/source/model/budgets as ON; fresh process/runtime'},
 {'id':'ontology-on','role':'candidate','derived_from':['baseline'],'changes':'Existing ontology enabled DB mode; no implementation modification','controls':'Same code/source/model/questions; existing publications only'}]
m['runs'][0].update(arm_ids=['baseline','ontology-on'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='Two prospective fixed article questions, counterbalanced order, one run per cell; one independent synthetic comparison')
m['dataset'].update(name='Stored public Commercial Act365/369 and synthetic two-document approval comparison',version='20261103-v1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ['baseline','ontology-on']}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=[str((code/n).relative_to(ROOT)) for n in release['files']]
paths += ['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py']
candidate=ac.snapshot(ADR,'selected-main133',paths,experiment_id=m['experiment_id'],arm_id='ontology-on',run_ids=['run-001'])
ac.freeze(candidate);assert not ac.validate(candidate),ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];snap=candidate/'revisions'/rev['revision_id']/'snapshot';C=snap/release['code_root']
assert all(sha(C/n)==h for n,h in release['files'].items())
pin={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'candidate.json',{'code_root':str(C.relative_to(ROOT)),'snapshot_root':str(snap.relative_to(ROOT)),'pin':pin,'selected_files':release['files']})
transport=ART/'transport';transport.mkdir(exist_ok=False)
modules={'lawrag':'02_BACKEND/lawrag/__init__.py','lawrag.core':'02_BACKEND/lawrag/core/__init__.py','lawrag.research':'02_BACKEND/lawrag/research/__init__.py','lawrag.core.request_deadline':'02_BACKEND/lawrag/core/request_deadline.py','lawrag.research.experiment_client':'02_BACKEND/lawrag/research/experiment_client.py','lawrag.research.openrouter_legal_adapter':'02_BACKEND/lawrag/research/openrouter_legal_adapter.py'}
for rel in modules.values():
 src=C/rel
 if not src.is_file():src=ROOT/rel
 dst=transport/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
put(transport/'transport-pins.json',{'modules':modules,'files':{rel:sha(transport/rel) for rel in modules.values()}})
gp=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';gout=ART/'gold-connector';gout.mkdir(exist_ok=False)
for name in ['connect.py','engine_common.py','physical_mapping.py','binding.json','ACTIVE_MAPPING.json','ontology_settings.json']:
 shutil.copyfile(gp/name,gout/name)
mapping=read(gp/'ACTIVE_MAPPING.json')['mapping_file'];shutil.copyfile(gp/mapping,gout/mapping)
put(gout/'active-pointer.json',pointer)
for enabled in [True,False]:put(DES/('ontology-on.json' if enabled else 'ontology-off.json'),{'schema_version':'gold-ontology-settings-v1','enabled':enabled})
put(DES/'root-files.json',{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'service.py',ROOT/'service/__init__.py',ROOT/'service/service.py',ROOT/'main_router.py',ROOT/'main_workflow.py'] if p.exists()})
print('PREPARED',len(release['files']),'selected files;',rev['revision_id'])
