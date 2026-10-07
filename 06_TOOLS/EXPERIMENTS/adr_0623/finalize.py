"""Offline accounting only. Gold is joined after product selection finishes."""
import hashlib,json,statistics,subprocess
from pathlib import Path
from run import ROOT,ADR,DESIGN,RUN,read,put,sha

ARMS=['baseline','compact-reference']
HEADINGS=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'

def main():
    m=read(ADR/'실험/manifest.json');cases=read(DESIGN/'inputs.json');gold=read(DESIGN/'gold.json');coords=read(DESIGN/'source-coordinates.json')
    rows=[];arms=[];metrics={};usage=[]
    def identities(values):
        rows=[{'doc_id':d,'node':n} for d,n in {(coords[v]['doc_id'],coords[v]['node']) for v in values if v in coords}]
        return sorted(rows,key=lambda r:json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    for arm in ARMS:
        ledcases=[];counts=[];scores=[];latencies=[];calls=0;hits=0;before_total=0;after_total=0
        for c in cases:
            cid=c['case_id'];d=RUN/cid/arm;r=read(d/'result.json');s=read(d/'selection.json') if (d/'selection.json').exists() else {}
            rec=read(d/'recall.json') if (d/'recall.json').exists() else {}
            corpus=set(r.get('corpus_ids',coords));selected=set(r.get('selected_ids',[]));g=set(gold[cid]['decisive_source_ids'])
            body_ids=set()
            for e in s.get('actual_selector_excerpts',[]):
                for card in e['cards']:
                    if card.get('source_id') and card.get('text'):body_ids.add(card['source_id'])
                    if card.get('original',{}).get('text') or card.get('excerpts'):
                        body_ids.add(s['label_to_source'][card['id']])
            sets={'corpus':corpus,'recall':set(rec.get('discovered',[])),
                'read':set(rec.get('selection_complete',rec.get('read_complete',[]))),
                'initial_selection':set(s.get('first_ids',[])),
                'relations':set(s.get('first_ids',[]))|set(s.get('reference_navigation',{}).get('seen_target_ids',[])),
                'selection':selected,'present':selected&body_ids}
            stages=[];previous=set()
            for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
                sid=plan['stage_id'];current=sets[sid];added=current-previous;dropped=previous-current
                reason={'corpus':'outside_public_article_scope','recall':'run_aborted_without_completed_discovery_receipt' if r['error'] and not rec else 'not_recalled','read':'not_complete_in_requested_extent',
                    'initial_selection':'invalid_unit_choice_aborted_selection' if r['error'] else 'not_selected_in_first_unit_decision','relations':'not_offered_as_verified_reference','selection':'run_aborted_without_completed_selection' if r['error'] else 'not_selected_for_question','present':'selected_source_body_not_delivered_to_selector'}[sid]
                row={**plan,'executed':True,'skip_reason':None,
                    **{k:identities(v) for k,v in [('before',previous),('added',added),('discarded',dropped),('after',current)]},
                    **{k+'_count':len(identities(v)) for k,v in [('before',previous),('added',added),('discarded',dropped),('after',current)]},
                    'occurrence_counts':{'before':len(previous),'after':len(current),'canonical_collapsed_before':len(previous)-len(identities(previous)),'canonical_collapsed_after':len(current)-len(identities(current))},
                    'discard_receipts':[{'identity':v,'reason':reason} for v in identities(dropped)],
                    'discard_reason_counts':{reason:len(identities(dropped))} if identities(dropped) else {},
                    'gold_total':len(identities(g)),'gold_before':len(identities(previous&g)),'gold_added':len(identities(added&g)),
                    'gold_discarded':len(identities(dropped&g)),'gold_after':len(identities(current&g)),
                    'golden_recall':len(identities(current&g))/len(identities(g)),
                    'gold_before_identities':identities(previous&g),'gold_added_identities':identities(added&g),'gold_after_identities':identities(current&g),
                    'discarded_gold':[{'identity':v,'reason':reason} for v in identities(dropped&g)]}
                stages.append(row);previous=current
            ledcases.append({'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':cid,
                'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
                'gold_total':len(identities(g)),'gold_identities':identities(g),'stages':stages,
                'failed_run':r['error'],'missing_stage_receipt_is_not_recall_quality':bool(r['error'] and not rec)})
            counts.append(len(identities(previous)));hits+=len(identities(previous&g));before_total+=len(identities(sets['recall']));after_total+=len(identities(selected))
            success=not r['error'] and bool(selected) and not r.get('needs_search')
            scores.append(success);latencies.append(r['seconds']);calls+=r['model_calls'];usage+=r['usage']
            rows.append({'case_id':cid,'arm':arm,'source_selection_complete':success,'required_roots_selected':len(selected&g),
                'required_roots_total':len(g),'required_root_selection_complete':g<=selected,
                'required_roots_body_presented':len(previous&g),'selected_articles':len(selected),
                'chosen_unit_scopes':r.get('read_scopes',[]),'source_chars':r.get('source_chars'),
                'model_calls':r['model_calls'],'seconds':r['seconds'],'needs_search':r.get('needs_search'),'error':r['error'],
                'reference_rounds':sum(b.get('model_called',False) for b in s.get('reference_navigation',{}).get('batches',[])),
                'reference_navigation_pending':s.get('reference_navigation',{}).get('pending'),
                'legal_answer_accuracy':None})
        met={'before_filter':before_total,'after_filter':after_total,'presented_total':sum(counts),'presented_mean':statistics.mean(counts),
            'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':hits/4,'selectivity':statistics.mean(counts)/len(coords)}
        metrics[arm]=met;arms.append({'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in stages],'cases':ledcases,'aggregate':met})
        m['results']['by_arm'][arm]={'correct':sum(scores),'total':len(scores),'metric':'source_selection_completion_only; legal-answer correctness not measured',
            'required_roots_selected':[x['required_roots_selected'] for x in rows if x['arm']==arm],'model_calls':calls}
        m['results']['latency'][arm]={'p50_seconds':statistics.median(latencies),'p95_seconds':max(latencies),'scope':'resource setup + source recall + selection; no final answer; shared build host'}
    ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
        'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
        'runs':[{'run_id':'run-001','arms':arms}],
        'audit':{'present_meaning':'Selected roots whose verbatim body appeared in selector input; does not assert entire requested expansion was model-read. No ASSESS or final legal answer generated.',
            'unit_occurrences':'Unit hits, selected scopes and exact evidence are separately retained in recall/selection artifacts; canonical article roots remain accounting identity.',
            'known_cases':True,'unit_index':'../ADR-0620-unit-fulltext-adaptive-read/artifacts/run-001/unit-index/manifest.json'}}
    ledger['artifact_sha256']=hashlib.sha256(json.dumps(ledger,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();put(RUN/'stage-ledger.json',ledger)
    m['retrieval_accounting'].update(corpus_total=len(coords),**metrics['compact-reference'])
    for key in ('presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):
        m['retrieval_accounting'][key]={arm:metrics[arm][key] for arm in ARMS}
    m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'stage-ledger.json')
    comparisons=[]
    paired=[(next(x for x in rows if x['case_id']==c['case_id'] and x['arm']=='baseline'),next(x for x in rows if x['case_id']==c['case_id'] and x['arm']=='compact-reference')) for c in cases]
    comparisons=[{'baseline':'baseline','candidate':'compact-reference','metric':'required_root_selection_complete_only; not answer accuracy',
        'candidate_only':sum(not a['required_root_selection_complete'] and b['required_root_selection_complete'] for a,b in paired),
        'baseline_only_regression':sum(a['required_root_selection_complete'] and not b['required_root_selection_complete'] for a,b in paired),
        'both_complete':sum(a['required_root_selection_complete'] and b['required_root_selection_complete'] for a,b in paired),
        'neither_complete':sum(not a['required_root_selection_complete'] and not b['required_root_selection_complete'] for a,b in paired),
        'paired_delta':sum(int(b['required_root_selection_complete'])-int(a['required_root_selection_complete']) for a,b in paired)/len(paired)}]
    m['results'].update(status='complete',judge_disagreements=0,comparisons=comparisons,
        usage={'model_calls':sum(x['model_calls'] for x in rows),'raw_usage':usage,'no_offline_llm_judge':True},
        error_taxonomy=[{'case_id':x['case_id'],'arm':x['arm'],'type':x['error']['type'] if x['error'] else 'governing_rule_selection','reason':x['error']['message'] if x['error'] else 'required source roots not all selected or additional investigation pending'} for x in rows if x['error'] or not x['required_root_selection_complete'] or x['needs_search']])
    result={'rows':rows,'contracts':read(ADR/'artifacts/contract-results.json'),'index':read(ROOT/m['design']['index_reuse']['manifest']),
        'metrics':metrics,'usage':m['results']['usage'],'decision':'Proposed','main_wiring':'unchanged','legal_accuracy_measured':False}
    put(RUN/'result.json',result)
    m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
    qrefs=[]
    qhead=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
    for i,c in enumerate(cases,1):
        p=ADR/'실험'/f'질문-{i:03d}-{c["case_id"]}.md';texts=[]
        for arm in ARMS:
            d=RUN/c['case_id']/arm
            for inp in sorted(d.glob('model-input-*.json')):
                out=d/inp.name.replace('input','output');texts.append(block({'arm':arm,'request':read(inp),'output':read(out) if out.exists() else None}))
        values=[block({'case_id':c['case_id'],'run_id':'run-001','arms':ARMS,'model':m['llm_policy']['required_model']}),c['question'],
            'Gold source coordinates are joined only offline. No final legal-answer score.'+block(gold[c['case_id']]),
            '\n'.join(f'{arm}: [raw journal](../artifacts/run-001/{c["case_id"]}/{arm}/journal.sqlite), [dedicated stage ledger](../artifacts/run-001/stage-ledger.json).'+block(read(RUN/c['case_id']/arm/'recall.json') if (RUN/c['case_id']/arm/'recall.json').exists() else {'completed_recall_receipt':False,'error':read(RUN/c['case_id']/arm/'result.json')['error']}) for arm in ARMS),
            '\n'.join(texts),'Only selector product calls; no router/compiler/verifier/repair experiment calls.',
            'No LLM judge. Source identity/completion and exact stage sets computed offline; full legal answers not generated.',
            block([x for x in rows if x['case_id']==c['case_id']])]
        values[3]+='\n### 회수·탈락 단계 원장 — run·arm별\n\n'+block([{'arm_id':arm['arm_id'],'case':case} for arm in ledger['runs'][0]['arms'] for case in arm['cases'] if case['case_id']==c['case_id']])
        p.write_text('# '+c['case_id']+'\n'+'\n'.join('## '+str(i)+'. '+h+'\n\n'+v+'\n' for i,(h,v) in enumerate(zip(qhead,values),1)))
        qrefs.append({'number':i,'case_id':c['case_id'],'file':p.name,'sha256':sha(p)})
    m['questions']=qrefs;put(ADR/'실험/manifest.json',m)
    (ADR/'실험/README.md').write_text('# 질문 인덱스\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in qrefs)+'\n\n원문 선택·읽기 계약 검증이며 최종 법률 정답률 실험은 아니다.\n')
    summary='\n'.join(f'|{x["case_id"]}|{x["arm"]}|{x["source_selection_complete"]}|{x["required_roots_selected"]}/{x["required_roots_total"]}|{x["selected_articles"]}|{x["model_calls"]}|' for x in rows)
    (ADR/'RESULT.md').write_text('# 최소 단위 fulltext와 펼치기 선택\n\nlegal_agent는 유지한다. 저장된 구조 마디의 직접 원문만 검색하며, 첫 선택에 실제 원문과 펼칠 범위를 함께 제공한다.\n\n'+
        '최소 단위·경계 계약 22개와 통합 v6 회귀 18개를 검사했다. 재사용한 공개 색인은 '+str(result['index']['counts']['unit'])+'개 직접 원문 단위다. 원문·구조화·기존 색인은 변경하지 않았다.\n\n'+
        '|사례|경로|선택 완료|필수 조 선택|선택 조 수|모델 호출|\n|---|---|---|---|---|---|\n'+summary+'\n\n'+
        'ADR0620의 장·절 canonical source와 stored subtree 차이를 보완했다. 범위를 넘는 펼치기는 선택지에서 제외하고 이유를 표시한다. 직접 원문은 유지한다. 구조 마디 없는 원문은 canonical source의 원문만 읽는다. 실제 성공·실패는 위 표와 원값을 따른다.\n\n'+
        '두 알려진 질문의 검색·선택 probe다. 정답률 개선, 전체 질의 시간 절감, GENOS 성능은 검증하지 않았다. CM3의 명시 좌표는 구조 우선 경로를 유지한다.\n\n'+
        '[선택 원값·단계 원장](artifacts/run-001/result.json), [미반영 후보 연결 계획](INTEGRATION.md). 후보 코드만 동결했으며 MAIN·GENOS는 전환하지 않았다.\n')
    front=(ADR/'README.md').read_text().split('---',2)[1]
    front=front.replace('status: Proposed','status: Proposed')
    bodies=['최소 단위 원문과 닫힌 펼치기 후보 검사를 수행했다. MAIN unchanged. [결과](RESULT.md).','Article FTS and title-only first selection; stored fine hierarchy unused.',
        block(m['design']),'Fresh paired source-selection probes with two known public questions; baseline is exact frozen ADR0621 parent; gold joined only offline.',
        block(m['dataset']),summary,'Required-root availability and pending requests remain separately recorded; no answer-quality score.',
        block({'index':result['index'],'metrics':metrics,'usage':m['results']['usage'],'latency':m['results']['latency']}),
        'Exact own originals remain readable across navigation grouping. Cross-source expansion is unavailable. Required-root selection and legal-answer quality remain separate.',
        'Known two-case probe, synthetic recovery, public corpus only; GENOS unavailable; resource preflight errors preserved, no products replayed.',
        'Proposed, decision_eligible=false, unchanged MAIN generation37. Exact candidate/index hashes and rollback to existing release remain preserved.',
        'Frozen runner: .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0623/run.py. Completed model calls must not be replayed in this ADR.']
    (ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0623\n\n'+'\n'.join(f'## {i}. {h}\n\n{v}\n' for i,(h,v) in enumerate(zip(HEADINGS,bodies),1)))

if __name__=='__main__':main()
