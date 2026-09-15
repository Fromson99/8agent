# [장애 확인 요청] GENOS 전처리기 187 — DOCX PDF 미확보 및 NLTK punkt_tab 조회 실패

## 1. 요청 요약

**최신 서버 로그 확인(§11):** 일부 DOCX의 `NoneType.uri` 예외는 `/app/src/preprocessor.py:291`의 `set_media_files`에서 `item.image`가 None인데 `.uri`를 읽어 발생한 것으로 확인됐습니다. 직전 EMF 이미지 디코딩 실패가 반복됩니다. 이 직접 실패 위치는 확정됐지만 API 성공/PDF 미확보 전체와 동일 원인인지는 아직 확인되지 않았습니다.

GENOS 코드스페이스에서 내부 전처리기 `http://preprocessor-187:8080/run`을 호출해 DOC/DOCX/HWP 원문을 PDF로 확보하려고 합니다. 현재 DOC 1건은 PDF가 생성됐으나 후속 NLTK 처리 오류가 발생했고, 여러 DOCX는 API 성공 응답에도 예상 위치에서 유효한 PDF를 확보하지 못했습니다.

사용자는 전처리기 등록 코드를 수정할 수 없고 코드스페이스에 LibreOffice를 설치할 수도 없습니다. **사용자 측 설치·전처리기 코드 변경 없이, 유지보수팀에서 실제 배포 인스턴스 기준으로 원인 분석 및 지원 가능한 해결 경로 안내를 요청합니다.**

근거는 사용자 제공 현장 사진·로그와 함수 사진입니다. 외부 작성자는 GENOS 내부 인스턴스에 접근하지 않았습니다. 아래에서 관측 사실과 원인 가설을 구분합니다. 첨부한 별도 수집 도구를 현장에서 실행하면 상세 실행 ID/경로/해시/선별 오류 기록을 보완할 수 있습니다.

## 2. 환경과 호출 계약

| 항목 | 확인 내용 |
|---|---|
| 실행 위치 | GENOS 코드스페이스/Jupyter 터미널 |
| 사용자 프로젝트 | `~/DEV`; `findmnt -T "$HOME/DEV"` 결과 `/workspace`, FSTYPE `nfs` |
| 내부 원본 | `~/DEV/01_DATA/RAW/internal`의 ZIP 및 하위 폴더 |
| 전처리기 주소 | `http://preprocessor-187:8080` |
| 요청 | `POST /run`, JSON `file_path`와 `params` |
| 변환 작업 저장소 | `/nfs-root/diamo/8-agent/pdf-output/run-.../work/doc-.../` |
| NFS 확인 | 코드스페이스에서 `/workspace`, `/nfs-root/diamo`, `/ext_vol/aiweb_upload` 마운트 확인 |
| 클라이언트 | `genos_zip_to_pdf.sh`; Python 표준 라이브러리로 ZIP 추출·API 요청·산출물 수집 |
| 사용자 결과 위치 | v4 선택 시 `~/DEV/01_DATA/PDF/internal`로 원래 폴더·파일명에 맞춰 복사 |
| 미확인 | 전처리기 이미지 digest/리비전, 등록 코드와 실행 코드 일치, 전체 마운트 설정, 실행 UID/GID, LibreOffice/NLTK 버전 |

요청 형태:

```http
POST http://preprocessor-187:8080/run
Content-Type: application/json

{"file_path":"/nfs-root/diamo/8-agent/pdf-output/run-<ID>/work/doc-<ID>/source.docx","params":{}}
```

원문 바이트를 HTTP로 업로드하지 않고 공유 파일 경로를 전달합니다. 클라이언트는 입력 파일과 같은 디렉터리의 `source.pdf`를 확인합니다. PDF 헤더 `%PDF-`와 끝부분 `%%EOF` 확인 후 결과 폴더로 복사합니다. 이 검사는 PDF 내용/레이아웃의 완전성 검사와는 다릅니다.

**계약 확인 요청:** `/run`의 `code=0`은 문서 파싱/전처리 성공만 뜻하는지, DOCX의 PDF 생성도 보장하는지 명확히 알려주세요. PDF가 다른 경로/스토리지에 저장되는 설계라면 공식 산출물 경로 또는 다운로드 API를 요청합니다. 현재 관측만으로 API 전체가 규약 위반이라고 단정하지 않습니다.

## 3. 장애 A — DOC의 NLTK 데이터 조회 실패 (직접 원인 확인)

확인 실행:

```text
/nfs-root/diamo/8-agent/pdf-output/run-20260915T064137Z-2d5219c6
```

해당 실행 ID의 UTC 시작 시각은 2026-09-15 06:41:37(한국 시각 15:41:37)입니다. 파일: `이사회규정(170817).doc`.

관측 로그:

```text
HTTP status: 200
API code: 1
Resource punkt_tab not found.
Attempted to load tokenizers/punkt_tab/english/
pdf_with_api_warning: 1
```

- 이번 DOC의 PDF 생성·복사는 확인됐으며 사용자가 PDF가 정상으로 나온다고 확인했습니다.
- NLTK가 실행 프로세스의 데이터 검색 경로에서 `punkt_tab`을 찾지 못한 사실은 확인됩니다.
- 이는 `nltk` Python 패키지 자체의 import 실패와 다릅니다. 데이터 미배포, 검색 경로 불일치, 접근 권한 등 **왜 조회하지 못하는지**는 서버에서 확인이 필요합니다.
- 사진에 표시된 검색 경로에는 `/app/nltk_data`, `/app/.venv/nltk_data`, `/app/.venv/share/nltk_data`, `/usr/share/nltk_data`, `/usr/local/share/nltk_data` 등이 있습니다.
- 실제 전처리기 프로세스와 동일한 실행 사용자·Python 환경에서 NLTK 버전, `nltk.data.path`, `nltk.data.find('tokenizers/punkt_tab/english/')` 결과를 확인해주세요.
- 필요한 데이터가 이미지/볼륨에 포함돼 있는지, 재배포 후에도 보존되는지, `NLTK_DATA` 설정 및 읽기 권한이 맞는지 확인해주세요. 망분리 환경이므로 외부 다운로드를 런타임에 전제하지 않는 배포가 필요합니다.

## 4. 장애 B — DOCX API 성공과 PDF 산출물 불일치 (근본 원인 미확정)

전체 처리 사진에서 여러 DOCX가 반복적으로 아래 상태를 보였습니다.

```text
HTTP status: 200
API code: 0
errMsg: success
failed
reason: no_valid_sidecar_pdf; check shared mount and conversion backend
```

예시 문서: 지배구조 내부규범 DOCX, 리스크관리위원회규정 DOCX의 여러 버전. 후속 사진에서 전체 실행 ID는 `run-20260915T065449Z-9218fd91`로 확인됐습니다. 정확한 요청 시각/파일명/원문 해시는 현장에서 생성한 `SUMMARY.md`와 `evidence.json`을 참조하세요. 앞의 DOC 단건 확인 실행 ID와 구분합니다.

확정 범위:

1. 클라이언트가 HTTP 응답을 수신했습니다. 단순 서비스 주소 오타/전면 접속 불능으로 보이지 않습니다.
2. DOCX 요청의 API 응답은 성공이지만, 응답이 끝난 뒤 클라이언트가 확인한 예상 sidecar 경로에는 **검사를 통과한 PDF가 없었습니다**. PDF 자체가 전혀 안 만들어졌는지, 다른 위치에 있는지, 손상됐는지는 아직 구분되지 않았습니다.
3. 같은 작업 저장소를 이용한 DOC PDF 수집은 성공했습니다. 따라서 NFS가 모든 형식/경로에서 전면적으로 불통이라고 단정하지 않습니다. DOCX 처리별 접근·쓰기·저장 경로는 별도 확인이 필요합니다.
4. 장애 A의 NLTK 오류와 장애 B는 별도 관측입니다. NLTK 데이터 보완만으로 DOCX의 PDF 미확보도 해결된다고 보장할 근거는 없습니다.

### 제공된 함수 사진에서 확인한 사항

- `convert_to_pdf(file_path: str)`가 LibreOffice `soffice --headless --convert-to ... --outdir ...`를 호출합니다.
- `.doc`/`.docx`의 필터는 이미 `pdf:writer_pdf_Export`입니다. 단순 DOCX 필터 문자열 누락으로 진단하지 않습니다.
- `subprocess.run(..., capture_output=True, text=True)` 후 종료 코드와 예상 PDF 존재 여부를 검사합니다.
- 실패 경로에서 stderr만 출력하고 `None`을 반환합니다. stdout은 기록하지 않는 것으로 보입니다.
- 고유 `UserInstallation` 프로필과 timeout 옵션은 제공된 함수 사진에서 보이지 않았습니다.
- 비ASCII 임시 복사 분기가 있으나 현재 클라이언트가 보내는 이름은 ASCII `source.docx`입니다. 한글 파일명 분기를 이번 사례의 원인으로 단정하지 않습니다.
- DOCX 호출부 전체 및 실제 배포 소스는 아직 제공되지 않았습니다. 공개 참고 코드에는 PDF 변환 반환값을 검사하지 않고 후속 처리하는 부분이 있지만, 그 코드와 현장 코드의 동일성은 미확인입니다.

### 유지보수팀이 확인해 주실 항목 — 우선순위 순

| 순서 | 확인 | 필요한 결과 |
|---|---|---|
| 1 | 요청 시각에 처리한 pod/worker, 이미지 digest, 등록/배포 리비전 | 실제 실행 코드 식별 및 라우팅 확인 |
| 2 | 해당 DOCX 처리에서 `convert_to_pdf` 호출 여부 | 호출 전/후 로그와 반환값. 호출이 없다면 해당 코드 분기/설정 |
| 3 | 실제 LibreOffice 실행 | argv, 실행 파일 경로/버전, UID/GID, cwd, 시작/종료 시각, returncode, **stdout와 stderr 둘 다** |
| 4 | 입출력 파일 접근과 저장 위치 | 서버가 읽은 입력 해시, 파일 크기, 출력 디렉터리 쓰기 결과, 실제 생성된 파일명·크기·헤더 |
| 5 | 프로필/필터/시스템 의존성 | 프로필 권한·잠금·동시 실행 여부, Writer/DOCX 필터 가용성, 공유 라이브러리 오류. 충돌이나 누락은 로그로 확인 후 확정 |
| 6 | API 성공 판정 | PDF 변환 실패/None 반환을 호출부가 무시하는지, PDF가 선택 산출물인지, 공식 성공·실패/산출물 계약 |

LibreOffice가 종료 코드 0을 반환해도 파일이 없을 수 있으므로 stdout/stderr와 출력 디렉터리 실물을 함께 확인해 주세요. 실행 파일 존재 확인만으로 DOCX 필터 및 실제 변환 성공을 판단하지 말아 주세요.

## 5. 별도 과거 오류 — ZIP 내부 DRM

초기 실행 `run-20260915T062432Z-a570be4a`에서는 `Input document source.docx is not valid.`가 발생했습니다. 사용자가 ZIP 내부 원문에 DRM이 남아 있음을 확인하고 이후 해제했다고 보고했습니다.

현재는 이후 실행의 DOC PDF 생성과 DOCX API 성공이 관측됩니다. 과거 DRM 오류를 현재 DOCX의 성공 응답/PDF 미확보 원인으로 그대로 재사용하지 않습니다. 모든 내부 파일이 동일 상태라고 가정하지 않으며, 필요한 경우 선택된 샘플의 파일 해시·컨테이너 구조를 수집 도구로 확인합니다.

## 6. 사용자 측에서 제공할 증거

첨부 `collect_pdf_evidence.sh`를 GENOS의 `~/DEV/06_TOOLS/COMMANDS/`에 놓고 실행합니다.

```sh
cd "$HOME/DEV" &&
sh 06_TOOLS/COMMANDS/collect_pdf_evidence.sh \
  /nfs-root/diamo/8-agent/pdf-output \
  "$HOME/DEV/01_DATA/LOGS/pdf-maintenance"
```

특정 실행만 수집하려면 첫 인자에 그 run 폴더를 지정합니다. 전체 실행이 계속되는 중이면 기록이 변할 수 있으므로 가능하면 완료/중단된 실행을 수집합니다. 중단 시 서버 요청은 남아 있을 수 있어 work 폴더를 삭제하지 않습니다.

- 생성 결과: `DEV/01_DATA/LOGS/pdf-maintenance/pdf-evidence-<시각>-<ID>.zip`.
- 포함: 상태별 건수, 샘플별 요청/결과 시각, 원본 경로/제목/해시, API code/errMsg, HTTP 상태(기록이 있을 때), 로컬 파일 존재/크기/해시 일치, DOCX ZIP 필수 항목 존재 여부, 현재 PDF 존재/헤더/EOF.
- 제외: 원본 DOC/DOCX/HWP/PDF 바이트, 전체 API 응답 `data` 및 추출 본문, 환경변수 전체 덤프.
- 설치·네트워크 요청·API 재호출·원본 파일 변경을 하지 않습니다. Python 표준 라이브러리만 사용합니다. 출력은 새 증거 폴더/ZIP에만 씁니다.
- 사례는 기본적으로 실행별 상태/사유/확장자 조합당 2건입니다. 전수 실패 건수와 샘플 수는 구분됩니다. 128 MiB 초과 원본의 현재 해시 계산은 생략합니다.
- 로컬 파일 검사만으로 전처리기 파일 접근·DOCX 전체 유효성을 증명하지 않습니다. 실행 후 나중에 PDF가 생겼다면 상태 기록 시점과 수집 시점을 구분합니다.

내부 원문이 재현에 필요하면 증거의 `remote_file`이 가리키는 기존 NFS 파일을 내부 권한 범위에서 사용해 주세요. 이 보고서에는 원문을 외부 첨부하지 않습니다.

## 7. 요청하는 조치·회신과 완료 기준

1. 실제 DOCX PDF 미확보 원인과 재현 로그를 회신해 주세요. 특정 줄 수정안을 미리 원인으로 확정해 적용하도록 요청하는 것이 아닙니다.
2. 전처리기에서 PDF 생성이 공식 지원 기능인지와 결과 접근 방식을 확인해 주세요. 지원 대상이 아니라면 사용자 설치 없이 이용 가능한 공식 PDF 변환 API/리소스를 안내해 주세요.
3. DOC의 punkt_tab 조회 실패는 전처리기 이미지/데이터 경로/권한을 확인해 조치해 주세요.
4. 운영자 조치 후 동일 해시의 DOCX 샘플 여러 건에서 실제 PDF 접근 가능 여부와 API 상태가 일치하는지, 기존 DOC PDF 생성이 유지되는지 확인해 주세요. 사용자에게 페이지/글꼴/표 품질 확인을 요청해 주세요.
5. HWP/HWPX의 공식 지원 여부와 필요한 변환 백엔드는 별도로 명시해 주세요. 이번 DOC 성공을 HWP 성공으로 확대하지 않습니다.
6. 수정 리비전·적용 범위·롤백 방법을 알려주세요. 사용자는 전처리기 코드를 수정하거나 LibreOffice를 설치할 수 없습니다.

## 8. 참고 근거

- [GENOS v1.8.6 변환 전처리기 설명](https://genos-docs.gitbook.io/default/v1.8.6/admin-management/settings/resource/basic_preprocessor_for_rag/convert_processor)
- [공개 참고 변환 코드 — 현장 동일성 미확인](https://github.com/genonai/doc_parser_code_serving/blob/aa610c3db24aaa02c65e953279f1a60d014babaf/genon/preprocessor/facade/convert_processor.py)
- [NLTK 데이터 설치·경로 안내](https://www.nltk.org/data.html)
- [LibreOffice 명령행 옵션](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html)

작성 기준: 2026-09-15 대화에서 제공된 현장 기록. 사진과 수집 로그가 코드 추정보다 우선합니다. 소스 변경 패치는 사용자 적용 대상에서 제외했으며 적용했다고 간주하지 않습니다.

## 9. 후속 사진: 추가 서버 예외와 전체 실행 ID 확인

사진 `62D13DE1-8F79-4E48-9C31-2D733EAD73CE/1-사진-1.jpg`에서 다음이 추가 확인됐습니다.

- 전체 실행 폴더: `/nfs-root/diamo/8-agent/pdf-output/run-20260915T065449Z-9218fd91`.
- 일부 DOCX에서 HTTP 200 / API code 1 / `errMsg: 'NoneType' object has no attribute 'uri'`가 발생했습니다. 해당 속성에 접근한 객체와 코드 위치는 응답 문자열만으로 확인할 수 없습니다. 서버 traceback과 동일 요청의 앞선 로그를 요청합니다. PDF 변환 실패의 후속 오류인지 독립 파싱/이미지 참조 오류인지 단정하지 않습니다.
- 사용자가 Ctrl+C로 중단했습니다. summary는 request_started 21, documents 21, pdf_with_api_warning 1, failed 19, batch_stopped 1, stopped true입니다. 종료 결과가 없는 나머지 1건은 성공/실패로 확정할 수 없고 서버에서 계속 처리 중일 수 있습니다.
- DEV 결과 복사 로그에는 copied 1, reused 0, failed 0이 표시됩니다. 이것은 확보된 PDF 1건의 복사 성공이며 21건 전부의 변환 성공이 아닙니다.
- 증거 수집 명령에는 원본 internal 경로가 추가로 들어가 `unrecognized arguments`가 발생했습니다. 이는 클라이언트 수집 도구의 명령 인자 오류로, 위 서버 예외들과 구분합니다. 이 시점에서 증거 ZIP 생성 완료는 확인되지 않았습니다.

해당 전체 실행만 수집하는 정확한 명령:

```sh
cd "$HOME/DEV" &&
sh 06_TOOLS/COMMANDS/collect_pdf_evidence.sh \
  /nfs-root/diamo/8-agent/pdf-output/run-20260915T065449Z-9218fd91 \
  "$HOME/DEV/01_DATA/LOGS/pdf-maintenance"
```

모든 기존 실행을 수집할 때는 첫 경로를 `/nfs-root/diamo/8-agent/pdf-output`으로 지정합니다. 원본 `01_DATA/RAW/internal`은 수집 인자로 넣지 않습니다. 수집 중에도 서버 요청이 남아 있다면 이후 생성된 파일과 기록 시점을 구분합니다.


## 10. 증거 수집 결과 확인 및 이관 시 핵심 판단

사용자가 생성된 `SUMMARY.md`를 연 사진 4장(`97B58CA4-3D18-41A2-B3BD-F9B4D5FF0DD2/1-사진-1.jpg` ~ `4-사진-4.jpg`)을 제공했습니다. 요약 파일 생성은 확인됐으며 전체 evidence.json/ZIP 바이트를 외부 작성자가 직접 받은 것은 아닙니다. 사진에서 읽을 수 있는 값만 다음에 반영합니다.

| 대상 | 확인된 수집 값 | 판단과 한계 |
|---|---|---|
| 최초 DOCX 실패: `run-20260915T062432Z-a570be4a` | local_exists true, recorded_hash_matches true, nasca_drm_marker true, is_zip_container false, sidecar_exists_now false, API `Input document source.docx is not valid.` | 과거 스테이징 파일에 NASCA DRM 표식이 남아 있음을 확인. 해제 전 실행 기록이 보존된 것으로 이후 샘플의 재암호화 증거는 아님 |
| DOC 단건: `run-20260915T064137Z-2d5219c6` | recorded_hash_matches true, nasca_drm_marker false, ole_container true, sidecar_exists_now true, PDF header/EOF true, HTTP 200 및 punkt_tab 오류 | DOC는 일반적으로 OLE 컨테이너이므로 이 표식만으로 암호화라고 판단하지 않음. PDF가 실제 남아 있고 NLTK 조회 실패는 별도로 확인됨 |
| 전체 실행의 동일 DOC: `run-20260915T065449Z-9218fd91` | PDF 경고 확보 기록과 현재 sidecar 존재/헤더/EOF 확인, NLTK 오류 반복 | DOC PDF 생성은 반복 관측됨. 전체 21건 중 모든 형식이 정상이라는 뜻은 아님 |
| 전체 실행의 DOCX 실패 샘플: 지배구조 내부규범 | local_exists true, recorded_hash_matches true, nasca_drm_marker false, ole_container false, is_zip_container true | 이 샘플에는 확인한 NASCA 헤더가 없고 DOCX의 ZIP 컨테이너를 읽을 수 있음. 최초 DRM 샘플과 상태가 다름. ZIP 필수 항목 전체·CRC·문서 의미 유효성 및 다른 DRM 유무까지 보장하지 않음 |

`recorded_hash_matches=true`는 **추출 직후 클라이언트가 기록한 해시와 수집 시점 파일의 해시가 동일하다**는 뜻입니다. 원본 ZIP 외부 정본의 해시나 전처리기가 읽은 바이트와 자동 대조한 값은 아닙니다.

수집 사진 4는 DOCX ZIP 검사 부분 이후가 화면 아래로 잘렸으므로, 필수 항목별 결과나 현재 PDF 존재를 그 사진만으로 추가 확정하지 않습니다. 해당 DOCX의 API success/PDF 미확보는 이전 실행 사진에서 이미 확인된 별도 근거입니다.

### 유지보수팀 전달 시 한 문단 요약

> 전처리기 187 호출에서 과거 DRM 포함 DOCX 오류와 이후 장애를 구분해 주십시오. DRM 해제 후 DOC는 PDF를 생성하지만 NLTK punkt_tab 조회 오류가 반복되고, 여러 DOCX는 HTTP 200/code 0/success에도 예상 PDF를 확보하지 못합니다. DOCX 샘플은 수집 시 NASCA 헤더가 없고 ZIP 컨테이너로 읽히며 추출 시점 해시와 일치합니다. 일부 DOCX에서는 별도로 NoneType.uri 예외도 발생했습니다. 실제 배포 코드/이미지 기준으로 DOCX 변환 호출 여부, LibreOffice returncode와 stdout/stderr, 실제 PDF 저장 위치, NoneType.uri 전체 traceback, NLTK 데이터 경로를 확인해 주십시오. 사용자는 전처리기 수정과 LibreOffice 설치가 불가능합니다.

이번 자료는 서버 측 원인 분석을 요청하기에 충분한 증상·재현 경로를 제공합니다. LibreOffice 프로필 충돌, Writer 필터/시스템 의존성 누락, NFS 특정 경로 권한, PDF 저장 위치 중 하나를 근본 원인으로 확정한 것은 아닙니다. 기존에 생성된 증거 ZIP을 이 보고서와 함께 내부 유지보수팀에 전달하면 됩니다. 보고서 보완만을 위해 변환을 다시 실행할 필요는 없습니다.


## 11. 컨테이너 로그 수신: NoneType.uri 직접 실패 위치 확인

사용자가 전처리기 187 상세 → 컨테이너 상태 → 컨테이너 로그 사진 2장(`ACE41E4D-15DE-49EC-A179-2F4E93561748/1-사진-1.jpg`, `2-사진-2.jpg`)을 제공했습니다. 화면에는 GENOS v1.8.6이 표시돼 있습니다. 외부 작성자가 서버에 접속한 것은 아닙니다.

### 11.1 확인된 서버 로그와 직접 원인

2026-09-15 15:55:35 및 15:55:38 KST 부근, 전체 실행 `run-20260915T065449Z-9218fd91`의 DOCX 요청에서 아래 경로가 보입니다.

```text
/app/src/main.py:57              run
  data = await preprocessor(request, file_path, **params)
/app/src/preprocessor.py:1494    __call__
  return await self.docx_processor(request, file_path, **kwargs)
/app/src/preprocessor.py:1078    __call__
  vectors = await self.compose_vectors(document, chunks, file_path, request, **kwargs)
/app/src/preprocessor.py:1054    compose_vectors
  self.set_media_files(chunk.meta.doc_items)
/app/src/preprocessor.py:291     set_media_files
  path = str(item.image.uri)
AttributeError: 'NoneType' object has no attribute 'uri'
```

**직접 실패 원인은 `item.image`가 None인 상태에서 `.uri`를 참조한 것입니다.** 이미지가 없는 항목에 대한 처리 계약/분기가 필요합니다. 이 예외를 기존 sh의 ZIP 추출이나 인자 전달 오류로 진단하지 않습니다. HTTP POST 응답이 200이어도 애플리케이션 오류는 발생할 수 있으며, 기존 API code 1/errMsg 기록과 대응됩니다.

### 11.2 선행 EMF 이미지 오류

같은 로그 구간에 다음 메시지가 반복됩니다.

```text
Attempting Wand conversion for format: image/x-emf
Wand conversion failed: no decode delegate for this image format ... BlobToImage/481
Wand fallback conversion failed: no decode delegate for this image format ... BlobToImage/481
Pillow failed to load image: cannot identify image file <_io.BytesIO object ...>
```

EMF 형식 이미지 디코딩이 실패한 사실은 확인됩니다. 원인은 이미지 변환 환경의 해당 포맷 지원/설정/실행 권한 또는 입력 데이터 문제 등을 실제 컨테이너에서 대조해야 합니다. 로그에 이름이 없거나 설치 여부를 확인하지 않은 특정 OS 패키지를 원인/해결책으로 확정하지 않습니다.

**가장 유력한 연결 가설:** DOCX 내부 EMF 이미지 처리 실패로 이미지 참조가 만들어지지 않은 항목이 남았고, 뒤의 set_media_files에서 None.uri 예외가 발생했을 가능성입니다. 이를 확정하려면 같은 요청·같은 doc_item의 이미지 생성/실패와 None 상태를 연결해야 합니다. 현재 사진은 두 사건의 선후 관계와 직접 예외 위치를 제공하지만 객체별 인과관계 전체를 기록한 것은 아닙니다.

### 11.3 별도로 보이는 길이 경고

```text
Token indices sequence length is longer than the specified maximum sequence length for this model (427 > 256)
Token indices sequence length is longer than the specified maximum sequence length for this model (295 > 256)
```

해당 모델 입력 길이 제한 초과 경고도 있습니다. 실제로 예외가 발생한 traceback은 None.uri이므로 길이 경고를 이번 직접 종료 원인으로 바꾸지 않습니다. 유지보수팀에서 대상 모델/토크나이저, 분할·길이 제한 정책, 결과 영향 여부를 별도 확인해 주세요.

### 11.4 PDF 생성과의 관계 — 아직 별도 검증 필요

로그에는 `docling.document_converter`의 `Finished converting document source.docx ...`가 있습니다. 이 메시지는 해당 Docling 처리 단계가 끝났다는 로그이며, LibreOffice PDF 파일 생성·NFS 저장·사용자 접근 성공을 뜻하지 않습니다.

이번 로그는 **API code 1을 반환한 일부 DOCX의 uri 예외를 설명**합니다. 앞서 **API code 0/success인데 PDF가 없었던 다른 요청들까지 설명한다고 단정하지 않습니다.** 해당 요청들의 convert_to_pdf 호출 여부, soffice stdout/stderr/returncode 및 실제 산출물 위치는 계속 확인이 필요합니다. DOC의 NLTK punkt_tab 조회 실패도 별도 조치 대상입니다.

### 11.5 유지보수팀에 요청하는 구체적 조치

1. 실제 배포 `/app/src/preprocessor.py`의 291행과 호출부 1054행을 확인하고 `item.image`가 없는 항목에 대한 처리 정책을 구현/검증해 주세요. 무조건 속성 접근으로 전체 요청이 중단되지 않도록 해야 합니다. 이미지를 건너뛸 수 있는 경우 경고·누락 항목을 기록하고, 필수 이미지라면 원인을 설명하는 명시적 실패를 반환해 주세요. 조용히 삭제해 성공으로 처리하지 말아 주세요.
2. 같은 요청에서 EMF 디코딩 실패 항목과 None 이미지 참조를 매칭해 원인을 확정해 주세요. 실제 컨테이너의 Wand/이미지 변환 도구 포맷 지원·delegate 설정·정책·버전을 확인하고 지원되는 처리 경로를 마련해 주세요.
3. EMF 포함 DOCX와 비교용 DOCX를 각각 처리해 이미지 손실 여부, 파싱 결과, API 상태, PDF 파일 존재·내용을 확인해 주세요. 성공 로그 하나로 전체 산출물 성공을 판단하지 말아 주세요.
4. 별도 문제인 API success/PDF 미확보와 NLTK punkt_tab 조회 실패를 함께 추적해 주세요. 토큰 길이 초과 경고도 대상 모델의 제한과 처리 정책을 확인해 주세요.
5. 사용자가 전처리기를 수정하거나 LibreOffice를 설치할 수 없다는 제약을 유지해 주세요. 필요한 조치는 운영자 측 배포/공식 API 제공 범위에서 진행해야 합니다.

이전 §9~10에서 uri 오류 위치를 미확인으로 둔 부분은 이번 traceback으로 보완됐습니다. 이미지 참조 None 검사를 위한 사용자 패치를 적용했다는 뜻은 아니며, 현장 수정/복구 완료는 아직 확인되지 않았습니다.
