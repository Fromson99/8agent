"""Add the isolated runner-repair repeat without rewriting primary measurements."""
import json,hashlib
from pathlib import Path
import report
ROOT=report.ROOT;ADR=report.ADR;ART=report.ART
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.relative_to(ROOT))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
    report.main()
    retry=read(ART/'run-002/results.json')['cases']['cm-038']['relations-v3']
    trace=read(ART/'run-002/cm-038/relations-v3/trace.json')
    judged=read(ART/'run-002/judged-results.json')
    verdict=judged['cases']['cm-038']['by_arm']['relations-v3']
    note={'case_id':'cm-038','arm':'relations-v3','run_id':'run-002',
        'reason':'Experiment runner omitted pipeline_sha256 in run-001. Add the required binding only; same product code, source, model, prompt and budget.',
        'correct':verdict['correct'],'judge_reason':verdict['reason'],'error':retry['error'],
        'seconds':retry['seconds'],'physical_calls':retry['physical_calls'],'usage':retry['usage'],
        'stages':{k:len(v) for k,v in retry.get('stages',{}).items()},'relation_notices':len(trace.get('notices',[])),
        'relation_families':dict(__import__('collections').Counter(n['family'] for n in trace.get('notices',[]))),
        'relation_assessments':len(trace.get('relation_assessments',[])),
        'semantic_errors':trace.get('errors',[]),'coverage':trace.get('coverage'),
        'limitations':retry.get('limitations',[]),'claims':len(retry.get('result',{}).get('answer',{}).get('claims',[])),
        'gate':retry.get('control',{}).get('gate')}
    write(ART/'run-002/diagnostics.json',note)
    m=read(ADR/'실험/manifest.json');m['runs'][1].update(status='complete',sha256=sha(ART/'run-002/results.json'))
    m['retrieval_accounting']['stage_ledger'].update(artifact_path=rel(ART/'retrieval-stage-ledger-combined.json'),sha256=sha(ART/'retrieval-stage-ledger-combined.json'))
    m['results']['runner_repair_repeat']={k:v for k,v in note.items() if k not in ('coverage','semantic_errors','usage','error')}
    m['results']['runner_repair_repeat'].update(diagnostics_path=rel(ART/'run-002/diagnostics.json'),diagnostics_sha256=sha(ART/'run-002/diagnostics.json'),execution_error=retry['error'] is not None)
    primary=read(ART/'run-001/results.json');pj=read(ART/'run-001/judged-results.json')
    selected={'baseline':{c:r['baseline'] for c,r in primary['cases'].items()},
        'relations-v3':{c:(retry if c=='cm-038' else r['relations-v3']) for c,r in primary['cases'].items()}}
    valid={a:{'correct':sum((verdict['correct'] if a=='relations-v3' and c=='cm-038' else pj['cases'][c]['by_arm'][a]['correct']) for c in selected[a]),
        'total':3,'result_origins':{c:('run-002' if a=='relations-v3' and c=='cm-038' else 'run-001') for c in selected[a]},
        'seconds_by_case':{c:r['seconds'] for c,r in selected[a].items()},
        'calls':sum(r['physical_calls'] for r in selected[a].values()),
        'input_tokens':sum(u.get('input_tokens') or 0 for r in selected[a].values() for u in r['usage']),
        'output_tokens':sum(u.get('output_tokens') or 0 for r in selected[a].values() for u in r['usage'])} for a in selected}
    m['results']['observations_after_runner_repair']={'by_arm':valid,'note':'Three distinct CM questions; replace only the invalid runner case with its explicit repeat for this descriptive summary. Primary paired results remain separately preserved; no independent holdout inference.'}
    write(ART/'observations-after-runner-repair.json',m['results']['observations_after_runner_repair'])
    q=ADR/'실험/질문-003-cm-038.md'
    paths=sorted((ART/'run-002').rglob('*.json'))+[ART/'retrieval-stage-ledger-combined.json']
    q.write_text(q.read_text()+'\n## 9. 평가 실행기 수정 후 run-002\n\n원래 v3 실행의 누락은 제품 기능 오답과 구분한다. 파이프라인 해시 binding만 보완했으며 해당 문항만 재실행했다. baseline은 run-001의 동일 원본을 채점에 재사용했다. 나머지 두 문항은 재실행하지 않았다.\n\n'+report.envelope(paths))
    m['questions'][2]['sha256']=sha(q)
    # Keep detailed errors in hash-bound raw JSON, not unreadable exception chains in the main summary.
    paragraph=f"평가 실행기 수정 후 서로 다른 CM 3문항 관측값은 v2 {valid['baseline']['correct']}/3, v3 {valid['relations-v3']['correct']}/3이다. CM038/v3만 run-002를 사용한 기술적 요약이며 최초 paired 결과를 소급 변경하지 않았다. 재측정 시간 {retry['seconds']:.2f}초, 호출 {retry['physical_calls']}회, READ 조문 {note['stages'].get('read',0)}개, 관계 안내 {note['relation_notices']}개, 관계 평가 {note['relation_assessments']}개."
    text=(ADR/'README.md').read_text();text=text.replace('## 1. 결정 요약\n\n','## 1. 결정 요약\n\n'+paragraph+'\n\n')
    text=text.replace('## 7. 사례별 오류 분석\n\n','## 7. 사례별 오류 분석\n\n최초 CM038/v3의 `pipeline_sha256` KeyError는 실험 실행기 누락이다. 이를 제품 성능 실패로 귀속하지 않으며 위 재측정으로 구분했다.\n\n')
    text+='\n## 추가 확인: 실행기 수정 후 CM038/v3\n\n'+paragraph+'\n\n[재측정 상세](artifacts/run-002/diagnostics.json) · [출처를 구분한 3문항 요약](artifacts/observations-after-runner-repair.json)\n'
    (ADR/'README.md').write_text(text)
    p=ADR/'실험/README.md';p.write_text(p.read_text()+'\n'+paragraph+'\n')
    write(ADR/'실험/manifest.json',m)
    am=read(ART/'manifest.json');paths=[ROOT/f['path'] for f in am['files']]
    paths += [p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json']
    paths += list((ROOT/'06_TOOLS/EXPERIMENTS/adr_0485').glob('*.py'))
    c=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0485/tools-v3-qwen-retry';paths.append(c/'candidate.json')
    paths += [ROOT/f['frozen_path'] for f in read(c/'candidate.json')['revisions'][0]['files']]
    am['files']=[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code/input or exact raw result including isolated runner repair repeat','contains_raw_prompts_and_outputs':p.suffix=='.json' and ('run-001' in str(p) or 'run-002' in str(p))} for p in sorted(set(paths))]
    write(ART/'manifest.json',am)
    print(paragraph)
if __name__=='__main__':main()
