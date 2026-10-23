"""Finalize measured native run and preserve failed paired-runner results."""
from common import *
import sys,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');o=read(ART/'observations.json');r=o['native_result'];P=ART/'known-query/candidate'
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert all(sha(ROOT/n)==h for n,h in s['working_before'].items())
assert o['main_unchanged']
paired=[read(p) for p in sorted((ART/'paired').glob('*/*/result.json'))]
usage=[u for p in paired for u in p['usage']]+r['usage'];calls=sum(p['model_calls'] for p in paired)+r['model_calls']
read_evidence=read(ART/'source-audit.json')['read_evidence']
# Acquired source headings and corpus binding are measured, not predicted.
heads=[x['heading'] or '' for x in read_evidence]
required={key:any(h.startswith(title) for h in heads) for key,title in [('income_tax97','제97조'),('decree163','제163조')]}
# Inspect canonical document names to avoid treating same-number articles as the target law.
import sqlite3
G=ROOT/s['base_release']['data_path'];db=sqlite3.connect((G/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
for key,title,law in [('income_tax97','제97조','소득세법'),('decree163','제163조','소득세법 시행령')]:
 found=[]
 for x in read_evidence:
  v=db.execute('select json from source where id=?',(x['source_id'],)).fetchone()
  if not v:continue
  v=json.loads(v[0]);name=v.get('document_name','').split(' > ')[-1]
  if name==law and (v.get('heading') or '').split()[0].split('(')[0]==title:found.append(x['source_id'])
 required[key]=sorted(set(found))
db.close()
paired_errors=[{'case':x['case_id'],'arm':x['arm'],'error':x['error']} for x in paired if x['error']]
native_pass=o['outcome'].get('stop_reason')!='MODEL_DECISION_UNRESOLVED' and r.get('service_status')==200 and r['model_calls']<=14 and all(required.values()) and not o['source_checks']['mismatches'] and not o['source_checks']['scope_violations']
summary={'status':'COMPLETE','verdict':'CRITERIA_NOT_MET','criteria_met':False,'native_operational_criteria_met':bool(native_pass),'paired_formal_grade':None,'paired_error_count':len(paired_errors),'paired_runner_error':'Four offline replays passed; two chain replays failed because the runner reused a path variable for a prior-opinion object. Preserved; independent ADR1004 checked all six original replies without new model calls.','native_calls':r['model_calls'],'total_physical_calls':calls,'native_seconds':r['seconds'],'service_status':r.get('service_status'),'required_sources':required,'source_checks':o['source_checks'],'outcome':o['outcome'],'usage':{'input_tokens':sum(u['input_tokens'] or 0 for u in usage),'output_tokens':sum(u['output_tokens'] or 0 for u in usage),'cost_usd':sum(u['cost_usd'] or 0 for u in usage)},'contract_checks':{'initial':'27passed/1failed; expected exception type changed from semantic to schema rejection','final_repair_checks':'2passed after assertion update; product unchanged;28 distinct candidate checks passed','inherited':'38 connection checks passed in parent, corresponding source code unchanged'},'quality_certified':False,'decision_eligible':False,'working_code_changed':False,'main_changed':False,'genos_changed':False}
save(ART/'result.json',summary);save(ART/'paired-runner-errors.json',paired_errors)
findings=[f"기준 ADR1001은34호출·1258.073초였다. 첫 후보 ADR1002는9호출·191.827초에 판단 충돌로 제한 종료했다. 상관 계약 후보는{r['model_calls']}호출·{r['seconds']:.3f}초·HTTP{r.get('service_status')}다. 호출 수만으로 성공 판정하지 않는다.",f"필수 원문 도달: {json.dumps(required,ensure_ascii=False)}. 원문 검사: {json.dumps(o['source_checks'],ensure_ascii=False)}. 종료: {json.dumps(o['outcome'],ensure_ascii=False)}.","최상위 FINISH 행동은 같지만 중첩 status가 다른 두 분기를 출력 축약기가 구분하지 못해 MINIMAL_OUTPUT_BRANCH 오류가 발생했다. 기존1회 보정 이후에도 반복되어 모의 raw-schema 검증과 실제 gateway 변환의 차이를 확인했다. frozen 후보는 변경하지 않는다.","이 ADR의 offline 재검증은4통과/2실행기 변수 오류다. 독립 ADR1004에서 원래6응답을 원래 입력·schema·canonical projection으로6/6 확인했고 모델 추가 호출0회다. 기존 실패 결과는 보존한다.","상관 계약의 모의검사28개와 부모의 기존 연결38검사를 기록했다. 실제 모델의 충분성·계속 판단 개선과 필수 연결 도달은 성공 인증하지 않는다.","선택 MAIN102·GENOS 미변경. 외부 Qwen 결과는 GENOS 내부 모델 결과가 아니다."]
limits=['Known in-sample single request; no legal-answer gold, no out-of-sample quality proof.','Candidate inspection/control mode is off by default; no MAIN pointer change or GENOS field deployment.','Two chain-replay harness failures and native projection failure preserved; original ADR remains not passed.']
(ADR/'RESULT.txt').write_text('\n\n'.join(findings+limits)+'\n')
runtime=P/'runtime';archive=P/'runtime.tar.gz'
if runtime.exists():
 assert not archive.exists();hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
 with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
 with tarfile.open(archive,'r:gz') as t:
  for name,h in hashes.items():
   with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==h
 save(P/'runtime-archive.json',{'archive':'runtime.tar.gz','sha256':sha(archive),'verified_files':hashes,'restore':'Extract into an empty directory; runtime relative paths preserved.','process_finished':True})
 shutil.rmtree(runtime)
m=read(ADR/'실험/manifest.json');assert m['design']==f['design']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={arm:{'status':'complete','correct':None,'total':3+(arm=='candidate'),'accuracy':None,'accuracy_not_scored_reason':'Paired harness response-envelope extraction failed; raw replies retained; native coverage separately measured, no approved legal gold.','new_calls':sum(x['model_calls'] for x in paired if x['arm']==arm)+(r['model_calls'] if arm=='candidate' else 0),'quality_certified':False} for arm in ('baseline','candidate')},comparisons=[],judge_disagreements=0,usage={'physical_calls':calls,**summary['usage']},latency={'service_seconds':r['seconds'],'model_seconds':o['model_seconds'],'request_p50_seconds':r['seconds'],'request_p95_seconds':r['seconds'],'sample_size':1},error_taxonomy=['MINIMAL_OUTPUT_NESTED_BRANCH_AMBIGUITY','OFFLINE_RUNNER_VARIABLE_SHADOW']+([] if native_pass else ['NATIVE_REQUIRED_CRITERIA_NOT_MET']))
nr=len(o['read_coordinates']);nf=len(o['final_coordinates'])
m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter=nr,after_filter=nf,presented_total=nf,presented_mean=nf,presented_p50=nf,presented_p95=nf,golden_recall={'candidate':None},selectivity=nf/o['corpus_total'])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
parts=['CRITERIA_NOT_MET: nested stop-branch projection conflict; native and offline replay failures preserved.','\n\n'.join(findings[:2]),m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],'431 frozen files; explicit answer_progress_control=true in experiment only. [동결](artifacts/design-freeze.json).','\n\n'.join(findings),'[모의 검사](artifacts/contracts-final.txt), [실제 기록](artifacts/known-query/candidate/result.json), [원문](artifacts/source-audit.json).',json.dumps(summary,ensure_ascii=False,indent=2),'No MAIN activation; preserve original failures and perform independent offline replay if needed.','\n\n'.join(limits),'Candidate-only; working/selected/GENOS state unchanged.','reserve → design → isolated implementation → deterministic checks/repairs → freeze → paired6 → native<=14 → source audit → archive → final validation.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 답변 진전 기반 종료 실험\n\n'+''.join(h+'\n\n'+x+'\n\n' for h,x in zip(ADR_HEADINGS,parts)))
for row in m['questions']:
 case=row['case_id'];public=case=='public-expenses';native='[native result](../artifacts/known-query/candidate/result.json)' if public else '[paired responses](../artifacts/paired/)'
 vals=[f"run-001/{case}; synthetic paired stage" if not public else 'run-001/candidate native public request',read(ART/'known-request.json')['json']['question'] if public else next(x['question'] for x in read(ART/'stage-inputs.json') if x['id']==('chain' if case=='required-chain' else case)), 'No approved legal gold; frozen stage action labels in stage-gold.json, never product context.','[input](../artifacts/stage-inputs.json) and [known request](../artifacts/known-request.json).','[source ledger](../artifacts/retrieval-ledger.json); synthetic stage has no retrieval execution.',native,'Usage/call counts retained in raw result and experiment manifest.','No model judge; paired harness error prevents original formal grade.','\n\n'.join(findings if public else [findings[2]])]
 qp=ADR/'실험'/row['file'];qp.write_text('# '+case+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));row['sha256']=sha(qp)
save(ADR/'실험/manifest.json',m)
index=ROOT/'04_EXPERIMENTS/ADR/README.md';text=index.read_text();line='- [ADR-1003 답변 진전 기반 종료](ADR-1003-correlated-answer-progress/README.md) — 원본 paired 실행기 오류 보존, 실제 질의 호출·원문 도달 별도 측정, MAIN 미변경.\n';assert 'ADR-1003 답변' not in text;index.write_text(text.replace('# ADR workspace\n','# ADR workspace\n'+line))
print(json.dumps(summary,ensure_ascii=False,indent=2))
