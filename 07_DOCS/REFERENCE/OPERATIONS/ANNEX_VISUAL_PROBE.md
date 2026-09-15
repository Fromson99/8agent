# 별첨 감사·DOCX/HWP PDF 시각화 후보

운영 MAIN을 변경하지 않는 ADR-0350 연구 도구다. 실제 모델 호출은 하지 않는다.

## 로컬에서 확인한 사항

- law manifest 첨부1488개: 파일 존재·hash 일치, MD sidecar 없음1488개.
- XML 별표1473개: 빈 내용0개. 평문 존재가 표·서식 보존을 보증하지 않는다.
- 기존 제목 정규식에 안 맞는 첨부15개: 번호 없는 별표 외에도 개정전문·ZIP 등이 섞여 있다.
  이 숫자를 누락 별표 수로 해석하면 안 된다.
- raw-layout-0339 입력 로그에서 ZIP3개·XLSX1개가 미지원으로 제외됐다.
  GENOS 현장과 동일한 실행 로그는 아니므로 현장 skip의 확정 원인은 아니다.
- 현재 GENOS 빌더는 ingest에 manifest_item={}을 전달하므로 기존 annex_md_map 연결을
  기대해서는 안 된다. 별첨은 별도 입력으로 선택되며 그 성공/실패 추적이 중요하다.

## 실행

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/annex_visual_probe.py audit \
  --root 01_DATA/RAW/law --output /새로운/별첨감사폴더

.venv/bin/python 06_TOOLS/EXPERIMENTS/annex_visual_probe.py render \
  --source /실제/문서.docx --page 1 --page 2 --output /새로운/시각화폴더
```

render 입력: PDF, DOCX, DOC, HWP, HWPX. Office 형식은 LibreOffice/soffice가 필요하다.
HWP/HWPX는 해당 설치의 importer가 지원하는 파일만 변환된다. 지원되지 않는 버전,
암호화, 손상은 conversion_failed이며 텍스트를 PDF처럼 꾸미는 fallback은 하지 않는다.
현재 WSL에 converter가 없어 실제 로컬 DOCX/HWP 실행은 converter_unavailable이다.
이 환경에서의 원본 Office 렌더 성공은 아직 검증하지 않았다.

원문을 별도 임시폴더에 복사하고 격리 프로필에서 매크로 보안·자동 링크 갱신 제한을
설정해 변환한다. 완전한 OS 네트워크 sandbox를 제공하는 것은 아니다.
외부 비신뢰 Office를 처리할 때는 OS 수준 격리와 변환기 보안 업데이트도 필요하다.

출력 conversion.json은 원본 hash, converter hash, PDF hash, 시간, 상태를 기록한다.
완성 PDF는 PyMuPDF로 열어 페이지 존재를 검사하고 최대4페이지를 VLM 입력으로 만든다.
vlm-request.json은 전송하지 않은 요청 패킷이다. PDF 페이지 좌표와 원본 Office hash를
분리해 기록하며 layout_fidelity/original_pagination_preserved는 unverified로 남긴다.
글꼴/페이지 나눔/표가 달라질 수 있으므로 변환 성공을 원본 재현 성공으로 보고하지 않는다.

## 아직 남은 작업

실제 변환기 설치 및 HWP importer 확인, 원문-변환본 대조, GENOS VLM 실호출,
ZIP 내부 문서의 안전한 개별 반입, XLSX 표 전용 경로, 별첨-본문 연결 승인과 MAIN 반영.
현재 도구는 누락을 찾아 보고하며, 운영 skip 정책을 자동으로 바꾸지 않는다.
