from common import *
import datetime
report=ROOT/'09_ARTIFACTS/AUDITS/20261104-sqlite-oracle-diverse'
prior=ROOT/'09_ARTIFACTS/AUDITS/20261104-latency-repair-live/graph-validation.txt'
old={s for s in prior.read_text().splitlines() if s.startswith('ERROR:')};new={s for s in (report/'graph.log').read_text().splitlines() if s.startswith('ERROR:')};assert not(new-old),(new-old)
put(report/'graph-check.json',{'errors':len(new),'prior_errors':len(old),'new_errors':sorted(new-old)})
f=read(DES/'candidate-after.json');C=ROOT/f['code_root'];n='02_BACKEND/semantic_runtime/oracle_query_matcher.py';integration=read(ART/'working-integration.json');assert sha(ROOT/n)==sha(C/n);assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==integration['main_pointer_sha256']
put(report/'final-bindings.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repaired_module':n,'sha256':sha(ROOT/n),'candidate_sha256':sha(C/n),'main_pointer_unchanged':True,'main_pointer_sha256':integration['main_pointer_sha256'],'active_release':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'graph_new_errors':[],'final_validation_pass':['ADR1313','ADR1314'],'new_model_calls':0,'oracle_writes':0,'ddl':0})
block='''<!-- ORACLE_ROOT_DIVERSE_1313_1314_20261104 -->
**2026-11-04 — SQLite·실제 로컬Oracle Gold 다양한조회검증 및 root반복조회수정:** [결과/남은문제 TXT](09_ARTIFACTS/AUDITS/20261104-sqlite-oracle-diverse/두DB_다양한케이스_검증과_남은문제.txt) · [ADR1313](04_EXPERIMENTS/ADR/ADR-1313-sqlite-oracle-diverse-validation/README.md) · [ADR1314](04_EXPERIMENTS/ADR/ADR-1314-oracle-root-local-reuse/README.md). **작업제품1(oracle_query_matcher)+pin31=32파일, 선택MAIN136유지.** 같은상법10구조/6원문/4FTS·권한·기한 등 **최종SQLite17/17·실제readonlyOracle18/18**, 원문6/성공선택6·동일DB전후35결과동일. Oracleroot는3946unit약5.9MB가4MiB페이지cache초과해버려진뒤부모166/점1191재조회; 요청내완료문서1개/4096unit/16MiB재사용으로 **229.486→47.749초(-79.19%),1397→40SQL(-97.14%)**, 전체234.487→51.886초. **계약230통과/기존fixture2실패·작업43/기존1(중복)**, 신규11·API3포함. 원문반복/선택재검증SQL0, ACL/판본/기한/불완전·초과fallback유지. 초기동시작업oracle_dp/pin혼합API3차단은격리검증모듈복원후통과·관측기cursor준비1실패보존; 실제oracle_dp/ORDS병행작업덮어쓰기0. FTS첫두페이지본문/순서/총수동일, **통계범위SQLite255806행/5690178토큰 vs 로컬Gold21문서56475행/1499236토큰**으로점수다름. **남은Oracle40페이지38.374초SQL벽시간·SQLite첫준비약20초·실모델대기**, 단회순차비교·현장Oracle19/Dataiku/새답품질/FINISH실제효과인증아님. 새모델/DDL/DML/MAIN·Goldbinding/원문/기본검토표/배포/메일0. runtime각2전파일SHA보관·두ADR최종검사통과/graph기존16·새0.
<!-- /ORACLE_ROOT_DIVERSE_1313_1314_20261104 -->

'''
p=ROOT/'AGENTS.md';s=p.read_text();assert 'ORACLE_ROOT_DIVERSE_1313_1314_20261104' not in s;p.write_text(block+s)
skill=Path('/mnt/c/Users/Jin/.codex/skills/legal-rag-db-optimization/references');p=skill/'incidents.md'
with p.open('a') as out:out.write('''

## 2026-11-04 ADR1313/1314 실제Oracle root조회 및 다양한두DB검증

- **증상/근거:** 실제SQLite17/17·Oracle18/18동일query조건통과이나 Oracle root229.486초/1397SQL. 전체문서3946unit약5.9MB를40페이지로읽고4MiB완료페이지cache상한초과로버림. 부모166SQL166.193초, unit점1191SQL1.291초. 페이지40SQL40.726초. 점조회수만보면시간주원인을오해한다.
- **수정:** oracle_query_matcher.Units의완료root뷰를요청내1문서/4096unit/16MiB로재사용; parentindex/pointmap, partial/overflow캐시금지, copy반환·권한/판본/manifest/deadlinecheck유지. 제품1+pin31작업반영,MAIN136유지.
- **결과:** root229.486→47.749초(-79.19%),1397→40SQL(-97.14%),전체Oracle234.487→51.886초. 원문6/선택6·모든35query결과동일. SQLite17/Oracle18최종통과,계약230/기존2실패·작업43/기존1(중복),root신규11. 새모델0.
- **실패보존:** 동시작업oracle_dp캡처와옛pin혼합으로API3차단. 격리해서이전검증oracle_dp복원후엔진pin전수확인/API3통과; 현재병행작업oracle_dp/ORDS덮어쓰기0. 최초관측기cursoriteration메타데이터1SELECT뒤준비실패보존. 기존fixture2동일실패.
- **검색비교:** 실제FTS첫두페이지본문/순서/총수동일,score다름. 로컬Gold게시21문서56475검색행/1499236토큰 vsSQLite255806행/5690178토큰. 원문storeSHA같아도게시검색통계범위가달라BM25점수동일성은보장되지않음.
- **남은것/범위:** Oracle40페이지SQL벽38.374초/전체root47.749,SQLite첫준비약20초,NearAI응답대기와FINISH실모델효과별도. 로컬Oracle23단회,현장Oracle19/Dataiku및법률품질미인증. 원문/Goldbinding/MAIN/DDL/DML/배포/메일0. 두ADRfinal통과/graph기존16새0, 각runtime2전파일SHA보관.
- **원본:** 09_ARTIFACTS/AUDITS/20261104-sqlite-oracle-diverse/두DB_다양한케이스_검증과_남은문제.txt, ADR1313/1314의analysis·actualSQL·계약·working-integration.json.
''')
p=skill/'source-map.json';v=read(p);sources=['04_EXPERIMENTS/ADR/ADR-1313-sqlite-oracle-diverse-validation/실험/manifest.json',str((ADR/'실험/manifest.json').relative_to(ROOT)),str((ART/'analysis.json').relative_to(ROOT)),str((ART/'working-integration.json').relative_to(ROOT)),str((report/'두DB_다양한케이스_검증과_남은문제.txt').relative_to(ROOT)),str((report/'final-bindings.json').relative_to(ROOT)),str((report/'graph-check.json').relative_to(ROOT))];v['oracle_root_diverse_1313_1314']={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'selected_main':'MAIN136 unchanged','working_product_modules':1,'sqlite_cases_passed':17,'oracle_actual_cases_passed':18,'oracle_root_seconds':[229.48551114008296,47.748547241906635],'oracle_root_selects':[1397,40],'new_model_calls':0,'source_hashes':{n:sha(ROOT/n) for n in sources}};p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print('Memory updated; graph16prior/new0, selectedMAINunchanged, workingmoduleexact')
