from common import *
import datetime
report=ROOT/'09_ARTIFACTS/AUDITS/20261104-oracle-development-main138'
errors=[s for s in Path('/tmp/adr1317-graph.json').read_text().splitlines() if s.startswith('ERROR:')]
new=[s for s in errors if 'ADR-1317' in s];other=[s for s in errors if 'ADR-1318' in s]
assert not new and len(errors)-len(other)==16
put(report/'graph-check.json',{'errors':errors,'count':len(errors),'this_ADR_errors':new,'prior_count':16,'concurrent_ADR1318_errors':other})
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==138
assert all(sha(ROOT/release['code_root']/n)==sha(ROOT/n)==h for n,h in release['files'].items())
put(report/'final-bindings.json',{'active':active,'serving_files':len(release['files']),'working_selected_exact':True,
 'Gold_binding_sha256':sha(ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json'),
 'release_manifest_sha256':sha(ROOT/active['manifest_path']),'ADR_manifest_sha256':sha(ADR/'실험/manifest.json'),
 'graph_errors':len(errors),'new_this_ADR_graph_errors':0,'other_concurrent_errors':len(other)})
block='''<!-- MAIN138_ORACLE_DEVELOPMENT_VECTOR_1317_20261104 -->
**2026-11-04 현재 로컬 MAIN138 — 개발계 Oracle 벡터 연결:** [수정·검증](09_ARTIFACTS/AUDITS/20261104-oracle-development-main138/수정_검증_개발계확인.txt) · [개발계 확인방법](08_DEPLOYMENT/GENOS/handoffs/main138_oracle_vector_20261104_r1/개발계_확인방법.txt) · [ADR1317](04_EXPERIMENTS/ADR/ADR-1317-oracle-development-vector-import-main/README.md). **oracle-development-vector-20261104-r1·서빙525/MAIN137대비37(제품6+pin31)·후보/작업540동일**, 공식prepare/apply·Gold같은MAIN. `DP=oracle`+`GENOS_ORACLE_TABLE_MAPPING=development_g19_1`에서 G19 벡터 HEAD/POST/ITEM·적재프로필→GENOS임베딩 명시결속; 모델없는 RAG_SEARCH의 Oracle논리경로 tempfile500 제거. **PeCab/pyarrow수정0**, runtime sqlglot0·639계획check/engine30·497파일preflight. **실제임시Oracle23.26.3 17테이블/파일SQLite차단·원문파일격리 상태로 서비스기동/원문/검색/벡터SQL/ACL/기록재조회통과·최종92SQL**, 임베딩은고정3차원1응답. 준비32/native실제Oracle39/MAIN16/Goldbinding9통과(중복합산금지), 회귀68통과/fixture1실패는ROOT정정후boot9통과. 추가기존Gold벡터는100후보반환뒤기록기오류,재검사swap보호중단으로미완료·이후재시도0. **실제GENOS임베딩/답변LLM/현장배포0**, 로컬기본모드보존·개발계명시설정필수,온톨로지전체/실모델품질미인증. 기존Oracle데이터변경0·임시6스키마삭제; MAIN137/Goldbinding원복·USER_DIRECTED_CUTOVER/quality_certified=false. ZIP528(서빙525+점검3)준비·메일0·ADRfinal통과/graph本ADR새0(기존16+병행1318미완료6). 아래MAIN137은이전시점이다.
<!-- /MAIN138_ORACLE_DEVELOPMENT_VECTOR_1317_20261104 -->

'''
for name in ('AGENTS.md','GENOS.md'):
 p=ROOT/name;s=p.read_text();assert 'MAIN138_ORACLE_DEVELOPMENT_VECTOR_1317_20261104' not in s;p.write_text(block+s)
skill=Path('/mnt/c/Users/Jin/.codex/skills/legal-rag-db-optimization/references')
with (skill/'incidents.md').open('a') as o:
 o.write('''

## 2026-11-04 ADR1317 MAIN138 개발계 Oracle 벡터와 tempfile 오류

- 원인: 표준 G19 원문/검색/Agent 매핑은 있었으나 initial_vector는 옛PBLS/SEG/ACT물리명. 적재Dataiku프로필과GENOS질의모델연결부재. 실제Oracle RAG_SEARCH는논리runtime에tempfile을만들어500.
- 수정: oracle_query_vector의HEAD/POST/ITEM물리투영·query/source/dataset/documents/profile/READY결속,GENOS_EMBED_PROFILE_SHA256+MODEL/gateway/tenant/차원검사. metadata-only document_agent는미사용매핑파일생성생략. ACL/원문검증/기한/요청재사용보존. 사용자정정으로PeCab/pyarrow미변경·sqlglot build-only유지.
- 결과: 임시Oracle23.26.3 split-owner17테이블·원문파일격리·파일SQLite/runtime sqlglot차단. 최종92SQL의실제service기동/원문/검색/동일resources벡터SQL/ACL/기록재조회통과,임베딩고정3차원1응답. 준비32/native실제Oracle39/MAIN16/Goldbinding9(중복합산금지). 회귀68통과1fixtureROOT혼합실패→같은ROOT boot9통과.
- 실패: rev001 tempfile제품오류→rev002해결. 추가기존Gold BGE벡터100후보반환후관측기value필드오류1,재검사1회SQL7시작뒤swap증가보호중단. 이후재시도0·Gold추가probe전체미완료를개발계합성검사와혼합금지.
- 적용: MAIN138 oracle-development-vector-20261104-r1·서빙525/후보540·제품6+pin31. 공식prepare/apply·Gold동일엔진,개발계DP=oracle/development_g19_1필수·로컬기본보존. 기존Oracle데이터변경0·임시6스키마삭제. 실GENOS임베딩/답변LLM/배포/메일0;온톨로지전체/실모델품질미검증. MAIN137/Gold이전binding원복. ADRfinal통과,graph본ADR0·기존16·병행1318미완료6은별도.
- 원본: 09_ARTIFACTS/AUDITS/20261104-oracle-development-main138/수정_검증_개발계확인.txt; ADR1317; 08_DEPLOYMENT/GENOS/handoffs/main138_oracle_vector_20261104_r1/개발계_확인방법.txt/HANDOFF.json. 서빙525+점검3 ZIP. 현장은metadata-only→동일임베딩모델확인→벡터1조회→워크플로우UI실제요청 순서.
''')
p=skill/'source-map.json';v=read(p)
paths=[report/'수정_검증_개발계확인.txt',report/'final-bindings.json',report/'graph-check.json',ADR/'실험/manifest.json',ROOT/active['manifest_path']]
v['main138_oracle_development_vector_1317']={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'selected_main':active,'field_executed':False,'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in paths}}
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print('MAIN138/Gold/code hashes verified; audit and memory updated')
