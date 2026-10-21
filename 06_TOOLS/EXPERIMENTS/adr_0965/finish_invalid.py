"""Preserve the initial trial as invalid fixture evidence, never promotion proof."""
from common import *
import statistics,collections
m=read(ADR/'실험/manifest.json');analysis=read(ART/'analysis.json')
counts={arm:sum(r['pass'] for r in trials) for arm,trials in analysis['by_arm'].items()}
result={'strict_success':False,'checks':{**analysis['checks'],'valid_structural_fixture':False},
 'status':'INVALID_FIXTURE','physical_model_calls':analysis['physical_model_calls'],'source_delivery_counts':counts,
 'reason':'Synthetic source_unit has coordinate_scope but lacks legal_coordinate and coordinate_key. Runtime correctly marks PARTIAL_STORED_SCOPE_KEY/unresolved and refuses direct article lookup. Name choices and alternative-path reads are not a valid evaluation of the requested retry flow.',
 'product_code_changed':False,'promotion_allowed':False,'analysis':{'path':str((ART/'analysis.json').relative_to(ROOT)),'sha256':sha(ART/'analysis.json')},
 'limits':['First source delivery grading uses authoritative selected_originals. The runner also saved legacy read_scopes-derived selected, which is empty for v8 delivered_context_only results; no product output was changed.','No legal-answer quality measurement; follow-up must use a new ADR and new questions.']}
save(ART/'result.json',result)
m['decision_eligible']=False;m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={arm:{'status':'complete','correct':counts[arm],'total':8,'qualification':'invalid_fixture'} for arm in counts},comparisons=[analysis['comparison']],judge_disagreements=0,
 usage={'physical_model_calls':analysis['physical_model_calls'],'input_tokens':sum(x.get('input_tokens') or 0 for x in analysis['usage']),'output_tokens':sum(x.get('output_tokens') or 0 for x in analysis['usage'])},latency={'per_trial_seconds':{a:[r['seconds'] for r in ts] for a,ts in analysis['by_arm'].items()}},error_taxonomy=['authority_or_version: missing synthetic coordinate binding','retrieval_miss: unresolved fixture'])
retr=m['retrieval_accounting']
for metric in ('presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):retr[metric]={a:v[metric] for a,v in analysis['retrieval'].items()}
retr['before_filter']={a:32*8 for a in counts};retr['after_filter']=retr['presented_total']
retr['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
paragraphs=[
 'Invalid synthetic fixture; not accepted and not eligible for MAIN. All raw outputs and setup failures are preserved.',
 result['reason'],m['design']['success_criteria'],m['design']['sampling']+' '+m['design']['preexisting_work'],
 'Qwen3.8 / Parasail FP8 / none reasoning. Frozen synthetic corpus, no real or internal documents. Product runner never loads grading-only.json.',
 str(counts)+' source-delivery outcomes on invalid structural input; this is not a supported retrieval quality comparison.',
 'Name selection was observed. Direct coordinate retries were refused because the fixture lacked required stored keys; alternative reads sometimes delivered originals. Test-construction failure is not product failure or evidence of real corpus absence.',
 str(m['results']['usage'])+'; exact per-call usage/latency in trials/*/*/model. Source accounting joins gold only after all choices.',
 'The lookup must retain the integrity refusal. Repair the synthetic source fields in a new ADR rather than relax runtime validation.',
 'Eight developer-authored synthetic tasks, malformed coordinate binding, no legal-answer scoring, no GENOS execution.',
 'Keep MAIN97 unchanged. New ADR must use complete stored legal coordinates and fresh questions; candidate product bytes can stay identical.',
 'run_trials.py preserves fixed-order raw runs; analyze.py performs exact post-selection source delivery scoring. Do not overwrite completed trials.'
]
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
old=(ADR/'README.md').read_text();front=old.split('---',2)[1].replace('decision_eligible: true','decision_eligible: false')
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0965: 법령명 복구 조회 — 합성 구조 계약 누락 기록\n\n'+''.join(f'## {i}. {h}\n\n{p}\n\n' for i,(h,p) in enumerate(zip(heads,paragraphs),1)))
index=['# 실행 사례\n\n초기 합성 구조 계약 누락으로 승격 불가. 실제 원시 호출은 각 질문의 파일 링크에 보존했다.\n']
cases={c['id']:c for c in read(ART/'cases.json')};gold={c['case_id']:c for c in read(ART/'grading-only.json')}
for q in m['questions']:
    cid=q['case_id'];chunks=[f'# 질문 {q["number"]:03d} — {cid}', '## 1. 실행 메타','ADR-0965 / run-001 / baseline,candidate / exact / Qwen3.8; offline deterministic source identity matching; no LLM judge.',
        '## 2. 사용자 질문 원문',cases[cid]['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',json.dumps(gold[cid],ensure_ascii=False),
        '## 4. 제품 입력을 구성한 원값','[동결 합성 문서](../artifacts/documents.json), [질문](../artifacts/cases.json), [회수·탈락 단계 원장](../artifacts/retrieval-ledger.json). 이름 후보는 조문 존재 근거가 아니다.',
        '## 5. 제품 모델 호출 — run·arm별 실제 원문']
    for arm in ('baseline','candidate'):
        folder=ART/'trials'/cid/arm
        chunks.append(f'### run-001 / {arm}\n\n[전체 결과·모델 관찰](../artifacts/trials/{cid}/{arm}/result.json)')
        for call in sorted((folder/'model').glob('call-*')):
            chunks.append(' '.join(f'[{call.name}/{p.name}](../artifacts/trials/{cid}/{arm}/model/{call.name}/{p.name})' for p in sorted(call.glob('*.json'))))
        item=next(r for r in analysis['by_arm'][arm] if r['case_id']==cid);chunks.append(json.dumps({k:v for k,v in item.items() if k!='error'},ensure_ascii=False))
    chunks += ['## 6. 중간 LLM 호출','All navigation and correction calls are in the exact model files above. No omitted hidden judge.',
        '## 7. 채점 호출','No LLM judge. Initial deterministic grading checks the frozen expected article against verified delivered selected_originals; legacy read_scopes is not used as delivery proof.',
        '## 8. 사례 판정','Invalid structural fixture; results are retained without promotion. Complete per-arm outcomes and reasons: [analysis.json](../artifacts/analysis.json).']
    path=ADR/'실험'/q['file'];path.write_text('\n\n'.join(chunks)+'\n');q['sha256']=sha(path);index.append(f'- [{cid}]({q["file"]})')
(ADR/'실험/README.md').write_text('\n'.join(index)+'\n')
save(ADR/'실험/manifest.json',m)
files=[]
for p in sorted(ART.rglob('*')):
    if not p.is_file() or p==ART/'manifest.json' or any(x.startswith('code-') or x=='runtime' for x in p.relative_to(ART).parts):continue
    files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen trial or diagnostic evidence, invalid fixture retained','contains_raw_prompts_and_outputs':'model' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':files})
print('Completed invalid-fixture record',counts,'calls',analysis['physical_model_calls'])
