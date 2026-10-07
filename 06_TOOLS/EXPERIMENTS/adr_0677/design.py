"""Freeze unseen groups and user-authoritative acceptance before any model call."""
from pathlib import Path
import json,sqlite3,hashlib,copy
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0675-investigation-control-binding-closure/artifacts/design'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
generation=R/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation';c=sqlite3.connect(generation.resolve().as_uri()+'/store.sqlite?mode=ro',uri=True) if False else sqlite3.connect((generation/'store.sqlite').resolve().as_uri()+'?mode=ro',uri=True);n=sqlite3.connect((generation/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
entries=[
('ACTOR','상법','1503','상법상 대표이사는 누가 선정하고 정관으로 달리 정할 수 있나요?'),
('ACTOR','주식회사 등의 외부감사에 관한 법률','154','외부감사법상 회계감사기준은 누가 어떤 승인을 받아 정하나요?'),
('ACTOR','개인정보 보호법','65','개인정보 보호위원회 위원장의 업무와 직무 대행자는 어떻게 정해지나요?'),
('ACTOR','벤처기업육성에 관한 특별법','531','벤처기업확인위원회 위원은 누가 위촉하고 어떤 자격을 갖춰야 하나요?'),
('TIMING','상법','1507','상법상 이사회 소집 통지는 언제 해야 하며 통지 기간과 절차의 예외는 무엇인가요?'),
('TIMING','상법','1810','상법상 이사는 재무제표 등의 서류를 감사에게 언제 제출해야 하나요?'),
('TIMING','상법','1825','상법상 재무제표와 감사보고서는 언제부터 얼마나 오래 본점과 지점에 비치하나요?'),
('TIMING','개인정보 보호법','70','개인정보 보호위원회 위원의 임기와 연임, 궐위 시 후임 임기는 어떻게 정하나요?'),
('CLASSIFICATION','개인정보 보호법','291','개인정보 보호법상 민감정보 처리 금지의 예외와 예외적으로 처리할 때 지켜야 할 사항은 무엇인가요?'),
('CLASSIFICATION','주식회사 등의 외부감사에 관한 법률','172','외부감사법상 비밀엄수 의무의 대상과 금지행위, 예외는 무엇인가요?'),
('CLASSIFICATION','상법','1018','상법상 주식이 여러 사람의 공유에 속할 때 납입 책임과 주주 권리 행사자는 어떻게 정하나요?'),
('CLASSIFICATION','개인정보 보호법','297','개인정보 보호법상 고유식별정보 처리 제한의 원칙과 허용 예외는 무엇인가요?'),
('STRUCTURE','상법','1801','상법상 이사가 결산기마다 작성하고 이사회 승인을 받아야 할 재무제표의 구성은 무엇인가요?'),
('STRUCTURE','상법','1519','상법상 이사회 의사록에는 무엇을 적고 누가 기명날인 또는 서명해야 하나요?'),
('STRUCTURE','개인정보 보호법','18','개인정보 보호법의 개인정보 보호 원칙에 포함된 사항을 정리해 주세요.')]
public=set(read(R/'02_BACKEND/lawrag/research/candidates/adr_0677/integrated/snapshot/00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']);cases=[];gold=[]
for i,(kind,law,u,q) in enumerate(entries,1):
 d=c.execute('SELECT document_id FROM document WHERE name=?',(law,)).fetchone()[0];assert d in public
 unit=json.loads(c.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',(d,u)).fetchone()[0]);assert unit['family']=='kr_article' and unit.get('coordinate_scope')=='body',(law,u,unit)
 sid,j=n.execute("SELECT id,json FROM source WHERE document_id=? AND json_extract(json,'$.unit_id')=?",(d,u)).fetchone();src=json.loads(j)
 text='\n'.join(c.execute('SELECT text FROM block_payload WHERE document_id=? AND block_id=?',(d,str(b['block_id']))).fetchone()[0] for b in src['blocks'])
 cases.append({'case_id':f'NG{i:02}','question':q,'kind':kind})
 gold.append({'case_id':f'NG{i:02}','kind':kind,'document_id':d,'document_name':law,'unit_id':u,'source_id':sid,'canonical_coordinate':unit['coordinate_key'],'source_text':text,'source_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_artifact_sha256':c.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(d,)).fetchone()[0],'rubric':'Grade the requested subject/rules/conditions against this pinned original. Semantic mistakes are improvement observations, not automatic MAIN blockers. Never alter the product.'})
old=read(P/'dataset.json');oldgold=read(P/'gold.json');remaining={f'IC{i:02}' for i in range(16,33)}
cases += [v for v in old['cases'] if v['case_id'] in remaining];gold += [v for v in oldgold['cases'] if v['case_id'] in remaining]
assert len(cases)==32 and len({v['source_id'] for v in gold})==32
observed={v['source_id'] for v in oldgold['cases'] if v['case_id'] not in remaining};assert not observed & {v['source_id'] for v in gold}
from collections import Counter
assert set(Counter(v['kind'] for v in cases).values())=={4}
put(D/'dataset.json',{'cases':cases,'regression_cases':old['regression_cases'],'source_generation':str(generation.relative_to(R)),'selection':'32 distinct target article groups not executed in this task: 15 new and 17 previously frozen but unexecuted; 8 types x 4; existing 8 cases are regressions only','product_gold':None,'max_calls_per_case':40,'max_output_tokens':6400})
put(D/'gold.json',{'cases':gold,'visibility':'Offline evaluator only after immutable product response','version_scope':'Pinned repository originals, not a latest-law certification'})
put(D/'rubric.json',{'semantic_correctness':'Same subject, all requested conditions/numbers/exceptions faithful to pinned source; binary observation, failures kept for generalization work.','promotion':'All contract/package/fingerprint/span/ACL/state checks pass; all 32 independent cases and 8 regressions attempted once; at least one supported answer per independent type and four regression responses. Bounded rejected model choices or confirmed provider interruption are recorded. Internal code/data/ACL/citation/state integrity failures block. Detailed semantic correctness and baseline-only semantic mistakes are not absolute blockers under user instruction 2026-10-07.','evaluator':'Qwen3.8 Parasail FP8 reasoning none, one grade, no fallback, cannot modify product.'})
m=read(A/'실험/manifest.json');ref=m['lineage']['parents'][0]['experiment_id']+'/'+m['lineage']['parents'][0]['arm_id'];arm=next(v for v in m['design']['arms'] if v['id']=='integrated');arm['derived_from']=[ref];m['design']['arms']=[arm];m['design']['retrieval_stage_plan']['stages_by_arm']={'integrated':m['design']['retrieval_stage_plan']['stages_by_arm']['integrated']}
m['design'].update(hypothesis='The same integrated investigation code preserves serving/evidence/state contracts on unseen queries; detailed semantic failures expose generalization gaps without becoming a blanket MAIN veto',primary_metric='Zero critical execution/evidence/authorization/state/binding regressions; separately record semantic correctness on 32 independent cases',success_criteria=read(D/'rubric.json')['promotion'],failure_criteria='Any candidate internal integrity, unsupported quotation, authorization breach, state corruption or serving fingerprint mismatch blocks MAIN; insufficient usable execution coverage blocks qualification',criteria_frozen_before_run=True)
m['design']['baseline_pipeline_reference']={'active_pointer':'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json','release_id':'local-genos-unit-v6-20261006-r1','generation':42,'model_reexecution':False,'reason':'Candidate-only independent characterization; no A/B accuracy or latency improvement claim, existing baseline failures retained in parents; reduce repeated runtime storage'}
m['runs'][0].update(arm_ids=['integrated'],selection_rule='All 32 preselected unseen target groups once; all outcomes retained, no replacement or hidden rerun; semantic scores recorded separately from critical invariants',status='planned',sha256=None)
m['dataset'].update(name='32 unseen public article groups / eight types, candidate-only characterization',version='20261007-integrity-generalization-v1',sha256=hashlib.sha256((D/'dataset.json').read_bytes()).hexdigest());m['phase']='holdout';m['in_sample']=False;m['decision_eligible']=False
put(A/'실험/manifest.json',m)
put(D/'acceptance-policy.json',{'user_instruction':'우리 용량이 많이 없어 최대한 용량을 차지 않하는 방향; 세부적으로 답이 다 맞아야 메인에 반영하는게 아니야; 일반화 부족과 판단미스 별도 기록','frozen_before_calls':True,'critical_blockers':['INTERNAL_CONTRACT_ERROR','SOURCE_TOOL_ERROR','unverified quote or adopted scope','authorization/scope leakage','code/profile/data/search/schema drift','state/chain/CAS corruption'],'bounded_model_outcomes':['MODEL_PROPOSAL_INVALID','MODEL_TRANSPORT_ERROR','BUDGET_EXHAUSTED','DEADLINE_EXCEEDED','SOURCE_INVESTIGATION_INCOMPLETE'],'required_cases':32,'regression_cases':8,'minimum_successful_types':8,'minimum_regression_responses':4,'semantic_correctness_absolute_gate':False,'no_historical_waiver_reused':True})
# Retire only unused generated scaffolding before any product call.
for p in (A/'실험').glob('질문-*.md'):p.unlink()
print('Unseen groups',len(gold),'types',dict(Counter(v['kind'] for v in cases)),'regressions',len(old['regression_cases']))
