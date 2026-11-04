"""Finalize MAIN142 observation without changing observed inputs or outcomes."""
from common import *
import re, collections

OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-main142-charter-resolution'
OUT.mkdir(exist_ok=True)
base=ART/'public-live/charter-main142'
turns=read(base/'result.json')['turns'];calls=read(base/'calls.json')
audit=read(ART/'source-wire-audit.json');semantic=read(ART/'semantic-review.json')
candidate=read(DES/'candidate-main142.json');before=read(DES/'baseline.json')
assert all(sha(ROOT/candidate['code_root']/n)==h and sha(selected()/n)==h for n,h in candidate['selected_files'].items())
resources=read(base/'resource-final.json')
assert resources['selected_code_unchanged']
assert all(str(ROOT/candidate['code_root']) in p for p in resources['loaded_modules'].values())
assert read(ART/'runtime-archives.json')['all_restore_hashes_verified']
summary={
 'main':142,'release_id':before['pointer']['release_id'],'release_manifest_sha256':before['pointer']['release_manifest_sha256'],
 'selected_pointer_unchanged':before['pointer']==read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'frozen_files':528,'selected_files_unchanged':True,'candidate_revision':candidate['pin'],'new_product_changes':0,
 'all_product_imports_frozen':True,'loaded_product_modules':len(resources['loaded_modules']),
 'planned_questions':1,'executed_questions':len(turns),'turns':turns,'semantic':semantic,
 'physical_calls':len(calls),'http200':sum(c.get('http_status')==200 for c in calls),'http429':sum(c.get('http_status')==429 for c in calls),'unknown':sum(c.get('status')=='unknown' for c in calls),
 'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),
 'reported_prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) for c in calls),
 'reported_completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) for c in calls),
 'request_seconds':sum(t['request_seconds'] for t in turns),'model_seconds':sum(c.get('seconds',0) for c in calls),
 'source_checks':sum(a['source_checks'] for a in audit['cells']),'delivered_checks':sum(a['delivered_checks'] for a in audit['cells']),
 'source_mismatches':sum(len(a['source_mismatches']) for a in audit['cells']),'acl_violations':sum(len(a['acl_violations']) for a in audit['cells']),'wire_mismatches':sum(len(a['wire_mismatches']) for a in audit['cells']),
 'budget_matches':all(a['budget_matches'] for a in audit['cells']),
 'duplicate_extra_model_calls':sum(t.get('duplicate',{}).get('extra_model_calls',0) for t in turns),
 'source_storage':'SQLite','state_storage':'isolated SQLite','oracle_tested':False,'genos_tested':False,'quality_certified':False,
 'working_drift_not_imported':{n:{'before':h,'after':sha(ROOT/n)} for n,h in before['working_before'].items() if sha(ROOT/n)!=h}}
put(RUN/'result.json',summary);put(OUT/'검증요약.json',summary)

sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
m=read(ADR/'실험/manifest.json')
inventory={(x[0],int(x[1])) for x in read(ART/'source-inventory.json')['article_roots']}
a=audit['cells'][0];acquired={(x[0],int(x[1])) for x in a['acquired_articles']};presented={(x[0],int(x[1])) for x in a['presented_articles']}
assert presented<=acquired<=inventory
rec=StageLedgerRecorder('charter','main142',identity_canonicalizer)
rec.record_stage('source','source',sorted(inventory))
rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),discard_reasons={x:'Not acquired during this run; no absence inference' for x in inventory-acquired})
rec.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),discard_reasons={x:'Original not seen in actual model input' for x in acquired-presented})
ledger=build_experiment_artifact('ADR-1338',m['experiment_id'],[build_run_artifact('run-001',[grade_capture(rec.capture(),[])],{'main142':['source','acquired','present']})])
ledger['audit']={'meaning':'Single public question; no independent gold recall or causal comparison. Relation traversal is separately audited.'}
ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
lp=ART/'retrieval-stage-ledger.json.gz';put(ART/'retrieval-stage-ledger-ref.json',write_raw_json(lp,ledger))
def per(v):return {'baseline':None,'main142':v}
m['retrieval_accounting']={'changed':False,'corpus_total':len(inventory),'before_filter':per(len(inventory)),'after_filter':per(len(acquired)),'presented_total':per(len(presented)),'presented_mean':per(len(presented)),'presented_p50':per(len(presented)),'presented_p95':per(len(presented)),'golden_recall':per(None),'selectivity':per(len(presented)/len(inventory)),'not_applicable_reason':'Unchanged retrieval; observed acquisition and presentation only, no approved gold recall.','stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'physical_calls':0},'main142':summary},comparisons=[],judge_disagreements=0,usage={k:summary[k] for k in ('physical_calls','reported_cost_usd','reported_prompt_tokens','reported_completion_tokens','unknown')},latency={'request_seconds':summary['request_seconds'],'model_seconds':summary['model_seconds'],'p50':summary['request_seconds'],'p95':None,'reason':'One question; population p95 not estimated'},error_taxonomy=semantic['error_taxonomy'])
put(ADR/'실험/manifest.json',m)
answer=(base/'turn-1/answer.txt').read_text()
env='선택 MAIN142 gold-workflow-review-20261104-r1의 528파일과 전파일 SHA 동일한 격리본. 공개 상법 1문서·SQLite 원문·격리 SQLite 기록·Qwen3.8-27b FP8/추론none·Parasail 우선, 알려진429에만 NearAI 1회 전환. 기본 검토표 ON·온톨로지 OFF·출력상한 없음. 조문번호·정답 힌트 주입0. 제품/선택 MAIN/현장/메일 변경0.'
cost=f"요청 {summary['request_seconds']:.3f}초 / 모델 {summary['physical_calls']}회 / HTTP200 {summary['http200']} / 429 {summary['http429']} / UNKNOWN {summary['unknown']} / 보고비용 ${summary['reported_cost_usd']:.9f}. 원문대조 {summary['source_checks']}, 전달대조 {summary['delivered_checks']}, 원문·ACL·wire 불일치 {summary['source_mismatches']}/{summary['acl_violations']}/{summary['wire_mismatches']}. 예산일치 {summary['budget_matches']}, 동일요청 재조회 추가모델 {summary['duplicate_extra_model_calls']}."
limits='단일 질문 단회 관측이며 일반 정답률·속도 개선 비교가 아니다. SQLite와 외부 Qwen 결과이며 Oracle·GENOS 내부모델·현장 배포를 인증하지 않는다. 앞선 진단의 원인 가설은 이번 실제 연결 기록으로 구분한다. 관측 후 제품/질문/프롬프트 변경·실모델 재전송 없음.'
report='\n\n'.join([semantic['conclusion_ko'],env,'질문: '+turns[0]['step']['question'],'실행 경로와 원인\n'+'\n'.join(semantic['findings_ko']),'수정 방향\n'+'\n'.join(semantic['recommendations_ko']),cost,'실제 최종 답변\n'+answer,limits,'원시 입력·출력·연결/원문/행동 원장과 무손실 runtime: '+str(ADR.relative_to(ROOT))+'/artifacts'])+'\n'
(OUT/'실제질문_연결탐색_실험결과.txt').write_text(report)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[semantic['conclusion_ko'],'사용자가 정관 변경 질문의 연결 탐색 실패를 보고하고 최신 MAIN142 실험을 요청했다. 저장 역방향 참조의 존재와 실제 선택/읽기/종료를 구분한다.',json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'한 질문1회, 원문번호나 정답을 제시하지 않음. MAIN142 동결·모델0 입장점검 뒤 실제1회. 기술 오류/UNKNOWN 후 재전송 없음.',env,'판정: '+semantic['verdict_ko']+'\n\n실제 최종 답변:\n'+answer,'\n'.join(semantic['findings_ko']),cost,semantic['conclusion_ko']+'\n\n'+'\n'.join(semantic['recommendations_ko']),limits,'실험·읽기전용 진단만 수행했다. 제품 수정·MAIN 승격·배포·메일0. 후속 구현 및 실제 재검증은 별도 변경 기록으로 다룬다.','setup.py → live_public.py charter main142 --admission (model0) → live_public.py charter main142 (one real run) → audit.py/inspect_results.py/navigation_trace.py → semantic-review.json → archive_runtime.py → finish.py → adr_structure hash/status/validate --final/graph. 실제 모델 명령은 자동 재실행하지 않는다.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if semantic['all_criteria_passed'] else 'Rejected'),front)
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN142 정관 변경 결의요건 실제 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
qv=['run-001/main142; one question, baseline reference only.',turns[0]['step']['question'],'저장 상법 제433조·제434조 원문과 수치·분모·동시충족을 오프라인 대조. 기준답변/조문번호는 제품 입력에 넣지 않았다.','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz, source-wire-audit.json, navigation-trace.json.gz. 후보·제시·획득·사용을 분리한 원시 기록.','artifacts/public-live/charter-main142/raw/call-*/request.json.gz 및 response.json.gz가 실제 provider payload다. canonical은 별도 보존.','calls.json/generations.json과 canonical/ 전체, inspection-records.json.gz 및 navigation-trace.json.gz; runtime 전체 무손실 archive.','채점 LLM0. semantic-review.json 수동 판정 및 원문/ACL/wire 기계 대조. 재채점·재생성0.',json.dumps(semantic,ensure_ascii=False)]
(ADR/'실험'/m['questions'][0]['file']).write_text('# 정관 변경 단일 질문 실제 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,qv),1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 질문\n\n- [정관 변경 질문과 결과](질문-001-charter.md)\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]
paths+=list(Path(__file__).parent.glob('*.py'))+[p for p in OUT.glob('*') if p.is_file()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1338','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen MAIN142, exact raw model records, navigation/source audits and lossless runtime','contains_raw_prompts_and_outputs':'raw' in p.parts or 'canonical' in p.parts or p.name.endswith('.tar.gz')} for p in sorted(paths)]})
print(json.dumps({k:summary[k] for k in ('physical_calls','unknown','request_seconds','reported_cost_usd','source_checks','delivered_checks','budget_matches')},ensure_ascii=False))
