"""Render completed measurements and all exact receipts; never call a model."""
import hashlib,json,sqlite3,statistics
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0487-qwen-v3-paging-cm3-retest'
ART=ADR/'artifacts';RUN=ART/'run-001';ARMS=['baseline','relations-v3']
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.relative_to(ROOT))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def envelope(paths):return '```json\n'+json.dumps({rel(p):read(p) for p in paths},ensure_ascii=False,indent=2)+'\n```\n'
def main():
    results=read(RUN/'results.json');metrics=read(RUN/'metrics.json');judged=read(RUN/'judged-results.json')
    ledger=read(ART/'retrieval-stage-ledger-run-001.json');product=read(ADR/'product-cases.json');gold=read(ADR/'gold-cases.json')
    m=read(ADR/'실험/manifest.json');gold_by={c['case_id']:c for c in gold['cases']}
    details={};pairs=Counter()
    for cid,rows in results['cases'].items():
        correct=[judged['cases'][cid]['by_arm'][a]['correct'] for a in ARMS]
        pairs['both_correct' if all(correct) else 'both_wrong' if not any(correct) else 'baseline_only' if correct[0] else 'candidate_only']+=1
        details[cid]={}
        for arm,row in rows.items():
            trace=read(RUN/cid/arm/'trace.json')
            details[cid][arm]={'seconds':row['seconds'],'calls':row['physical_calls'],
                'cost_usd':sum(u.get('cost_usd') or 0 for u in row['usage']),
                'stages':{s:len(v) for s,v in row.get('stages',{}).items()},
                'claims':len(row.get('result',{}).get('answer',{}).get('claims',[])),
                'gate':row.get('control',{}).get('gate'),'semantic_errors':trace.get('errors',[]),
                'coverage':trace.get('coverage'),'relation_notices':len(trace.get('notices',[])),
                'relation_families':dict(Counter(n.get('family') for n in trace.get('notices',[]))),
                'relation_assessments':len(trace.get('relation_assessments',[])),
                'execution_error':row.get('error'),'limitations':row.get('limitations',[])}
    diagnostic={'by_case':details,'paired_outcomes':dict(pairs),'result_sha256':sha(RUN/'results.json'),
        'model':'qwen/qwen3.5-122b-a10b','main_unchanged':True,
        'cost_usd':sum(x['cost_usd'] for d in details.values() for x in d.values())}
    write(RUN/'diagnostics.json',diagnostic)
    gen=ROOT/product['generation'];scope=product['public_scope_document_ids']
    with sqlite3.connect('file:'+str(gen/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
        corpus=db.execute('SELECT count(*) FROM source WHERE document_id IN ('+','.join('?' for _ in scope)+')',scope).fetchone()[0]
    m['runs'][0].update(status='complete',sha256=sha(RUN/'results.json'))
    la={x['arm_id']:x for x in ledger['runs'][0]['arms']}
    counts={a:[c['stages'][-1]['after_count'] for c in la[a]['cases']] for a in ARMS}
    r=m['retrieval_accounting'];r.update(corpus_total=corpus,before_filter={a:corpus for a in ARMS},
        after_filter={a:sum(counts[a]) for a in ARMS},presented_total={a:sum(counts[a]) for a in ARMS},
        presented_mean={a:round(statistics.mean(counts[a]),4) for a in ARMS},
        presented_p50={a:statistics.median(counts[a]) for a in ARMS},presented_p95={a:max(counts[a]) for a in ARMS},
        golden_recall={a:metrics['by_arm'][a]['answer_gold_recall'] for a in ARMS},
        selectivity={a:statistics.mean(counts[a])/corpus for a in ARMS})
    r['stage_ledger'].update(summary_run_id='run-001',artifact_path=rel(ART/'retrieval-stage-ledger-run-001.json'),sha256=sha(ART/'retrieval-stage-ledger-run-001.json'))
    m['results']={'status':'complete','by_arm':metrics['by_arm'],
        'comparisons':[{'arms':ARMS,'metric':'stored_reference_agreement','delta':metrics['paired_delta'],**dict(pairs)}],
        'judge_disagreements':None,'judge_note':metrics['judge_note'],'criteria':metrics['criteria'],
        'usage':{'product_calls':sum(metrics['by_arm'][a]['calls'] for a in ARMS),
            'product':{k:sum(metrics['by_arm'][a]['usage'][k] for a in ARMS) for k in ('input_tokens','output_tokens','total_tokens')},
            'offline_evaluator':metrics['judge_usage'],'product_cost_usd':diagnostic['cost_usd']},
        'latency':{a:{'p50_seconds':metrics['by_arm'][a]['latency_p50_seconds'],'p95_seconds':metrics['by_arm'][a]['latency_p95_seconds']} for a in ARMS},
        'error_taxonomy':sorted({x for a in ARMS for x in metrics['by_arm'][a]['failure_types']}),'main_wiring':'unchanged'}
    rows=[]
    for i,case in enumerate(product['cases'],1):
        cid=case['case_id'];lines=[f'# 질문 {i:03d} — {cid}',
            '## 1. 실행 메타','run-001; Qwen qwen/qwen3.5-122b-a10b; 각 arm 1회, 원시 기록 exact.',
            '## 2. 사용자 질문 원문',case['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',gold_by[cid]['reference_answer'],
            '## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별',
            '| arm | stage | before | added | discarded | after | gold before/add/loss/after | recall |',
            '|---|---|---:|---:|---:|---:|---|---:|']
        for arm in ARMS:
            lc=next(c for c in la[arm]['cases'] if c['case_id']==cid)
            for s in lc['stages']:lines.append(f"| {arm} | {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_before']}/{s['gold_added']}/{s['gold_discarded']}/{s['gold_after']} | {s['golden_recall']} |")
        lines+=['\n정확한 후보 집합·탈락 이유·gold 좌표는 다음 원장 원문에 보존한다.',envelope([ART/'retrieval-stage-ledger-run-001.json']),
                '## 5. 제품 모델 호출 — run·arm별 실제 원문']
        for arm in ARMS:
            files=sorted((RUN/cid/arm).rglob('*.json'))
            lines+=['### '+arm,envelope(files)]
        lines+=['## 6. 중간 LLM 호출 — router/compiler/verifier/repair','위 호출 기록에는 investigate 및 실제 발생한 compose/review/repair를 모두 포함한다. 발생하지 않은 단계는 실행 성공으로 세지 않는다.',
            '## 7. 채점 호출과 반복 판정',envelope(sorted((RUN/'judge'/cid).rglob('*.json'))),
            '## 8. 사례 최종 판정',envelope([RUN/'judged-results.json',RUN/'diagnostics.json'])]
        path=ADR/'실험'/f'질문-{i:03d}-{cid}.md';path.write_text('\n\n'.join(lines)+'\n')
        m['questions'][i-1]['sha256']=sha(path)
        for arm in ARMS:
            d=details[cid][arm];v=judged['cases'][cid]['by_arm'][arm]
            rows.append(f"| {cid} | {arm} | {'정답' if v['correct'] else '오답'} | {d['claims']} | {d['calls']} | {d['seconds']:.2f} | {d['stages']['read']} | {d['relation_notices']} |")
    write(ADR/'실험/manifest.json',m)
    table='| 문항 | arm | 기준답 일치 | 검토된 주장 | 호출 | 전체 시간(초) | READ | 관계 안내 |\n|---|---|---|---:|---:|---:|---:|---:|\n'+'\n'.join(rows)
    front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected').replace('Gemini','Qwen')
    errors=Counter(e['message'] for d in details.values() for v in d.values() for e in v['semantic_errors'])
    sections=[('결정 요약',f"현재 tools-v2 {metrics['by_arm']['baseline']['correct']}/3, tools-v3 {metrics['by_arm']['relations-v3']['correct']}/3. 사전 기준 충족: {metrics['success']}. 소표본 점검이며 MAIN/GENOS는 변경하지 않았다."),
      ('문제와 변경 전 구조','원문 채택·기각·보류 기록, 실제 미리보기와 6종 관계 처리를 추가한 v3를 현재 v2와 비교했다. 양쪽 모두 현재 작업 코드 스냅샷이며 활성 릴리스 품질 측정과는 구분한다.'),
      ('가설과 사전 판정 기준',m['design']['success_criteria']),
      ('실험 설계',m['runs'][0]['selection_rule']+' 각 문항 각 arm 1회. 실행 순서와 익명 채점 A/B 위치를 교대했다. 질문과 공개 145문서 scope만 제품에 제공했으며 정답 조문 선읽기·주입은 없다. 사용자가 실행 전 기본 모델을 Qwen으로 변경했다.'),
      ('데이터·모델·재현성',f"모델은 Qwen FP8, thinking off. source generation `{product['generation']}`. 원문 store는 이전 CM 고정 자료와 동일한 hash이며 현재 관계·본문검색 색인을 사용한다. 최초 무모델 점검의 실행기 세대 불일치는 첫 호출 전에 수정하고 원래 입력을 보존했다. 기준답변과 법령의 현행성은 독립 검증하지 않았다."),
      ('결과',table+'\n\nPaired outcomes: '+json.dumps(dict(pairs),ensure_ascii=False)),
      ('사례별 오류 분석','실제 모델 선택 검증 오류: '+json.dumps(dict(errors),ensure_ascii=False)+'\n\nR1은 전체 자료의 루트다. READ는 문서·원문 후보 핸들이 필요하다. 이 오류로 원문에 도달하지 못한 사례의 관계 성능은 미측정이며 관계 기능 성공/실패로 대신 세지 않는다. 사례별 전송 실패와 deadline은 diagnostics.json 및 원응답에 따로 보존했다.'),
      ('비용·지연·회수 규모',json.dumps(m['results']['usage'],ensure_ascii=False)+'\n\n'+json.dumps(m['results']['latency'],ensure_ascii=False)+f'\n\n공개 scope 조문 source 수 {corpus}. 전체 시간은 초기 자원 로딩도 포함한다. 낮은 시간이 탐색 조기 종료 때문일 수 있으므로 처리 속도 개선으로 해석하지 않는다. 회수 원장의 마지막 단계는 검토를 통과한 최종 답변이며 실제 모델 제시 단계 지표도 별도 기록했다.'),
      ('해석','현재 무유도 질문에서 탐색 첫 단계와 오류 복구가 병목이다. 단위 계약 통과만으로 실모델 탐색 성공을 보장하지 않았다. 탐색에 성공하지 못한 문항은 준용·위임·정의 등 관계의 판단 품질을 평가할 수 없다.'),
      ('한계와 일반화 가능 범위','CM 3개 인샘플, 단회 익명 Qwen 평가이며 judge calibration과 변동성은 미측정이다. 실제 GENOS 실행이 아니다. 괄호 업무 문맥을 별도 Q 구간으로 나누는 기존 공통 동작을 유지했다. 정확도 향상이나 속도 우위를 일반화할 수 없다.'),
      ('운영 결정·롤백 조건','검증 결과를 반영한 탐색 프롬프트·도구 계약 수정은 이 실험에서 하지 않았다. 후속 수정과 재평가는 새 ADR로 분리한다. 활성 MAIN 포인터는 실험 전 hash 그대로다. Qwen 신규 기본값 전환은 별도 ADR-0486에서 완료했다.'),
      ('재현 명령','현재 run-001은 덮어쓰거나 재실행하지 않는다. 재실행은 새 ADR을 선점해 frozen-design.json의 코드·데이터·모델·설정을 사용한다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+rel(ADR)+' --final`\n\n[질문별 전체 입출력](실험/README.md) · [상세 측정](artifacts/run-001/diagnostics.json) · [산출물 해시](artifacts/manifest.json)')]
    (ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0487: 도구 탐색 v2·v3 CM3 Qwen 비교\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(sections,1))+'\n')
    (ADR/'실험/README.md').write_text('# CM3 Qwen 비교\n\n'+table+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']}) — 전체 입력·출력·채점·단계 원장" for q in m['questions'])+'\n')
    am=read(ART/'manifest.json')
    paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json']
    paths+=list((ROOT/'06_TOOLS/EXPERIMENTS/adr_0487').glob('*.py'))
    cand=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0487/paging-v3'
    paths+=[cand/'candidate.json']+[ROOT/f['frozen_path'] for f in read(cand/'candidate.json')['revisions'][0]['files']]
    paths+=[ADR/'PLAN.md',ADR/'product-cases.json',ADR/'gold-cases.json']
    am['files']=[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact measured receipt, frozen input or reproducible research code','contains_raw_prompts_and_outputs':p.suffix=='.json' and 'run-001' in str(p)} for p in sorted(set(paths))]
    write(ART/'manifest.json',am)
    print(table)
if __name__=='__main__':main()
