# Agent Legal 최종 설계 산출물

- [최종 통합 설계서](FINAL_DESIGN.md): 두 하네스, 반복 판단, 내부 탐색, 상태·근거·주장 계약, 파이프라인 재진입, 구현 지도, 검증·도입.
- [핵심 설계 필요성 표](DESIGN_RATIONALE.md): 20개 결정의 실제 문제·근거 수준·대응·검증 연결.
- [자체 검토](SELF_REVIEW.md): 수치·계약·실행 연결 보완과 아직 미검증인 범위.
- [결정 목록](decisions.json), [원자료 해시](sources.json), [제어 스키마](control.schema.json), [모의 메시지](control-examples.json).
- [제품 완료 시나리오](acceptance-scenarios.json): 20개 계획, 제품 실행 검증 전.
- [문서 검증 스크립트](validate_final_design.py), [검증 결과](validation.json).

상태: 최종 통합 설계 v1.0. 제품 코드·활성 릴리스·진행 ADR 변경 없음. JSON 형태·문서 정합성 검사는 법률 품질 인증이 아니다.

저장소 루트에서 검증: .venv/bin/python -B 07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/FINAL/validate_final_design.py
