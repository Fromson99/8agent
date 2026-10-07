"""Post-run stage attribution and human review, preserving primary grading."""
from pathlib import Path
import hashlib
import json
from xml.etree import ElementTree

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal'
OUT=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    data=read(OUT/'result.json');summary=read(OUT/'offline-grade.json')
    changes=[]
    for r in data['results']:
        own=read(OUT/'cases'/r['case_id']/r['arm']/'result.json')
        changes.append({'case_id':r['case_id'],'arm':r['arm'],
                        'aggregate_rank_entries':len(r['fts']),'case_rank_entries':len(own['fts']),
                        'case_receipt_sha256':sha(OUT/'cases'/r['case_id']/r['arm']/'result.json')})
    data['results']=[read(OUT/'cases'/r['case_id']/r['arm']/'result.json') for r in data['results']]
    write(OUT/'instrumentation-audit.json',{'aggregate_raw_preserved':True,
        'issue':'Shared cached FulltextIndex retained wrapper closures and appended later FTS timings to earlier aggregate in-memory lists',
        'correction':'Immutable per-case results cross-checked against sequential SQL console events',
        'wall_cost_reads_answer_scores_changed':False,'entries':changes})
    gold=read(A/'artifacts/design/expected-offline.json')
    # Console is sequential. Each emitted case result terminates its SQL metrics.
    sql=[];current=[]
    for line in (A/'artifacts/live-console.log').read_text().splitlines():
        try:v=json.loads(line)
        except ValueError:continue
        if v.get('event')=='fulltext.sql.timings':current.append(v)
        if 'case' in v and 'arm' in v:
            sql.append({'case_id':v['case'],'arm':v['arm'],'rank_calls':len(current),
                'fetched_rows':sum(x['fetched_count'] for x in current),
                'selected_rows':sum(x['selected_count'] for x in current),
                'sql_seconds':sum(sum(x.get(k,0) for k in ['sql_execute_ms','sql_first_row_ms','sql_fetch_ms']) for x in current)/1000,
                'metrics':current});current=[]
    assert len(sql)==14 and not current
    for row in sql:
        r=next(r for r in data['results'] if r['case_id']==row['case_id'] and r['arm']==row['arm'])
        assert row['rank_calls']==len(r['fts'])
    totals={}
    for arm in ['baseline','graph']:
        rs=[r for r in data['results'] if r['arm']==arm];ss=[s for s in sql if s['arm']==arm]
        totals[arm]={'sql_rank_calls':sum(s['rank_calls'] for s in ss),'sql_fetched_rows':sum(s['fetched_rows'] for s in ss),
            'sql_seconds':sum(s['sql_seconds'] for s in ss),'read_chars':sum(r['read_chars'] for r in rs),
            'read_actions':sum(r['read_actions'] for r in rs),
            'cached_input_tokens':sum(u.get('usage',{}).get('prompt_tokens_details',{}).get('cached_tokens',0) for r in rs for u in r['usage']),
            'model_roundtrip_seconds':sum(u['seconds'] for r in rs for u in r['usage']),
            'app_cost_usd':sum(u['cost_usd'] for r in rs if r['case_id'].startswith('APP') for u in r['usage'])}
    tests=list(ElementTree.parse(A/'artifacts/native-access.xml').getroot().iter('testcase'))
    assert len(tests)==8 and not any(x.find('failure') is not None or x.find('error') is not None for x in tests)
    purpose=[{'case_id':r['case_id'],'expected':gold['expected_purpose'][r['case_id']],
              'actual':r['classifier']['purpose'],'exact_match':r['classifier']['purpose']==gold['expected_purpose'][r['case_id']],
              'active_relation_ids':r['policy']['active_relation_ids'],'excluded_count':len(r['policy']['excluded_node_ids']),
              'fallback_reason':r['policy'].get('fallback_reason')} for r in data['results'] if r['arm']=='graph']
    observation={'schema_version':'investigation-value-stage-attribution-v1','computed_post_selection':True,
        'primary_grade_changed':False,'sql_cases':sql,'totals':totals,'native_boundary_tests_passed':8,
        'purpose_labels':purpose,'purpose_exact_match':sum(x['exact_match'] for x in purpose),
        'purpose_total':7,'policy_branch_matches_intended_scope':True,
        'qualitative_review':{'reviewer':'Codex; post-run supplemental, not a new model/evaluator call',
            'APP-01':'양쪽 모두 미국 국적·의결권 요건과 7영업일·국적/의결권 제출자료를 현재 합성 원문에서 인용함',
            'APP-02':'양쪽 모두 대한민국 국적이면 해외 거주만으로 외국인이 되지 않는다고 답함',
            'APP-03':'양쪽 모두 비의결권 제외·보고 의무 없음·별도 규정 후속 확인을 제시함',
            'INV-01':'규정·실적 자료 유형을 양쪽 모두 제시함. 후보는 INVENTORY를 MIXED로 분류했지만 제외를 하지 않음',
            'PERF-01':'양쪽 모두 120건·17퍼센트로 답하고 실적 원문을 인용함',
            'MIX-01':'규정과 실적을 모두 조사하고 C를 보존함',
            'DRIFT-01':'후보는 해시가 다른 신판 때문에 제외를 해제함. 양쪽 모두 신판 특례와 3영업일을 제시하나 일반 제외 조문을 최종 인용하지 않아 동결한 인용 기준 실패. 점수를 바꾸지 않음'}}
    write(OUT/'stage-attribution.json',observation)
    m=read(A/'실험/manifest.json');m['results']['native_boundary_contracts']={'passed':8,'total':8}
    m['results']['purpose_labels']={'exact_match':6,'total':7,'inventory_as_mixed_preserves_scope':True}
    m['results']['sql_attribution']=totals
    m['results']['decision']='사전 기능7/7 미충족·속도 악화로 운영 채택 보류; 원문/입력/비용 절감은 관측된 조건부 효용'
    write(A/'실험/manifest.json',m)
    rows=[]
    for cid in m['runs'][0]['case_ids']:
        b=next(r for r in data['results'] if r['case_id']==cid and r['arm']=='baseline')
        g=next(r for r in data['results'] if r['case_id']==cid and r['arm']=='graph')
        rows.append(f"| {cid} | {len(b['read_ids'])} → {len(g['read_ids'])} | {b['seconds']:.2f} → {g['seconds']:.2f} | {g['classifier']['purpose']} | {g['policy'].get('fallback_reason','')} |")
    b=summary['by_arm']['baseline'];g=summary['by_arm']['graph']
    ub=summary['usage']['baseline'];ug=summary['usage']['graph']
    lb=summary['latency']['baseline'];lg=summary['latency']['graph']
    report=R/'07_DOCS/REFERENCE/REPORTS/INVESTIGATION_ONTOLOGY_VALUE_20260929.md'
    report.write_text(f'''# 조사 목적 온톨로지 가치 재실험 — 2026-09-29

이번 방식은 불필요한 원문 회수와 모델 입력량을 줄였지만, Fulltext 병목이나 전체 응답 속도를 개선하지 못했다. 원문·비용 절감에 조건부 가치가 있으며 현재 후보의 운영 채택은 보류한다.

실험은 [ADR-0567](../../../04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal/README.md)에 보존했다. 실행 전 journal 연결이 잘못된 [ADR-0566](../../../04_EXPERIMENTS/ADR/ADR-0566-investigation-ontology-value/README.md)은 모델 호출0의 실패로 남기고, 새 ADR에서 연결만 수정했다. 질문·원문·gold·프롬프트·DB 정책은 byte 동일하다.

## 실제로 비교한 것

선택된 로컬 release `legal-agent-structure-catalogue-pecab-repair-20260929-r1`의 SourceRecall/global branch/source_selection/Fulltext와 hash가 일치하는 기준 모듈을 사용했다. 부모 ADR-0565의 SQLite 조사 목적 그래프는 그대로 계승했다.

양쪽에서 같은 합성 corpus 55개 조문, 질문7개, 공통 검색 계획, 실제 FTS5 검색·v5 READ·native 원문 선별·Gemma 답변을 실행했다. 후보는 질문 목적을 Gemma로 판별하는 호출1개를 추가하고, 목적→EXCLUDES→자료 종류 관계를 DB에서 컴파일해 두 회수 분기와 READ 직전에 적용했다. 후보 목적 인식 비용·시간을 모두 포함했다. 모델은 Gemma / Parasail FP8 / thinking off다. arm 순서는 질문마다 교대했고 반복1·재시도0이다.

전체 BoundedSourceSession/Compose API를 실행한 것은 아니다. 양쪽 query plan은 사전 고정했고 의무 계획·기본 Compose를 공통 연구 답변 호출로 대체했다. 따라서 전체 MAIN 서비스의 속도 인증으로 쓰지 않는다. 실제 사용자 로그의 자동 추출·밤 시간 학습은 실행하지 않았으며, 목적·자료 분류·EXCLUDES는 사람이 설계한 합성 온톨로지다. 이는 **유효한 개념 정책이 있을 때 온라인 소비가 이익을 주는지** 시험한 것이다.

## 결과

| 항목 | 기준 | 개념 정책 후보 | 변화 |
|---|---:|---:|---:|
| 전체 원문 조문 회수 | {b['read_roots']} | {g['read_roots']} | {100*(1-g['read_roots']/b['read_roots']):.1f}% 감소 |
| 적용규정3질문의 원문 회수 | {b['app_read_roots']} | {g['app_read_roots']} | {100*summary['app_read_reduction']:.1f}% 감소 |
| 모델 입력 토큰 | {ub['input_tokens']:,} | {ug['input_tokens']:,} | {100*(1-ug['input_tokens']/ub['input_tokens']):.1f}% 감소 |
| 모델 물리 호출 | {ub['calls']} | {ug['calls']} | 목적 인식7회 추가 |
| provider 보고 제품 비용 | ${ub['cost_usd']:.8f} | ${ug['cost_usd']:.8f} | {100*summary['cost_reduction']:.1f}% 감소 |
| 질문당 평균 관측 시간 | {lb['mean_seconds']:.2f}초 | {lg['mean_seconds']:.2f}초 | {100*(lg['mean_seconds']/lb['mean_seconds']-1):.1f}% 증가 |
| 필수 근거·인용·답변요소 기준 | {b['correct']}/7 | {g['correct']}/7 | 후보만의 신규 실패0 |
| SQL rank 호출 | {totals['baseline']['sql_rank_calls']} | {totals['graph']['sql_rank_calls']} | 동일 |
| SQL이 fetch한 검색 행 | {totals['baseline']['sql_fetched_rows']} | {totals['graph']['sql_fetched_rows']} | 동일 |
| 실제 SQL 구간 시간 합계 | {totals['baseline']['sql_seconds']:.4f}초 | {totals['graph']['sql_seconds']:.4f}초 | 소형 로컬 자료, 병목 개선 근거 없음 |

비용은 호출이 보고한 값으로 목적 판별과 cache 할인까지 포함한다. 양쪽 cached input은 {totals['baseline']['cached_input_tokens']:,} / {totals['graph']['cached_input_tokens']:,}토큰이다. 장기 평균이나 cache 없는 고정 요금 효과로 해석하지 않는다. 별도의 오프라인 구축·분류·로그 검토 비용은 온라인 비교에 포함하지 않았다.

| 사례 | 읽은 조문 기준→후보 | 시간 기준→후보(초) | 후보 목적 | 되돌림 |
|---|---:|---:|---|---|
{chr(10).join(rows)}

## 근거 보존과 실패

적용규정3질문에서는 54개에서6개로 줄였다. 단순히 프롬프트에 C 제외를 추가한 것이 아니라 DB 그래프가 만든 scope를 두 native 회수 분기에서 소비하고, READ에서도 제외한 원문·상위 문서의 우회 접근을 차단했다. 실제 native 접근 계약8개가 모두 통과했다. 이 연결은 회수 분기와 READ에만 적용했으며 다른 native 도구 전체 배선은 이번 실험에서 완료하지 않았다.

목록·실적·복합 질문에서는 C를 보존했다. 목적 이름은 6/7 일치했고 목록 질문을 MIXED로 분류한1건은 제외하지 않아 자료를 잃지 않았다. 이 결과가 수천 개 개념에서의 목적 인식 정확도를 입증하지는 않는다.

버전 변경 사례에서는 현재 원문 해시가 과거 분류와 달라 제외 정책을 해제하고55개를 조사했다. 양쪽 모두 신판 특례와3영업일을 답했다. 다만 비교한 일반 비의결권 제외 규정의 원문을 최종 claims에 인용하지 않아 사전 기준은 양쪽6/7이다. 필수 원문은 선별 입력까지100% 보존됐으며 이 실패는 최종 인용 단계다. 결과를 보고 gold나 성공 문턱을 바꾸지 않았다.

## 판단

과거 안내 prototype ADR-0562는 이미 최소 원문에 가까워 읽은 수17→16에 그쳤고 입력·비용이 약44% 증가했다. 이번에는 **읽기 전 범위를 줄이는 DB 소비자**를 연결해 원문 회수와 선별 inventory 입력을 줄였다. 잡음 자료가 많고 조사 목적·자료 분류가 검증된 곳에서는 이 방향의 가치가 관측됐다.

사용자가 지적한 Fulltext 병목은 그대로다. 현재 `rank()`는 전체 FTS SQL을 실행하고 반환된 행을 allowed scope로 거른다. 후보는 SQL 검색 호출과 fetch 행을 줄이지 못했다. 원문 회수 전체 시간은 {lb['recall_total_seconds']:.2f}→{lg['recall_total_seconds']:.2f}초였고, 추가 목적 인식에는 합계 {lg['recognition_total_seconds']:.2f}초가 들었다. 원문을 줄여도 모델 호출을 추가하면 느려질 수 있다는 결과다.

다음 설계의 우선순위는 기존 검색 계획·행동 판단에서 조사 목적을 함께 생성해 추가 판별 호출을 없애고, DB 정책을 공통 데이터 접근 계약으로 전달한 뒤 backend가 검색 전에 가능한 범위로 적용하는 것이다. Fulltext에는 SQL/색인 범위 제약, 다른 검색에는 그 backend의 범위 제약으로 번역한다. 이 개선은 이번 결과로 검증한 기능이 아니며 새 후보·분리 평가가 필요하다. 그다음 실제 로그에서 만든 관계의 오제외와 분류·통합 유지 비용을 평가해야 한다.

MAIN·활성 포인터 generation31·운영 registry·GENOS는 변경하지 않았다. 사전 기능7/7 기준과 속도 목표를 충족하지 않아 운영 승격 근거로 사용하지 않는다. 전체 graph validator의 기존 오류는 검증 기록에 별도로 남긴다.

[원시 결과](../../../04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal/artifacts/run-001/result.json) · [사전 기준·채점](../../../04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal/artifacts/run-001/offline-grade.json) · [SQL·목적 분류 상세](../../../04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal/artifacts/run-001/stage-attribution.json)
''')
    print(json.dumps({'report':str(report),'sql_totals':totals,'native_tests':8,'primary_grade_preserved':True},ensure_ascii=False))


if __name__=='__main__':main()
