"""Availability/drift follow-up; never replace failed parent or merge its timing."""
from pathlib import Path
import json

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0570-provider503-frozen-replay'
O=A/'artifacts/run-001'
P=R/'04_EXPERIMENTS/ADR/ADR-0569-compact-plan-smallpool'
read=lambda p:json.loads(p.read_text())


def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'


def main():
    data=read(O/'result.json');m=read(A/'실험/manifest.json');grade=read(O/'offline-grade.json')
    checks=[]
    for r in data['results']:
        g=next(g for g in grade['grades'] if g['arm']==r['arm'])
        policy=r.get('policy') or {}
        checks.append({'arm':r['arm'],'status':r['status'],'seconds':r['seconds'],'model_calls':r['model_calls'],
            'required_originals_presented':not g['missing_presented'],
            'full55_scope_preserved':len(policy.get('allowed_node_ids',[]))==55,
            'version_revalidation_observed':any(v.get('fallback_reason') for v in policy.get('queries',{}).values()),
            'small_pool_shortcut_applied':read(O/'cases'/r['case_id']/r['arm']/'selection.json').get('small_pool_full_originals',False) if r['status']=='ANSWER' else None,
            'strict_citation_term_pass':g['pass'],'missing_cited':g['missing_cited'],'error':r['error']})
    success=all(c['status']=='ANSWER' and c['required_originals_presented'] and c['full55_scope_preserved'] for c in checks)
    audit={'unchanged_frozen_implementation':True,'availability_and_drift_pass':success,'checks':checks,
        'parent_failed_receipt_unchanged':True,'not_merged_with_parent_timing':True,'main_changed':False}
    write(O/'availability-drift-audit.json',audit);m['results']['availability_drift_audit']=audit
    write(A/'실험/manifest.json',m)
    front=(A/'README.md').read_text().split('---',2)[1]
    if success:front=front.replace('status: Rejected','status: Proposed')
    sections=[('1. 결정 요약','동일 frozen 후보의 외부503 이후 완료·원문보존 확인 '+('통과' if success else '미통과')+'. 부모 실패·속도 gate는 그대로 보존한다.'),
        ('2. 문제와 변경 전 구조','ADR0569 combined 마지막 DRIFT-01 계획 요청이 Parasail/OpenRouter HTTP503으로 실패했다. 같은 구현을 독립2회 다시 확인했다.'),
        ('3. 가설과 사전 판정 기준',block(m['design']['success_criteria'])),
        ('4. 실험 설계','baseline/replay 둘 다 동일 ADR0569 combined frozen revision이다. 후보 구현·프롬프트·스키마·질문·corpus를 변경하지 않았다. 두 호출 arm을 결과 확인 전에 동결했다.'),
        ('5. 데이터·모델·재현성','합성55원문·DRIFT-01 한 질문. Gemma ParasailFP8 thinking off,1536출력, retries/repairs0. gold byte동일, 제품 입력 미노출. 새 generation fixture이며 MAIN은 유지한다.'),
        ('6. 결과',block(audit)),
        ('7. 사례별 오류 분석',block(grade['grades'])),
        ('8. 비용·지연·회수 규모',block({k:v for k,v in grade.items() if k!='grades'})),
        ('9. 해석','외부503 여부와 프로그램의 분류·근거 보존을 구분한다. 정상 실행은 최종 인용 정확도나 운영 성능 인증을 뜻하지 않는다. 이전 실패의0.64초를 빠른 응답으로 간주하지 않는다.'),
        ('10. 한계와 일반화 가능 범위','동일 모의 질문2호출뿐이다. 부모7질문 비교에 재실행 시간을 끼워 넣지 않는다. 전체 서비스·GENOS·실제 로그 학습·현장 부하 미실행.'),
        ('11. 운영 결정·롤백 조건','MAIN·generation31·registry 변경 없음. 동일 frozen code를 명시 연구 runner에서만 호출했다. parent 결과의 사전7질문 gate는 통과로 바꾸지 않는다.'),
        ('12. 재현 명령','`.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0570/run.py --live`. 완료 기록을 덮어쓰지 않고 새 ADR로 분기한다.')]
    (A/'README.md').write_text('---'+front+'---\n\n# ADR-0570 외부503 뒤 동결 후보 재확인\n\n'+'\n\n'.join('## '+h+'\n\n'+v for h,v in sections)+'\n')
    original=read(P/'artifacts/run-001/phase-gate-audit.json')
    common=original['supplemental_common_completed_cases']
    small_results=read(P/'artifacts/run-001/result.json')['results']
    stats={}
    for arm in ['baseline','compact','combined']:
        rs=[r for r in small_results if r['arm']==arm and r['case_id'].startswith('APP')]
        us=[u for r in rs for u in r['usage']]
        stats[arm]={'plan':sum(u['seconds'] for u in us if u['phase']=='source-query-plan')/3,
            'selection':sum(u['seconds'] for u in us if u['phase'] in ['source-triage','source-omission-review'])/3,
            'whole':sum(r['seconds'] for r in rs)/3,'calls':sum(r['model_calls'] for r in rs)}
    rows='\n'.join(f"| {name} | {stats['baseline'][key]:.2f} | {stats['combined'][key]:.2f} |" for name,key in [('계획 생성','plan'),('선별·누락 검토','selection'),('전체 응답','whole')])
    retries='\n'.join(f"- {c['arm']}: {c['status']}, {c['seconds']:.2f}초, 모델 호출 {c['model_calls']}회, 필수 원문 보존 {c['required_originals_presented']}, 전체55개 scope 보존 {c['full55_scope_preserved']}, 최종 인용 기준 {c['strict_citation_term_pass']}." for c in checks)
    text=f'''# 계획과 원문 선별 단축 — 원본 비교와 외부503 재확인

계획에서 중복 설명 대신 개념 ID만 붙이고, 작은 완독 후보의 원문 선별·누락 점검을 한 호출로 합쳤다. 로컬 합성 질문7개·세 구현 비교에서 마지막 통합 후보 요청이 외부503으로 실패했다. 실패를 원본에 남기고 같은 동결 코드를 별도 ADR에서2회 다시 실행했다.

## 단축한 방법

계획은 기존 queries와 reason을 재사용하고 query별 concept ID만 추가한다. 제외 관계는 DB에서 컴파일한다. 선별은 후보1~16개 모두 완독·원문 합계16000자 이하·입력80000자 이하일 때 후보 전부의 전체 원문을 첫 호출에 넣는다. 그 호출에서 선별과 누락 점검을 함께 한다. 미완독·큰 후보·큰 원문·구조 전용 경로는 기존 처리를 유지한다.

## 원본 비교에서 완료한 규정 질문3개

| 질문당 평균·초 | 이전 후보 재실행 | 통합 후보 |
|---|---:|---:|
{rows}

모델 호출은 질문당4회에서3회로 줄었다. 세 질문 모두 필수 원문 제시·인용·답변 용어 기준을 통과했다. 원문 회수는 각각6개로 동일했다. 같은 후보 원문을 먼저 한 번에 읽어 별도 누락 검토 호출을 줄인 결과다.

## 전체 비교의 한계

원래7개 사전 게이트는 통과하지 못했다. 마지막 DRIFT-01 통합 후보 계획 요청이 외부503으로 실패해 처리되지 않았기 때문이다. 실패의0.64초를 전체 평균에 넣으면 속도가 부당하게 좋아 보인다. 이 값은 속도 개선 주장에 사용하지 않았다.

세 구현 모두 정상 완료한 공통6개만의 보조 비교에서 이전 후보 평균은 {common['baseline']['mean_seconds']:.2f}초, 통합 후보는 {common['combined']['mean_seconds']:.2f}초였다. 감소율은 {original['supplemental_common_completed_wall_reduction']:.1%}다. 완료6개 기준 모델 호출은24→21회다. 이는 선택된 성공 표본의 보조 결과이며7개 전체 사전 게이트의 통과를 대신하지 않는다. 계획만 간소화한 후보는7개 모두 실행했고 계획 출력2598→1080토큰, 계획 평균14.73→7.08초였지만 전체 평균은37.94→36.49초로 차이가 작았다.

외부 모델 지연과 캐시가 흔들렸고, 작은 합성 질문·반복1뿐이다. 전체 시간 delta를 특정 변경 하나의 인과 효과나 현장 성능으로 단정하지 않는다. 계약 테스트11개 통과, graph/SQL/READ/recall은 부모와 해시 동일하며 기존14개 계약 검증을 연결했다. MAIN은 변경하지 않았다.

## 동일 코드로 실패 사례 재확인

두 재확인의 완료·버전 원문 보존 게이트: {success}.

{retries}

부모 실패를 수정하거나 재실행 시간을 원래7개 비교에 합치지 않았다. 최종 답변에서 일반 예외 규정의 필수 인용이 빠지는 공통 실패는 원문 보존과 별도로 채점했다. 제품 답변을 평가 결과로 고치지 않았다.

## 근거

- [원본 비교 보고서]({R}/07_DOCS/REFERENCE/REPORTS/COMPACT_PLAN_SMALLPOOL_20260930.md)
- [원본 실패·단계별 분석]({P}/artifacts/run-001/phase-gate-audit.json)
- [503 재확인 설계·결과]({A}/README.md)
- [재확인 원문·scope·인용 판정]({O}/availability-drift-audit.json)
'''
    report=R/'07_DOCS/REFERENCE/REPORTS/COMPACT_PLAN_SMALLPOOL_FOLLOWUP_20260930.md'
    report.write_text(text)
    print(json.dumps({'availability':audit,'followup_report':str(report)},ensure_ascii=False))


if __name__=='__main__':main()
