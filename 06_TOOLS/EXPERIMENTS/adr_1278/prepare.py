from common import *
import sqlite3,shutil,os
from copy import deepcopy
DES.mkdir(parents=True,exist_ok=True)
base=ART/'corpus';base.mkdir(exist_ok=False)
sys.path[:0]=[str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import pytest,conftest
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation
from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.unit_fulltext import build
texts=['제1조 작업 승인: 일반 작업은 비용이 1000000원 이하이고 담당자의 서면 승인을 받은 경우에만 시작할 수 있다. 두 요건은 모두 충족하여야 한다. 비용은 1건의 작업 총액이다.',
'제2조 긴급 예외: 사람의 생명 보호를 위한 긴급 작업은 제1조의 비용 한도와 사전 승인 없이 시작할 수 있다. 작업 시작 후 24시간 이내에 담당자에게 보고하여야 한다.',
'제3조 기록: 일반 작업과 긴급 작업의 비용, 승인 및 보고 기록을 기록부에 보관하여야 한다.']
raw=source(base/'raw.sqlite',[('synthetic-whatif-v1','가정검증규정',texts)])
with sqlite3.connect(raw) as db:
 for did,uid,text in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
  unit=json.loads(text);coordinate=find_coordinates(unit['surface'])[0].coordinate
  unit.update(title=['작업 승인','긴급 예외','기록'][int(uid)],legal_coordinate=coordinate.as_dict(),coordinate_scope='body',coordinate_key='body:'+coordinate.canonical_surface())
  db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',(json.dumps(unit,ensure_ascii=False),did,uid))
glossary=conftest.term_glossary.__wrapped__(base)
build_generation(raw,glossary,base/'built',serving=True)
data=base/'built/generation';index=base/'index';build(data,data/'navigation',index,workers=1)
source_manifest=read(data/'manifest.json')
put(DES/'source.json',{'synthetic':True,'document_ids':['synthetic-whatif-v1'],'texts':texts,'data_path':str(data.relative_to(ROOT)),'index_path':str(index.relative_to(ROOT)),'source_manifest':source_manifest})
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/p['manifest_path']);assert p['generation']==132
put(DES/'baseline.json',{'pointer':p,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'selected_release':r,'release':dict(r,data_path=str(data.relative_to(ROOT))),'experimental_data_override':True})
question='가정검증규정 제1조와 제2조 원문을 읽고 판단해 주세요. 이번 사건은 긴급 작업이 아닌 일반 작업입니다. 작업 비용 cost는 1500000원이고 담당자의 서면 승인 여부는 아직 모릅니다. 작업을 시작할 수 있나요? 금액 요건과 승인 요건을 구분하고 미확인 사항을 알려주세요.'
request={'question':question,'document_ids':['synthetic-whatif-v1'],'use_llm':True,'public_question':True,'team_id':'risk_team','session_id':'adr1278-review-whatif','request_id':'baseline-case'}
put(DES/'cases.json',[{'id':'review-whatif','request':{'API_TYPE':'RAG_ASK','json':request},'followup_plan':['if first source-only and REVIEW_AGAIN offered: one explicit review','VIEW_REVIEW without model','WHAT_IF FACT cost=1500000 then cost=500000 independently','WHAT_IF RULE limit=2000000','SCENARIO_REVIEW FACT cost=500000 once','duplicate each completed request; reread original after branch']}])
criteria={'hypothesis':'Actual Qwen with a source-bound reviewed ontology produces a preserved incomplete or supported response; current acquisition and review stay separate; numeric branches preserve unknown approval and semantic branch preserves baseline.',
'success':['First response has verified explanation and current source acquisition separate from review','Ontology catalog received by actual Qwen; report explicit adoption or NOT_RECORDED without inventing use','View and numeric comparisons issue zero physical calls, high-cost FALSE and low-cost TRUE while final conclusion remains UNCONFIRMED','Semantic branch produces response with hypothetical marker, different case and unchanged baseline; approval is not invented','Repeated operations cause zero physical calls; original spans, ACL, hashes and budgets verify'],
'failure':'Any UNKNOWN or exhausted provider error stops additional model turns; no rerun of a terminal cell. Source-only response is not semantic legal success. Unavailable branch is NOT_TESTED. No response injection or output rewriting.',
'limits':{'physical_model_calls_total':40,'per_turn_wall_seconds':1800,'per_model_seconds':180,'rss_GiB':4,'minimum_available_GiB':3,'max_swap_growth_MiB':128},
'quality':'One in-sample synthetic regulation, manually prepared reviewed ontology and fixed interactions; not a legal quality benchmark, no causal A/B or performance improvement claim.',
'authoring':'Synthetic source and source-bound graph/AST are predefined test input, normal approval/publication contracts enforced in isolated SQLite. No claim of real-model ontology authoring.'}
put(DES/'criteria.json',criteria)
put(DES/'authorization.json',{'user_instruction':'한번 실제로 실험해봐','scope':'One synthetic regulation and approved synthetic ontology; native API question and exact server-issued actions; no private source or answer key','external_transmission_allowed':True,'document_ids':['synthetic-whatif-v1'],'questions':[question],'model':'qwen/qwen3.8-27b','maximum_model_turns':3,'physical_limit':40})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='actual API source/ontology/branch integrity with explicit semantic limitation',success_criteria=criteria['success'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Historical completed ADR1277 only',controls='Different synthetic question, no stochastic A/B claim')
m['design']['arms'][1].update(changes='Current working review-explanation and typed branch implementation',controls='Same native pipeline, approved Qwen policy, original validation and durable requests')
m['runs'][0].update(arm_ids=['verified'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='One prospectively fixed conversation with conditional single rereview and one semantic branch')
m['dataset'].update(name='Synthetic cost and written approval rule',version='20261102-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='Functional branch and source integrity test; retrieval implementation unchanged, no recall-effect benchmark.';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sources=set(r['files'])
for path in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):sources.add(str(path.relative_to(ROOT)));sources.update(read(path).get('files',{}))
sources.update(['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py'])
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=ac.snapshot(ADR,'verified',sorted(sources),experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'])/'snapshot'
put(DES/'working-before.json',{n:sha(ROOT/n) for n in sorted(sources)});put(DES/'candidate-path.json',{'snapshot':str(S.relative_to(ROOT))})
print('Prepared',len(sources))
