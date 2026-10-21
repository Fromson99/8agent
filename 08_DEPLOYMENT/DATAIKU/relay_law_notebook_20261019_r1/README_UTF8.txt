Dataiku 중계서버 통신 확인 → 법제처 호출 / 2026-10-19 R1

실행에 필요한 파일은 DATAIKU_RELAY_LAW_20261019_R1.ipynb 하나입니다.
앞서 보낸 LAW_API/PHOTO_INPUTS 노트북 대신 이번 통합본으로 연결 확인을 진행하세요.

1. Dataiku 프로젝트의 Python Notebook으로 ipynb를 가져옵니다.
2. 준비 셀에서 중계 주소와 CA 설정을 확인합니다. 기본 주소는 이전 사진의 개발계입니다.
3. 공통 코드 셀을 수정 없이 실행합니다. 이 셀은 네트워크 호출을 하지 않습니다.
4. '1. API 중계서버 통신 확인'을 실행합니다. /law/DRF로 HEAD 1회, 인증값과 target_url 없음.
5. HTTP 응답을 받았으면 '2. 중계를 통해 법제처 법령 본문 호출'을 실행합니다.
   국가법령정보센터에 등록한 OC를 입력하고, 중계 Cookie가 필요하면 현재 값을 입력합니다.
   입력값은 화면에 표시하지 않습니다. 이전 입법센터 OC를 같은 인증값으로 가정하지 않습니다.
6. '3. 결과 확인'에서 단계별 상태와 본문 예시를 확인합니다.

HEAD가 401/403/404/405여도 현재 중계 주소 또는 프록시 경로에서 HTTP 응답을 받은 것입니다.
이 결과만으로 중계 인증·법제처 API 성공을 판정하지 않습니다.
법제처 GET의 BODY_OK는 HTTP200 + XML 법령 ID/명칭/조문 확인이 통과한 상태입니다.
기본 조회는 자본시장과 금융투자업에 관한 법률의 공포일 기준 본문(target=law) 1건입니다.
시행일 기준 eflaw·행정규칙·예고·별표·전체 수집 성공을 뜻하지 않습니다.

같은 run_id의 셀을 다시 실행하거나 커널을 재시작해도 요청을 중복 전송하지 않습니다.
연결 설정 변경 후 새로 확인하려면 설정 셀의 run_id를 relay-law-02처럼 바꾸고 위에서부터 실행합니다.
이전 실패/중단 기록은 삭제하지 않습니다. IN_FLIGHT/INTERRUPTED는 완료 불명이므로 자동 재시도하지 않습니다.
실행당 HEAD1회 + GET1회, 자동 재시도0회, 새 요청 시작 전 15분 한도 검사를 적용합니다.

결과는 실행 커널의 dataiku_relay_law_results/<run_id>/에 저장됩니다.
connection_result.json은 단계별 요약이며 법령 응답과 개별 receipt는 law_response 하위에 있습니다.
이 파일은 Oracle·Managed Folder·RAG MAIN에 자동 적재하지 않습니다.

ZIP/TXT는 보조 형식입니다. ipynb를 가져왔다면 실행할 필요가 없습니다.
ZIP을 사용하려면 다운로드 위치에서 풀고 안의 동일 ipynb만 가져옵니다.
Linux 터미널에서 풀 경우:
python3 -m zipfile -e ./DATAIKU_RELAY_LAW_20261019_R1.zip ./DATAIKU_RELAY_LAW_20261019_R1
ipynb 가져오기가 불가능할 때만 RUN.txt 전체를 빈 Python Notebook의 코드 셀에 붙여 넣습니다.
RUN.txt는 Python 코드이며 bash 실행 파일이 아닙니다.

로컬 검증: 실제 전달 Notebook 셀로 15검사 통과. 로컬 TLS 서버에 실제 HEAD→GET 요청 순서·헤더·결과 저장 확인.
사내 Dataiku·중계서버·GENOS 접속과 외부 법제처 새 호출은 수행하지 않았습니다.
기존 RelayCheck 전송/본문 검증 코드는 변경 없이 포함했습니다. MAIN/GENOS 배포 변경은 없습니다.
