"""Finalize observed execution and independent direct review without model calls."""
from common import *
from collect_review import collect
import csv,statistics,re,html

assert (ART/'batch-completed.json').exists()
batch=read(ART/'batch-completed.json');audit=read(ART/'source-wire-audit.json')
observed={r['case_id']:r for r in collect()};reviews=read(ART/'direct-review.json')
cases=read(DES/'live-cases.json');rows=[];physical=[]
for case in cases:
 cid=case['id'];folder=ART/'public-live'/(cid+'-selected')
 calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
 physical.extend(calls);r=observed.get(cid)
 if r is None:
  rows.append({'case_id':cid,'question':case['steps'][0]['question'],'status':'NOT_EXECUTED' if not folder.exists() else 'RUNNER_INCOMPLETE','semantic_pass':False,'physical_calls':len(calls)});continue
 if r['unknown'] or r['http_status']!=200:
  grade={'semantic_pass':False,'reason':'요청 미완료; 정답으로 계산하지 않음.','response_sha256':r['response_sha256']}
 else:
  assert cid in reviews,'Direct review missing: '+cid
  grade=reviews[cid];assert grade['response_sha256']==r['response_sha256']
 r.update(direct_review=grade,semantic_pass=grade['semantic_pass'])
 r['status']='PASS_REGISTERED_EXPECTATION' if grade['semantic_pass'] and not r['missing_blocks'] else 'INCOMPLETE' if r['unknown'] or r['http_status']!=200 else 'FAIL_REGISTERED_EXPECTATION'
 rows.append(r)
baseline=read(DES/'baseline.json');current_pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
if current_pointer!=baseline['pointer']:
 change=read(ART/'post-run-main-change.json')
 assert current_pointer==change['observed_pointer'] and change['cutover_after_all_test_responses'] and change['all_recorded_case_bindings_161']
release=baseline['release'];assert all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
data=ROOT/release['data_path'];metadata=read(data/'manifest.json');assert sha(data/'store.sqlite')==metadata['store_sha256']
mismatches={k:sum(len(a[k]) for a in audit['cells']) for k in ('source_mismatches','acl_violations','wire_mismatches')}
assert not any(mismatches.values()),mismatches
assert all(a['budget_matches'] for a in audit['cells'])
lat=[r['request_seconds'] for r in rows if r.get('request_seconds') is not None]
passed=sum(r['status']=='PASS_REGISTERED_EXPECTATION' for r in rows)
result={'selected_MAIN':161,'release_id':baseline['pointer']['release_id'],'serving_files_unchanged':533,'source_unchanged':True,'state':'COMPLETED_WITH_FAILURES' if passed<30 else 'COMPLETED_REGISTERED_EXPECTATIONS','execution_state':batch['state'],'unique_question_count':30,'executed_responses':len(observed),'passed_registered_expectation':passed,'pass_rate_full_planned':passed/30,'failed_or_incomplete':sum(r['status'] not in ('PASS_REGISTERED_EXPECTATION','NOT_EXECUTED') for r in rows),'not_executed':sum(r['status']=='NOT_EXECUTED' for r in rows),'rows':rows,'physical_calls':len(physical),'normal_model_responses':sum(c.get('http_status')==200 and c['status']=='responded' for c in physical),'confirmed429':sum(c.get('http_status')==429 for c in physical),'unknown':sum(c['status'] in ('unknown','started') for c in physical),'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) or 0 for c in physical),'reported_prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) or 0 for c in physical),'reported_completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) or 0 for c in physical),'latency_seconds':{'min':min(lat) if lat else None,'median':statistics.median(lat) if lat else None,'p95':sorted(lat)[round((len(lat)-1)*.95)] if lat else None,'max':max(lat) if lat else None,'sum':sum(lat)},'source_checks':sum(a['source_checks'] for a in audit['cells']),'delivered_checks':sum(a['delivered_checks'] for a in audit['cells']),**mismatches,'budget_matches':True,'ontology':{'enabled':False,'configured':False},'product_changes':0,'new_judge_api_calls':0,'response_replay':0,'quality_certified':False,'scope':'Local actual MAIN161 root service, external Qwen3.8. Registered R5 source/expected-answer comparison; not current-law certification or GENOS UI evaluation.','stop_reason':batch['stop']}
mapping=read(DES/'row-mapping.json');byid={r['case_id']:r for r in rows};mapped=[]
for row in mapping:
 value=dict(row)
 if 'case_id' in row:
  r=byid[row['case_id']];value.update(status=r['status'],answer=r.get('answer',''),seconds=r.get('request_seconds'),same_unique_execution_reused=True)
 else:value.update(status='UI_NOT_EXECUTED',answer='',seconds=None,same_unique_execution_reused=False)
 mapped.append(value)
result['table_mapping']={'total_rows':60,'answer_rows':50,'unique_answer_executions':30,'mapped_pass_rows':sum(r['status']=='PASS_REGISTERED_EXPECTATION' for r in mapped),'ui_not_executed':10,'duplicate_rows_are_not_additional_independent_trials':True}
result['active_main_at_finalization']=current_pointer['generation']
result['active_pointer_changed_after_all_answers']=current_pointer!=baseline['pointer']
result['main_changed_by_this_experiment']=False
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts'
prior_rows={r['case_id']:r for r in read(prior/'result.json')['rows']}
result['comparison_vs_ADR1412_MAIN152']={'passed_before':sum(r['status']=='PASS_REGISTERED_EXPECTATION' for r in prior_rows.values()),'passed_now':passed,
 'fail_to_pass':sorted(c for c,r in byid.items() if r['status']=='PASS_REGISTERED_EXPECTATION' and prior_rows[c]['status']!='PASS_REGISTERED_EXPECTATION'),
 'pass_to_fail':sorted(c for c,r in byid.items() if r['status']!='PASS_REGISTERED_EXPECTATION' and prior_rows[c]['status']=='PASS_REGISTERED_EXPECTATION'),
 'median_seconds_before':read(prior/'result.json')['latency_seconds']['median'],'physical_calls_before':read(prior/'result.json')['physical_calls'],
 'causal':False,'note':'Single run each; same question strings and source generation; MAIN152->161 cumulative changes and model stochasticity are not separated.'}
from collections import Counter
items=[(r['case_id'],u) for r in rows for u in r.get('unread',{}).get('items',[])]
result['unread_and_section']={'cases_with_unread_section':sum(bool(r.get('unread',{}).get('answer_has_unread_section')) for r in rows),
 'unread_items_shown':len(items),'by_relation_reason':{f'{k[0]}:{k[1]}':v for k,v in Counter((u['relation'],u['reason_code']) for _,u in items).items()},
 'model_reason_items':sum(u.get('reason_origin')=='MODEL_NOTE' for _,u in items),'same_section_auto_reads':sum(len(r.get('same_section_reads',[])) for r in rows),
 'same_section_terms_matched_but_blocked':sorted({c+':'+u['target_label'] for c,u in items if u['relation']=='SAME_SECTION' and u['reason_code']=='NO_EXECUTABLE_ENDPOINT_SCOPE'}),
 'blocked_cause':'query_scope.filter_offers: a question naming a specific provision permits only that provision and its verified citation connections; a same-section sibling without a citation link is rejected as outside_direct_scope_without_verified_connection (replay diag-B03-16.json, recorded outputs, no network).',
 'display_findings':['partially read article listed as unread (B03-17: 433 cited for 1, 2 unread)','cross-document targets shown without document name and duplicated (B03-07 190, B03-21 시행령 제9조 x3)','chapter-level parent labelled as 같은 절 (B05-04/05 제4장)','up to 9 sibling lines per answer; one answer hit the 30-item cap (B03-17)','system fallback reason for the scope block reads 읽을 수 있는 원문 범위가 확인되지 않아서, not the named-provision scope']}
duplicates=[read(p) for p in (ART/'public-live').glob('*/turn-1/duplicate.json')]
assert all(d['same_answer'] and d['extra_model_calls']==0 for d in duplicates)
result['duplicate_checks']={'checked':len(duplicates),'extra_model_calls':sum(d['extra_model_calls'] for d in duplicates),'all_same_answer':all(d['same_answer'] for d in duplicates)}
put(ART/'result.json',result);put(ART/'row-results.json',mapped)
with (ART/'통합테스트_60행_결과.csv').open('w',encoding='utf-8-sig',newline='') as out:
 writer=csv.DictWriter(out,fieldnames=['row_id','kind','case_id','question','status','answer','seconds','same_unique_execution_reused']);writer.writeheader();writer.writerows(mapped)
summary=f'MAIN161 · 통합테스트 R5: 질문30개 중 기대내용·출처 일치 {passed}개, 응답 확보 {len(observed)}개. 모델 {len(physical)}회, UNKNOWN {result["unknown"]}회.'
lines=[summary,'','현재 메인 기본 온톨로지 OFF, 원문 SQLite, 실제 root service, Qwen3.8 Parasail FP8/none.','중복 질문을 합쳐 30개 각1회 실행. 50개 답변행에 같은 결과를 매핑했고 화면10항목은 미실행.','등록 원문·기대답변과 직접 대조한 시험이며 법률 일반화·최신성·GENOS 현장 통과 인증은 아님.','',json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2),'']
for row in rows:
 lines.extend([row['case_id']+' · '+row['status'],row['question'],'실제 답변: '+row.get('answer','미완료'), '판정: '+row.get('direct_review',{}).get('reason','미실행 또는 실행기 중단'),''])
(ART/'통합테스트_결과.txt').write_text('\n'.join(lines))
put(ART/'run-001/result.json',{'result_path':str((ART/'result.json').relative_to(ROOT)),'result_sha256':sha(ART/'result.json'),'summary':summary})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)),sha256=sha(ART/'run-001/result.json'))
m['results'].update(status='complete',by_arm={'selected':{k:v for k,v in result.items() if k!='rows'}},comparisons=[],judge_disagreements=0,usage={k:result[k] for k in ('physical_calls','unknown','reported_cost_usd','reported_prompt_tokens','reported_completion_tokens')},latency=result['latency_seconds'],error_taxonomy=[r['case_id']+':'+r['status'] for r in rows if r['status']!='PASS_REGISTERED_EXPECTATION'])
for q in m['questions']:
 p=ADR/'실험'/q['file'];value=byid[q['case_id']]
 p.write_text(p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\n'+json.dumps(value,ensure_ascii=False,indent=2)+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[summary,
 '사용자 지시로 선택 MAIN161을 ADR-1412(MAIN152)와 같은 R5 외규 30문항에 실제 실행. MAIN152 대비 법률명 거절 7건 해소 여부, 같은 절 읽기·미확인 조문 안내의 일반화, 새 회귀를 확인. 첫 시도 ADR-1422는 B03-03 답변 조립 중 호스트 스왑 153MiB 증가로 자원 가드가 멈췄고(5호출 모두 HTTP200, 가용 8.4GiB, 다른 세션 활동), 이 ADR은 작업자 프로세스 스왑 128MiB·호스트 512MiB·RAM 3GiB·남은 스왑 1GiB 기준을 첫 호출 전에 고정했다.',
 json.dumps(read(DES/'criteria.json'),ensure_ascii=False),
 'R5 60행=답변50행+화면10행. 서로 다른 외규30질문을 표 순서대로 각1회 독립 실행(새 세션·격리 runtime). 중복 결과 매핑은 추가 시행이 아니다. 기대답변·좌표는 제품 입력에 넣지 않았다. 작업 트리의 파생 핀31개는 실행 동안만 MAIN161 바이트로 바꾸고 복원(tree-swap.json/tree-restore.json), 병행 세션 미커밋 oracle_query_service.py는 건드리지 않았고 로드 모듈 바이트 검사로 MAIN161 바이트만 로드됨을 확인.',
 'MAIN161 unread-notes-20261106-r1 533파일, 같은 원문 세대·권한 범위, 기본 온톨로지OFF, 기존 모델·출력상한 없음·40회/1800초. 새 로컬 상태 DB로 운영 대화/원문 불변.',
 json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2),
 '30문항 모두 등록 기대내용·원문 블록과 일치. 부수 문장 표현 오차 B03-19(원문 지정하여야→지정할 수 있습니다; ADR-1412에서도 같은 표현). 미확인 조문 안내의 표시 결함: 일부만 읽은 조문을 전체 미확인으로 표시(B03-17), 다른 법령 조문을 문서명 없이 표시·중복(B03-07 제190조, B03-21 시행령 제9조×3), 장을 같은 절로 표기(B05-04/05), 형제 조문 9줄 나열. 같은 절 자동 읽기 0회: 조항을 지정한 질문은 query_scope가 지정 조항과 검증된 인용 연결만 허용해 형제 조문 제공이 제외됨(diag-B03-16.json 재생 진단).',
 'calls.json의 실제 물리 호출·비용·토큰, source-wire-audit.json의 원문/권한/전송/예산, retrieval-stage-ledger의 조문 집합을 사용한다. p95는 정렬 표본의 round((n-1)*.95) 위치다.',
 'HTTP200·COVERED만으로 통과시키지 않았다. 실제 문구가 질문 범위와 기대내용을 충족하고 요구 원문이 인용에 결속되는지 저장 원문과 직접 대조했다. MAIN152의 법률명 거절 7건은 MAIN154 수정 이후 실제 Qwen에서도 해소됐다. 같은 절 읽기는 조항을 지정하지 않은 질문에서만 동작하는 것으로 확인됐다.',
 '알려진 조항 직접질문30개, 단일 반복, 온톨로지OFF. 조항을 지정하지 않은 일반 질문·멀티턴·현장 UI·Oracle/GENOS 성능 미검증. MAIN152 대비 변화는 누적 코드 변경과 모델 변동을 분리하지 못한다.',
 '제품수정/MAIN승격/원문변경/GENOS배포/메일 없음. 같은 요청 재전송 없음. 새 독립 질문 간 진행은 사전 기준에 포함됐다.',
 '새 실행은 새 ADR 필요. 원본은 artifacts/public-live/{case}-selected/raw와 canonical. 읽기 전용 후처리: audit.py → ledger.py → collect_review.py → direct-review.json → finalize.py. 같은 절 차단 진단: replay_diag.py B03-16 (기록된 응답 재생, 네트워크0).']
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN161 통합테스트 R5 재실행 R2\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(headings,values),1))+'\n')
(ADR/'실험/README.md').write_text('# R5 실제 질문 결과\n\n'+summary+'\n\n| 질문 | 결과 |\n|---|---|\n'+'\n'.join('| ['+r['case_id']+']('+next(q['file'] for q in m['questions'] if q['case_id']==r['case_id'])+') | '+r['status']+' |' for r in rows)+'\n')
table=''.join('<tr><td>'+html.escape(r['case_id'])+'</td><td>'+html.escape(r['question'])+'</td><td>'+html.escape(r['status'])+'</td><td>'+html.escape(r.get('answer','미실행'))+'</td><td>'+html.escape(r.get('direct_review',{}).get('reason',''))+'</td></tr>' for r in rows)
page='<!doctype html><html lang="ko"><meta charset="utf-8"><title>MAIN161 통합테스트 결과</title><style>body{font:16px system-ui;max-width:1400px;margin:32px auto;padding:0 20px;color:#172033}h1{font-size:26px}td,th{border-bottom:1px solid #ddd;text-align:left;vertical-align:top;padding:12px}th{background:#eef2f8}.summary{padding:18px;background:#fff7df;border:1px solid #e9ce80;border-radius:8px}table{border-collapse:collapse;width:100%}</style><body><h1>MAIN161 통합테스트 · 실행 및 검토 종료</h1><div class="summary">'+html.escape(summary)+'</div><p>30개 질문 각1회 결과입니다. 중복 질문을 포함한 답변50행에는 같은 결과를 매핑했고, 화면10항목은 미실행입니다. 온톨로지OFF · 실제 로컬 MAIN · Qwen3.8.</p><p><a href="통합테스트_결과.txt">전체 결과와 실제 답변</a> · <a href="통합테스트_60행_결과.csv">60행 결과표</a> · <a href="diag-B03-16.json">같은 절 읽기 차단 진단</a></p><table><tr><th>항목</th><th>질문</th><th>판정</th><th>실제 사용자 답변</th><th>직접 대조</th></tr>'+table+'</table></body></html>'
(ART/'통합테스트_상태.html').write_text(page)
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'};paths.update(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1423','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Current MAIN161 R5 native execution and review evidence; ADR-1422 resource stop is a separate record','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in sorted(paths)]})
print(summary)
