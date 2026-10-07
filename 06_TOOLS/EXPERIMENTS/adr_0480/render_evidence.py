"""Mechanically render exact recorded I/O and hash inventory; no rerun or model."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0480-cm003-reviewed-source-relations'
def main():
    fixture=json.loads((ADR/'fixture.json').read_text())
    q='# 질문 001 — cm-003\n\n## 1. 실행 메타\n\n2026-09-20 / run-001 / baseline + explicit-link. 원본 exact, 무모델·무네트워크. 실험 시작source와 수동관계는 고정이며 자율 탐색 실험이 아니다.\n\n## 2. 사용자 질문 원문\n\n'+fixture['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n법률 정답 채점 안 함. 사후 결정 조문 좌표 원장만 결합. 수동으로 만든 CM003 관계라 인샘플이며 blind 검증이 아니다. 기준답변은 실행기가 읽지 않음.\n\n## 4. 제품 입력을 구성한 원값\n'
    paths=[ADR/'artifacts/frozen-design.json',ADR/'artifacts/run-001/result.json',ADR/'artifacts/retrieval-stage-ledger.json']
    for arm in ('baseline','explicit-link'):
        paths += [ADR/'artifacts/run-001'/arm/name for name in ('input.json','lookup.json','reads.json','evidence.json','observations.json')]
    q+='\n### 회수·탈락 단계 원장 — run·arm별\n\n단계 전체 원장은 아래 retrieval-stage-ledger.json 원문에 포함한다.\n'
    for p in paths:
        q+='\n### '+str(p.relative_to(ADR))+'\n\n```json\n'+p.read_text().rstrip()+'\n```\n'
    q+='\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\n없음. system/user/schema/provider request/response는 모두 해당 없음. 모델 제시0, 토큰0, 모델비용0. 아래 원문 READ 로그는 모델 응답이 아니다.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n[] — 전부 미실행. proposal의 producer simulated-not-qwen은 합성 계약 입력이며 실제 LLM 실행 아님.\n\n## 7. 채점 호출과 반복 판정\n\njudge0, 사람 승인0. 사전 조건에 대한 deterministic assertion 검사. 법률 정확도 판정은 하지 않았다.\n\n## 8. 사례 최종 판정\n\n1개 관계의 정확한 subtree 회수 통과. 빈 relation release는 관련 원문0블록, fixture relation release는9블록508자3페이지. 신규18+기존47=65 계약 통과. 사전 SQL placeholder 오류는rev002에서 수정, 최초 실패 기록보존. 자동 탐색·자동 관계 생성·사람 인증·운영 게시 미확인.\n'
    (ADR/'실험/질문-001-cm-003.md').write_text(q)
    paths=[p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
    paths+=list((ROOT/'06_TOOLS/EXPERIMENTS/adr_0480').glob('*.py'))
    paths+=[ADR/'PLAN.md',ADR/'fixture.json',ROOT/'05_TESTS/CONTRACTS/test_source_relations_candidate.py',
            ROOT/'07_DOCS/REFERENCE/ARCHITECTURE/SOURCE_RELATION_REVIEW_SCHEMA.md',
            ROOT/'02_BACKEND/lawrag/research/candidates/adr_0480/explicit-link/candidate.json']
    candidate=json.loads(paths[-1].read_text())
    paths += [ROOT/r['frozen_path'] for r in candidate['revisions'][-1]['files']]
    am=json.loads((ADR/'artifacts/manifest.json').read_text())
    am['files']=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                'bytes':p.stat().st_size,'description':'CM003 no-model explicit relation probe artifact',
                'contains_raw_prompts_and_outputs':p.name in ('input.json','lookup.json','reads.json','evidence.json','observations.json')}
                for p in sorted(set(paths))]
    (ADR/'artifacts/manifest.json').write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
    print('Exact question evidence and artifact hashes rendered')

if __name__=='__main__':main()
