from common import *
import datetime,collections
v=read(O/'live/result.json');wire=read(O/'live/wire.json');v.update(reported_success_cost_usd=sum((r.get('usage') or {}).get('cost',0) for r in wire),known_complete_responses=sum(r.get('http_status')==200 for r in wire),known_http429=sum(r.get('http_status')==429 for r in wire),normalizations_persisted=2,readback=read(O/'readback.json'),synthetic_contracts=88,native_synthetic_contracts=9,actual_compile=False,actual_knowledge_approval=False,actual_rag=False)
capacity=[read_line for read_line in map(json.loads,(O/'live/capacity-samples.jsonl').read_text().splitlines())]
v['last_capacity_sample']=capacity[-1];v['source_sql_trace_count']=len(json.loads(gzip.decompress((O/'live/source-sql.json.gz').read_bytes())))
put(O/'result.json',v)
ledger=[]
for n in (3,4):
 x=json.loads(gzip.decompress((O/f'live/authoring/{n:03d}-input.json.gz').read_bytes()))['context'];g=x['glossary_candidates']
 ledger.append({'normalization_input':n,'raw_payload_hash':x['raw']['payload_hash'],'candidate_count':len(g['candidates']),'concept_ids':[c['concept_id'] for c in g['candidates']],'queries':g['queries'],'unsearched':g['unsearched'],'policy':g['query_policy'],'not_article_root_candidates':True})
put(O/'glossary-candidate-ledger.json',{'accounting_unit':'raw_payload_hash + concept_id','actual_inputs':ledger,'read_only_retained_body_check':read(A/'artifacts/oracle-literal-check/result.json'),'article_retrieval_changed':False,'normalization_glossary_candidate_policy_changed':True,'gold_recall':None,'not_quality_score':True})
m=read(A/'실험/manifest.json');put(O/'manifest-before-accounting-classification-correction.json',m)
m['runs'][0].update(status='complete',arm_ids=['literal'],sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','historical_only':True,'source':'ADR1259 typed'},'literal':{**v,'status':'complete','outcome':'REJECTED_BOTH_APPROVED_PROVIDERS_HTTP429'}},usage={'physical_calls':len(wire),'reported_success_cost_usd':v['reported_success_cost_usd'],'unknown_external':0,'known_http429':2,'provider_switches':1},latency={'seconds':v['seconds']},error_taxonomy=['Both approved providers returned known HTTP429; one authorized switch used; no further dispatch'])
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':len(wire)}]
reason='Article-root RAG retrieval unchanged and never reached. Normalization glossary candidate policy changed and is fully measured separately in artifacts/run-001/glossary-candidate-ledger.json using raw_payload_hash + concept_id; these lexical nodes are not article-root coordinates. Initial changed=true classification and correction preserved; no acceptance criterion changed.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason)
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
p=A/'README.md';s=p.read_text().replace('status: Proposed','status: Rejected')
s=s.replace('수정 후보의 실제 전체 검증 준비 중.','외부 공급자 제한으로 실제 전체 검증 미통과.')
s=s.replace('실제 전체 실행 전. 모의 계약88개 통과.','실제6물리/정상4/확인된429 2/외부UNKNOWN0·289.739초. Parasail 정상2→429→승인된Near AI전환1→정규화 정상2→Near AI429로 종료. 보고된 성공응답 비용 $'+format(v['reported_success_cost_usd'],'.8f')+'. 새모델0의 추가 재시도 없이 중단. 축적2·문장2·정규화2·새 프로세스 Oracle8객체 재조회 통과. source SQL494/agent206/work248. 원문 분석 첫 전송은429로 거절되어 컴파일/지식승인/게시/RAG0. 모의 계약88개와native API9개 통과.')
s=s.replace('전체 결과를 받은 뒤 실제 원자료로 기록한다. 초기 준비/연결 오류도 별도 보존한다.','[실제 결과](artifacts/run-001/result.json), [입출력](실험/질문-001-workspace-literal-001.md). 용어 조회 범위 수정 뒤600초 projection 예산 내 원문 분석 요청까지 도달했지만 HTTP429로 중단됐다. 두 실행의 모델 지연·공급자 조건이 달라 전체 성능 개선율로 해석하지 않는다. 기존 서버 검증·시간/호출 제한은 동일하다. 기록과 실패 job HTTP_REJECTED를 수정하거나 재시작하지 않았다.')
s=s.replace('불필요한 자동 의미 확장을 줄이는 가설이며 모의/원소 검사를 실제 전체 성공으로 확대하지 않는다.','자동 조각에서 미요청 token 확장의 상세 복원을 줄이면서 실제 모델 참조와 기존 원문 내용을 유지함을 확인했다. 정상 정규화2개까지 저장됐으며 전체 성공은 미확인이다. 외부429가 다음 단계를 차단했다. 공급자 전환 한도를 늘리거나 다른 모델을 사용하지 않았다.')
s=s.replace('원문/RAG 회수 엔진은 그대로다.','원문/RAG 회수 엔진은 그대로다. 초기 manifest의 retrieval.changed=true는 용어 후보 변경을 조문 회수로 분류한 표기였다. 이전 manifest를 보존하고 article-root 회수는 unchanged로 정정했으며, 용어 후보 변경 자체는 [별도 원장](artifacts/run-001/glossary-candidate-ledger.json)에 실제ID/개수/보류/queries로 기록했다. 기준·실패 판정은 변경하지 않았다.')
s=s.replace('전체 조건 통과 전 MAIN 반영0.','최종 MAIN129 유지·반영0. 마지막 쓰기 전 SIDDA176,750,592바이트/기존300MiB의56.1875%,270MiB하드상한 유지. 원기록/모델응답/기존Gold 게시3건 보존.')
p.write_text(s)
q=A/'실험/질문-001-workspace-literal-001.md';heads=['## 1. 실행 메타','## 2. 사용자 질문 원문','## 3. 기준답변 — 채점 전용, 제품 입력 비공개','## 4. 제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정']
texts=['ADR1260/literal/run-001/rev001508파일. 실제6회 요청/응답 exact.','실제 모델·Oracle로 기록 축적→컴파일·승인·RAG 검증. SIDDA 기록 보존 후 진행.','제품에 정답 주입0. 사전 전체gate 모두 통과 필요.','[원기록](../artifacts/design/records.json), [현재원문](../artifacts/design/originals.json), [동결](../artifacts/design/freeze.json).','RAG 회수 미도달. [용어 후보 원장](../artifacts/run-001/glossary-candidate-ledger.json). article-root와 concept ID를 혼동하지 않는다.', '\n'.join(f'- [{i} 실제요청](../artifacts/run-001/live/wire/{i:03d}-request.json.gz) · [응답](../artifacts/run-001/live/wire/{i:03d}-response.json.gz)' for i in range(1,7)), 'WIKI_PROPOSE2/정규화2완료. 정규화 첫429 뒤 동일모델 승인공급자전환1. SOURCE_ANALYSIS는다른공급자429로실패; 컴파일/최종RAG0. 원래 prompt/context/schema는 live/authoring에 전량 gzip보존.','모델 judge0. 서버계약·정확원문·Oracle재조회 기술검사이며 법률 품질 인증이 아니다.','전체Rejected. 두공급자429 뒤추가모델0, UNKNOWN0. [전체결과](../artifacts/run-001/result.json).']
q.write_text('# 실제 Oracle 자동 용어 조회 수정 시험\n\n'+'\n\n'.join(h+'\n\n'+t for h,t in zip(heads,texts))+'\n')
(A/'실험/README.md').write_text('# 시험 결과\n\n[질문/원자료](질문-001-workspace-literal-001.md), [전체결과](../artifacts/run-001/result.json).\n')
files=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design, actual Oracle/model evidence, explicit glossary accounting and synthetic contracts','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1260','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files})
print('Recorded provider rejection; MAIN unchanged')
