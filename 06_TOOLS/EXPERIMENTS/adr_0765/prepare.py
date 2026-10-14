"""Freeze the prospective recall contract before changing candidate code."""
import hashlib,json,sqlite3,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');manifest=read(R/pointer['manifest_path'])
for p,h in manifest['files'].items():assert sha(R/p)==h,p
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':manifest})
criteria={
 'scope':'MAIN53 incremental extractive memory cards; zero-model bounded lexical recall; relevance selected in existing request-entry or memory-intent; current source re-read; ordinary discovery on rejection/error/miss.',
 'required':{'new_contracts_all_pass':True,'no_new_regression':True,'candidate_supported':3,'matched_memory_selected':2,'no_match_normal_discovery':1,'auxiliary_model_calls':0,'memory_searches_per_request_max':1,'offered_cards_max':3,'card_chars_max':2400,'recall_seconds_max':0.5,'successful_pair_calls_delta_max':0,'successful_pair_seconds_ratio_max':1.5,'acl_generation_invalidation_original_integrity':True},
 'execution':{'order':[['public-memory-01','baseline'],['public-memory-01','integrated'],['public-memory-02','integrated'],['public-memory-02','baseline'],['public-memory-03','baseline'],['public-memory-03','integrated']],'repeats':1,'max_model_calls_per_request':40,'no_adaptive_repeats':True},
 'limits':'No measured speed claim from three cases. CM is development-only local data; never sent externally. Small public qualification certifies wiring and bounds, not all legal semantics.',
 'design':'Derived versioned SQL cards and indexed token postings, added compatibly without mutating immutable sw_* authority. Public/private and source-generation filters before model exposure; bounded shortlist and per-read authority checks. No saved answer, facts or approved legal claims in cards. No model at save/search; reuse existing INTENT purpose and original question/topic/queries as extractive discovery summary. Default three candidates, two chosen, 2400 serialized characters, one lookup. Roll back feature plus release; projection can remain inert.',
 'authorization':'User explicitly requested redesign, working implementation and current local MAIN integration. Existing public source export policy only; GENOS deployment separate.',
 'failure':'Do not promote on any required gate failure; retain all outputs; follow-up candidate or rerun needs new ADR.'}
put(D/'criteria.json',criteria)
db=sqlite3.connect((R/manifest['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
specs=[
 ('public-memory-01','article:4bad08abfcca5d38281da8ad','상법상 영업에 관한 대리권 존속','영업 대리권은 본인이 사망하면 사라지는가?','상인이 영업과 관련해 준 대리권이 있는데, 본인이 사망하면 그 권한도 없어지나요? 상법의 대리권 존속 규정만 확인해 주세요.',True),
 ('public-memory-02','article:1d686f0620f2bc30efbc3873','상법상 대화자간 청약의 구속력','대화자간 계약 청약에서 즉시 승낙하지 않은 경우의 효력','대화 중 계약을 청약했지만 상대방이 즉시 승낙하지 않았습니다. 상법에서 대화자간 청약의 효력은 어떻게 처리하나요? 이 규정 자체만 설명해 주세요.',True),
 ('public-memory-03','article:b4b48aca62da213f740376ee','상사법정이율',None,'상법 제54조에서 상행위 채무의 법정이율을 얼마로 정하는지 해당 조문만 설명해 주세요.',False)]
allowed=set(read(R/manifest['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
cases=[];gold=[];seeds=[]
for cid,sid,topic,prior,q,matched in specs:
    source=json.loads(db.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()[0]);assert source['document_id'] in allowed
    cases.append({'case_id':cid,'question':q,'memory_expected':matched,'role':'prospectively-authored-public-holdout','arm_ids':['baseline','integrated']})
    gold.append({'case_id':cid,**{k:source[k] for k in ('id','document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}})
    if prior:seeds.append({'seed_id':cid,'question':prior,'topic':topic,'source_id':sid,'provenance':'SYNTHETIC_PUBLIC_MEMORY_FIXTURE_NOT_ACTUAL_USER_HISTORY'})
db.close()
put(D/'dataset.json',{'cases':cases,'source_generation':manifest['data_path'],'gold_product_visible':False})
put(D/'memory-seeds.json',{'seeds':seeds,'scope':'Authored public-only private-scope fixtures, never internal CM','answer_in_seed':False})
put(D/'gold.json',{'product_visible':False,'cases':gold})
m=read(A/'실험/manifest.json');m['decision_eligible']=True;m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Bounded memory reuse without auxiliary model calls; native source-backed completion',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,repeats=1)
for arm in m['design']['arms']:arm.update(changes='Unmodified selected MAIN53' if arm['id']=='baseline' else criteria['scope'],controls='Same public source generation, private public-only memory seeds, model/provider, native API, budgets, one fresh process per request')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['dataset'].update(name='Three prospective public recall cases; CM excluded',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Fixed three paired public cases in criteria.execution.order; no adaptive repetitions',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={x['id']:stages for x in m['design']['arms']}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for p in sorted(set(manifest['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',p]
subprocess.run(cmd,cwd=R,check=True)
print('Prospective design and MAIN53 baseline frozen; production unchanged')
