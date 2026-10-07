# GENOS 전체 코드 ZIP — 2026-09-21

2026-09-28 시간 설정 전체 갱신 인계본은 `genos_code_replace.py --archive`로
기존 `~/DEV`에 매니페스트 파일을 백업 후 적용한다. 아래 새 폴더 해제 설명은
과거 인계 방식이다. 현재 인계에서는 후보 폴더에만 코드를 두지 않는다.
완료 세대·실제 `.env`·Git 이력을 보존하고 실제 적용 파일의 해시를 확인한다.
과거 패치 payload와 9월 25일 붙여넣기 TXT는 전체 ZIP에서 제외하며 원본은 보존한다.
[전체 갱신·검증·원복](GENOS_TIMEOUT_SYNC_20260928.md).

`genosIgnore`는 이 저장소의 코드 ZIP 도구가 읽는 제외 목록이다. Gitignore 문법을
쓰지만 `.gitignore`와 독립적으로 적용한다. GENOS 플랫폼이나 일반 ZIP 프로그램이
자동으로 읽는 파일이라는 의미가 아니다. 지정하지 않으면 기존 도구의 허용목록 방식이다.

## 만들기와 확인

저장소 루트에서 실행한다. 로컬은 WSL의 `.venv/bin/python`을 사용한다.
선택 규칙 해석에는 Git 실행 파일이 필요하며, 실제 저장소 설정·전역 ignore는 사용하지 않는다.

```bash
.venv/bin/python 06_TOOLS/COMMANDS/code_ship.py list --ignore-file genosIgnore
.venv/bin/python 06_TOOLS/COMMANDS/code_ship.py pack --ignore-file genosIgnore --out 90_RUNTIME/OUT/ship/8agent-genos-full-code.zip
.venv/bin/python 06_TOOLS/COMMANDS/code_ship.py verify 90_RUNTIME/OUT/ship/8agent-genos-full-code.zip --python .venv/bin/python
```

`--python`은 선택한 인터프리터로 보존된 과거 코드까지 전부 문법 검사한다.
현장과 같은 Python 3.11을 쓸 때 아래에 기록한 과거 코드 1건으로 실패하며,
이를 전체 ZIP의 Python 3.11 통과로 해석하면 안 된다.

이미 있는 ZIP은 덮어쓰지 않는다. 다시 만들 때는 새 출력 이름을 쓴다.
현재 미커밋·미추적 파일도 제외 목록에 없으면 들어간다. 파일 내용·SHA256·권한과
사용한 제외 목록의 SHA256은 ZIP 안의 `CODE_MANIFEST.json`에 기록한다.
제외된 디렉터리는 순회하지 않으며, 선택된 심볼릭 링크는 오류로 중단한다.
`.git`, 실제 `.env`와 개인키 파일은 제외 목록에서 예외를 줘도 담지 않는다.

## 범위

- 포함: 현재 Python 코드, 웹 화면 CSS/HTML, 엔진·스키마·설정 템플릿, 운영 문서,
  데이터 계약·SourceSet 선언, requirements, 두 ignore 파일.
- 보존하는 고정 의존성: WORKSPACE 활성 영수증이 선택한
  `02_BACKEND/GENERATIONS/20260904-code-v19`와
  `06_TOOLS/GENERATIONS/20260904-code-v19`, 기존 코드 ZIP 계약 호환을 위한
  ADR-0252의 authoring 보조 Python 3개.
  이 선택이 변경되면 두 ignore 파일의 예외도 함께 변경해야 한다.
- 제외: JavaScript 계열(`.js`·`.jsx`·`.mjs`·`.cjs`), 원문·용어·색인 데이터, 배포 릴리스와 실행 결과, 다른 코드 세대·실험 후보,
  실험 실행기·테스트, 보고서·감사 결과·업로드 예시, 기존 ZIP, 모델 가중치,
  가상환경·캐시, Git 이력, 실제 `.env`·키.

원문·용어 데이터와 현장 `.env`는 별도 준비해야 한다. 이 ZIP만으로 용어 데이터나
서빙 세대가 생성되지는 않는다. 새 현장 작업 폴더에서 ZIP을 풀고 설정·데이터를 연결한다.
JavaScript를 제외한 ZIP에서는 웹 뷰어 화면의 동작을 보장하지 않는다. RAG API와
세대 구축·검증 명령을 위한 코드 인계로 사용한다.
기존 폴더에 단순 덮어쓰기하면 구버전 파일이 남으므로 새 폴더를 사용한다.
이 전체 ZIP은 새 폴더 반입용이며 기존 `genos_code_replace.py`의 DELIVERY 설치 묶음과 다르다.
ZIP 반입·Git 커밋/push·GENOS 리비전 배포는 별도 작업이다.

2026-09-22 사용자 요청으로 만든 `8agent-genos-pipeline-workflow-team-env-20260922-r2.zip`은
예외적으로 기존 `~/DEV` 루트에 직접 푸는 메일용 작업판 스냅샷이다.
ZIP 항목이 `service.py`, `02_BACKEND/...`, `06_TOOLS/...`처럼 루트 상대 경로라
`cd -P ~/DEV && python3 -m zipfile -e TRANSFER/<ZIP이름> .`로 포함 파일을 덮어쓴다.
기존 `.env`·`01_DATA`는 ZIP에 없어서 보존된다. ZIP에 없는 구 코드 파일은 남으므로
사전 백업과 설치 후 확인이 필요하다. 디스크 코드 적용과 코드서빙 리비전 배포는 별도다.

## Git과 설치

`.gitignore` 하나를 로컬·GENOS에서 공통 사용한다. 데이터·산출물·비밀값은 Git에 넣지 않고,
현재 실행에 필요한 고정 코드 의존성은 예외로 포함한다. 이미 추적 중인 파일은 ignore를
추가해도 자동으로 Git 이력에서 사라지지 않는다. 이번 작업은 기존 파일 삭제나 이력 변경을 하지 않는다.

```bash
python -m pip install -r requirements.txt
```

주어진 153개 고정 버전이 정본이다. 다른 루트 `requirements-*.txt` 세 개는
`-r requirements.txt`만 참조해 기존 설치 명령을 유지한다. 과거 불변 코드 세대 내부의
requirements와 별도 도구용 OFFLINE requirements는 당시 이력으로 보존한다.
전체 CUDA/Torch 패키지를 포함하므로 코드 ZIP 크기와 설치 후 환경 크기는 별개다.
이번 정리는 실제 패키지 다운로드·의존성 해결·GENOS 설치 성공을 인증하지 않는다.

## 로컬 확인 결과와 제한

2026-09-21 제외 규칙·ZIP 검증·변조 거부·압축 해제 실행·기존 교체 설치기 회귀
테스트 21개가 통과했다. ZIP을 별도 폴더에 풀어 주요 pipeline 도움말, 서비스 import,
현행 genos_preflight와 고정 코드 세대 선택 경로를 확인했다.
requirements는 중복 없는 정확한 버전 고정 153개이며 호환 파일 3개 모두 같은 정본을 참조한다.

Python 3.11.15 문법 검사에서 **현행 Python 파일 580개는 통과**했다.
함께 보존한 고정 코드 Python 314개 중
`02_BACKEND/GENERATIONS/20260904-code-v19/lawrag/core/casereview/pipeline.py:1365`는
f-string 내부 역슬래시 때문에 3.11에서 문법 오류가 난다. 따라서 전체 894개 검사 결과는
실패다. 이 파일은 현재 `02_BACKEND/lawrag` 서비스/구축 코드와 별도인 불변 과거 코드다.
영수증의 해시를 유지하려고 수정하지 않았으며, GENOS Python 3.11에서 이 과거 문서 검토
모듈을 실행 가능한 것으로 취급하면 안 된다. 실제 GENOS 배포·의존성 설치는 미검증이다.
