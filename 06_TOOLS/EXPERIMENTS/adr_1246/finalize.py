from common import *
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path']);f=read(DES/'freeze.json');entry=read(OUT/'main-entry.json');cap=read(RUN/'capacity-after.json');comparison=read(RUN/'comparison.json')
assert active['generation']==129 and active['release_id']==RELEASE and entry['passed']
assert release['files']==f['files'] and all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(OUT/'authorization.json'),read(OUT/'validation.json'))
status={'selected_main':129,'release_id':RELEASE,'serving_files':495,'working_candidate_selected_exact':True,'product_modules':3,'pin_files':31,'technical_passes':188,'same_existing_failures':14,'new_failures':0,'actual_root_oracle_api_cases':2,'selected_root_health_checks':13,'new_real_model_calls':0,'actual_question_retested':False,'new_ddl':0,'oracle_tables':4,'oracle_user_columns':26,'comparison':comparison,'capacity':cap,'original_failed_scope_preserved':True,'default':'NFS/SQLite','DP=oracle':'Oracle structured authority; raw diagnostics NFS; no persistent SQLite','rollback_reader_required':'After any v3 body write, retain v3-capable reader; do not run MAIN128 v2-only reader over new records','source_adrs':[1246,1248],'field_genos_nfs_ords_19c_verified':False,'quality_certified':False}
put(OUT/'final-status.json',status)
guide=f'''Oracle 기록 저장·메모리 갱신 수정 — MAIN129 / 2026-10-30

반영
  MAIN129 / {RELEASE}, 제품3모듈+엔진핀31=34변경.
  작업/동결후보/선택495파일 동일. 공식prepare/apply, 실제service.service HEALTH200/13조건 확인.
  Gold 연결기는 같은MAIN129 엔진으로만 결속; 기존매핑/R18/온톨로지설정/원문/벡터/게시내용 유지.

수정
  1. 열려 있는 결과 커서가 가리키는 SQLite 메모리를 deserialize로 바꾸던 경로 제거.
     결과행을 실행 시 분리하고, native backup으로 갱신. 연결RLock과 Oracle연결의 statement cache 비활성.
     기존 코드가 작은40교차쓰기 재현에서SIGSEGV(-11), 수정본 동일재현 통과.
     실제1245 충돌과 모든C내부원인이 동일하다는 인증은 아니며 실제모델 재시험은 하지 않았다.
  2. Oracle 모드에서는 기존SQLite 문자열/압축blob factor의 새쓰기를 생략.
     BODY가 내용주소·압축을 담당. 기존compact blob/판본2 reader와 원래기록은 유지.
  3. 본문 전체를 압축한 뒤2KB로 나누는v3형식, v2/v3 모두 복원.
     변경행+작업영수증 본문을 함께 업로드하고 해시/미완료/CAS/fence 검증은 그대로 유지.

고정 실제Oracle 비교
  구조화 근거100객체·8판본, 동일입력·정확복원.
  BODY조각74→46 ({comparison['body_part_reduction_percent']:.2f}% 감소), SQL241→107 ({comparison['sql_reduction_percent']:.2f}% 감소).
  REC행54→27. Envelope문자는33,453→33,761로 소폭 증가했다.
  이 숫자는 작은고정fixture의행/호출수이며, 전체실제질의의속도/할당용량개선율이 아니다.
  raw metric의legacy_compact_new_writes는재오픈reader에서측정한값이라writer상태를뜻하지않는다.
  실제writer는baseline compact=True, candidate=False이며원본metric은그대로보존했다.

검증
  기술188통과: 신규단위14+실제Oracle기존18+서비스2+기존153+고정Oracle1.
  기존14실패가MAIN128과동일·새실패0. 전체저장소통과/법률품질인증은아니다.
  실제root Oracle/NFS정상·장애2와선택MAIN129기본NFS HEALTH13조건은별도확인.
  상세NFS는합성어댑터검증이며현장mount/ORDS/Oracle19/GENOS 인증은아니다.
  최종필요-근거 NEED_TARGET_INCOMPLETE/NEED_RESOLUTION_CLAIM은기존검증그대로다.
  이법률판단문제·Gold원문반복조회·실제369질의전체는이번수정후미재시험이다.

DB / 설정
  테이블·컬럼 추가0. 기존Agent3표21컬럼+기존STATE5=4표26컬럼 유지.
  기존Dataiku R3 SQL은그대로사용하며이미생성한표를재생성하지않는다.
  DP미설정/NFS 기본유지. DP=oracle는구조화정본Oracle/상세프롬프트·응답·trace는NFS.
  추가필수환경변수없음. NFS미설정/실패시진단참조가명시되고로컬/Oracle raw fallback은없다.
  이전실패scope는RUN/REC/BODY/STATE=1/2987/52742/52와FAILED상태그대로보존.
  현재SIDDA할당 {cap['sidda_used_percent']:.3f}%, 디스크 {cap['disk_used_percent']:.3f}%, 사용자한도90%이내.
  기존이력을삭제/재압축/이관하지않아기존할당량을줄인것은아니다.

복구·기록
  새v3본문을쓴뒤에는v2전용MAIN128로단순복귀하면안된다.
  v3reader를유지하는호환복구릴리스또는검증한이전snapshot/namespace로복구하며신규기록을보존한다.
  상세원시로그NFS/기존NFS모드·원문/권한/LLM/예산/UNKNOWN·판단검증규칙변경0.
  실제모델/임베딩0·현장배포/Git/메일0.
  기술근거1246의승격메타누락은공식검사가차단했다. 완료기술결과를덮어쓰지않고별도1248반영감사로결속.
  ADR1247은별도세션의고정MAIN128/SQLite시험으로우리수정·반영작업과구분해보존했다.
'''
(OUT/'수정과_검증_메인반영결과.txt').write_text(guide)
print('Final MAIN129495 exact; root13PASS; no newDDL/model; original Oracle failure preserved')
