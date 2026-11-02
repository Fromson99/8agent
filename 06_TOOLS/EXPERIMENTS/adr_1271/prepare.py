from common import *
import sqlite3,shutil,os
from copy import deepcopy
DES.mkdir(parents=True,exist_ok=True)
base=ART/'corpus';base.mkdir(exist_ok=False)
sys.path[:0]=[str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import pytest
import conftest
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation
from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.unit_fulltext import build
texts=['제1조 일반 작업: 일반 작업은 서면 승인을 받은 뒤 시작하고, 종료 후 48시간 이내에 담당자에게 보고하여야 한다. 제2조의 긴급 복구 작업은 예외로 한다.',
'제2조 긴급 복구: 긴급 복구 작업은 사전 승인 없이 시작할 수 있다. 작업을 시작한 후 24시간 이내에 담당자에게 보고하여야 한다.',
'제3조 기록 보관: 승인과 보고 기록은 기록부에 보관한다.']
raw=source(base/'raw.sqlite',[('synthetic-recovery-v1','복구검증규정',texts)])
with sqlite3.connect(raw) as db:
 for did,uid,text in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
  unit=json.loads(text);coordinate=find_coordinates(unit['surface'])[0].coordinate
  unit.update(title=['일반 작업','긴급 복구','기록 보관'][int(uid)],legal_coordinate=coordinate.as_dict(),coordinate_scope='body',coordinate_key='body:'+coordinate.canonical_surface())
  db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',(json.dumps(unit,ensure_ascii=False),did,uid))
glossary=conftest.term_glossary.__wrapped__(base)
build_generation(raw,glossary,base/'built',serving=True)
data=base/'built/generation';index=base/'index';build(data,data/'navigation',index,workers=1)
source_manifest=read(data/'manifest.json')
put(DES/'source.json',{'synthetic':True,'document_ids':['synthetic-recovery-v1'],'texts':texts,'data_path':str(data.relative_to(ROOT)),'index_path':str(index.relative_to(ROOT)),'source_manifest':source_manifest,'scope':'three fixed synthetic clauses, same native product profile; no legal-quality inference'})
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/p['manifest_path'])
put(DES/'baseline.json',{'pointer':p,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'selected_release':deepcopy(r),'release':dict(r,data_path=str(data.relative_to(ROOT))),'experimental_data_override':True})
criteria={'hypothesis':'Matching structural scope prefixes on a single exact coordinate normalize without changing document, scope, or original-evidence gates, allowing actual Qwen fault repair to continue.',
'success':['Fault injected exactly once into an actual Qwen READ response; original and changed envelopes preserved','Actual Qwen corrective call leads to validated answer and durable source/claim receipts','Same request returns the same stored answer with zero extra physical calls','Original text/hash/ACL and all current scope/need/requirement validation remain enforced'],
'failure':'422, 500, transport failure, missing injection or missing answer is not successful fault recovery. Preserve UNKNOWN; no same-cell redispatch. Stop remaining cells after UNKNOWN/provider429 exhaustion or missing injection. Missing injection is NOT_TESTED, even if API200.',
'limits':{'physical_model_calls_per_case':40,'wall_seconds':1800,'per_model_seconds':180,'tool_actions':1024,'rss_GiB':4,'available_GiB':3,'swap_growth_MiB':128},
'case_ids':['duplicate-selection','conflicting-selection','malformed-json'],
'change_from_1270':'All three real repairs were rejected on body:제1조 coordinates. The only product change normalizes matching scope prefixes and supplies precise repair diagnostics; mismatch/ranges remain invalid. Same fixed three clauses and question; stochastic paired performance inference is not claimed.',
'injection':'First actual READ only: append identical selection; or append same selection with contradictory DEPENDENCY/source_ref=null (also invalid with no delivered original); or truncate its JSON. The model naturally produced the original, not the injected fault.',
'quality':'Technical, in-sample, synthetic-original test. Not a representative legal-quality, latency or production failure-rate evaluation.'}
put(DES/'criteria.json',criteria)
question='복구검증규정 제1조와 제2조를 조문 구조로 찾아 원문을 읽고, 각 조문의 승인·보고 기준을 알려주세요.'
cases=[{'id':name,'fault':name,'request':{'API_TYPE':'RAG_ASK','json':{'question':question,'document_ids':['synthetic-recovery-v1'],'use_llm':True,'public_question':True,'team_id':'risk_team','session_id':'adr1271-'+name,'request_id':'recovery-'+name}}} for name in criteria['case_ids']]
put(DES/'cases.json',cases)
put(DES/'authorization.json',{'user_instruction':'전체다 수정했냐? qwen으로 실험하고 (데이터 보내도 됨 외부로) 확인해봐','external_transmission_allowed':True,'synthetic_originals':True,'document_ids':['synthetic-recovery-v1'],'question':question,'source_manifest_sha256':sha(data/'manifest.json'),'model':'qwen/qwen3.8-27b','actual_thread_id':'01a19992-930c-73c2-830b-199e61fc1869'})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual correction plus saved-answer reuse per fault',success_criteria=criteria['success'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Historical ADR1266/1268 only, no fresh baseline model',controls='Different corpus so no failure-rate or latency A/B claim')
m['design']['arms'][1].update(changes='Source target exact coordinate scope-prefix contract repair only; same three-clause source and structure question',controls='Current full profile, Qwen/provider policy, same budgets and validators')
m['runs'][0].update(arm_ids=['repaired'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='Three fixed synthetic-source fault cases, first actual READ response only')
m['dataset'].update(name='Three-clause synthetic recovery policy',version='20261102-r1',frozen_source=str((DES/'source.json').relative_to(ROOT)),sha256=sha(DES/'source.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='Fault recovery test, no retrieval implementation/effect comparison.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason,stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':None,'artifact_path':None,'sha256':None,'not_applicable_reason':reason})
put(ADR/'실험/manifest.json',m)
sources=set(r['files'])
for path in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):sources.add(str(path.relative_to(ROOT)));sources.update(read(path).get('files',{}))
sources.update(['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py'])
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=ac.snapshot(ADR,'repaired',sorted(sources),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])/'snapshot'
exec((Path(__file__).parent/'patch_candidate.py').read_text(),dict(ROOT=ROOT,S=S,sha=sha,json=json))
put(DES/'working-before.json',{n:sha(ROOT/n) for n in sorted(sources)});put(DES/'candidate-path.json',{'snapshot':str(S.relative_to(ROOT))})
print('Prepared',len(sources),'files; synthetic source',source_manifest['generation_id'])
