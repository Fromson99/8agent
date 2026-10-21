사진의 커밋 수정까지 완료된 상태에서 쓰는 다음 단계입니다.
첨부 GENOS_NEXT_COPY_PASTE_20261020_R1.txt 전체를 현재 GENOS 터미널에 한 번에 붙여넣으세요.
또는 파일을 업로드한 폴더에서 bash ./GENOS_NEXT_COPY_PASTE_20261020_R1.txt 로 실행해도 같습니다.
기존 GENOS_IGNORE_TRANSFER_20261020_R1 폴더와 STATE.json을 보존하세요.
스크립트가 현재 위치·checkout·홈의 바로 아래에서 실제 TRANSFER와 적용된 패키지를 찾습니다.
찾지 못하거나 둘 이상이면 중단하며 잘못된 폴더를 임의 선택하지 않습니다.
검증 통과 뒤 수정된 main 커밋 하나만 일반 push합니다. 비밀번호를 물으면 평소처럼 입력하세요.
add/rm/amend/force-push/데이터 삭제는 실행하지 않습니다.
PUSH_CONFIRMED=... 가 나오면 Git 전송 확인 완료입니다.
다음은 GENOS 코드서빙에서 그 커밋의 리비전 배포입니다.
기존 MAIN92 WORKFLOW_PASTE_ALL.txt를 아직 반영하지 않았다면 편집기에 교체·저장한 뒤 워크플로우 테스트 화면에서 확인하세요.
코드서빙 직접 테스트 화면/API 실행은 요구하지 않습니다.
로그 경로와 종료코드는 마지막에 출력됩니다. 오류 시 다음 작업을 자동 진행하지 않습니다.
ZIP으로 받았다면 실제 업로드한 TRANSFER 위치에서 다음과 같이 풉니다.
python3 -m zipfile -e ./GENOS_NEXT_COPY_PASTE_20261020_R1.zip ./GENOS_NEXT_COPY_PASTE_20261020_R1
bash ./GENOS_NEXT_COPY_PASTE_20261020_R1/GENOS_NEXT_COPY_PASTE_20261020_R1.txt
