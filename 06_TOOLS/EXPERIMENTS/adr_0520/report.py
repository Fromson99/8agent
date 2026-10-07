"""Offline descriptive report. Gold is loaded only after every frozen replay is stored."""
import gc,hashlib,importlib.util,json,math,sqlite3,statistics,sys
from pathlib import Path
from bootstrap import R,A,C
P=R/'04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
def read(p):return json.loads(p.read_text())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while c:=f.read(8388608):h.update(c)
    return h.hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n')
def main():
    results=read(A/'artifacts/run-001/results.json');m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json')
    assert set(results['cases'])==set(m['runs'][0]['case_ids'])
    gold={v['case_id']:v for v in read(A/'gold-cases.json')['cases']}
    spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    db=sqlite3.connect('file:'+str(A/'artifacts/reference-rebuild.sqlite')+'?mode=ro',uri=True)
    sources={sid:json.loads(raw) for sid,raw in db.execute('SELECT id,json FROM source')};db.close()
    coords={sid:{'doc_id':s['document_id'],'node':int(s['unit_id'])} for sid,s in sources.items() if str(s.get('unit_id','')).isdigit()}
    corpus=len({h.key(coords[s]) for s in coords if sources[s]['document_id'] in prod['public_scope_document_ids']})
    arms={arm:[] for arm in ('baseline','exploration')};summary=[];case_rows={}
    for cid,path in results['cases'].items():
        v=read(R/path);old=read(P/'artifacts/run-001'/cid/'result.json');root_ids=[r['extent']['source_id'] for r in v['roots']]
        g=h.ordered(coords[sid] for sid in gold[cid]['decisive_source_ids']);rows=[]
        # corpus stage enumerates the frozen retrieved candidate pool. corpus_total records all selected source roots separately.
        pools={'baseline':{'corpus':old['discovered'],'roots':old['selected_for_read'],'reference_walk':old['read_complete'],'prepared':old['prepared_complete']},
               'exploration':{'corpus':old['discovered'],'roots':root_ids,'reference_walk':v['source_ids'],'prepared':v['source_ids']}}
        for arm,pool in pools.items():
            prev=[];stages=[]
            for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
                after=h.ordered(coords[s] for s in pool[plan['stage_id']] if s in coords);ak={h.key(x) for x in after};bk={h.key(x) for x in prev}
                dropped=[x for x in prev if h.key(x) not in ak]
                why='not_selected_in_historical_input' if arm=='baseline' else 'not_an_independent_selected_discovery_root'
                stage=h.stage(plan['stage_id'],plan['kind'],plan['parent_stage_ids'],prev,[x for x in after if h.key(x) not in bk],dropped,{h.key(x):why for x in dropped},g)
                stages.append(stage);prev=stage['after']
            record={'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':stages}
            arms[arm].append(record)
            missing=sorted(set(gold[cid]['decisive_source_ids'])-set(pool['prepared']))
            row={'case_id':cid,'arm':arm,'source_count':len(pool['prepared']),'root_count':len(pool['roots']),
                 'gold_total':len(g),'gold_obtained':stages[-1]['gold_after'],'missing_source_ids':missing,
                 'count_by_stage':{s['stage_id']:s['after_count'] for s in stages},
                 'gold_by_stage':{s['stage_id']:s['gold_after'] for s in stages},
                 'seconds':old['seconds'] if arm=='baseline' else v['seconds'],
                 'status':'HISTORICAL' if arm=='baseline' else v['status'],
                 'pending_states':0 if arm=='baseline' else len(v['pending']),
                 'gap_receipts':0 if arm=='baseline' else len(v['gaps']),
                 'stored_source_chars':old['source_chars'] if arm=='baseline' else v['source_chars']}
            rows.append(row);summary.append(row)
        case_rows[cid]=rows
        print('graded',cid,flush=True)
        del v,old;gc.collect()
    ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,
        'runs':[{'run_id':'run-001','arms':[{'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':{'presented_total':sum(c['stages'][-1]['after_count'] for c in records),'gold_after':sum(c['stages'][-1]['gold_after'] for c in records),'gold_total':sum(c['gold_total'] for c in records)}} for arm,records in arms.items()]}],
        'audit':{'corpus_total':corpus,'corpus_stage':'Frozen historical discovered candidate pool, not enumeration of entire selected corpus.','prepared':'Full original source bytes saved locally; graph traversal extents remain narrower. Neither arm supplies new model inputs.','comparison_limit':'Historical acquisition vs bounded graph reachability from frozen independent roots; no equivalent end-to-end relevance or answer comparison.','latest_user_policy':'Recursive incoming/outgoing at every exact extent; DB-external hops require discovery or explicit-reference gap provenance.'}}
    ledger['artifact_sha256']=h._canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
    totals={}
    for arm in arms:
        rows=[r for r in summary if r['arm']==arm];counts=sorted(r['source_count'] for r in rows);g=sum(r['gold_total'] for r in rows);got=sum(r['gold_obtained'] for r in rows)
        totals[arm]={'cases':len(rows),'gold_obtained':got,'gold_total':g,'source_count_mean':statistics.mean(counts),'source_count_p95':counts[math.ceil(.95*len(counts))-1],'partial_cases':sum(r['status']=='PARTIAL' for r in rows),'graph_seconds_mean':statistics.mean(r['seconds'] for r in rows),'golden_recall':got/g,'source_chars_mean':statistics.mean(r['stored_source_chars'] for r in rows)}
        metrics={'before_filter':sum(r['count_by_stage']['corpus'] for r in rows),'after_filter':sum(r['source_count'] for r in rows),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':counts[math.ceil(.95*len(counts))-1],'golden_recall':got/g,'selectivity':statistics.mean(counts)/corpus}
        for k,val in metrics.items():
            if not isinstance(m['retrieval_accounting'].get(k),dict):
                m['retrieval_accounting'][k]={}
            m['retrieval_accounting'][k][arm]=val
    m['retrieval_accounting']['corpus_total']=corpus;m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'artifacts/retrieval-stage-ledger.json')
    outcome={'totals':totals,'by_case':summary,'model_calls':0,'mandatory_90_of_90':False,'semantic_answer_quality_measured':False,'main_unchanged':True,
        'decision':'Deferred: contract candidate and DB rebuild verified, but large frozen root sets still expand broadly; no completeness or efficiency certification.',
        'contract_tests':12,'v5_regression_tests':53,'compatible_provision_tests':13,'superseded_provision_tests':2,'limitations':['No live root selection or corrective search tested.','No automatic approval of inferred missing edges.','Scope-preserving graph reachability is not legal relevance.','Source-level recall does not certify the decisive provision was in traversal scope; original full text is only stored.','Frozen runner pins changed modules and records source inputs; shared serving dependencies are working-tree imports, not a deployable release.']}
    write(A/'artifacts/summary.json',outcome)
    m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/results.json'))
    m['results'].update(status='complete',by_arm=totals,comparisons=[{'baseline':'baseline','candidate':'exploration','interpretation':outcome['decision']}],judge_disagreements=None,usage={'physical_model_calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},latency={k:v['graph_seconds_mean'] for k,v in totals.items()},error_taxonomy=['bounded_frontier_incomplete','explicit_reference_data_gap','excessive_independent_starting_points'])
    write(A/'실험/manifest.json',m)
    headings=[x for x in (A/'README.md').read_text().splitlines() if x.startswith('## ')]
    bodies=[outcome['decision']+' 운영 release와 원본 DB는 변경하지 않았다.',
        '조 ID만 따라가면 제10호→제39호 연결이 섞인다. 일부 세부 좌표 실패가 확정 간선으로 남고 부칙 제목이 본문 참조로 생성됐다.',
        '90/90은 필수 기준이 아니다. 원문·좌표·방향·이동 이유를 보존한다. 연결로 도달한 하위에서도 양방향 탐색한다. 사전 기준과 사용자 정정은 artifacts/design-freeze*.json 및 user-correction-v2.json에 보존했다.',
        'baseline: ADR0513 완료 회수 기록. exploration: 같은 검색 기록에서 독립적으로 발견·선택된 시작점만 추출해 새 참조 DB로 탐색한다. 두 arm의 실행 방식이 다르므로 품질 우열 비교가 아니다.',
        '공개 145개 문서 범위, 원문·구조는 선택 세대 고정. 코드 rev-002. 새 모델 호출 0회. 원시 경로와 입력 hash는 replay-freeze.json.',
        '```json\n'+json.dumps(totals,ensure_ascii=False,indent=2)+'\n```',
        '질문별 입력·미회수 근거·미방문 경로는 실험 파일 및 원시 result.json에 보존했다. PARTIAL은 부재 확인이나 탐색 완료가 아니다.',
        '실제 모델 제시 0건. prepared는 로컬 원문 묶음이다. 규모·지연·단계별 회수는 artifacts/summary.json, retrieval-stage-ledger.json. 수치만으로 관계 정확도나 답변 성능을 주장하지 않는다.',
        '범위 보존·누락 분리로 잘못된 확장 유형을 차단해도 다수 시작점에서 연결된 그래프는 크다. 근거 없이 역참조 깊이를 잘라 문제를 숨기지 않는다. 시작점의 질문 관련성, 반복 방문의 계산·저장 중복을 후속으로 분리 검증해야 한다.',
        '\n'.join('- '+s for s in outcome['limitations']),
        '보류. MAIN 승격/활성 DB 포인터 변경/GENOS 배포 없음. 후보를 실행하지 않으면 기존 활성 경로를 유지한다. 실제 DB 재구축 반영은 전체 navigation generation 생성·검증과 소비자 계약 이행이 필요하다.',
        '```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0520/bootstrap.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0520/replay.py prepare\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0520/replay.py rebuild\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0520/replay.py run\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0520/report.py\n```\n완료 산출물은 덮어쓰지 않는다. 재실행은 새 ADR/경로에서 수행한다.']
    original=(A/'README.md').read_text();front=original.split('---',2)[1]
    (A/'README.md').write_text('---'+front+'---\n\n# ADR-0520: 명시 근거 기반 관계 탐색\n\n'+'\n\n'.join(hd+'\n\n'+body for hd,body in zip(headings,bodies))+'\n')
    prod_cases={c['case_id']:c for c in prod['cases']};index=[]
    for q in m['questions']:
        cid=q['case_id'];path=A/'실험'/q['file'];template=path.read_text();heads=[s for s in template.splitlines() if s.startswith('## ')];p=prod_cases[cid];rows=case_rows[cid]
        raw=results['cases'][cid];ref='원시 산출물: '+raw+'; 기준: '+str((P/'artifacts/run-001'/cid/'result.json').relative_to(R))
        blocks=[json.dumps({'experiment':m['experiment_id'],'case_id':cid,'run':'run-001','origin':'exact','models_called':[]},ensure_ascii=False),
            '```json\n'+json.dumps(p,ensure_ascii=False,indent=2)+'\n```',
            '```json\n'+json.dumps(gold[cid],ensure_ascii=False,indent=2)+'\n```\n제품 실행 완료 후 grader에서만 사용했다.',
            ref+'\n\n단계 원장: artifacts/retrieval-stage-ledger.json 의 해당 case_id. 전체 원문과 탐색 범위·참조 근거·미방문 작업을 원시 기록에 보존한다.\n\n```json\n'+json.dumps(rows,ensure_ascii=False,indent=2)+'\n```',
            '새 제품 모델 호출 없음. system/user/schema/provider response 모두 해당 없음. 과거 검색 계획을 입력으로 재사용했으며 원시 입력 hash를 동결했다.',
            '```json\n[]\n```\nLLM router/compiler/verifier/repair 호출 없음.',
            '모델 채점 없음. 원문 조 좌표 집합과 동결 gold 좌표의 결정적 대조. 답변 정확도는 측정하지 않았다.',
            '사례 답변 정오 미판정. 새 규칙의 확보 원문 수 '+str(rows[1]['source_count'])+', gold '+str(rows[1]['gold_obtained'])+'/'+str(rows[1]['gold_total'])+', 탐색 '+rows[1]['status']+'. 미확보 원인은 시작점·범위·DB·예산을 추가 분해해야 하며 gold 복구를 위해 경로를 추가하지 않는다.']
        path.write_text('# 질문 '+str(q['number'])+' — '+cid+'\n\n'+'\n\n'.join(hd+'\n\n'+b for hd,b in zip(heads,blocks))+'\n')
        index.append(f"| {cid} | {rows[1]['status']} | {rows[1]['gold_obtained']}/{rows[1]['gold_total']} | [{q['file']}]({q['file']}) |")
    (A/'실험/README.md').write_text('# ADR-0520 실험 기록\n\n새 모델 호출 없음. 과거 시작점 고정 재생이며 답변 품질 인증이 아니다. 두 arm의 확보 원문 수와 탐색 상태를 기록했다.\n\n| case | 탐색 | 확보 gold | 원문 기록 |\n|---|---|---|---|\n'+'\n'.join(index)+'\n')
    print(json.dumps(totals,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
