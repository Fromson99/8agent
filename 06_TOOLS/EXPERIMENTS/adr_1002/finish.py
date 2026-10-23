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
  if name==law and (v.get('heading') or '').split('(')[0].strip()==title:found.append(x['source_id'])
 required[key]=sorted(set(found))
db.close()
paired_errors=[{'case':x['case_id'],'arm':x['arm'],'error':x['error']} for x in paired if x['error']]
native_pass=r.get('service_status')==200 and r['model_calls']<=14 and all(required.values()) and not o['source_checks']['mismatches'] and not o['source_checks']['scope_violations']
summary={'status':'COMPLETE','verdict':'CRITERIA_NOT_MET','criteria_met':False,'native_operational_criteria_met':bool(native_pass),'paired_formal_grade':None,'paired_error_count':len(paired_errors),'paired_runner_error':'Runner indexed the transport envelope as a raw provider body; raw six responses preserved. No adaptive rerun or retroactive pass. Separate offline replay required.','native_calls':r['model_calls'],'total_physical_calls':calls,'native_seconds':r['seconds'],'service_status':r.get('service_status'),'required_sources':required,'source_checks':o['source_checks'],'outcome':o['outcome'],'usage':{'input_tokens':sum(u['input_tokens'] or 0 for u in usage),'output_tokens':sum(u['output_tokens'] or 0 for u in usage),'cost_usd':sum(u['cost_usd'] or 0 for u in usage)},'contract_checks':{'initial':'21passed/1failed; handoff omitted just-delivered original','delivery_repaired':'60passed','final_replay_repair_checks':'24passed, includes6 actual API checks; total62distinct'},'quality_certified':False,'decision_eligible':False,'working_code_changed':False,'main_changed':False,'genos_changed':False}
save(ART/'result.json',summary);save(ART/'paired-runner-errors.json',paired_errors)
findings=[f"기준 ADR1001은34호출·1258.073초·97확보/163미확보였다. 후보 실제 공개 질문은{r['model_calls']}호출·{r['seconds']:.3f}초·HTTP{r.get('service_status')}다. 서로 다른 시점의1회 실행이므로 인과적 속도 개선 인증이 아니다.",f"필수 원문 도달: {json.dumps(required,ensure_ascii=False)}. 원문 검사: {json.dumps(o['source_checks'],ensure_ascii=False)}.",f"짝지은6개 모델 응답은 저장됐으나 실행기 응답 envelope 해석 오류6건으로 정식 판정은 미완료다. 기존 성공 기준은 변경하지 않고 전체 기준 미충족으로 기록한다. 추가 모델 호출 없이 별도 ADR에서 원본을 재검증할 수 있다.","모델 호출을 늘리는 감시 단계 없이 기존 다음행동 판단에 현재답·필수원문·기대변화·직전효과를 추가했다. NO_CHANGE/TOOL_FAILED 연속2회에는 확인 원문을 기존 판단 단계에 넘긴다. 참조 경로 구체화는 계속할 수 있다. 의견은 법률 정답으로 승인하지 않는다.","초기 모의검사에서 막 읽은 원문의 handoff 누락1건을 발견해 전체 원문 검증·receipt 보존으로 수정했다. 기존 연결38검사와 신규24검사 총62개 통과. 재시작 시 schema가 달라져 모델을 재호출할 위험도 동일 receipt의 schema 보존으로 수정하고 실제 SQLite 결정 journal 재개·보정 성공/실패를 확인했다.","선택 MAIN102·GENOS 미변경. candidate opt-in만 실행; 외부 Qwen 결과는 GENOS 내부 모델 결과가 아니다."]
limits=['Known in-sample single request; no legal-answer gold, no out-of-sample quality proof.','Candidate inspection/control mode is off by default; no MAIN pointer change or GENOS field deployment.','Six stage-runner failures preserved with raw responses; cannot report original ADR as passing.']
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
m['results'].update(status='complete',by_arm={arm:{'status':'complete','correct':None,'total':3+(arm=='candidate'),'accuracy':None,'accuracy_not_scored_reason':'Paired harness response-envelope extraction failed; raw replies retained; native coverage separately measured, no approved legal gold.','new_calls':sum(x['model_calls'] for x in paired if x['arm']==arm)+(r['model_calls'] if arm=='candidate' else 0),'quality_certified':False} for arm in ('baseline','candidate')},comparisons=[],judge_disagreements=0,usage={'physical_calls':calls,**summary['usage']},latency={'service_seconds':r['seconds'],'model_seconds':o['model_seconds'],'request_p50_seconds':r['seconds'],'request_p95_seconds':r['seconds'],'sample_size':1},error_taxonomy=['EXPERIMENT_RUNNER_RESPONSE_ENVELOPE']+([] if native_pass else ['NATIVE_REQUIRED_CRITERIA_NOT_MET']))
nr=len(o['read_coordinates']);nf=len(o['final_coordinates'])
m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter=nr,after_filter=nf,presented_total=nf,presented_mean=nf,presented_p50=nf,presented_p95=nf,golden_recall={'candidate':None},selectivity=nf/o['corpus_total'])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
parts=['CRITERIA_NOT_MET: original paired runner failed; native result separately preserved.','\n\n'.join(findings[:2]),m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],'431 frozen files; explicit answer_progress_control=true in experiment only. [동결](artifacts/design-freeze.json).','\n\n'.join(findings),'[모의 검사](artifacts/contracts-final.txt), [실제 기록](artifacts/known-query/candidate/result.json), [원문](artifacts/source-audit.json).',json.dumps(summary,ensure_ascii=False,indent=2),'No MAIN activation; preserve original failures and perform independent offline replay if needed.','\n\n'.join(limits),'Candidate-only; working/selected/GENOS state unchanged.','reserve → design → isolated implementation → deterministic checks/repairs → freeze → paired6 → native<=14 → source audit → archive → final validation.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 답변 진전 기반 종료 실험\n\n'+''.join(h+'\n\n'+x+'\n\n' for h,x in zip(ADR_HEADINGS,parts)))
for row in m['questions']:
 case=row['case_id'];public=case=='public-expenses';native='[native result](../artifacts/known-query/candidate/result.json)' if public else '[paired responses](../artifacts/paired/)'
 vals=[f"run-001/{case}; synthetic paired stage" if not public else 'run-001/candidate native public request',read(ART/'known-request.json')['json']['question'] if public else next(x['question'] for x in read(ART/'stage-inputs.json') if x['id']==('chain' if case=='required-chain' else case)), 'No approved legal gold; frozen stage action labels in stage-gold.json, never product context.','[input](../artifacts/stage-inputs.json) and [known request](../artifacts/known-request.json).','[source ledger](../artifacts/retrieval-ledger.json); synthetic stage has no retrieval execution.',native,'Usage/call counts retained in raw result and experiment manifest.','No model judge; paired harness error prevents original formal grade.','\n\n'.join(findings if public else [findings[2]])]
 qp=ADR/'실험'/row['file'];qp.write_text('# '+case+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));row['sha256']=sha(qp)
save(ADR/'실험/manifest.json',m)
index=ROOT/'04_EXPERIMENTS/ADR/README.md';text=index.read_text();line='- [ADR-1002 답변 진전 기반 종료](ADR-1002-answer-progress-termination/README.md) — 원본 paired 실행기 오류 보존, 실제 질의 호출·원문 도달 별도 측정, MAIN 미변경.\n';assert 'ADR-1002 답변' not in text;index.write_text(text.replace('# ADR workspace\n','# ADR workspace\n'+line))
print(json.dumps(summary,ensure_ascii=False,indent=2))
