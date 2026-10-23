from common import *
import sys,tarfile,shutil,sqlite3
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');o=read(ART/'observations.json');r=o['native_result'];P=ART/'known-query/candidate'
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert all(sha(ROOT/n)==h for n,h in s['working_before'].items())
assert o['main_unchanged']
required={};G=ROOT/s['base_release']['data_path'];db=sqlite3.connect((G/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
for key,title,law in [('income_tax97','제97조','소득세법'),('decree163','제163조','소득세법 시행령')]:
 found=[]
 for x in read(ART/'source-audit.json')['read_evidence']:
  v=db.execute('select json from source where id=?',(x['source_id'],)).fetchone()
  if not v:continue
  v=json.loads(v[0]);name=v.get('document_name','').split(' > ')[-1]
  if name==law and (v.get('heading') or '').split()[0].split('(')[0]==title:found.append(x['source_id'])
 required[key]=sorted(set(found))
db.close()
expected=read(ART/'offline-required-content.json')
assert sha(ART/'offline-required-content.json')==f['offline_required_content_sha256']
actual={b for row in read(ART/'source-audit.json')['read_evidence'] if row['source_id']==expected['source_id'] for b in row['blocks']}
content_coverage={'required_block_ids':expected['required_block_ids'],'verified_read_block_ids':sorted(actual),
 'missing_block_ids':sorted(set(expected['required_block_ids'])-actual)}
trace=read(ART/'calls.json');choices=[x['proposal'] for x in trace if x['proposal'].get('choice')]
save(ART/'completion-audit.json',{'content_coverage':content_coverage,'choices':choices,'monitor_calls':0})
met=r.get('service_status')==200 and r['model_calls']<=14 and all(required.values()) and not content_coverage['missing_block_ids'] and not o['source_checks']['mismatches'] and not o['source_checks']['scope_violations'] and o['outcome'].get('stop_reason')!='MODEL_DECISION_UNRESOLVED'
usage={'input_tokens':o['input_tokens'],'output_tokens':o['output_tokens'],'cost_usd':o['cost_usd']}
summary={'status':'COMPLETE','criteria_met':bool(met),'verdict':'KNOWN_CASE_CRITERIA_MET' if met else 'CRITERIA_NOT_MET','native_calls':r['model_calls'],'total_physical_calls':r['model_calls'],'native_seconds':r['seconds'],'service_status':r.get('service_status'),'required_sources':required,'required_content':content_coverage,'source_checks':o['source_checks'],'outcome':o['outcome'],'usage':usage,'quality_certified':False,'decision_eligible':False,'working_code_changed':False,'main_changed':False,'genos_changed':False,'limitations':['Known exposed single question; no legal-answer gold or out-of-sample inference','Native budget changed from40 to14; counts are descriptive, not isolated causal estimate','External Qwen does not certify GENOS internal model']}
save(ART/'result.json',summary)
findings=[f"실제 실행: {r['model_calls']}호출 / {r['seconds']:.3f}초 / HTTP{r.get('service_status')}. 기준 충족: {bool(met)}.",f"원문 도달: {json.dumps(required,ensure_ascii=False)}. 세부 원문 미확보 블록: {content_coverage['missing_block_ids']}. 검증: {json.dumps(o['source_checks'],ensure_ascii=False)}.",f"종료: {json.dumps(o['outcome'],ensure_ascii=False)}.","직전 ADR1005 call004에는97조 전체 원문과97에서 연결된163조9항의 역방향 참조 카드가 같은 입력에 있었다. 모델은 항목 이름만으로 충분하다고 임의 축소했고 추가 필요없음이라고 하면서 NEXT_TERM_MATCHES 두번을 선택했다. 정확한 입력 해시와 출처는 ../ADR-1006-source-content-completion/artifacts/prior97-input-diagnosis.json.","후보는 같은 조사 판단에서 실제 원문의 위임·준용 문장별 필요성 판단과 모델이 선택한 next_step을 하나의 계획으로 결속한다. 시스템이 선택을 기존 도구로 조립하며 필요한 READ와 별개의 FINISH 투표를 제거했다. 각 문장은 시스템이 원문·범위와 결속하고 모델이 문장을 재작성하지 않는다. 일반적인 충분 선언만으로 검토를 건너뛰지 못한다. 미확보 필요 내용을 선언한 채 충분 종료할 수 없다. 상태값을 도구 종류에서 자동 채우지 않고 실제 모델 출력에 유지한다. 연결된 조 전체는 별도 선택지이며 정확한 기존 항·호 READ를 바꾸지 않는다. 특정 법령번호나 정답을 제품에 넣지 않았다.","총 모델 예산14·최종화예약3. 감시 LLM 추가0. 관련 없는 연결은 모델이 제외하고 조회 실패·진전 없음은 제한 답변으로 넘긴다. 원문·권한·상태 오류는 계속 거부한다.","선택 MAIN102/GENOS 변경없음. 작업 통합은 별도 기록한다."]
(ADR/'RESULT.txt').write_text('\n\n'.join(findings+summary['limitations'])+'\n')
runtime=P/'runtime';archive=P/'runtime.tar.gz'
if runtime.exists():
 assert not archive.exists();hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
 with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
 with tarfile.open(archive,'r:gz') as t:
  for name,h in hashes.items():
   with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==h
 save(P/'runtime-archive.json',{'archive':'runtime.tar.gz','sha256':sha(archive),'verified_files':hashes,'restore':'Extract into an empty directory; original relative paths preserved.','process_finished':True})
 shutil.rmtree(runtime)
m=read(ADR/'실험/manifest.json');assert m['design']==f['design']
m['runs'][0].update(arm_ids=['candidate'],status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'accuracy_not_scored_reason':'Historical ADR1006 only; no new baseline execution','new_calls':0},'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'Source reachability and operational contract only; no approved legal-answer gold','new_calls':r['model_calls'],'quality_certified':False}},comparisons=[],judge_disagreements=0,usage={'physical_calls':r['model_calls'],**usage},latency={'service_seconds':r['seconds'],'model_seconds':o['model_seconds'],'request_p50_seconds':r['seconds'],'request_p95_seconds':r['seconds'],'sample_size':1},error_taxonomy=[] if met else ['NATIVE_REQUIRED_CRITERIA_NOT_MET'])
nr=len(o['read_coordinates']);nf=len(o['final_coordinates'])
m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter=nr,after_filter=nf,presented_total=nf,presented_mean=nf,presented_p50=nf,presented_p95=nf,golden_recall={'candidate':None},selectivity=nf/o['corpus_total'])
for k in ('presented_total','presented_mean','presented_p50','presented_p95','selectivity'):m['retrieval_accounting'][k]={'candidate':m['retrieval_accounting'][k]}
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
status='Proposed' if met else 'Rejected';front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+status)
parts=[summary['verdict']+'; known exposed case, not quality certification.','\n\n'.join(findings[3:5]),m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],'444 frozen files; [동결](artifacts/design-freeze.json).','\n\n'.join(findings),'[계약](artifacts/contracts-initial.txt), [실제 기록](artifacts/known-query/candidate/result.json), [원문](artifacts/source-audit.json).',json.dumps(summary,ensure_ascii=False,indent=2),'Historical comparisons are descriptive; no causal isolation.','\n\n'.join(summary['limitations']),'Selected MAIN pointer unchanged; candidate preserved and working fixes separately audited.','reserve → design → isolated implementation → deterministic checks → freeze → native<=14 → source audit → archive → final validation.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 필요한 연결 원문 확인과 조사 종료\n\n'+''.join(h+'\n\n'+x+'\n\n' for h,x in zip(ADR_HEADINGS,parts)))
for row in m['questions']:
 vals=['run-001/candidate; one known public request',read(ART/'known-request.json')['json']['question'],'No approved legal-answer gold. Expected source coordinates are offline audit targets only.','[Exact request](../artifacts/known-request.json); provider messages and responses in known-query/candidate/model.','[Read/final stage ledger](../artifacts/retrieval-ledger.json), source-level exact checks in source-audit.json.','[Native response](../artifacts/known-query/candidate/response.json).','[All call inputs/outputs](../artifacts/calls.json). No separate monitor.','No model judge; source/ACL/usage audit only.','\n\n'.join(findings)]
 qp=ADR/'실험'/row['file'];qp.write_text('# '+row['case_id']+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));row['sha256']=sha(qp)
save(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실행 질문\n\n- [known-query](질문-001-known-query.md): '+summary['verdict']+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';text=index.read_text();line='- [ADR-1008 필요한 연결 원문과 조사 종료](ADR-1008-content-plan-execution/README.md) — 공개 질문1개, 호출 예산14, 선택 MAIN 미변경.\n';assert 'ADR-1008-content-plan-execution/README.md' not in text;index.write_text(text.replace('# ADR workspace\n','# ADR workspace\n'+line))
print(json.dumps(summary,ensure_ascii=False,indent=2))
