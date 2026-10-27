from pathlib import Path
import sys,json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1054-ontology-mvp-state-binding';ART=ADR/'artifacts';prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1053-ontology-mvp-step-state'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
old=read(prior/'실험/manifest.json');m=read(ADR/'실험/manifest.json')
for k in ['design','dataset','llm_policy','retrieval_accounting','questions','runs']:m[k]=old[k]
# Paths to this run only; inherited fixed inputs remain byte-identical.
for k in ['dataset','retrieval_accounting','questions','runs']:
 m[k]=json.loads(json.dumps(m[k],ensure_ascii=False).replace(prior.name,ADR.name))
m['design']['criteria_frozen_before_run']=False;m['design']['code_isolation']['candidates']=[];m['lineage']['hypothesis_delta']='Same1053 state projection and1052 navigation; repair local model grant policy hash before any model call.1053 zero-call failure preserved as dependency, not quality parent.'
m['design']['operational_success_criteria']+=' Exact candidate LocalGemmaTransport must construct with synthetic credential before freeze; never bypass hash check.'
m['design']['working_integration']='Isolated candidate only;1053 implementation retained with corrected explicit policy scope/hash binding; MAIN unchanged.'
save(ADR/'실험/manifest.json',m)
save(ART/'implementation-plan.json',{'before_implementation':True,'change':'rebind local-public grant policy_sha256 to exact1054 policy; retain scope/checks; add real adapter startup regression','cause':'1053 changed provider_failover scope but did not refresh local grant hash','product_calls_in_failed1053':0,'authorization':'user requested implementation and experiment; deterministic wiring repair within same authorization','preserve':'1053 frozen code, failed cell and0call record;1049 all prior outputs','live':'new111cells after actual adapter and candidate/API checks; no automatic replay of failed cells'})
for n in ['cases-product.json','cases-evaluator-r1.json','corpus-selection-r1.json','execution-authorization-20261024-r1.json','evaluation-contract.json','dataset-freeze-r1.json','approved-bundles-20261024-r1.json','corpus-article-root-count-r1.json','provider-authorization.json','provider-endpoints.json']:shutil.copyfile(prior/'artifacts'/n,ART/n)
for p in (prior/'실험').glob('질문-*.md'):(ADR/'실험'/p.name).write_text(p.read_text().replace(prior.name,ADR.name).replace('ADR-1053 /','ADR-1054 /'))
front=(ADR/'README.md').read_text().split('---',2)[1];body=(prior/'README.md').read_text().split('---',2)[2].replace('ADR-1053','ADR-1054').replace('adr_1053','adr_1054');body=body.replace('## 1. 결정 요약\n','## 1. 결정 요약\nADR1053은 호출 전 정책/권한 결속 해시 불일치로0호출 중단됐다. 동일 구현의 설정 해시를 올바르게 갱신하고 실제 어댑터 초기화 회귀검사를 추가한다. 기존 실패와 동결 코드는 보존하며 검증을 우회하지 않는다.\n\n');(ADR/'README.md').write_text('---'+front+'---\n'+body)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
parent=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1053/step-state-r1';rows=read(parent/'candidate.json')['files'];frozen=parent/'revisions/rev-001/snapshot';target=c.snapshot(ADR,'step-state-r1',[r['target_path'] for r in rows if r['upstream_state']=='present'],experiment_id=m['experiment_id'],arm_id='A2',run_ids=['run-001'])
for r in rows:
 n=r['target_path'];p=target/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(frozen/n,p)
 if r['upstream_state']=='absent':c.register_file(target,n,upstream_state='absent')
base=target/'snapshot'
for n in ['00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','02_BACKEND/lawrag/research/provider_failover.py','05_TESTS/CONTRACTS/test_provider_failover_adr1049.py']:
 p=base/n;p.write_text(p.read_text().replace('ADR-1053-experiment-v1','ADR-1054-experiment-v1'))
p=base/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json';v=read(p);v['policy_sha256']=hashlib.sha256((base/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_bytes()).hexdigest();save(p,v)
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1053').glob('*.py'):
 if p.name=='prepare.py':continue
 s=p.read_text().replace('ADR-1053-ontology-mvp-step-state','ADR-1054-ontology-mvp-state-binding').replace('ADR-1053-experiment-v1','ADR-1054-experiment-v1').replace('adr_1053','adr_1054').replace('adr1053-','adr1054-').replace('ADR-1053 /','ADR-1054 /')
 if p.name=='freeze_candidate.py':s=s.replace("t['passed']==139","t['passed']==140")
 if p.name=='freeze_run.py':
  s=s.replace('(tested,139),(frozen_test,21)','(tested,140),(frozen_test,22)').replace("allowed={'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'", "allowed={'05_TESTS/CONTRACTS/test_model_binding_adr1054.py','00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'").replace('139 contract/API checks,21 repeated','140 contract/API checks,22 repeated').replace('139 targeted contracts/API,21 exact','140 targeted contracts/API,22 exact').replace('691files','692files')
 (ROOT/'06_TOOLS/EXPERIMENTS/adr_1054'/p.name).write_text(s)
c.refresh(target);print(target)
