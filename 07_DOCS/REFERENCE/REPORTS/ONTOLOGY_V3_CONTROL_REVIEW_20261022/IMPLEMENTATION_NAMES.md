# 구현 단위 문서 안내

[전체 목차](../../ARCHITECTURE/ONTOLOGY_V3.md) · [DB 설계](DATABASE_ARCHITECTURE.md) · [현재 코드 검토](REVIEW.md)

**기업지식 통제 시스템의 구현 책임을 M01~M12로 나눈 설계입니다.** 현재 코드를 유지·분리·확장할 위치와 목표 파일·함수·입출력을 연결합니다. 신규 목표 모듈은 아직 구현하지 않았습니다.

<a id="v3-23"></a>

## 상세 문서

| 문서 | 내용 |
|---|---|
| [구현 단위 이름과 파일 구조](implementation/MODULES.md) | M01~M12 이름표, 기존 이름 변경 범위, 목표 파일 트리 |
| [데이터 객체와 함수 계약](implementation/CONTRACTS.md) | KnowledgeAssertion·KnowledgeUse 등 객체, 파일별 호출 시그니처와 소비자 |
| [호출 연결과 저장 책임](implementation/INTEGRATION.md) | 기존 CLI/API·RAG 연결, 저장 정본과 동기화, 변경 전후 목표 |
| [구현 이행과 실패 처리](implementation/MIGRATION.md) | 적용 순서, 호환·복구·검증과 완료 범위 |

전체 패키지는 기존 lawrag.legal_knowledge를 확장합니다. 여기서 서비스는 Python 애플리케이션 클래스의 책임이며 별도 서버를 의미하지 않습니다. 숏컷의 기록·회수 기반과 기존 basis 관계 원장을 재사용합니다.

기준일은 2026-10-22입니다. [코드 근거](EVIDENCE.json)는 당시 관측으로 보존하며 현재 구현 여부와 구분합니다. DB 테이블·조회·트랜잭션은 [DB 설계 목차](DATABASE_ARCHITECTURE.md)에서 이어집니다.
