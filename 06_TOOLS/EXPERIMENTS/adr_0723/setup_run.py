from pathlib import Path
import json,hashlib,sqlite3
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0723-source-target-recovery-complete';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for name in ['run_case.py','run_all.py','repeat_ledger.py','audit.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0721'/name).read_text().replace('adr_0721','adr_0723').replace('ADR-0721-request-repair-final-qualification','ADR-0723-source-target-recovery-complete').replace('adr0721','adr0723').replace("'repaired'","'integrated'")
 if name=='audit.py':
  s=s.replace("x['case_id'].startswith('H')","not x['case_id'].startswith('S')")
  s=s.replace("==9,","==6,")
  s=s.replace("'candidate_repeat_supported':sum(x['supported_response'] for x in repeated)==3,","'candidate_repeat_supported':len(repeated)==0,")
  s=s.replace("parent=read(R/'04_EXPERIMENTS/ADR/ADR-0720-immutable-decision-retry-resume/artifacts/run-001/result.json')","parent=read(A/'artifacts/contract-result.json')")
  s=s.replace("'all23_new_contracts_pass':parent['new_contracts']['tests']==23", "'all_new_contracts_pass':parent['new_contracts']['tests']==34")
  s=s.replace("'unseen_primary_roots':not(set(read(D/'selection-audit.json')['primary_roots'])&set(read(D/'excluded-source-ids.json'))),", "'known_probe_not_used_for_promotion':m['in_sample'] is True and not m['decision_eligible'],")
  s=s.replace("'all_candidate_primary_gold_presented':all(x['gold_presented'] for x in candidate),","'gold_coverage_reported_separately':all(isinstance(x['gold_presented'],bool) for x in candidate),")
  # CM final-assessment-excluded must retain a nonterminal NEEDS_INVESTIGATION call.
  old="row.update(content_integrity_errors=integrity"
  s=s.replace(old,"if assessment.get('disposition') not in ('ANSWER','LIMITED_ANSWER'):last_assess=len(attempts)\n  "+old)
 (T/name).write_text(s)
old=read(R/'04_EXPERIMENTS/ADR/ADR-0717-main50-cm51-sequential-profile/artifacts/design/gold.json')
# Exact historical coordinates remain offline only, not certified current legal answers.
cases=read(D/'dataset.json')['cases'];g=[]
for c in cases:
 item=next(x for x in old['cases'] if x['case_id']==c['case_id']);main=next((x for x in item['references'] if x['evidence_role']=='MAIN'),item['references'][0]);g.append({'case_id':c['case_id'],**main,'historical_references':item['references'],'reference_answer':item['reference_answer'],'current_legal_correctness_certified':False})
put(D/'gold.json',{'product_visible':False,'cases':g})
m=read(A/'실험/manifest.json');m['questions']=[]
headings=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for n,c in enumerate(cases,1):
 name=f'질문-{n:03}-{c["case_id"]}.md';p=A/'실험'/name
 texts=['ADR0723/run-001; known regression, not holdout',c['question'],'Offline artifacts/design/gold.json; historical reference, never read by product runner.','### 회수·탈락 단계 원장 — run·arm별\n\nMeasured catalogue/recall/acquired/presented in retrieval-ledger.json.gz; exact native logs retained.','Exact provider inputs/outputs/usage in each arm/case/provider, later lossless archive with hashes.','All phases use same ExperimentClient, physical40-call limit, same model/provider; no hidden retry.','Independent saved-original inspection, no evaluator model. Semantic errors separate from source/ACL/state contracts.','Results pending execution; frozen criteria unchanged.']
 p.write_text('# '+c['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headings,texts),1))+'\n');m['questions'].append({'number':n,'case_id':c['case_id'],'file':name,'sha256':sha(p)})
put(A/'실험/manifest.json',m)
s=(R/'06_TOOLS/EXPERIMENTS/adr_0721/freeze.py').read_text().replace('adr_0721','adr_0723').replace('ADR-0721-request-repair-final-qualification','ADR-0723-source-target-recovery-complete').replace('ADR-0721-experiment-v1','ADR-0723-experiment-v1').replace("'repaired'","'integrated'").replace('adr_0723/repaired','adr_0723/integrated')
s=s.replace("base=read(D/'baseline.json');subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)","base=read(D/'baseline.json')")
s=s.replace("for p,h in read(D/'parent-inheritance.json')['files'].items():assert sha(code/p)==h,p","assert read(A/'artifacts/contract-result.json')['all_new_contracts_pass']")
s=s.replace("'reviewed request-local", "'reviewed request-local")
(T/'freeze_run.py').write_text(s)
put(D/'preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False});put(D/'preview-validation.json',{'structural_checks_passed':True})
print('Six paired CM requests prepared; exact authorization and offline reference separation preserved')
