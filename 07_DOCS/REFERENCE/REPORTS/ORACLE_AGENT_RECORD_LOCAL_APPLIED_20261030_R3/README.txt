R3 실제 Oracle 적용 명세 — 2026-10-30

Agent_실제생성_테이블컬럼_R3.xlsx는 Oracle에서 조회해 저장한 실제 메타데이터를 사용한다.
신규 SIDDA Agent3표21컬럼 + 기존 상태1표5컬럼, 총4표26사용자 컬럼이다.
R2 Excel은 적용 전 설계 이력으로 보존한다. 현재 생성 결과는 이 R3를 확인한다.
R2의 원 기록141정의/832컬럼 대응표는 설계 당시 정적 분석이며 실제 데이터 이관 결과가 아니다.

적용·검증 상세:
  09_ARTIFACTS/AUDITS/20261030-agent-record-oracle-r2/적용과_검증결과.txt
실행기:
  06_TOOLS/maintenance/agent_record_oracle_r2.py

로컬 FREEPDB1의 SIDDA에 실제 생성했고 실제 DB검사19개가 통과했다.
실제 RAG의 Oracle 기록 adapter/consumer 연결·기존 기록 이관·NFS 제거는 아직이다.
현재 MAIN125/Gold13표/현장 GENOS/기존 SQLite는 이번 작업으로 전환하지 않았다.
허용량을 확대할 필요 없이 기존 SIDDA300MiB 한도 내 약16.06MiB를 사용한다.

엑셀의 논리명은 후보이고 물리명/타입/인덱스는 실제 로컬 DB 조회값이다.
시간대 인덱스의 내부 숨김 컬럼2개·LOB 내부 인덱스는 Oracle 자동 생성 항목이다.
운영 앱 계정/권한·불변판본·업무 유일성·동시성은 저장 adapter에서 추가 구현/검증해야 한다.
