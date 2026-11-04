from pathlib import Path
import json,sys,shutil
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent;OLDT=ROOT/'06_TOOLS/EXPERIMENTS/adr_1312'
for n in ['common.py','resource_guard.py','sql_observer.py','check.py']:
 s=(OLDT/n).read_text().replace('ADR-1312-finish-handoff-live','ADR-1313-sqlite-oracle-diverse-validation')
 if n=='check.py':s=s.replace("default='after'","default='sqlite'")
 (T/n).write_text(s)
sys.path.insert(0,str(T));from common import *
DES.mkdir(exist_ok=False);parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1312-finish-handoff-live';base=read(parent/'artifacts/design/baseline-after.json');put(DES/'baseline.json',base)
put(DES/'ontology-off.json',{'schema_version':'gold-ontology-settings-v1','enabled':False})
D='7bbe815ff43b6635'
def single(n):return {'kind':'SINGLE','value':{'n':n}}
def group(article,include=None,exclude=None):return {'parent_path':[{'unit':'조','n':article}],'unit':'항','include':include or [{'kind':'ALL'}],'exclude':exclude or []}
def sel(groups):return {'coordinate_scope':'body','groups':groups}
cases=[{'id':'paragraph-all','category':'query-scope','selection':sel([group(369)]),'expected':['1421','1422','1423']},
 {'id':'exclude-middle','category':'query-scope','selection':sel([group(369,exclude=[single(2)])]),'expected':['1421','1423']},
 {'id':'range-exclude','category':'query-scope','selection':sel([group(369,[{'kind':'RANGE','start':{'n':1},'end':{'n':3},'start_inclusive':True,'end_inclusive':True}],[single(2)])]),'expected':['1421','1423']},
 {'id':'duplicate-reorder','category':'query-scope','selection':sel([group(369,[single(3),single(1),single(3)])]),'expected':['1421','1423']},
 {'id':'multiple-articles','category':'query-scope','selection':sel([group(365),group(369)]),'expected':['1389','1390','1391','1421','1422','1423']},
 {'id':'missing-endpoint','category':'query-guards','selection':sel([group(369,[single(99)])]),'expected_error':'MISSING_ENDPOINT'},
 {'id':'missing-parent','category':'query-guards','selection':sel([group(99999)]),'expected_error':'MISSING_PARENT'},
 {'id':'empty-exclusion','category':'query-guards','selection':sel([group(369,exclude=[{'kind':'ALL'}])]),'expected_error':'EMPTY_SELECTION'},
 {'id':'reversed-range','category':'query-guards','selection':sel([group(369,[{'kind':'RANGE','start':{'n':3},'end':{'n':1},'start_inclusive':True,'end_inclusive':True}])]),'expected_error':'REVERSED_RANGE'},
 {'id':'root-article-set','category':'query-scope','selection':sel([{'parent_path':[],'unit':'조','include':[single(365),single(369)],'exclude':[]}]),'expected':['1388','1420']}]
put(DES/'query-cases.json',{'document_id':D,'selections':cases,'fts':[{'id':'single-term','terms':['의결권']},{'id':'phrase','terms':['의결권은 없다']},{'id':'multi-term','terms':['의결권','자기주식']},{'id':'no-hit','terms':['존재하지않는검증용검색어1313']}],'source_blocks':['1389','1390','1391','1421','1422','1423'],'global_deadline_seconds':300,'oracle_max_queries':2500,'same_case_retry':False})
criteria={'hypothesis':'Working latency repairs preserve exact structured selection and original text on SQLite and real readonly Oracle Gold; repeated successful selection/source calls reuse bound data without weakening errors, ACL, deadline, history or final validation.', 'primary_metric':'Cross-DB exact IDs/selection hash/source content agreement and cache-hit SQL counts; diverse API/contracts; request preparation and percase times descriptive only.', 'success':['10 structural cases yield declared exactIDs or declarederror on bothDBs.','6sourceblocks exactly match original text/version/hash and repeat reads preserve values; unauthorized scope/tampered selection remain rejected.','4fulltext queries preserve scoped results and ordering/scores when published statistics match; if mismatch identify document/published-index/version cause.','No new fixture-independent regression in targeted source/scope/FTS/cache/read-review/stop/API tests.'], 'failure':['Source/ACL/hash mismatch, unexpected corpus write or credential exposure stops actual DB sequence.','Per-request300seconds/2500Oraclecalls resourcebudget stops that DB arm; preservecompletedcases; no samecellretry.'], 'order':['contracts','sqlite','oracle'],'new_model_calls':0,'main_unchanged':True,'ddl':0,'oracle_writes':0,'scope':'Local Oracle23 Gold mapped read port, real published corpus. Not fieldOracle19/Dataiku throughput or model answer quality. Both use same517workingfiles; main unchanged.','limits':read(parent/'artifacts/design/criteria.json')['limits'],'followup':'New live NearAI diverse questions require separate frozen followup after actual DB findings; no replay of priorUNKNOWNcell.'}
put(DES/'criteria.json',criteria)
put(DES/'working-files.json',{n:sha(ROOT/n) for n in base['release']['files']})
gp=ART/'gold-connector';gp.mkdir();gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
for p in gold.iterdir():
 if p.is_file() and p.suffix in ('.py','.json','.yaml'):shutil.copyfile(p,gp/p.name)
put(gp/'active-pointer.json',base['pointer'])
m=read(ADR/'실험/manifest.json');old=read(parent/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1312-experiment-v1/after'],'changes':'Completed repair lineage, previous live incomplete','controls':'Same5repairmodules'},*({'id':a,'role':'candidate','derived_from':['baseline'],'changes':'Current working code on '+a,'controls':'Same source corpus/version and typed query fixtures; no model, no default table ablation'} for a in ('sqlite','oracle'))]
m['design']['retrieval_stage_plan']={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{}}
m['dataset'].update(name='Declared structured-query and source-contract cases',version='20261104-cross-db-v1',frozen_source=str((DES/'query-cases.json').relative_to(ROOT)),sha256=sha(DES/'query-cases.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']=old['llm_policy'];m['llm_policy']['llm_calls']=[];m['llm_calls']=[];m['retrieval_accounting'].update(changed=False,not_applicable_reason='No product answer/retrieval selection experiment; typed source/query API equivalence with declared coordinates and no model delivery.');m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=m['retrieval_accounting']['not_applicable_reason'])
m['runs'][0].update(arm_ids=['sqlite','oracle'],selection_rule='Fixed10typed selections,6blocks,4fts plusguards onceeach perDB; contracts first, then SQLite, thenOracle, no adaptive rerun.',artifact_path=str((RUN/'result.json').relative_to(ROOT)));m['lineage']['hypothesis_delta']=criteria['hypothesis'];put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
for arm in ('sqlite','oracle'):
 can=ac.snapshot(ADR,arm,list(base['release']['files']),experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001']);put(DES/(arm+'-path.json'),{'candidate':str(can.relative_to(ROOT))})
print('1313 declared cases and exact working snapshots prepared')
