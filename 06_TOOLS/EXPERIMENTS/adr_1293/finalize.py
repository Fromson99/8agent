"""Close the failed probe without reclassifying failed endpoints as passed."""
from common import *
import re
rows=[];calls=[];errors=[]
for d in sorted((ART/'live').iterdir()):
 r=read(d/'result.json');r['cell']=d.name;rows.append(r)
 calls.extend([{**c,'cell':d.name} for c in read(d/'calls.json')])
for p in ART.glob('*.log'):
 for line in p.read_text().splitlines():
  try:x=json.loads(line)
  except ValueError:continue
  e=x.get('error_diagnostics',{}).get('diagnostics',{})
  if e:errors.append({'log':p.name,'error_type':e.get('error_type'),'message':e.get('error_message'),'location':e.get('location')})
result={'status':'NOT_PASSED','performance_improvement':'NOT_EVALUABLE','cells':rows,'errors':errors,
 'physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls),
 'http200':sum(c.get('http_status')==200 for c in calls),'http429':sum(c.get('http_status')==429 for c in calls),
 'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),
 'reported_tokens':sum((c.get('usage') or {}).get('total_tokens',0) for c in calls),
 'model_seconds':sum(c['seconds'] for c in calls),'request_seconds':sum(r['request_seconds'] for r in rows),
 'local_checks':{'real_api_http_checks':13,'contracts_passed':66,'contracts_failed':4,'oracle_readonly_checks':9},
 'interpretation':'Three public cells failed loading embedding weights under the experiment-only RLIMIT_AS 6GiB. One public cell exhausted known429 providers. Comparison failed native supervisor authorization after2 accepted model responses; no comparison table. No complete pair or legal answer. Keyword endpoint returned navigation metadata and zero candidate articles.',
 'main_product_oracle_write_changes':0,'quality_certified':False}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');put(ART/'preregistered-manifest-before-final-accounting.json',m)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
reason='The planned retrieval-performance comparison was aborted before any completed source acquisition/presentation endpoint: three embedding mapping failures, one429, one comparison supervisor rejection. Original stage plan and raw attempts are retained; null metrics mean unavailable, never zero recall or successful filtering.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason)
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=reason)
m['results'].update(status='complete',by_arm={a:{'cells':[r for r in rows if r['arm']==a],'completed_answers':0} for a in ('baseline','ontology-on')},comparisons=[{'result':'NOT_EVALUABLE','reason':reason}],judge_disagreements=0,usage={k:result[k] for k in ('physical_calls','reported_cost_usd','reported_tokens')},latency={k:result[k] for k in ('request_seconds','model_seconds')},error_taxonomy=errors)
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=['전체 미통과. 대사표 실제 생성 실패, 온톨로지 성능 향상 판정 불가. 기본 목록22개에 성공/실패/모의확인을 구분한다.',
 '사용자가 기본20기능과 대사표·온톨로지 성능 비교를 요청했다. 시험 시작 시 선택MAIN133/513파일을 고정했다. 병행1292 작업은 포함하지 않는다.',
 '[사전 기준](artifacts/design/criteria.json): 두 완성된 ON/OFF 쌍의 품질 보존 후 시간/호출/토큰 중10% 이상 절감. 실패 쌍이 있으면 향상 주장 금지.',
 '공개365/369의 OFF/ON 각1회, 합성 내외규 대사1회. fresh process/SQLite, 원문Oracle read-only. RLIMIT_AS6GiB는 시험기 설정이며 실제RSS4GiB와 다르다. 이 제한으로3개 셀이 모델 파일 매핑 실패해 별도 새ADR에서 설정을 수정해야 한다.',
 'Qwen3.8-27b, Parasail FP8 우선/기존429 NearAI 전환, 출력상한 없음. 후보·코드·입력·전송기는 design/freeze.json. 실제 법령의 현행성 평가 없음.',
 json.dumps(result,ensure_ascii=False,indent=2),
 '365 OFF/ON 및369 ON: MemoryError; 369 OFF: Parasail429→NearAI429/API503. 대사: workflow-intake와 navigation200 후 native action lacks current supervisor authorization/API500. STOP_EXTERNAL 작성 전 모든 셀이 이미 끝났으며 STOP 때문에 실패한 것이 아니다. 초기pytest hook/build-data 준비 실패도 원본보존. 계약4실패는 기존fixture/HTML문자열 기대 불일치로 보이며 추가 검증 전 제품 통과로 세지 않는다.',
 f'실제{len(calls)}물리, HTTP200 {result["http200"]}/429 {result["http429"]}/UNKNOWN {result["unknown"]}, 보고${result["reported_cost_usd"]:.8f}, 보고토큰{result["reported_tokens"]}, 요청합{result["request_seconds"]:.3f}초. 성공응답 보고비용이며429사용량 없음. 회수계획 미완료이므로 원래계획을 보존하고 최종회수지표는 미평가로 처리했다.',
 '기본 읽기 API13개의HTTP검사 통과. 키워드 검색은 관련조문0/탐색시작점2이므로 원문검색 성공으로 확대하지 않는다. 계약66통과/4실패, Oracle 게시온톨로지 읽기9검사 통과는 모델효율 향상 증거가 아니다.',
 '소수사례·합성대사·SQLite상태저장. 현장GENOS/NFS/Oracle기록 전체, 실제브라우저 조작, 부하, 법률품질 미인증. 실패시간을 개선율로 계산하지 않는다.',
 '제품/MAIN/Gold설정/Oracle내용·DDL/게시 변경0. 이전실패불변, 결과 후 셀 재실행0. 다음 시험은 새ADR에서 가상주소제한만 제거하고 실제RAM/스왑 감시 유지.',
 '06_TOOLS/EXPERIMENTS/adr_1293/{prepare,checks,build_data,freeze,run_all,finalize}.py. 실제 호출은 재실행하지 않는다. 기록 재분석만 가능. 전체입출력과SQLite는 artifacts/live에 보존.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 로컬 통합 검증1293\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
for q in m['questions']:
 case=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
 sections=[('실행 메타','run-001, design/freeze.json; fresh process; 모델전송 원문은 live/<case>-<arm>/raw.'),('사용자 질문 원문',case['question']),('기준답변 — 채점 전용, 제품 입력 비공개','design/scoring-only-originals.json 및criteria.json. 외부채점0.'),('제품 입력을 구성한 원값','design/cases.json; canonical/*.json.gz.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n예정된 비교는 미완료. 최종회수지표 미평가. 원래계획은 artifacts/preregistered-manifest-before-final-accounting.json 보존.'),('제품 모델 호출 — run·arm별 실제 원문','artifacts/live/'+case['id']+'-*/raw/call-*/request.json.gz·response.json.gz. calls.json에 실제공급자/토큰/시간.'),('중간 LLM 호출 — router/compiler/verifier/repair','generations.json/canonical과calls.json. 정상응답5와4292, 추가채점0.'),('채점 호출과 반복 판정','외부채점/재실행0. API/실제오류 수동판독; 미완료를 법률오답으로 집계하지 않음.'),('사례 최종 판정',json.dumps([r for r in rows if r['case_id']==case['id']],ensure_ascii=False,indent=2))]
 (ADR/'실험'/q['file']).write_text('# '+case['id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 기록\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
print(json.dumps({k:result[k] for k in ('status','physical_calls','http200','http429','reported_cost_usd')},ensure_ascii=False))
