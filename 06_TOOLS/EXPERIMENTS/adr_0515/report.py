"""Post-selection canonical scoring, isolated from all product calls."""
from pathlib import Path
import json
import hashlib
import statistics
import importlib.util
import subprocess
import sys

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0515-compact-provenance-selection'
P=R/'04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0515/selection'

def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
def percentile(v,p):return sorted(v)[round((len(v)-1)*p)]

def main():
    m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json');gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']}
    frozen=read(A/'artifacts/frozen-design.json')
    for p,h in frozen['grader_only_hashes'].items():assert sha(R/p)==h
    spec=importlib.util.spec_from_file_location('canonical_ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    manifest_results=read(A/'artifacts/run-001/results.json');case_rows=[];arm_records={'baseline':[],'selection':[]};stage_by_case={};results={};usages=[]
    for cid in m['runs'][0]['case_ids']:
        parent=read(P/'artifacts/run-001'/cid/'result.json');out=read(R/manifest_results['cases'][cid]);results[cid]=out
        assert sha(R/out['input_parent_path'])==out['input_parent_sha256']
        evidence=parent['evidence'];coords={e['source_id']:{'doc_id':e['document_id'],'node':int(e['unit_id'])} for e in evidence}
        all_ids=parent['read_complete'];first=out['first_ids'];final=out['final_ids']
        if out.get('error'):
            # Recover only a physically logged first-turn selection after a later failure.
            f=A/'artifacts/run-001'/cid/'model/call-001-source-triage/output.json'
            if f.exists():
                labels={f'C{i+1:03d}':sid for i,sid in enumerate(dict.fromkeys(s for s in parent['selected_for_read'] if s in all_ids))}
                first=[labels[x['id']] for x in read(f)['choices']]
        assert set(first).issubset(all_ids) and set(final).issubset(all_ids)
        if out['status']=='complete':assert set(first).issubset(final)
        originals={e['evidence_id']:e for p in parent['packets'] for e in p['evidence']}
        sent={e['evidence_id']:e for p in out.get('final_packets',[]) for e in p['evidence']}
        expected={k:v for k,v in originals.items() if v['source_id'] in final}
        assert sent==expected,(cid,'final full-source packet loss or mutation')
        assert all(p['delivery_status']=='PREPARED_NOT_SENT' for p in out.get('final_packets',[]))
        golden=gold[cid]['decisive_source_ids'];g=h.ordered(coords[sid] for sid in golden)
        for arm in ('baseline','selection'):
            prev=[];stages=[]
            ids_by_stage={'acquired':all_ids,'triage':first,'recovery':final,'final_pool':all_ids if arm=='baseline' else final}
            for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
                after=h.ordered(coords[sid] for sid in ids_by_stage[plan['stage_id']]);before_keys={h.key(x) for x in prev};after_keys={h.key(x) for x in after};discarded=[x for x in prev if h.key(x) not in after_keys]
                reason='model_or_budget_failure' if out.get('error') and arm=='selection' else 'deferred_by_provenance_source_selection'
                stage=h.stage(plan['stage_id'],plan['kind'],plan['parent_stage_ids'],prev,[x for x in after if h.key(x) not in before_keys],discarded,{h.key(x):reason for x in discarded},g)
                stages.append(stage);prev=stage['after']
            rec={'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':stages}
            arm_records[arm].append(rec);stage_by_case.setdefault(cid,{})[arm]=rec
        missing=[sid for sid in golden if sid not in final]
        meta={e['source_id']:e['metadata'] for e in evidence}
        usages.extend(out['usage'])
        case_rows.append({'case_id':cid,'gold_total':len(golden),'baseline_count':len(all_ids),'first_count':len(first),'recovered_count':len(out['recovered_ids']),'final_count':len(final),
            'gold_first':len(set(golden)&set(first)),'gold_final':len(set(golden)&set(final)),
            'gold_recovered':len((set(golden)&set(final))-set(first)),
            'missing':[{'source_id':sid,'document_name':meta[sid]['document_name'],'heading':meta[sid]['heading'],'stage':'triage_not_recovered' if sid not in first else 'later_failure'} for sid in missing],
            'error':out['error'],'selection_seconds':out['selection_wall_seconds'],'composed_seconds':out['composed_seconds'],
            'physical_calls':out['physical_model_calls'],
            'selector_excerpt_sources':len(out.get('actual_selector_excerpts',[{}])[0].get('cards',[])) if out.get('actual_selector_excerpts') else None})
    corpus=read(P/'실험/manifest.json')['retrieval_accounting']['corpus_total'];arms=[]
    for arm,records in arm_records.items():
        arms.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':{'presented_total':sum(x['stages'][-1]['after_count'] for x in records),'gold_after':sum(x['stages'][-1]['gold_after'] for x in records),'gold_total':sum(x['gold_total'] for x in records)}})
    ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],
        'audit':{'corpus_total':corpus,'final_present_semantics':'Final full-source packets prepared for a downstream answer model; PREPARED_NOT_SENT. Selector saw bounded excerpts and retrieval provenance, not all source full text.','parent_pool_replayed':True,'actual_answer_model_calls':0}}
    ledger['artifact_sha256']=h._canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
    counts=[x['final_count'] for x in case_rows];times=[x['selection_seconds'] for x in case_rows];composed=[x['composed_seconds'] for x in case_rows]
    totals={'cases':len(case_rows),'gold_total':sum(x['gold_total'] for x in case_rows),'gold_first':sum(x['gold_first'] for x in case_rows),'gold_final':sum(x['gold_final'] for x in case_rows),'gold_recovered':sum(x['gold_recovered'] for x in case_rows),
        'baseline_count_mean':statistics.mean(x['baseline_count'] for x in case_rows),'final_count_mean':statistics.mean(counts),'final_count_p50':statistics.median(counts),'final_count_p95':percentile(counts,.95),'final_count_max':max(counts),
        'all_gold_retained_cases':sum(not x['missing'] for x in case_rows),'error_cases':sum(bool(x['error']) for x in case_rows),'selection_p50':statistics.median(times),'selection_p95':percentile(times,.95),'composed_p50':statistics.median(composed),'composed_p95':percentile(composed,.95),
        'physical_calls':sum(x['physical_calls'] for x in case_rows),'input_tokens':sum(x.get('input_tokens',0) or 0 for x in usages),'output_tokens':sum(x.get('output_tokens',0) or 0 for x in usages),'cost_usd':sum(x.get('cost_usd',0) or 0 for x in usages)}
    passed=totals['gold_final']==90 and max(counts)<=24 and statistics.mean(counts)<=20 and totals['error_cases']==0 and totals['composed_p95']<=240
    summary={'totals':totals,'criteria_met':passed,'in_sample':True,'decision_eligible':False,'main_changed':False,'actual_answer_model_calls':0,'provenance_effect_ablation_measured':False,'by_case':case_rows}
    write(A/'artifacts/summary.json',summary)
    for arm in ('baseline','selection'):
        records=arm_records[arm];cs=[x['stages'][-1]['after_count'] for x in records];got=sum(x['stages'][-1]['gold_after'] for x in records)
        stats={'before_filter':sum(x['stages'][0]['after_count'] for x in records),'after_filter':sum(cs),'presented_total':sum(cs),'presented_mean':statistics.mean(cs),'presented_p50':statistics.median(cs),'presented_p95':percentile(cs,.95),'golden_recall':got/90,'selectivity':statistics.mean(cs)/corpus}
        for k,v in stats.items():m['retrieval_accounting'][k]={**({} if arm=='baseline' else m['retrieval_accounting'][k]),arm:v}
    m['retrieval_accounting']['corpus_total']=corpus;m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'artifacts/retrieval-stage-ledger.json')
    m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/results.json'))
    m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','gold':90,'cases':61},'selection':{'status':'complete',**totals}},comparisons=[{'baseline_gold':90,'selection_gold':totals['gold_final'],'delta':totals['gold_final']-90,'criteria_met':passed}],usage={k:totals[k] for k in ('physical_calls','input_tokens','output_tokens','cost_usd')},latency={k:totals[k] for k in ('selection_p50','selection_p95','composed_p50','composed_p95')},error_taxonomy=[x for x in case_rows if x['missing'] or x['error']])
    m['gemma_binding']['live_calls']=totals['physical_calls'];write(A/'실험/manifest.json',m)
    verdict='Proposed' if passed else 'Rejected'
    conclusion=f"필수 원문 {totals['gold_final']}/90 보존, 첫 선별 {totals['gold_first']}/90에서 복구 {totals['gold_recovered']}개. 후보 평균 {totals['baseline_count_mean']:.1f} → {totals['final_count_mean']:.1f}; 최대{totals['final_count_max']}. 사전 기준 {'통과' if passed else '미달'}."
    sections=[('결정 요약',conclusion),('문제와 변경 전 구조','ADR0513에서90/90 전문을 확보했지만 평균230개 후보였다. 검색어·순위·정확좌표·정/역참조·중복 제거한 재발견 이력을 사용해 후단 후보를 줄인다.'),('가설과 사전 판정 기준','[동결 PLAN](PLAN.md). 전체90/90, 최대24·평균20이하, 오류0, 합산 p95<=240초. 결과 후 기준 변경 없음.'),('실험 설계','같은 부모 원문 풀 재생 → 원문 발췌·회수 경로 카드 → Gemma 최대16선별 → 선택 원문 확장 발췌 및 보류 풀 재검토 → 최대8복구 → 최종 전문 패킷 준비. 첫 선택을 유지하고 원래 풀은 삭제하지 않는다.'),('데이터·모델·재현성','공개145문서·고정61문항. google/gemma-4-31b-it, OpenRouter DeepInfra FP8, thinking off, temperature0. 전송 허용 출처·문서·세대를 사전 결속. 부모 query plan은 재사용, 이번 원문 선별은 실제 신규 호출. gold는 이 사후 검사기에만 들어간다.'),('결과',block(totals)),('사례별 오류 분석','[문항별 결과](실험/README.md), [정확한 탈락 조문](artifacts/summary.json), [단계 원장](artifacts/retrieval-stage-ledger.json). 첫 선별과 복구 후 손실을 분리한다.'),('비용·지연·회수 규모',block({k:totals[k] for k in ('physical_calls','input_tokens','output_tokens','cost_usd','selection_p50','selection_p95','composed_p50','composed_p95')})+'\n합산 지연은 과거3worker 검색 기록+현재3worker 선별이며 새로운 실제 종단 지연이 아니다. 선별 모델은 초기 전체 후보 발췌를 보며, 최종 답변 후보만 줄어든다.'),('해석',conclusion+' 회수 경로 단독 기여는 경로 없는 대조군을 실행하지 않아 미측정이다. 경로의 빈도는 법적 적용 확률이 아니다.'),('한계와 일반화 가능 범위','노출된 질문의 인샘플 실험. 독립 holdout·GENOS·최종 답변 품질 미측정. 확장 발췌도5000자 한도가 있어 모든 후보 전문을 선별 모델에 전달하지 않았다. 실제 보인 slice는 원문 좌표와 함께 기록된다.'),('운영 결정·롤백 조건',verdict+'; MAIN unchanged. 새 단계는 기존 recall output의 evidence/packet/route 계약을 소비하는 격리 후보이며 운영 API 자동 호출 배선은 추가하지 않았다. 기준 미달이면 원문 확보 부모를 유지하고 후보축소는 채택하지 않는다.'),('재현 명령','```bash\n.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0515/selection\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0515-compact-provenance-selection --final\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR\n```\n완료된 모델 호출은 덮어쓰지 않는다. 재실행/설계 변경은 새 ADR.')]
    front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+verdict)
    (A/'README.md').write_text('---'+front+'---\n\n# 회수 경로 기반 원문 선별 루프\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(sections,1))+'\n')
    qlookup={c['case_id']:c for c in prod['cases']};rows={x['case_id']:x for x in case_rows};index='# 61문항 후보 선별 결과\n\n|문항|전체 후보|첫 선별|복구 후|필수 보존|누락|\n|---|---:|---:|---:|---:|---|\n'
    for q in m['questions']:
        cid=q['case_id'];row=rows[cid];out=results[cid];parent=read(R/out['input_parent_path']);calls=[]
        for call in sorted((A/'artifacts/run-001'/cid/'model').glob('call-*')):
            calls.append({'path':str(call.relative_to(R)),**{p.name:read(p) for p in call.glob('*.json')}})
        inputs={'question':qlookup[cid]['question'],'parent_record':out['input_parent_path'],'parent_sha256':out['input_parent_sha256'],'pool':parent['read_complete'],'original_packets':parent['packets'],'routes':{sid:parent['routes'].get(sid,[]) for sid in parent['read_complete']}}
        parts=[('실행 메타',block({'run_id':'run-001','parent':'ADR0513/retrieval','product_model':'google/gemma-4-31b-it','answer_model_calls':0})),('사용자 질문 원문',qlookup[cid]['question']),('기준답변 — 채점 전용, 제품 입력 비공개',block(gold[cid])),('제품 입력을 구성한 원값',block(inputs)+'\n### 회수·탈락 단계 원장 — run·arm별\n'+block(stage_by_case[cid])),('제품 모델 호출 — run·arm별 실제 원문',block(calls)),('중간 LLM 호출 — router/compiler/verifier/repair','선별·누락점검2개 product 호출을 위에 기록했다. 숨은 repair/fallback·답변 호출은 없다.\n'+block(out)),('채점 호출과 반복 판정','모델 채점0회. 사후 canonical source 좌표와 최종 전체 evidence 패킷 동일성 검사.'),('사례 최종 판정',block(row))]
        (A/'실험'/q['file']).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(parts,1))+'\n')
        index+=f"|[{cid}]({q['file']})|{row['baseline_count']}|{row['first_count']}|{row['final_count']}|{row['gold_final']}/{row['gold_total']}|"+', '.join(x['document_name']+' '+x['heading'] for x in row['missing'])+'|\n'
    (A/'실험/README.md').write_text(index)
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(A.relative_to(R))],check=True)
    files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ('manifest.json','completion.json','validation-final.txt','graph-check.txt')]
    files += [A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',C/'candidate.json']+list(Path(__file__).parent.glob('*.py'))+[R/f['frozen_path'] for f in read(C/'candidate.json')['revisions'][-1]['files']]
    write(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen provenance selection input, original provider record, or offline audit'} for p in sorted(set(files))]})
    print(json.dumps(summary['totals'],ensure_ascii=False))

if __name__=='__main__':main()
