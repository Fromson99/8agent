from pathlib import Path
import json,hashlib
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1212-gold-main120-engine-check';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(O/'preflight.json');a=read(O/'port-audit.json');b=read(D/'baseline.json');C=R/b['release']['code_root']
assert p['code_unchanged'] and p['pointer_unchanged'] and a['code_unchanged'] and a['pointer_unchanged'] and not p['product_import_leaks']
assert all(sha(C/n)==h for n,h in b['release']['files'].items())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
result={'status':'FAIL_ENGINE_COMPATIBILITY','diagnostic_complete':True,'engine_startup_passed':False,'engine_answers':0,'model_calls':0,'embedding_calls':0,'selected_main':120,'selected_files_verified':len(b['release']['files']),'gold_documents':21,'sql_statements':p['sql_calls']+a['sql_calls'],'source_read_passed':p['checks']['original_read']['passed'],'positive_lexical_documents':a['positive_fulltext']['total'],'vector_publication_count':a['gold_vector']['completion']['count'],'required_navigation_kinds_missing':list(a['required_navigation_rows']),'blockers':['Latest-selection proof is not published','Bound navigation descriptor/compiler hashes and 8 derived navigation kinds are missing','Full glossary bundle/lookup/metadata is absent','Legacy expanded reference projection has zero rows although raw reference payloads are present','Existing initial-vector repository and profile/encoder contract do not match compact Gold'], 'cases':{x['id']:'NOT_RUN_BOOTSTRAP_GATE' for x in read(D/'cases.json')},'main_code_and_pointer_unchanged':True,'gold_mutations':0,'source_sqlite_fallback':False,'original_corpus_databases_opened':0,'peak_rss_MiB':round(p['peak_rss_KiB']/1024,2),'free_disk_GiB':a['free_disk_GiB'],'quality_certified':False,'vector_evidence_correction':a['vector_interpretation_correction']}
put(O/'result.json',result)
report='''기존 MAIN120 추론 엔진 × R12 골드 연결 검증 (2026-10-29)

판정: 현재 연결 상태에서는 기존 추론 엔진이 정상 시작하지 못한다.
골드 데이터 조회 검증과 전체 추론 연결 검증은 다르다. 이전 ADR1208은 별도 데이터 API를 검증했고, 이번 ADR1212는 현재 선택 MAIN120의 기존 Oracle Store와 실제 create_app을 그대로 사용했다.

확인된 정상 부분
- 골드 21문서와 검색 게시물/원문 게시물의 결속을 읽었다.
- MAIN120 원문 reader로 코스닥 상장규정 원문 1구간을 실제 읽었다.
- MAIN120 전문검색에서 ‘상장’은 18문서에 대응하고 첫 5개를 반환했다. ‘의무인수’의 정확 토큰 검색은 0건이었다. 이 0건을 회수 품질 통과로 해석하지 않는다.
- 골드 벡터 게시물은 READY, 16,085개, 활성 변경순번 3으로 기존 값과 동일하다. 이번 벡터 재생성이나 임베딩 호출은 없다.

실제 차단 원인
1. 서비스 시작: search_selection/selection_proof가 없어 QUERY_SELECTION 오류. 최신 문서 검증을 건너뛰지 않았다.
2. 탐색 구성: navigation/manifest.json 검증 메타와 navigation_compilers가 없다. QUERY_NAV_BINDING 오류를 독립 재현했다.
3. 추가 탐색 자료: native.unit/source/surface/index_label/member/coordinate/structure_proof/definition_summary 8종이 없다. 8개 새 물리 테이블이 아니라 기존 검색 행 저장소에 담기는 논리 자료 종류다.
4. 용어집: glossary/bundle/manifest.json 및 묶음/조회 자산이 없어 QUERY_GLOSSARY_BINDING 오류. 현재 원문에서 추출한 용어 출현과 외부 용어집의 정의·연결·조회 묶음은 별도 계약이다.
5. 참조: payload 59,389 / body 28,218 / end 110,106 / target 64,152행은 존재한다. 기존 term_index reader가 조회하는 펼친 reference 투영은 0행이다. 원본 참조 데이터 소실이라고 단정하지 않으며, 기존 reader가 읽는 형식의 재구성이 필요하다.
6. 벡터: 엔진의 oracle_query_resources에는 initial_vector.Retriever가 있고 기본 auto 모드다. 하지만 SIDDS.LGL_VCTR_* 테이블·legal-vector-profile-v1·GENOS 임베딩 연결을 요구한다. 이번 IDD_B03_LGL_VCTR_*의 축소 컬럼/JSON과 로컬 BGE-M3 판본은 이 계약에 자동 변환되지 않는다. 기존 벡터 HEAD 조회는 READ_FAILED, 프로필 검증은 VECTOR_PROFILE: fields로 거절됐다.

정정: 초기 preflight의 vector=False만으로 벡터 미연결을 설명한 문장은 불완전하다. 별도 initial-vector 경로가 있으므로 위 6번과 port-audit.json을 최종 근거로 삼는다. 초기 증거는 덮어쓰지 않았다.

실행 범위와 보존
- 골드 SELECT 28회, 생성 모델 0회, 임베딩 0회, 최종 답변 0개.
- CM007·009는 서비스 초기화 실패로 전체 추론 미실행이다. HTTP 질문 API나 모델 답변 통과라고 보고하지 않는다.
- 선택 MAIN120의 487파일과 ACTIVE_RELEASE 포인터 동일. 골드 변경·원본 SQLite 연결·우회 조회·GENOS 배포 없음.
- 명시적 실험 로컬 요청 상태 경로만 준비했다. 실제 배포 Factory의 NFS/CIFS 요구를 속이거나 우회하지 않았고, 실제 GENOS/ORDS/NFS 배포는 검증하지 않았다.
- 최초 제한 환경의 로컬 연결 차단은 별도 attempt-001에 보존했고, 승인된 로컬 읽기 실행으로 실제 DB 검증을 했다.
'''
report+=f"- 현재 여유 공간: WSL {a['free_disk_GiB'][str(R)]} GiB / C {a['free_disk_GiB']['/mnt/c']} GiB. 검사 프로세스 최고 RSS {result['peak_rss_MiB']} MiB. 이번 작업은 DB 복사/적재가 아니다.\n"
report+='''
다음 구현에 필요한 구체적 범위
- 기존 엔진을 유지하고 별도 골드 게시/연결 코드에서 최신 선택을 실제 검증한 증명, 탐색 파생 자료·컴파일 해시, 용어집 읽기 묶음, 펼친 참조 형식을 완성해야 한다. 검증 플래그만 true로 쓰거나 빈 용어집으로 통과시켜서는 안 된다.
- R12 벡터 reader를 기존 초기검색 인터페이스에 연결하고 동일 BGE-M3 모델/판본·분할·정규화·차원의 질문 인코더를 명시적으로 주입해야 한다. 기존 벡터를 다른 모델 출력과 섞지 않는다.
- 추가 행은 기존 SRCH_ROW, 게시 메타는 SRCH_POST의 JSON에 담는 방향으로 13테이블·60컬럼 유지 가능성을 검증한다. 이 가능성은 구현/용량 통과가 아니다.
- 게시 해시가 바뀌면 벡터의 query/source 결속도 재검증해야 한다. 새 게시물과 기존 게시물의 동시 보관분까지 포함해 Oracle 9.6GB 상한을 다시 계산한 뒤 활성 전환한다.
- 그 뒤 동일 MAIN120으로 CM007·009를 실제 모델에 순차 1회 실행하고 선택 원문→최종 입력→저장 답변을 검증한다. 모든 CM51 답변 품질을 이 2건으로 일반화하지 않는다.

근거: 04_EXPERIMENTS/ADR/ADR-1212-gold-main120-engine-check/artifacts/run-001/
preflight.json, port-audit.json, result.json, sql-statements.json, port-audit-sql.json, imports.json, sqlite-opens.json.
'''
U=R/'09_ARTIFACTS/AUDITS/20261029-gold-main120-engine-check';U.mkdir(parents=True,exist_ok=True);(U/'기존엔진_연결검증결과.txt').write_text(report)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'HISTORICAL_DATA_API_ONLY','reexecuted':False},'gold-engine':result},comparisons=[],judge_disagreements=None,usage={'model_calls':0,'embedding_calls':0,'sql_calls':28},latency={'preflight_seconds':p['seconds'],'port_audit_seconds':a['seconds']},error_taxonomy=[{'kind':k,'count':1} for k in result['blockers']]+[{'kind':'Initial sandbox loopback denied','resolution':'preserved; approved local read-only execution used'},{'kind':'Incomplete initial vector wiring interpretation','resolution':'preserved and corrected from actual initial_vector Retriever path'}])
m['retrieval_accounting'].update(corpus_total=21,not_applicable_reason='Bootstrap failure before CM retrieval; positive lexical query is a data-port probe, not CM recall.')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
cases={x['id']:x for x in read(D/'cases.json')}
for q in m['questions']:
    c=cases[q['case_id']];values=['run-001/gold-engine; 기존 MAIN120 / R12 골드 21문서',c['request']['json']['question'],'전체 추론 미실행, 기준답변 채점 없음. 정답·정답 좌표를 제품에 제공하지 않았다.','동결 cases.json의 질문·21문서만 예정.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n엔진 시작 단계 QUERY_SELECTION 거절. 질문별 탐색 후보·확보·최종 인용 모두 미실행.','0회. 서비스 초기화 실패로 모델 입력/출력 없음.','0회. 보완·감독 호출 없음.','채점 모델 0회. 법률 정확도 미평가.','NOT_RUN_BOOTSTRAP_GATE. 실패를 보존하며 연결 완료로 판정하지 않는다.']
    qp=A/'실험'/q['file'];qp.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n');q['sha256']=sha(qp)
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 실험 인덱스\n\n| 질문 | 상태 |\n|---|---|\n'+''.join(f"| [{q['case_id']}]({q['file']}) | NOT_RUN_BOOTSTRAP_GATE |\n" for q in m['questions'])+'\n사전 자료 연결 검사 실패. 실제 모델과 법률 답변 검증은 수행하지 않았다.\n')
front=(A/'README.md').read_text().split('---',2)[1]
sections=[
('결정 요약','검증 완료, 연결은 실패다. 현재 골드 게시물만으로 기존 MAIN120 추론 서비스가 시작하지 못한다. 제품·MAIN·Gold 불변. 데이터 API 검증과 추론 연결 검증을 구분한다.'),
('문제와 변경 전 구조','ADR1208은 원문·검색·벡터 독립 API를 제공했다. 이번에는 선택 MAIN120의 실제 Oracle Store 및 create_app을 주입하고 제품 파일을 수정하지 않았다.'),
('가설과 사전 판정 기준','가설: 동일 엔진이 기존 R12 게시물을 소비한다. 기준은 artifacts/design/criteria.json에 호출 전에 동결했다. 시작/탐색/용어집/원문 계약 모두 통과해야 CM007·009 각 1회 실제 모델 실행에 진입한다. 누락, 원문/권한 위반, 응답 없음은 실패다. 실패 뒤 검증기를 약화하지 않는다.'),
('실험 설계','baseline은 완료 ADR1208/gold-b03의 역사적 데이터 API 결과이며 재실행하지 않았다. gold-engine은 격리 rev-001 연결기와 현재 선택487파일을 사용한다. 원문 corpus는 Oracle만, 실험 요청 상태만 로컬. MAIN120의 도메인 authoring 실험 ADR1211과 작업/데이터 쓰기 범위가 다르다.'),
('데이터·모델·재현성','R12 B03 21문서, query 983415dd8d28478644da41635924d6525f573a457f63e50e07c6a092de787598. 정확 코드/자료 hash는 baseline.json/freeze.json/audit-freeze.json. CM007·009는 개발 중 알려진 질문이며 분리평가가 아니다. 실제 모델·임베딩 0회, 기준답변 채점 0회. 법령 현행성 미평가.'),
('결과','원문 읽기 성공, 양성 전문검색 상장 18문서/5개 첫 페이지, 벡터 READY16085/HEAD3 유지. create_app은 QUERY_SELECTION으로 실패. navigation은 QUERY_NAV_BINDING, glossary는 QUERY_GLOSSARY_BINDING. native 탐색자료8종 누락. 최종 답변0. 자세한 내용은 artifacts/run-001/result.json 및 별도 TXT.'),
('사례별 오류 분석','CM007·009 모두 NOT_RUN_BOOTSTRAP_GATE다. 질문별 모델 추론 실패가 아니라 공통 사전 연결 실패다. 최초 로컬 연결 권한 차단, 벡터 배선 해석 정정은 원본과 별도 증거를 보존했다.'),
('비용·지연·회수 규모',f"SQL28회, 모델0/임베딩0, 사전 검사 {p['seconds']:.3f}초·추가 포트 조사 {a['seconds']:.3f}초. 모델 비용0, 엔진 속도나 회수율 측정 아님. 골드 corpus21문서. CM 후보 생성에 도달하지 않아 단계별 recall/p50/p95 해당 없음."),
('해석','골드의 원문/검색/벡터 저장은 확인됐지만 기존 엔진의 게시·탐색·용어집 계약을 충족하지 않는다. vector=False만의 해석은 불완전하며 실제 initial_vector 경로의 테이블/프로필 불일치로 정정했다. 원시 참조가 있어도 기존 펼친 reference 조회가0행이면 같은 소비 계약이 아니다.'),
('한계와 일반화 가능 범위','실제 로컬 Oracle DB와 선택 MAIN120 모듈을 사용했으나 GENOS/ORDS/NFS 배포는 미검증. 전체 CM51/법률 품질/새 벡터 질/대규모 용량 효과 미검증. 새 게시물 용량과 겹쳐 보관할 기존 게시물의 합계를 추가로 계산해야 한다.'),
('운영 결정·롤백 조건','MAIN 유지, 승격하지 않는다. 현재 정상 골드 게시물/선택 포인터 변경0이므로 DB 롤백 대상 없음. 후속은 새 ADR에서 증명/탐색8종/용어집/참조 투영 및 R12 벡터·동일 모델 질문 encoder 연결을 구현한다. 세부 범위는 기존엔진_연결검증결과.txt. 누락 플래그 덮어쓰기·빈 용어집·원본 SQLite 우회 금지.'),
('재현 명령','실행 증거는 artifacts/preflight-002.log, port-audit.log와 run-001 JSON.\n\n```bash\nPYTHONDONTWRITEBYTECODE=1 .venv/bin/python 06_TOOLS/COMMANDS/adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1212-gold-main120-engine-check --final\n```\n\n실행기는 완료 파일이 있으면 거절한다. 다시 검사하려면 완료 ADR을 덮어쓰지 않고 새 ADR/실행을 선점한다. 원시 산출물과 SHA는 artifacts/manifest.json.')]
(A/'README.md').write_text('---'+front+'---\n\n# ADR-1212: R12 골드와 선택 MAIN120 기존 추론 엔진 연결 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
paths=[x for x in (A/'artifacts').rglob('*') if x.is_file() and x.name!='manifest.json']+[U/'기존엔진_연결검증결과.txt']+list(Path(__file__).parent.glob('*.py'))
am=read(A/'artifacts/manifest.json');am['files']=[{'path':str(x.relative_to(R)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Read-only compatibility diagnostic and preserved raw evidence','contains_raw_prompts_and_outputs':False} for x in paths];put(A/'artifacts/manifest.json',am)
print(json.dumps(result,ensure_ascii=False,indent=2))
