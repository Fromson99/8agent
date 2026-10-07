"""Offline stage attribution and policy evaluation; no answer modifications."""
from pathlib import Path
import hashlib
import json
import statistics
from xml.etree import ElementTree

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql'
OUT=A/'artifacts/run-001'
ARMS=['baseline','integrated']
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def block(v):return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'


def main():
    m=read(A/'실험/manifest.json');data=read(OUT/'result.json');grade=read(OUT/'offline-grade.json')
    if data['status']!='complete':raise ValueError('incomplete product run')
    # Every per-case receipt and aggregate counter must agree after wrapper restore.
    for r in data['results']:
        own=read(OUT/'cases'/r['case_id']/r['arm']/'result.json')
        assert r==own
    sql=[];current=[]
    for l in (A/'artifacts/live-console.log').read_text().splitlines():
        try:v=json.loads(l)
        except ValueError:continue
        if v.get('event')=='fulltext.sql.timings':current.append(v)
        if 'case' in v and 'arm' in v:
            r=next(r for r in data['results'] if r['case_id']==v['case'] and r['arm']==v['arm'])
            sql.append({'case_id':v['case'],'arm':v['arm'],'executed_rank_calls':len(current),
                'rank_wrapper_calls':len(r['fts']),'fetched_rows':sum(x['fetched_count'] for x in current),
                'selected_rows':sum(x['selected_count'] for x in current),
                'sql_seconds':sum(sum(x.get(k,0) for k in ['sql_execute_ms','sql_first_row_ms','sql_fetch_ms']) for x in current)/1000,
                'metrics':current});current=[]
    assert len(sql)==14 and not current
    totals={}
    for arm in ARMS:
        rs=[r for r in data['results'] if r['arm']==arm];ss=[s for s in sql if s['arm']==arm]
        ts=[r['seconds'] for r in rs]
        totals[arm]={'executed_rank_calls':sum(s['executed_rank_calls'] for s in ss),
            'fetched_rows':sum(s['fetched_rows'] for s in ss),'sql_seconds':sum(s['sql_seconds'] for s in ss),
            'read_chars':sum(r.get('read_chars',0) for r in rs),
            'planner_calls':sum(u['phase']=='source-query-plan' for r in rs for u in r['usage']),
            'standalone_purpose_calls':sum(u['phase']=='purpose-recognition' for r in rs for u in r['usage']),
            'plan_seconds':sum(r.get('plan_seconds',0) for r in rs),
            'recall_seconds':sum(r.get('recall_seconds',0) for r in rs),
            'model_roundtrip_seconds':sum(u['seconds'] for r in rs for u in r['usage']),
            'planner_input_tokens':sum(u.get('input_tokens') or 0 for r in rs for u in r['usage'] if u['phase']=='source-query-plan'),
            'planner_output_tokens':sum(u.get('output_tokens') or 0 for r in rs for u in r['usage'] if u['phase']=='source-query-plan'),
            'case_p50':statistics.median(ts),'case_p95':sorted(ts)[round((len(ts)-1)*.95)]}
    mixed=next(r for r in data['results'] if r['case_id']=='MIX-01' and r['arm']=='integrated')
    c_nodes={s for s,c in mixed['catalogue'].items() if c['document_id']=='mock-performance:v1'}
    mixed_actions=[]
    for a in mixed.get('plan',{}).get('search_actions',[]):
        p=mixed['policy']['queries'][a['query']]
        mixed_actions.append({'action':a,'allowed_count':len(p['allowed_node_ids']),
            'excluded_count':len(p['excluded_node_ids']),'c_allowed':bool(c_nodes&set(p['allowed_node_ids'])),
            'policy_sha256':p['sha256']})
    app=[x for x in mixed_actions if x['action']['concept_refs']==['purpose:applicable']]
    perf=[x for x in mixed_actions if x['action']['concept_refs']==['purpose:performance']]
    mixed_ok=bool(app and perf and all(not x['c_allowed'] for x in app) and all(x['c_allowed'] for x in perf))
    drift=next(r for r in data['results'] if r['case_id']=='DRIFT-01' and r['arm']=='integrated')
    policies=list((drift.get('policy') or {}).get('queries',{}).values())
    fallback=any(p.get('fallback_reason') for p in policies)
    tests=list(ElementTree.parse(A/'artifacts/contracts.xml').getroot().iter('testcase'))
    passed=sum(t.find('failure') is None and t.find('error') is None for t in tests)
    paired={'both_correct':0,'candidate_only_correct':0,'baseline_only_correct':0,'both_wrong':0}
    for cid in m['runs'][0]['case_ids']:
        b=next(g for g in grade['grades'] if g['case_id']==cid and g['arm']=='baseline')['pass']
        c=next(g for g in grade['grades'] if g['case_id']==cid and g['arm']=='integrated')['pass']
        paired['both_correct' if b and c else 'baseline_only_correct' if b else 'candidate_only_correct' if c else 'both_wrong']+=1
    recall_ok=all(not g['missing_presented'] for g in grade['grades'])
    no_extra=totals['integrated']['planner_calls']==7 and totals['integrated']['standalone_purpose_calls']==0
    source_rowids=read(OUT/'fts-projection.json')['source_rowids']
    sql_scope=all(f['sql_scope_applied'] and
        all(source_rowids[sid] in set(f['scope_rowids']) for sid in f['returned_ids'])
        for r in data['results'] if r['arm']=='integrated' for f in r['fts'])
    gold=read(A/'artifacts/design/upstream-receipts.json')
    assert gold['parent_gold_sha256']==sha(A/'artifacts/design/expected-offline.json')
    success=not paired['baseline_only_correct'] and recall_ok and no_extra and sql_scope and mixed_ok and passed==len(tests)
    audit={'classification':'SYNTHETIC','primary_grade_preserved':True,'scope_success':success,
        'parent_gold_byte_identical':True,'standalone_purpose_calls0':no_extra,
        'required_originals_presented100':recall_ok,'sql_scope_applied':sql_scope,
        'mixed_action_scopes_passed':mixed_ok,'mixed_actions':mixed_actions,'drift_fallback_observed':fallback,
        'paired':paired,'contracts':{'passed':passed,'total':len(tests)},'totals':totals,'sql_cases':sql,
        'boundaries':['hand-curated synthetic concepts; no actual log learning','7questions1repeat; cache and external latency variable',
            'not full BoundedSourceSession/Compose request','rowid predicate can introduce temporary ORDER BY sort',
            'unbound automatic variants revert to conservative union/default; derived action lineage not complete']}
    write(OUT/'action-scope-audit.json',audit)
    m['results']['action_scope_audit']={k:v for k,v in audit.items() if k!='sql_cases'}
    m['results']['comparisons'][0].update(paired)
    m['results']['latency']['by_arm']={a:{**m['results']['latency']['by_arm'][a],
        'case_seconds_p50':totals[a]['case_p50'],'case_seconds_p95':totals[a]['case_p95']} for a in ARMS}
    write(A/'실험/manifest.json',m)
    summary={k:v for k,v in audit.items() if k not in ['sql_cases','mixed_actions']}
    front=(A/'README.md').read_text().split('---',2)[1]
    front=front.replace('status: Rejected','status: Proposed') if success else front
    sections=[('1. 결정 요약','행동별 개념·SQL scope 기능 '+('통과' if success else '미통과')+'. MAIN 변경 없음. 운영 승격·전체 서비스 속도 인증은 별도다.'),
        ('2. 문제와 변경 전 구조','부모 ADR0567은 별도 목적 판별 호출을 추가하고 FTS SQL 이후 scope를 걸렀다. 현재 candidate는 기존 catalogue 호출의 출력 계약을 확장하고 SQL에 eligibility를 선반영한다.'),
        ('3. 가설과 사전 판정 기준',block(m['design']['success_criteria'])),
        ('4. 실험 설계',block(m['design']['arms'])+'\n기존 catalogue prompt/schema를 실제 model call로 실행했다. candidate는 query별 concept_refs/reason/expected_information을 함께 생성한다. 단독 목적분류 단계가 없다. 두 native SourceRecall 분기·READ·native source_selection을 사용했다. BROWSE는 실제 browse 후 공통 원문 예시 검색으로 계속하며 기본 Compose는 공유 연구 답변 호출이다.'),
        ('5. 데이터·모델·재현성','부모 corpus55개·질문7개·gold byte동일. Gemma Parasail FP8 thinking off, 출력1536, schema-in-prompt true, retries/repairs0, 순서교대·반복1. 개념과 분류는 수작업 합성이며 실제 로그학습 성공을 뜻하지 않는다.'),
        ('6. 결과',block({'scope':summary,'grade':{k:v for k,v in grade.items() if k!='grades'}})),
        ('7. 사례별 오류 분석',block([g for g in grade['grades'] if not g['pass']])),
        ('8. 비용·지연·회수 규모',block({'usage':grade['usage'],'latency':grade['latency'],'sql_and_stage':totals})),
        ('9. 해석','추가 호출은 없지만 개념 메타데이터를 생성하는 입력·출력 비용은 남는다. SQL rowid scope를 MATCH와 함께 실행해 반환행을 제한했고 BM25 원래 순위와 tie를 native contract로 검증했다. rank query의 전체 물리 비용이 언제나 감소한다는 보장은 없다.'),
        ('10. 한계와 일반화 가능 범위',block(audit['boundaries'])+'\n기본 API 전체·GENOS/NFS·실제 비공개 문서·자동 로그 학습 미실행. 원문 버전이 다르면 현재 분류의 재검토가 필요하며 hard 제외를 해제한다.'),
        ('11. 운영 결정·롤백 조건','Proposed probe. MAIN·generation31·production registry 불변. unknown/mixed 자동파생 query는 보수적 scope로 처리한다. SQL rowid projection은 fulltext index hash에 결속된다. out-of-sample·현장 부하 검증 후 별도 승격한다.'),
        ('12. 재현 명령','`.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0568/run.py --live` 및 `test_contracts.py`. 완료 산출물은 덮어쓰지 말고 새 ADR/run을 선점한다.')]
    (A/'README.md').write_text('---'+front+'---\n\n# ADR-0568 기존 계획 내 행동 개념과 SQL scope\n\n'+'\n\n'.join('## '+h+'\n\n'+body for h,body in sections)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
