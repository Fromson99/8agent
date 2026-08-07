# 접속 프로파일 — 규정 문서 수집기 (Phase 0)

검증일: 2026-08-07. 검증 도구: curl 8.18.0 (OpenSSL 3.5.5), Python 3.14.4 + requests 2.32.5.
모든 항목은 실제 요청으로 확인했다. 요청 간격 1초 유지, 도메인당 요청 수 10건 미만.

## 요약

| 도메인 | 접속 조건 | TLS | 세션 선행요청 | robots.txt |
|---|---|---|---|---|
| www.kofia.or.kr | 조건 없음 | TLSv1.2 DHE-RSA | 불필요 | 없음 (에러페이지로 307) |
| law.kofia.or.kr | 조건 없음 | TLSv1.2 DHE-RSA | 불필요 (첫 요청에서 JSESSIONID 발급) | 없음 (에러페이지로 307) |
| www.fss.or.kr | **UA에 `curl` 문자열 금지** | TLSv1.2 ECDHE-RSA | 불필요 | 있음 — Yeti(네이버봇)만 제한 |
| www.krx.co.kr | 조건 없음 | TLSv1.3, HTTP/2 | 불필요 | 없음 (404) |
| law.krx.co.kr | 조건 없음 | TLSv1.2 ECDHE-RSA | 불필요 (첫 요청에서 JSESSIONID 발급) | 없음 (404) |

Python `requests` 기본 설정(기본 UA `python-requests/2.32.5` 포함)으로 **5개 도메인 전부 통과**를
확인했다. `LegacyTLSAdapter`·SECLEVEL 완화는 이 환경(OpenSSL 3.5.5)에서는 불필요하다.

---

## 금투협 — www.kofia.or.kr / law.kofia.or.kr

- **필요 헤더**: 없음. 기본 curl UA로도 200.
- **TLS**: TLSv1.2, `DHE-RSA-AES256-GCM-SHA384`, 인증서 `CN=*.kofia.or.kr`.
  OpenSSL 3.5.5 기본값으로 협상 성공. DHE 계열이므로 구형 배포판(SECLEVEL=2 + 소형 DH 키
  거부)에서는 실패할 수 있다 — 그 경우에만 Task 문서의 `LegacyTLSAdapter` 적용.
- **세션**: `law.kofia.or.kr`는 첫 응답에서 `WMONID` + `JSESSIONID` 쿠키를 발급한다.
  선행요청 없이 `/service/main/main.do` 직접 GET으로 200. 이후 요청에 세션이 필수인지는
  Phase 1에서 확인.
- **리다이렉트 특성**: 루트(`/`)는 HTML meta refresh / JS(`document.location.href`)로
  이동시킨다. HTTP 리다이렉트가 아니므로 curl `-L`로는 따라가지 못한다.
- **주의 — 404 위장**: 존재하지 않는 경로는 404가 아니라 **307 → `/common/error.html` (200)**
  로 떨어진다. 상태코드만으로 성공 판정하면 에러페이지를 본문으로 저장하게 된다.
  200이어도 콘텐츠 타입·크기·본문 검증 필수 (Task §8-3와 일치).
- **레이트 리밋**: 진단 수준 요청량(1초 간격)에서는 관찰되지 않음.
- **재현 curl**:
  ```
  curl -sS "https://law.kofia.or.kr/service/main/main.do"   # 200, 24397 bytes
  ```

## 금감원 — www.fss.or.kr

- **차단 방식**: UA 문자열에 `curl`이 포함되면 TLS 핸드셰이크 완료 후 **HTTP 응답 없이
  연결을 끊는다** (`SSL_read: unexpected eof`). 403이 아니라 커넥션 드롭이므로
  타임아웃/SSL 에러로 보인다는 점 주의.
- **통과 조건**: UA만 바꾸면 됨. `Mozilla/5.0 ...`은 물론 `corpus-collector/0.1`,
  `python-requests/2.32.5`(requests 기본값)도 통과 확인. Referer·Accept-Language 불요.
  수집기에서는 브라우저 UA + `Accept-Language: ko-KR`을 고정 사용 권장.
- **TLS**: TLSv1.2, `ECDHE-RSA-AES256-GCM-SHA384`, `CN=*.fss.or.kr`. 특이사항 없음.
- **세션**: 첫 요청에서 `WMONID` + `JSESSIONID_user` 발급, `/` → 302 →
  `/fss/main/main.do?menuNo=200000`. 선행요청 없이 main.do 직접 GET으로 200 (378KB).
- **robots.txt** (전문):
  ```
  User-agent : Yeti
  Disallow: /bos/
  Disallow: /upload/
  Disallow: /fss/cvpl/stepNotice/
  Disallow: /fss/cvpl/extincNotice/
  ```
  네이버 Yeti 봇만 대상. 일반 UA에 대한 제한 없음. `/upload/`가 Yeti에 막혀 있는 점을 보면
  첨부파일이 이 경로에 있을 가능성 — Phase 1에서 확인.
- **레이트 리밋**: 진단 수준 요청량에서는 관찰되지 않음.
- **재현 curl**:
  ```
  curl -sS -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36" \
    "https://www.fss.or.kr/fss/main/main.do?menuNo=200000"   # 200, 378523 bytes
  ```

## 거래소 — www.krx.co.kr / law.krx.co.kr

- **필요 헤더**: 없음. 기본 curl UA로도 200.
- **TLS**: 메인은 TLSv1.3 + HTTP/2 (`CN=*.krx.co.kr`), 내규 서비스(law)는 TLSv1.2
  `ECDHE-RSA-AES256-GCM-SHA384`. 특이사항 없음.
- **내규 검색 서비스 진입 경로**: `https://law.krx.co.kr/` → JS 리다이렉트
  (`window.location = "http://law.krx.co.kr/las"` — **http로 하드코딩**되어 있으나
  https도 동작) → `/las` 302 → **`https://law.krx.co.kr/las/`** 가 실제 진입점 (200).
- **인코딩 주의**: law.krx.co.kr 응답은 `charset=EUC-KR`. 본문 저장·파싱 시 인코딩 폴백 필요.
- **경로 검증 존재**: 임의 경로(`/robots.txt`) 접근 시 404 + "정상적인 경로의 접근이
  아닙니다" 에러 본문. 일부 엔드포인트에 Referer/세션 검증이 있을 가능성 —
  [Phase 1에서 확인].
- **세션**: `/las/` 첫 응답에서 `JSESSIONID` 발급. 메인 사이트는 `SCOUTER` 쿠키(APM 추적용).
- **파일 서버 분리**: 페이지 소스에서 `file.krx.co.kr`(첨부), `pdf.krx.co.kr`(PDF) 도메인
  확인됨. 첨부 다운로드 시 이 도메인들의 접속 프로파일 별도 확인 필요 — [Phase 1에서 확인].
- **레이트 리밋**: 진단 수준 요청량에서는 관찰되지 않음.
- **재현 curl**:
  ```
  curl -sSL "https://law.krx.co.kr/las/"   # 200, 655 bytes (frameset 추정)
  ```

---

## 수집기 공통 권장 설정

- 세션: `requests.Session` + 브라우저 UA + `Accept-Language: ko-KR,ko;q=0.9` 고정.
  (FSS 요구조건이자 전 도메인 무해. 도메인별 분기 불필요.)
- TLS: 기본값 사용. `verify=False` 금지. DHE 협상 실패가 나는 환경에서만
  KOFIA 한정 `LegacyTLSAdapter`.
- 성공 판정: 상태코드 200 + Content-Type + 본문 크기/매직바이트 검증.
  KOFIA(에러페이지 200), KRX(에러 본문 200 가능성) 때문에 상태코드만으로는 불충분.
- 요청 간격 1초, 동시 요청 1개 (Task §8-3).
