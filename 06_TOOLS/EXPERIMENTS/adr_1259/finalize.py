from common import *
import datetime,collections
v=read(O/'live/result.json');wire=read(O/'live/wire.json');v.update(reported_cost_usd=sum((r.get('usage') or {}).get('cost',0) for r in wire),known_complete_responses=len(wire),normalizations_persisted=2,readback=read(O/'readback.json'),synthetic_contracts=83,native_synthetic_contracts=9,actual_compile=False,actual_approval=False,actual_rag=False)
put(O/'result.json',v)
sqls=json.loads(gzip.decompress((O/'live/source-sql.json.gz').read_bytes()));counts=collections.Counter(sqls)
put(O/'query-repetition.json',{'total':len(sqls),'distinct':len(counts),'top':[{'sha256':hashlib.sha256(s.encode()).hexdigest(),'count':n,'sql':s} for s,n in counts.most_common(12)],'root_cause':'Automatic literal fragments use token fallback (따라/한다 among this sample), restoring16/12 full glossary candidates repeatedly; only3 were referenced by first model. No legal stopword exception proposed.'})
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',arm_ids=['typed'],sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','historical_only':True,'source':'ADR1255 connected'},'typed':{**v,'status':'complete','outcome':'REJECTED_PROJECTION_DEADLINE'}},usage={'physical_calls':len(wire),'reported_cost_usd':v['reported_cost_usd'],'unknown_external':0},latency={'seconds':v['seconds']},error_taxonomy=['Repeated full glossary hydration from automatic token-fallback candidates exhausted600second projection budget'])
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':len(wire)}]
reason='RAG retrieval not reached; four source units frozen explicitly; literal glossary candidates16/12 and all queries retained in actual inputs'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
p=A/'README.md';s=p.read_text().replace('status: Proposed','status: Rejected')
s=s.replace('실행 전 준비 중이며 MAIN은129를 유지한다.','전체 미통과이며 MAIN은129를 유지한다.')
s=s.replace('실제1259 실행 전. 별도 모의 검사 결과는 artifacts의 contracts/native-contracts 기록에 남긴다.','실제4회/stop4/외부UNKNOWN0·644.182초·보고 비용 $'+format(v['reported_cost_usd'],'.8f')+'. 기록2/변경2/문장2/정규화2를 실제 Oracle에 저장했다. 새 프로세스에서 원기록2·정규화2·탐색항목2·문장2의 hash/body를 다시 확인했다. 이유·목적4필드 NOT_RECORDED 유지. 원문 분석 호출 전600초 projection 예산 종료로 컴파일/승인/게시/RAG0. 실제 결과는 [result](artifacts/run-001/result.json). 후보 모의83·native9통과; 서로 다른 검사이나 법률 품질 표본 아님.')
s=s.replace('실제 결과를 받은 뒤 원자료와 함께 기록한다. 준비 실패와 외부 모델 실패를 구분한다.','일반 문장 조각의 token fallback이 상법3개 외 따라/한다 등의 부분일치 후보를 가져와 정규화별16/12개 전체 상세를 반복 복원했다. 실제 source SQL1334/agent198/work248. source 분석 전 송신0의 BUDGET_EXHAUSTED는 외부 UNKNOWN이 아니다. 앱 모의검사는 초기 pytest import/path/pin 불일치와 제한 환경의 TestClient 내부통신 대기를 보존한 뒤 정확 후보 및 허용된 로컬 실행환경으로92개 통과했다. 재조회 첫 검사는 wire 필드명으로 canonical 값을 읽어 KeyError가 났으며 정정 후 새 readback2 통과; DB/model 변경0.')
s=s.replace('아직 결과 없음. 모의 검사와 실제 전체 성공을 합쳐 주장하지 않는다.','변경안 형식·참조 수정은 실제2회 모두 최초 응답으로 통과했다. 기록 없는 이유/목적을 생성하지 않은 정규화2개도 보존했다. 전체 실패 원인은 다량의 용어 후보 상세를 반복 검증하는 비용이다. 시간 한도나 원문 검사를 느슨하게 바꾸지 않고 자동 문자조각 조회와 명시적 탐색을 분리하는 후속 가설을 세운다. 통과한 앞단을 전체 성공으로 표현하지 않는다.')
p.write_text(s)
q=A/'실험/질문-001-workspace-public-001.md'
heads=['## 1. 실행 메타','## 2. 사용자 질문 원문','## 3. 기준답변 — 채점 전용, 제품 입력 비공개','## 4. 제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정']
texts=['ADR1259/typed/run-001/rev002508파일. 실제4회 응답 exact.','실제 모델·Oracle에서 기록 축적→컴파일·승인·RAG 연결 검증.','정답을 제품 입력에 주입하지 않음. 사전 전체gate 모두 통과 필요.','[원기록](../artifacts/design/records.json), [원문](../artifacts/design/originals.json), [동결](../artifacts/design/freeze.json).','원문4개 고정. 실제 용어 후보16/12와 상세는 각 input에 전량 보존; 전체 RAG 미도달.', '\n'.join(f'- [{i} 실제요청](../artifacts/run-001/live/wire/{i:03d}-request.json.gz) · [응답](../artifacts/run-001/live/wire/{i:03d}-response.json.gz) · [원래 입력/스키마](../artifacts/run-001/live/authoring/{i:03d}-input.json.gz)' for i in range(1,5)), 'WIKI_PROPOSE2 + NORMALIZE2; 모두 최초 응답. SOURCE_ANALYSIS/누적/컴파일/최종RAG0.','모델 judge0. 정확 인용과 원기록 보존·서버 계약·실제 Oracle 재조회 검사, 법률 품질 인증 아님.','전체Rejected. 입력 형식 오류 수정은 실제 앞단에서 통과했으나 조회 지연으로 전체 완료 실패. [전체결과](../artifacts/run-001/result.json), [SQL반복](../artifacts/run-001/query-repetition.json).']
q.write_text('# 실제 Oracle 작업공간 시험\n\n'+'\n\n'.join(h+'\n\n'+t for h,t in zip(heads,texts))+'\n')
(A/'실험/README.md').write_text('# 시험 결과\n\n[질문/원자료](질문-001-workspace-public-001.md), [전체결과](../artifacts/run-001/result.json).\n')
files=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design, actual Oracle/model evidence, preserved preparation failures and synthetic contracts','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1259','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files})
print('Finalized failed trial; no MAIN mutation')
