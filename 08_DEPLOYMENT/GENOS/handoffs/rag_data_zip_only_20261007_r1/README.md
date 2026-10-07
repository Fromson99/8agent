# GENOS 데이터 ZIP 생성 전용 TXT

사용자가 데이터 ZIP 생성만 요청하고 삼성메일 인계를 지시했다. 검증된 NFS R7의
데이터 압축 도구를 해시 그대로 내장한 실행 TXT 한 개를 만들었다.
기존 GENOS DEV/generation/runtime을 읽고 ZIP을 `~/DEV/TRANSFER`에 생성한다.
실행 전 RAG/AD 쓰기는 정상 종료되어 있어야 한다.

```bash
bash "$HOME/DEV/TRANSFER/GENOS_DATA_ZIP_ONLY_20261007_R1.txt"
```

선택 경로는 현장 사진의 generation/runtime 및 별도 state 미설정이다.
현장은 python3를 사용한다. TXT는 원본/기존 checkout 파일을 보존하며,
진행 로그와 EXIT_STATUS를 남긴다. 실제 TXT의 합성 데이터 ZIP 생성·복원,
Git HEAD/staged 변경 보존, SQLite sidecar·내장 해시·누락 경로 실패 처리를
포함한 4개 검사를 통과했다. 실제 GENOS 데이터 ZIP은 현장에서 실행해야 생성된다.

삼성파트너 `hyungjininfocz.son@partner.samsung.com`으로 실행 TXT 한 개를 발송했다.
SENT `1a113a78310df395`에서 수신자와 첨부 이름·14,500바이트를 확인했다.
이 데이터 ZIP 작업에는 본 TXT를 사용한다. 앞선 NFS/조사 제어 반입 이력은 보존한다.

- [실행 TXT](GENOS_DATA_ZIP_ONLY_20261007_R1.txt)
- [파일 및 내장 도구 해시](HANDOFF.json)
- [모의 검증](VALIDATION.json)
- [발송 확인](EMAIL_VERIFIED.json)
