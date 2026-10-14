# CM 51건 shortcut·legal_wiki 등록

2026-10-08 로컬 MAIN46의 CM 공통 등록은 `cm51-native-team-20261008-r1`이다.
최종 R15의 같은 51문항·98근거 seed를 새 로컬 1,546문서/21개 대상 문서에 다시 연결했다.
문서 ID·조문 단위·본문 span 해시와 source/navigation/fulltext 결속을 새로 확인했다.
기존 공통 51건은 RETIRED 이력으로 남기고 개인 데이터와 lifecycle은 변경하지 않았다.
다른 사용자·팀의 공통 조회, 문서 ACL 축소 시 차단, 외부 transport에서 내부 CM 경로
차단을 확인했다. 실제 로컬 `service.service`가 이 소비 코드를 선택하며 모델 호출은 0회다.
[실제 등록·권한·세대 확인](../../../09_ARTIFACTS/AUDITS/20261008-native-cm-serving/live-cm-connection.json),
[활성 선택·SQLite 백업·롤백](../../../09_ARTIFACTS/AUDITS/20261008-native-cm-serving/completion.json).
아래 GENOS 인계는 해당 시점의 기록이며 이번 로컬 활성화로 현장 배포 상태가 바뀌지 않는다.

2026-10-08 후속 R14 사전 검사 실패의 현행 보완 인계는
[R15](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r15/GUIDE_UTF8.txt)다.
오류 로그 R10 적용 뒤 R14가 이전 조사 한도 service 해시와 비교해 중단한 것을 사진과
모의 순서로 확인했다. R15는 R10 VERIFIED 영수증·부모 백업·APPLIED_CODE.zip 전체와
고정 변환을 검증하고 CM 이름 연결/등록 보호와 함께 보존한다. 원문/RAW/DB/예산/로그/
백업은 유지한다. 현재 DEV의 TRANSFER에서 실행하며 상태·영수증은 `cm-oneclick-r15/`다.
R10 또는 조사 한도를 다시 apply/undo하지 않는다. R10의 부분 apply 복구 명령 자체를
수정한 것은 아니며 VERIFIED 상태만 지원한다. 로컬 MAIN45와 GENOS 현장 배포는 별도다.
이름/등록 계약79개와 최종 R15 첨부 TXT 검사9개가 통과했다. 7개 모의 설치 상태별2회 실행과
R15 부분 쓰기 실패 복구 후 실제 TXT 재개를 확인했다. 51건/98근거 등록·중복 방지·기존 코드/
DB/세대/로그/백업 보존·같은 checkout/generation gate/모의 push·코드 원복이 통과했다.
[검증 기록](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r15/VALIDATION.json).
삼성메일 SENT `1a118d77f4cbb635`의 수신자와 ZIP/독립 RUN TXT/안내 TXT 세 첨부 이름·
정확한 크기를 확인했다. [발송 기록](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r15/EMAIL_SENT.json).
메일 발송과 현장 수신·실행·배포 성공은 별도다.
아래 R14/R12 인계는 당시 검증·발송 이력이다.

2026-10-08 이름 연결 보완의 당시 인계는
[R14](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r14/GUIDE_UTF8.txt)다.
R11/R12 대신 실행한다. 정식명·개별 파일명·보존된 원래 이름으로 연결하고 부모 폴더명만으로
다른 법령을 연결하지 않는다. 정상 규정명의 서식/별첨은 보존하며 추가된 개정·참고·비본문
역할/폴더와 분해 한글을 구분한다. 기존 등록도 새 문서·조문·근거와 대조해 같으면 재사용하고
다르면 보존 후 중단한다. RAW 이름·원문 generation·예산 코드/설정·DB·백업은 보존한다.
관련 계약84개, 등록 외규 body114경로·CM33경로의 자기/교차 이름 검사, 로컬 선택159문서의
CM21개 유일 연결,216개 recipe/엔진 pin, 최종 첨부 TXT의 모의4설치 상태별2회 실행과
등록51건/98근거·중복 방지·같은 checkout/generation gate/모의 push·코드 원복이 통과했다.
[검증 기록](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r14/VALIDATION.json).
삼성메일 SENT `1a1170217b6b0164`의 수신자와 ZIP/독립 RUN/안내 세 첨부 이름·정확한 크기를
확인했다. [발송 기록](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r14/EMAIL_SENT.json).
현행 문서 매핑·상태·영수증·백업·로그는 `TRANSFER/cm-oneclick-r14/`에 저장한다.
로컬 MAIN45는 그대로이며 실제 GENOS 적용·리비전·워크플로우 성공은 현장 확인이 필요하다.
미발송 R13 검증 후보와 아래 R12 이력은 보존한다.

2026-10-08 당시 복구 인계는
[R12](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r12/GUIDE_UTF8.txt)다.
독립 파일명 끝의 `본문`을 추가로 연결한다. 기존 전문/조문·시행령/시행규칙/개정문 구분을
유지하며 RAW 이름이나 선택 원문 generation을 바꾸지 않는다. R11 코드 적용 뒤
`target body document missing: 중소기업기본법`으로 중단한 상태에 이어 적용한다.
조사 한도 수정이 있으면 R11 백업의 부모 inventory와 예산 metadata를 함께 검증한다.
관련 계약70개·216개 recipe/엔진 pin·실제 첨부 TXT의 모의3설치 상태별2회 실행에서
51건/98근거 등록, 중복 방지, 원문·기존 DB·예산·백업·실패 이력 보존, 같은 checkout
commit/generation gate/모의 push와 코드 원복을 확인했다.
[검증 기록](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r12/VALIDATION.json).
SENT `1a116e71fe37d263`의 수신자·ZIP/독립 RUN TXT/안내 TXT 세 첨부 이름과 정확한 크기를
확인했다. [발송 기록](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r12/EMAIL_SENT.json).
당시 매핑은 `TRANSFER/cm-oneclick-r12/DATA_CHECKED.json`, 상태·백업·영수증·실패 로그는
같은 R12 폴더에 저장한다. 이전 R8/R10/R11·조사 한도 기록은 보존한다.
실제 원문 누락은 이 이름 처리만으로 해결되지 않는다. 로컬 MAIN45는 그대로이고
실제 GENOS 등록·리비전·워크플로우 성공은 현장 실행 전까지 미확인이다.

후속 [R12 이름 변환 대조](../../../09_ARTIFACTS/AUDITS/20261008-cm-name-patterns-r12/README.md)에서
정상 제목의 `서식` 등 부분 문자열 제외, 서로 다른 정식명을 부모 폴더명으로 연결,
일부 개정/참고 표기와 NFD 한글 배제 누락을 확인했다. 현재 로컬 CM21의 후보 연결은
각1개였으며 추가 문제는 이후 R14에서 보완했다. 실제 GENOS 선택 결과로 확대하지 않는다.

2026-10-07 현장 문서명 연결 수정의 당시 복구 인계는
[R11](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11/GUIDE_UTF8.txt)이다.
이전 R10은 삼성메일 SENT `1a1167e769559d89`에서 ZIP/독립 실행 TXT/안내 세 첨부를 확인했다.
후속 사진의 조사 한도 R1 check/apply/verify는 통과했지만 CM R10은 R8 inventory 차이로
코드 적용 전에 중단했다. 검증된 R1의 service 변경과 부모 inventory를 R11에서 함께 확인해
조사 한도 수정을 보존한다. `unzip` 대신 Python3 표준 ZIP 도구를 사용한다.
R11은 삼성메일 SENT `1a11697955af743f`로 ZIP/독립 RUN TXT/안내 TXT를 발송하고
수신자와 세 첨부 이름·정확한 크기를 확인했다. 당시 실패 상태에서 원복 없이 이어 적용했다.
로컬159공개 원문과
현장2121문서의 일괄 해시 대조는 이 등록의 동일 원문 판정 기준으로 사용하지 않는다.

새 `source_binding_policy=target-selected-document-article-v1` 패키지는 논리 규정명과
본문 파일 별칭으로 현장 문서를 찾고 각 조문 좌표를 현재 source에서 한 건으로 해결한다.
로컬 해시/판본은 참고 계보이며 현장 문서 ID·조문 본문/해시·세대 결속이 실제 등록 근거다.
개정문·비교표는 본문 후보에서 제외하고 기존 표현본 우선순위를 따른다. 동일 우선순위
본문 중복, 조문 중복/누락, ACL 및 source/nav/fulltext 불일치는 쓰기 전에 중단한다.
당시 R11의 정식명↔현장 이름/ID/원본 SHA 매핑은 `TRANSFER/cm-oneclick-r11/DATA_CHECKED.json`,
상태·코드 백업·SQL 백업·등록 영수증·실패 로그는 같은 R11 폴더에 남긴다.
기존 R8/R10와 조사 한도 백업/로그는 해당 이전 경로에 보존한다.
기존 exact-source 패키지는 로컬/같은 입력의 엄격한 이름/해시 계약을 그대로 사용한다.

관련 계약34개,216개 반입 recipe pin, 정확한 첨부 TXT의 모의 현장21문서에 대한
R8 실패 재현과 R10 등록51건/98근거 및 재실행2회를 확인했다. 동일 checkout의 commit/
generation gate/모의 local remote push, 원문·기존 DB·실패 이력 보존도 확인했다.
모델 호출0회이고 로컬 MAIN45/기존 공통 DB는 그대로다. 실제 GENOS 등록·배포·
워크플로우 성공은 미확인이다. R11의216개 recipe/엔진 pin과 실제 첨부 TXT를 모의3설치
상태에서 각각2회 검사했다. 사진과 같은 순서의 실패·복구, R10 이후 조사 한도 상태,
무패치 기존 입력, 예산 코드 보존·재실행·같은 checkout/generation gate·모의 push·
미승인 변경 거부를 확인했다. [현장 관찰 및 로컬 검증](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11/VALIDATION.json).
아래 R8와 엄격한 로컬 해시 대조 설명은 이전 이력이다.

2026-10-07 사용자 추가 요청으로 진단 범위를 CM21문서에서 로컬 MAIN45의 전체159문서와
현장 선택 원문 전체로 확장했다. [전수 진단 R2 안내](../../../08_DEPLOYMENT/GENOS/handoffs/cm_source_diagnose_20261007_r2/GENOS_CM_SOURCE_DIAG_20261007_R2_GUIDE.txt)의
한 줄은 문서명+원본 SHA와 이름을 무시한 원본 SHA를 독립 대조하고 이름 차이·원본 누락/변경·
현장 추가·중복을 구분한다. 원문 DB 해시를 먼저 검증하고 기존 코드/등록 상태를 변경하지 않는다.
[삼성메일 발송 기록](../../../08_DEPLOYMENT/GENOS/handoffs/cm_source_diagnose_20261007_r2/EMAIL_SENT.json)의
SENT `1a1163917bae06bf`에서 RUN/안내 TXT 두 첨부 이름·크기를 확인했다.
아래21문서 진단 R1 대신 R2를 사용한다. 현장 일치 결과와 그에 따른 등록 복구는 아직 미확인이다.

2026-10-07 현장 R8 실행은 공통 코드 검사 후 `package-check`에서
`source document version missing or ambiguous: 코스닥시장 상장규정`으로 중단했다.
사진은 선택 원문의 문서명+원본 SHA가 정확히 한 건 매칭되지 않음을 확인한다.
문서 누락·원본 해시 차이·동일 원본 중복은 추가 대조 전까지 미확인이다.
[읽기 전용 진단 안내](../../../08_DEPLOYMENT/GENOS/handoffs/cm_source_diagnose_20261007_r1/GENOS_CM_SOURCE_DIAG_20261007_R1_GUIDE.txt)의
TXT로 원본 패키지와 R8의 같은 세대 설정을 확인해 대상21문서를 한 번에 대조한다.
이 진단은 코드·원문·등록 DB를 변경하지 않는다. 현장 진단과 복구·등록 성공은 아직 미확인이다.
아래 R8의 준비/로컬 검증 기록은 현장 등록 완료를 뜻하지 않는다.

현행 사용자 실행은 [자동 인계 R8](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r8/GUIDE_UTF8.txt)의 TXT 한 번 실행이다. 수동 generation/runtime/receipt 경로와 사용자·팀 JSON을 없앴다. 다른 NFS 이관 메일에서 확인한 경로를 사용하고 등록 영수증을 자동 저장한다. 코드 적용·원문 검사·commit·실제 generation gate·공통 등록/검증·push를 자동 처리하며, 생성한 서빙 경로 설정을 실제 `service.py`가 읽으므로 리비전에 CM 경로 환경변수를 추가하지 않는다. NFS 목록 확인 코드와 기존 개인 DB 기록을 보존한다. 최종 새 리비전 배포·워크플로우 확인은 현장 UI에서 한다.

[삼성메일 발송](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r8/EMAIL_SENT.json)의 SENT `1a1161a33176a64a`에서 최종 RUN/짧은 안내 TXT 두 첨부와 수신자·제목을 확인했다. 사용자 입력은 안내의 한 줄이며, 실제 GENOS 적용·리비전 배포 성공은 현장 로그로 별도 확인한다.

R8의108입력 inventory/216개 정적 recipe와 엔진 pin, 대표6상태의 준비/변조 보존 검사, 환경변수 없는 최종 TXT 전체3회 실행과 설정 계약9개가 통과했다. 전체 실행은 실제 로컬 공개 CM 원문을 읽기 전용 공유해51건/98근거 등록, 기존 SQLite 보존, 중복 없는 재실행, 동일 commit/generation 배포 gate, 모의 로컬 remote push를 확인했다. 모델 호출0회이며 실제 GENOS 적용 성공과 구분한다. 로컬 MAIN45와 기존 로컬 공통 등록은 바꾸지 않았다. 이전 R4/R6 안내는 아래 당시 이력으로 보존한다.

2026-10-07 사용자 정정: 지정 CM51은 **모든 사용자가 공유하는 공통 숏컷**이다. 이전에 개인 `jin`/팀 `CM` scope로 등록한 것은 의도를 잘못 구현한 상태였다. 현재 작업 코드와 [공통 인계 R6](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_common_20261007_r6/GUIDE_UTF8.txt)는 `package-* --store-version 4 --common`으로 한 번 등록한다. 소비 사용자·팀 JSON을 받지 않는다.

공통 데이터 revision은 `cm51-curated-common-20261007-r3`다. 기존 로컬 `cases-v4.sqlite`에 공통 활성51건/근거98개를 등록했고, 이전 개인 R1/R2의102건은 RETIRED 이력으로 보존했다. 공통 legal_wiki를 같은 SQL에서 한 번 생성한다. 기존 대화·사실·개인 native 숏컷의 권한 범위는 그대로이며, 모든 개인 기록을 공통으로 승격하지 않는다.

요청의 실제 사용자·팀은 문서 ACL·대화 이력·감사에 사용한다. 공통 조회도 현재 원문 권한과 source/nav/fulltext 세대 결속을 검사하며, 외부 모델에서는 이 내부 CM 경로를 제공하지 않는다. 공통 읽기 권한은 공통 수정·publish·retire 권한을 주지 않는다. 공통 작업의 내부 operator는 파일 접근이 가능한 CLI가 생성하며 사용자 JSON으로 가장할 수 없다.

[로컬 등록 확인](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_common_20261007_r6/LOCAL_REGISTRATION_VERIFIED.json)에서 다른 사용자·팀 세 곳이 같은51개 unit을 읽고 같은 근거 경로를 회수했다. 개인/공통·권한 축소·원문 변경·외부 호출 차단·원자성·이력 보존·공통 쓰기 제한·기존 개인 메뉴 계약20개가 통과했다. 모델 호출은0회이며, 답변 품질51건 통과를 뜻하지 않는다. 현장 R4 설치 위에 R6 코드 반입·commit/gate/push·리비전 배포·공통 등록·워크플로우 검증이 필요하다. 로컬 MAIN45는 그대로다.

아래는 개인 scope로 처리한 최초 등록과 R4 인계의 당시 이력이다. 현행 등록에는 위의 공통 R6를 사용한다.

최종 공통 R6의 첨부 TXT는 알려진54설치 상태/331명령, 대표9계열의 계약227개, 같은 committed checkout·compact 모의 generation의 gate6개를 통과했다. [삼성메일 정정 발송](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_common_20261007_r6/EMAIL_SENT.json)의 SENT `1a115fd2f87b2ff3`에서 수신자·제목과 첨부5개 이름/정확한 크기를 확인했다. 현장 적용과 리비전·워크플로우 성공은 별도 확인이 필요하다.

사용자 요청에 따라 과거 오답·미답변 CM을 등록했다. ADR-0426의 실제 전수 실행/후속 채점에는 51건 모두 미답변 기록이 있다. 이것은 현재 MAIN45에서 51건 모두 실패한다는 뜻이 아니다. 이후 의미 오답 기록과 이전 완료 실험은 변경하지 않았다.

정본은 `01_DATA/review/cm_core_e2e_v3.json`이다. 주 조문과 조건·예외·정의·준용·위임 조문 총98개가 현재 선택된 로컬 source generation의21문서에 모두 존재했다. 새 원문 반입이나 NFS generation 교체는 하지 않았다.

등록된 데이터 revision은 `cm51-curated-20261007-r2`, 로컬 owner는 `jin`, team은 `CM`이다. 기존 `90_RUNTIME/semantic/case-memory/cases-v4.sqlite`의 독립된 PRIVATE scope에 활성51건을 추가했고 같은 SQL 정본으로 legal_wiki를 생성했다. 초기 등록51건은 RETIRED로 보존했다. DB 전체 교체/복사나 전역 사용자·팀 권한 확대는 하지 않았다.

업무 기준답변은 `ACTUAL_WORK_REFERENCE_NOT_APPROVED_INTERPRETATION` observation으로 보존한다. 법률 claims/procedures는 비어 있으며 completeness는 OPEN이다. 성공한 모델 goal/route를 만들어 가장하지 않는다. `sw_import`의 불변 receipt와 source dependency가 등록 authority다.

소비 경로는 기존 `WikiExecution.stage(RECALL)` → `core_evidence_route.lookup` → `law_candidates.discover/direct_discovery`다. curated route는 현재 원래 입력 질문 또는 명시적으로 등록된 문자열로 찾는다. 모델이 task를 요약해도 원래 입력으로 조회하며 실제 현재 facts는 SELECT/ASSESS에 유지한다. 원문을 현재 source handles로 다시 확보하고 추가 조사가 필요하면 기존 fulltext로 돌아간다. 이전 답변의 결론을 재생하지 않는다. 표현 전체의 의미 일반화는 검증하지 않았다.

CM-016에는 원래 행사 시점 질문과 ADR-0684의 사진 정규화 입력을 연결했다. 실제 현재 원문/source handles 검사에서 벤처기업법16조의5, 시행령11조의4, 준용 연결16조의3·16조의4를 직접 회수했다. 이 검사는 법률 답변 의미 채점 또는 내부 모델 품질 인증이 아니다.

원본 파일·조문 본문 해시가 다르거나 대상 문서 권한이 부족하면 등록 전체를 중단한다. 기존 source/nav/fulltext 세대 바인딩도 검사한다. 같은 데이터/권한/세대 import는 중복 등록하지 않는다. rollback은 해당 import의 unit만 retire하고 등록·실패·원문 이력을 보존한다. retire된 import를 같은 재실행으로 다시 publish하지 않는다. 다른 사용자/팀, 줄어든 문서 권한, 다른 source generation, 외부 모델에는 해당 경로를 제공하지 않는다.

등록은 실험/모델 호출이 없는 데이터 운영 작업이다. source/ACL/원문 바인딩/원자성/현재 질문/롤백 계약10개, 기존 source route 계약23개, GENOS 알려진 코드9상태에서 첨부 TXT61명령, 세 field code variant의 native 계약23개씩, 동일 committed checkout의 compact mock generation 게이트3개가 통과했다. 신규 실험/전체51문항 답변 성공률/의미 개선이나 unseen 일반화 성능을 주장하지 않는다. 이후 CM 평가는 이 등록 자료를 사용하는 arm에서 training/in-sample임을 표시해야 한다.

실제 확인한 등록과 별도로 **로컬 활성 MAIN45와 frozen 코드268파일은 변경하지 않았다.** 새 curated 소비 코드는 작업 코드와 GENOS 인계 R4에 연결돼 있고 MAIN45에는 포함되지 않는다. 로컬 MAIN 활성화·GENOS 코드 반입·Git push·리비전 배포·현장 workflow 질문 성공을 등록 성공과 혼동하지 않는다.

최종 인계는 [CM 데이터 R4](../../../08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_data_20261007_r4/GUIDE_UTF8.txt)다. 선행 core shortcut R1에 해시 고정36파일 패치를 적용하고, 실제 현장 사용자/팀과 선택 generation/runtime/state로 기존 등록 모듈을 호출한다. 현장 원문과 정확히 결속하므로 원문 전체/기존 DB를 첨부하지 않는다. 현재 Codex 세션은 GENOS에 직접 접근하지 못하며, 메일 전달 뒤 현장 반입·검증이 필요하다.

R1/R2 인계 준비 중 실패도 보존했다. R2 테스트의 shared state 설정은 HTTP fixture의 runtime 격리를 깨뜨렸고, 이어진 현장 모의 반입에서는 GENOS inventory에 없는 로컬 `06_TOOLS/pipeline.py` 경로가 없었다. 최종 R3는 동일 배포 모듈 `lawrag.pipeline.unified_memory.main`을 현장 Python으로 호출한다. 이력은 이전 인계 디렉터리의 압축 로그와 최종 `VALIDATION_BUILD_NOTES.txt`에 남았다.

최종 인계 R4는 core shortcut R1의9종뿐 아니라 최신 화면표시 R2 적용18종도 지원한다. UI·검색·로그 변경은 각 선행 inventory에서 보존한다. R3까지의 데이터/게이트 검증을 유지하고, 최종 R4의 추가27종/배포게이트 결과는 인계 디렉터리 VALIDATION.json과 요약에 기록한다.
