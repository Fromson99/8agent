from common import *
import re
P=ART/'live/review-followup';a=read(P/'audit.json');r=read(P/'result.json');f=read(DES/'freeze.json')
first=a.get('first_turn_review') or {};follow=a.get('followup') or {}
safe=not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches','changed_release_files','changed_inputs','output_cap_fields'))
checks={'first_source_only':a['http_status']==200 and a['first_turn_claims']==0 and first.get('stop_reason')=='ASSESSMENT_CONTRACT_UNRESOLVED',
 'two_injections':len(r['injections'])==2,'first_repost_zero':(a.get('duplicate') or {}).get('extra_model_calls')==0,
 'followup_answer':follow.get('http_status')==200 and follow.get('claims',0)>0,
 'same_case':follow.get('same_goal') is True and follow.get('same_investigation') is True,
 'followup_repost_zero':(follow.get('duplicate') or {}).get('extra_model_calls')==0,
 'source_wire_integrity':safe,'budgets_exact':a['physical_budget_matches'],'unknown_zero':a['unknown']==0,
 'no_resource_stop':not a['resources']['resource_stop'],'cleanup':a['cleanup_completed']}
passed=all(checks.values())
result={'status':'PASS' if passed else 'NOT_PASSED','checks':checks,'case_id':'review-followup','candidate_revision':f['candidate_revision'],
 'physical_calls':a['physical_calls'],'turn_calls':a['turn_calls'],'unknown':a['unknown'],'post_unknown_calls':a['post_unknown_calls'],
 'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls'],'elapsed_seconds':r['seconds'],
 'source_checks':a['source_checks'],'delivered_checks':a['delivered_checks'],'source_mismatches':len(a['source_mismatches']),
 'wire_mismatches':len(a['wire_mismatches']),'acl_violations':len(a['acl_violations']),'audit':{'path':str((P/'audit.json').relative_to(ROOT)),'sha256':sha(P/'audit.json')},
 'quality_certified':False,'main_changed':False,'oracle_calls':0,'new_calls_after_terminal':0,
 'limitations':['One in-sample synthetic-original fault injection, not broad legal quality or causal call-reduction proof','First turn source-only output is not an accepted legal conclusion','Provider UNKNOWN internal cause is not resolved','No actual Oracle/GENOS/NFS verification']}
put(RUN/'result.json',result)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 ('고정2턴 실제 기술 시험 통과.' if passed else '고정2턴 실제 시험 미통과. 실패/미확인을 보존하고 같은 셀을 재실행하지 않았다.')+' MAIN131과 운영 데이터 유지. 코드 기술 검증1274 및 MAIN반영1276과 분리한다.',
 '최종 모델 검토가 반복해서 계약을 어기면 기존422로 끝났다. 원문만 명시적으로 반환한 뒤 같은 사건에 사용자 사실을 보태 실제 모델이 재판단하는 경로를 확인한다.',
 '[기준](artifacts/design/criteria.json): 실제 최초 ASSESS/보완2응답의 needs만 비워 원문응답을 유도하고, 고정 후속 사실에 대한 지원된 주장·같은 사건·재전송0·원문/권한/예산 동일을 요구한다. 미충족은 성공으로 세지 않는다.',
 '한 대화의 고정 첫 질문과 사실 보완1회. 공급자 원래 응답과 시험이 바꾼 응답을 모두 보존한다. 두번째 턴은 변경하지 않는다. UNKNOWN/429 소진/첫 복구 미충족이면 후속 전송을 중단한다.',
 'Qwen qwen/qwen3.8-27b, 현재 전송/공급자 정책, 합성 규정3조, SQLite 원문/기록, 현재 전체제품518파일 rev-002. 사용자 외부전송 승인이 있으며 현장 법률자료·Oracle는 사용하지 않았다. 전송기와 요청은 동결 해시로 결속했다.',
 f'[결과](artifacts/run-001/result.json): {result["status"]}, 실제{a["physical_calls"]}회/턴별{a["turn_calls"]}, UNKNOWN{a["unknown"]}, 첫HTTP{a["http_status"]}, 후속HTTP{follow.get("http_status")}, 후속주장{follow.get("claims",0)}. 첫 재조회{a.get("duplicate")}, 후속 재조회{follow.get("duplicate")}.',
 '시험 주입과 모델 자연 오류를 구분한다. first/second canonical·raw·주입 원본·저장 journal을 보존했다. 세부 통과/실패는 checks에 각각 기록하며 HTTP200만으로 최종 법률 판단 통과로 확대하지 않는다. 준비 중 API 응답 경로 참조와 timeout 표식 수정은 모델0회 때 새동결로 기록했다.',
 f'실제{r["seconds"]:.3f}초, 모델통신{a["model_seconds"]:.3f}초, 보고비용${a["reported_cost_usd"]:.8f}; 사용량 미보고{a["missing_usage_calls"]}회. 원문{a["source_checks"]}/전달{a["delivered_checks"]}대조, 불일치{len(a["source_mismatches"])}·권한위반{len(a["acl_violations"])}·wire차이{len(a["wire_mismatches"])}. 전체 서비스 성능 개선율 아님.',
 '복구 성공은 사용자 사실을 반영한 검증된 후속 주장과 기록 보존까지 충족할 때만 말한다. 단지 오류 문구를 감추거나 검토 실패 제안을 게시하는 방식이 아니다. 호출 수는 실제 단계별 기록이며 최적 호출 수를 인증하지 않는다.',
 '한 합성 대화·in-sample 주입. 실제법률 품질·Oracle·GENOS·NFS·부하 미검증. 공급자 내부 timeout 해결을 주장하지 않는다. 원래의 과거 실패ADR을 수정하지 않았다.',
 '이 실험은 운영 MAIN 변경0. 기술 코드의 명시 사용자 반영은1276 별도 감사에서 수행한다. 원문·기록·이전MAIN131은 보존한다.',
 'live.py review-followup --preflight → live.py review-followup 단1회 → audit.py review-followup 새프로세스 → finalize.py. 완료dispatch가 존재하므로 같은 live 셀 재실행은 거절한다. 재검토는 저장된 증거로 수행한다.'
]
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True},'verified':result},judge_disagreements=0,usage={'physical_model_calls':a['physical_calls'],'reported_cost_usd':a['reported_cost_usd']},latency={'elapsed_seconds':r['seconds']},error_taxonomy=[{'type':'INJECTED_NEED_REVIEW_OMISSION','count':len(r['injections'])},{'type':'UNKNOWN','count':a['unknown']}])
put(ADR/'실험/manifest.json',m)
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Accepted' if passed else 'Rejected'),front)
p.write_text('---'+front+'---\n\n# ADR1275 Qwen 검토 복구·후속 사실\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
q=ADR/'실험/질문-001-review-followup.md';case=read(DES/'cases.json')[0]
q.write_text('# 고정2턴 실제 복구 시험\n\n첫 질문: '+case['request']['json']['question']+'\n\n후속: '+case['followup']['json']['question']+'\n\n[실제 결과와 미확인](../README.md). 원래 모델 원문과 주입 응답을 구분하며 법률품질 기준답변이 아니다.\n')
(ADR/'실험/README.md').write_text('# 실제2턴 검증\n\n[고정 질문](질문-001-review-followup.md) · [실행 manifest](manifest.json) · [결정](../README.md) · [산출물](../artifacts/manifest.json)\n')
p=ART/'manifest.json';am=read(p);files=[x for x in ART.rglob('*') if x.is_file() and x!=p and '/runtime/' not in str(x) and '/__pycache__/' not in str(x)]
am['files']=[{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen input and preserved original model/transport/audit evidence','contains_raw_prompts_and_outputs':any(t in str(x) for t in ('/raw/','/canonical/','/injection/'))} for x in sorted(files)];p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print(result)
