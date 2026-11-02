"""Summarize recorded evidence only; no model imports or dispatch."""
from common import *
import re,statistics
P=ART/'live/review-whatif';a=read(P/'audit.json');r=read(P/'result.json');f=read(DES/'freeze.json')
responses=a['responses'];initial=responses.get('initial',{});sem=responses.get('semantic',{})
def condition(label):
 rows=responses.get(label,{}).get('comparison',{}).get('comparisons',[])
 return next((row['after']['status'] for row in rows if row['node_id']=='N2'),None)
checks={'initial_explanation':initial.get('http_status')==200 and initial.get('explanation_hash_verified') is True,
 'ontology_actual_delivery':initial.get('ontology_status')=='RESPONSE_RECEIVED' and bool(initial.get('ontology_bundles')),
 'numeric_false_true':condition('high')=='FALSE' and condition('low')=='TRUE',
 'numeric_zero_calls':all(any(t['label']==label and t['http_status']==200 and t['physical_calls']==0 for t in a['turns']) for label in ('view','high','low','rule')),
 'numeric_keeps_unconfirmed':all(responses.get(label,{}).get('comparison',{}).get('legal_conclusion')=='UNCONFIRMED' for label in ('high','low','rule')),
 'semantic_branch_response':sem.get('http_status')==200 and bool(sem.get('hypothetical')) and (r.get('branch') or {}).get('different_goal') is True,
 'actual_baseline_preserved':read(P/'baseline-preservation-inspection.json')['passed'],
 'duplicate_zero':bool(a['turns']) and all(t.get('duplicate',{}).get('extra_model_calls')==0 for t in a['turns']),
 'original_wire_integrity':not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches','changed_release_files','changed_inputs','output_cap_fields')),
 'budgets_exact':a['new_physical_budget_matches'],'unknown_zero':a['unknown']==0,'no_resource_stop':not a['resources']['resource_stop'],
 'active_unchanged':a['active_pointer_unchanged'],'cleanup':a['cleanup_completed']}
semantic=read(P/'semantic-review.json') if (P/'semantic-review.json').exists() else {'status':'NOT_REACHED'}
checks['approval_not_invented']=semantic.get('approval_not_invented') is True
checks['semantic_applies_changed_value']=semantic.get('semantic_applies_changed_value') is True
passed=all(checks.values());status='PASS' if passed else 'NOT_PASSED'
result={'status':status,'checks':checks,'candidate_revision':f['candidate_revision'],'physical_calls':a['physical_calls'],'inherited_model_calls':3,'turn_calls':a['turn_calls'],
 'unknown':a['unknown'],'post_unknown_calls':a['post_unknown_calls'],'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls'],
 'elapsed_seconds':r['seconds'],'model_seconds':a['model_seconds'],'source_checks':a['source_checks'],'delivered_checks':a['delivered_checks'],
 'source_mismatches':len(a['source_mismatches']),'wire_mismatches':len(a['wire_mismatches']),'acl_violations':len(a['acl_violations']),
 'turns':a['turns'],'semantic_observation':semantic,'quality_certified':False,'main_changed':False,'oracle_calls':0,'not_tested':r.get('not_tested',[])+['explicit rereview: initial response did not fail'],
 'limitations':['One synthetic in-sample conversation; no representative legal-quality or causal improvement estimate','Ontology is predefined test input, not real-model ontology authoring','Actual SQLite/native API only; Oracle/NFS/GENOS not tested','Original model outputs unmodified; optional adoption may remain unrecorded']}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True},'verified':result},judge_disagreements=0,
 usage={'physical_model_calls':a['physical_calls'],'reported_cost_usd':a['reported_cost_usd'],'input_tokens':a['reported_input_tokens'],'output_tokens':a['reported_output_tokens']},
 latency={'elapsed_seconds':r['seconds'],'model_seconds':a['model_seconds']},error_taxonomy=[{'type':'UNKNOWN','count':a['unknown']},{'type':'FAILED_CHECK','checks':[k for k,v in checks.items() if not v]}])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 f'실제 Qwen 기술 실험 {status}. MAIN132·운영 원문·Oracle 유지. [상세 결과](artifacts/run-001/result.json). 법률 품질 인증 아님.',
 '확보된 원문을 다시 요청하는 표시, 최종 검토 실패와 사실 부족의 혼동, 온톨로지 채택과 숫자 가정의 연결을 작업 코드에 구현한 뒤 실제 모델과 같은 API에서 확인한다.',
 '[사전 기준](artifacts/design/criteria.json). 모델 응답은 바꾸지 않는다. 자료/검토 분리, 전달/채택 구분, 숫자 비교 무호출, 승인 미확인 유지, 불변 기준·분기와 중복 방지·원문/권한/해시를 각각 확인한다.',
 '기존 실제 답변 재조회(재생성 금지) → 검토 미완료일 때 한 번만 명시 재검토 → 상태 조회 → cost 고액/저액 비교 → 규칙 한도 가정 → cost 저액 의미 분기 → 기준 사건 조회. UNKNOWN 또는 공급자 실패 뒤 추가 모델0. 실행되지 않은 단계는 NOT_TESTED다.',
 'Qwen qwen/qwen3.8-27b, 동결 정책·전송기, 합성 규정3조/별도 SQLite. 제품522파일을 현재 작업 코드에서 격리동결했다. 온톨로지는 제1조 원문과 금액·승인 두 요건에 결속한 사전작성 입력이며 정상 draft/review/publication을 거쳤다. 모델 온톨로지 저작 성공으로 확대하지 않는다.',
 f'상태 {status}, 실제 {a["physical_calls"]}호출, UNKNOWN {a["unknown"]}, 턴별 {a["turn_calls"]}. 체크별 결과·HTTP·중복 호출 수는 [결과](artifacts/run-001/result.json).',
 '미통과 조건: '+', '.join(k for k,v in checks.items() if not v)+'. 가정 cost=500000이 전달됐으나 작업 비용=1500000원과 원래 질문이 그대로 남아 모델은 원래 금액으로 불가 판단했다. 실제 기준 사건은 보존됐고 live의 false는 요청별 id/query_id 비교 차이였음을 별도 원장 대조로 구분했다. 모델 자연 응답과 실행기 준비 실패를 구분하고 원본 raw/canonical/저널을 보존했다. 의미 해석은 semantic-review.json의 범위에 한정한다.',
 f'전체 {r["seconds"]:.3f}초, 모델 경계 {a["model_seconds"]:.3f}초, 보고 ${a["reported_cost_usd"]:.8f}, 사용량 미보고 {a["missing_usage_calls"]}. 원문 {a["source_checks"]}/전달 {a["delivered_checks"]} 대조, 원문·wire·ACL 불일치 {len(a["source_mismatches"])}/{len(a["wire_mismatches"])}/{len(a["acl_violations"])}. 여러 단계 모델지연을 제품 성능 개선율로 해석하지 않는다.',
 '숫자 조건의 변화와 법률 결론은 분리한다. 승인 여부가 미확인인 경우 금액 TRUE만으로 시작 가능을 확정하지 않는다. 준비된 온톨로지, 실제 모델 입력, 모델의 명시적 사용 보고를 각각 확인한다.',
 '합성 원문·in-sample·단일 대화. 법률 정답률·운영 지연·동시 부하·Oracle/NFS·GENOS 내부 모델은 미검증이다. 과거 ADR1277은 다른 질문/설정으로 인과 비교 대상이 아니다.',
 'MAIN132·Gold·운영 데이터 변경0. 이번 모델 실행 후 제품 수정·동일 셀 재실행0. 실패한 데이터·응답·완료 기록은 그대로 보존한다.',
 'prepare.py → freeze.py → live.py review-whatif --preflight → live.py review-whatif 단1회 → audit.py review-whatif 새프로세스 → finalize.py. 완료 dispatch가 있어 live 재실행 거절. 과거 입력과 원시는 gzip/참조 해시로 재현한다.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Accepted' if passed else 'Rejected'),front)
p.write_text('---'+front+'---\n\n# ADR1279 검토 설명·가정 비교 실제 실험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
q=ADR/'실험/질문-001-review-whatif.md';question=read(DES/'cases.json')[0]['request']['json']['question']
sections=[('실행 메타','run-001/verified/review-whatif, Qwen3.8. 시각·코드·해시는 ../artifacts/design/freeze.json와 live/review-whatif/dispatch.json. 실제 native API, 기준 모델 새 호출0.'),('사용자 질문 원문',question),('기준답변 — 채점 전용, 제품 입력 비공개','별도 법률 기준답변·judge0. 기술 기준은 ../artifacts/design/criteria.json. 온톨로지와 원문은 사전작성 입력이며 답안 키가 아니다.'),('제품 입력을 구성한 원값','원문 ../artifacts/design/source.json, 온톨로지 ../artifacts/design/ontology-input.json, 첫 질문 cases.json, 실제 후속 *-request.json. 전체 canonical/*.json.gz 및 raw/call-*/request.json.gz 보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n회수 효과 비교가 아닌 기능 검사. stage_ledger not_applicable. 실제 원문·전달/ACL은 audit.json.gz와 states/*.json.gz로 대조한다.'),('제품 모델 호출 — run·arm별 실제 원문','../artifacts/live/review-whatif/raw/call-*/request.json.gz, response.json.gz, finished.json에 exact 원문·usage·지연 보존. 모델 출력 주입·재작성0.'),('중간 LLM 호출 — router/compiler/verifier/repair','제품 분류·탐색·최종 검토·보완도 같은 raw/canonical에 전량 보존. calls.json/generations.json에서 순서·단계·턴 확인.'),('채점 호출과 반복 판정','평가모델0, fresh-process audit.py 대조. 동일 operation 재조회는 새 확률 반복이 아니다. 의미 판단은 별도 사람 검토 기록이며 품질 인증 아님.'),('사례 최종 판정','../artifacts/run-001/result.json checks와 ../README.md. 실행 실패·미도달을 통과로 고치지 않는다.')]
q.write_text('# 실제 Qwen 검토·가정 시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 검증 기록\n\n[질문](질문-001-review-whatif.md) · [manifest](manifest.json) · [결정](../README.md) · [원시 산출물](../artifacts/manifest.json)\n')
p=ART/'manifest.json';am=read(p);files=[x for x in ART.rglob('*') if x.is_file() and x!=p and '/runtime/' not in str(x) and '/__pycache__/' not in str(x)]
am['files']=[{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen design and preserved experiment evidence','contains_raw_prompts_and_outputs':any(t in str(x) for t in ('/raw/','/canonical/'))} for x in sorted(files)];p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
