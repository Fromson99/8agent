from pathlib import Path
import hashlib,json,zipfile
R=Path.cwd();O=Path(__file__).resolve().parent;NAME='GENOS_V6_SQL_AD_CUMULATIVE_20261006_R5';archive=O/(NAME+'.zip')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
# Reuse the previously tested backup/receipt installer without embedding shell substitutions from input.
source=(R/'08_DEPLOYMENT/GENOS/handoffs/unified_v6_cumulative_20261002_r4/GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.txt').read_text()
source=source.replace('GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4',NAME).replace('v6-r4-logs','v6-r5-logs').replace('r4_checked_installer','r5_checked_installer').replace('R4 code ZIP','R5 code ZIP')
import re
source=re.sub(r"expected='[0-9a-f]{64}'","expected='"+sha(archive)+"'",source)
source=source.replace("elif mode=='gate':",'''elif mode=='state-check':
 state=os.environ.get('GENOS_STATE_DIR','')
 if not state or not Path(state).is_absolute():raise ValueError('Set GENOS_STATE_DIR to the verified persistent LOCAL state volume absolute path; do not point to NFS')
 sys.path.insert(0,str(root/'02_BACKEND'))
 from semantic_runtime.ad_store import Store
 import uuid
 probe=Path(state)/('ad-storage-probe-'+uuid.uuid4().hex+'.sqlite')
 db=Store(probe)
 try:
  assert db.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  print('SQL_LOCAL_STORAGE_CHECKED',probe.parent,'PERSISTENCE_ACROSS_DEPLOYMENTS=VERIFY_ON_PLATFORM',flush=True)
 finally:
  db.close()
  for suffix in ('','-wal','-shm'):
   Path(str(probe)+suffix).unlink(missing_ok=True)
elif mode=='gate':''')
source=source.replace(" generation=os.environ.get('GENOS_GENERATION')", " generation=os.environ.get('GENOS_GENERATION')\n if not generation:raise ValueError('Set GENOS_GENERATION to the exact selected complete generation absolute path')")
source=source.replace(" if not argument:raise ValueError('Supply exact BACKUP/RECOVERY path printed by apply')", " print('CODE_ONLY_ROLLBACK: stop workers and preserve new AD SQL; select pre-migration DB or compatible code separately',flush=True)\n if not argument:raise ValueError('Supply exact BACKUP/RECOVERY path printed by apply')")
source=source.replace('Modes: check apply verify gate rollback','Modes: check apply verify state-check gate rollback')
(O/(NAME+'.txt')).write_text(source)
guide=f'''GENOS v6 SQL AD 누적 R5 (2026-10-06)

이 R5 ZIP + 실행 TXT를 사용합니다. 2026-10-02 전체 RAG 메일의 R4 이후 유지 중인 코드 업데이트와 이번 SQL AD모드를 누적했습니다. 별도 v3/user_wiki 시스템을 추가하지 않습니다. Redis는 없습니다.

1. 반입과 코드 적용
ZIP과 같은 이름의 TXT를 ~/DEV/TRANSFER에 업로드합니다. 기존 ~/DEV에서:
  bash TRANSFER/{NAME}.txt check
  bash TRANSFER/{NAME}.txt apply
  bash TRANSFER/{NAME}.txt verify
파일별 백업/receipt 경로가 출력됩니다. 재실행은 동일 설치를 확인합니다. 원문, 데이터 generation, 기존 DB, .env, .git은 덮어쓰지 않습니다. python3 실제 경로/버전 및 시작부터 전체 로그가 v6-r5-logs에 남습니다. 새 Python 라이브러리는 추가하지 않았습니다(Python 3.11+).

2. SQL 저장소와 상주 작업자
관리/shortcut v4 DB는 GENOS_STATE_DIR/case-memory의 명시 선택 DB를 사용합니다.
GENOS_STATE_DIR = 현장에서 확인한 영속 로컬 볼륨의 절대경로 (사용자가 실제 값을 지정)
TEAM_ID = 현재 서비스의 고정 업무 공간 (예: 이미 사용 중인 *_team 값)
AD_WORKER_ENABLED = 1
GENOS_RUNTIME_DIR = 기존 로그/runtime 경로, GENOS_STATE_DIR과 구분
현재 SQLite v4는 NFS/CIFS WAL을 거부합니다. /nfs-root를 상태 DB 경로로 그대로 쓰지 마세요. 영속 로컬 볼륨이 없으면 이 기능을 현장 활성화할 수 없습니다. 서버형 SQL로 바꾸는 별도 작업이 필요합니다. 코드를 설치했다는 이유로 볼륨 조건이 해결된 것은 아닙니다.
기존 v4를 옮길 경우 서비스 중지 후 SQLite backup API로 복사, integrity_check/행수 대조, 원본과 pointer/receipt 보존 후 선택하세요. 실행 중 WAL DB의 본체 파일 하나만 복사하면 안 됩니다. v3 데이터는 기존 이행 절차와 별도 receipt가 필요합니다. 빈 DB 초기화는 데이터 이행 완료가 아닙니다.
코드서빙 설정에 위 값을 저장하고 같은 값으로 현장 셸에서 다음 저장소 확인을 실행합니다:
  bash TRANSFER/{NAME}.txt state-check
저장소가 로컬인지·SQL 동작은 확인하지만 배포 간 영속성은 플랫폼에서 확인해야 합니다.
예약은 서버가 살아 있을 때 실행됩니다. scale-to-zero/프로세스 종료 중에는 SQL에 남겨 재가동 시 복구합니다. 현재 상태에 heartbeat_age_seconds가 표시됩니다. 작업 중 모델 호출의 즉시 종료는 보장하지 않으며 중지 후 출력 커밋은 차단합니다.

3. 배포와 workflow 편집기 (각각 별도)
반영한 ~/DEV에서 변경 파일과 git diff --check를 검토하고 커밋합니다. GENOS_GENERATION을 실제 선택한 완료 generation의 절대경로로 지정한 후:
  bash TRANSFER/{NAME}.txt gate
이 게이트는 그 checkout/commit의 코드와 ZIP·generation을 대조합니다. PASS한 commit을 push하고 그 commit과 generation으로 새 코드서빙 리비전을 배포하세요. 이 세션에서는 push/현장 배포를 수행하지 못했습니다.
기존 workflow Python 단계 편집기에 ZIP의 08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py 전체 내용을 반영합니다. ZIP 적용/push만으로 편집기는 바뀌지 않습니다. stable chatId/sessionId 전달을 유지하세요. user_wiki 인증은 사용하지 않습니다. 기존 앱/서비스 게이트웨이 접근은 유지합니다. main.py /chat 경로는 GENOS_CHAT_TRUST_PLATFORM_IDENTITY=1과 기존 GENOS_CHAT_GATEWAY_TOKEN(32자 이상)을 사용합니다. 키는 채팅이나 로그에 적지 않습니다.

4. workflow 테스트 화면에서만 현장 확인
일반 질문 → [AD모드 시작] → 현재 상태 → shortcut 목록 → 다음 → 행 번호 자세히 → 2번 승인 → 2번 버려 → 휴지통 → 방금 버린 것 복구 → 야간작업 돌리기 → 진행상황 알려줘 → 야간작업 리포트 줘 → 1번 자세히 → 계속 → 야간작업 시작 예약 저녁 12시 → 예약 목록 → 1번 예약 취소 → 위키 꺼 → 현재 상태 → 위키 켜 → [AD모드 종료] → 일반 질문.
빈 DB는 0건 목록/0건 작업이 정상입니다. 실제 행이 있을 때만 번호 변경을 시험하세요. 다른 chatId에서는 AD가 꺼져 있어야 합니다. 일반 질문의 삭제/승인 말은 관리 변경을 일으키면 안 됩니다. 임의 표현을 다 이해하는 LLM 관리기가 아니라 명령/한국어 표현을 안전하게 해석하는 관리기입니다. 도움말에 전체 명령이 있습니다.
위키 사용자 승인과 법률 검증은 다릅니다. 게시 전 현재성 검사도 자동 법률 검증이 아닙니다. 오류/스키마/traceback은 AD에서 조회하고 인증 비밀만 마스킹합니다.

5. 복구
개별 자료: 휴지통 → 번호 복구. 실행: 작업 중지/재개/취소/실패 작업 재시도. 예약은 별도 취소. AD 종료는 예약 취소가 아닙니다.
코드 원복: 출력된 정확한 BACKUP/RECOVERY 경로를 사용합니다:
  bash TRANSFER/{NAME}.txt rollback /출력된/정확한/백업경로
신규 AD 상태를 읽지 못하는 구 코드가 휴지통/OFF를 무시할 수 있습니다. 따라서 서비스 중지·새 DB 보존 후 이행 전 DB/포인터를 함께 선택하거나 호환 코드로 복구하세요. 코드 원복 TXT는 DB를 삭제/복구하지 않습니다. 이행 후 기록은 따로 보존하고 조정합니다.

검증: 로컬 MAIN generation41, 131 구조/회귀 계약, 배포 파일253·엔진30 전체 해시, 실제 활성 AD/일반 조회 통과. 실제 모델 호출0. GENOS 내부 모델·현장 예약 실행·상주 조건은 미확인. 법률 품질 인증이 아닙니다.
설계/SQL DDL/명령어/구현/검증 문서는 ZIP의 07_DOCS/REFERENCE/REPORTS/SQL_AD_MODE_SHORTCUT_WIKI_20261006/에 있습니다.
ZIP SHA256: {sha(archive)}
'''
(O/(NAME+'_GUIDE_UTF8.txt')).write_text(guide)
with zipfile.ZipFile(archive) as z:(O/'CODE_MANIFEST.json').write_bytes(z.read('CODE_MANIFEST.json'))
print('Prepared standalone execution TXT and guide')
