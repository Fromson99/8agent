# GENOS data 경로 (2026-09-09 폴더 메타데이터 패치부터)

설치 코드 루트가 `/home/genos/DEV`인 경우 아래로 고정합니다. `/workspace`가 같은
볼륨의 별칭인 환경에서는 준비 명령이 출력한 실제 경로를 사용하세요.

```text
/home/genos/DEV/data/
├── corpus/
│   ├── internal/                  ← 내규 폴더째 업로드
│   │   └── 영업본부/준법/업무지침/고객관리규정.pdf
│   ├── law/법령제목/              ← 외부 법령 XML
│   ├── krx/규정제목/              ← 거래소 규정 HTML/HWP
│   ├── kofia/규정제목/            ← 금투협 규정 HTML/HWP
│   └── expc/, fsc/, moleg/, prec/  ← 기타 외부 원본
└── builds/실행이름/               ← 새 파생 결과·진행 로그
```

실제 디렉터리를 한층으로 합치거나 파일을 옮기지 않습니다. `internal` 아래 모든 하위
폴더를 재귀적으로 읽습니다. 예시 표시명은 `영업본부 > 준법 > 업무지침 > 고객관리규정`.
원래 문서 제목, 폴더 이름 목록, 평탄화 폴더 경로, 상대 파일 경로, 내규/외규 구분을
`document_metadata`에 별도로 저장합니다. 법령 XML은 원문의 `법령명_한글`을 제목으로 읽고,
그 밖의 파일은 파일명에서 확장자를 뺀 값을 기본 제목으로 쓰며
실제 제목이 다르면 `파일명.pdf.genos.json`에 `{"name":"실제 규정 제목"}`을 지정하세요.
태그의 `folder`는 기존 파서 분류값이며 실제 디렉터리 메타데이터를 지우지 않습니다.
같은 제목의 다른 문서는 경로로 구분되지만 내용까지 완전히 같은 중복 파일은 기존처럼
중복 ID 오류를 냅니다. 숨김 폴더는 제외, 심볼릭 링크는 거절합니다.

폴더+제목은 구조 결과, 원문 SQLite, 추출 작업의 문서명, 최종 DRAFT 문서 표시명으로
전달되고 임베딩 입력에도 붙습니다. 원문 블록/인용 좌표에는 붙이지 않습니다.
폴더명은 검색 맥락이지 법적 효력·사실의 근거가 아니며, 폴더별 접근권한을 구현한 것은 아닙니다.

## 1. 준비 (모델 호출 없음, 최초 한 번)

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_data.sh setup
```

기존 전체 ZIP의 `01_DATA/PACKAGES/EXTERNAL`에 있는 검증된 외규 원본만
`data/corpus`로 복사하고 `internal` 폴더를 만듭니다. 인터넷 재수집이나 과거 LLM 결과
복사는 하지 않습니다. 동일 파일은 재사용하며 충돌 파일은 덮어쓰지 않고 중단합니다.
기존 `GENOS_DATA`는 자동 이동/삭제하지 않으므로 이전 사본만큼 추가 공간이 필요할 수 있습니다.
`01_DATA/PACKAGES/EXTERNAL`, `.env`, Git 및 기존 운영 세대도 삭제하지 마세요.
준비 시 `data/.gitignore`가 없으면 데이터 전체 제외 규칙을 만듭니다. 기존 ignore는 유지합니다.
이미 Git에 추적된 파일에는 ignore가 소급 적용되지 않으며, 이 명령은 Git 이력을 수정하지 않습니다.

기존 안내대로 bootstrap 했다면 외규가 `/home/genos/DEV/GENOS_DATA/corpus`에 있을 수
있습니다. 원래 ZIP에는 문자 그대로의 최상위 `data/` 폴더가 없었습니다. 패키지 manifest의
과거 `data/corpus/...` 문자열과 실제 설치 폴더는 다릅니다. 이 명령 이후 새 위치는 위와 같습니다.

법령·거래소·금투협은 문서 제목 폴더가 맞습니다. 판례/해석례 등은 숫자 ID 폴더도 있습니다.
Jupyter 파일 탐색기로 `DEV/data/corpus/law`, `krx`, `kofia`를 열면 원본을 볼 수 있습니다.

## 2. 내규 업로드 후 실행

`data/corpus/internal/` 아래에 기존 폴더 구조 그대로 넣으세요. 입력 루트 지정 없이:

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_data.sh build \
  --build-dir /home/genos/DEV/data/builds/internal-001 \
  --model-revision genos-deploy-20260909 \
  --embed-batch-size 64
```

`--model-revision`은 운영자가 관리하는 실제 서빙 배포 버전 표식입니다(226 등의 serving ID나
요청 model ID를 바꾸는 옵션이 아님). 태그/등록 형식 선택 → 구조화 → 스키마 추출·검토·
필요 시 재추출 → 64개 이하 배치 임베딩 → 새 DRAFT 적재를 실행합니다.
`setup`은 외규 원본 준비만 하고, 위 `build`는 **내규 폴더 전체**를 처리합니다. 준비됐다는
이유로 외규 전체를 다시 모델에 보내지 않습니다. 외규 본문/첨부를 한꺼번에 섞어 입력하지 마세요.
외규 전체의 출처별 처리 범위는 기존 외규 pipeline 안내를 따릅니다.

이번 패치는 코드와 임베딩 입력 형식이 달라져 기존 빌드에 `--resume`할 수 없습니다.
새 실행이름을 쓰세요. 새 패치로 시작한 작업의 중단 복구에만 동일 명령 끝에 `--resume`.
파일·폴더명·태그·스키마·코드가 바뀌면 새 실행이름으로 재생성합니다.
출력은 `<build-dir>/generation`, 진행은 화면과 `plan.json`, `authoring-status.json`, `result.json`.
기존 서비스에 자동 활성화하지 않으며 실제 GENOS 모델 성공/검색 품질은 현장에서 확인해야 합니다.
