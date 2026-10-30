from pathlib import Path
import json,hashlib,sys,gzip
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1232-gold-connected-live-revalidation';D=A/'artifacts/design';O=A/'artifacts/run-001';P=O/'live/cm-009';U=R/'09_ARTIFACTS/AUDITS/20261030-gold-e2e-revalidation';U.mkdir(exist_ok=True)
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary

def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(P/'result.json');a=read(P/'audit.json');e=read(O/'ontology-vector-e2e.json');tests=read(O/'checks-current-schema.json');integrity=read(O/'post-run-integrity.json');originals=read(O/'original-database-integrity.json');calls=read(P/'calls.json');last=calls[-1]
result={'status':'INCOMPLETE_FINAL_MODEL_UNKNOWN','diagnostic_complete':True,'actual_case':'cm-009','planned_cases':2,'actual_cases':1,'not_run_cases':['cm-007'],'final_answers':0,'quality_certified':False,'real':r,'audit':{k:a[k] for k in ['source_checks','nested_view_checks','flat_view_checks','wire_request_matches','source_mismatches','acl_violations','physical_budget_matches','tool_actions','model_seconds','other_seconds','reported_cost_usd','input_tokens','output_tokens','resource']},'vector':e['vector'],'ontology':e['ontology'],'ontology_native_synthetic_checks':{'passed':tests['passed'],'failed':tests['failed'],'initial_old_fixture_failures':6,'models':'synthetic','engine':'selected MAIN123'},'integrity':integrity,'original_database_count':originals['original_database_count'],'original_databases_unchanged':originals['all_unchanged'],'main_promoted':False,'gold_published':False,'provider_switches':0,'new_actual_model_calls_after_unknown':0}
write_summary(O/'result.json',result)
report=f'''골드 연결 실제 재검증 및 온톨로지·벡터 E2E 확인 — 2026-10-30

결론
전체 실제 E2E는 아직 미통과다. 벡터는 실제 질문→Oracle 검색→원문 확보→최종 모델 입력까지 동작했다.
승인 온톨로지는 골드 실행에 연결되지 않았다. 별도 MAIN123 모의 native API의 온톨로지 기술 경로만 통과했다.

실제 CM009 (새 고정 ADR1232 / MAIN120 487파일 / 연결부 rev036)
- {r['seconds']:.3f}초, SQL {r['sql_calls']:,}회, 모델 물리 {r['model_calls']}회 = 예산 차감6, 도구 {a['tool_actions']}회.
- SQL1만회 한도에 도달하지 않고 최종 memory-assess에 진입. 같은 저장응답 재생이 아닌 새 실모델 판단이다.
- 조사5응답은 Parasail HTTP200/stop. 마지막6번째는 HTTP200 헤더 후 공백60조각·660바이트만 수신.
- 절대기한 {last['seconds']:.3f}초에 종료, UNKNOWN1·API504·저장FAILED·최종답변0. 통신 worker 회수 확인.
- 총 모델대기 {a['model_seconds']:.3f}초, 나머지 {a['other_seconds']:.3f}초. 나머지를 순수 SQL 시간으로 해석하지 않는다.
- 보고 비용 ${a['reported_cost_usd']:.8f}, 정상5응답 입력{a['input_tokens']:,}/출력{a['output_tokens']:,}토큰. UNKNOWN 사용량/비용 미보고.
- 429/공급자 전환0. 자원중단0, 호스트swap증가0, RAM가용 최소{a['resource']['minimum_available_GiB']:.3f}GiB.
- 사전 기준상 UNKNOWN 뒤 배치를 중단했다. CM007 이번미실행·자동재시험0; CM007 실패로 집계하지 않는다.
- 감독은 NO_ANSWER_PROGRESS로 호출됐으나 SUPERVISOR_UNRESOLVED:ProposalError 인계. 최종평가의 직접 실패는 별도의 공급자 공백/기한종료다.

벡터 실제 연결
- 로컬 BGE-M3 질문 임베딩1회, Oracle VECTOR_DISTANCE SQL1회, 후보100개·상위100한도 표시.
- 100개 ID 고유·21문서 권한범위·순위/유한거리 정렬 확인.
- 후보 중3개가 실제 확보 원문과 최종6출처 목록에 연결됐다. 나머지 원문은 기존 추가 조사 경로로 확보했다.
- 확보 원문146구간, 중첩모델입력356구간, 평면최종78구간을 원본과 대조: 불일치0·권한위반0.
- 최종78구간 모두 실제 전송본문에 존재. journal의 전송 전 요청6개를 실제 wire와 대조해 모두 동일.
- 벡터 생성/저장 존재만 확인한 상태를 넘어 실제 검색·원문·최종입력까지 확인했다. 최종답변·인용완료는0이므로 전체E2E 통과는 아니다.
- 100개 후보를 전부 읽었거나 정답근거가 전부 검색됐다는 뜻은 아니다. 골든 회수율/검색 정확도는 채점하지 않았다.

온톨로지 실제 연결 및 별도 기술검사
- 실제 골드 profile: ontology_enabled=false, mode=A0. 선택 MAIN123 기본 profile도 동일하다.
- GENOS_RAG_ONTOLOGY_CONFIG 미설정. 실제 실행의 온톨로지 조회/전달 기록0·최종 ontology_bundles0.
- Oracle에서 읽은 게시 명세의 excluded_features에 approved ontology publications가 명시되고 ontology 테이블 종류는0이다.
- 따라서 용어집69,813개 연결을 승인 온톨로지 연결로 설명할 수 없다. 골드 Oracle 경로의 온톨로지 E2E는 미연결이다.
- 별도 선택 MAIN123(작업/선택489파일일치)에서 모의 모델·합성원문·로컬SQLite로6개 계약검사 통과.
  누적2판본→내용승인→staged→소비검증→활성화→native RAG 입력→claim/답변→저장·동일요청 재조회,
  OFF/빈게시 fallback, 원문변경/부분원문 withholding, CAS/롤백/중복게시 경로다.
- 이는 실제 골드 Oracle·실제LLM과 결합한 온톨로지 성공이 아니다. 사람 승인된 실지식이나 실제 모델의 정규화·누적 품질도 인증하지 않는다.
- 최초6검사는 오래된 모의생성응답과 MAIN123 wire schema가 달라 정규화에서 실패했다. 기존 ADR1231의 테스트 전용 wire변환을 재사용한 후6통과.
  제품검증기를 우회하거나 제품코드를 수정하지 않았다. 최초실패와 정정실행을 모두 보존했다.

보존·한계·다음 연결 지점
- MAIN120엔진487/골드연결부/실행기·설계·기존ADR1214 해시불변. 활성MAIN123 포인터불변. 원본DB9개 SHA불변.
- 원문/용어/벡터는 실제추론 중 Oracle만 조회. SQLite는 요청journal과 실행후 원문대조에 사용; corpus 우회0.
- 승인/게시/OracleDDL/운영선택/Git/메일/GENOS 변경0. 금번 새로운 모델 호출은6회다.
- 다음 필수 작업은 승인 온톨로지 저장소·게시본을 골드 요청의 원문/용어/권한에 결속하고, 별도 시험설정에서 ON/DB로 연결하는 것이다.
  켜기만 해서는 누락된 게시본이 생기지 않는다. 현재 configuration의 원문 reader는 oracle-silver/sqlite-local이고 도메인 glossary factory는 sqlite-local이므로,
  R12 Gold Oracle의 인증된 source/glossary 포트 주입과 실제 approved publication 저장/조회 계약도 검증해야 한다.
- 최종모델의 공백응답은 원시수신 증거로 확인했으나 공급자 내부 원인은 미확인이다. SQL/벡터 오류로 분류하거나 재시도로 성공을 만들지 않았다.
- audit 최초압축journal reader 오류와 vector helper 필드명 오류는 읽기전용 진단코드에서 정정했다. 원본실패/불완전임시파일 보존·추가모델0.

주요 증거
{O.relative_to(R)}/result.json
{O.relative_to(R)}/ontology-vector-e2e.json
{O.relative_to(R)}/gold-manifest-check.json
{O.relative_to(R)}/checks-current-schema.json
{P.relative_to(R)}/audit.json
{P.relative_to(R)}/raw/006/partial.json.gz
{P.relative_to(R)}/runtime/
'''
(U/'실제재검증_온톨로지_벡터_E2E결과.txt').write_text(report)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True,'reexecuted':False,'parent':'ADR-1214-experiment-v1/connected'},'live':result},comparisons=[],judge_disagreements=None,usage={'physical_calls':6,'unknown':1,'reported_cost_usd':a['reported_cost_usd'],'unknown_cost_reported':False},latency={'cm-009_seconds':r['seconds'],'cm-007':None,'p50_p95_reason':'one executed request; no population latency claim'},error_taxonomy=[{'kind':'provider_incomplete_response','count':1,'case_id':'cm-009','stage':'ASSESS','result':'UNKNOWN/API504'},{'kind':'ontology_not_connected','observed':True,'actual_calls':0}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정'];cases={x['id']:x for x in read(D/'cases.json')}
for q in m['questions']:
 cid=q['case_id'];outcome='실제6물리·최종ASSESS UNKNOWN/API504·답변0' if cid=='cm-009' else '미실행: 앞선009 UNKNOWN으로 사전중단조건 적용·물리0'
 values=['run-001/live; 2026-10-30 KST; MAIN120/rev036',cases[cid]['request']['json']['question'],'기준답변을 제품모델에 제공하지 않았고 별도채점모델0회.', '[고정 입력](../artifacts/design/cases.json)·골드21문서.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n실제벡터100후보와확보/최종ID는 ontology-vector-lineage.json.gz에 기록. 회수정책변경/골든회수율채점없음.',outcome+'; [원시 자료](../artifacts/run-001/) raw 및 canonical 압축본문/내용해시 보존.','009 최초/조사/감독5정상 후 최종1UNKNOWN. 007 없음.','자동재시험·LLM채점0. 원문146/356/78대조와실제wire6개대조.',outcome]
 path=A/'실험'/q['file'];path.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n');q['sha256']=sha(path)
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 실험 인덱스\n\n'+''.join(f"- [{q['case_id']}]({q['file']}): "+('실제504/답변0' if q['case_id']=='cm-009' else '배치중단으로미실행')+'\n' for q in m['questions']))
sections=[('결정 요약','실제009 SQL3992로 최종평가 도달, 마지막공백응답UNKNOWN/API504. 벡터실제최종입력까지연결·온톨로지골드미연결. 전체미통과.'),('문제와 변경 전 구조','ADR1214의실제목록/SQL한도실패와rev036저장응답재생 이후 새실제완주검증이없었다.'),('가설과 사전 판정 기준','[호출전동결기준](artifacts/design/criteria.json). CM009→007각1회, SQL10000/40물리/1024도구/1800초; UNKNOWN/자원/권한/해시실패시나머지중단.'),('실험 설계','제품무변경 MAIN120487+동일rev036고정. 독립새journal, 실제1회. 결과확인뒤 사용자 온톨로지/벡터E2E요청은 읽기전용실행감사와별도기존계약검사로수행.'),('데이터·모델·재현성','골드21문서·동일게시물ID. OpenRouter Qwen3.8/Parasail, 429전환실제0. 반출범위승인과계속확인지시기록. 정답비공개.'),('결과',report),('사례별 오류 분석','009 ASSESS HTTP200헤더/공백660바이트→179.884초기한종료. SQL3992<10000. 007미실행. 온톨로지OFF·게시본제외이며모의6검사는별도.'),('비용·지연·회수 규모',f"557.067초·모델331.941초·기타225.126초·물리6·보고${a['reported_cost_usd']:.8f}. UNKNOWN사용량미보고. 벡터100중3확보/최종입력연결; 전체회수율미채점."),('해석','검색/원문확보/전송/모델완료/저장답변을분리한다. 원문무결성통과는최종법률정답이아니다.'),('한계와 일반화 가능 범위','실제전체E2E미통과·온톨로지골드미연결·MAIN123모의native6통과는실제Oracle/LLM증명아님. 다른질문/GENOS/법률품질일반화없음.'),('운영 결정·롤백 조건','운영변경0, MAIN123/원본9DB보존. 기존연결폴더에후속결과링크만추가. 후속실행은새동결범위에서수행.'),('재현 명령','run.py health/cm-009 (완료경로재실행거부); audit.py cm-009; e2e_audit.py; ontology_contracts.py current-schema. 과거결과덮어쓰지말것. 완료구조검사는 stable adr_structure.py validate --final.')]
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected');(A/'README.md').write_text('---'+front+'---\n\n# ADR-1232: 골드 실제 E2E 재검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
print(result['status'],U/'실제재검증_온톨로지_벡터_E2E결과.txt')
