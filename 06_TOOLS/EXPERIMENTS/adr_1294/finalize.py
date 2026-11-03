from common import *
import re
rows=[read(d/'result.json') for d in sorted((ART/'live').iterdir()) if (d/'result.json').exists()]
calls=[x for d in (ART/'live').iterdir() for x in read(d/'calls.json')]
result={'status':'NOT_PASSED','performance_improvement':'NOT_EVALUABLE','cells':rows,'execution':read(ART/'execution-progress.json'),
 'physical_calls':len(calls),'unknown':sum(x['status']=='unknown' for x in calls),'reported_cost_usd':sum((x.get('usage') or {}).get('cost',0) for x in calls),
 'reported_tokens':sum((x.get('usage') or {}).get('total_tokens',0) for x in calls),
 'failure':'Both365arms reached actual vector/source processing then experiment exact-question grant rejected host-derived task/facts. Remaining369cells stopped. Product/source validation not bypassed. No usable final answer.',
 'vector_preflight':'Actual local bge-m3 model loaded and Oracle vector search returned rows with no external model call. Original1293virtualmemoryfailure was harness caused.',
 'resource_note':'Preflight ru_maxrss4290348KiB (~4.09GiB) exceeded nominal4GiB but1secondcurrentRSSsamples remained below4GiB; no resource stop. Do not claim continuous4GiBcompliance.',
 'product_changes':0,'quality_certified':False}
if (ART/'supplement/result.json').exists():result['supplement']={k:v for k,v in read(ART/'supplement/result.json').items() if k not in ('reports','origins')}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');put(ART/'preregistered-manifest-before-final-accounting.json',m)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
reason='No completed paired answer or source presentation: experiment authorization rejected validated host task/facts. Original measured-stage plan preserved; null final retrieval metrics are unavailable, not zero. Raw source acquisitions and attempts retained.'
m['design']['retrieval_stage_plan']['stages_by_arm']={};m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason);m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=reason)
m['results'].update(status='complete',by_arm={a:{'cells':[r for r in rows if r['arm']==a]} for a in ('baseline','ontology-on')},comparisons=[{'result':'NOT_EVALUABLE','reason':reason}],judge_disagreements=0,usage={k:result[k] for k in ('physical_calls','reported_cost_usd','reported_tokens')},latency={'request_seconds':sum(r['request_seconds'] for r in rows)},error_taxonomy=[{'type':'EXPERIMENT_DERIVED_QUESTION_GRANT','count':2}]);put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=['온톨로지 성능 비교 미평가. 시험기 파생질문 승인 오류로365두셀 실패·369미실행. 원본 보존.',
 '완료1293은 시험기 가상주소6GiB로 모델매핑 실패. 이번에는 그 제한만 제거하고 실제자원 감시를 유지했다.',
 'artifacts/design/criteria.json. 완성된2쌍/원문품질 보존 후 시간·호출·토큰10%향상. 실패시간으로 개선율 계산 금지.',
 'MAIN133/513파일동일, 원문Oracle읽기전용·상태SQLite, 두질문교차순서각1회. 남은셀은 첫시험기오류를 확인한 뒤전송차단. ON첫호출은차단전에시작.',
 'Qwen3.8-27b·Parasail우선·출력상한없음. design/freeze.json에 코드·전송기·질문 고정.',json.dumps(result,ensure_ascii=False,indent=2),
 '실제검색을통과했으나 UnifiedRag.open이기존제품계약대로task+facts질문으로파생한뒤 시험기authorize의원문질문완전일치조건에거절됨. 제품오류로판정하지않음. 부모1293대사감독오류는별개이며재실행없음.',
 f'실제{len(calls)}회/보고${result["reported_cost_usd"]:.8f}/UNKNOWN{result["unknown"]}, 최종답변0. 상세시간·SQL은각result와sql-statements. 회수성능원장은미평가이고원계획별도보존.',
 '메모리매핑 문제해소는확인. 온톨로지최종효율은아직판정불가. 승인확인은고정사용자요청에서제품이검증해파생한task/facts만허용해야하며전체질문제한을해제하면안된다.',
 'preflight의ru_maxrss4.09GiB와초당RSS표본을구분.4GiB이하상시준수주장없음. 합성추가검사는자연모델품질이아님.',
 '제품/MAIN/Gold설정/운영DB·DDL·게시0. 다음새ADR에서실험승인연결만수정하고5GiBRSS/가용RAM3GiB/스왑증가128MiB기준을사전명시한다. 원래응답/질문/상태재작성없음.',
 'prepare→vectorpreflight→freeze→run_all→supplement→finalize. 실제실행디렉터리재사용금지. 재현자료artifacts/live;실패와중단보존.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 로컬 온톨로지 시험1294\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
for q in m['questions']:
 case=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
 sections=[('실행 메타','run-001/baseline,ontology-on; design/freeze.json'),('사용자 질문 원문',case['question']),('기준답변 — 채점 전용, 제품 입력 비공개','design/scoring-only-originals.json. 외부채점0.'),('제품 입력을 구성한 원값','design/cases.json·live/canonical.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n미완료비교로최종성능원장미평가;원계획및실제원문기록보존.'),('제품 모델 호출 — run·arm별 실제 원문','live/<case>-<arm>/raw/call-*/request.json.gz·response.json.gz; calls.json'),('중간 LLM 호출 — router/compiler/verifier/repair','365각request-entry1회후시험기승인거절,369미실행.'),('채점 호출과 반복 판정','모델채점/재실행0; 실패기록확인.'),('사례 최종 판정',json.dumps([r for r in rows if r['case_id']==case['id']],ensure_ascii=False) or '미실행')]
 (ADR/'실험'/q['file']).write_text('# '+case['id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 기록\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved probe record','contains_raw_prompts_and_outputs':'raw' in p.parts or 'canonical' in p.parts} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json']
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1294','files':files})
print(json.dumps(result,ensure_ascii=False)[:900])
