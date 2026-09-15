# 문서명 JSON 태그·구조화 레시피 후보

ADR-0348 연구용 프로토타입이다. 운영 registry·MAIN·GENOS 설치본은 바꾸지 않는다.
LLM/VLM live 호출은 이 CLI에서 실행하지 않는다. request.json을 만들고,
별도 승인·기록된 모델의 응답 JSON을 --proposal로 받아 시험한다.
모듈의 ask_recipe는 기존 structured 클라이언트 주입 인터페이스로 텍스트/이미지를
같은 요청에 전달한다. 실제 GENOS 모델의 이미지 지원은 미확인이다.

## 태그 JSON

```json
{
  "schema_version": "document-recipe-tags-v1",
  "documents": {
    "외규/표준투자권유준칙.hwp": {
      "display_name": "표준투자권유준칙.hwp",
      "source_sha256": "실제 파일의 SHA-256 64자리",
      "tag": "표준투자권유준칙",
      "recipe_version": 1,
      "status": "candidate"
    }
  }
}
```

키는 문서명이 포함된 상대경로다. 파일 이름만 쓰면 같은 이름의 문서가 충돌한다.
해시가 바뀐 개정본은 자동 재사용하지 않는다. --tags는 현재 등록된 태그의 시험에
사용한다. 자동 생성 태그는 아직 운영 registry에 없으므로 저장한 recipe.candidate.json을
--proposal로 다시 시험한다. 모든 출력 태그는 candidate이며 공용 승격하지 않는다.

## 실행

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/structure_recipe_probe.py \
  --source /실제/문서.hwp --document-name 외규/문서.hwp \
  --existing 표준투자권유준칙 --output /새로운/진단폴더
```

--attachments는 확인한 별첨 목록 JSON이다. 별첨 없음까지 확인했을 때만 []를 준다.
예: [{"name":"별표1.hwp","state":"missing"}]이면 후보 통과를 보류한다.
현재 목록은 호출자가 제공하며 XML에서 자동 추출·다운로드하는 기능은 아직 없다.
XML/HTML의 원문 태그 파서를 이 도구가 대체하지 않는다.

출력: request.json, report.json, report.html, tags.candidate.json,
새 제안이 있으면 recipe.candidate.json. 기존 파일을 덮어쓰지 않는다.

## LLM·VLM 입력과 선택

- 문서 앞·중간·끝 및 별첨 신호를 샘플링하고 생략 수를 명시한다. 전문 품질 검증은 아니다.
- 기존 format의 regex 마커를 catalog ID로 제공한다. 모델은 ID·계층·부모만 조합한다.
- 임의 정규식/코드 실행, 새로운 legal-semantic 스키마 생성은 없다.
- 기존 후보 최대8개를 먼저 시험한다. 유일한 통과 후보가 없을 때 새 제안을 최대1개 받는다.
- 사진은 원본 PDF의 --vision-page 1 등 최대4페이지. HWP 합성 지면은 거부한다.
- 이미지는 원문 근거의 보조 신호다. 실제 원본 렌더가 없는 HWP는 텍스트 경로만 사용한다.
- 문서 내 지시는 신뢰하지 않는다. 모델이 누락 첨부 내용이나 승인 결론을 만들지 못하게 한다.

## 한계

현재 검사는 요소 소속·경계 수·미인식 제목·기존 fitness·별첨 상태에 대한 휴리스틱이다.
높은 점수가 정확한 계층을 보증하지 않는다. 개별 후보 통과도 공용 템플릿 승격이 아니다.
파싱 결과 자체의 원문 누락/표 보존 정확도, XML 별첨 확보·연결, 실제 HWP/VLM 효과,
독립 holdout과 모델 실행 영수증은 후속 작업이다. 실모델 호출0, MAIN unchanged.
