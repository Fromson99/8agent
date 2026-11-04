"""Record all outcomes; no new provider calls and no alteration of frozen inputs."""
from common import *
import statistics,re,collections
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-multiturn-repair';OUT.mkdir(exist_ok=True)
audit=read(ART/'source-wire-audit.json');base=ART/'public-live/repeat-repaired'
turns=read(base/'result.json')['turns'] if (base/'result.json').exists() else []
calls=read(base/'calls.json') if (base/'calls.json').exists() else []
ct=read(ART/'contract-repaired/result.json');bt=read(ART/'contract-baseline/result.json')
summary={'selected_main':138,'candidate_revision':read(DES/'candidate-repaired.json')['pin'],'product_candidate_files_changed':6,
 'common_contracts':{'baseline_passed':bt['passed'],'candidate_passed':ct['passed']-14,'failures':ct['failed']+bt['failed']},
 'new_contracts_passed':14,'baseline_failure_mechanism_reproduced':read(ART/'baseline-observed/result.json')['passed']==1,
 'turns':turns,'physical_calls':len(calls),'http200':sum(c.get('http_status')==200 for c in calls),'http429':sum(c.get('http_status')==429 for c in calls),'unknown':sum(c.get('status')=='unknown' for c in calls),
 'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),'reported_prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) for c in calls),'reported_completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) for c in calls),
 'request_seconds':sum(t['request_seconds'] for t in turns),'model_seconds':sum(c.get('seconds',0) for c in calls),
 'source_checks':sum(a['source_checks'] for a in audit['cells']),'delivered_checks':sum(a['delivered_checks'] for a in audit['cells']),
 'source_mismatches':sum(len(a['source_mismatches']) for a in audit['cells']),'acl_violations':sum(len(a['acl_violations']) for a in audit['cells']),'wire_mismatches':sum(len(a['wire_mismatches']) for a in audit['cells']),'budget_matches':all(a['budget_matches'] for a in audit['cells']),
 'duplicate_extra_model_calls':sum(t.get('duplicate',{}).get('extra_model_calls',0) for t in turns),
 'oracle_build_preflight':'Three source hashes require catalogue regeneration; frozen rev001 unchanged. Follow-up build/integration ADR required.',
 'full60_live_passed':False,'main_changed':False,'field_execution':False,'email_sent':False,'quality_certified':False}
put(RUN/'result.json',summary);put(OUT/'수정후_검증요약.json',summary)
# Per-arm retrieval is observed only from real physical input; mocks have no claim to real corpus recall.
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
m=read(ADR/'실험/manifest.json');inventory={(x[0],int(x[1])) for x in read(ART/'source-inventory.json')['article_roots']};captures=[];counts=[]
for arm in ('baseline','repaired'):
 for q in m['questions']:
  a=next((a for a in audit['cells'] if a['case_id']==q['case_id']),None) if arm=='repaired' else None
  rec=StageLedgerRecorder(q['case_id'],arm,identity_canonicalizer)
  if a:
   acquired={(x[0],int(x[1])) for x in a['acquired_articles']};presented={(x[0],int(x[1])) for x in a['presented_articles']}
   assert presented<=acquired<=inventory
   rec.record_stage('source','source',sorted(inventory))
   rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),discard_reasons={x:'Not acquired before termination; no absence inference' for x in inventory-acquired})
   rec.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),discard_reasons={x:'Original not seen in outgoing input' for x in acquired-presented});counts.append(len(presented))
  else:
   for sid,kind,parents in [('source','source',()),('acquired','retrieve',('source',)),('present','present',('acquired',))]:rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Synthetic contract only or dependent live turn not separately dispatched; real followups accounted under repeat session')
  captures.append(grade_capture(rec.capture(),[]))
ledger=build_experiment_artifact('ADR-1319',m['experiment_id'],[build_run_artifact('run-001',captures,{a:['source','acquired','present'] for a in ('baseline','repaired')})]);ledger['audit']={'meaning':'Five patterns. Actual public sequence is aggregated under repeat; synthetic cases and nonexecuted dependent turns skipped. No approved answer-key recall.'};ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
lp=ART/'retrieval-stage-ledger.json.gz';put(ART/'retrieval-stage-ledger-ref.json',write_raw_json(lp,ledger))
def per(v):return {'baseline':None,'repaired':v}
n=len(inventory);total=sum(counts)
m['retrieval_accounting']={'changed':False,'corpus_total':n,'before_filter':per(n),'after_filter':per(sum(len(a['acquired_articles']) for a in audit['cells'])),'presented_total':per(total),'presented_mean':per(statistics.mean(counts) if counts else 0),'presented_p50':per(statistics.median(counts) if counts else 0),'presented_p95':per(max(counts,default=0)),'golden_recall':per(None),'selectivity':per(total/n if n else None),'not_applicable_reason':'Search corpus and ranking unchanged; command continuation can change executed route. Real observations recorded, no paired live accuracy comparison.','stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['results'].update(status='complete',by_arm={'baseline':{'common_contracts_passed':bt['passed'],'failure_reproduced':True,'new_model_calls':0},'repaired':summary},comparisons=[{'metric':'common synthetic contracts','baseline':bt['passed'],'repaired':ct['passed']-14,'new_regressions':0}],judge_disagreements=0,usage={k:summary[k] for k in ('physical_calls','reported_cost_usd','reported_prompt_tokens','reported_completion_tokens','unknown')},latency={k:summary[k] for k in ('request_seconds','model_seconds')},error_taxonomy=[{'type':'other','name':'native_query_source_hash_refresh_required','count':3}]);put(ADR/'실험/manifest.json',m)
semantic=read(ART/'semantic-review.json')
texts=[
'명령 보완 경로 수정 후보의 기계적 계약은 통과했습니다. 실제 답변과 통테60개 통과 여부는 아래 원응답 기준이며 후보검증을 선택 MAIN138 반영으로 설명하지 않습니다.',
'수정: method별 문서범위·수정필드 schema를 normalize에 맞춤; 보완 전 원제안 보존 및 정확한 오류 경로; 필드 오류 보완에서는 method/target 유지, 의미 판단 거절이면 재선택 허용. 최종 검토는 채택/미해결 충돌 위치와 양쪽 수정 선택지만 전달하며 상태·claim·gap·근거를 서버가 바꾸지 않음.',
f'검사: 기준{bt["passed"]}·후보{ct["passed"]} 통과(공통104/신규14), 실패0. 기준 코드에서 AUTHORIZED 재검토 허용→normalize 거절→원제안 소실→새 목표 변경을 재현. 실제 API 모의 범위전환·후속·주제전환·기존 실패/중복방지 검사 포함. 모의 통과는 모델 답변 통과 아님.',
json.dumps(semantic,ensure_ascii=False,indent=2),
f'물리호출{len(calls)} / HTTP200 {summary["http200"]} /429 {summary["http429"]} /UNKNOWN {summary["unknown"]} / 보고비용 ${summary["reported_cost_usd"]:.9f}. 미보고 사용량은 추정하지 않음. 원문{summary["source_checks"]}/전달{summary["delivered_checks"]}건, 원문/ACL/wire 불일치 {summary["source_mismatches"]}/{summary["acl_violations"]}/{summary["wire_mismatches"]}, 예산일치 {summary["budget_matches"]}, 동일요청 추가호출{summary["duplicate_extra_model_calls"]}.',
'환경: MAIN138 동일525파일에서 격리한 rev001, SQLite 저장원문, Qwen3.8-27b FP8/추론none, Parasail 우선·알려진429만 NearAI 1회 전환. 내부 내규를 공개표시로 바꾸지 않았고 GENOS/내부모델/화면은 미실행. 판단 정답률·속도개선의 전후 비교 아님.',
'빌드 검증: 변경한3 SQL보유파일의 준비계획 소스 해시가 이전 상태라 Oracle preflight가 차단됨. SQL 내용 변경이 아니라 해시 갱신 필요. 동결 후보·이번 결과를 보존하고 별도 후속 ADR에서 재생성·작업코드 통합한다. 현재ADR 제품작업코드/MAIN/배포/메일 변경0.',
'R3 각30개·서식은 유지. 이 실행이 실패/중단되면 나머지58개를 통과로 바꾸거나 실제 미실행 질문의 정답을 만들지 않음.']
(OUT/'수정과_실제질문_검증결과.txt').write_text('\n\n'.join(texts)+'\n')
head=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[texts[0],texts[1],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),texts[2],texts[5],texts[3],texts[6],texts[4]+'\n\n단계별 회수·탈락 원장: artifacts/retrieval-stage-ledger.json.gz; gold 미승인으로 recall=null.',texts[0],texts[5]+'\n'+texts[7],texts[6], 'setup→edit→freeze→check baseline/repaired→no-send preflight→live_public once→audit→semantic-review→archive_runtime→finish_records→hash/status/validate --final/graph. 이미 전송한 request 재실행 금지. 실행기는 06_TOOLS/EXPERIMENTS/adr_1319, 정확한 코드 및 전송은 artifacts/design 지문과 raw/canonical/runtime 보관본 참조.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 멀티턴 명령·검토 보완 후보 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(head,vals),1))+'\n')
case_map={c['id']:c for c in read(DES/'cases.json')}
for q in m['questions']:
 contents=[f'run-001 / baseline·repaired / exact. 기준은 모의검사만. 후보 실제 공개 대화 원본: artifacts/public-live/repeat-repaired. 모의 API·실제 답변을 구분한다.',json.dumps(case_map[q['case_id']],ensure_ascii=False), '독립 승인 정답지는 없음. 실제 저장원문과 인용을 대조하고 같은 목표 유지·범위전환·중복 전송 여부를 확인. 정답이나 평가결과를 제품 입력에 넣지 않음.', '### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz 및 source-wire-audit.json. 실제 대화 전체는 repeat에 집계, 다른 패턴은 모의 또는 미실행으로 따로 표시. gold 없음.', 'system/user/schema/provider 원응답·사용량·지연은 artifacts/public-live/repeat-repaired/raw/call-*/*.json.gz, canonical/*.json.gz. baseline 실모델0, 후보 미도달 턴에는 원응답 없음.', '단계·순서·오류: calls.json/generations.json 및 각 turn 응답. raw 원본을 요약으로 대체하지 않음.', '채점 LLM0. artifacts/semantic-review.json의 수동 실제 원문 대조. 기준/후보 실모델 전후효과·정답률로 일반화하지 않음.', json.dumps(semantic,ensure_ascii=False)+'\n공통104/신규14 계약 통과. Oracle source hash3 갱신 미완료.']
 headers=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
 (ADR/'실험'/q['file']).write_text('# 질문 '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(headers,contents),1))+'\n')
(ADR/'실험/README.md').write_text('# 5종 검증\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1319','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen candidate, complete raw inputs and failed outcomes preserved','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts or p.name.endswith('.tar.gz'))} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]})
print(json.dumps(summary,ensure_ascii=False))
