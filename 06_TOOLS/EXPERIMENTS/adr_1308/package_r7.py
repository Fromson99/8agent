from common import *
import zipfile
P=ROOT/'08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_seek_20261103_r7';old=ROOT/'08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_fast_20261103_r6/package'
manifest=read(P/'package/CODE_MANIFEST.json');assert all(sha(P/'package'/n)==h for n,h in manifest['files'].items())
prior=read(old/'CODE_MANIFEST.json');assert all(sha(old/n)==h for n,h in prior['files'].items())
note='''R7 적재 재개 최적화 — 2026-11-03

기존 R6 배포본·Oracle 데이터·query release를 바꾸지 않고 별도 준비한 후속 코드입니다. 실제 Dataiku 현장 실행은 하지 않았습니다.

변경: 일반 테이블은 저장된 ordinal 다음 OFFSET부터 생성합니다. FTS 길이는 rowid, posting은 (doc,col,term) 다음부터 생성합니다. posting 재개에서 완료된 길이 전체 집계를 다시 만들지 않습니다. 재개 위치는 마지막으로 DB가 인정한 배치와 함께 저장합니다. 읽기 선행으로 generator가 앞서 진행해도 저장 위치는 마지막 배치 행입니다.
기존 R6 state에는 생산자 커서가 없으므로 최초 재개는 기존 행 건너뛰기 경로를 사용합니다. 새로 완료한 배치부터 커서가 붙습니다. source/native 단계는 기존 순회 후 건너뛰기를 유지합니다.

기존 job/state 경로와 G19_OLD_JOB_DIR, G19_DIAGNOSTIC_FILE 환경값을 그대로 사용합니다. 먼저 새 package의 pipeline_entry.py check로 연결/체크포인트 결속을 확인하고 기존 load 진입점을 사용합니다. 상태 초기화, 새 적재 시작, 자동 publish, DDL, 통계 수집을 하지 않습니다.
INSERT acknowledgement, 불확실한 pending 배치 키 확인, checkpoint 잠금과 원래 R6의 검증 정책을 유지합니다. full-value 재대조를 추가하지 않습니다.

검증: 합성 일반 테이블·FTS5 2개에서 모든 행 경계 재개 시 ID/내용/순서 동일, 이전 R6 체크포인트와 새 커서 재개, 기존 manifest/부모 코드 결속 통과. 현장 SQLExecutor2 native prepared-bind API는 확인되지 않아 임의 인터페이스를 만들지 않았습니다.
'''
(P/'사용방법과_범위.txt').write_text(note)
archive=P.parent/'gold_fresh_1_jdbc_seek_20261103_r7.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(P.rglob('*')):
  if p.is_file() and '__pycache__' not in str(p):z.write(p,p.relative_to(P.parent))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None;count=len(z.namelist())
put(ART/'r7-package.json',{'path':str(archive.relative_to(ROOT)),'sha256':sha(archive),'bytes':archive.stat().st_size,'files':count,'old_r6_manifest_unchanged':True,'field_executed':False})
print('R7 archive',count,'files',archive.stat().st_size,'bytes; R6 verified unchanged')
