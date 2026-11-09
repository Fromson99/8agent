"""Close ADR-1422 as a frozen-rule resource stop. No model call; the stop is not re-run here."""
from common import *
stop=read(ART/'stop-record.json');crit=read(DES/'criteria.json');cases=read(DES/'live-cases.json')
calls=read(ART/'public-live/B03-03-selected/calls.json')
result={'selected_MAIN':161,'release_id':read(DES/'baseline.json')['pointer']['release_id'],'state':'STOPPED_RESOURCE_GUARD','executed_responses':0,'judged':0,'passed_registered_expectation':None,
 'not_executed':[c['id'] for c in cases][1:],'stopped_case':'B03-03','physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls),
 'reported_cost_usd':stop['reported_cost_usd'],'stop':stop,'quality_certified':False,'successor':'ADR-1423','scope':'Resource-guard stop record only; no answer was returned or judged.'}
put(ART/'result.json',result);RUN.mkdir(exist_ok=True);put(RUN/'result.json',{'result_path':str((ART/'result.json').relative_to(ROOT)),'sha256':sha(ART/'result.json')})
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
m=read(ADR/'실험/manifest.json');caps=[]
for q in m['questions']:
 rec=StageLedgerRecorder(q['case_id'],'selected',identity_canonicalizer)
 for sid,kind,parents in [('source','source',()),('acquired','retrieve',('source',)),('present','present',('acquired',))]:
  rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Batch stopped by the frozen resource guard before an answer was returned; not a legal absence judgment')
 caps.append(grade_capture(rec.capture(),[]))
ledger=build_experiment_artifact('ADR-1422',m['experiment_id'],[build_run_artifact('run-001',caps,{'selected':['source','acquired','present']})]);ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
lp=ART/'retrieval-stage-ledger.json.gz'
if not lp.exists():write_raw_json(lp,ledger)
corpus=len(read(ROOT/'04_EXPERIMENTS/ADR/ADR-1423-main161-integration-r5-qwen-r2/artifacts/source-inventory.json')['article_roots'])  # same scope and source generation as ADR-1423
m['retrieval_accounting']={'changed':False,'corpus_total':corpus,'before_filter':{'selected':0},'after_filter':{'selected':0},'presented_total':{'selected':0},'presented_mean':{'selected':0},'presented_p50':{'selected':0},'presented_p95':{'selected':0},'golden_recall':{'selected':None},'selectivity':{'selected':0.0},
 'not_applicable_reason':'Stopped before any answer; no retrieval outcome is judged.','stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
m['runs'][0].update(status='complete',artifact_path=str((RUN/'result.json').relative_to(ROOT)),sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'selected':{'correct':0,'total':0,'accuracy':None,'decision_eligible':False,'scope':'resource stop, nothing judged'}},comparisons=[],judge_disagreements=0,
 usage={'physical_calls':len(calls),'unknown':result['unknown'],'reported_cost_usd':result['reported_cost_usd']},latency={'median':None,'reason':'no answer returned'},error_taxonomy=[{'type':'resource_guard_stop','case_id':'B03-03'}])
for q in m['questions']:
 p=ADR/'실험'/q['file'];v={'case_id':q['case_id'],'status':'STOPPED_DURING_REQUEST' if q['case_id']=='B03-03' else 'NOT_EXECUTED','reason':stop['reason'] if q['case_id']=='B03-03' else 'batch stopped by frozen resource rule; executed in ADR-1423'}
 p.write_text(p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
summary='MAIN161 R5 30문항 첫 시도: B03-03 답변 조립 중 호스트 스왑 %.1fMiB 증가로 동결 자원 가드가 중단(5호출 모두 HTTP200, 가용 RAM %.2fGiB, 작업자 RSS %.0fMiB). 답변·판정 0건, 나머지 29문항 미실행, 보고비용 $%.6f. 같은 지시로 ADR-1423에서 작업자 기준 가드로 새로 실행.'%(stop['global_swap_growth_mib'],stop['available_gib_at_stop'],stop['worker_rss_mib_at_stop'],stop['reported_cost_usd'])
front=(ADR/'README.md').read_text().split('---',2)[1]
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[summary,'선택 MAIN161을 ADR-1412와 같은 R5 외규 30문항에 실행하려 했다.',json.dumps(crit,ensure_ascii=False),'30문항 순차 독립 실행 계획. 첫 문항에서 중단.','MAIN161 533파일, 같은 원문 세대. 작업 트리 핀31개는 실행 동안만 MAIN161 바이트로 바꾸고 복원(tree-restore.json: 31 복원/0 보존).',json.dumps(result,ensure_ascii=False,indent=2),
 stop['observation'],'물리 %d회, 보고비용 $%.6f.'%(len(calls),stop['reported_cost_usd']),'동결 기준대로 중단했으며 기준 자체는 이 ADR에서 바꾸지 않았다. 작업자 메모리는 ADR-1412와 비슷해 원인을 이 작업자로 확정하지 않는다.','판정 0건.','제품/MAIN 변경 없음. 같은 요청 재전송 없음. 후속 실행은 별도 ADR-1423.','기록: artifacts/stop-record.json, public-live/B03-03-selected/resource-stop.json.']
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN161 통합테스트 R5 30문항 첫 시도(자원 가드 중단)\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
(ADR/'실험/README.md').write_text('# R5 실제 질문 첫 시도\n\n'+summary+'\n')
print(summary)
