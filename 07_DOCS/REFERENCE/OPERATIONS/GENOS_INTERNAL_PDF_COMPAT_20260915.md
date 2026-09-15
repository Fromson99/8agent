# GENOS 내규 PDF 입력 호환 — 2026-09-15 현장 기록

## 확인된 상태

- 환경: 사용자 GENOS 코드스페이스 `~/DEV`. 플랫폼/전체 설치 리비전은 미확인.
- 근거: 사용자가 제공한 `git apply --check` 실패 화면과 대상 3개 파일의 `sha256sum` 화면.
- v1은 `genos_corpus.py:43`에서 문맥 불일치로 적용 사전 검사가 실패했다. 제공된 화면에는 실제 적용 명령이 없으며 사전 검사는 코드를 변경하지 않는다.
- 3개 파일의 해시가 보관된 `genos-four-stage-20260910.zip`과 일치했다. 나머지 설치 파일까지 동일하다는 뜻은 아니다.

| 파일 | 현장 SHA256 |
|---|---|
| `02_BACKEND/lawrag/pipeline/genos_corpus.py` | `41de9358cca5d650a6f2f2619a9fef1acd92a5fc4bd7042f637c40db7cd8d12e` |
| `06_TOOLS/COMMANDS/genos_data_stages.py` | `7b0b9fe9573b09e5b58a8e19f149d1b67d967156de37f3c0f495954c0bedf06d` |
| `02_BACKEND/lawrag/pipeline/genos_build.py` | `cfa42e40ebbe114ee5ab3533ebfd71f0ea00ca5bcd54d643863e7b3e258caacb` |

## 전달한 수정본

`09_ARTIFACTS/HANDOFF/GENOS/genos-internal-pdf-input-20260915-v2.zip`

- ZIP SHA256: `50fcafe4a30777b35f934ffb2d8166e046ccf59e806244f3077dee0b1568a0bb`
- 기존 현장 버전에서 내규 입력을 논리 data root의 `PDF/internal`로 지정한다. 원본 RAW는 보존한다.
- 외규는 기존 manifest 기반 선택/해시 검증을 유지한다. 명시적 PDF 입력 모드에서는 존재하지 않는 외규 source 폴더를 건너뛴다.
- 새 의존성·모델 설정 없음. 기존 구조화 엔진을 유지한다. 최신 작업 코드의 VLM 검수·용어 연결·HTML 상태표를 추가하는 패키지가 아니다. v1의 해당 최신 기능 안내를 정정했다.
- 설치기는 3개 파일 전체 해시 확인 → 백업 → 교체 → 결과 해시 확인을 수행한다. 재적용과 백업 기반 복구를 지원한다.
- 생성기: [package_genos_internal_pdf_compat.py](../../../06_TOOLS/OFFLINE/package_genos_internal_pdf_compat.py)
- 실행/재개/검증/복구: [인계 안내](../../../06_TOOLS/OFFLINE/GENOS_INTERNAL_PDF_COMPAT.md)

## 검증 및 인계 상태

외부 WSL에서 `test_genos_pdf_compat_package.py` 15개 통과.
적용/역적용, 백업/복구/재적용, 버전 불일치/변조 차단, PDF 입력/오류 반환,
모의 파서·저장소 어댑터를 사용한 구조화 출처 메타데이터와 캐시 재사용을 검증했다.
이 테스트는 실제 PDF 파싱 품질이나 전체 현장 의존성 검증을 대신하지 않는다.

사용자가 지정한 기존 파트너 메일로 v2 ZIP과 안내를 전송했다.
Gmail SENT 메시지 ID: `1a0a43250bc85b7a`.
**현장 v2 적용·실제 내부 문서 처리·서빙 리비전 배포·MAIN 활성화는 미확인/미수행이다.**

## 후속 현장 화면: DEV 링크 경로로 설치 중단

같은 날 사용자가 v2 설치 결과 `STOP: symlink rejected: /home/genos/DEV`를 제공했다.
설치기의 root 사전 검사에서 중단된 것으로, 코드 교체는 시작되지 않았다.
GENOS의 DEV 링크를 삭제하거나 설치기의 파일 링크 검사를 해제하지 않고,
실제 디렉터리로 이동한 뒤 설치 root를 물리 경로로 전달한다.

```bash
cd -P "$HOME/DEV"
.venv/bin/python TRANSFER/genos-internal-pdf-input-20260915-v2/install.py --root "$(pwd -P)" --apply
```

외부 WSL 임시 디렉터리에서 동일한 DEV 심볼릭 링크를 만들어 오류를 재현했고,
위 물리 경로 방식으로 기존 v2 설치기의 `APPLY OK` 및 3개 파일 결과 해시를 확인했다.
전송된 v2 ZIP은 변경하지 않았다. 현장 재실행 성공은 아직 미확인이다.

## 후속 확인: 설치 성공 및 Docling 모델 초기화 실패

사용자가 물리 경로 방식으로 설치한 뒤 "성공함"이라고 확인했다. 따라서 v2 설치는
사용자 확인 기준 성공이다. 이어 제공한 `detail.log` 사진에는 `/workspace`에서
`genos_stages.structure → genos_build.ingest_files → Docling StandardPdfPipeline`로
PDF 처리가 진입한 기록이 있다. 전체 문서 구조화 완료는 아니다.

실패 지점은 `layout_object_detection_model → transformers_engine → hf_vision_base`
모델 초기화다. Hugging Face `snapshot_download`가 연결 재설정으로 실패했고,
`LocalEntryNotFoundError`에 요청한 revision의 로컬 snapshot도 찾지 못했다고 나온다.
PDF 입력 전환은 이 문서에 대해 동작했지만, 필요한 레이아웃 모델을 찾는 단계에서
중단됐다. 이 화면은 GENOS VLM 호출·인증 실패를 나타내지 않는다.

외부 작업 환경의 Docling 2.117.0 / docling-ibm-models 3.13.3은 기본 layout으로
`docling-project/docling-layout-heron`을 사용한다. 로컬 HF cache에는 해당 모델과
`docling-project/docling-models`가 있으나 이 버전을 현장 버전으로 간주하지 않는다.
현장 패키지 버전 확인을 요청했으며, 오프라인 모델 반입·경로 설정·현장 재처리는 미완료다.
Docling은 `DOCLING_ARTIFACTS_PATH` 또는 `PdfPipelineOptions.artifacts_path`로
사전 반입한 모델을 선택한다. HF offline 설정만으로 누락 모델을 복구할 수는 없다.
참조: https://docling-project.github.io/docling/usage/advanced_options/

## 현장 Docling 버전 확인 및 오프라인 모델 묶음

다음 사진의 `importlib.metadata.version('docling')` 결과는 **2.126.0**이다.
같은 화면의 2.127.0 설치 시도는 사용자에 의해 취소됐으며, 설치 완료로 기록하지 않는다.
현장 `docling-ibm-models` 버전은 사진에 나오지 않았다.

Docling v2.126.0의 공식 소스에서 기본 transformers 레이아웃 Heron과 TableFormer V1
기본 선택 및 artifacts 경로 규칙을 대조했다. 보관된 공개 모델 snapshot을 일반 파일로
복사해 아래 반입 ZIP을 만들었다. 기존 코드·패키지·모델 캐시는 변경하지 않았다.

- 묶음: `09_ARTIFACTS/HANDOFF/GENOS/docling-models-2.126.0-v1.zip`
- 크기: 493,638,182 bytes
- SHA256: `97a326c88f2a3ad0250b504995618a9bc28fb6f0f0209a54762ac8e25c0e926b`
- 파일별 SHA256 및 모델 revision: 동봉 `MODEL_MANIFEST.json`
- 범위: Heron transformers 모델과 TableFormer V1 accurate/fast. OCR/ONNX/VLM 미포함.
- 명령/검증/재개/복구: [모델 반입 안내](../../../06_TOOLS/OFFLINE/DOCLING_2126_OFFLINE.md)

외부 WSL Python 3.14의 임시 패키지 overlay에서 Docling/docling-slim 2.126.0,
docling-core 2.94.1, docling-ibm-models 4.0.2, docling-parse 7.16.0으로 검사했다.
14개 모델 파일 해시를 확인하고 소켓 연결을 차단한 상태에서 합성 PDF 1장의
레이아웃·표 모델 로딩 및 텍스트 보존이 성공했다. 기존 `.venv`는 변경하지 않았다.
검증 영수증은 묶음 디렉터리의 `validation-receipt.json`에 보관한다.
현장 Python 3.11 의존성 조합·모델 반입·실제 내부 문서 품질은 현장 `check_models.py
--smoke-test`와 처리 결과로 확인해야 한다. VLM 현장 설치 여부는 별도 미확인이다.
