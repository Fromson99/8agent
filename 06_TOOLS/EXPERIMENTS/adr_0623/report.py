"""Report functional navigation separately from failed legal/source choices."""
from pathlib import Path
from run import ROOT,ADR,RUN,read,put,sha
HEADINGS=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
def historical_audit():
    parent=ROOT/'04_EXPERIMENTS/ADR/ADR-0619-unified-cm-guidance-interrupted-continuation/artifacts/run-001/cm-051/guided'
    products=read(parent/'products.json');failed=next(p for p in products if p['turn']==2)
    judges=[]
    for folder in sorted((parent/'provider').glob('call-*')):
        req=read(folder/'request.json')
        if '현재 질문·현재 사실' not in req['messages'][0]['content']:continue
        import json
        v=json.loads(req['messages'][1]['content']);v=v.get('view',v)
        if v.get('source_stage')!='memory-judge-answer':continue
        resp=read(folder/'response.json');decision=json.loads(resp['choices'][0]['message']['content'])
        if decision.get('valid') is False:
            judges.append({'request':str((folder/'request.json').relative_to(ROOT)),'response':str((folder/'response.json').relative_to(ROOT)),
                'source_ids':[s['source_id'] for s in v['sources']], 'draft_claims':v['answer']['claims'], 'verdict':decision,
                'source_body_delivered':all(s.get('text') for s in v['sources'])})
    # Keep the provider phase spelling authoritative; failures may be assessment
    # or answer validation. Do not manufacture a successful final answer.
    if not judges:
        for folder in sorted((parent/'provider').glob('call-*')):
            req=read(folder/'request.json')
            if '현재 질문·현재 사실' not in req['messages'][0]['content']:continue
            import json
            v=json.loads(req['messages'][1]['content']);v=v.get('view',v)
            resp=read(folder/'response.json');decision=json.loads(resp['choices'][0]['message']['content'])
            if decision.get('valid') is False:
                judges.append({'request':str((folder/'request.json').relative_to(ROOT)),'response':str((folder/'response.json').relative_to(ROOT)),
                    'source_ids':[s['source_id'] for s in v['sources']], 'draft_claims':v.get('answer',v.get('assessment',{})).get('claims',[]), 'verdict':decision,
                    'source_body_delivered':all(s.get('text') for s in v['sources']),'source_stage':v.get('source_stage')})
    put(ADR/'artifacts/cm051-historical-answer-audit.json',{'source':'ADR0619 guided turn2','original_records_unchanged':True,'http_status':failed['http_status'],
        'http_error':failed['output'],'internal_judges':judges,'interpretation_of_log_only':True,'independent_legal_accuracy_certified':False})

def main():
    m=read(ADR/'실험/manifest.json');r=read(RUN/'result.json');historical_audit()
    cm3=read(RUN/'cm-003/compact-reference/selection.json')['reference_navigation']['batches'][0]
    needed=next(g for g in cm3['data']['groups'] if g['target']['source_id']=='article:1fa6eb7a10072f0d8f71bfc1')
    choice=next(d for d in cm3['decision']['decisions'] if d['id']==needed['id'])
    table='|사례|경로|선택 완료|필수 원문 조 선택|모델 호출|초|\n|---|---|---|---|---|---|\n'+'\n'.join(f'|{x["case_id"]}|{x["arm"]}|{x["source_selection_complete"]}|{x["required_roots_selected"]}/{x["required_roots_total"]}|{x["model_calls"]}|{x["seconds"]:.2f}|' for x in r['rows'])
    explanation='CM003: 23 verified edges became 10 groups. All10, including bylaw article23, were shown; omitted_groups=0. The model explicitly chose SKIP for article23: '+choice['reason']+' Required-root selection remains1/2.\n\nCM051: first id/scope pair was invalid. One fresh model redecision was attempted; it again contained an invalid pair, so the server rejected it. No relation navigation/final source set/final answer was produced. This is a closed-identifier failure, not evidence that the regulations were unavailable or legally unnecessary.'
    (ADR/'RESULT.md').write_text('# 법률 연결 묶음 탐색 — 구현·실제 판단 분리\n\n동일 legal_agent의 공통 선택 경로에 정·역참조 묶음, witness, 정확한 READ 옵션, FOLLOW/SKIP/DEFER 이유를 연결했다. 58개 동결 계약 통과. 기존 색인 재사용, MAIN·GENOS 미반영.\n\n'+table+'\n\n'+explanation+'\n\n기준은 ADR0622/batch-reference의 완료 원값을 재사용했다. 새 후보만 두 질문을 호출했다. 과거 호출 비용과 이번 비용은 분리한다. 실제 두 질문에서는 사전 개선 기준을 충족하지 못했다. 원문 선택·법률 정답률은 별개다.\n\n사용자가 말한 CM51의 규정2곳은 ADR0619 guided 2차 정정이다. 해당 기록에서는 두 원문이 판단·답변 초안에 실제로 들어갔고, 내부 검증이 제6조제3항의 대상 설명이 원문과 다르다고 거부했다(HTTP422). 검색 근거가 최종 단계에서 유실된 경우와 구분한다. [기존 실제 초안·검증 기록](artifacts/cm051-historical-answer-audit.json).\n\n[단계 원장·선택 원값](artifacts/run-001/result.json), [연결과 남은 작업](INTEGRATION.md).\n')
    (ADR/'INTEGRATION.md').write_text('# 공통 legal_agent 연결\n\nsource_recall 두 branch의 eager 참조 확장을 중단하고 unit_selection→unit_relations에서 선택한 범위만 READ한다. 구조 MATCH에도 똑같은 연결 메뉴를 제공한다. 16묶음/배치, 최대2회 탐색, 한번의 잘못된 단위 선택 재판단, 입력·READ 예산을 공통으로 지킨다. 빠진 연결은 요약·개수를 남기고 pending이다. 같은 출발/대상/방향의 참조 witness들을 묶는다. 미해결·범위 밖·해시가 틀린 연결은 실행하지 않는다.\n\nmemory_rag와 bounded_source_session도 이 경로를 호출한다. 참조 READ의 실제 근거는 SELECT selected_originals/evidence로 ASSESS/COMPOSE, 확정 경험, 두 위키, 다른 대화의 재사용까지 소비된다. 원 READ checkpoint와 잘못된 과거 기록을 덮어쓰지 않는다. 이 연결은 합성 계약으로 확인했으며 실제 두 질문의 법률 답변 정확도는 검증하지 않았다.\n\n남은 문제: CM3의 필요한 연결을 건너뛴 판단, CM51 id/scope 출력 실패. 후속 실험 후보는 READ 옵션 하나가 단위와 범위를 함께 가리키는 닫힌 action ID, 연결 미조사 결정에 대한 근거 검토, 독립 holdout이다. 현재 후보는 Proposed이며 MAIN 승격 대상이 아니다. 별도 작업 트리의 native 최소단위 fulltext builder와의 결합도 검증 전이다.\n\nADR0622의 final metadata validation에는 잘못된 상대 artifact 경로와 미사용 scaffold 질문 파일이 남았다. 완료 부모 manifest/원값을 덮어쓰지 않고 이 ADR에서 정확한 root-relative 경로와 baseline 원값 hash를 결속했다. 부모 전체 인증을 주장하지 않는다. 활성 generation37을 유지하므로 rollback은 기존 활성 릴리스다. GENOS 배포·색인 구축은 하지 않았다.\n')
    front=(ADR/'README.md').read_text().split('---',2)[1]
    bodies=['Proposed. Same legal_agent batch navigation implemented; 58 contracts pass. CM3 needed menu now visible but skipped; CM51 invalid pair remains. [결과](RESULT.md).',
        'Parent menu lost the final group under24000 characters; selector exposed an independently generated id/scope pair and rejected mismatches.',
        m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
        'Immutable ADR0622 baseline reuse; fresh candidate CM003 then CM051. Two known public cases, closed schemas, at most5 product calls; one redecision limit. No answer judge.',
        'Exact pinned parent,145 public docs/store, unchanged223127-unit FTS index. Qwen3.8 Parasail FP8 reasoning none no fallback. Context80000 and menu24000 unchanged. No GENOS access.',
        table,explanation,
        str(m['results']['latency'])+'\n\nNew candidate usage is recorded separately from inherited baseline below. Timing includes local setup/recall/selection; two samples only.',
        'Menu delivery, actual traversal choice, legal answer quality and reused experience accuracy are separate. CM3 is now a recorded SKIP, not a hidden or absent connection.',
        'Known cases/in_sample; synthetic consumer confirmation only; no final live answer. Inherited baseline is not a fresh randomized comparison. Parent metadata validation limitations retained.',
        'Proposed, decision_eligible=false; active generation37/store/index unchanged. Preserve outcomes and limit any outcome-driven follow-up to a new ADR.',
        '.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0623/contracts.py --frozen. Completed model calls must not be replayed.']
    (ADR/'README.md').write_text('---'+front+'---\n\n# ADR0623 연결 메뉴와 제한적 재판단\n\n'+'\n'.join(f'## {i}. {h}\n\n{v}\n' for i,(h,v) in enumerate(zip(HEADINGS,bodies),1)))
    new_usage=[];inherited_usage=[]
    for cid in ('cm-003','cm-051'):
        new_usage+=read(RUN/cid/'compact-reference/result.json')['usage'];inherited_usage+=read(RUN/cid/'baseline/result.json')['usage']
    m['results']['usage'].update(new_product_calls=len(new_usage),new_product_usage=new_usage,new_cost_usd=sum(v.get('cost_usd',0) for v in new_usage),
        inherited_product_calls=len(inherited_usage),inherited_cost_usd=sum(v.get('cost_usd',0) for v in inherited_usage),inherited_calls_replayed=False)
    m['design']['primary_metric_result']={'functional_contracts_passed':58,'cm003_all_reference_groups_presented':len(cm3['data']['groups'])==10 and cm3['data']['omitted_groups']==0,'cm003_needed_reference_decision':choice,'live_criteria_met':False,'cm051_redecision_did_not_make_valid_choices':True}
    put(ADR/'실험/manifest.json',m)
    r['usage']=m['results']['usage'];put(RUN/'result.json',r);m['runs'][0]['sha256']=sha(RUN/'result.json');put(ADR/'실험/manifest.json',m)
if __name__=='__main__':main()
