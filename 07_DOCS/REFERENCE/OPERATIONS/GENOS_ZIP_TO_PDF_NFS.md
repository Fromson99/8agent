# GENOS ZIP → PDF: 전처리기 호출과 NFS 현장 기록

기록일: 2026-09-15. 이 대화에서 진행한 Windows 변환 검토, GENOS 전처리기 조사, 스크립트 전달, NFS 확인을 정리한다. 현장 근거는 사용자가 제공한 사진과 설명이다. 외부 Codex에서 내부 서버에 접속하지 않았다.

## 1. 목표와 현재 상태

- 입력: GENOS 프로젝트 `~/DEV/01_DATA/RAW/internal` 아래 ZIP 파일들. 하위 폴더와 중첩 ZIP을 포함한다.
- 처리: 이미 생성한 내부 전처리기의 `http://preprocessor-187:8080/run`을 코드스페이스에서 호출한다.
- 출력: NFS 작업 폴더에서 생성된 PDF와 원본–결과 대응표, 실패 기록.
- MAIN 연결: 독립적인 원문 변환 준비 도구다. 결과는 추후 검토·반입 대상이며 SourceSet, CURRENT, 운영 서빙을 자동 변경하지 않는다.
- 완료: 독립 실행 `.sh` 작성, 로컬 모의 서버 검증, Samsung partner 메일 발송, 코드스페이스 NFS 마운트 사진 확인.
- 최신 현장 결과: DRM 해제 후 DOC 1건에서 `pdf_with_api_warning=1` 확인. PDF 생성·수집은 됐고 후속 전처리는 NLTK `punkt_tab` 데이터 누락으로 실패했다(§11). 이 파일 경로에서 양쪽 파일 처리·PDF 수집 경로가 작동했다. DOCX/HWP 전체 지원·레이아웃 품질·전처리기 리비전은 미확인이다. 아래 초기 미확인 기록은 당시 상태로 보존한다.

## 2. 대화 경위와 판단 변경

1. Windows에서 하위 폴더의 DOCX/HWP를 PDF로 일괄 변환하려고 했다. WSL이 없는 외부 PC여서 PowerShell 스크립트도 준비했다.
2. `.ps1.txt` 확장자 문제 이후 ParserError/UnexpectedToken이 발생했다. 사진에는 스크립트 첫 부분의 `NASCA DRM FILE` 표식과 깨진 문자열이 보였다. 실행 정책 변경만으로 해결되는 문제로 보지 않는다.
3. 사용자가 DRM 해제 후에도 같은 오류를 확인했고, 이후 스크립트 자체에 DRM이 적용된 상태라고 설명했다. 사용자 관찰상 변환 PDF도 생성 즉시 DRM이 적용됐다.
4. ZIP 전달, 메모리에서 처리 후 ZIP 저장 등의 방안을 논의했지만 DRM 회피가 작동한다고 검증한 적은 없다. Windows에서 변환한 뒤 옮기는 방식 대신 GENOS 내부 변환으로 방향을 정했다.
5. LibreOffice 활용과 pip 설치 가능 여부가 논의됐다. 이 최종 도구는 코드스페이스에 LibreOffice를 설치하는 방식이 아니라 이미 배포한 전처리기를 호출한다. Python 표준 라이브러리를 사용하므로 도구 자체의 pip 설치는 없다.
6. GENOS 변환 전처리기 문서와 공개 코드를 찾아 직접 호출 계약을 확인했다. 벡터DB를 거쳐 호출하는 방식은 이 도구에 사용하지 않는다. 처음의 “GENOS에서는 변환 기능이 없을 것”이라는 가정은 전처리기 조사 후 수정됐다.
7. 사용자가 전처리기 생성 및 내부 주소 `http://preprocessor-187:8080`을 알려줬다. 이를 기본 주소로 하는 ZIP 변환 스크립트를 만들었다.
8. 스크립트와 한국어 README를 ZIP으로 묶어 사용자가 지정한 Samsung partner 메일로 보냈다. 원본 Windows용 묶음과 GENOS용 묶음은 별개다.
9. 초기 `/mnt/nfs`, `/data` 안내는 예시였다. 아래 현장 사진에서 확인된 마운트 경로로 구체화한다.

## 3. 현장 사진으로 확인한 데이터·NFS

사용자는 `~/DEV/01_DATA/RAW/internal`로 이동해 내규 하위 폴더들과 ZIP들을 확인했다. 따라서 이번 입력은 현행 RAW/internal 경로다. 과거 `data/corpus/internal` 안내로 되돌려 이동시키지 않는다.

처음 NFS 확인에서 `findmnt -f ...`로 보이는 명령이 입력됐다. 종류 필터는 소문자 `-t`, 특정 폴더의 저장소 확인은 대문자 `-T`다. 이후 사용자가 다음 명령의 결과를 제공했다.

```sh
findmnt -t nfs,nfs4 -o TARGET,SOURCE,FSTYPE
findmnt -T "$HOME/DEV" -o TARGET,SOURCE,FSTYPE
```

사진에서 확인한 마운트:

| 코드스페이스 TARGET | FSTYPE | 확인 범위 |
|---|---|---|
| `/workspace` | `nfs` | SOURCE는 프로젝트 `DEV/volume/176`으로 끝남. `findmnt -T "$HOME/DEV"`도 이 마운트를 반환함 |
| `/nfs-root/diamo` | `nfs` | 프로젝트 작업 볼륨과 별도로 연결된 NFS 경로 |
| `/ext_vol/aiweb_upload` | `nfs` | 별도로 연결된 업로드 볼륨. 이번 변환 출력 대상으로 선택하지 않음 |

`~/DEV`가 `/workspace`의 NFS를 사용한다는 점은 확인됐다. 하지만 이것만으로 `/workspace`가 전처리기에도 같은 위치로 마운트됐다는 뜻은 아니다. `pwd -P`를 확인하지 않았으므로 두 경로의 정확한 별칭/하위 경로 관계까지 단정하지 않는다.

이번 첫 파일 확인용 출력 위치는 `/nfs-root/diamo/8-agent/pdf-output`으로 지정한다. `/nfs-root/diamo` 자체가 코드스페이스에 있다는 것은 확인됐지만 하위 폴더 생성 권한, 전처리기의 동일 경로 접근·쓰기는 아직 미확인이다. 이 선택은 첫 문서 실행으로 확인할 작업 경로이며 현장 성공 기록이 아니다.

## 4. 스크립트 위치와 첫 실행 명령

전달한 `genos-zip-to-pdf.zip`을 풀고 `genos_zip_to_pdf.sh`를 코드스페이스의 다음 위치에 넣는다.

```text
~/DEV/06_TOOLS/COMMANDS/genos_zip_to_pdf.sh
```

스크립트 자체는 전처리기에 업로드할 필요가 없다. 원본 ZIP도 internal에 그대로 두면 된다. 스크립트가 변환 대상 문서를 NFS 작업 폴더로 추출한다.

먼저 한 문서만 처리한다. `cd` 실패 시 다른 폴더에서 실행하지 않도록 `&&`로 연결했다.

```sh
cd "$HOME/DEV" &&
sh 06_TOOLS/COMMANDS/genos_zip_to_pdf.sh \
  "$HOME/DEV/01_DATA/RAW/internal" \
  /nfs-root/diamo/8-agent/pdf-output \
  --limit 1
```

유효한 PDF가 생기고 결과가 정상일 때 전체 실행:

```sh
cd "$HOME/DEV" &&
sh 06_TOOLS/COMMANDS/genos_zip_to_pdf.sh \
  "$HOME/DEV/01_DATA/RAW/internal" \
  /nfs-root/diamo/8-agent/pdf-output
```

기본 전처리기 주소는 이미 설정돼 있다. `sh`로 실행하므로 chmod는 필요 없다. Python 3가 있어야 한다. 별도 API 키/환경변수는 기본 계약에서 사용하지 않는다. 배포 환경이 인증을 요구한다면 해당 인증 계약에 맞춘 변경이 필요하다.

입력 폴더에서 ZIP을 재귀 탐색한다. ZIP 밖에 이미 풀려 있는 DOCX/HWP를 직접 탐색해 변환하는 기능은 현재 스크립트에 없다. ZIP 내부 기존 PDF는 확인 후 복사한다. 첫 문서가 기존 PDF라면 복사만 수행하므로 `converted` 및 `request_started` 기록으로 실제 전처리기 호출 여부를 확인해야 한다.

## 5. API와 파일 경로 계약

```http
POST http://preprocessor-187:8080/run
Content-Type: application/json

{"file_path":"/nfs-root/diamo/8-agent/pdf-output/run-.../work/doc-.../source.docx","params":{}}
```

- `/run`은 파일 업로드 API가 아니다. 서버가 읽을 수 있는 파일 경로를 전달한다.
- 공개 구현의 응답은 `code`, `errMsg`, `data` JSON이다. PDF 바이너리를 직접 내려주지 않는다.
- 스크립트는 입력 옆 `source.pdf`를 찾아 `pdf/`에 모은다. HTTP/API 성공만으로 PDF 성공 처리하지 않는다.
- 전체 전처리가 호출되므로 이미지·설정에 따라 PDF 변환 뒤 파싱/OCR 등이 이어질 수 있다. 변환 전용 옵션을 임의로 가정하지 않는다.
- 전처리기가 같은 저장소를 다른 경로로 마운트했다면 `--remote-root`에 전처리기 측의 **동일 출력 폴더** 경로를 준다. 이 옵션은 마운트 생성·파일 업로드 기능이 아니다.

예를 들어 코드스페이스 `/nfs-root/diamo/8-agent/pdf-output`이 전처리기에서 `/data/diamo/8-agent/pdf-output`으로 보인다고 실제 확인됐을 때만 다음 옵션을 붙인다.

```sh
--remote-root /data/diamo/8-agent/pdf-output
```

해당 `/data/diamo`는 경로 대응 설명용 예시이며 확인된 현장 경로가 아니다.

## 6. 결과·실패·재실행

실행마다 `/nfs-root/diamo/8-agent/pdf-output/run-날짜-식별자/`를 새로 만든다.

- `pdf/`: 원래 파일명과 고유 식별자를 붙인 결과 PDF.
- `manifest.jsonl`: ZIP/내부 경로/추출 파일/원본 SHA-256/PDF SHA-256/처리 결과 대응표.
- `summary.json`: 처리 수와 중단 여부.
- `run.json`: 실행 주소와 옵션.
- `work/`: 추출 원본, 전처리기 산출물, `response.json`. 내부 문서가 포함될 수 있으므로 GENOS 안에서 취급한다.

결과 분류:

| 상태 | 의미 |
|---|---|
| `converted` | API 성공과 실제 PDF 확인 |
| `existing_pdf` | ZIP에 이미 있던 PDF 복사. 변환 API 검증 아님 |
| `pdf_with_api_warning` | PDF 생성 확인, API 오류 또는 응답 규약 미확인 |
| `failed` | PDF 미생성/손상, ZIP 오류 등 |
| `pending` | 연결 단절/시간 초과 등으로 서버 완료 여부 불명 |
| `ignored` | 대상이 아닌 확장자 |

기본 제한: 파일당 512 MiB, 총 추출 10 GiB, ZIP 항목 100,000개, 중첩 ZIP 3단계, 문서 요청 시간 제한 900초. `--help`로 조정한다. 지원 요청 대상에 DOCX/HWP/HWPX 등이 있어도 배포된 변환 백엔드가 해당 형식을 지원한다는 보장은 없다.

`PermissionError`이면 해당 NFS 폴더의 계정/그룹 쓰기 권한을 확인한다. 임의로 전체 볼륨 권한을 바꾸지 않는다. `no_valid_sidecar_pdf`이면 `work/*/response.json` 및 전처리기의 공유 경로·변환 백엔드·PDF 저장 위치를 확인한다. HTTP 401/403은 인증, 404/405는 API 경로를 확인한다.

시간 초과, HTTP 5xx, 수동 중단 뒤에는 서버 작업이 계속될 수 있다. 작업 폴더를 보존하고 완료 여부를 확인한 후 재실행한다. 자동 재시도나 이어하기는 없다. 재실행은 새 실행 폴더를 만들며 먼저 성공한 문서도 다시 처리한다. 원본 ZIP과 이전 결과는 덮어쓰지 않는다. 실행 중인 작업의 work 폴더를 지우지 않는다.

PDF 검사는 헤더/EOF 확인 수준이다. 페이지 누락, 글꼴, 표와 레이아웃은 실제 결과를 열어 확인해야 한다. 검증한 결과를 후속 문서 구조화 단계에 반입하는 절차는 별도이며 이 도구가 자동 수행하지 않는다.

## 7. 전달 산출물과 검증 근거

- 외부 작성본: `/home/jin/docs-to-pdf/genos-zip-to-pdf/genos_zip_to_pdf.sh`
- 전달 ZIP: `/home/jin/docs-to-pdf/genos-zip-to-pdf.zip`
- 포함 파일: `genos_zip_to_pdf.sh`, `README_KO.md`
- 스크립트 SHA-256: `1352f1de6d1b4a3a37917783ced7bac2e2ab956fee4ca290a0924f288485a797`
- ZIP SHA-256: `24e16ba37a4b98e7609d47a443791a765e140c80ee0e3891a8e9e5962bfdc9c1`
- Samsung partner 발송은 완료됐으나 해당 ZIP에는 이후 작성한 이 현장 기록이 포함돼 있지 않다. 이 기록은 별도 파일이다.
- 현재 문서 작업은 기존 전달 ZIP/스크립트나 현장 실행본을 수정하지 않는다.
- 로컬 모의 서버 검증: 중첩 ZIP, 한글 이름, 동명 문서 분리, 경로 대응, 기존 PDF, API 성공/PDF 미생성, API 오류/PDF 생성 경고, ZIP 경로 이탈 거절, 지연 시 중단·작업 보존, 처리 개수 제한, 인증 오류 중단.
- 이 검증은 실제 문서 변환 엔진 검증이 아니며, 현장 DOCX/HWP 품질 또는 전처리기 187의 상태를 보장하지 않는다.

## 8. 공식 문서와 출처

- [GENOS v1.8.6 공유 볼륨 생성](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/development/code_space/share_volume): 개발 → 공유 볼륨 메뉴와 공유 저장소 사용 설명.
- [코드스페이스 생성](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/development/code_space/create_code_space): 생성 시 공유 볼륨 선택.
- [전처리기 관리](https://genos-docs.gitbook.io/default/v1.8.6/admin-management/settings/resource/preprocessor): 생성·코드·파라미터·배포 설명. 확인한 문서에는 코드스페이스 볼륨이 전처리기에 자동 공유된다고 명시되지 않았다.
- [공개 `/run` 구현](https://github.com/genonai/doc_parser_code_serving/blob/aa610c3db24aaa02c65e953279f1a60d014babaf/genon/preprocessor/src/main.py).
- [공개 변환 구현](https://github.com/genonai/doc_parser_code_serving/blob/aa610c3db24aaa02c65e953279f1a60d014babaf/genon/preprocessor/facade/convert_processor.py). 고정 공개 커밋은 현장 배포 리비전과 동일하다고 확인되지 않았다. 이전 GitBook 예제와 최신 공개 코드의 HWP/HWPX 지원 설명에 차이가 있어 현장 이미지 기준으로 판단한다.
- [우리 RAW 데이터 안내](../../../01_DATA/README.md), [4단계 운영 안내](GENOS_FOUR_STAGE.md).
- 현장 마운트 증거: 이 대화에 첨부된 `DBE4CA08-3D8F-426C-B958-A87D08CD8242/1-사진-1.jpg`. 외부 세션의 임시 첨부 경로이므로 영구 저장/현장 접근 가능하다고 가정하지 않는다. 필요한 마운트 사실은 위 표로 전사했다.

## 9. 첫 현장 실행: DOCX 1건 실패

후속 사진 `B04D22C5-F9FB-4B5E-B9F1-163D96CB6F92/1-사진-1.jpg`에서 확인했다.

- 실행 폴더: `/nfs-root/diamo/8-agent/pdf-output/run-20260915T062432Z-a570be4a`.
- 입력 ZIP: `/workspace/01_DATA/RAW/internal/1. 상위규정.zip`으로 표시됨.
- 첫 대상은 ZIP 안의 DOCX. `archive_started=1`, `request_started=1`, `failed=1`, `documents=1`, `stopped=false`, `limited=true`.
- 코드스페이스에서 NFS 실행 폴더 생성 및 DOCX 추출은 가능했다. 전처리기 측의 파일 읽기·쓰기 권한까지 확인된 것은 아니다.
- `request_started`는 요청 직전에 쓰는 기록이다. 이 표시만으로 서버 처리 성공을 판단하지 않는다.
- 스크립트가 인정한 결과 PDF는 없다. summary에는 reason/HTTP 상태/응답 코드가 표시되지 않아 실패 원인은 미확정이다. DRM·NFS·백엔드 중 하나로 단정하지 않는다.

재호출 전에 아래 명령으로 해당 실행의 실패 사유와 API 오류 필드만 확인한다. 전체 응답의 `data`는 출력하지 않는다. 이 명령은 파일을 읽기만 하고 변환을 재실행하지 않는다.

```sh
python3 - <<'PY'
import json
from pathlib import Path
r = Path('/nfs-root/diamo/8-agent/pdf-output/run-20260915T062432Z-a570be4a')
for line in (r / 'manifest.jsonl').read_text().splitlines():
    row = json.loads(line)
    if row.get('status') == 'failed':
        print('reason:', row.get('reason'))
files = list((r / 'work').glob('*/response.json'))
if not files:
    print('response.json: none')
for f in files:
    try:
        body = json.loads(f.read_text())
        print({k: body.get(k) for k in ('code', 'errMsg', 'error_code')} if isinstance(body, dict) else 'Unexpected JSON type')
    except ValueError:
        print('response.json: invalid JSON')
PY
```

다음 현장 기록은 위 reason과 응답 오류를 근거로 원인을 좁힌다. 전체 ZIP 재실행이나 변환 백엔드 교체는 아직 하지 않았다.


## 10. v2: 실패 진단을 sh에 통합

사용자가 오류 확인 코드를 sh에 반영하고 Samsung partner 메일로 수정본 전달을 요청했다. pip 설치 문제 가능성도 제기했으나 현재 현장 응답은 아직 제공되지 않아 원인은 미확정이다.

- v1 스크립트와 ZIP은 보존한다. 수정본 작성 경로: `/home/jin/docs-to-pdf/genos-zip-to-pdf-v2/`.
- 수정본 파일명은 `genos_zip_to_pdf.sh`로 유지한다. 현장에서는 기존 `06_TOOLS/COMMANDS/genos_zip_to_pdf.sh`를 이 파일로 교체한다.
- `--diagnose RUN_DIR` 추가: 기존 manifest/response/http 기록만 읽고 API 호출·파일 변경 없이 오류를 표시한다. v1 기록도 지원한다.
- 변환 실행 시 reason, HTTP 상태, API 오류 필드를 화면에 표시한다. HTTP 오류 응답도 최대 1 MiB 저장하고 `http.json`에 상태 코드를 남긴다.
- 응답의 data/chunk, FastAPI validation의 input/ctx, JSON이 아닌 응답 본문은 화면에 덤프하지 않는다. 오류 문자열은 길이를 제한하고 일부 인증 문자열을 가린다.
- 패키지/import 오류, 변환 백엔드 이름, 파일 없음, 쓰기 권한 오류에 따라 확인 항목을 안내한다. 안내는 원인 확정이나 자동 설치가 아니다.
- 이 sh 자체는 Python 표준 라이브러리만 사용한다. 코드스페이스와 전처리기의 패키지 환경은 별개이므로 전처리기 누락 패키지를 코드스페이스 pip 설치로 해결했다고 판단하지 않는다.

기존 실패 진단 명령:

```sh
cd "$HOME/DEV" &&
sh 06_TOOLS/COMMANDS/genos_zip_to_pdf.sh --diagnose \
  /nfs-root/diamo/8-agent/pdf-output/run-20260915T062432Z-a570be4a
```

로컬 검증: 기존 모의 서버 계약 검사 7개, 추가 진단 검사 3개 통과. 구버전 기록 진단 시 파일 해시 불변, 패키지 오류 안내, 응답 데이터 비출력, 잘못된 JSON 처리, HTTP 422 오류 본문 저장/진단을 확인했다. 현장 패키지 상태·API 오류·변환 성공은 여전히 미확인이다.

v2 스크립트 SHA-256: `478d3b45ca68f03ade822737948d0750285ca1adf3959082d8c7a35d82a4713a`.

v2 ZIP `genos-zip-to-pdf-v2.zip`을 Samsung partner 메일로 발송 완료했다(SENT 확인). 스크립트, README, 발송 직전까지의 이 MD 기록을 포함한다. ZIP SHA-256: `9e715ad7d297625008b3fc5fbcc7535702e4cd1950baeb923609244aa864216e`. 내부 설치·진단 실행 완료를 뜻하지 않는다.

## 11. DRM 해제 후 DOC 1건: PDF 확보, NLTK 데이터 누락

사용자가 ZIP 내부 문서에 DRM이 남아 있었음을 확인하고 해제했다고 보고했다. 이전 DOCX 오류는 `API code: 1`, `Input document source.docx is not valid.`였다. 이 오류 문구만으로 모든 실패의 원인을 DRM이라고 일반화하지 않는다.

이후 첫 문서 재실행 사진 `FE99EFE1-13CB-4F3F-A650-C809B95BC352/1-사진-1.jpg`에서 다음을 확인했다.

- 새 실행: `/nfs-root/diamo/8-agent/pdf-output/run-20260915T064137Z-2d5219c6`.
- 이번 대상은 `이사회규정(170817).doc`이다. 이전 실패 대상 DOCX와 다른 파일이다.
- HTTP 200, API code 1, `Resource punkt_tab not found`, `Attempted to load tokenizers/punkt_tab/english/`.
- `archive_started=1`, `request_started=1`, `pdf_with_api_warning=1`, `documents=1`, `stopped=false`, `limited=true`.
- 스크립트는 PDF 헤더/EOF 확인 후 결과 PDF 복사를 완료했을 때만 `pdf_with_api_warning`을 기록한다. 따라서 이번 문서는 PDF 생성·수집이 확인됐고 API 후속 처리만 오류다. 육안으로 PDF 내용/페이지/글꼴을 검증한 기록은 아직 없다.
- 코드스페이스와 전처리기 사이의 이번 NFS 파일 전달/결과 수집은 작동했다. 전처리기 마운트 설정 전체를 조회하거나 모든 계정/경로 권한을 검증한 것은 아니다.

결과 확인:

```sh
ls -lh /nfs-root/diamo/8-agent/pdf-output/run-20260915T064137Z-2d5219c6/pdf/
```

PDF 결과를 확인한 뒤 전체 ZIP 변환은 §4의 `--limit 1` 없는 명령으로 진행할 수 있다. v2는 이 경고에서 배치를 중단하지 않으므로 이후 문서를 계속 처리한다. 경고가 있으면 최종 종료 코드는 2다. `pdf_with_api_warning`은 PDF 확보 건수에 포함할 수 있지만 전체 전처리 성공으로 계산하지 않는다. 다른 문서에서 `failed`가 발생할 수 있으므로 전체 결과의 상태별 건수를 확인한다.

이번 오류는 NLTK 라이브러리 자체가 없다는 메시지가 아니라 NLTK가 사용하는 별도 `punkt_tab` 데이터가 없다는 메시지다. `pip install nltk`만으로 이 데이터가 채워진다고 보지 않는다. [NLTK 공식 데이터 설치 안내](https://www.nltk.org/data.html)는 라이브러리 설치와 데이터 설치를 구분하고, 수동으로 받은 자료를 적절한 하위 디렉터리에 풀어 `NLTK_DATA`로 지정하는 방법을 제공한다.

망분리 현장에서 전체 전처리까지 고치려면 필요한 데이터 패키지를 승인된 경로로 반입하고, **전처리기 컨테이너**가 읽는 `nltk_data/tokenizers/punkt_tab/english/` 구조를 맞춰야 한다. 사진의 검색 경로에는 `/app/nltk_data`, `/app/.venv/nltk_data`, `/usr/share/nltk_data` 등이 보인다. 다른 디렉터리에 배치하면 전처리기 프로세스의 `NLTK_DATA`를 해당 상위 `nltk_data` 경로로 설정한다. 코드스페이스에서만 설정/설치해도 별도 전처리기 프로세스에 자동 적용되지는 않는다. 이 설치·설정 변경은 아직 실행하지 않았다.

추가 이력: 중간에 DOCX 구조 진단용 v3를 외부에서 작성·모의 검증했으나 사용자가 DRM 원인을 확인하며 재실행으로 전환했다. v3의 ZIP 전달/메일 발송/현장 교체는 수행하지 않았다. 현재 현장 결과 해석은 전달된 v2 기준이다.


## 12. 사용자 PDF 확인·DEV 결과 폴더 정리(v4)

전달 상태: `genos-zip-to-pdf-v4.zip`을 Samsung partner 메일로 발송 완료(SENT 확인). ZIP SHA-256: `208e2404ba7e5aae9d08a3af0855234621b13b2184cac0610283befe6616177f`. 스크립트·README·발송 직전까지의 누적 MD를 포함한다. 현장 교체·실행 완료와는 구분한다.

사용자가 생성된 PDF가 잘 나온다고 확인했다. 확인한 파일에 대한 사용자 품질 확인이며 전체 DOCX/HWP 형식·전수 품질 검증으로 확대하지 않는다. 이어 DEV에서 결과를 보고 결과 경로/파일명을 이해하기 쉽게 해달라고 요청했다.

v4는 현장 사용 중인 v2를 기반으로 `--pdf-dir`과 `--export-run`을 추가한다. 기존 NFS 변환 작업 경로는 유지하고, 사용자 지정 DEV 폴더로 결과를 실제 복사한다. Jupyter에서 NFS 외부 심볼릭 링크를 따라갈 수 있다고 가정하지 않는다.

- 권장 결과: `~/DEV/01_DATA/PDF/internal/<ZIP 이름>/<기존 하위 폴더>/<원래 문서명>.pdf`.
- ZIP 이름과 첫 내부 폴더 이름이 같으면 그 중복 한 단계를 줄인다.
- 같은 위치의 같은 PDF 해시는 재사용한다. 내용이 다른 동명 파일은 `(2)` 등 번호로 보존한다. 매우 긴 파일명만 길이를 제한한다.
- 대응 기록은 결과 폴더 `.conversion/exports.jsonl`에 남긴다. NFS run/manifest/work와 원본 ZIP은 유지한다.
- `--export-run`은 기존 완료 실행에서 PDF를 복사하며 API를 호출하지 않는다. `--pdf-dir`을 일반 변환 명령에 추가하면 배치 종료 후 PDF를 복사한다.
- NFS 결과와 DEV 복사본이 함께 존재해 저장 공간을 추가 사용한다. `01_DATA/PDF`는 이번 요청의 파생 파일 표시 위치이며 RAW/SourceSet/CURRENT/MAIN에 자동 반영하지 않는다.
- v3의 미전달 진단 확장은 v4에 포함하지 않는다. v1/v2 ZIP과 외부 작성본은 보존한다.

이미 생성한 결과 정리:

```sh
cd "$HOME/DEV" &&
sh 06_TOOLS/COMMANDS/genos_zip_to_pdf.sh \
  --export-run /nfs-root/diamo/8-agent/pdf-output/run-20260915T064137Z-2d5219c6 \
  --pdf-dir "$HOME/DEV/01_DATA/PDF/internal"
```

앞으로 전체 ZIP 변환:

```sh
cd "$HOME/DEV" &&
sh 06_TOOLS/COMMANDS/genos_zip_to_pdf.sh \
  "$HOME/DEV/01_DATA/RAW/internal" \
  /nfs-root/diamo/8-agent/pdf-output \
  --pdf-dir "$HOME/DEV/01_DATA/PDF/internal"
```

로컬 모의 서버에서 기존 변환/진단 회귀, 자동 DEV 복사, 폴더·이름 보존, 동명 충돌, 중첩 ZIP, 반복 복사 재사용, 원본 불변, 저장 PDF 해시 변경 거절, 경로 이탈/심볼릭 링크 거절을 확인했다. v4 현장 실행은 아직 미확인이다.

v4 스크립트 SHA-256: `ad11145017473850178d46439005a7b90e7ef4694fee92fa4db041df3ad050eb`.

## 13. 전체 실행에서 DOCX 여러 건: API 성공, PDF 없음

후속 사진 `1B3B209D-8982-41C2-B0E6-9BDF3E76735D/1-사진-1.jpg`에서 DOC 1건의 `pdf_with_api_warning` 뒤 여러 DOCX가 다음 상태로 이어지는 것을 확인했다.

- HTTP status 200, API code 0, errMsg success.
- 스크립트 상태는 `failed`, reason은 `no_valid_sidecar_pdf; check shared mount and conversion backend`.
- 첫 DOC의 PDF 확보와 여러 DOCX의 PDF 미생성을 구분한다. DOCX의 API 성공은 PDF 파일 저장 성공의 증거가 아니다.
- NFS에서 DOC의 결과를 수집한 이력이 있어 공통 마운트 전체 불통으로 단정하지 않는다. DOCX 변환 분기, 실제 변환 백엔드, 저장 위치, 파일별 권한 등을 우선 확인한다. DOC의 punkt_tab 오류와 이번 DOCX의 PDF 미생성은 서로 다른 관측이다.
- 같은 증상이 반복되는 전체 실행은 Ctrl+C 중단을 안내했다. 중단된 서버 요청이 계속 처리될 수 있으므로 작업 폴더를 보존한다. 실제 중단 완료 여부는 아직 사용자에게 확인받지 않았다.

공식 GitBook v1.8.6 변환 전처리기 설명에는 DOCX/PPTX에서 `convert_to_pdf(file_path)` 호출이 있다. 앞서 확인한 공개 고정 리비전의 함수는 변환 실패 시 None을 반환할 수 있고, 호출부는 그 반환값을 확인하지 않은 채 후속 처리를 진행한다. 따라서 그 구현에서는 PDF 변환 실패와 API 성공이 동시에 나타날 수 있다. 이 설명이 현장 실패의 확정 원인이라는 뜻은 아니다. 현장 이미지/등록 코드가 공개 소스와 같은지 아직 확인되지 않았다.

현재 필요한 추가 근거는 **전처리기 187에 실제 등록한 코드의 `convert_to_pdf` 함수 및 DOCX 처리 부분**, 가능하면 해당 문서 처리 시의 변환 로그다. 호출 sh의 성공 판정을 완화하거나 전체 반복 실행, 코드스페이스의 임의 pip 설치로 해결됐다고 처리하지 않는다. 전처리기 등록 코드에서 변환 명령/반환 코드/저장 경로를 확인한 뒤 필요한 수정을 준비한다.

## 14. 현장 convert_to_pdf 함수 사진과 교체 패치

사용자가 `A53BB95E-310A-41D4-8110-B0D98B376B67/1-사진-1.jpg`로 함수를 제공했다. 사진에서 DOC/DOCX writer PDF 필터, subprocess.run, stderr 출력, 실패 시 None 반환, 비ASCII 임시 복사 분기를 확인했다. 고유 UserInstallation 프로필과 timeout은 보이지 않았다. 기존 sh는 ASCII `source.docx`를 보내므로 비ASCII 결과명 불일치를 이번 실패의 확정 원인으로 보지 않는다. 프로필 충돌도 아직 가설이다.

교체 함수를 `/home/jin/docs-to-pdf/genos-preprocessor-pdf-fix/convert_to_pdf_replacement.py`에 작성했다. sh가 아닌 **전처리기 187 등록 코드의 해당 함수만** 교체하는 자료다. 전체 전처리기 소스/실제 리비전은 아직 받지 않았으며 외부에서 직접 배포하지 않았다.

변경 내용: 요청별 로컬 임시 복사/독립 프로필, 명시적 변환 필터, timeout 및 본인 프로세스 그룹 종료, stdout/stderr/종료 코드 로그, PDF 확인 후 NFS sidecar 복사, 원본/PDF 해시, 기존 출력 보존. 실패 시 None 대신 `GENOS_PDF_FIX_1` 표식을 포함한 RuntimeError를 발생시키는 **의도적 계약 변경**이며 호출부가 잡아 숨기는지는 추가 확인이 필요하다. 로그도 NFS 입력 옆에 남긴다.

실제 오류가 실행 파일/필터/시스템 라이브러리 누락이면 이 패치가 패키지를 설치해서 해결하지는 않는다. 진단 결과를 보고 전처리기 이미지를 수정해야 한다. 기존 DOC의 NLTK punkt_tab 누락과 별개다.

로컬 모의 실행 파일로 subprocess 실행, 한글 경로, 결과 수집, 기존 출력 보존, PDF 미생성/오류 종료/표준출력 전달, timeout 정리, 동시 독립 프로필, 실행 파일 부재를 검증했다. 현장 LibreOffice 렌더링과 패치 적용은 미확인이다. README에는 백업·함수 교체·저장/재배포·리비전 확인·롤백과 v4 sh의 `--limit 2` 확인 명령을 담았다. 사진의 DOC 다음 DOCX 순서를 이용하며 실제 처리 확장자를 확인하도록 했다.

교체 함수 ZIP `genos-preprocessor-pdf-fix.zip`을 Samsung partner 메일로 발송 완료(SENT 확인). SHA-256: `19837e0973c3270c88b50c394a87322fb6f480bcd07a53ea53e7b18c2cd89c44`. 함수 파일과 적용/롤백 README를 포함한다. 현장 적용·성공 완료를 뜻하지 않는다.

## 15. 제약 확인: 전처리기 코드는 사용자 수정 불가

사용자가 전처리기 코드는 본인이 작성한 것이 아니며 수정할 수 없다고 명확히 밝혔다. 따라서 §14의 교체 함수는 **적용 대상에서 제외**한다. 발송한 패치가 현장 적용됐다고 기록하지 않는다. 이후 작업에서 전처리기 소스 변경·재배포를 사용자에게 전제하지 않는다.

대안으로 코드스페이스에 이미 설치된 LibreOffice를 직접 호출해 DOC/DOCX를 PDF로 변환하는 경로를 검토한다. 이는 전처리기 호출 경로와 별개이며 코드스페이스의 실제 실행 파일·설치 권한·오프라인 패키지 확보 여부는 미확인이다. 전처리기에서 soffice가 실행됐다는 사실이 코드스페이스에도 설치됐다는 뜻은 아니다.

현장에서 먼저 실행할 읽기 전용 명령:

```sh
command -v soffice || command -v libreoffice
```

경로가 나오면 코드스페이스 직접 변환을 준비할 수 있다. 없다면 LibreOffice가 포함된 코드스페이스 이미지 또는 현장 OS에 맞는 오프라인 설치가 필요하다. 이 도구는 Python pip 패키지만으로 대체된다고 가정하지 않는다. HWP/HWPX 지원은 별도 백엔드/샘플 검증이 필요하다.

현재 확인한 v1.8.6 문서와 제공된 함수에는 호출 JSON만으로 DOCX PDF 생성을 보장하는 `pdf_only`/`convert_only` 옵션이 확인되지 않았다. 숨은 파라미터·확장자 위장 등을 해결책으로 제시하지 않는다. 기존 서비스를 계속 활용하려면 운영자가 제공하는 별도 PDF 변환 API나 해당 전처리기의 오류 수정을 요청하는 경로가 남아 있다.

근거: [LibreOffice 공식 CLI](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html)의 headless/convert-to/outdir. 이 대안은 아직 구현·설치·현장 변환을 완료한 상태가 아니다.

## 16. 추가 설치 불가·유지보수팀 이관 요청

사용자가 LibreOffice도 설치할 수 없다고 확인하고, 정확한 진단 자료를 유지보수팀에 넘기기를 요청했다. 따라서 사용자 측 전처리기 수정·LibreOffice 설치·직접 변환 전환은 진행하지 않는다.

[유지보수 요청서](GENOS_PDF_MAINTENANCE_REQUEST.md)를 작성했다. DOC의 NLTK punkt_tab 조회 실패와 DOCX의 API 성공/PDF 미확보를 별도 장애로 분리하고, 확인된 사실·가설·미확인 배포 정보·요청할 서버 로그·완료 기준을 정리했다. DOCX의 근본 원인은 실제 전처리기 측 호출 여부/argv/returncode/stdout/stderr/산출물 경로를 확인해야 확정된다. API code=0이 PDF 생성까지 보장하는 공식 계약인지도 유지보수팀에 확인하도록 했다.

외부 작성본 `/home/jin/docs-to-pdf/genos-pdf-maintenance/collect_pdf_evidence.sh`는 현장 기존 run 로그를 읽어 샘플별 시각·경로·해시·오류·DOCX 컨테이너 기본 상태를 수집한다. 설치·API 호출·원본 변경 없이 별도 출력 폴더에 SUMMARY.md/evidence.json ZIP을 생성한다. 원본 문서/PDF 바이트와 전체 응답 data는 제외한다. 파일명/경로/해시·오류는 포함하므로 GENOS 내부 유지보수 자료로 취급한다.

```sh
cd "$HOME/DEV" &&
sh 06_TOOLS/COMMANDS/collect_pdf_evidence.sh \
  /nfs-root/diamo/8-agent/pdf-output \
  "$HOME/DEV/01_DATA/LOGS/pdf-maintenance"
```

로컬 모의 기록으로 원본 파일 해시 불변, 부분 기록 처리, 샘플 메타데이터, ZIP 내 문서/응답 본문 비포함, 구버전 HTTP 기록 없음, DRM 표식/원본 해시 변경 보고를 확인했다. 내부 실제 증거 수집 실행은 아직 사용자 수행 전이다. 유지보수팀 수신 주소는 제공되지 않았으므로 직접 발송하지 않으며 사용자 partner 메일에 전달용 자료를 보낸다.

`genos-pdf-maintenance.zip`을 사용자 Samsung partner 메일로 발송 완료(SENT 확인). 유지보수팀 직접 발송은 하지 않았다. ZIP SHA-256: `fb7d65d2c7f174c4f6829234893ea0e3d2122e397178d11bdcf753f3eafeed0a`. 장애 요청서와 증거 수집 sh를 포함하며 실제 현장 증거 ZIP은 사용자가 위 명령으로 생성해야 한다.

## 17. 수집 명령 인자 오류·추가 uri 예외

사진 `62D13DE1-8F79-4E48-9C31-2D733EAD73CE/1-사진-1.jpg`에서 수집 명령에 원본 internal, NFS 실행 루트, 증거 출력의 세 경로를 전달해 unrecognized arguments가 발생했다. 수집기는 runs와 output의 두 위치 인자만 받으므로 internal 경로를 제거하는 명령을 안내한다. 아직 수집 완료가 아니다.

또한 전체 실행 ID `run-20260915T065449Z-9218fd91`과 HTTP 200/API code 1의 `'NoneType' object has no attribute 'uri'`를 확인했다. request_started/documents 21, PDF 경고 확보 1, failed 19, 수동 중단 1이다. 나머지 1건의 서버 완료 상태는 불명이다. DEV 복사 1건은 확인됐다. 유지보수 요청서 §9에 이 관측과 traceback 요청을 추가했으며, uri 오류를 특정 원인으로 추측하지 않았다. 기존 발송 ZIP에는 이 후속 기록이 포함돼 있지 않다.


## 18. 현장 SUMMARY.md 생성과 샘플 검사 값 확인

사용자가 SUMMARY.md 사진 4장을 제공했다. 요약 생성은 확인됐으나 외부 세션에서 전체 evidence.json/ZIP 파일을 직접 열어본 것은 아니다. 과거 실행 파일의 NASCA 표식 true/ZIP false, 이후 DOC의 NASCA false/OLE true/PDF 헤더·EOF true, 전체 실행 DOCX 샘플의 NASCA false/ZIP true/추출 시점 해시 일치를 확인했다. DOCX 필수 항목 전체와 현시점 PDF 확인 부분은 사진 하단에서 잘렸으므로 추정하지 않았다.

유지보수 보고서 §10에 관측값·한계·전달용 요약을 보완했다. 과거 DRM 실행 기록이 남아 있다는 사실을 사용자 해제 실패나 현재 전체 재암호화로 해석하지 않는다. 현재는 추가 변환/설치 없이 기존 증거 ZIP과 보완 보고서로 서버 측 LibreOffice 로그·저장 위치·NoneType.uri traceback·NLTK 경로 확인을 요청하는 단계다.


## 19. 전처리기 컨테이너 traceback 수신

사용자가 전처리기 187의 컨테이너 로그 사진 2장을 제공했다(ACE41E4D-15DE-49EC-A179-2F4E93561748). `/app/src/preprocessor.py:291`, set_media_files의 `path = str(item.image.uri)`에서 item.image가 None이어서 실패하는 직접 원인을 확인했다. 호출 경로는 main.py:57 → preprocessor.py:1494(docx_processor) → :1078(compose_vectors) → :1054(set_media_files) → :291이다.

직전 EMF(image/x-emf) Wand decode delegate 실패와 Pillow 이미지 로드 실패가 반복된다. EMF 처리 실패로 None 이미지 참조가 남았을 가능성은 높지만 같은 doc_item 매칭은 미확인이다. 427>256, 295>256 토큰 길이 경고도 있으나 실제 예외 traceback은 None.uri이다. Docling Finished converting 로그는 LibreOffice PDF 저장 성공을 뜻하지 않는다.

유지보수 보고서 §11과 첫 요약에 직접 원인·선행 오류·가설·서버 수정 요청을 반영했다. API code0/PDF 미확보 사례 전체와 이 code1 예외를 같은 원인으로 합치지 않는다. NLTK punkt_tab도 별도다. 사용자 설치/전처리기 변경 없이 유지보수팀 조치를 요청하는 상태를 유지한다.

## 20. 2026-09-15 v5 클라이언트 DOCX 분기 우회 — 현장 미검증

사용자가 보고서 메일 중단과 실행 SH 수정을 요청했다. 공식 attachment_processor 문서의 DOCX 전용 분석 경로와 DOC의 선행 PDF 변환 경로를 확인했다. v5는 원본 ZIP/source.docx를 보존하고 동일 바이트의 source.doc 작업 복사본을 `/run`으로 전송한다. 실제 DOC 재인코딩이 아니며 이미지 삭제도 없다. 서버의 자동 형식 인식 호환성은 현장 미확인이다. 기존 확장자 위장 배제 판단은 이 분기 근거 확인 전 기록이며, v5에서는 우회임을 명시하고 선택적으로 되돌릴 수 있게 했다.

산출물: `/home/jin/docs-to-pdf/genos-zip-to-pdf-v5/genos_zip_to_pdf_v5.sh`, `/home/jin/docs-to-pdf/genos-zip-to-pdf-v5.zip`. `--extensions docx --limit 1`로 DOCX 한 건부터 확인한다. `--docx-route native`로 기존 요청 경로 복구. DOCX 우회 후 PDF 미확보 시 큐 중단. DOCX ZIP/필수 항목/CRC 검사, 요청 복사본 해시 기록, 기존 DEV 경로 내 PDF 내보내기 유지.

로컬 모의 API에서 바이트·이미지 보존, 분기 요청, 실패 중단, 경고 PDF 내보내기 및 기존 회귀 검사 통과. 실제 GENOS/LibreOffice 렌더링 검증과 서버 코드 수정·배포는 하지 않았다. 서버의 NLTK/EMF/None.uri 오류를 수리한 것으로 보고하지 않는다.
