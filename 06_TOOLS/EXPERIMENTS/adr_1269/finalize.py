from common import *
import re
control=read(ART/'live-runner-summary.json');cells=[]
for case in read(DES/'cases.json'):
 name=case['id'];P=ART/'live'/name
 if not (P/'result.json').exists():
  cells.append({'case_id':name,'status':'NOT_RUN','reason':control.get('stop')});continue
 r=read(P/'result.json');a=read(P/'audit.json');injections=r.get('injections',[])
 integrity=None
 if injections:
  receipt=read(P/'injection/receipt.json');original=read(P/'injection/provider-original.json.gz');changed=read(P/'injection/delivered-response.json.gz');raw=read(P/'raw'/f"call-{receipt['physical_call']:03d}"/'response.json.gz')
  integrity={'provider_original_preserved':original['body_json']==raw,'injected_reply_is_different':original!=changed,'hash_matches_receipt':original['body_sha256']==receipt['original_sha256'] and changed['body_sha256']==receipt['injected_sha256']}
  assert all(integrity.values())
 checks={'injected_once':len(injections)==1,'answer_200':r.get('http_status')==200 and a['answer_chars']>0,'repost_same_answer':bool(a['duplicate'] and a['duplicate']['http_status']==200 and a['duplicate']['same_answer'] and a['duplicate']['extra_model_calls']==0),'no_unknown':a['unknown']==0,'source_and_wire_valid':not(a['source_mismatches'] or a['acl_violations'] or a['wire_mismatches']),'fixed_code':not(a['changed_release_files'] or a['changed_inputs']) and a['active_pointer_unchanged'],'native_budget_matches_physical':a['physical_budget_matches'],'no_harness_exception':not r.get('error_type')}
 status='PASS' if all(checks.values()) else 'NOT_TESTED_NO_INJECTION' if not injections else 'FAIL'
 row={'case_id':name,'status':status,'http_status':r.get('http_status'),'seconds':r['seconds'],'injections':injections,'injection_integrity':integrity,'checks':checks,'metrics':{k:a[k] for k in ('physical_calls','unknown','post_unknown_calls','reported_cost_usd','reported_input_tokens','reported_output_tokens','source_checks','delivered_checks','source_mismatches','acl_violations','wire_mismatches','duplicate','resources')},'audit_path':str((P/'audit.json').relative_to(ROOT))}
 cells.append(row)
passed=sum(c['status']=='PASS' for c in cells);total_calls=sum(c.get('metrics',{}).get('physical_calls',0) for c in cells);cost=sum(c.get('metrics',{}).get('reported_cost_usd',0) for c in cells)
result={'status':'PASS' if passed==3 else 'REJECTED','fault_cases_passed':passed,'cells':cells,'physical_model_calls':total_calls,'reported_cost_usd':cost,'real_model':'qwen/qwen3.8-27b','all_corrections_from_actual_qwen':True,'synthetic_originals':True,'full_current_product_profile':True,'main_promoted':False,'legal_quality_certified':False,'comparison_limit':'Three fixed in-sample cases, not a production error-rate or legal-quality benchmark. Synthetic sources differ from ADR1266/1268 real public corpus. No automatic replay of UNKNOWN requests.'}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True},'repaired':result},judge_disagreements=0,usage={'physical_model_calls':total_calls,'reported_cost_usd':cost,'unknown':sum(c.get('metrics',{}).get('unknown',0) for c in cells)},latency={'per_case_seconds':{c['case_id']:c.get('seconds') for c in cells}},error_taxonomy=[{'case_id':c['case_id'],'status':c['status'],'http_status':c.get('http_status')} for c in cells if c['status']!='PASS'])
summary=f"오류주입 복구 {passed}/3, 실제 모델 {total_calls}호출, 보고 비용 ${cost:.8f}. "+'; '.join(c['case_id']+': '+c['status']+' / HTTP'+str(c.get('http_status')) for c in cells)+'. MAIN130 및 작업 제품 변경0. 전체프로필·합성원문·실제Qwen을 구분한다.'
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,case,cell in zip(m['questions'],read(DES/'cases.json'),cells):
 name=q['case_id'];vals=['run-001/repaired; full native API, no service wrapper or production deployment',case['request']['json']['question'],'합성원문 정합성·저장·무추가호출 검사. 법률 기준답변/평가모델0.','[사전 기준](../artifacts/design/criteria.json) · [원문/동결](../artifacts/design/source.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n회수율 비교 아님. 원문 대조는 각 감사에 기록.',f'[원시 전송/응답](../artifacts/live/{name}/raw/) · [canonical](../artifacts/live/{name}/canonical/)','제안 오류는 실험에서 주입한 것으로, 모델이 자연스럽게 낸 오류가 아니다. 주입0은 미검증으로 판정.',f"[감사](../artifacts/live/{name}/audit.json) · [재조회](../artifacts/live/{name}/duplicate.json)",json.dumps(cell,ensure_ascii=False,indent=2)]
 p=ADR/'실험'/q['file'];p.write_text('# '+name+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[summary,'큰 원문 실험에서 응답 기한 종료로 오류주입에 도달하지 못했다. 작은 고정 원문에서 현재 전체 루프를 실제 Qwen으로 확인한다.','[동결 기준](artifacts/design/criteria.json). 주입1/HTTP200/같은답변무추가호출/원문·전송일치가 모두 필요.','중복선택·충돌선택·잘린JSON, 각 독립 runtime·고정 질문1회.','518파일과 고정 합성3조문. 원문·질문·정책·전송기·실행기 해시 고정.','[결과](artifacts/run-001/result.json).','주입이 일어나지 않으면 성공답변도 복구 성공으로 세지 않는다. 최종 검토 거절과 외부 결과불명도 별도 보존.','사례별 실제 전송/usage/경계시간은 결과와 원본에 기록. 보고비용과 미보고 사용량을 구분.','합성원문에서 실제 모델과 런타임의 오류 피드백·보완·재사용 동작을 확인한 범위만 주장.','실제Oracle/NFS/GENOS·부하/동시실모델·법률품질 인증 아님.','제품 및 MAIN을 바꾸지 않는다. 완료 셀/실패 원본 보존, 같은 실패 자동 재전송 없음.','prepare → freeze → live --preflight → run_live → audit → finalize. 완료 셀 재실행 금지.']
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Accepted' if passed==3 else 'Rejected'),front);p.write_text('---'+front+'---\n\n# '+m['adr_id']+' 실제 Qwen 선택 오류 복구\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
(ADR/'실험/README.md').write_text('# 실험 인덱스\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']}): {c['status']}" for q,c in zip(m['questions'],cells))+'\n')
p=ART/'manifest.json';v=read(p);v['files']=[{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen synthetic source/design, actual model wire, injection receipt and native-loop audit','contains_raw_prompts_and_outputs':any(t in str(x) for t in ('/raw/','/canonical/','/experiment-client/','/injection/'))} for x in ART.rglob('*') if x.is_file() and x!=p and '/runtime/' not in str(x) and '/states/' not in str(x)];p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print(summary)
