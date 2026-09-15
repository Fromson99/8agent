# Docling 2.126.0 — PDF 레이아웃/표 모델 반입

현장 사진에서 Docling 2.126.0이 확인됐다. 이전 로그는 Heron 레이아웃 모델을
로컬에서 찾지 못하고 Hugging Face 접근이 실패한 상태다. 패키지 재설치가 아니라
모델 파일 반입으로 해결한다. 이 묶음은 코드·Python 패키지를 덮어쓰지 않는다.

포함: 기본 transformers Heron 레이아웃 모델 + TableFormer V1 accurate/fast 모델.
정확한 공개 모델 revision과 파일 해시는 MODEL_MANIFEST.json에 고정했다.
Docling 2.126.0의 기본 선택과 폴더 규칙은 동봉한 해당 버전 소스로 대조했다.
이 묶음에는 OCR, ONNX 레이아웃, GENOS VLM 모델/인증키가 없다.

## 반입과 검사

ZIP을 GENOS `~/DEV/TRANSFER/`에 업로드한다. 실행 중인 문서 처리를 중단하고:

```bash
cd -P "$HOME/DEV"
.venv/bin/python -m zipfile -e TRANSFER/docling-models-2.126.0-v1.zip TRANSFER
.venv/bin/python TRANSFER/docling-models-2.126.0-v1/check_models.py --smoke-test
```

MODEL HASHES OK 후 OFFLINE PDF OK까지 확인한다. 검사는 동봉 파일 해시를 확인하고,
합성 PDF 한 장으로 레이아웃·표 모델을 CPU에서 로딩한다. 이 검사 프로세스는 외부
소켓 연결을 차단한다. 실제 내부 PDF, 한국어 OCR, GENOS VLM 품질 검사는 아니다.
STOP이면 마지막 오류를 확인한다. 버전이 다르면 자동 업그레이드하지 않는다.

## 같은 터미널에서 설정 후 재개

```bash
export DOCLING_ARTIFACTS_PATH="$(pwd -P)/TRANSFER/docling-models-2.126.0-v1/models"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id internal-pdf-002 --stage structure --execute
```

DOCLING_ARTIFACTS_PATH는 두 모델 폴더가 함께 있는 `models`를 가리켜야 한다.
새 터미널에서는 export를 다시 실행한다. 기존 .env를 덮어쓰지 않는다.
원본/완료 산출물은 보존하고 같은 run-id로 실패 문서 처리를 재개한다.
다른 경로에서 성공한 구조화 캐시의 품질을 이 모델 변경만으로 재검증했다고 보지 않는다.

## 별도 확인 범위

- 패키지 버전·모델 초기화는 현장 smoke-test로 확인한다. 이미지에 보인 설치 중단이
  전체 의존성 변경을 일으켰는지는 아직 확인되지 않았다.
- 스캔 PDF의 OCR 모델은 별도이며, 이후 OCR 자산 누락 오류가 나오면 그 설정을 확인한다.
- 우리 PDF VLM 코드의 현장 설치·내부 모델 호출은 이 묶음으로 추가되지 않는다.
- 복구: 실행을 중단하고 위 환경변수의 이전 값을 복원하거나 새 터미널을 연다.
  코드·기존 모델·입력 원본은 이 반입 과정에서 변경되지 않는다.

공식 안내: https://docling-project.github.io/docling/usage/advanced_options/
