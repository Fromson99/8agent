from common import *
import datetime
v=read(O/'live/result.json');wire=read(O/'live/wire.json');v['reported_cost_usd']=sum((r.get('usage') or {}).get('cost',0) for r in wire);v['actual_known_responses']=2;v['actual_transport_unknown']=0;v['stored_job_may_mark_unknown']='The runner usage archive failure occurs after second complete provider response. Do not rewrite stored job or retry it.';v['regression_contracts']=read(A/'artifacts/contracts.json')['passed'];put(O/'result.json',v)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',arm_ids=['connected'],sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','historical_only':True,'selected':'MAIN129'},'connected':{**v,'status':'complete','outcome':'REJECTED_BEFORE_WORKSPACE_COMMIT'}},usage={'physical_calls':2,'reported_cost_usd':v['reported_cost_usd'],'unknown_external':0},latency={'seconds':v['seconds']},error_taxonomy=['open operation values and ambiguous raw/source/object references','research usage archive collision after complete second response'])
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':2}]
reason='Stopped in first workspace proposal before any compiled publication or RAG retrieval; selected four source units frozen explicitly'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=['전체미통과/Rejected. 첫원기록Oracle저장·중복억제 후실제위키제안2회에서중단. 컴파일/승인/RAG0·MAIN129불변.',
 '기존자유작업공간의본문저장Oracle누락·Oracle빈목록cursor를격리후보에서수정했다. 모델operation.value는개방object여서실제형식·참조를제약하지못했다.',
 '[호출전고정기준](artifacts/design/criteria.json), [동결507파일rev003](artifacts/design/freeze.json). 원문→실제2기록축적→컴파일→위임승인→실제RAG전달/답변→철회검증/회귀전체통과필요.',
 '기존MAIN129+작업중위키/1251변경을보존한별도507파일. 신규OracleWorkStore/config/목록수정만후보에추가. 독립정답/법률품질실험아님. 이전선택MAIN과의새모델A/B없음.',
 '[원기록선정](artifacts/design/records.json): 실패1235의실제claim norm문자열2개정확subtree. Oracle현재상법369원문4단위171자. 실제Qwen3.8/ParasailFP8, 모델혼합0. 원문31SQL사전읽기·부모/현재작업hash보존.',
 '[전체결과](artifacts/run-001/result.json). 실전송2/정상stop2/UNKNOWN0·188.596초. 첫원기록Oracle저장/중복억제, Workspace의미변경commit0. 73계약통과는전체실모델성공아님.',
 '첫응답18operation: 한글/공백handle·중복handle·문장을CREATE_ENTRY로생성·원문S ID를origin_refs로사용·source_basis객체형·좌표불일치. 검증기의origin guard거절. 두번째보완도같은형태. 단두번째는실행기usage.json무손실압축기의기존파일충돌로제품검증전에중단. 두wire원본보존. 저장jobUNKNOWN을외부UNKNOWN으로해석하지않는다. 사전RecordSQL16000상한오류는모델/DB쓰기0의준비실패로보존후10000정정.',
 f"실제비용보고${v['reported_cost_usd']:.8f}, source47/agent52/work44 SQL. 준비/저장별경계이며전체SQL CPU아님. 새임베딩0. 공간은별도1257에서195.25MiB회수; 이모델결과에합산안함.",
 '느슨한모델operation계약과실행기기록오류를실제호출로확인했다. 원문/권한검사를완화하지않고모델입력명세와정확quote복원을후속후보에서수정한다.',
 '실제컴파일/승인/게시/전체RAG미도달. 실제Oracle원문과구조화본문저장은연결했으나전단계품질/회귀/성능인증아님. NFS미설정상세captureUNCONFIGURED; 연구raw는별도gzip보존·현장NFS/GENOS/ORDS미검증.',
 'MAIN승격0. 실패scope/2응답/이전ADR보존. 같은job/UNKNOWN재전송0. 수정과새판정은새ADR에서동결한다. SIDDA270MiB상한유지, 원문/Gold기존게시내용불변.',
 'live.py의동결실행영수증과gzip입출력을읽는다. 동일실패시험을그대로재실행하지않는다. 후속은새ADR.']
p=A/'README.md';front=p.read_text().split('---',2)[1].replace('status: Proposed','status: Rejected');p.write_text('---'+front+'---\n\n# 실제 작업공간 Oracle 시험 미통과\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,vals),1))+'\n')
q=A/'실험/질문-001-workspace-public-001.md';heads=['## 1. 실행 메타','## 2. 사용자 질문 원문','## 3. 기준답변 — 채점 전용, 제품 입력 비공개','## 4. 제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정'];vals=['ADR1255/connected/run-001/507파일rev003.','실제모델·Oracle로기록축적→컴파일·승인·RAG검증.','별도정답주입없음. 호출전criteria의전체gate로판정.','[실제원기록](../artifacts/design/records.json), [현재원문](../artifacts/design/originals.json).','정해진원문4단위;RAG검색미도달.', '[실제wire1](../artifacts/run-001/live/wire/001-request.json.gz), [응답1](../artifacts/run-001/live/wire/001-response.json.gz), [wire2](../artifacts/run-001/live/wire/002-request.json.gz), [응답2](../artifacts/run-001/live/wire/002-response.json.gz).','WIKI_PROPOSE 최초+기존보완1회. 정규화/컴파일/최종RAG0.','모델채점0;서버계약거절과실행기오류를분리.','[실제결과](../artifacts/run-001/result.json). 전체미통과. 제품의형식거절과연구로그오류;원문이나상태를임의수정해성공처리하지않음.'];q.write_text('# 실제 작업공간 검증\n\n'+'\n\n'.join(h+'\n\n'+x for h,x in zip(heads,vals))+'\n');(A/'실험/README.md').write_text('# 시험결과\n\n[질문](질문-001-workspace-public-001.md), [결과](../artifacts/run-001/result.json).\n')
files=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design, real Oracle/model evidence, preserved preparation failure or synthetic regression checks','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1255','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files})
