"""Render exact ADR0352 run records; no model calls."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0352-law-annex-pdf-vlm'
OUT=ADR/'artifacts'
parts=['# law-annex-001\n\n## 사용자 질문 원문\n\n이거말고 법령으로 해 이놈은 법령이 아니잖아 우리 law에 해당하는놈(거기에 pdf 가 없나? 너가 하나 알아서 바꿔봐\n',
       '## 기준답변 — 채점 전용, 제품에는 미제공\n\n```json\n'+(OUT/'gold.json').read_text()+'\n```\n',
       '## 실행 메타\n\nADR0352/run-001, Anthropic claude-haiku-4-5-20251001, 3 repeats, temperature0, no retries. Binary image is linked in exact request artifact; all text below is verbatim.\n']
for n in range(1,4):
    for arm in ['baseline','vision']:
        prefix=f'repeat-{n}-{arm}'
        request=json.loads((OUT/(prefix+'.request.json')).read_text())
        parts.append(f'## repeat {n} / {arm}\n\nExact full payload: [request](../artifacts/{prefix}.request.json)\n')
        parts.append('### System\n\n'+request['system']+'\n')
        parts.append('### User\n\n```json\n'+request['messages'][0]['content'][-1]['text']+'\n```\n')
        parts.append('### Tools/schema\n\n```json\n'+json.dumps(request['tools'],ensure_ascii=False,indent=2)+'\n```\n')
        parts.append('### Provider response, usage and latency\n\n```json\n'+(OUT/(prefix+'.response.json')).read_text()+'\n```\n')
parts.append('## 중간·채점 호출\n\n없음. 사전 고정한 agent 기준답과 exact tuple set 비교. 사람 교정된 정확도 아님.\n')
parts.append('## 사례 판정\n\n```json\n'+(OUT/'results.json').read_text()+'\n```\n')
(ADR/'실험/질문-001-law-annex-001.md').write_text('\n'.join(parts))
