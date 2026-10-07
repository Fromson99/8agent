"""Post-run reporting only; exact failed and successful turns retained."""
import hashlib
import importlib.util
import json
import sqlite3
import statistics
from common import ROOT,ADR,DESIGN,RUN,ARMS,read,put,sha

HEADINGS=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
QHEAD=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
def block(value):
    return '\n```json\n'+json.dumps(value,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'
def load_trace():
    path=ROOT/'06_TOOLS/EXPERIMENTS/adr_0619/finalize.py'
    spec=importlib.util.spec_from_file_location('inherited_exact_trace',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
def identity_set(values,coords):return {(coords[i]['doc_id'],coords[i]['node']) for i in values}
def objects(values):
    return sorted([{'doc_id':d,'node':n} for d,n in values],key=lambda row:json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')))
def ledger(m,cases,gold):
    trace=load_trace();coords=read(DESIGN/'source-coordinates.json');arms=[];metrics={};audits=[]
    for arm in ARMS:
        records=[];present_counts=[];hits=gold_total=before_total=after_total=0
        plan=m['design']['retrieval_stage_plan']['stages_by_arm'][arm]
        for case in cases:
            cid=case['case_id'];directory=RUN/cid/arm
            row=read(directory/'products.json')[-1]
            sets,audit,parts=trace.trace(directory,row,coords)
            audits.append({'case_id':cid,'arm':arm,**audit})
            canonical={k:identity_set(v,coords) for k,v in sets.items()}
            g=identity_set(set(gold[cid]['decisive_source_ids']),coords);stages=[];previous=set()
            for stage in plan:
                current=canonical[stage['stage_id']];added=current-previous;dropped=previous-current
                reason='not_in_recorded_'+stage['stage_id']
                record={**stage,'executed':True,'skip_reason':None,'before':objects(previous),'added':objects(added),
                    'discarded':objects(dropped),'after':objects(current),'before_count':len(previous),'added_count':len(added),
                    'discarded_count':len(dropped),'after_count':len(current),
                    'occurrence_counts':{'before':len(previous),'after':len(current),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
                    'discard_receipts':[{'identity':x,'reason':reason} for x in objects(dropped)],
                    'discard_reason_counts':{reason:len(dropped)} if dropped else {},
                    'gold_total':len(g),'gold_before':len(previous&g),'gold_added':len(added&g),'gold_discarded':len(dropped&g),'gold_after':len(current&g),
                    'golden_recall':len(current&g)/len(g),'gold_before_identities':objects(previous&g),
                    'gold_added_identities':objects(added&g),'gold_after_identities':objects(current&g),
                    'discarded_gold':[{'identity':x,'reason':reason} for x in objects(dropped&g)]}
                stages.append(record);previous=current
            rec={'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':cid,
                'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,
                'gold_visible_to_product':False,'gold_total':len(g),'gold_identities':objects(g),'stages':stages}
            records.append(rec);put(directory/'retrieval-stage-ledger.json',rec)
            present_counts.append(len(previous));hits+=len(previous&g);gold_total+=len(g)
            before_total+=len(canonical['discovered']);after_total+=len(canonical['selected'])
        met={'before_filter':before_total,'after_filter':after_total,'presented_total':sum(present_counts),
             'presented_mean':statistics.mean(present_counts),'presented_p50':statistics.median(present_counts),
             'presented_p95':max(present_counts),'golden_recall':hits/gold_total,'selectivity':statistics.mean(present_counts)/m['retrieval_accounting']['corpus_total']}
        metrics[arm]=met;arms.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in plan],'cases':records,'aggregate':met})
    value={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
        'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
        'runs':[{'run_id':'run-001','arms':arms}],'audit':{'final_bindings':audits,'scope':'First baseline versus last guided turn; exact stored-current route and native delivered sources. Secondary reuse traces separately retained. Aborted resource acquisition has zero delivered originals.'}}
    value['artifact_sha256']=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    put(RUN/'retrieval-stage-ledger.json',value)
    return metrics,audits

def main():
    m=read(ADR/'실험/manifest.json');cases=read(DESIGN/'inputs.json');gold=read(DESIGN/'gold.json')
    scores=read(RUN/'offline-judge/scores.json');scoremap={(s['case_id'],s['arm'],s['turn']):s for s in scores}
    metrics,audits=ledger(m,cases,gold)
    rows=[];all_usage=[];byarm={};errors=[]
    for arm in ARMS:
        correct=complete=0;latencies=[];calls=0
        for case in cases:
            cid=case['case_id'];directory=RUN/cid/arm;final='initial' if arm=='baseline' else 'guide2'
            s=scoremap[cid,arm,final];correct+=int(s['correct']);complete+=int(s['product_complete'])
            products=[]
            for path in sorted(directory.glob('turn-*.json')):
                row=read(path);latencies.append(row['seconds']);calls+=row['calls']
                products.append({k:row[k] for k in ('turn','http_status','seconds','calls','input','output','process_id')})
            for summary in directory.glob('summary-*.json'):all_usage+=read(summary)['usage']
            if not s['correct']:
                errors.append({'type':'other' if not s['product_complete'] else 'condition_exception',
                    'case_id':cid,'arm':arm,'detail':s['judges'] or 'Product did not complete; see exact request/error.'})
            row={'case_id':cid,'arm':arm,'correct':s['correct'],'product_complete':s['product_complete'],'turns':products}
            if arm=='guided':
                def get(label):
                    return next((x for x in products if x['turn']==label),None)
                confirm=get('confirm');auto=get('automatic-reuse');explicit=get('explicit-reuse');changed=get('changed-conditions')
                freshpath=RUN/cid/'baseline/turn-fresh.json';fresh=read(freshpath)
                before=read(directory/'wiki-before-restart.json') if (directory/'wiki-before-restart.json').exists() else {}
                after=read(directory/'wiki-after-restart.json') if (directory/'wiki-after-restart.json').exists() else {}
                def pages(view,kind):return view.get(kind,{}).get('output',{}).get('pages',[])
                eid=confirm['output'].get('experience_id') if confirm else None
                w1,w2=pages(after,'user_wiki'),pages(after,'legal_wiki')
                matching=bool(eid and w1 and w2 and w1[0].get('experience_id')==w2[0].get('experience_id')==eid and w1[0].get('judgment_refs')==w2[0].get('judgment_refs'))
                reuse_metrics={}
                for label,value in [('automatic',auto),('explicit',explicit)]:
                    reuse_metrics[label]={'status':value['output'].get('status') if value else 'BLOCKED',
                        'executed':value['output'].get('executed') if value else [],
                        'calls':value['calls'] if value else None,'seconds':value['seconds'] if value else None,
                        'latency_change_percent':(value['seconds']/fresh['seconds']-1)*100 if value else None,
                        'fresh_calls':fresh['calls'],'fresh_seconds':fresh['seconds'],
                        'quality_pass':scoremap.get((cid,'guided',label+'-reuse'),{}).get('correct',False),
                        'paired_fresh_quality_pass':scoremap.get((cid,'baseline','fresh'),{}).get('correct',False)}
                safe=bool(changed and changed['output'].get('status')=='READY' and 'ASSESS' in changed['output'].get('executed',[]))
                row['memory']={'confirmation_status':confirm['output'].get('status') if confirm else 'BLOCKED',
                    'experience_id':eid,'persisted_two_wikis':matching,'restart_process_different':bool(confirm and auto and confirm['process_id']!=auto['process_id']),
                    'reuse':reuse_metrics,'changed_condition_reinvestigated':safe}
            rows.append(row)
        byarm[arm]={'correct':correct,'total':len(cases),'product_completed':complete,'physical_calls_including_secondary':calls,
                     'p50_seconds':statistics.median(latencies),'p95_seconds':max(latencies),'latency_sample_count':len(latencies)}
    judge=read(RUN/'offline-judge/summary.json');all_usage+=judge['usage']
    costs={'recorded_model_calls':len(all_usage),'product_calls':sum(x['physical_calls_including_secondary'] for x in byarm.values()),
           'judge_calls':judge['attempts'],'cost_usd':sum(x.get('cost_usd') or 0 for x in all_usage),
           'input_tokens':sum(x.get('input_tokens') or 0 for x in all_usage),'output_tokens':sum(x.get('output_tokens') or 0 for x in all_usage),
           'scope':'Provider-returned usage only; no price estimate. Missing failed-call usage is unknown.'}
    outcomes={'guided_only_correct':0,'baseline_only_correct':0,'both_correct':0,'both_incorrect':0}
    for case in cases:
        cid=case['case_id'];a=scoremap[cid,'guided','guide2']['correct'];b=scoremap[cid,'baseline','initial']['correct']
        outcomes['both_correct' if a and b else 'guided_only_correct' if a else 'baseline_only_correct' if b else 'both_incorrect']+=1
    success=True
    for row in rows:
        if row['arm']!='guided':continue
        mem=row['memory'];success &= row['correct'] and mem['confirmation_status']=='STORED' and mem['persisted_two_wikis'] and mem['restart_process_different'] and mem['changed_condition_reinvestigated']
        for met in mem['reuse'].values():
            success &= met['status']=='REUSED' and met['quality_pass'] and met['paired_fresh_quality_pass'] and met['calls']<met['fresh_calls'] and met['latency_change_percent']<=-20
    result={'success_criteria_met':bool(success),'by_arm':byarm,'comparisons':outcomes,'case_results':rows,'costs':costs,
            'quality_scope':'Stored-source offline automated evaluation, not expert legal certification. Simple case baseline/guided differ in explicitly corrected facts; quality delta is not an identical-fact A/B effect.',
            'main_unchanged':True,'genos_measured':False}
    put(RUN/'result.json',result)
    m['results'].update(status='complete',by_arm=byarm,comparisons=[outcomes],judge_disagreements=sum(x.get('disagreement',False) for x in scores),usage=costs,
                        latency={a:{k:v for k,v in x.items() if k.startswith('p') or k.startswith('latency')} for a,x in byarm.items()},error_taxonomy=errors,success_criteria_met=bool(success))
    m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
    for key in metrics['guided']:
        m['retrieval_accounting'][key]={a:v[key] for a,v in metrics.items()}
    m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-stage-ledger.json')
    put(ADR/'실험/manifest.json',m)
    front=(ADR/'README.md').read_text().split('---',2)[1]
    table='| 사례 | 최초 | 가이드 최종 | 확정 | 재시작 후 두 위키 | 자동 재사용 | 명시 재사용 | 조건 변경 재조사 |\n|---|---|---|---|---|---|---|---|\n'
    for case in cases:
        cid=case['case_id'];r=next(x for x in rows if x['case_id']==cid and x['arm']=='guided');mem=r['memory']
        table+='| '+cid+' | '+str(scoremap[cid,'baseline','initial']['correct'])+' | '+str(r['correct'])+' | '+mem['confirmation_status']+' | '+str(mem['persisted_two_wikis'])+' | '+mem['reuse']['automatic']['status']+' | '+mem['reuse']['explicit']['status']+' | '+str(mem['changed_condition_reinvestigated'])+' |\n'
    values=['사전 전체 성공 기준 '+('충족' if success else '미충족')+'. Proposed, MAIN 불변.\n\n'+table,
        '사용자가 멀티턴으로 답을 찾고 확정 경험을 다음 사건에서 재사용하는 현재 작업 v6를 측정했다. 모의 계약 통과와 실제 데이터/모델 결과를 분리한다.',
        block({k:m['design'][k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria')}),block(m['design']),block(m['dataset']),
        table+block(byarm)+block(outcomes),block(errors),block(costs)+block({r['case_id']:r['memory'] for r in rows if r['arm']=='guided'}),
        '확정 저장, 실제 재사용 선택, 답변 정합성, 시간/호출 감소는 각각 독립 지표다. 확정 명령은 실험이 작성했고 법률 정확도 승인이 아니다.',
        '공개 2사례 단회 probe. 개인 신원은 연구 호스트의 명시 어댑터. GENOS/NFS 현장·내부 모델·독립 사례 일반화는 미측정. p95는 소표본 관찰값 최댓값으로 기록한다.',
        '제품 MAIN 포인터·원문/완료 세대·GENOS 리비전은 변경하지 않았다. 연구 산출물은 보존하며 새 결과에 따른 수정/재실험은 새 ADR에서 실행한다.',
        '.venv/bin/python 06_TOOLS/EXPERIMENTS/'+ADR.name.split('-')[1].lower().replace('063','adr_063')+'/run.py (원래 결과의 덮어쓰기 거부; 새 실행은 새 ADR 필요). 원시 요청/응답과 native SQLite journal, 데이터/코드 해시를 artifacts/manifest.json에서 확인한다.']
    (ADR/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' v6 멀티턴·경험 루프\n\n'+'\n\n'.join('## '+str(i)+'. '+h+'\n\n'+v for i,(h,v) in enumerate(zip(HEADINGS,values),1))+'\n')
    (ADR/'RESULT.md').write_text('# 현재 v6 멀티턴·경험 재사용 결과\n\n'+table+'\n'+block(result))
    for question in m['questions']:
        cid=question['case_id'];case=next(c for c in cases if c['case_id']==cid)
        raw=[];turns=[];sources=[]
        for arm in ARMS:
            directory=RUN/cid/arm
            for path in sorted(directory.glob('turn-*.json')):
                row=read(path);turns.append({k:v for k,v in row.items() if k!='db'})
                sources.append({'arm':arm,'turn':row['turn'],'checkpoint_nodes':row['db'].get('node',[]),'authority_sqlite':row['db'].get('authority_sqlite')})
            for path in sorted(directory.glob('provider-*/call-*/request.json')):
                raw.append({'arm':arm,'request_artifact':str(path.relative_to(ROOT)),'request':read(path),
                    'response':read(path.parent/'response.json') if (path.parent/'response.json').exists() else None})
        judge_raw=[]
        for p in sorted((RUN/'offline-judge/provider').glob('call-*/request.json')):
            if cid in p.parent.name:judge_raw.append({'request':read(p),'response':read(p.parent/'response.json')})
        values=[block({'case_id':cid,'run':'run-001','model':m['llm_policy']['required_model'],'scope':'Stored approved public corpus'}),block(case),
            block(gold[cid]),block(sources)+'\n### 회수·탈락 단계 원장 — run·arm별\n\n'+block([read(RUN/cid/a/'retrieval-stage-ledger.json') for a in ARMS]),block(raw), '모든 중간 실제 호출은 위 원문 및 해당 provider artifact에 있다. '+block(turns),
            block([s for s in scores if s['case_id']==cid])+block(judge_raw),block([r for r in rows if r['case_id']==cid])]
        path=ADR/'실험'/question['file'];path.write_text('# '+cid+'\n\n'+'\n\n'.join('## '+str(i)+'. '+h+'\n\n'+v for i,(h,v) in enumerate(zip(QHEAD,values),1))+'\n')
    (ADR/'실험/README.md').write_text('# 질문 인덱스\n\n'+table+'\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
    files=[p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and '/research-generation/' not in str(p)]
    files += [*(ROOT/'06_TOOLS/EXPERIMENTS'/('adr_'+m['adr_id'].split('-')[1])).glob('*.py'),ADR/'RESULT.md']
    files += [ROOT/p for p in read(DESIGN/'freeze.json') if '/revisions/' in p or p.endswith('/candidate.json')]
    put(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],
        'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Actual input/output, native journal, frozen code or reporting artifact','contains_raw_prompts_and_outputs':'provider' in str(p)} for p in sorted(set(files))]})
    print(json.dumps({'criteria_met':bool(success),'by_arm':byarm,'costs':costs},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
