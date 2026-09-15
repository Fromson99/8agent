# 공개 용어집 수집 — 2026-09-12

요청 범위: 조사에서 찾은 한국은행·정부 시사경제사전·국세청·KRX·금투협의 공개 용어집.
외부 공개 원문만 수집한다. 현재 상태는 **수집 실행 종료 — 4개 원천 수집 완료, KRX 정의 본문 미확보**이며 아래 실행 기록이 우선한다.

- 실행 명령: `.venv/bin/python 06_TOOLS/pipeline.py glossary collect-external --snapshot public-20260912`
- [실행 기록](../../../01_DATA/LOGS/glossaries/public-20260912/collection.json)
- 원문: `01_DATA/RAW/glossaries/public-20260912/<source>/`
- 항목: `01_DATA/STRUCTURE/glossaries/public-20260912/<source>/entries.jsonl`
- [실행·재개 방법](../OPERATIONS/GLOSSARY_ALIGNMENT.md#외부-기관-공개-사전-수집)

## 원천별 결과

| 원천 | 확보/진행 | 범위와 한계 |
|---|---|---|
| 한국은행 경제금융용어 800선 | 2026년판 PDF 428쪽 확보 | PDF 원문 수집. 항목별 구조화 미실행 |
| 경제배움e 시사·경제 용어 사전 | 전체 엑셀 및 설명 3,029항목 확보 | 공식 목록의 총건수와 엑셀 행 수 일치; ID 없는 엑셀 행을 snapshot·행으로 식별 |
| 금융투자협회 증권 용어사전 | PDF 349쪽 확보 | 텍스트층 없는 스캔본; 과거 금융투자사료이며 VLM 구조화 미실행 |
| 국세청 국세법령정보 용어사전 | 전체 목록과 상세 정의 1,718건 확보 | 목록 ID·상세 ID·표제어·전체 정의를 전수 대조 완료 |
| KRX ETF 용어사전 | 검색 도구에서 56개 표제어 확인, 원문 연결 지연 | 개별 정의 본문 미확보; 표제어는 별도 발견 기록에 보존, 공식 원문 다운로드 완료로 집계하지 않음 |

국세청 최종 `details_complete`는 1,718이다. 전체 `collection_complete=false`는 KRX 미확보를 포함한
전체 원천 집계이며, 다른 4개 원천이 실패했다는 뜻이 아니다.
출처별 설명 항목은 총 **4,747건**이다. 기관 간 중복 표제어를 병합한 고유 개념 수가 아니다.

[전수 검증 기록](../../../01_DATA/LOGS/glossaries/public-20260912/verification.json): HTTP 원문 1,743개 해시,
엑셀 3,029행, 국세청 목록·상세 1,718건의 ID와 정의 원문 보존을 모두 확인했다.
[수집 코드·의존성 버전](../../../01_DATA/LOGS/glossaries/public-20260912/collector-version.json)도 보관했다.

KRX 표제어는 [발견 기록](../../../01_DATA/LOGS/glossaries/public-20260912/krx-discovery.json)에 있다.
원천 ID와 정의가 없는 목록 확인 기록이며 `entries.jsonl`로 발행하지 않았다.

## 저장된 자료

- [한국은행 PDF](../../../01_DATA/RAW/glossaries/public-20260912/bok/dictionary.pdf)
- [금투협 PDF](../../../01_DATA/RAW/glossaries/public-20260912/kofia/dictionary.pdf)
- [경제배움e 전체 엑셀](../../../01_DATA/RAW/glossaries/public-20260912/econedu/dictionary.xlsx) / [3,029개 설명 항목](../../../01_DATA/STRUCTURE/glossaries/public-20260912/econedu/entries.jsonl)
- [국세청 1,718개 전체 정의](../../../01_DATA/STRUCTURE/glossaries/public-20260912/nts/entries.jsonl) — 원천 ID별 원본 JSON은 RAW의 `nts/detail/`에 보존.

## 공식 출처

- [한국은행 2026년판 게시물](https://www.bok.or.kr/portal/bbs/B0000249/view.do?menuNo=200765&nttId=10096081): 2026-01-29 게시.
- [경제배움e 시사·경제 용어 사전](https://econedu.go.kr/user/playEcon/currEconTermDoc/menu/list): 화면의 전체 다운로드 엑셀 사용.
- [국세청 용어사전](https://taxlaw.nts.go.kr/st/USESTJ001M.do): 화면에서 사용하는 목록·상세 조회 응답 수집.
- [금투협 증권 용어사전](https://www.kofia.or.kr/brd/m_117/view.do?seq=11): 2014-06-12는 게시일이며 발행연도로 단정하지 않음. 첨부 `011.pdf` 확보.
- [KRX ETF 용어사전](https://open.krx.co.kr/contents/OPN/01/01030500/OPN01030500.jsp) 및 [표제어 목록](https://open.krx.co.kr/contents/OPN/01/01030500/OPN01030500T1.jsp).

처음 조사한 `mofe.go.kr/sisa/dictionary`는 목록 요청이 빈 응답을 반환했다. 공식 경제배움e의
시사·경제 사전 전체 다운로드 경로를 추가로 확인해 수집했다. 두 서비스의 항목·개정 이력이
완전히 같다고 검증한 것은 아니다. 별도 서비스 ID를 합치지 않는다.

## 데이터의 내용과 후속 소비

경제배움e 원문 범주: 금융 815, 경제 705, 경영 631, 공공 556, 과학 210, 사회 112항목.
사용자가 전체 수집을 요청했으므로 범주 필터 없이 전부 보존했다. 전환사채·금리스왑·금전신탁·
사모펀드·PF대출·장외파생상품·자산유동화증권 등 우리 문서와 연결할 후보가 실제로 포함돼 있다.
이 확인은 표제어 확인이며 문서별 포괄률이나 검색 개선 효과를 측정한 실험이 아니다.

기관별 설명은 `dictionary_explanation`으로 보관하고 모두 `unreviewed`다.
사전의 해설·과거 제도 설명을 현재 법령의 정의로 승인하지 않는다. 같은 표제어를 기관 간에 병합하지 않는다.
엑셀은 출처표시+변경금지 안내를 함께 보존하고 설명 원문을 그대로 저장했다.

[다기관 용어집 설계](../ARCHITECTURE/MULTI_SOURCE_GLOSSARY.md)의 정규화·출처별 의미·관계 검토
입력으로 사용한다. 현행 법제처 전용 패키지 import나 운영 RAG에는 아직 자동 연결하지 않는다.
PDF는 이후 Document Ingestion의 PDF/VLM 구조화 경로에서 처리해야 한다.
GENOS에 접근하거나 내부 데이터·모델을 호출하지 않았으며 배포도 실행하지 않았다.

## 검증

- 새 수집 및 기존 용어집 회귀 테스트 32개 통과.
- 엑셀 총건수/항목 수, 빈 정의, 중복 ID, 국세청 상세 원천 ID·표제어 대응을 검사.
- 각 HTTP 원문에 URL·요청 조건·시각·바이트 수·SHA-256을 기록하고 재개 시 검증.
- 다운로드된 PDF의 파일 시그니처·열기·페이지 수 확인.
- 코드: `lawrag.pipeline.collect_public_glossaries`; 기존 `pipeline.py glossary` CLI에 연결.
- 파이프라인 선언: `00_SYSTEM/GLOSSARY_PIPELINE.json.external_dictionary_collection`.
