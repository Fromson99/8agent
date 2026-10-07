"""Publish the verified cutover state separately from the immutable experiment."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0655-shortcut-serving-closure';ART=A/'artifacts'
def read(p):return json.loads(p.read_text())
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');result=read(ART/'run-001/result.json');smoke=read(ART/'main-smoke.json');install=read(ART/'working-install-receipt.json')
assert result['strict_success'] and smoke['status']=='passed' and pointer==smoke['pointer']
release=R/pointer['manifest_path'];manifest=read(release)
rows=[]
for case in read(ART/'design/inputs.json'):
 for r in read(ART/'run-001'/case['case_id']/'integrated/result.json'):
  rows.append(f"| {case['case_id']} | {r['turn']} | {r['seconds']:.2f}초 | {r['provider_calls']}회 | 통과 |")
receipts=[]
for p in (R/'01_DATA/ACTIVE/local/receipts').glob('*.json'):
 if pointer['release_id'] in p.read_text():receipts.append(p)
report=A/'MAIN_RESULT.md'
text=f'''# shortcut · legal_wiki v6 로컬 MAIN 반영 결과

로컬 제품 MAIN을 **{pointer['release_id']}**, 포인터 **generation {pointer['generation']}**으로 전환했다. 기본 구현은 `legal-agent-unified-v6`이다. 검증된 후보의 코드와 서빙 파일 해시를 결속한 승격이며, 품질 게이트 우회를 쓰지 않았다. 원문 데이터 세대는 바꾸지 않았다.

## 실패 기점과 수정

1. 최초 근거 선별: 첫 선택과 추가 누락 검토에 같은 빈 선택 지침이 섞여 있었다. 둘을 구분하고 첫 선택이 비었을 때 현재 후보 원문의 제한된 구간을 제공한다. 기대·실제 선택과 `EMPTY_INITIAL_SELECTION` 이유를 호출 기록에 남긴다. 관련 원문을 강제로 정답으로 채택하지 않는다.
2. 실제 멀티턴 출처 오류: 모델이 `current_facts`를 법령 출처 ID처럼 인용했다. 실제 제공된 원문 ID만 선택하도록 출력 계약을 제한하고 잘못된 claim·ID·인용의 검증 오류를 구체화했다. [ADR-0651](../ADR-0651-shortcut-evidence-id-contract/README.md).
3. 분리 평가에서 추가 발견: 정정은 저장됐지만 ASSESS가 과거 목적 요약과 사실만 받아 새 판단 범위를 놓쳤다. COMPOSE는 그 과도한 claim을 그대로 복사하는 계약 때문에 복구하지 못했다. 금지 대상 제외를 전체 영업 허용으로 확대해 [ADR-0652](../ADR-0652-shortcut-main-separated-validation/README.md)는 **8/9로 기각**했다. ASSESS에 현재 요청 원문을 전달하고 제한된 결론·미확인 사항을 보존하도록 수정했다. [ADR-0653](../ADR-0653-shortcut-current-request-boundary/README.md)의 같은 실패 사례는 **기준 1/2 → 후보 2/2**, 정정 요청은 **28.13초·4호출**로 통과했다.

실패 원본을 지우거나 채점 기준을 낮추지 않았다. ADR-0654는 수정에 쓰지 않은 조문·시나리오로 다시 평가했다.

## 실제 모델 검증

Qwen3.8 27B, OpenRouter Parasail FP8, reasoning none, fallback 없음. 공개 원문과 모의 사건만 사용했다. 상법 표현지배인, 개인정보 수집 근거, 정보공개 부분 공개의 **9개 후보 응답 모두 원문 대조 2회 채점에 통과**했다. 대조군도 9개를 새로 실행했다. 대조군은 직전 완료 v6를 명시적으로 선택하고 후보는 기본 설정으로 선택한다. 과거 활성 MAIN과의 법률 품질 우열 비교는 아니다.

| 후보 사례 | 턴 | 전체 요청 시간 | 모델 호출 | 원문 채점 |
| --- | ---: | ---: | ---: | --- |
{chr(10).join(rows)}

시간에는 독립 시나리오의 동시 실행에 따른 대기가 포함된다. 사용자 정정·재정정·미확인 상태 전환, 같은 사건 연결, 새 세션에서 명시적 사건 연결을 실제 모델로 확인했다. 동일 질문의 새 사건 재사용은 탐색 선택 모델 없이 저장된 절차를 실행하고 ASSESS·COMPOSE만 2회 호출한다. 변경된 사실은 새 판단이 필요하므로 일반적으로 4회다. 답변 자체를 정답 캐시로 복사하지 않는다.

계약·회귀·승격 검사 **103개 통과**. 최초 빈 선택 회복, 조건 변경 시 재조사, 원문·후보 메뉴 변경 시 절차 재사용 거부, 저장·정정·권한·복구·legal_wiki 구성 계약을 포함한다. [전체 측정과 원본](README.md), [결과 JSON](artifacts/run-001/result.json), [계약 검사](artifacts/contracts.txt).

## 실제 연결과 저장

`service.application()` → 활성 릴리스 → 기존 Pipeline → v6 shortcut ingress → 사건·발언·정정·판단·도구 기록 → 기존 action-memory / unified-memory CLI를 통한 legal_wiki 구성·검토·조회로 연결했다. DB가 정본이고 Markdown은 투영이다. 법률 검증과 사용자 확인, 저장 여부를 분리하며 미검증 주장은 확정 법률 판단으로 승격하지 않는다.

선택된 shortcut 저장 경로는 기본 `90_RUNTIME/semantic/case-memory/cases-v4.sqlite`이며, `SHORTCUT_CURRENT.json`이 있으면 그 검증된 포인터를 따른다. 운영 경로에 기존 v3 DB가 없어 이행할 사건 기록은 없었다. 실험 사건 DB는 운영 DB로 복사하지 않았다. 야간 구성은 기존 CLI에 연결했으며 별도 예약 작업을 신규 설치한 것은 아니다.

기존 `06_TOOLS/pipeline.py action-memory`의 `--mode shortcut-v4`와 `unified-memory`의 이행·검증·백업·복구·wiki 명령을 유지한다. 같은 사용자·팀의 세션 연결에는 신뢰된 인증 주체와 명시적인 investigation ID가 필요하다. 실제 모델 검증은 인증 주체를 주입해 수행했다. 로컬 `.env`에는 서명 키가 설정되어 있지 않아, 외부 호출자가 사용자·팀을 주장하는 요청은 거부된다. 운영의 사용자별 멀티턴 연결은 기존 서명 어댑터를 설정해야 하며 인증을 우회하지 않았다.

## 적용·기동 확인

- 작업 코드: 검증된 변경 {install['count']}개를 기존 파일 백업 후 적용. 다른 작업 변경은 보존.
- 릴리스: 사전에 고정한 서빙 242개 파일과 원문 해시 결속. `deployment_basis={pointer.get('deployment_basis')}`.
- 실제 `service.application()`에서 `/health`, 검색, 모델 없는 요청의 durable intake와 사건 ID 생성 확인. 익명 사건 조회 거부 확인. [서비스 확인](artifacts/main-smoke.json).
- 이 확인은 실제 활성 릴리스를 읽는 로컬 서비스 진입 검사다. 상주 서버를 새로 띄우거나 GENOS 리비전을 배포하지 않았다. Git `main` 병합도 별도다.
- 원문 세대: `term-source-1acfbe06921527e74a0b`, SHA-256 `422cfa15b9dba609f3c6105e3d5d3c7dbdb27e90a09469d57ca6bc602b4d9c72` 유지.
- 법률 전문가 인증과 GENOS 현장 성능은 미확인이다. 소규모 분리 평가의 통과이며 `quality_certified=false`를 유지한다.

승격 정본: [릴리스]({release.relative_to(R)}) 대신 저장소의 `{release.relative_to(R)}`와 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`을 확인한다. [작업 적용 영수증](artifacts/working-install-receipt.json), [승격 입력](artifacts/main-authorization.json), [최종 ADR 검사](artifacts/final-validation.txt).

## 복구

WSL 저장소 루트에서 아래 순서로 실행한다. 활성 포인터는 직전 릴리스로 되돌리고 generation 이력은 이어 간다. 두 번째 명령은 이번 작업으로 바꾼 파일만 복원하며 추가 편집이 있으면 중단한다. 원문 세대와 새 shortcut 기록 DB는 삭제하지 않는다.

```bash
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py --root /home/jin/8-AGENT rollback --confirm-main
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0655/rollback_working.py --confirm-working-rollback
```

전체 실험 그래프에는 과거 ADR의 중복·누락 등 기존 오류가 남아 있다. 이번 ADR-0654 자체는 `validate --final`을 통과했고 새 계보에 관한 graph 오류는 없다. 과거 완료 기록을 임의 수정하지 않았다.
'''
# Store absolute targets for repository-wide artifacts so every link resolves.
text=text.replace(f'[{"릴리스"}]({release.relative_to(R)}) 대신 저장소의',f'[릴리스]({release}) 및 저장소의')
text+='\n승격 영수증:\n\n'+''.join(f'- [{p.name}]({p})\n' for p in receipts)
report.write_text(text)
print(report)
