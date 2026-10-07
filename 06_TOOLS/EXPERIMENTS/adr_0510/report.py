"""Offline-only gold join after acquisition. No product module imports."""
import json
import sqlite3
import hashlib
import statistics
import importlib.util
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0510-source-recall-first'
P = R/'04_EXPERIMENTS/ADR/ADR-0509-gemma-search-skill-harness-paired'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v): return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'

def complete(source, evidence):
    for b in source['blocks']:
        covered=set()
        for e in evidence:
            if e['source_id']==source['id']:
                for s in e['spans']:
                    if s['block_id']==b['block_id']:
                        assert b['text'][s['start_cp']:s['end_cp']]==s['text']
                        covered.update(range(s['start_cp'],s['end_cp']))
        if len(covered)!=len(b['text']): return False
    return True

def main():
    m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json');gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']}
    spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    with sqlite3.connect('file:'+str(R/prod['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
        sources={sid:json.loads(raw) for sid,raw in db.execute('SELECT id,json FROM source')}
    coords={sid:{'doc_id':s['document_id'],'node':int(s['unit_id'])} for sid,s in sources.items() if str(s['unit_id']).isdigit()}
    corpus=len({h.key(c) for sid,c in coords.items() if sources[sid]['document_id'] in prod['public_scope_document_ids']})
    old=read(P/'artifacts/retrieval-stage-ledger.json');old_cases={c['case_id']:c for a in old['runs'][0]['arms'] if a['arm_id']=='integrated' for c in a['cases']}
    inverse={h.key(v):sid for sid,v in coords.items()}
    summaries=[];ledger_runs=[];raw_by_case={};question_stages={}
    for run in m['runs']:
        result=read(A/'artifacts'/run['id']/'results.json');arms=[]
        for arm in run['arm_ids']:
            records=[]
            for cid in run['case_ids']:
                if arm=='baseline':
                    parent=P/'artifacts/run-001'/cid/'integrated';trace=read(parent/'trace.json');es=trace['evidence']
                    discovered=[inverse[h.key(c)] for c in old_cases[cid]['stages'][0]['after']]
                    read_ids=sorted(sid for sid in {e['source_id'] for e in es} if complete(sources[sid],es))
                    with sqlite3.connect('file:'+str(parent/'journal.sqlite')+'?mode=ro',uri=True) as db:
                        presented={r[0] for r in db.execute("SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'")}
                    shown=[e for e in es if e['evidence_id'] in presented]
                    packet_ids=[sid for sid in read_ids if complete(sources[sid],shown)]
                    row={'origin':str(parent.relative_to(R)),'discovered':discovered,'read_complete':read_ids,'prepared_complete':packet_ids,'actual_model_presentation':'Historical successful model attempts; not a new call', 'source_chars':None,'packets':[],'request_seconds':None,'error':None,'limits':[]}
                else:
                    row=read(R/result['cases'][cid]);raw_by_case[cid]=row
                    es=row.get('evidence',[])
                    read_ids=sorted(sid for sid in {e['source_id'] for e in es} if complete(sources[sid],es))
                    assert set(read_ids)==set(row.get('read_complete',[])),(cid,'complete read mismatch')
                    flattened=[e for p in row.get('packets',[]) for e in p['evidence']]
                    packet_ids=[sid for sid in read_ids if complete(sources[sid],flattened)]
                    assert set(packet_ids)==set(row.get('prepared_complete',[])),(cid,'packet mismatch')
                    discovered=row.get('discovered',[])
                g=h.ordered(coords[sid] for sid in gold[cid]['decisive_source_ids'])
                stage_sets={'discovered':discovered,'read_complete':read_ids,'packet':packet_ids}
                stages=[];prev=[]
                for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
                    after=h.ordered(coords[sid] for sid in stage_sets[plan['stage_id']] if sid in coords)
                    bk={h.key(v) for v in prev};ak={h.key(v) for v in after};dropped=[v for v in prev if h.key(v) not in ak]
                    stage=h.stage(plan['stage_id'],plan['kind'],plan['parent_stage_ids'],prev,[v for v in after if h.key(v) not in bk],dropped,{h.key(v):'not_fully_acquired_within_frozen_policy' for v in dropped},g)
                    stages.append(stage);prev=stage['after']
                rec={'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':stages};records.append(rec)
                missing=[sid for sid in gold[cid]['decisive_source_ids'] if sid not in packet_ids]
                summary={'case_id':cid,'arm':arm,'run_id':run['id'],'gold_total':len(g),'gold_by_stage':{s['stage_id']:s['gold_after'] for s in stages},'count_by_stage':{s['stage_id']:s['after_count'] for s in stages},'all_gold_complete':not missing,'missing':[{'source_id':sid,'document_name':sources[sid]['document_name'],'heading':sources[sid].get('heading'),'stage':'not_discovered' if sid not in discovered else 'not_read_complete','selected_for_read':sid in row.get('selected_for_read',[])} for sid in missing],'seconds':row.get('request_seconds'),'retrieval_seconds':row.get('seconds'),'source_chars':row.get('source_chars'),'packet_count':len(row.get('packets',[])),'limits':row.get('limits',[]),'error':row.get('error')}
                summaries.append(summary);question_stages.setdefault(cid,{})[arm]=rec
            # Validator requires every manifest case in every run. Explicitly mark
            # cases outside this run's PRE-FROZEN partition as unexecuted, no denominator.
            for q in m['questions']:
                if q['case_id'] in run['case_ids']: continue
                skipped=[h.stage(p['stage_id'],p['kind'],p['parent_stage_ids'],[],[],[],{},[],skip_reason='NOT_IN_FROZEN_RUN_CASE_SELECTION') for p in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]]
                records.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':q['case_id'],'gold_total':0,'gold_identities':[],'stages':skipped})
            arms.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':{'presented_total':sum(c['stages'][-1]['after_count'] for c in records),'gold_after':sum(c['stages'][-1]['gold_after'] for c in records),'gold_total':sum(c['gold_total'] for c in records)}})
        ledger_runs.append({'run_id':run['id'],'arms':arms})
        run.update(status='complete',sha256=sha(A/'artifacts'/run['id']/'results.json'))
    ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':ledger_runs,'audit':{'corpus_total':corpus,'packet_semantics':'retrieval=prepared source packets, no model sent; baseline=historical successful presentation; compare complete reading only','baseline_origin':str(P.relative_to(R)),'actual_model_calls':0}}
    ledger['artifact_sha256']=h._canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
    def aggregate(rows):
        times=[r['seconds'] for r in rows if r['seconds'] is not None];g=sum(r['gold_total'] for r in rows);got=sum(r['gold_by_stage']['packet'] for r in rows)
        return {'cases':len(rows),'gold_total':g,'gold_found':sum(r['gold_by_stage']['discovered'] for r in rows),'gold_fully_read':sum(r['gold_by_stage']['read_complete'] for r in rows),'gold_in_packets':got,'full_recall':got/g if g else None,'all_gold_complete_cases':sum(r['all_gold_complete'] for r in rows),'source_count_mean':statistics.mean(r['count_by_stage']['packet'] for r in rows),'source_chars_mean':statistics.mean([r['source_chars'] for r in rows if r['source_chars'] is not None]) if times else None,'request_p50':statistics.median(times) if times else None,'request_p95':sorted(times)[max(0,__import__('math').ceil(.95*len(times))-1)] if times else None,'packet_count_max':max(r['packet_count'] for r in rows),'error_cases':sum(bool(r['error']) for r in rows),'actual_new_model_calls':0}
    totals={'baseline_primary':aggregate([r for r in summaries if r['arm']=='baseline']),'retrieval_primary':aggregate([r for r in summaries if r['arm']=='retrieval' and r['run_id']=='run-001']),'retrieval_all61':aggregate([r for r in summaries if r['arm']=='retrieval'])}
    passed=totals['retrieval_primary']['full_recall']==1 and totals['retrieval_all61']['full_recall']>=.99 and not totals['retrieval_all61']['error_cases']
    assessment={'by_group':totals,'criteria_met':passed,'actual_model_delivery_verified':False,'semantic_answer_quality_measured':False,'by_case':summaries};write(A/'artifacts/summary.json',assessment)
    primary=[r for r in summaries if r['run_id']=='run-001' and r['arm']=='retrieval']
    for arm in ('baseline','retrieval'):
        rows=[r for r in summaries if r['run_id']=='run-001' and r['arm']==arm];counts=[r['count_by_stage']['packet'] for r in rows];gt=sum(r['gold_total'] for r in rows)
        metrics={'before_filter':sum(r['count_by_stage']['discovered'] for r in rows),'after_filter':sum(r['count_by_stage']['read_complete'] for r in rows),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':sum(r['gold_by_stage']['packet'] for r in rows)/gt,'selectivity':statistics.mean(counts)/corpus}
        for k,v in metrics.items():
            if not isinstance(m['retrieval_accounting'].get(k),dict):m['retrieval_accounting'][k]={}
            m['retrieval_accounting'][k][arm]=v
    m['retrieval_accounting']['corpus_total']=corpus;m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-001',artifact_path=str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),sha256=sha(A/'artifacts/retrieval-stage-ledger.json'))
    m['results'].update(status='complete',by_arm={'baseline':{'status':'complete',**totals['baseline_primary']},'retrieval':{'status':'complete',**totals['retrieval_all61']}},comparisons=[{'primary':totals['retrieval_primary'],'primary_read_delta':totals['retrieval_primary']['gold_fully_read']-totals['baseline_primary']['gold_fully_read'],'criteria_met':passed}],usage={'physical_model_calls':0,'tokens':0,'api_cost_usd':0},latency={k:{x:v[x] for x in ('request_p50','request_p95')} for k,v in totals.items()},error_taxonomy=[r for r in summaries if r['missing'] or r['error']])
    write(A/'실험/manifest.json',m)
    table='|문항|기존 완전 읽기|보강 완전 읽기|필수 조문|\n|---|---:|---:|---:|\n'
    for r in primary:
        b=next(x for x in summaries if x['arm']=='baseline' and x['case_id']==r['case_id']);table+=f"|{r['case_id']}|{b['gold_by_stage']['read_complete']}|{r['gold_by_stage']['read_complete']}|{r['gold_total']}|\n"
    conclusion=f"실패6문항의 완전 원문 회수는 {totals['baseline_primary']['gold_fully_read']}/10 → {totals['retrieval_primary']['gold_fully_read']}/10. 고정61문항은 {totals['retrieval_all61']['gold_fully_read']}/{totals['retrieval_all61']['gold_total']} ({totals['retrieval_all61']['full_recall']:.1%})이다. 모델 호출0회이며 패킷은 준비했으나 Gemma 실제 전달/답변은 이번에 측정하지 않았다."
    sections=[('결정 요약',conclusion+'\n\n'+table),('문제와 변경 전 구조','ADR0509는 후보9/10·부분 포함 읽기6/10·성공 호출 전달5/10. 후단 검토만 개선할 문제가 아니었다. 역방향 참조 색인에도 있는 예외 조문을 탐색하지 않았고, 모델이 일부 후보만 읽었다.'),('가설과 사전 판정 기준','[PLAN](PLAN.md):6문항10/10 전체 원문·패킷 확보,61문항99% 이상. source64개·32만자·192도구·120초 제한. Gold 제품 입력 비공개.\n'+block({'criteria_met':passed})),('실험 설계','원질문/문맥/첫 문장 전문 검색 + 구조 일치 + 정·역방향 참조의 원문 witness 검증 + 기존 READ 전체 페이지. 기존 ObligationSession.investigate 시작점의 prepare_source_recall 호출에 연결. 원문 확보와 법적 출처 채택은 별개. 기준은 ADR0509 과거6문항만 재사용하므로 동시 Gemma A/B가 아니다.'),('데이터·모델·재현성','공개145문서의 같은 선택 세대·코드 부모, 입력61문항과 source/gold/후보/runner hash 동결. 모델·judge0회, GENOS 접근 없음. 기준답과 원문 버전은 과거 고정판이며 최신성 재인증 아님. 테스트6문항도 추가55문항도 기존 사용 이력이 있어 독립 holdout이 아니다.'),('결과',table+'\n'+block(totals)),('사례별 오류 분석','[전체 문항표](실험/README.md), [단계별·누락 요약](artifacts/summary.json). canonical ID를 얻었어도 전체 span이 없으면 미완료로 처리한다.'),('비용·지연·회수 규모',block(totals)+'\n공유 자원 로딩은 결과 JSON의 resource_load_seconds_shared에 별도 표시. 패킷이 여러 개이므로 실제 모델 호출 토큰·시간·선택 품질은 이후 확인 대상이다. 실제 LLM 제시 수는0이며 ledger의 최종 present는 이번 후보에서는 준비 패킷이라는 것을 명시한다.'),('해석',conclusion+'\n100%가 나온 부분집합을 전체 검색 성능으로 일반화하지 않는다. 후보를 넓게 읽는 비용과 모델에 전달할 정보량을 함께 본다.'),('한계와 일반화 가능 범위','상위 검색·참조 깊이·조문수·원문량·시간 제한이 있으므로 corpus 전체 recall 보장은 없다. 준비 패킷은 기존 답변 단계로 모두 전달된 상태가 아니다. 기존 모델 view는 별도의 페이지 처리를 요구한다. source-only 후보와 완성 답변 품질을 혼동하지 않는다.'),('운영 결정·롤백 조건','Rejected; in_sample=true, decision_eligible=false. MAIN·GENOS·데이터 포인터 미변경. 실험 코드 보존, 새 변경은 새 ADR. 합성7개 계약 검사 통과. startup 어댑터 누락은 문항 실행 전 0회 호출 상태로 수정했으며 원기록은 artifacts/preflight-001에 보존.'),('재현 명령','```bash\n.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0510/retrieval\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0510-source-recall-first --final\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR\n```\n완료 run은 덮어쓰지 않는다. 최종 검사와 기존 graph 오류는 artifacts/completion.json에 기록.')]
    front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected');(A/'README.md').write_text('---'+front+'---\n\n# 원문 회수 우선 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
    expected={q['file'] for q in m['questions']}
    for extra in (A/'실험').glob('질문-*.md'):
        if extra.name not in expected:
            archive=A/'artifacts/scaffold-unused';archive.mkdir(exist_ok=True);extra.rename(archive/extra.name)
    qlookup={q['case_id']:q for q in prod['cases']};index='# 전체61문항 원문 회수\n\n|문항|전체 원문 회수|필수|누락|\n|---|---:|---:|---|\n'
    for q in m['questions']:
        cid=q['case_id'];row=next(r for r in summaries if r['arm']=='retrieval' and r['case_id']==cid);raw=raw_by_case[cid]
        sections=[('실행 메타',block({'run_id':row['run_id'],'model_calls':0,'source_only':True})),('사용자 질문 원문',qlookup[cid]['question']),('기준답변 — 채점 전용, 제품 입력 비공개',block(gold[cid])),('제품 입력을 구성한 원값',block(raw)+'\n### 회수·탈락 단계 원장 — run·arm별\n'+block(question_stages[cid])),('제품 모델 호출 — run·arm별 실제 원문','새 호출0. 위 패킷은 PREPARED_NOT_SENT이며 실제 모델 전달로 세지 않는다. 기존6문항 호출은 부모 ADR0509 immutable 기록 참조.'),('중간 LLM 호출 — router/compiler/verifier/repair','없음.'),('채점 호출과 반복 판정','모델 채점 없음. 고정 gold canonical 좌표와 원문 전체 span 포함을 실행 종료 후 대조. 인용/법률 해석 정답률은 미평가.'),('사례 최종 판정',block(row))]
        (A/'실험'/q['file']).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
        index+=f"|[{cid}]({q['file']})|{row['gold_by_stage']['read_complete']}|{row['gold_total']}|"+', '.join(x['heading'] for x in row['missing'])+'|\n'
    (A/'실험/README.md').write_text(index)
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(A.relative_to(R))],check=True,stdout=subprocess.DEVNULL)
    files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ('manifest.json','completion.json','validation-final.txt','graph-check.txt') and not p.name.endswith(('-wal','-shm'))]
    C=R/'02_BACKEND/lawrag/research/candidates/adr_0510/retrieval';files+=[A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',C/'candidate.json']+list(Path(__file__).parent.glob('*.py'))+[R/f['frozen_path'] for f in read(C/'candidate.json')['revisions'][-1]['files']]
    write(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input, source acquisition, evidence packet or offline audit'} for p in sorted(set(files))]})
    print(json.dumps(totals,ensure_ascii=False))

if __name__=='__main__': main()
