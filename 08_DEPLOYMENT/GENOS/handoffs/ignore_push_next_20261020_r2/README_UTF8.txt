R2 수정본 사용법
GENOS_NEXT_COPY_PASTE_20261020_R2.txt 전체를 현재 GENOS 터미널에 붙여넣으세요.
이전 R1 TXT는 사용하지 않습니다. 기존 GENOS_IGNORE_TRANSFER_20261020_R1 폴더와 STATE.json은 보존합니다.
다른 add/rm/amend 명령, 데이터 파일 강제 add, 코드 재설치는 필요하지 않습니다.
PUSH_CONFIRMED=커밋번호가 나오면 Git 전송 확인 완료입니다.
그다음 해당 커밋의 GENOS 코드서빙 리비전 배포와 워크플로우 편집기 반영/테스트를 진행합니다.
실패하면 로그 경로와 종료코드를 남기고 중단합니다.
ZIP 경로를 이용할 경우 실제 업로드한 TRANSFER에서 아래처럼 실행할 수도 있습니다.
python3 -m zipfile -e ./GENOS_NEXT_COPY_PASTE_20261020_R2.zip ./GENOS_NEXT_COPY_PASTE_20261020_R2
bash ./GENOS_NEXT_COPY_PASTE_20261020_R2/GENOS_NEXT_COPY_PASTE_20261020_R2.txt
