"""Freeze the requested three public cases and unchanged release comparison."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, sqlite3, subprocess

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0762-main53-three-public-cases'
D = A / 'artifacts/design'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

assert not (D / 'criteria.json').exists()
active = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert active['generation'] == 53
releases = {}
for arm, rid in [('baseline', 'compact-navigation-20261012-r1'), ('main53', active['release_id'])]:
    path = R / '08_DEPLOYMENT/RELEASES' / rid / 'release.json'
    manifest = read(path)
    for name, digest in manifest['files'].items():
        assert sha(R / manifest['code_root'] / name) == digest, name
    releases[arm] = {'manifest': manifest, 'path': str(path.relative_to(R)), 'sha256': sha(path)}
assert releases['baseline']['manifest']['data_path'] == releases['main53']['manifest']['data_path']
put(D / 'releases.json', releases)
put(D / 'baseline.json', {'manifest': releases['baseline']['manifest'], 'pointer': active,
    'pointer_sha256': sha(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'note': 'manifest is the read-only MAIN52 comparison; pointer is the current MAIN53 preserved throughout this experiment'})

criteria = {
    'scope': 'Three purposively authored public questions, unchanged MAIN52 versus unchanged MAIN53; descriptive comparison, planning separate, no implementation or promotion.',
    'authorization': 'User asked item4 to be measured on about three questions, and remaining items planned using Opus5.5. Only public authored questions; no internal CM/risk_cm originals.',
    'execution': {'cases': 3, 'requests': 6, 'order': [['P01','baseline'],['P01','main53'],['P02','main53'],['P02','baseline'],['P03','baseline'],['P03','main53']], 'no_adaptive_reruns': True, 'model_calls_per_request_max': 40},
    'hypothesis': 'MAIN53 can preserve requested conditions, exceptions and duties on three different public sources while reducing repeated context. Measure direction without claiming population improvement.',
    'measurement_complete': 'All six prospectively scheduled requests have outcomes and exact available usage; failures retained. Frozen bindings, source scope, original quotes and durable accepted state audited.',
    'quality_target': '3/3 supported MAIN53 responses, no baseline-only supported regression; semantic correctness, omissions, condition logic and paraphrase repetition reported separately for each arm.',
    'performance': 'Report per-case and all-request totals. Efficiency delta uses only pairs with supported responses on both arms. No improvement threshold or automatic promotion. p50 and observed maximum only; n=3 p95 not a stable tail estimate.',
    'semantic_review': 'Codex offline review against frozen source gold and saved answers only; no judge model, no changes to product inputs/answers. Evidence delivery, execution success and semantic correctness are separate.',
    'controls': 'Same immutable source generation and65-document approved scope, Qwen3.8 Parasail FP8 none fallback=false, temperature0, output6400, model40, native profile budgets, fresh process per request. Alternating arm order; no repetitions, provider/cache variation remains.',
    'sample_limit': 'Purposive public sources inspected before authoring; exposure not fully audited, in_sample=true, decision_eligible=false. Not a CM51 sample, not a fresh holdout, not GENOS.',
    'main_wiring': 'unchanged', 'cache_changes': False,
}
put(D / 'criteria.json', criteria)
selections = [
    ('P01','article:002c7206aff335f4f8f0a3b4','permission_duty_exception',
     '저장된 독점규제 및 공정거래에 관한 법률 제120조의3을 기준으로, 자율준수평가기관을 지정할 수 있는 요건과 지정 취소 또는 업무정지가 가능한 사유를 설명해 주세요. 반드시 지정을 취소해야 하는 경우와 재량으로 조치할 수 있는 경우를 구분하고, 대통령령이나 제120조의2의 세부 내용은 추가로 조사하지 말아 주세요.'),
    ('P02','article:00aa2b7ab69069ec5168a9eb','title_lookup_deadline_exception',
     '저장된 코스닥시장 공시규정에서 집합투자업자 등의 의결권 행사 내용 공시 조항을 찾아, 일반적인 신고 대상 기간·기한과 신고할 내용, 신탁업자에게 적용되는 예외를 설명해 주세요. 외부 법령의 세부 정의나 다른 공시 조항은 추가로 조사하지 말아 주세요.'),
    ('P03','article:00b2cb6fc653d3308e322ea8','actor_duty_conditional_accounts',
     '저장된 외국환거래규정 제7-24조를 기준으로, 비거주자의 증권 발행 신고 때 제출할 자료, 주식예탁증서 발행을 위한 계좌 개설 요청자와 실제 개설자의 의무, 원화증권과 외화증권의 납입대금 예치 계정을 구분해 설명해 주세요. 별지 서식 내용과 다른 조문의 세부 요건은 추가로 조사하지 말아 주세요.'),
]
selected = releases['main53']['manifest']
allowed = set(read(R / selected['code_root'] / '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
db = sqlite3.connect((R / selected['data_path'] / 'navigation/navigation.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
cases, gold = [], []
for cid, sid, kind, question in selections:
    source = json.loads(db.execute('select json from source where id=?', (sid,)).fetchone()[0])
    assert source['document_id'] in allowed
    cases.append({'case_id':cid,'kind':kind,'question':question,'arm_ids':['baseline','main53'],'role':'purposive_public_probe'})
    gold.append({'case_id':cid,'source_id':sid, **{k:source[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}})
db.close()
put(D / 'dataset.json', {'cases':cases,'product_gold':False,'source_generation':selected['data_path']})
put(D / 'gold.json', {'product_visible':False,'version':'Pinned selected source generation; not current-law advice','cases':gold})
put(D / 'selection-audit.json', {'selection_before_results':True,'purposive':True,'exposure_unverified':True,'primary_roots':[x[1] for x in selections], 'rule':'First inspected eligible roots from distinct approved documents chosen for permission/exception, title/deadline and actor/account distinctions; no unseen claim.'})

m = read(A / '실험/manifest.json')
m.update(in_sample=True, decision_eligible=False)
m['lineage']['hypothesis_delta'] = criteria['scope']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Supported response and separately reviewed semantics; paired cost/latency', success_criteria=criteria['measurement_complete'], failure_criteria='Missing planned outcome, binding/scope/citation/state inconsistency, or unrecorded usage; semantic failures reported, no promotion.', criteria_frozen_before_run=True, repeats=1)
for arm in m['design']['arms']:
    arm.update(changes='Unchanged frozen '+('MAIN52' if arm['id']=='baseline' else 'MAIN53'), controls=criteria['controls'])
    arm['derived_from'] = [] if arm['id']=='baseline' else ['ADR-0761-experiment-v1/integrated']
    arm['source_binding'] = {k:releases[arm['id']][k] for k in ('path','sha256')}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['dataset'].update(name='Three purposive authored public regulation questions',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls'] = [{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Exact six requests in criteria.execution.order, no adaptive repeats/replacement',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a['id']:stages for a in m['design']['arms']}
m['retrieval_accounting'].update(changed=False,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
headings=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
m['questions']=[]
for n,c in enumerate(cases,1):
    name=f'질문-{n:03}-{c["case_id"]}.md';p=A/'실험'/name
    texts=['ADR0762/run-001; MAIN52 and MAIN53 public purposive probe.',c['question'],'Frozen artifacts/design/gold.json. Product runner never loads gold.', '### 회수·탈락 단계 원장 — run·arm별\n\nNative API; same authorized65 documents; exact provider views and canonical ledger.', 'Physical provider requests/responses/usage retained in original artifacts; no reconstructed payload claim.', 'Same ExperimentClient audits all product phases. No separate judge model.', 'Codex offline saved-source review. No adaptive reruns. Semantic quality distinct from source support.', 'Not run at freeze; fill from six original outcomes.']
    p.write_text('# '+c['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headings,texts),1))+'\n')
    m['questions'].append({'number':n,'case_id':c['case_id'],'file':name,'sha256':sha(p)})
put(A/'실험/manifest.json',m)

cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','main53','--experiment-id',m['experiment_id'],'--arm-id','main53','--run-id','run-001']
names=sorted(set(selected['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'})
for name in names:cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0762/main53'
for name in selected['files']:
    shutil.copy2(R/selected['code_root']/name,C/'snapshot'/name)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],cwd=R,check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
for name,h in selected['files'].items():assert sha(code/name)==h
binding={'candidate_id':'main53','arm_id':'main53','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0762/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0762/run_case.py')}
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=[binding];put(A/'실험/manifest.json',m)
put(D/'bindings.json', {'codes':{'baseline':releases['baseline']['manifest']['code_root'],'main53':str(code.relative_to(R))},'stage':str(code.relative_to(R)),'source_generation':selected['data_path'],'experiment_client':str((code/'02_BACKEND/lawrag/research/experiment_client.py').relative_to(R))})
paths=list(D.glob('*.json'))+[C/'candidate.json',R/'06_TOOLS/EXPERIMENTS/adr_0762/run_case.py',R/'06_TOOLS/EXPERIMENTS/adr_0762/run_all.py',R/'06_TOOLS/EXPERIMENTS/adr_0762/audit.py',R/'06_TOOLS/EXPERIMENTS/adr_0762/repeat_ledger.py',R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
frozen={str(p.relative_to(R)):sha(p) for p in paths}
for row in cm['files']:frozen[str((code/row['target_path']).relative_to(R))]=sha(code/row['target_path'])
for name,h in releases['baseline']['manifest']['files'].items():frozen[str(Path(releases['baseline']['manifest']['code_root'])/name)]=h
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':frozen,'serving_files':selected['files'],'candidate':binding})
print('Frozen three public cases/six requests; unchanged295-file MAIN53; MAIN52 shared; no product edits')
