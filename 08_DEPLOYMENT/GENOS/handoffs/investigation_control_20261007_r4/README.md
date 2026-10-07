# GENOS 조사 제어 통합 R4

두 현장 사진의 반입 중단을 확인했다. 조사 제어 R2에는 이전 NFS 진단 훅을 적용한
`stream_app.py`와 `service.py`의 정확한 선행 해시가 빠져 있었다. NFS R7는 설치 후
`checkout_commit_preflight`에서 작은 진단 커밋 범위 밖의 추적 수정 때문에 멈췄다.
사진만으로 그 수정 파일명은 확인할 수 없다.

R4는 해시가 고정된 이전 릴리스와 R7 설치기로 사진의 두 해시를 재현해 허용 목록에
추가하고, 기존 NFS 도구 4파일을 동일 반입/검증/커밋 범위에 포함한다. 적용 전에
모든 코드 해시·관계없는 추적/스테이징 변경·미확인 staged 바이트를 보고서로 남긴다.
임의 현장 수정과 데이터/cache 불일치는 계속 차단한다.

서빙 265파일은 현재 선택 로컬 MAIN generation 43과 같은 바이트이며, R2의 서빙
동작이나 워크플로우를 바꾸지 않는다. 전체 ZIP은 코드 286파일과 manifest다.
기존 R2/R3/R7 및 완료된 기록을 보존하며, 현장 반입에는 R4 ZIP/APPLY 쌍을 사용한다.

- [현장 실행·진단·원복 안내](GUIDE_UTF8.txt)
- [코드 ZIP](GENOS_INVESTIGATION_CONTROL_20261007_R4.zip)
- [전체 실행 TXT](GENOS_INVESTIGATION_CONTROL_20261007_R4_APPLY.txt)
- [워크플로우 전체 TXT](GENOS_INVESTIGATION_CONTROL_20261007_R4_WORKFLOW_PASTE_ALL.txt)
- [반입 파일·해시·재현 근거](HANDOFF.json)
- [로컬 검사 결과](DELIVERY_TESTS.log)
- [검증 영수증과 압축 로그 해시](DELIVERY_VALIDATION.json)

실제 R2/R7 실행 TXT로 사진과 같은 중단 원인을 재현했으며 적용·재실행·원복,
코드/ZIP/cache 변조 차단, 미확인 staged 변경 보존, 같은 checkout의 gate 및
로컬 bare remote push 검사까지 14개가 통과했다. 원래 합성 setup의 실패 사유는
TEST_ITERATIONS.json에 남겼다. 종료한 합성 checkout/DB는 진단 로그를 무손실 압축한
뒤 정리했으며 실제 운영 데이터는 수정하지 않았다.

현장 R4 적용·generation 검증·push·코드서빙 리비전 배포·내부 모델 질의는 미확인이다.
이 작업에서는 메일을 발송하지 않았다.
