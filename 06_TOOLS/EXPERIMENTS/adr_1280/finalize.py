"""Finalize recorded evidence only; never dispatch a model."""
from common import *
import re,statistics
P=ART/'live/review-whatif';a=read(P/'audit.json');r=read(P/'result.json');f=read(DES/'freeze.json');semantic=read(P/'semantic-review.json')
def condition(label):
 return next((x['after']['status'] for x in a['responses'].get(label,{}).get('comparison',{}).get('comparisons',[]) if x['node_id']=='N2'),None)
checks={'baseline_response':a['responses'].get('initial',{}).get('claims',0)>0,
 'numeric_general_inputs':condition('low')=='TRUE' and condition('high')=='FALSE' and condition('rule')=='TRUE',
 'numeric_no_calls':all(any(t['label']==label and t['http_status']==200 and t['physical_calls']==0 for t in a['turns']) for label in ('high','low','rule')),
 'three_semantic_branches':len(r.get('branches',{}))==3 and all(x['different_goal'] and x['hypothetical'] and x['claims']>0 for x in r.get('branches',{}).values()),
 'semantic_changed_values_and_unknowns':semantic['all_passed'],
 'baseline_preserved':r.get('baseline_preserved') is True,
 'duplicate_no_calls':all(t.get('duplicate',{}).get('extra_model_calls')==0 for t in a['turns']),
 'input_source_integrity':not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches','changed_release_files','changed_inputs','output_cap_fields')),
 'budget_matches':a['physical_budget_matches'],'unknown_zero':a['unknown']==0,
 'resource_safe':not a['resources']['resource_stop'],'main_unchanged':a['active_pointer_unchanged'],'cleanup':a['cleanup_completed']}
result={'status':'PASS' if all(checks.values()) else 'NOT_PASSED','checks':checks,'physical_calls':a['physical_calls'],'reported_cost_usd':a['reported_cost_usd'],
 'unknown':a['unknown'],'post_unknown_calls':a['post_unknown_calls'],'seconds':r['seconds'],'turn_calls':a['turn_calls'],'semantic':semantic,
 'source_checks':a['source_checks'],'delivered_checks':a['delivered_checks'],'source_mismatches':len(a['source_mismatches']),'wire_mismatches':len(a['wire_mismatches']),'acl_violations':len(a['acl_violations']),
 'candidate_revision':f['candidate_revision'],'quality_certified':False,'main_changed':False,'oracle_calls':0,'not_tested':r.get('not_tested',[]),
 'limits':'New amounts in one repaired synthetic workflow; not a representative legal quality test or causal A/B. Prepared ontology reused; no model ontology authoring.'}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True},'verified':result},judge_disagreements=0,
 usage={'physical_model_calls':a['physical_calls'],'reported_cost_usd':a['reported_cost_usd'],'input_tokens':a['reported_input_tokens'],'output_tokens':a['reported_output_tokens']},
 latency={'elapsed_seconds':r['seconds'],'model_seconds':a['model_seconds']},error_taxonomy=[{'type':'FAILED_CHECK','checks':[k for k,v in checks.items() if not v]}])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[f'실제 Qwen 검증 {result["status"]}. MAIN132 유지. [상세](artifacts/run-001/result.json). 인샘플·품질 미인증.',
 'ADR1279의 별칭 사실 중복과 이전 금액 재사용을 수정한 작업 코드524파일을 격리 동결했다. 부모의 실패 기록은 보존한다.',
 '[동결 기준](artifacts/design/criteria.json). 변경값 적용·승인 미확인·기준 사건 보존·정확 전송·중복 요청 모델0을 분리 확인한다.',
 '새1380000원 기준 사건 → 원문 상태/숫자 비교 → 독립735000원/1725000원/규칙2450000원 의미 분기 → 원래 사건 조회. 각 요청은 재조회 모델0. 사용자 지시로 실모델 수행; 추가 승인 단계 없음.',
 '동결524파일·native API·SQLite·합성3조문·기존 원문 결속 승인 온톨로지. Qwen3.8/Parasail 기본과 확정429 허용 전환 정책은 동결 정책 그대로. 모델 출력 주입·재작성0. 원문과 판정 키는 분리.',
 json.dumps(result,ensure_ascii=False,indent=2),
 '자연 응답의 의미와 구조화 결과를 [검토](artifacts/live/review-whatif/semantic-review.json)에 기록했다. 소스 전용 응답이나 미도달 분기는 의미 성공으로 세지 않는다.',
 f'실제 {a["physical_calls"]}호출 / 보고 ${a["reported_cost_usd"]:.8f} / {r["seconds"]:.3f}초. 사용량 미보고 {a["missing_usage_calls"]}. 원문{a["source_checks"]}/전달{a["delivered_checks"]}; 불일치 원문/ACL/wire {len(a["source_mismatches"])}/{len(a["acl_violations"])}/{len(a["wire_mismatches"])}. 회수 개선율 비교 아님.',
 '특정 사례의 금액·필드명 분기는 핵심4모듈 AST 검사에서 발견되지 않았다. 별도 변수명/한도 변경4개 결정적 검사도 통과. 고정된 타입/단위/검토 안전 규칙과 일반 안내문은 존재한다. [코드 대조](artifacts/hardcoding-audit.json).',
 '같은 합성 규정의 새 금액으로 일반 법률 품질을 인증하지 않는다. 숫자 검증은 자연어 모든 의미의 증명이 아니다. Oracle/NFS/GENOS·실제 동시 부하 미검증. 부모와 신규 실행은 확률/입력이 달라 인과 A/B 점수를 만들지 않았다.',
 '운영·MAIN·Gold·기존 원문 변경0. 제품 코드 수정0. 최종 실패 이후 같은 셀 재실행0. 새모델 결과를 기존 완료 ADR에 덮어쓰지 않는다.',
 'prepare.py → freeze.py → live.py review-whatif --preflight → live.py review-whatif 1회 → audit.py review-whatif → 의미 검토 → finalize.py → 표준 hash/validate/graph. 모든 산출물 hash는 artifacts/manifest.json.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if all(checks.values()) else 'Rejected'),front)
p.write_text('---'+front+'---\n\n# ADR1280 명시적 가정 사실 연결 실제 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
q=ADR/'실험/질문-001-review-whatif.md';question=read(DES/'cases.json')[0]['request']['json']['question']
sections=[('실행 메타','run-001/verified/review-whatif. 후보·정책·입력은 ../artifacts/design/freeze.json. 실제 시각과 입력/출력은 live/review-whatif/raw와 canonical.'),('사용자 질문 원문',question),('기준답변 — 채점 전용, 제품 입력 비공개','별도 법률 기준답변/평가모델0. 기술 기대조건 ../artifacts/design/criteria.json; 공개 합성 규정과 승인 온톨로지만 제품에 제공.'),('제품 입력을 구성한 원값','source.json/ontology-input.json/cases.json 및 canonical/*.json.gz, raw/call-*/request.json.gz에 원문·전체 system/user/schema.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n회수 효과 변경 비교 없음. stage_ledger not_applicable; 확보·전달 좌표와 ACL 대조는 audit.json.gz.'),('제품 모델 호출 — run·arm별 실제 원문','raw/call-*/request.json.gz, response.json.gz, finished.json. 전체 provider 원응답/사용량/지연 보존, 응답 주입0.'),('중간 LLM 호출 — router/compiler/verifier/repair','모든 단계는 calls.json/generations.json, canonical과 raw에 연결. 실제 ASSESS 보완도 그대로 기록.'),('채점 호출과 반복 판정','평가모델0. 새 프로세스 무결성 대조와 별도 의미검토. 동일 요청 재조회는 확률 반복이 아니다.'),('사례 최종 판정','../artifacts/run-001/result.json. 실제 의미검토는 ../artifacts/live/review-whatif/semantic-review.json. 미실행·실패 그대로 유지.')]
q.write_text('# 실제 Qwen 가정 분기 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 검증 기록\n\n[질문](질문-001-review-whatif.md) · [manifest](manifest.json) · [결정](../README.md)\n')
p=ART/'manifest.json';am=read(p);am['files']=[{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen design and actual experiment evidence','contains_raw_prompts_and_outputs':any(t in str(x) for t in ('/raw/','/canonical/'))} for x in sorted(ART.rglob('*')) if x.is_file() and x!=p and '/runtime/' not in str(x) and '/__pycache__/' not in str(x)];p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
