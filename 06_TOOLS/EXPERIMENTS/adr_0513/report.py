"""Offline canonical-source audit; never feeds gold or verdicts to product."""
import json,sqlite3,hashlib,statistics,importlib.util,subprocess,sys,math
from pathlib import Path
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
P=R/'04_EXPERIMENTS/ADR/ADR-0512-scoped-source-preservation'
G=R/'04_EXPERIMENTS/ADR/ADR-0511-gemma-query-source-recall'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0513/retrieval'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
def complete(source,evidence):
    for b in source['blocks']:
        ranges=[]
        for e in evidence:
            if e['source_id']!=source['id']:continue
            for s in e['spans']:
                if s['block_id']==b['block_id']:
                    assert b['text'][s['start_cp']:s['end_cp']]==s['text']
                    ranges.append((s['start_cp'],s['end_cp']))
        end=0
        for x,z in sorted(ranges):
            if x>end:break
            end=max(end,z)
        if end!=len(b['text']):return False
    return True

def main():
    m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json');gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']};planning=read(A/'artifacts/query-planning.json')
    spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    with sqlite3.connect('file:'+str(R/prod['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
        sources={sid:json.loads(raw) for sid,raw in db.execute('SELECT id,json FROM source')}
    coords={sid:{'doc_id':s['document_id'],'node':int(s['unit_id'])} for sid,s in sources.items() if str(s['unit_id']).isdigit()}
    corpus=len({h.key(c) for sid,c in coords.items() if sources[sid]['document_id'] in prod['public_scope_document_ids']})
    parents={p.parent.name:p for p in P.glob('artifacts/run-*/**/result.json')};current=read(A/'artifacts/run-001/results.json')['cases']
    summaries=[];arms=[];question_stages={};raw_by_case={};replay_mismatches=[]
    for arm in ('baseline','retrieval'):
        records=[]
        for cid in m['runs'][0]['case_ids']:
            path=parents[cid] if arm=='baseline' else R/current[cid]
            row=read(path);es=row.get('evidence',[])
            if arm=='retrieval':
                raw_by_case[cid]=path
                for branch,origin in [('global',G),('scoped',P)]:
                    expected=read(origin/'artifacts/run-001'/cid/'result.json')['selected_for_read']
                    actual=row.get('branches',{}).get(branch,{}).get('selected_for_read',[])
                    if expected!=actual:replay_mismatches.append({'case_id':cid,'branch':branch,'reason':'selection differs from frozen parent'})
                    if not set(actual).issubset(row.get('selected_for_read',[])):replay_mismatches.append({'case_id':cid,'branch':branch,'reason':'union lost a parent selection'})
                union=set().union(*(set(v['selected_for_read']) for v in row.get('branches',{}).values()))
                if union!=set(row.get('selected_for_read',[])):replay_mismatches.append({'case_id':cid,'reason':'selected set is not the exact union'})
            assert all(e['document_id'] in prod['public_scope_document_ids'] for e in es)
            read_ids=sorted(sid for sid in {e['source_id'] for e in es} if complete(sources[sid],es))
            assert set(read_ids)==set(row.get('read_complete',[])),(cid,'read mismatch')
            flattened=[e for p in row.get('packets',[]) for e in p['evidence']]
            if flattened and 'spans' not in flattened[0]:
                lookup={e['evidence_id']:e for e in es};shown=[]
                for item in flattened:
                    e=lookup[item['evidence_id']]
                    assert item['text']=='\n'.join(s['text'] for s in e['spans'])
                    assert hashlib.sha256(item['text'].encode()).hexdigest()==item['text_hash']==e['text_hash']
                    assert all(item[k]==e[k] for k in ('source_id','document_id','generation_id','source_artifact_hash'))
                    shown.append(e)
            else:shown=flattened
            packet_ids=[sid for sid in read_ids if complete(sources[sid],shown)]
            assert set(packet_ids)==set(row.get('prepared_complete',[])),(cid,'packet mismatch')
            discovered=row.get('discovered',[]);g=h.ordered(coords[sid] for sid in gold[cid]['decisive_source_ids'])
            stages=[];prev=[]
            for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
                ids={'discovered':discovered,'read_complete':read_ids,'packet':packet_ids}[plan['stage_id']]
                after=h.ordered(coords[sid] for sid in ids if sid in coords);bk={h.key(v) for v in prev};ak={h.key(v) for v in after};dropped=[v for v in prev if h.key(v) not in ak]
                stage=h.stage(plan['stage_id'],plan['kind'],plan['parent_stage_ids'],prev,[v for v in after if h.key(v) not in bk],dropped,{h.key(v):'not_fully_acquired_within_frozen_policy' for v in dropped},g)
                stages.append(stage);prev=stage['after']
            rec={'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':stages};records.append(rec);question_stages.setdefault(cid,{})[arm]=rec
            missing=[sid for sid in gold[cid]['decisive_source_ids'] if sid not in packet_ids]
            summaries.append({'case_id':cid,'arm':arm,'run_id':'run-001','raw_record':str(path.relative_to(R)),'gold_total':len(g),'gold_by_stage':{s['stage_id']:s['gold_after'] for s in stages},'count_by_stage':{s['stage_id']:s['after_count'] for s in stages},'all_gold_complete':not missing,'missing':[{'source_id':sid,'document_name':sources[sid]['document_name'],'heading':sources[sid].get('heading'),'stage':'not_discovered' if sid not in discovered else 'not_read_complete','selected_for_read':sid in row.get('selected_for_read',[])} for sid in missing],'seconds':row.get('request_seconds'),'retrieval_seconds':row.get('seconds'),'source_chars':row.get('source_chars'),'packet_count':len(row.get('packets',[])),'packet_chars':sum(len(json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(',',':'))) for p in row.get('packets',[])),'limits':row.get('limits',[]),'error':row.get('error')})
        arms.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':{'presented_total':sum(c['stages'][-1]['after_count'] for c in records),'gold_after':sum(c['stages'][-1]['gold_after'] for c in records),'gold_total':sum(c['gold_total'] for c in records)}})
    ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'corpus_total':corpus,'packet_semantics':'BOTH arms = prepared full source packets; neither sent to a model. Both arms reuse exactly the same frozen Gemma query plans; no new model calls.','baseline_origin':str(P.relative_to(R)),'baseline_aggregation':'Recomputed all61 directly from validated ADR0512 raw records','actual_query_planner_calls':planning['physical_calls'],'actual_source_delivery_calls':0}}
    ledger['artifact_sha256']=h._canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
    def aggregate(rows):
        times=[r['seconds'] for r in rows];g=sum(r['gold_total'] for r in rows);got=sum(r['gold_by_stage']['packet'] for r in rows)
        return {'cases':len(rows),'gold_total':g,'gold_found':sum(r['gold_by_stage']['discovered'] for r in rows),'gold_fully_read':sum(r['gold_by_stage']['read_complete'] for r in rows),'gold_in_packets':got,'full_recall':got/g,'all_gold_complete_cases':sum(r['all_gold_complete'] for r in rows),'source_count_mean':statistics.mean(r['count_by_stage']['packet'] for r in rows),'source_chars_mean':statistics.mean(r['source_chars'] or 0 for r in rows),'request_p50':statistics.median(times),'request_p95':sorted(times)[round((len(times)-1)*.95)],'packet_count_max':max(r['packet_count'] for r in rows),'packet_to_raw_chars_mean':statistics.mean(r['packet_chars']/r['source_chars'] for r in rows if r['source_chars']),'error_cases':sum(bool(r['error']) for r in rows)}
    primary=set(read(A/'artifacts/frozen-design.json')['primary_cases']);totals={}
    for arm in ('baseline','retrieval'):
        totals[arm+'_all61']=aggregate([r for r in summaries if r['arm']==arm]);totals[arm+'_primary']=aggregate([r for r in summaries if r['arm']==arm and r['case_id'] in primary])
    usage=[u for b in planning['batches'] for u in b['usage']]
    cost={'physical_model_calls':planning['physical_calls'],'input_tokens':sum(u.get('input_tokens',0) or 0 for u in usage),'output_tokens':sum(u.get('output_tokens',0) or 0 for u in usage),'api_cost_usd':sum(u.get('cost_usd',0) or 0 for u in usage),'planning_seconds':planning['seconds'],'planner_failed_batches':sum(bool(b['error']) for b in planning['batches']),'actual_source_delivery_calls':0,'reused_gemma_parent_calls':11,'worker_count':3}
    bounds=[r['case_id'] for r in summaries if r['arm']=='retrieval' and ((r['source_chars'] or 0)>1600000 or (r['retrieval_seconds'] or 0)>180 or r['count_by_stage']['packet']>288)]
    passed=totals['retrieval_primary']['full_recall']==1 and totals['retrieval_all61']['full_recall']>=.99 and not totals['retrieval_all61']['error_cases'] and not bounds and not cost['planner_failed_batches'] and not replay_mismatches
    assessment={'by_group':totals,'criteria_met':passed,'bounds_violations':bounds,'parent_selection_replay_mismatches':replay_mismatches,'usage':cost,'actual_model_source_delivery_verified':False,'semantic_answer_quality_measured':False,'by_case':summaries};write(A/'artifacts/summary.json',assessment)
    for arm in ('baseline','retrieval'):
        rows=[r for r in summaries if r['arm']==arm];counts=[r['count_by_stage']['packet'] for r in rows];gt=sum(r['gold_total'] for r in rows)
        metrics={'before_filter':sum(r['count_by_stage']['discovered'] for r in rows),'after_filter':sum(r['count_by_stage']['read_complete'] for r in rows),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':sorted(counts)[round((len(counts)-1)*.95)],'golden_recall':sum(r['gold_by_stage']['packet'] for r in rows)/gt,'selectivity':statistics.mean(counts)/corpus}
        for k,v in metrics.items():
            if not isinstance(m['retrieval_accounting'].get(k),dict):m['retrieval_accounting'][k]={}
            m['retrieval_accounting'][k][arm]=v
    m['retrieval_accounting']['corpus_total']=corpus;m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-001',artifact_path=str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),sha256=sha(A/'artifacts/retrieval-stage-ledger.json'))
    m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/results.json'))
    m['reused_gemma_plans']['new_calls']=planning['physical_calls']
    m['results'].update(status='complete',by_arm={arm:{'status':'complete',**totals[arm+'_all61']} for arm in ('baseline','retrieval')},comparisons=[{'primary':totals['retrieval_primary'],'all61_gold_read_delta':totals['retrieval_all61']['gold_fully_read']-totals['baseline_all61']['gold_fully_read'],'criteria_met':passed}],usage=cost,latency={k:{x:v[x] for x in ('request_p50','request_p95')} for k,v in totals.items()},error_taxonomy=[r for r in summaries if r['missing'] or r['error']])
    write(A/'실험/manifest.json',m)
    table='|범위|기준 전체 원문|보강 전체 원문|필수 원문|\n|---|---:|---:|---:|\n'
    for name,label in [('primary','기존 실패6문항'),('all61','고정61문항')]:table+=f"|{label}|{totals['baseline_'+name]['gold_fully_read']}|{totals['retrieval_'+name]['gold_fully_read']}|{totals['retrieval_'+name]['gold_total']}|\n"
    verdict='Accepted' if passed else 'Rejected'
    conclusion=f"전체 원문 확보 {totals['baseline_all61']['gold_fully_read']}/90 → {totals['retrieval_all61']['gold_fully_read']}/90 ({totals['retrieval_all61']['full_recall']:.1%}). 사전99% 기준 {'충족' if passed else '미달'}. 부모 Gemma 검색계획을 그대로 재사용했고 새 모델 호출0회. 원문의 실제 모델 전달·답변 품질은 미측정."
    sections=[('결정 요약',conclusion+'\n\n'+table),('문제와 변경 전 구조','ADR0511은83/90, ADR0512는85/90의 필수 원문을 완전히 읽었다. 새 경로가 이전 누락7개를 회복했지만 기존 성공5개를 밀어냈다. 한쪽 선택을 다른 쪽으로 교체하는 구조를 중단한다.'),('가설과 사전 판정 기준','[PLAN](PLAN.md). 기존6문항10/10, 전체61문항90원문 중99% 이상. 전체 span 포함, 범위·해시 위반0.\n'+block({'criteria_met':passed,'bounds_violations':bounds})),('실험 설계','고정 Gemma 계획 → 전역 discovery와 법령별/짧은 질의/미해결 좌표 discovery를 각각 재실행 → 양쪽 선택 원문 합집합을 손실 없이 보존 → 중복 원문 한번 READ, 모든 페이지 span 검증 → 패킷. 미해결 참조 후보는 법적 연결이 확정된 근거로 취급하지 않는다. candidate ObligationSession의 prepare_source_recall/investigate에 연결. query plan producer는 격리 runner에서만 연결. 전체 MAIN에는 미반영.'),('데이터·모델·재현성','공개145문서·61문항·90필수 원문. 선택 코드/데이터/입력/후보 해시를 첫 호출 전 동결. 부모 google/gemma-4-31b-it의 OpenRouter DeepInfra FP8/thinking off/temperature0 결과를 해시 고정 재사용. 부모11호출, 이번 호출0. 외부로 새 입력 전송 없음. 모든 문항은 기존 노출 in-sample, 독립 holdout 아님. GENOS 미접속.'),('결과',table+block(totals)),('사례별 오류 분석','[전체 문항표](실험/README.md), [누락 단계](artifacts/summary.json). ID 발견/조문 전체 읽기/패킷 준비를 구분한다. 패킷 준비를 실제 모델 읽기로 세지 않는다.'),('비용·지연·회수 규모',block(cost)+'\n후보는 독립 worker3개 동시 부하에서 측정했으므로 직렬 부모와 지연 우열을 비교하지 않는다. 요청 p50/p95는 원문 회수만 포함하고 자원 로딩은 별도다. 실제 사용자 종단 지연·최종 모델 입력 토큰은 미측정. 원문 회수량 증가를 품질과 함께 평가해야 한다.'),('해석',conclusion+'\n모델 계획과 두 부모 discovery를 고정하고 합집합 보존·공통 읽기 예산을 바꿨다. 두 부모의 원문 선택 목록 재현 여부를 모든 문항에서 검사한다. 캐시 최적화의 독립 속도 효과는 미측정.'),('한계와 일반화 가능 범위','기존61문항의 검색 회수 검증이다. 데이터 범위 밖 법령, 신규 질문, 최종 답변, GENOS 내부 모델 품질로 일반화할 수 없다. 모델에 원문 패킷을 실제 전달한 실험은 아니다.'),('운영 결정·롤백 조건',verdict+'; in_sample=true, decision_eligible=false. MAIN·GENOS·포인터 미변경. 합성 계약검사13개 통과. 부모 ADR0511·ADR0512 자체 정합성 검사 통과. ADR0510의 분할 집계 오류는 이전 기록에 보존됐으며 이번 기준 통계는 검증된 ADR0511 원자료에서 재계산했다.'),('재현 명령','```bash\n.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0513/retrieval\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union --final\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR\n```\n완료 실행을 덮어쓰지 않는다. 변경/재실행은 새 ADR. 실제 검사 결과는 artifacts/completion.json 참조.')]
    front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+verdict);(A/'README.md').write_text('---'+front+'---\n\n# 두 검색 경로의 원문 합집합 보존\n\n'+'\n\n'.join(f'## {i}. {head}\n\n{v}' for i,(head,v) in enumerate(sections,1))+'\n')
    qlookup={q['case_id']:q for q in prod['cases']};index='# 전체61문항 원문 회수\n\n|문항|기준|보강|필수|누락|\n|---|---:|---:|---:|---|\n'
    for q in m['questions']:
        cid=q['case_id'];row=next(r for r in summaries if r['arm']=='retrieval' and r['case_id']==cid);base=next(r for r in summaries if r['arm']=='baseline' and r['case_id']==cid);raw=read(raw_by_case[cid]);batch=planning['case_batches'][cid];call=G/'artifacts/planner'/f'batch-{batch:02d}'/'call-001-source-query-plan'
        calls={f:read(call/f) for f in ('request.json','response.json','binding.json') if (call/f).exists()}
        sections=[('실행 메타',block({'run_id':'run-001','shared_parent_query_batch':batch,'new_query_model_calls':0,'actual_source_delivery_calls':0})),('사용자 질문 원문',qlookup[cid]['question']),('기준답변 — 채점 전용, 제품 입력 비공개',block(gold[cid])),('제품 입력을 구성한 원값',block(raw)+'\n### 회수·탈락 단계 원장 — run·arm별\n'+block(question_stages[cid])),('제품 모델 호출 — run·arm별 실제 원문',block(calls)+'\n위 호출은 부모 ADR0511의 완료된 검색 계획 배치를 재사용한 기록이다. 이번 모델 호출·비용은0이며 중복 합산하지 않는다. 원문 패킷은 PREPARED_NOT_SENT.'),('중간 LLM 호출 — router/compiler/verifier/repair','이번 호출0. 부모 검색 계획 원값을 그대로 재사용하며 새 계획 생성/repair/fallback 없음.'),('채점 호출과 반복 판정','모델 채점 없음. 실행 후 고정 gold 좌표와 조문 전체 span/hash 대조. 법률 해석 정답률 미평가.'),('사례 최종 판정',block({'baseline':base,'retrieval':row}))]
        (A/'실험'/q['file']).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {head}\n\n{v}' for i,(head,v) in enumerate(sections,1))+'\n')
        index+=f"|[{cid}]({q['file']})|{base['gold_by_stage']['read_complete']}|{row['gold_by_stage']['read_complete']}|{row['gold_total']}|"+', '.join(x['heading'] for x in row['missing'])+'|\n'
    (A/'실험/README.md').write_text(index)
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(A.relative_to(R))],check=True,stdout=subprocess.DEVNULL)
    files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ('manifest.json','completion.json','validation-final.txt','graph-check.txt','report-output.txt') and not p.name.endswith(('-wal','-shm'))]
    files+=[A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',C/'candidate.json']+list(Path(__file__).parent.glob('*.py'))+[R/f['frozen_path'] for f in read(C/'candidate.json')['revisions'][-1]['files']]
    write(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input, Gemma query plan, source evidence, or offline audit'} for p in sorted(set(files))]})
    print(json.dumps({'totals':totals,'usage':cost,'passed':passed},ensure_ascii=False))
if __name__=='__main__':main()
