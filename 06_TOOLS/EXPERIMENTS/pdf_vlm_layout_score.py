"""Offline exact scorer for ADR0351. Never calls a model or feeds gold to product."""
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0351-pdf-vlm-layout-probe'
OUT = ADR / 'artifacts'

def main():
    gold = json.loads((OUT/'gold.json').read_text())['cases']
    scores = []
    for n, (case, expected) in enumerate(gold.items(), 1):
        sections = [f'# {case}\n\n## 실행 메타\n\nADR0351/run-001; backend anthropic; Haiku; exact JSON request/response artifacts.\n',
                    '## 사용자 질문 원문\n\n어어 성능확인해봐\n',
                    '## 기준답변 — 채점 전용, 제품 입력 비공개\n\n```json\n'+json.dumps(expected,ensure_ascii=False,indent=2)+'\n```\n']
        lines = json.loads((OUT/(case+'.json')).read_text())['lines']
        ids = {r['line'] for r in lines}
        for arm in ['baseline','vision']:
            request = json.loads((OUT/f'{case}-{arm}.request.json').read_text())
            raw = json.loads((OUT/f'{case}-{arm}.response.json').read_text())
            tools = [x for x in raw['body'].get('content',[]) if x.get('type')=='tool_use' and x.get('name')=='record_layout']
            parsed = tools[0]['input'] if len(tools)==1 else {}
            valid = False
            try:
                import jsonschema
                jsonschema.validate(parsed,request['tools'][0]['input_schema'])
                valid = (raw['http_status']==200 and raw['body'].get('stop_reason')=='tool_use'
                         and all(x['line'] in ids and (x['parent_line']==0 or x['parent_line'] in ids) for x in parsed['headings'])
                         and len({x['line'] for x in parsed['headings']})==len(parsed['headings']))
            except (ValueError,KeyError,jsonschema.ValidationError):
                pass
            actual = {(x['line'],x['parent_line']) for x in parsed.get('headings',[])}
            desired = {(x['line'],x['parent_line']) for x in expected['headings']}
            row = {'case':case,'arm':arm,'valid':valid,
                   'exact':valid and actual==desired and parsed['has_table']==expected['has_table'] and parsed['table_columns']==expected['table_columns'],
                   'tp':len(actual&desired),'fp':len(actual-desired),'fn':len(desired-actual),
                   'extra_edges':sorted(actual-desired),'missing_edges':sorted(desired-actual),
                   'table_correct':parsed.get('has_table')==expected['has_table'] and parsed.get('table_columns')==expected['table_columns'],
                   'seconds':raw['seconds'],'usage':raw['body'].get('usage',{}),'output':parsed}
            scores.append(row)
            # Preserve text verbatim; binary image remains in exact request artifact.
            text_input=request['messages'][0]['content'][-1]['text']
            sections += [f'## {arm}: 제품 입력·출력 원값\n\n정확한 이미지 포함 payload: `../artifacts/{case}-{arm}.request.json`.\n',
                         '### System\n\n'+request['system']+'\n', '### User\n\n```json\n'+text_input+'\n```\n',
                         '### Schema\n\n```json\n'+json.dumps(request['tools'],ensure_ascii=False,indent=2)+'\n```\n',
                         '### Provider 원응답 및 지연\n\n```json\n'+json.dumps(raw,ensure_ascii=False,indent=2)+'\n```\n',
                         '### 사례 판정\n\n```json\n'+json.dumps(row,ensure_ascii=False,indent=2)+'\n```\n']
        sections += ['## 중간·채점 호출\n\n없음. 고정된 기준답과 집합 일치로 채점. 기준답은 에이전트의 원본 이미지 사전 검토로 작성했으며 사람 교정은 받지 않음.\n']
        (ADR/'실험'/f'질문-{n:03d}-{case}.md').write_text('\n'.join(sections))
    summary = {}
    for arm in ['baseline','vision']:
        rows=[r for r in scores if r['arm']==arm]
        tp=sum(r['tp'] for r in rows); fp=sum(r['fp'] for r in rows); fn=sum(r['fn'] for r in rows)
        times=sorted(r['seconds'] for r in rows)
        summary[arm]={'correct':sum(r['exact'] for r in rows),'total':len(rows),'edge_tp':tp,'edge_fp':fp,'edge_fn':fn,
                      'edge_f1':2*tp/(2*tp+fp+fn),'table_correct':sum(r['table_correct'] for r in rows),
                      'p50_seconds':statistics.median(times),'p95_seconds':times[math.ceil(.95*len(times))-1],
                      'input_tokens':sum(r['usage'].get('input_tokens',0) for r in rows),
                      'output_tokens':sum(r['usage'].get('output_tokens',0) for r in rows)}
    paired={'vision_only':0,'baseline_only':0,'both_correct':0,'both_wrong':0}
    for case in gold:
        a,b=[next(r['exact'] for r in scores if r['case']==case and r['arm']==arm) for arm in ['baseline','vision']]
        paired['both_correct' if a and b else 'baseline_only' if a else 'vision_only' if b else 'both_wrong']+=1
    passed=summary['vision']['correct']>=3 and paired['vision_only']>paired['baseline_only'] and paired['baseline_only']==0 and summary['vision']['p95_seconds']<=60
    report={'status':'complete','by_arm':summary,'paired':paired,'success_criteria_met':passed,'scores':scores,
            'limitations':['4 purposive pages from one public PDF; no generalization','Agent-annotated gold not human calibrated',
                           'Page layout subtask, not automatic recipe or full structure accuracy','One call per arm per page; no stability estimate',
                           'No cell-content extraction, cross-page tables or scanned PDF tested'],
            'main_wiring':'unchanged'}
    with (OUT/'results.json').open('x') as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='scores'},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
