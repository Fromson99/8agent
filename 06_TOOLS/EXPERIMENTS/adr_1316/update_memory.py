from common import *
import datetime
report=ROOT/'09_ARTIFACTS/AUDITS/20261104-query-latency-main137'
old={s for s in (ROOT/'09_ARTIFACTS/AUDITS/20261104-sqlite-oracle-diverse/graph.log').read_text().splitlines() if s.startswith('ERROR:')};new={s for s in (report/'graph-final.txt').read_text().splitlines() if s.startswith('ERROR:')};assert len(new)==16 and not new-old
put(report/'graph-check.json',{'prior_errors':len(old),'errors':len(new),'new_errors':sorted(new-old)})
f=read(DES/'candidate-after.json');p=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=read(p);release=read(ROOT/active['manifest_path']);G=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';g=read(G/'binding.json')
assert active['generation']==137 and release['release_id']==g['engine_release_id']=='query-latency-native-20261104-r1'
assert all(sha(ROOT/n)==sha(ROOT/f['code_root']/n)==h for n,h in f['selected_files'].items())
assert all(sha(ROOT/release['code_root']/n)==sha(ROOT/n)==h for n,h in release['files'].items())
assert g['engine_files']==release['files']
put(report/'final-bindings.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active':active,'active_pointer_sha256':sha(p),'release_manifest_sha256':sha(ROOT/active['manifest_path']),'working_candidate_exact':539,'serving_working_candidate_exact':524,'gold_same_release':True,'gold_binding_sha256':sha(G/'binding.json'),'current_mapping':read(G/'ACTIVE_MAPPING.json'),'source_manifest_sha256':release['data_manifest_sha256'],'final_validation_pass':['ADR1315','ADR1316'],'graph_new_errors':[],'new_models':0})
block='''<!-- MAIN137_DB_LATENCY_1315_1316_20261104 -->
**2026-11-04 현재 로컬 MAIN137 — SQLite 준비·Oracle 구조 ID 배치 및 누적 수정 반영:** [추가수정·실측·반영 TXT](09_ARTIFACTS/AUDITS/20261104-query-latency-main137/추가수정_실측_메인반영결과.txt) · [ADR1315](04_EXPERIMENTS/ADR/ADR-1315-bounded-structure-query-main/README.md) · [ADR1316](04_EXPERIMENTS/ADR/ADR-1316-oracle-root-key-batches-main/README.md). **query-latency-native-20261104-r1·서빙524/MAIN136대비53변경·동결후보/작업539일치**, 공식 prepare/apply·Gold동일MAIN. 작업6+pin31=37: SQLite 공유객체freeze/문서JSON반복제거, Gold종류별projection, 원본구조ID→99키 native.unit배치, native638계획재생성·기존개발계설정pin 포함; 이전1311/12/14·nativeSQL·ORDS누적보존. **종류별만1315 root49.451→49.173초 효과없음 보존; ID배치1316 root49.173→12.081초(-75.43%),전체Oracle53.692→16.117초(-69.98%)**. root SQL40→81이나 driver39.485→0.531초; 원문ID는후보이고최종row해시/권한/판본·개수·중복/누락·기한검증유지. **SQLite17/17·실제readonlyGold18/18·전후35결과/catalogue동일·원문6/구조선택6두DB동일**, 신규배치14포함56·준비API/계약40·실제MAIN16/Goldbinding9/선택Gold4통과. 1315계약49/회귀179/fixture준비30/native실제SELECT+ORDS71은중복합산금지·기존fixture2동일실패·SQL미등록/enginepin/bytecode준비실패보존. **SQLite첫수정전체23.525→20.643초,최종재관측18.758초·준비15.126초잔존**, OraclePython검증/복사약11.55초·모델대기잔존. 최신CHAN_NO/RFRN/RGSN/docid100·Gold게시/원문/기본검토표·제공자설정보존. **USER_DIRECTED_CUTOVER/quality_certified=false·새모델/DDL/DML/현장배포/메일0**; 새답품질/FINISH실효/Oracle19/Dataiku/A8호환미인증. MAIN136+Gold이전binding원복보존·두ADRfinal통과/graph기존16새0. 아래MAIN136유지는이전시점이다.
<!-- /MAIN137_DB_LATENCY_1315_1316_20261104 -->

'''
p=ROOT/'AGENTS.md';s=p.read_text();assert 'MAIN137_DB_LATENCY_1315_1316_20261104' not in s;p.write_text(block+s)
skill=Path('/mnt/c/Users/Jin/.codex/skills/legal-rag-db-optimization/references');p=skill/'incidents.md'
with p.open('a') as out:out.write('''

## 2026-11-04 ADR1315/1316 추가 최적화와 MAIN137

- 증거/실패: packed Gold native.unit의 문서/부모가 JSON 내부라 root40페이지마다 큰 자료를 펼침. 종류별 기존projection만 연결한1315는49.451→49.173초/40SQL로효과없음. SQL수만줄이는접근으로해결되지않음.
- 수정: SourceReader.unit_ids가판본·권한문서조건으로원본색인의ID만100행씩반환. IDs는근거가아니며 native.structure_proof개수와대조하고99개digest lookup키씩published native.unit을완전히확보/검증. 각row해시/ACL/누락·중복/기한보존,4096unit초과fallback·부분cache금지. 이전요청내root재사용유지. SQLitefreeze중복복사/문서JSON반복해석도제거.
- 실측: 실제Oracle root49.173→12.081초(-75.43%),전체53.692→16.117초(-69.98%). root SQL40→81(IDs40+proof1+묶음40),driver벽39.485→0.531초. 전체root에Python해시/검증/복사약11.55초남음. SQLite첫수정전체23.525→20.643·준비18.187→16.843초;최종동일SQLite코드재관측18.758/15.126초는변동포함.
- 검증: SQLite17/17·readonlyGold18/18·전후35결과/catalogue같음·원문6/선택6두DBexact. 새배치14포함56·preparedAPI40·actualMAIN16/Goldbinding9/selectedGold4. 1315회귀fixture샘플SQL미등록19는테스트컴파일러등록후해결,기존2실패before동일. 준비pin3/bytecode실패보존. native638계획--check/30engine496dependency preflight.
- 상태: 사용자추가수정·MAIN반영명시지시로MAIN137 query-latency-native-20261104-r1공식prepare/apply·Gold같은엔진. 서빙524/MAIN136대비53·후보/작업539exact. 작업6+pin31=37,기존1311/12/14/nativeSQL/ORDS/개발계매핑보존;누락될development_g19_1.json과모듈pin포함. 최신Gold R5매핑/게시/원문/검토표기본/모델기본설정불변. USER_DIRECTED_CUTOVER quality_certified=false. MAIN136및Gold이전binding원복보존.
- 범위: 단회상법여러조회조건. 새모델0·DDL/DML0·현장배포0. 새답정확도/FINISH실제효과/NearAI안정성/Oracle19/Dataiku/A8환경인증없음. 최종두ADRpass/graph16prior0new. 원문sourceID후보조회도최종근거검증을없애지않을것.
- 원본: 09_ARTIFACTS/AUDITS/20261104-query-latency-main137/추가수정_실측_메인반영결과.txt; ADR1315/1316 analysis.json·actual·main·candidate/freeze; final-bindings.json.
''')
p=skill/'source-map.json';v=read(p);sources=[str((report/n).relative_to(ROOT)) for n in ['추가수정_실측_메인반영결과.txt','final-bindings.json','graph-check.json']]+['04_EXPERIMENTS/ADR/ADR-1315-bounded-structure-query-main/실험/manifest.json',str((ADR/'실험/manifest.json').relative_to(ROOT)),str((ART/'analysis.json').relative_to(ROOT)),active['manifest_path']]
v['main137_query_latency_1315_1316']={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'selected_main':active,'serving_files':524,'working_candidate_files':539,'oracle_root_seconds':[49.172619591932744,12.081096859066747],'oracle_root_sql':[40,81],'oracle_root_driver_seconds':[39.48459848505445,0.5307674361392856],'new_models':0,'source_hashes':{n:sha(ROOT/n) for n in sources}}
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print('Current MAIN137 binding verified and memory updated; graph16prior/new0')
