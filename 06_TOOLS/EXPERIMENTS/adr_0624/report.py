"""Report selection coverage and observed decisions; never infer answer accuracy."""
from run import ROOT, ADR, RUN, read, put, sha
from finalize import HEADINGS, block


def main():
    m=read(ADR/'실험/manifest.json');result=read(RUN/'result.json')
    observations=[]
    for arm in ('baseline','required-unit-closure'):
        folder=RUN/'cm-003'/arm
        raw=read(folder/'result.json')
        selected=read(folder/'selection.json') if (folder/'selection.json').exists() else {}
        nav=selected.get('reference_navigation',{})
        review=[read(p) for p in folder.glob('model-input-*.json') if read(p).get('phase')=='source-unit-review']
        originals=review[0]['data'].get('sources',[]) if review else []
        delegated=[r for r in nav.get('required_reads',[]) if r.get('kind')=='EXPLICIT_DELEGATED_CASES']
        observations.append({'arm':arm,'error':raw['error'],'status':raw.get('status'),
            'selected_source_ids':raw.get('selected_ids',[]),
            'explicit_exception_clause_delivered':any('2. 벤처금융 또는 전문투자자가 취득한 경우' in v['text'] for v in originals),
            'required_scopes':delegated,
            'required_scope_chars':sum(r['chars'] for r in delegated if r['status']=='READ'),
            'mandatory_article_root_subtree':any(r['scope']=='subtree:202' for r in delegated),
            'optional_group_counts':[len(b['data']['groups']) for b in nav.get('batches',[])],
            'optional_decisions':[b['decision'] for b in nav.get('batches',[]) if b['decision']],
            'unresolved_delegations':nav.get('unresolved_delegations',[]),
            'focus_unresolved':nav.get('focus_unresolved',[]),
            'model_calls':raw['model_calls'],'seconds':raw['seconds'],
            'cost_usd':sum(u.get('cost_usd',0) for u in raw['usage'])})
    candidate=observations[1]
    row=next(r for r in result['rows'] if r['arm']=='required-unit-closure')
    complete=row['source_selection_complete'] and row['required_root_selection_complete']
    live_met=(complete and candidate['explicit_exception_clause_delivered']
        and {r['scope'] for r in candidate['required_scopes'] if r['status'] in ('READ','ALREADY_READ')}=={'subtree:218','subtree:227'}
        and not candidate['mandatory_article_root_subtree'] and not candidate['unresolved_delegations'])
    m['design']['primary_metric_result']={'functional_contracts':result['contracts'],
        'live_criteria_met':live_met,'observations':observations,
        'answer_accuracy_measured':False,'new_answer_judge_calls':0,'source_index_rebuilds':0}
    m['results']['usage'].update(new_product_calls=sum(o['model_calls'] for o in observations),
        new_cost_usd=sum(o['cost_usd'] for o in observations),all_arms_fresh=True,product_calls_replayed=False)
    result['usage']=m['results']['usage'];result['observations']=observations;result['live_criteria_met']=live_met
    put(RUN/'result.json',result);m['runs'][0]['sha256']=sha(RUN/'result.json')
    put(ADR/'실험/manifest.json',m)
    table='|경로|근거 선택 완료|필수 원문 조 선택|핵심 예외 문장 전달|모델 호출|실행 시간|\n|---|---|---|---|---|---|\n'
    for o in observations:
        r=next(r for r in result['rows'] if r['arm']==o['arm'])
        table+=f'|{o["arm"]}|{r["source_selection_complete"]}|{r["required_roots_selected"]}/{r["required_roots_total"]}|{o["explicit_exception_clause_delivered"]}|{o["model_calls"]}|{o["seconds"]:.2f}초|\n'
    explanation=('질문에서 지목한 제3호·제4호를 저장된 구조 역할·서수와 결속한다. '
        '정확한 참조 좌표와 SPECIFIES_DELEGATED_CASES_OF 원문 단서가 있는 시행세칙 제23조④·⑤만 '
        '하위 호·목까지 읽는다. 단서가 없는 다른 연결은 같은 legal_agent의 FOLLOW/SKIP/DEFER 선택으로 남는다. '
        '위임 조건이 미해결이거나 한도/접근 범위로 읽을 수 없으면 pending이며 추가 조사가 필요하다. '
        '이 READ는 법률 적용의 승인이나 과거 답변의 정답 승격이 아니다.')
    limitations=('알려진 한 질문의 in-sample probe이며 각 arm 한 번, baseline→candidate 고정 순서다. '
        '최종 답변·정답률·CM051·실제 사용자 기억 정확도·GENOS 성능은 측정하지 않았다. '
        '정확한 명시 위임과 다음 각 호/목만 다루며 모든 의미 의존성을 해결하지 않는다. '
        '모호한 질문 좌표는 추측하지 않고 pending이다. 별도 native fulltext-stage의 manifest 결속 검사 '
        '1개는 후보에 없는 새 builder 기능이라 제외했고 호환은 미확인이다. '
        '기존 전역 graph 오류와 ADR0622의 메타데이터 경로 오류는 보존한다.')
    (ADR/'RESULT.md').write_text('# 질문 단위의 명시 위임 조건 읽기\n\n'+table+'\n'+explanation+
        '\n\n사전 근거 선택 기준 충족: '+str(live_met)+'. 법률 답변 정확도는 미측정.\n\n'+
        '동결 계약 '+str(result['contracts']['passed'])+'개 통과, 1개 범위 제외. 실제 시행세칙 최소 READ와 선택 원문 전달 여부는 아래 원값에서 확인한다.\n'+
        block(observations)+'\n'+limitations+'\n\n후보 구현·검증이며 로컬 활성 generation37·MAIN·GENOS 미전환, 원문·색인 재구축0회.\n\n'+
        '[실제 제품 입력·출력](실험/질문-001-cm-003.md), [실행·단계 원장](artifacts/run-001/result.json), [연결 계약](INTEGRATION.md).\n')
    (ADR/'INTEGRATION.md').write_text('# 동일 legal_agent의 최소 원문 확인\n\n'+explanation+
        '\n\nSourceRecall→unit_selection→unit_relations→unit_dependencies의 공통 읽기 경로다. '
        'selected_originals/evidence/read_scopes에 실제 READ를 저장하고 bounded_source_session은 마지막 '
        'source-unit-review의 원문 전달 view와 필수 읽기 사유를 결속한다. memory_rag/unified_rag도 같은 '
        'SELECT 근거를 ASSESS/COMPOSE와 확인 경험에 전달한다. 선택 회복·두 위키·새 대화 재사용은 '
        '합성 회귀로 검사했으며 공개 CM003의 최종 답변은 생성하지 않았다.\n\n'
        '사용자 지시로 작업 코드에 이미 제거된 memory-assess-check/memory-compose-check와 관련 '
        '영수증만 후보에 맞췄다. 라이브 두 selector arm에는 해당 답변 단계가 없으며 추가 답변 '
        '검증 모델을 쓰지 않는다. 인용·좌표·범위 검사는 유지한다.\n\n'+limitations+
        '\n\n선택 릴리스·운영 registry는 그대로다. 독립 평가와 MAIN 승격, native builder 통합, '
        'GENOS 배포는 별도이며 이 후보를 자동 선택하지 않는다.\n')
    front=(ADR/'README.md').read_text().split('---',2)[1]
    bodies=['Proposed. 알려진 CM003 근거 선택 기준 '+str(live_met)+'. MAIN unchanged. [결과](RESULT.md).',
        '부모 ADR0623은 예외 도입 문장과 READ 옵션을 줬지만, 모델이 각 호를 읽기 전에 SKIP하고 조사 완료로 처리했다.',
        m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
        '완료된 ADR0623 exact parent와 격리 candidate를 fresh baseline→candidate 순서로 한 번씩 실행한다. 고정 공개 corpus·질문·질의·모델·색인. Gold는 제품 선택 뒤 offline 결속.',
        '기존 223127 최소 원문 색인·145 공개 문서·고정 원문 세대를 재사용. Qwen3.8/Parasail FP8/reasoning none/no fallback. '+block(m['design']['code_isolation']),
        table,block(observations),block({'metrics':result['metrics'],'usage':m['results']['usage'],'latency':m['results']['latency']}),
        explanation,limitations,
        'in_sample=true, decision_eligible=false, Proposed. 활성 generation37 유지. 완료 부모·실패한 계약 로그·원문·색인·코드 revision을 보존한다. 자동 승격하지 않는다.',
        '.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0624/contracts.py --frozen. 모델 실행은 run_all.py에 동결돼 있으며 완료된 호출은 이 ADR에서 재실행하지 않는다.']
    (ADR/'README.md').write_text('---'+front+'---\n\n# ADR0624 질문 단위 명시 위임 원문 확인\n\n'+
        '\n'.join(f'## {i}. {h}\n\n{value}\n' for i,(h,value) in enumerate(zip(HEADINGS,bodies),1)))
    print({'live_criteria_met':live_met,'observations':[{k:v for k,v in o.items() if k not in ('required_scopes','optional_decisions')} for o in observations]})


if __name__=='__main__':main()
