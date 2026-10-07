"""Render the historical comparison with explicit origins; no product calls."""
import json,sqlite3,statistics
from collections import Counter
from pathlib import Path
import report
ROOT=report.ROOT;ADR=report.ADR;ART=report.ART;RUN=ART/'run-001'
read=report.read;write=report.write;sha=report.sha;rel=report.rel

def main():
    report.main()
    m=read(ADR/'실험/manifest.json');results=read(RUN/'results.json');metrics=read(RUN/'metrics.json')
    diagnostics=read(RUN/'diagnostics.json');origins=read(ART/'historical-origins.json')
    wires={};outcomes=[]
    for cid,pair in results['cases'].items():
        row=pair['relations-v3'];trace=read(RUN/cid/'relations-v3/trace.json')
        with sqlite3.connect('file:'+str(RUN/cid/'relations-v3/journal.sqlite')+'?mode=ro',uri=True) as db:
            views=[json.loads(x[0]) for x in db.execute("SELECT DISTINCT v.body_json FROM model_view v JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'")]
            actions=[(json.loads(a),actor,status) for a,actor,status in db.execute('SELECT proposed_json,actor,status FROM action_context')]
            wire_sizes=[len(x[0].encode()) for x in db.execute('SELECT request_json FROM model_attempt')]
        phases=Counter(v['phase'] for v in views)
        info={'successful_views':len(views),'phases':dict(phases),'max_view_chars':max([len(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))) for v in views],default=0),
            'max_gateway_input_bytes':max(wire_sizes,default=0),'views_with_menu':sum(bool(v.get('relation_menu')) for v in views),
            'views_with_continuations':sum(bool(v.get('continuations')) for v in views),
            'tools':dict(Counter(a['tool'] for a,actor,status in actions if actor=='MODEL')),
            'relation_expansions':sum(a['tool']=='inspect_relation' and status=='OK' for a,actor,status in actions),
            'continuation_requests':sum(a['tool']=='view_page' for a,actor,status in actions),
            'semantic_errors':[{'code':e['code'],'message':e['message'][:1600]} for e in trace.get('errors',[])],
            'limitations':row.get('limitations',[]),'controller_seconds':row.get('controller_seconds'),
            'historical_origin':origins[cid]}
        wires[cid]=info;diagnostics['by_case'][cid]['relations-v3'].update(info)
        d=diagnostics['by_case'][cid]['relations-v3'];old=diagnostics['by_case'][cid]['baseline']
        outcomes.append(f"| {cid} | {old['seconds']:.1f} → {d['seconds']:.1f} | {old['stages']['read']} → {d['stages']['read']} | {old['stages']['presented']} → {d['stages']['presented']} | {d['calls']} | {d['claims']} | {'일치' if read(RUN/'judged-results.json')['cases'][cid]['by_arm']['relations-v3']['correct'] else '불일치'} |")
    candidate=metrics['by_arm']['relations-v3'];baseline=metrics['by_arm']['baseline']
    m['results']['usage']={'new_product_calls':candidate['calls'],'new_product':candidate['usage'],
        'historical_product_calls':baseline['calls'],'historical_product':baseline['usage'],
        'offline_evaluator':metrics['judge_usage'],
        'new_product_cost_usd':sum(u.get('cost_usd') or 0 for p in results['cases'].values() for u in p['relations-v3']['usage'])}
    m['results']['historical_origins']=origins
    m['results']['delivery_diagnostics']=wires
    m['results']['comparison_limit']='Historical baseline, not a contemporaneous randomized A/B; no causal latency claim.'
    m['runs'][0]['notes']='Fresh candidate only; baseline imports historical ADR0485 records. Preflight SQL quoting syntax fixed before first model call; failed preflight setup and old seal preserved. No product code modified during experiment.'
    m['results']['criteria']['no_repeated_root_read_failures']=all(sum('is a corpus/folder' in e['message'] for e in w['semantic_errors'])<2 for w in wires.values())
    m['results']['criteria']['no_input_overflow']=all(not any('input exceeds' in x or 'context limit' in x or 'input budget' in x for x in w['limitations']) for w in wires.values())
    success=all(m['results']['criteria'].values())
    m['results']['success']=success
    diagnostics.update(historical_origins=origins,comparison_limit=m['results']['comparison_limit'],new_product_cost_usd=m['results']['usage']['new_product_cost_usd'])
    write(RUN/'diagnostics.json',diagnostics)
    table='| 문항 | 전체 시간: 이전 → 이번(초) | READ 조문 | 실제 제시 조문 | 이번 호출 | 최종 주장 | 저장 기준답 |\n|---|---:|---:|---:|---:|---:|---|\n'+'\n'.join(outcomes)
    errors='\n\n'.join(f"**{cid}**: {json.dumps(w['semantic_errors'],ensure_ascii=False)}\n\n제한: {json.dumps(w['limitations'],ensure_ascii=False)}" for cid,w in wires.items())
    front=(ADR/'README.md').read_text().split('---',2)[1]
    front=front.replace('status: Rejected','status: Proposed' if success else 'status: Rejected')
    sections=[('결정 요약',f"수정 전 v3 {baseline['correct']}/3, 수정 후 v3 {candidate['correct']}/3(저장 기준답·Qwen 단회 채점). 이번 후보 실행 오류 {candidate['errors']}건, 최종 주장 없는 문항 {candidate['zero_claims']}건. 사전 기준 충족 {success}. 인샘플이며 MAIN·GENOS 변경 없음."),
      ('문제와 변경 전 구조','이전 v3는 R1 READ 반복과 입력 view 과대, 감사 요약 최대 64줄 위반으로 실패했다. 사용자 지시로 이미 구현된 입력 분할·이어보기·관계 메뉴·선택 펼치기·현재 검색 페이지만 발췌·READ 대상 안내를 새 격리 snapshot으로 검증했다. 이번 실험 중 제품 코드는 수정하지 않았다.'),
      ('가설과 사전 판정 기준',m['design']['success_criteria']),
      ('실험 설계',m['runs'][0]['selection_rule']+' baseline은 ADR0485 v3의 CM003/018 run001, CM038 run002 원본이다. 재실행하지 않았다. 후보 3건만 새로 실행하고 익명 A/B 위치를 교대해 단회 Qwen 평가했다. 제품은 질문·공개 scope만 받고 gold·정답 조문 선읽기는 받지 않았다.'),
      ('데이터·모델·재현성','Qwen qwen/qwen3.5-122b-a10b, FP8, thinking off, 자동 fallback 없음. 공개 145문서의 기존 store·navigation·fulltext hash를 재검증했다. 코드 89파일 snapshot과 나머지 실행 의존성·설정·출처를 동결했다. 사전 점검의 SQL 문자열 문법 오류는 실호출 전에 수정하고 이전 seal을 보존했다.'),
      ('결과',table+'\n\n'+json.dumps(diagnostics['paired_outcomes'],ensure_ascii=False)),
      ('사례별 오류 분석',errors),
      ('비용·지연·회수 규모',json.dumps(m['results']['usage'],ensure_ascii=False)+'\n\n공개 scope canonical source '+str(m['retrieval_accounting']['corpus_total'])+'개. 전체 시간은 초기 로딩 포함, controller 시간은 별도 기록. 과거 baseline 호출과 비용은 이번 새 실행 비용에 포함하지 않는다. 단계 원장의 마지막은 최종 답변이며 실제 성공 응답에서 제시한 원문 수는 presented 단계에 별도 기록한다. 검색 총 일치 수와 materialized 후보 수를 구분한다.'),
      ('해석','기계적 입력 전달과 최종 법률 결론은 별도 지표다. 메뉴나 원문이 전달됐어도 관련성을 판단하거나 최종 주장을 만들지 못하면 답변 성공으로 세지 않는다. 이번 결과의 도구·의미 오류를 보존하며 결과를 보고 고친 코드를 같은 run에서 재실행하지 않았다.'),
      ('한계와 일반화 가능 범위','과거 기록과 비교한 CM3 인샘플 단회다. 모델·provider 변동과 초기 로딩 때문에 시간 차이의 인과를 확정하지 않는다. judge calibration·반복 분산·현행 법령 버전 검증은 없다. GENOS 현장 시험이 아니다.'),
      ('운영 결정·롤백 조건','MAIN 기본·활성 포인터 불변. 선택 후보는 연구 snapshot으로만 실행했다. 후속 변경이나 재평가는 새 ADR로 분리하며 이 실행의 질문·코드·모델·원응답을 덮어쓰지 않는다.'),
      ('재현 명령','완료 run을 덮어쓰지 말고 새 ADR에서 동결 입력을 재사용한다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+rel(ADR)+' --final`\n\n[질문별 전체 입출력](실험/README.md) · [측정·실패 상세](artifacts/run-001/diagnostics.json) · [사전 설계](PLAN.md)')]
    (ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0487: Qwen v3 입력 분할 CM3 재실험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(sections,1))+'\n')
    for q in m['questions']:
        p=ADR/'실험'/q['file'];s=p.read_text().replace('각 arm 1회, 원시 기록 exact.','candidate 이번 1회; baseline은 역사적 실행 원본을 재사용, 원시 기록 exact.')
        s+='\n## 9. 재실험 전달·오류 상세 및 기준 원본\n\n'+json.dumps(wires[q['case_id']],ensure_ascii=False,indent=2)+'\n'
        p.write_text(s);q['sha256']=sha(p)
    write(ADR/'실험/manifest.json',m)
    (ADR/'실험/README.md').write_text('# Qwen v3 CM3 재실험\n\n'+table+'\n\nbaseline은 과거 v3 기록, 이번 새 실행은 candidate 3건이다.\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
    am=read(ART/'manifest.json');paths={ROOT/f['path'] for f in am['files']}
    paths.update(p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json')
    paths.update((ROOT/'06_TOOLS/EXPERIMENTS/adr_0487').glob('*.py'))
    am['files']=[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input/code, measured or explicitly historical receipt','contains_raw_prompts_and_outputs':p.suffix=='.json' and ('run-001' in str(p) or 'historical' in str(p))} for p in sorted(paths)]
    write(ART/'manifest.json',am)
    print(table)
if __name__=='__main__':main()
