"""Truthful report for a failed in-sample candidate; no product replay."""
from run import ROOT,ADR,RUN,read,put
HEADINGS=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
def main():
    m=read(ADR/'실험/manifest.json');r=read(RUN/'result.json')
    lines=['|사례|경로|선택 완료|필수 원문 조 선택|연결 판단 호출|총 호출|초|','|---|---|---|---|---|---|---|']
    for x in r['rows']:
        lines.append(f'|{x["case_id"]}|{x["arm"]}|{x["source_selection_complete"]}|{x["required_roots_selected"]}/{x["required_roots_total"]}|{x["reference_rounds"]}|{x["model_calls"]}|{x["seconds"]:.2f}|')
    table='\n'.join(lines)
    explanation='CM003: reference catalog found 23 verified edges, grouped into 10 routes. The 24000-character detailed menu fitted only the first 9 groups; bylaw article23 was the one omitted group. Model skipped the 9 shown groups, so this is still an input omission, not rejection of the needed reverse link. CM051: first model proposed source rule6 units but paired U100 with exact:100 although U100 offered exact:106. Server rejected the unoffered pair before READ; no final selection or answer was made.'
    result='# 묶음 연결 탐색 후보 — 실패 보존\n\n동일 legal_agent에 정·역참조 묶음 선택을 구현했다. 후보 코드의 최소단위·연결·위키 재사용 계약 54개는 통과했다. 실제 두 질문에서는 사전 성공 기준을 충족하지 못했다. MAIN·GENOS 미반영.\n\n'+table+'\n\n'+explanation+'\n\n[정확한 입력·출력과 단계 원장](artifacts/run-001/result.json). 최종 법률 답변을 생성하지 않았으므로 원문 선택 결과를 정답률로 해석하지 않는다. 후속 후보는 새 ADR에서 연결 메뉴 압축·누락 처리 및 닫힌 선택의 제한적 재판단을 검증한다. 색인은 재사용했다.\n'
    (ADR/'RESULT.md').write_text(result)
    (ADR/'INTEGRATION.md').write_text('# 연결 상태\n\n기준: ADR0621/bounded-unit의 동결 구현. 공통 source_selection→unit_selection에서 unit_relations를 호출한다. 구조 MATCH도 동일 메뉴를 사용한다. eager reference expansion은 두 recall branch에서 중단하고 모델이 선택한 READ만 실행한다. memory_rag 응답 계약과 bounded_source_session의 새 원문 저장·view 연결도 수정했다. 원 READ checkpoint는 변경하지 않는다.\n\n54개 동결 계약에는 선택한 참조 원문→ASSESS/COMPOSE→확정→두 위키→새 대화 재사용 및 bounded source bundle이 포함된다. 실제 CM3 메뉴 누락과 CM51 잘못된 id/scope를 보존한다. MAIN 승격 조건은 충족하지 않았다. 작업 트리의 별도 native fulltext builder는 수정하지 않았다. 통합·holdout·MAIN·GENOS는 별도다. 롤백은 기존 활성 generation37 유지다.\n')
    front=(ADR/'README.md').read_text().split('---',2)[1]
    bodies=['Proposed. Functional contracts pass, two live probes do not meet predeclared success criteria. [결과](RESULT.md).',
        'Exact structure MATCH did not offer reverse links; eager fulltext reference expansion read unrelated candidates.',
        str(m['design']['success_criteria'])+'\n\n'+str(m['design']['failure_criteria']),
        'Fresh baseline/candidate on fixed CM003/CM051. Baseline2 calls; candidate≤4. All references grouped before choosing targets. No final answer or offline model judge.',
        'Exact ADR0621 parent, same immutable public145 scope/store/unit index; Qwen3.8 Parasail FP8, reasoning none, no fallback. Raw requests/responses and generation/code hashes retained.',
        table,explanation,
        str(m['results']['latency'])+'\n\nUsage per call is in manifest/result; setup+recall+selector only; two samples cannot estimate broad latency.',
        'Existence of reference menus is separate from complete menu delivery and source choice validity. Gold joined after selection; source retrieval counts are not legal correctness.',
        'Known/in-sample questions, synthetic consumer correctness, public sources only. GENOS unavailable. No final ASSESS/COMPOSE on live cases.',
        'Proposed, decision_eligible=false, MAIN generation37 and GENOS unchanged. Preserve this frozen failed candidate; any outcome-driven fix requires a new ADR.',
        '.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0622/contracts.py --frozen. Completed live calls must not be rerun in this ADR.']
    (ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0622 묶음 연결 탐색\n\n'+'\n'.join(f'## {i}. {h}\n\n{v}\n' for i,(h,v) in enumerate(zip(HEADINGS,bodies),1)))
    m['design']['primary_metric_result']={'functional_contracts_passed':54,'live_criteria_met':False,'cm003_reverse_root_selected':False,'cm051_selector_contract_valid':False}
    put(ADR/'실험/manifest.json',m)
if __name__=='__main__':main()
