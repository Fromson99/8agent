# 기존 금융·법률 용어 사이의 관계 데이터 검토

검토일: 2026-09-14. 공개 이용조건·공식 명세·일부 실제 원본 응답을 읽은 진단이다.
데이터 적재, 매칭 성능 평가, LLM 호출, MAIN 변경은 하지 않았다. 실험 효과를 비교하지
않았으므로 새 ADR 실험이 아니다. 아래 우선순위는 적합성에 관한 판단이며 실측 커버리지가 아니다.

## 판정

| 데이터 | 상업 이용 조건 | 실제 확인 수준 | 우리 용도 판정 |
|---|---|---|---|
| 법제처 지식베이스 용어 관계 | 포털 이용허락범위 제한 없음 | 공식 관계 API 명세 및 현재 DB의 관계 행 확인 | 기존 관계 우선 재사용 |
| FIBO 원본 OWL | MIT, 저작권·허락 고지 보존 | 공개 RDF HTTP 200, XML 파싱 및 주식 계층 확인 | 금융 상품 종류 관계의 우선 후보 |
| Wikidata 구조화 데이터 | CC0 | Action API JSON HTTP 200, 우선주 항목과 상위 관계 확인 | 한국어·영어 개념 연결과 관계 후보에 적합 |
| 국립중앙도서관 주제명 NLSH | 공식 다운로드 페이지에 공공누리 1유형 및 CC0 명시 | 공개 TTL 샘플 HTTP 200, 관계 필드 확인 | 한국어 후보 발굴에 적합; 계층 의미 재검토 필요 |
| 우리말샘 | 일반 텍스트 CC BY-SA 2.0 KR, 예외 자료 별도 | 상세 API 명세의 관계 유형·상대 ID 확인; 인증 API 실호출 미실행 | 조건부 사용; 한국어 의미·관계 보강 |
| 온용어 | 원자료별 조건; 일괄 허용 아님 | 검색 API 명세, 개별 출처 표시, 공개 지식그래프 17개 목록 확인 | 허용 출처의 용어 대응 보조; 금융 관계 그래프로는 우선순위 낮음 |
| ConceptNet 5.7 | 데이터 CC BY-SA 4.0 | 공식 덤프 GET HTTP 200 및 응답 헤더; 공개 API는 이번 환경에서 502 | 덤프 사용 가능, 한국어 금융 관계 품질 미확인 |
| 한국법제연구원 법령용어 CSV | 공공누리 1유형 | CSV HTTP 200, 실제 헤더·예시 확인 | 정의·한자 대응용; 직접 관계 데이터 아님 |
| 국회도서관 학술정보 LOD | 소개에는 CC라고만 표시, 세부 유형 미확정 | 공식 소개·시소러스 포함 여부 확인 | 상업용 반입 보류 |
| KorLex | 현재 배포본의 명시적 상업 이용조건 미확인 | 공식 배포·허락 원문 확보 실패 | 반입 보류; 불허라고 확정한 것은 아님 |
| 법제처 법령용어한영사전 PDF | 공공누리 4유형: 상업 이용·변경 금지 | 해당 자료의 포털 이용조건 확인 | 이번 상업용 구축에서 제외 |

## 원천별 근거와 제한

### 법제처

[관계 API](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lstrmRltGuide)는
출발·상대 용어 ID와 동의/반의/상위/하위/연관의 구분을 제공한다.
[일상용어–법령용어 포털](https://www.data.go.kr/data/15111333/openapi.do)은 이용허락범위 제한 없음을 명시한다.
인증에는 승인된 LAW_OC를 사용해야 한다. 이번에 재수집하거나 예시 인증값을 사용하지 않았다.

현재 초안의 `official_relation` 95,043행은 동의 14,789, 반의 2,799, 상위 5,842,
하위 7,716, 연관 63,897행이다. 원천의 방향 있는 행 수이며 중복 제거한 무방향 쌍 수가 아니다.
다른 기관 항목으로 관계를 옮기려면 먼저 의미 대응을 확인해야 한다.

### FIBO

[라이선스](https://raw.githubusercontent.com/edmcouncil/fibo/master/LICENSE)와
[주식 RDF](https://raw.githubusercontent.com/edmcouncil/fibo/master/SEC/Equities/EquityInstruments.rdf)를 확인했다.
실제 명시적 `rdfs:subClassOf`는 `PreferredShare → Share`, `CommonShare → Share`,
`ConvertiblePreferredShare → PreferredShare`를 포함한다. 방향은 하위에서 상위다.
한국어 표시로 설명하면 우선주·보통주는 주식의 종류라는 후보 관계다.

공개 원본 OWL의 허락을 별도 파생 상품의 조건과 혼동하지 않는다. 실제 수집 시 master 대신
릴리스/커밋·파일 해시를 고정해야 한다. 영어 용어와 한국 법률상 개념의 대응은 미승인이다.
OWL restriction은 일반적인 용어 두 개 사이의 단순 계층과 구별해야 한다.

### Wikidata

[구조화 데이터 이용조건 및 덤프](https://www.wikidata.org/wiki/Wikidata:Database_download),
[우선주 Q622588](https://www.wikidata.org/wiki/Q622588)를 확인했다.
Action API `wbgetentities`의 JSON에 한국어 우선주, 영어 preferred stock,
preferred share 등의 별칭과 `P279 → Q11692`가 있다. 확인 revision은 2497980847이다.
해당 상위 관계의 references 배열은 없었다. 진술·한정자·출처·rank를 함께 보존할 필요가 있다.

Special:EntityData 경로는 이번 요청에서 403이었으나 공식 Action API와 REST 경로는 200이었다.
전체 서비스가 접근 불가능하다는 의미는 아니다. 전체 덤프는 받지 않았다.
P31(개별 사례)과 P279(종류)를 구분하고, 동명 항목이나 별칭만으로 의미를 합치지 않는다.

### 국립중앙도서관 NLSH

[다운로드 및 이용조건](https://lod.nl.go.kr/home/dataset/datadownload.do)에 주제명 데이터
257,749건, 갱신일 2026-08-07, TTL ZIP 73.8 MB가 표시되어 있다. 이는 우리 용어집과
매칭되는 건수가 아니다. 전체 파일은 기관명·사용목적 입력 화면이 있으며 이번에는 제출하지 않았다.
인증 없이 공개된 `Concept_sample.ttl` 939,595바이트를 메모리에서 읽었다.
`skos:altLabel`, `broader`, `narrower`, `related`, `closeMatch`, `definition`이 실제 존재한다.

[공식 RDF 변환표](https://lod.nl.go.kr/home/service/rdf.do)는 사례 관계 BTI/NTI와
전체·부분 관계 BTP/NTP도 broader/narrower로 변환한다고 명시한다.
따라서 이 관계를 그대로 우리 `BROADER_THAN/NARROWER_THAN`의 종류 관계로 확정하면 안 된다.
우선 후보 쌍과 출처 단서로 쓰고, 원관계 세분 정보가 없으면 관계 유형을 미확인으로 남긴다.

### 우리말샘

[저작권 정책](https://opendict.korean.go.kr/service/copyrightPolicy)은 일반 텍스트의
상업 이용을 허용하면서 저작자 표시와 변경 저작물 배포 시 동일조건을 요구한다.
출전이 있는 인용 용례 및 멀티미디어에는 별도 조건이 있으므로 포괄적으로 포함하지 않는다.

[상세 API 명세](https://opendict.korean.go.kr/service/openApiInfo?apiType=dict)의
`sense_info.relation_info`에는 `word`, `type`, `link_target_code`, `link`가 있다.
앞선 조사에서 관계 API를 확인하지 못했다고 한 부분은 이 확인으로 보완된다.
경제·경영·법률 전문 분야를 필터링하고 의미 ID를 보존할 수 있다.
다만 명세의 type은 문자열이며, 어휘 지도의 모든 상하위 간선이 이 API로 반환되는지는
미확인이다. 인증키를 이용한 실제 금융 용어 응답·호출 한도·대량 수집 완료는 검증하지 않았다.

### 온용어

[저작권 정책](https://kli.korean.go.kr/term/bbs/indexPolicyInfo.do?type=copy&lang=kr)은
원자료별 이용조건을 따른다. [상업신용 상세](https://kli.korean.go.kr/term/trgtWord/indexTrgtWord.do?trgtWordNo=2250892)는
우리말샘 출처와 CC BY-SA 조건을 표시한다. 기관 보도자료의 공공누리 1유형을 전체 데이터에
확장하지 않는다. API 예시의 라이선스 숫자만 믿지 말고 실제 원출처 조건과 대조해야 한다.

[현행 검색 API 명세](https://kli.korean.go.kr/term/bbs/indexOpenApiInfo.do?lang=kr)의 주소는
`https://kli.korean.go.kr/term/api/search.do`이며 회원 가입·키 발급이 필요하다.
반환 필드에는 `origin`, `definition`, `source`, `glossary`, `kr_gvrn_lcns_ty`, `relate_word`가 있다.
같은 안내 페이지의 다른 호스트를 사용하는 상세 API 설명은 현행 검색 API와 별도 검증이 필요하다.

[지식그래프 목록](https://kli.korean.go.kr/term/knowledgegraph/indexKnowledgeGraphList.do?main=Y)에
17개 주제와 JSON/엑셀 내려받기 메뉴가 있다. 주제들은 가족·건축·문학·공예·과학기술·생활문화
등이며 확인한 목록에 금융·법률 전용 그래프는 없다. 그래프 파일 자체는 내려받지 않았다.
단순한 정의문 추출어·참고어를 동의어 또는 상하위 관계로 확정해서는 안 된다.

### ConceptNet

[데이터 라이선스](https://raw.githubusercontent.com/commonsense/conceptnet5/master/DATA-CREDITS.md)는
CC BY-SA 4.0이다. 코드의 라이선스와 별개다.
[공유 지침](https://github.com/commonsense/conceptnet5/wiki/Copying-and-sharing-ConceptNet)은
출처 표시와 호환되는 데이터셋 라이선스를 요구한다.
[공식 다운로드 안내](https://github.com/commonsense/conceptnet5/wiki/Downloads)의
5.7.0 압축 파일은 GET 200, Content-Length 497,963,447이었다. 응답 본문 전체는 받지 않았다.
한국어 주식 API 요청은 이번 환경에서 502였다. 덤프의 한국어 금융·법률 간선 수는 미확인이다.
동일조건 자료는 배포 단위·조건을 명시해 관리해야 하며, 별도 테이블 보관만으로 의무가 사라지지 않는다.

### 한국법제연구원 CSV

[법령용어 정보](https://www.data.go.kr/data/15031282/fileData.do)는 공공누리 1유형이다.
공식 페이지가 연결한 CSV 2,691,987바이트를 메모리에서 CP949로 읽었다.
실제 헤더는 `연번, 한글용어, 한자용어, 용어설명`이며 예시 첫 용어는 흡수합병이다.
설명 페이지의 ‘관련 용어’ 언급과 달리 관계 유형·상대 ID·영문 열은 없다.
따라서 정의와 한자에 의한 의미 구분 자료로만 분류한다.
파일명 기준일은 20200831이며 페이지 수정일을 정의의 최신 법령 반영일로 해석하지 않는다.

### 보류·제외

- [국회도서관 학술정보 LOD](https://cloud.nanet.go.kr/lod/lodIntro.do): 시소러스 포함과
  CC 적용은 명시되지만 이번 확인에서 BY/NC/ND/SA 등 구체적 허락 유형을 확보하지 못했다.
  국립중앙도서관 데이터와 다른 출처이므로 그 이용조건을 전용할 수 없다.
- [KorLex 공식 배포 호스트](https://korlex.pusan.ac.kr/): 이번 조사에서 접근 가능한 현재
  배포본·허락 원문을 확보하지 못했다. 논문이나 타인의 재업로드 라이선스로 대체하지 않는다.
- [법제처 법령용어한영사전](https://www.data.go.kr/data/15032258/fileData.do): 해당 자료에
  공공누리 4유형이 표시되어 있어 이번 상업용 구축의 반입 대상에서 제외한다.

## 우리 데이터에 적용할 범위

확인한 기준은 `GLOSSARY_PIPELINE.json.current_draft`의
`01_DATA/LEXICON/glossary-v1/boundary-20260914-v3/dictionary.sqlite`다.
현재 항목은 법제처 100,178, 경제배움e 3,029, 국세청 1,718, 본문 정의 8,533이다.
국세청 중 영문 필드가 있는 항목은 1,618, 한자는 1,632이다. 다른 출처는 이 열들이 비어
있다는 뜻이며 정의문에 외국어가 전혀 없다는 뜻은 아니다.

국세청 채권 항목은 한자 債權, 영어 receivables, credit이다. 채권이라는 한국어 표기가
같아도 bond(債券) 관계를 붙이면 안 된다. 우선주는 preferred stock이므로 Wikidata 별칭과
FIBO label을 통해 대응 후보를 만들 수 있지만 자동 의미 승인이나 커버리지는 측정하지 않았다.

후속 작업의 순서는 다음과 같다.

1. 기존 법제처 관계를 재사용하고 NLSH·FIBO·Wikidata를 각각 독립된 후보 출처로 추가한다.
2. 양 끝이 현재 용어집의 의미 항목에 대응되는 관계만 검토 대상으로 남긴다.
3. 원천 ID·버전·관계 방향·라이선스·매핑 근거를 유지한다. 사례/부분 관계를 종류 관계와 구별한다.
4. 외부 근거와 우리 양쪽 정의를 함께 검토하고 불명확한 매핑·관계는 미확인으로 남긴다.
5. 우리말샘은 이용조건과 인증 접근을 준비한 뒤 추가한다. 온용어·KLRI는 정의/대응 보조,
   ConceptNet은 후순위로 둔다. 실제 매칭률·추가 후보의 정확도 비교는 새 ADR에서 수행한다.

새 외부 원천은 현재 `glossary assemble/review`의 입력 계약에 자동 연결되어 있지 않다.
이번 작업은 이 보고서만 추가했고 사전 DB·운영 설정·완료 실험·GENOS 상태를 변경하지 않았다.
