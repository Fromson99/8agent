from pathlib import Path
import hashlib,json,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0928-connected-source-other-cm-regression';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==89
paths={'baseline':'08_DEPLOYMENT/RELEASES/answer-first-followup-20261019-r1/release.json','current':pointer['manifest_path']}
releases={a:read(R/p) for a,p in paths.items()};assert releases['baseline']['data_path']==releases['current']['data_path'];assert releases['baseline']['files']['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json']==releases['current']['files']['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json']
put(D/'baseline.json',{'pointer':pointer,'manifest':releases['current']})
for arm,v in releases.items():put(D/(arm+'-binding.json'),{'code_root':v['code_root'],'serving_files':v['files'],'release_id':v['release_id'],'generation':88 if arm=='baseline' else 89,'manifest_path':paths[arm],'manifest_sha256':sha(R/paths[arm])})
cases=[
 {'id':'provision-comparison','topic_reference':'RISK-CM-027','kind':'definition-distinction','question':'대사: 금융투자회사의 대손충당금과 대손준비금은 외부 규정에서 어떻게 구분되고, 내부 규정에는 어떻게 반영되어 있나?'},
 {'id':'pf-downgrade','topic_reference':'RISK-CM-029','kind':'conditional-application','question':'대사: 부동산 PF 사업성 평가가 악화될 때 금융투자회사의 자산건전성 분류와 대손충당금 적립에 관한 외부 기준은 무엇이고, 내부 규정에는 어떻게 반영되어 있나?'},
 {'id':'rp-bond-scope','topic_reference':'RISK-CM-078','kind':'eligible-assets','question':'대사: 금융투자회사가 일반 고객과 원화 RP 거래를 할 때 대상 채권의 종류와 신용등급에 관한 외부 기준은 무엇이고, 내부 규정에는 어떻게 반영되어 있나?'}]
for c in cases:c.update(api_type='WORKFLOW_RUN',workflow_id='risk_team_compare_workflow',origin='Synthetic public-regulation topic mapped to risk_cm; original internal question, annotations and gold not sent.')
put(D/'cases.json',cases)
schedule=[{'arm':a,'case_id':c['id']} for i,c in enumerate(cases) for a in (('baseline','current') if i%2==0 else ('current','baseline'))];put(D/'schedule.json',schedule)
criteria={'hypothesis':'The MAIN89 connected-source release preserves the MAIN88 ability to return inspected originals and useful comparison observations on other public risk_cm topics, without source/consumer regressions.',
 'primary_metric':'Case-paired execution, exact source integrity and question-relevant evidence/answer coverage; no approved gold accuracy score.',
 'success':['All6planned calls finish as recorded outcomes without source/ACL/hash/side violations','Current does not introduce a failed/no-answer result where baseline returns a substantive sourced answer','Manual original-grounded comparison reports any lost requested issue, unsupported claim or newly incorrect scope; more citations alone do not count as improvement','Saved and duplicate answers agree and duplicate requests make no model calls'],
 'regression':['Any source/ACL/hash/side violation is critical','Any baseline-only substantive supported answer or needed source/issue loss is a quality regression','Flag latency increase when current >1.5x baseline AND >60seconds slower; flag >4extra calls or >2xinput tokens'],
 'selection':'Three different public topics mapped to027029078 chosen before results; leverage excluded; one attempt per arm/case with alternating order. Existing known topics are not holdout.',
 'scope':'Whole exact releases MAIN88vs89, not causal isolation of one feature; all94release-file deltas recorded. Same original generation/profile/model/public transport boundary.',
 'semantic_review':'Read-only human/assistant source-grounded comparison, not an evaluator-model score or legal certification. Preserve unknown and partial separately; internal missing evidence is not proof of absence.',
 'limits':{'cases':3,'arms':2,'repeats':1,'max_physical_model_calls_per_request':40,'wall_seconds_per_request':1800,'max_total_physical_calls':240,'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'min_disk_gib':10},
 'no_adaptive_reruns':True,'main_changes':False,'genos_executed':False,'original_risk_cm_transmitted':False,'gold_visible_to_product':False}
put(D/'criteria.json',criteria)
put(D/'release-deltas.json',[{'path':n,'baseline':releases['baseline']['files'].get(n),'current':releases['current']['files'].get(n)} for n in sorted(set(releases['baseline']['files'])|set(releases['current']['files'])) if releases['baseline']['files'].get(n)!=releases['current']['files'].get(n)])
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['regression'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'None; exact completed historical MAIN88 release','controls':'Same data, profile, public scope and model; full release binding'}, {'id':'current','role':'candidate','derived_from':['ADR-0927-experiment-v1/qualified'],'changes':'None; exact active MAIN89 release compared with baseline','controls':'Same data, profile, public scope and model; fresh request state'}]
m['design']['code_isolation'].update(mode='not_applicable',reason='No new product code candidate; compare two immutable completed release artifacts by explicit isolated service app injection.',candidates=[])
stages=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},{'stage_id':'returned','kind':'select','parent_stage_ids':['acquired']},{'stage_id':'cited','kind':'present','parent_stage_ids':['returned']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in releases}
m['runs'][0].update(arm_ids=['baseline','current'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='risk-cm-public-topic-paired-regression',version='20261019-r1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0,'max_calls':240}]
m['retrieval_accounting'].update(changed=True,not_applicable_reason='No approved legal gold; exact acquired/returned/cited identities measured after selection. Preview leads are not original reads.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
files={}
for arm,v in releases.items():
 files[paths[arm]]=sha(R/paths[arm])
 for n,h in v['files'].items():
  p=R/v['code_root']/n;assert sha(p)==h;files[str(p.relative_to(R))]=h
for p in [*D.glob('*.json'),*T.glob('*.py'),R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/'06_TOOLS/EXPERIMENTS/resource_guard.py']:
 files[str(p.relative_to(R))]=sha(p)
for n in ('manifest.json','navigation/manifest.json','fulltext/manifest.json'):
 p=R/releases['current']['data_path']/n;files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'known_topics':True,'legal_holdout':False})
print(json.dumps({'cases':len(cases),'planned_requests':len(schedule),'max_calls':240,'MAIN_unchanged':True},ensure_ascii=False))
