"""Offline final accounting; no models and no product changes."""
from common import *
import re,statistics,collections
audit=read(ART/'source-wire-audit.json');semantic=read(ART/'semantic-review.json');progress=read(ART/'execution-progress.json')
rows=[read(d/'result.json') for d in sorted((ART/'live').iterdir()) if (d/'result.json').exists()];aa=audit['cells'];sr=semantic['rows']
f=read(DES/'freeze.json');drift=[n for n,h in f['files'].items() if sha(ROOT/n)!=h]
code=ROOT/f['code_root'];code_drift=[n for n,h in f['selected_files'].items() if sha(code/n)!=h]
assert not drift and not code_drift
source_ok=all(not a[k] for a in aa for k in ('source_mismatches','acl_violations','wire_mismatches','output_caps'))
provider_rows=[];switches=[]
for d in sorted((ART/'live').iterdir()):
 for c in read(d/'calls.json') if (d/'calls.json').exists() else []:
  provider_rows.append({'cell':d.name,**c})
 for p in d.rglob('provider-switches.json'):switches.extend(read(p))
routing_ok=all(c['provider']=={'only':['near-ai/fp8'],'order':['near-ai/fp8'],'quantizations':['fp8'],'allow_fallbacks':False,'require_parameters':True} for c in provider_rows)
received=[c for c in provider_rows if c.get('http_status')==200]
received_ok=all(c.get('actual_provider')=='Near AI' and c.get('actual_model')=='qwen/qwen3.8-27b' for c in received)
metrics={}
for arm in ('baseline','ontology-on'):
 ar=[r for r in rows if r['arm']==arm];au=[a for a in aa if a['arm']==arm];scores=[s for s in sr if s['arm']==arm]
 metrics[arm]={'planned':2,'attempted':len(ar),'complete_correct':sum(s['verdict']=='PASS' for s in scores),'incorrect':sum(s['verdict']=='FAIL' for s in scores),'incomplete':sum(s['verdict']=='INCOMPLETE' for s in scores),'transport_or_runner_failure':sum(s['verdict']=='ERROR' for s in scores),'not_run':2-len(ar),'request_seconds':sum(r['request_seconds'] for r in ar),'physical_calls':sum(a['physical_calls'] for a in au),'reported_tokens':sum(a['reported_tokens'] for a in au),'reported_cost_usd':sum(a['reported_cost_usd'] for a in au),'source_sql_calls':sum(r['source_sql_calls_before_requery'] for r in ar)}
complete=sum(x['complete_correct'] for x in metrics.values());attempted=len(rows)
pairs=[]
for case in read(DES/'cases.json'):
 scores={s['arm']:s['verdict'] for s in sr if s['case_id']==case['id']}
 pairs.append({'case_id':case['id'],'OFF':scores.get('baseline','NOT_RUN'),'ON':scores.get('ontology-on','NOT_RUN')})
unknown=sum(a['unknown'] for a in aa);physical=len(provider_rows)
on_visible={a['cell']:bool(a.get('wire_ontology_inputs')) for a in aa if a['arm']=='ontology-on'}
duplicate_rows=[r for r in rows if r['http_status']==200]
duplicate_ok=(all(r.get('duplicate',{}).get('same_answer') and r.get('duplicate',{}).get('extra_model_calls')==0 for r in duplicate_rows) if duplicate_rows else None)
resources_ok=all(a['peak_rusage_below5GiB'] and not a['resource_stop'] for a in aa)
passed=complete==4 and source_ok and routing_ok and received_ok and not switches and not unknown and duplicate_ok and resources_ok and len(on_visible)==2 and all(on_visible.values()) and all(a['budget_matches'] for a in aa)
result={'status':'PASS' if passed else 'NOT_PASSED','correct_completed':complete,'planned_cells':4,'attempted_cells':attempted,'metrics':metrics,'pairs':pairs,'semantic_review':semantic,'source_integrity':source_ok,'only_near_ai_requests':routing_ok,'received_provider_model_verified':received_ok,'provider_switches':len(switches),'physical_calls':physical,'http200':len(received),'unknown':unknown,'reported_cost_usd':sum(a['reported_cost_usd'] for a in aa),'reported_tokens':sum(a['reported_tokens'] for a in aa),'request_seconds':sum(r['request_seconds'] for r in rows),'model_seconds':sum(a['model_seconds'] for a in aa),'source_span_checks':sum(a['source_checks'] for a in aa),'delivered_span_checks':sum(a['delivered_checks'] for a in aa),'budget_matches':all(a['budget_matches'] for a in aa),'duplicates':duplicate_ok,'resources':resources_ok,'ontology_delivered':on_visible,'ontology_display_mismatches':[a['cell'] for a in aa if a.get('ontology_display_vs_wire_mismatch')],'frozen_input_drift':drift,'frozen_code_drift':code_drift,'main':'MAIN135/ordinary-assessment-20261103-r1','selected_product_files':516,'main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer_sha256'],'product_changes':0,'oracle_writes':0,'external_judge_calls':0,'quality_certified':False,'limits':'Known2 questions,4 cells, one attempt each, not broad accuracy estimate. Historical MAIN133/Parasail-priority results differ in code and are not causal provider comparison. Stored source version; no current-law advice. Oracle/OS caches not reset. Reported usage may omit failed/unknown calls. NativeAPI on frozen identical MAIN135 product, isolated SQLite state, actual read-only Oracle Gold data. No GENOS field execution.'}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['retrieval_accounting']=read(ART/'retrieval-metrics.json')
times=[r['request_seconds'] for r in rows]
errors=[{'cell':s['cell'],'type':s.get('error_taxonomy','other'),'verdict':s['verdict'],'reason':s['basis']} for s in sr if s['verdict']!='PASS']
m['results'].update(status='complete',by_arm=metrics,comparisons=pairs,judge_disagreements=0,usage={'physical_calls':physical,'reported_cost_usd':result['reported_cost_usd'],'reported_tokens':result['reported_tokens'],'http200':len(received),'unknown':unknown},latency={'request_seconds':result['request_seconds'],'model_seconds':result['model_seconds'],'p50_request_seconds':statistics.median(times) if times else None,'p95_request_seconds':None,'p95_reason':'Only four predeclared cells; no meaningful general tail-latency estimate'},error_taxonomy=errors)
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
table='| 질문 | 온톨로지 | 판정 | 시간(초) | 물리 호출 |\n|---|---|---|---:|---:|\n'
for case,arm in [('ontology-365','baseline'),('ontology-365','ontology-on'),('ontology-369','ontology-on'),('ontology-369','baseline')]:
 r=next((r for r in rows if r['case_id']==case and r['arm']==arm),None);s=next((s for s in sr if s['case_id']==case and s['arm']==arm),None)
 table+=f'| 상법{case[-3:]} | {"OFF" if arm=="baseline" else "ON"} | {s["verdict"] if s else "NOT_RUN"} | {r["request_seconds"]:.3f} | {r["physical_calls"]} |\n' if r else f'| 상법{case[-3:]} | {arm} | NOT_RUN | — | 0 |\n'
conclusion=f'MAIN135·Near AI 단독 실제 시험: 완료 정답 {complete}/4건(실행 {attempted}/4). 일반OFF {metrics["baseline"]["complete_correct"]}/2, 온톨로지ON {metrics["ontology-on"]["complete_correct"]}/2. {result["status"]}. 두 질문의 제한된 점검 결과다.'
values=[conclusion,'사용자가 Qwen·FP8·추론 설정을 유지한 Near AI 단독 시험을 요청했다. 최신 선택 MAIN135516파일을 그대로 동결하고 모델 전송 설정만 실험 범위에서 지정했다. 기존 MAIN133/Parasail 우선 시험은 과거 참조이며 공급자만 바꾼 A/B가 아니다.',
 '실행 전 artifacts/design/criteria.json 동결. 각 문항3개 필수 규칙의 조건·대상·시점·임계값과 인용 근거를 사후 대조한다. 원문전용과 미완료는 정답으로 세지 않는다. 실제wire·권한·예산·재조회·제공자 고정도 별도 확인한다.',
 '상법365 OFF→ON,369 ON→OFF 각1회. 새 프로세스·격리SQLite기록, 실제Oracle Gold 읽기전용. 최대 물리120/셀40·도구1024·셀1800초·호출180초·출력토큰 상한없음. UNKNOWN/자원/실행기/5xx 뒤 새셀 중단. 네트워크 없는 모의429에서 자동재시도/전환0과 실제API 승인 재생을 먼저 확인했다.',
 'Qwen3.8-27b / near-ai/fp8 only / allow_fallbacks=false / reasoning effort none. MAIN135516파일 원본과 후보 동일. code/data/transport/settings hashes: artifacts/design/freeze.json. 기존routing schema의 switches상한1은providers길이1로 전환이 불가능하다. 실제전송에서는 Near AI 단독만 허용한다. 기준답변은 scoring-only-originals.json으로 제품과 분리했다.',
 table+'\n실제 전체: '+json.dumps({k:result[k] for k in ('physical_calls','http200','unknown','provider_switches','reported_cost_usd','source_integrity','budget_matches')},ensure_ascii=False),
 '\n\n'.join(s['cell']+' — '+s['verdict']+': '+s['basis'] for s in sr)+'\n\n준비 단계의 부모기록 경로·불변요약 writer·모의 import·질문 scaffold 형식 오류는 모두 실제모델0 상태에서 보존/정정했다. 실제셀 재실행0. 모든 모델 원제안·보완·실패를 보존했다.',
 f'실제 {physical}물리 호출, HTTP200 {len(received)}, UNKNOWN {unknown}, 보고비용 ${result["reported_cost_usd"]:.8f}, 보고토큰 {result["reported_tokens"]}. 요청시간 합계 {result["request_seconds"]:.3f}초, 모델구간 {result["model_seconds"]:.3f}초. 확보span {result["source_span_checks"]}, 실제전달span 대조 {result["delivered_span_checks"]}; 반복대조횟수이며 고유조문 수가 아니다. 단계별 회수율은 retrieval-stage-ledger.json. 실패 호출 사용량 미보고가 있으면 비용 하한이다.',
 '전송 성공·원문 회수·유효 주장·답변 완결성을 분리한다. ON의 게시본 전달은 실제wire로 판정하며 PREPARED_NOT_SENT 등의 표시와 다르면 별도기록한다. 기존시험 대비 변화는 MAIN변경과 공급자변경이 함께 있어 Near AI의 인과적 우위로 해석하지 않는다.',
 result['limits'],
 '제공자 고정은 이번 실험 설정에 적용했다. 선택 MAIN/기본공급자/Gold설정/제품/원문/게시/Oracle내용·DDL/Git push/메일/GENOS현장 변경0. 실험 기록과 실패 원문은 보존했다. 영구 공급자 설정 전환이나 새 MAIN 승격은 이번 작업에 포함하지 않았다.',
 'ADR예약→동일MAIN135 snapshot/freeze→모의routing/observer·nativegrant재생→설계동결→4셀순차실행→source-wire audit→원문대조 semantic-review→ledger→runtime보관→finalize→hash/status/validate--final/graph. 완료셀 재실행 금지, 후속은 새ADR.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if passed else 'Rejected'),front)
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN135 Near AI 단독 실제 답변 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
for q in m['questions']:
 p=ADR/'실험'/q['file'];s=p.read_text();s=s.split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\n'+json.dumps([r for r in sr if r['case_id']==q['case_id']],ensure_ascii=False,indent=2)+'\n';p.write_text(s)
(ADR/'실험/README.md').write_text('# 두 질문·네 셀의 실행 기록\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n\n'+table)
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-main135-nearai';OUT.mkdir(exist_ok=True)
(OUT/'실제답변_검증결과.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1303','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design, preserved exact input/output or offline verification','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts or p.name.endswith('.tar.gz'))} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json']})
print(json.dumps({k:result[k] for k in ('status','correct_completed','attempted_cells','physical_calls','unknown','reported_cost_usd')},ensure_ascii=False))
