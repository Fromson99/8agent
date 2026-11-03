"""Post-run reporting of the frozen paired comparison; never dispatches models."""
from common import *
import re,statistics,collections
A=read(ART/'source-wire-audit.json');S=read(ART/'semantic-review.json');ablation=read(ART/'ablation-wire-audit.json');scores={r['cell']:r for r in S['rows']}
f=read(DES/'freeze.json');assert all(sha(ROOT/n)==h for n,h in f['files'].items())
for arm in ('before','after'):
 c=read(DES/('candidate-'+arm+'.json'));assert all(sha(ROOT/c['code_root']/n)==h for n,h in c['selected_files'].items())
source=ROOT/read(DES/'baseline.json')['release']['data_path'];assert sha(source/'store.sqlite')==read(DES/'sqlite-source.json')['store_sha256']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline-after.json')['pointer_sha256']
rows=[];allcalls=[]
for cell in read(DES/'criteria.json')['order']:
 case,arm=cell.split('/');folder=ART/'live'/(case+'-'+arm)
 calls=read(folder/'calls.json') if (folder/'calls.json').exists() else [];allcalls.extend(calls)
 if not (folder/'result.json').exists():
  rows.append({'case_id':case,'arm':arm,'cell':folder.name,'status':'NOT_RUN' if not calls else 'ERROR','physical_calls':len(calls),'verdict':scores.get(folder.name,{}).get('verdict','NOT_RUN')});continue
 r=read(folder/'result.json');a=next(x for x in A['cells'] if x['cell']==folder.name);sql=read(folder/'sql-observation.json')
 q=[x for x in sql['rows'] if x['phase']=='request']
 buckets={}
 for db in ('corpus','journal','memory','other'):
  ds=[x for x in q if x['database']==db]
  buckets[db]={'trace_events_including_internal':sum(x['trace_statements'] for x in ds),'execute_api_calls':sum(x['api_calls'] for x in ds if x['operation'] in ('execute','executemany','executescript')),'select_statements':sum(x['trace_statements'] for x in ds if x['operation'] in ('trace_SELECT','trace_WITH')),'api_seconds':sum(x['api_seconds'] for x in ds),'api_calls':sum(x['api_calls'] for x in ds),'returned_rows':sum(x['returned_rows'] for x in ds)}
 model=sum(x.get('seconds',0) for x in calls)
 row={**r,'cell':folder.name,'verdict':scores[folder.name]['verdict'],'model_seconds':model,'outside_model_seconds':r['request_seconds']-model,'prepare_seconds':read(folder/'binding.json')['prepare_seconds'],'sqlite':buckets,'sqlite_api_seconds':sum(v['api_seconds'] for v in buckets.values()),'sqlite_trace_events_including_internal':sum(v['trace_events_including_internal'] for v in buckets.values()),'sqlite_execute_api_calls':sum(v['execute_api_calls'] for v in buckets.values()),'sql_trace_callback_seconds_all_phases':sql['trace_callback_seconds'],'model_stages':dict(collections.Counter(x['stage'] for x in calls)),'reported_cost_usd':a['reported_cost_usd'],'budget_matches':a['budget_matches'],'source_checks':a['source_checks'],'delivered_checks':a['delivered_checks']}
 rows.append(row)
byarm={};pairs=[]
for arm in ('before','after'):
 rr=[r for r in rows if r['arm']==arm];measured=[r for r in rr if 'request_seconds' in r]
 byarm[arm]={'planned':2,'attempted':len(measured),'source_correct':sum(r['verdict']=='PASS' for r in rr),'request_seconds':sum(r['request_seconds'] for r in measured),'model_seconds':sum(r['model_seconds'] for r in measured),'physical_calls':sum(r['physical_calls'] for r in rr),'sqlite_api_seconds':sum(r['sqlite_api_seconds'] for r in measured),'sqlite_trace_events_including_internal':sum(r['sqlite_trace_events_including_internal'] for r in measured),'sqlite_execute_api_calls':sum(r['sqlite_execute_api_calls'] for r in measured),'corpus_selects':sum(r['sqlite']['corpus']['select_statements'] for r in measured),'corpus_api_seconds':sum(r['sqlite']['corpus']['api_seconds'] for r in measured)}
for case in read(DES/'cases.json'):
 b=next(r for r in rows if r['case_id']==case['id'] and r['arm']=='before');a=next(r for r in rows if r['case_id']==case['id'] and r['arm']=='after');valid=b['verdict']==a['verdict']=='PASS'
 p={'case_id':case['id'],'comparable_completed_answers':valid,'before_verdict':b['verdict'],'after_verdict':a['verdict'],'before_seconds':b.get('request_seconds'),'after_seconds':a.get('request_seconds'),'request_reduction_percent':100*(1-a['request_seconds']/b['request_seconds']) if valid else None}
 pairs.append(p)
valid_all=all(p['comparable_completed_answers'] for p in pairs)
reduction=100*(1-byarm['after']['request_seconds']/byarm['before']['request_seconds']) if valid_all else None
integrity=all(not a[k] for a in A['cells'] for k in ('source_mismatches','acl_violations','wire_mismatches','output_caps')) and all(a['budget_matches'] and not a['resource_stop'] and not a['resources'].get('oracle_driver_loaded',True) for a in A['cells'])
near=all(c['provider']=={'only':['near-ai/fp8'],'order':['near-ai/fp8'],'quantizations':['fp8'],'allow_fallbacks':False,'require_parameters':True} for c in allcalls)
received=all(c.get('actual_provider')=='Near AI' and c.get('actual_model')=='qwen/qwen3.8-27b' for c in allcalls if c.get('http_status')==200)
unknown=sum(c['status']=='unknown' for c in allcalls)
passed=bool(valid_all and reduction>0 and integrity and near and received and not unknown and ablation['passed'])
usage={'physical_calls':len(allcalls),'http200':sum(c.get('http_status')==200 for c in allcalls),'http429':sum(c.get('http_status')==429 for c in allcalls),'unknown':unknown,**{k:sum((c.get('usage') or {}).get(u,0) for c in allcalls) for k,u in [('reported_cost_usd','cost'),('reported_tokens','total_tokens'),('prompt_tokens','prompt_tokens'),('completion_tokens','completion_tokens')]}}
result={'status':'PASS' if passed else 'NOT_PASSED','cells':rows,'by_arm':byarm,'pairs':pairs,'paired_sum_reduction_percent':reduction,'usage':usage,'integrity_passed':integrity,'nearai_only_verified':near,'received_model_provider_verified':received,'active_MAIN136_unchanged':True,'source_unchanged':True,'quality_certified':False,'code_and_support_drift':False,'semantic_review':S,'sql_boundary':read(DES/'criteria.json')['measurement']['sql']+' Trace events include SQLite internal/comment-prefixed statements (OTHER), so they are not application query or network round-trip counts. Report explicit execute API counts and top-level SELECT/WITH separately; base-method calls remain traced but lack individual API timers.','limits':read(DES/'criteria.json')['comparison'],'main_wiring':'unchanged'}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['retrieval_accounting']=read(ART/'retrieval-metrics.json')
m['results'].update(status='complete',by_arm={'baseline':{'inherited_reference':'ADR-1308-experiment-v1/optimized','new_model_calls':0},**byarm},comparisons=[{'baseline':'before','candidate':'after','pairs':pairs,'sum_request_reduction_percent':reduction,'both_correct':sum(p['before_verdict']==p['after_verdict']=='PASS' for p in pairs),'candidate_only_correct':sum(p['before_verdict']!='PASS' and p['after_verdict']=='PASS' for p in pairs),'baseline_only_correct':sum(p['before_verdict']=='PASS' and p['after_verdict']!='PASS' for p in pairs),'neither_correct':sum(p['before_verdict']!='PASS' and p['after_verdict']!='PASS' for p in pairs),'causal_claim':False}],judge_disagreements=0,usage=usage,latency={'by_arm':byarm,'p95_request_seconds':None,'p95_reason':'Two known questions per arm, one run each; no reliable general tail estimate'},error_taxonomy=[{'cell':r['cell'],'type':r.get('error_taxonomy','other'),'verdict':r['verdict'],'reason':r['basis']} for r in S['rows'] if r['verdict']!='PASS']);put(ADR/'실험/manifest.json',m)
table='| 질문 | MAIN135 이전 | MAIN136 최적화 | 응답시간 감소 | 호출 이전→최적화 |\n|---|---:|---:|---:|---:|\n'
for p in pairs:
 b=next(r for r in rows if r['case_id']==p['case_id'] and r['arm']=='before');a=next(r for r in rows if r['case_id']==p['case_id'] and r['arm']=='after')
 fmt=lambda v:'미실행' if v is None else f'{v:.3f}초'
 delta='비교 불가' if p['request_reduction_percent'] is None else f'{p["request_reduction_percent"]:.1f}%'
 table+=f'| {p["case_id"]} | {fmt(p["before_seconds"])} | {fmt(p["after_seconds"])} | {delta} | {b["physical_calls"]}→{a["physical_calls"]} |\n'
headers=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[f'실제 NearAI·SQLite 전후 비교 {result["status"]}. 정답 핵심내용 이전 {byarm["before"]["source_correct"]}/2, 최적화 {byarm["after"]["source_correct"]}/2. 완료응답 합계 감소율 '+('산출불가' if reduction is None else f'{reduction:.2f}%')+'. MAIN136 유지.',
 'MAIN135와 MAIN136의 서빙 코드516/517파일을 각각 격리하고, 양쪽 모두 최종 판단/요구 검토표 두 분기를 동일하게 끈 후보를 사용했다. 원문 인용·권한·판본·저장·예산 검증은 유지했다. 후보당 제품1+pin31=32변경이며 제품 기본 설정은 변경하지 않았다.',
 '같은 두 공개 질문의 원문 기반 핵심3규칙씩 최종 전달, 원문/ACL/wire/예산 무결성을 먼저 확인한다. 완료된 같은 질문 쌍에서 요청시간이 줄어야 속도 개선으로 계산한다. 실패·미실행을 빠른 응답으로 세지 않는다. 사전 기준은 artifacts/design/criteria.json과 freeze.json.',
 '상법365 이전→최적화, 상법369 최적화→이전 순서, 각1회, 새 프로세스·새 요청기록. 프로세스 cache는 새로 시작하지만 OS/DB page cache는 초기화하지 않았다. 물리호출 요청당40/전체160, 개별180초, UNKNOWN·자원중단 뒤 재전송 없음. 모델0회 승인 재생을 양쪽 통과한 뒤 실행.',
 'Qwen3.8-27b FP8 / near-ai/fp8 only / reasoningnone / fallback0 / 출력토큰상한없음. SQLite 기존 원문 동일SHA, ontologyOFF, 원문과 질문만 제품입력. scoring-only-originals는 사후채점 전용. code/data/transport hashes 동결. SQL 관측기는 별도 실험모듈이며10조건, 자원8, 승인8 사전검사. SQL 검사 첫 기대값15 오류는 실제14문장으로 정정하고 실패원본 보존(새모델0).',
 table+'\n'+json.dumps({'by_arm':byarm,'usage':usage,'integrity':integrity},ensure_ascii=False,indent=2),
 '\n\n'.join(r['cell']+' '+r['verdict']+': '+r['basis'] for r in S['rows']),
 f'보고 사용량 {json.dumps(usage,ensure_ascii=False)}. 전체 요청은 HTTP ask 호출부터 응답까지이며 앱 준비/중복 재조회/cleanup은 제외해 별도 기록한다. 모델 시간은 순차 물리POST 구간 합계. 나머지는 모델 밖 시간이며 DB시간이 아니다. SQL은 corpus와journal을 구분해 실제trace문장 수와 execute/fetch 관측시간을 기록했다. '+result['sql_boundary'],
 'MAIN136의 SQL/반복조회/중단 및 표시 변경 전체를 비교한 결과다. 모델의 탐색 경로와 출력 길이가 달라질 수 있으므로 순수 SQL 변경만의 인과 효과로 해석하지 않는다. 출처·최종답변·모델횟수·SQL량을 함께 보고한다. 과거1307 결과는 참고이며 이번 fresh 기준선을 대체하지 않는다.',
 result['limits']+' SQLite 결과를 Oracle Gold 현장 성능이나 로더R7 성능으로 확대하지 않는다. 두 질문 각1회는 일반 정답률·성능백분위·제공자안정성 인증이 아니다. SQL API 시간은 순수 엔진CPU와 다르고 관측기 비용이 양쪽에 포함된다.',
 '실험만 수행. 활성MAIN136/Gold binding/원문/기본제공자/검토표 기본값/Oracle/DDL/현장배포/Git push/메일 변경0. 실패와 원응답은 보존한다.',
 '예약→조건동결→MAIN135/136 snapshot/freeze→preflight/승인재생→설계hash freeze→run_all.py 4셀→audit.py→audit_ablation.py→사후원문검토→ledger.py→finalize.py→runtime해시검증보관→hash/status/validate--final/graph. 새 재실행은 새ADR.']
diag=read(ART/'latency-diagnosis.json')
values[0]+=' 양쪽 완료369조는165.220→198.500초(20.14% 느림). 365조 최적화는NearAI429로 완료되지 않아 전체2질문 개선율은 산출하지 않는다.'
values[7]+='\n\n완료369조 비교: 모델57.387→80.810초(+23.423), 모델밖107.833→117.689초(+9.856), 호출8→8. 원문DB SELECT/WITH4262→3983(-6.55%), 원문SQLite API관측2.886→2.581초(-10.60%), journal포함API5.175→4.943초. SQLite내부trace이벤트와 앱execute호출은 별도집계다.'
values[8]+='\n\n후보는제371조까지 추가확보·설명했고 이전버전은제369조만 사용했다. 둘다핵심3규칙은 맞지만 탐색경로가 달라 순수SQL효과를분리한시험은아니다. 전체요청이33.279초 증가했고 관측SQL API는0.232초 줄었으므로 이번SQL개선만으로체감속도는개선되지않았다. 모델밖117.689초의함수별귀속은미계측이다. 다음진단대상은원문조회후검증·입력/스키마조립·저장과FINISH뒤감독의추가연결탐색이다.'
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if passed else 'Rejected'),front)
(ADR/'README.md').write_text('---'+front+'---\n\n# SQLite 실제 전후 속도 비교\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(headers,values),1))+'\n')
for q in m['questions']:
 p=ADR/'실험'/q['file'];case=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
 ss=[r for r in S['rows'] if r['case_id']==q['case_id']]
 stages='| arm | 문서 전체 조문 | 확보 조문 | 실제 전달 조문 |\n|---|---:|---:|---:|\n'
 for arm in ('before','after'):
  ar=next((r for r in A['cells'] if r['case_id']==q['case_id'] and r['arm']==arm),None)
  stages+=f'| {arm} | {len(A["source_article_inventory"]) if ar else 0} | {len(ar["acquired_articles"]) if ar else 0} | {len(ar["presented_articles"]) if ar else 0} |\n'
 sections=[('1. 실행 메타','run-001 / before=MAIN135 / after=MAIN136 / NearAI FP8 only / reasoning none / each once. Code, data, routing and runner hashes: ../artifacts/design/freeze.json. Actual execution state: ../artifacts/execution-progress.json.'),('2. 사용자 질문 원문',case['question']),('3. 기준답변 (채점 전용·제품 입력 비공개)','../artifacts/design/scoring-only-originals.json, SHA256 '+sha(DES/'scoring-only-originals.json')+'. Stored source version only. Core3 rules per question; added rules require actually acquired original support.'),('4. 제품 입력 원값과 회수 단계',stages+'\n전체 canonical 입력과 원문 span: ../artifacts/live/'+case['id']+'-{before,after}/canonical/*.json.gz. 실제 provider payload: 같은 셀 raw/call-*/request.json.gz. 각 파일은 전체 입력을 보존하며 요약 재구성본이 아니다. 원문/ACL/wire 검증: ../artifacts/source-wire-audit.json. 후보 before/added/discarded/after, gold gain/loss와 discard 사유는 ../artifacts/retrieval-stage-ledger.json에 정확한 좌표로 보존. Gold는 실제 선택 이후에만 결합.'),('5. 제품 호출 원문','각 셀 raw/call-*/request.json.gz와 response.json.gz가 system/user/schema/provider 전체 원응답이며 calls.json에 실제 사용량·지연·모델·제공자를 기록한다. 실제 최종 전달: response.json.gz와 answer.txt. HTTP실패 원응답도 보존.'),('6. 중간 호출 원문','각 셀 canonical/*-output.json.gz와 raw/call-*에 탐색·감독·보완·ASSESS를 단계별 보존. generations.json은 채택/거절 상태, calls.json은 물리 전송 상태다. 재조회는 duplicate.json에 추가호출 수와 동일답변 확인을 기록.'),('7. 채점 호출과 방법','새 judge 호출0. 실행 종료 후 Codex가 동결 원문과 최종 각 주장을 대조했다. 의미 판정: ../artifacts/semantic-review.json, 기계 무결성 검사: ../artifacts/source-wire-audit.json. API오류는 내용오답과 구분.'),('8. 사례 최종 판정',json.dumps(ss,ensure_ascii=False,indent=2)+'\n\n'+table)]
 p.write_text('# '+case['id']+' 전후 속도 비교\n\n'+'\n\n'.join('## '+h+'\n\n'+v for h,v in sections)+'\n')
(ADR/'실험/README.md').write_text('# SQLite 실제 전후 비교\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n\n'+table)
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-main136-sqlite-latency';OUT.mkdir(exist_ok=True)
(OUT/'실제_전후속도_비교결과.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(headers,values))+'\n')
print(json.dumps({'status':result['status'],'by_arm':byarm,'reduction_percent':reduction,'usage':usage},ensure_ascii=False))
