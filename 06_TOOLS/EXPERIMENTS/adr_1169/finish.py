"""Finalize partial live result and distinguish runtime guard from supervisor behavior."""
from common import *
import subprocess,sqlite3,tempfile,tarfile,shutil,sys
f=read(DES/'freeze.json');m=read(ADR/'실험/manifest.json');r=read(RUN/'result.json');a=read(RUN/'supervisor-summary.json');assert r['model_calls']==17 and len(a)==2
assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in f['inputs'].items())
assert all(sha(ROOT/n)==h for n,h in f['scripts'].items())
p=RUN/'cm-001'
with tarfile.open(p/'runtime.tar.gz','r:gz') as tar,tempfile.TemporaryDirectory(dir=ART) as tmp:
 name=next(x.name for x in tar.getmembers() if x.name.endswith('/cases-v4.sqlite'));dest=Path(tmp)/'db.sqlite'
 for suffix in ('','-wal','-shm'):
  try:entry=tar.getmember(name+suffix)
  except KeyError:continue
  with tar.extractfile(entry) as src,Path(str(dest)+suffix).open('wb') as out:shutil.copyfileobj(src,out)
 db=sqlite3.connect(dest.as_uri()+'?mode=ro',uri=True);stored=[{'id':x[0],'status':x[1],'response_bytes':x[2]} for x in db.execute('SELECT id,status,length(response) FROM request')];db.close()
put(p/'publication-check.json',{'requests':stored,'scope':'Storage state only, no legal quality claim'})
stop=read(RUN/'cm-007/resource-stop.json')
r.update(execution_complete=False,planned=3,attempted=2,published_limited_answers=1,published_answers_with_claims=0,not_started=['cm-009'],supervisor_call_attempts=3,known_completed_supervisor_calls=2,unknown_provider_outcomes=1,usage_boundary='16 returned calls included in known usage/cost; final attempted supervisor response and billing unknown',case_results=a,runtime_stop={'case_id':'cm-007','reason':stop['reason'],'available_ram_gib':stop['current']['available']/1024**3,'worker_rss_gib':stop['current']['rss']/1024**3,'psi_full_avg10':stop['current']['psi']['full'],'interpretation':'Global PSI-only guard stopped with ample RAM; overly sensitive experiment guard, not OOM and not investigation-supervisor halt'},success_criteria_met=False,quality_certified=False)
put(RUN/'result.json',r)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=False)
m['results']['by_arm']['supervised'].update(planned=3,attempted=2,completed_answers=1,answers_with_claims=0,not_started=1,quality_certified=False)
m['results']['usage'].update(supervisor_attempts=3,supervisor_known_completed=2,unknown_provider_outcomes=1,cost_excludes_unknown_final_call=True)
m['results']['error_taxonomy']=[{'type':'LIMITED_ANSWER_WITHOUT_CLAIMS','count':1},{'type':'EXPERIMENT_GLOBAL_PSI_GUARD_UNKNOWN_PROVIDER_OUTCOME','count':1},{'type':'NOT_STARTED_DUE_BATCH_STOP','count':1}]
m['results']['latency']['interpretation']='2 attempted requests; second interrupted. Not3 completed answers, not successful end-to-end latency, no improvement percentage.'
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
ledger=read(RUN/'retrieval-ledger.json');graded=ledger['runs'][0]['arms'][0]['cases']
if not any(x['case_id']=='cm-009' for x in graded):
 skipped=StageLedgerRecorder('cm-009','supervised',identity_canonicalizer)
 for sid,kind,parents in [('delivered_or_read','source',[]),('original_read','select',['delivered_or_read']),('final_cited','present',['original_read'])]:
  skipped.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Case NOT STARTED after cm007 global-PSI guard and unknown provider outcome; no retrieval or answer score observed')
 gold=next(x for x in read(ART/'evaluation-only/cases.json') if x['id']=='cm-009')['targets']
 graded.append(grade_capture(skipped.capture(),[{'doc_id':x['doc_id'],'node':int(x['node'])} for x in gold]))
 put(RUN/'retrieval-ledger.json',build_experiment_artifact('ADR-1169',m['experiment_id'],[build_run_artifact('run-001',graded,{'supervised':['delivered_or_read','original_read','final_cited']})]))
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
refs={x['id']:x for x in read(ART/'evaluation-only/cases.json')}
for q in m['questions']:
 cid=q['case_id'];rec=next((x for x in a if x['case_id']==cid),None);link='../artifacts/run-001/'+cid
 if rec:
  texts=[f'run-001 / supervised / exact / {cid}; isolated same1167 candidate on MAIN112.',refs[cid]['question'],refs[cid]['reference_answer']+'\n\n평가 전용, 제품 비공개. 법률 정답률 미채점.',f'[동결](../artifacts/design/freeze.json), [실제요청]({link}/request.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[단계원장](../artifacts/run-001/retrieval-ledger.json), [회수]({link}/focus-audit.json). 최종인용은 claims 기반으로 산정; 제한답변의 원문 소개와 구분.',f'[호출 원장]({link}/calls.json), raw/call-*/request.json,response.json; canonical/*.json.gz; wire/*.json.gz에 실제 입력/출력 보존.',f'[감시·행동·근거 시간]({link}/supervisor-audit.json). 감시 요청 {rec["supervisor_calls"]}회;007의 마지막1회는 결과 미확인.','추가 evaluator0. 알려진 인샘플; 새 법률 정답률 없음.',f'실제 결론 주장{rec["claim_count"]}개. '+('HTTP200/READY, LIMITED_ANSWER/INSUFFICIENT. 원문/미확인 목록 반환과 저장 확인.' if cid=='cm-001' else '전역PSI 자원기준으로 중단. 가용RAM8.52GiB, OOM 아님. 마지막 제공자 응답 미확인, 재시도 없음.')]
 else:
  texts=['run-001 / supervised / cm-009; NOT STARTED',refs[cid]['question'],refs[cid]['reference_answer']+'\n\n평가 전용; 제품 전달0.','[동결 요청](../artifacts/design/cases.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n실행되지 않아 이 사례의 회수 원장 없음.','제품 호출0.','감시/보완0.','채점0.','007의 알려지지 않은 응답 및 자원 기준에 따라 배치 중단. 미실행을 오답으로 채점하지 않음.']
 qp=ADR/'실험'/q['file'];qp.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(qp)
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['CM001 제한답변,CM007 실험용PSI감시 중단,CM009 미실행. Proposed 유지·성공/승격 아님. MAIN112 유지.','ADR1168 초기준비 RAM차단 뒤 사용자 요청으로 메모리 확보. 완료1167 수정본459파일 동일. 실행환경 재시작 뒤빈 claim은 남아있는 reservation에서 복원했고 원본빈파일/복원근거 보존.','[사전동결](artifacts/design/criteria.json). 1168과 동일자원기준·40호출내 감시2·1024도구·1800초. 결과 뒤 기준 완화/재호출 없음.','CM001/007/009각1회 순차 예정. 모델0 사전 API 경계 통과 후0019호출,0078호출 시도(마지막응답미확인).009미시작.','MAIN112원문65개범위·Qwen3.8/ParasailFP8/no reasoning/fallback없음/출력상한없음. 정답은평가전용. 완결된 동시통제 A/B 아님.','001:117.167초·9호출(감시1),HTTP200/READY·LIMITED_ANSWER/INSUFFICIENT·실제주장0·저장확인.007:162.483초·8호출시도(감시2,마지막unknown),응답미발행.009미실행.','001 제26조 서버확보25.889초/모델전달46.619초. 감시가ASSESS_NOW 후 최초판단에서시행세칙제23조 부족을 제시했으나 뒤모델이추가읽기를진행하지않고 제한답변.007 코스닥13조 서버확보47.694초/모델전달50.747초,유가13조미확보. 감시는FINISH를취소했으나 유가13조확인이라는목적에증권인수규정15조⑦을선택. 그원문은실제로읽었고유가13도착은미확인.','총17호출시도,완료16·unknown1. 확인된input213569/output9477tokens·$0.07061636;unknown비용제외. 원문/권한/채택주장참조 위반0,출력상한0. 2시도지연을3개성공답변의속도로사용하지않음.','기계적인중단·진행전환집행은관측. 의미상목표와실제target결속은여전히실패가능. 종료제어만으로답변완성을보장하지않음.007전역PSI1.44%때가용RAM8.52GiB,RSS3.20GiB였으므로이번은메모리부족이나감시모델종료가아니라과민한실험자원기준중단.','001결론주장0,007중도중단,009미실행. 법률품질/전체회수/전체지연/GENOS미인증. 최초회수는서버확보와모델전달구분.유가13의현재조항카드부재는DB부재를뜻하지않음.','MAIN112불변·새승격/배포/메일/Git없음. unknown응답재시도없음. 다음실험은전역PSI단독중단을재설계하고목표법령/조항과도구target의실제좌표불일치를다뤄별도동결할필요.','prepare→freeze→host preflight→batch→summarize/supervisor_audit/finalize→finish→hash/validate→status completed→최종validate/graph. 완료실험재실행금지.']
rp=ADR/'README.md';meta=rp.read_text().split('---',2)[1];rp.write_text('---'+meta+'---\n\n# 메모리 확보 후 감시 CM3 실행\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
report=ROOT/'07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/INVESTIGATION_SUPERVISOR_LIVE_20261028.txt'
report.write_text('메모리 확보 후 감시 실제 실행 — ADR1169\n\n'+ '\n\n'.join(texts[5:11])+'\n\n기록: '+str(ADR)+'\n메모리: '+str(ROOT/'09_ARTIFACTS/AUDITS/20261028-memory-reclaim/결과.txt')+'\n')
if (ART/'manifest.json').stat().st_size==0:
 (ART/'empty-artifact-manifest-after-reconnect.bin').write_bytes(b'')
 manifest={'schema_version':'adr-artifacts-v1','adr_id':'ADR-1169','created_at':m['reservation']['created_at'],'files':[]}
else:manifest=read(ART/'manifest.json')
files=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json']+[ROOT/f['candidate_revision']['manifest_path'],report,Path(__file__),Path(__file__).with_name('supervisor_audit.py')]
manifest['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved retry inputs/actual outputs/partial-result audit','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts or 'wire' in p.parts)} for p in files];put(ART/'manifest.json',manifest)
print('Partial result sealed; validate BEFORE completing reservation. MAIN unchanged.')
