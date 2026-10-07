"""Apply only prospective latency/call gate to frozen full-API outcomes."""
import json
from harness import R,A,sha,write

def main():
    p=A/'artifacts/run-001';summary=json.loads((p/'offline-grade.json').read_text());m=json.loads((A/'실험/manifest.json').read_text());result=json.loads((p/'result.json').read_text())
    by={arm:[r for r in result['results'] if r['arm']==arm] for arm in ('baseline','integrated')}
    calls={a:sum(r['calls'] for r in rows) for a,rows in by.items()}
    wall={a:sum(r['seconds'] for r in rows if r['status']=='ANSWER') for a,rows in by.items()}
    cost={a:summary['usage'][a]['cost_usd'] for a in by}
    unresolved={a:sum(len(r.get('answer',{}).get('unresolved',[])) for r in rows) for a,rows in by.items()}
    speed=all(r['status']=='ANSWER' for rows in by.values() for r in rows) and calls['integrated']<calls['baseline'] and wall['integrated']<=wall['baseline']
    accepted=summary['functional_pass'] and summary['generation_roundtrip_pass'] and speed
    comparisons={'source_citation_term_gate':summary['functional_pass'],'generation_roundtrip':summary['generation_roundtrip_pass'],
      'model_calls':calls,'successful_wall_seconds':wall,'successful_mean_seconds':{a:wall[a]/4 for a in by},
      'cost_usd':cost,'unresolved_total':unresolved,'call_reduction':1-calls['integrated']/calls['baseline'],
      'wall_reduction':1-wall['integrated']/wall['baseline'],'cost_reduction':1-cost['integrated']/cost['baseline'],
      'speed_gate':speed,'accepted':accepted,'large_corpus_speed_certified':False,'genos_speed_certified':False}
    write(p/'integration-decision.json',comparisons)
    m['results']['comparisons']=[{'baseline':'baseline','candidate':'integrated',**comparisons}]
    m['results']['error_taxonomy'] += [{'kind':'prospective_speed_gate_failed','details':comparisons}] if not speed else []
    write(A/'실험/manifest.json',m)
    readme=A/'README.md';text=readme.read_text();text=text.replace('status: Accepted','status: '+('Accepted' if accepted else 'Rejected'))
    text += '\n## 추가 판정: 사전 동결된 속도 기준\n\n'+json.dumps(comparisons,ensure_ascii=False,indent=2)+'\n\n'
    text += ('후보는 정확한 원문·인용 조건과 자동 개념 생성은 충족했다. 그러나 성공한 전체 API 4쌍의 평균 지연이 기준보다 길고 입력·출력 토큰 비용도 증가했다. '
             '기준 17회 대비 후보 12회로 호출은 줄었지만, 더 빠른 숏컷이라고 판정하지 않는다. 원문 완독 뿌리 수는 양쪽 8개로 같다. '
             '후보에서는 추가 미확인 문구가 생성되어 검토가 필요하다. 현재 로컬 서빙 릴리스·MAIN은 변경하지 않는다. '
             'ADR0573에서 별도로 Accepted된 야간 오프라인 구축은 독립적으로 연결할 수 있다.\n')
    readme.write_text(text)
    print(json.dumps(comparisons,ensure_ascii=False))

if __name__=='__main__':main()
