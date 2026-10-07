# GENOS 조사 제어 통합 R3

사용자 현장 사진의 `CHECKOUT_DRIFT: 08_DEPLOYMENT/GENOS/stream_app.py`를 재현한 후,
과거 NFS 설치기가 만든 `service.py`와 `stream_app.py`의 정확한 선행 해시를 추가했다.
출고 코드 282개는 [R2](../investigation_control_20261007_r2/README.md)와 동일하고,
선택 로컬 MAIN generation 43의 서빙 265개 파일도 그대로다. 새 실험이나 모델 호출은 없다.

- [실행 안내](GUIDE_UTF8.txt)
- [원인 및 검증 보고서](COMPATIBILITY_REPORT_UTF8.txt)
- [ZIP](GENOS_INVESTIGATION_CONTROL_20261007_R3.zip)
- [전체 Bash 실행 TXT](GENOS_INVESTIGATION_CONTROL_20261007_R3_APPLY.txt)
- [워크플로우 전체 TXT](GENOS_INVESTIGATION_CONTROL_20261007_R3_WORKFLOW_PASTE_ALL.txt)
- [해시 재현 근거](PREDECESSOR_PROOFS.json)
- [반입 기록](HANDOFF.json)
- [로컬 검증](DELIVERY_VALIDATION.json)

R2를 덮어쓰지 않고 R3로 교체 인계한다. 기존 데이터 세대와 runtime DB는 복사·재구축하지 않는다.
사진에서는 R2 ZIP 및 cache 사전 검사 PASS, 코드 적용 전에 중단했다.
R3 현장 적용·전체 세대 검사·push·코드서빙 리비전·워크플로우 실제 질의는 별도 미확인 상태다.

삼성파트너 메일 발송 후 Gmail SENT `1a1139ec2056e2f1`에서 수신자와 첨부 5개 이름·크기를 확인했다.
[발송 기록](EMAIL_SENT.json), [발송 재확인](EMAIL_VERIFIED.json)에 남겼다. R2 대신 R3 ZIP/TXT를 사용한다.
