"""Generate exact case record for recipe-loop ADRs, no model calls."""
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2];adr=root/sys.argv[1];a=adr/'artifacts'
parts=['# annex-loop\n\n## 1. 실행 메타\n\nrun-001; Anthropic Haiku; exact requests/responses. Images remain in linked binary payload.\n',
       '## 2. 사용자 질문 원문\n\n다시 진행해봐 — 구조화 틀 자동 조립과 VLM 보정 루프 실험.\n',
       '## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n별표 설명 제목이14개 번호항목의 조상이어야 한다. 모든 번호1..14와 원문 좌표를 보존한다. 기존 사례를 본 에이전트 기준, 사람 calibration 없음.\n',
       '## 4. 제품 입력을 구성한 원값\n\n동일 법률 별표 이미지, 전체 파싱 블록, 관측된 기존 마커 계열, 현재 조합식, 실제 구조 트리.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nRAG 해당 없음. 원문 한 페이지 전체 제공.\n',
       '## 5. 제품 모델 호출 — run·arm별 실제 원문\n']
for p in sorted(a.glob('call-*.request.json')):
    r=json.loads(p.read_text());resp=p.with_name(p.name.replace('.request.json','.response.json'))
    parts += [f'### {p.stem}\n\n[Exact image+text payload](../artifacts/{p.name})\n',
              '#### System\n\n'+r['system']+'\n',
              '#### User\n\n```json\n'+r['messages'][0]['content'][-1]['text']+'\n```\n',
              '#### Schema/tool\n\n```json\n'+json.dumps(r['tools'],ensure_ascii=False,indent=2)+'\n```\n',
              '#### Provider response\n\n```json\n'+(resp.read_text() if resp.exists() else 'No response received')+'\n```\n']
parts += ['## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n모든 조합 생성·VLM 검수·수정 호출이 위에 원문으로 보존되어 있다. 트리는 코드 엔진이 재생성한다.\n',
          '## 7. 채점 호출과 반복 판정\n\n추가 LLM judge 없음. 사전 정의한14개항목 재고/제목 조상 관계를 코드와 에이전트가 점검. 검수 VLM은 제품 후보를 바꾸는 역할이지 독립 judge가 아니다.\n',
          '## 8. 사례 최종 판정\n\n[전체 실행 결과](../artifacts/results.json) 및 [판정](../artifacts/assessment.json)을 참조한다.\n']
(adr/'실험/질문-001-annex-loop.md').write_text('\n'.join(parts))
