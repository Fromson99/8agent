"""Post-run descriptive audit; no product edits or new model calls."""
from pathlib import Path
import json,hashlib,re,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0844-comparison-source-return';D=A/'artifacts/design';O=A/'artifacts/run-001';C=O/'committee-duties-01'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');m=read(A/'실험/manifest.json');run=read(C/'result.json');a=read(C/'audit.json');body=read(C/'response.json')['body'];criteria=read(D/'criteria.json')
assert all(sha(R/n)==h for n,h in f['files'].items())
children=body.get('rag_results',{});stages=[]
for path in (C/'runtime').rglob('journal.sqlite'):
 if 'children' not in path.parts:continue
 with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
  for raw, in db.execute('SELECT body_json FROM model_view'):
   v=json.loads(raw);stages.append(v.get('source_stage',''))
checks={'originals_exact':a['original_span_mismatches']==0 if 'original_span_mismatches' in a else all(x['exact_original_match'] for x in a['evidence_span_checks']),
 'internal_whole_document':children.get('internal',{}).get('investigation_return',{}).get('acquisition',{}).get('documents',{}).get('11478916f48b00e5',{}).get('read_complete') is True,
 'native_sources_both':all(children.get(s,{}).get('bundle',{}).get('export_mode')=='SOURCE_HANDOFF' for s in ('internal','external')),
 'no_child_assess_compose':not any(s.startswith(('memory-assess','memory-compose')) for s in stages),
 'comparison_rows_returned':bool(body.get('report',{}).get('rows')),
 'one_table':sum(s.startswith('|---') for s in body.get('answer',{}).get('text','').splitlines())==1,
 'saved_duplicate':all(run.get('checks',{}).values()),'development32':'32 passed' in (A/'artifacts/development-tests.txt').read_text(),
 'additional2':'2 passed' in (A/'artifacts/additional-contracts.txt').read_text(),'frozen_code':True}
limits=['One known question, in_sample=true; no approved legal gold or accuracy certification.',
 'Candidate create_app with selected service.py dispatch was used; active pointer bootstrap is a separate promotion check.',
 'Native source return case terminal is committed, but child run journal status still remains RUNNING; deterministic terminal bookkeeping correction is required before promotion.',
 'Retrieval stage accounting was not predeclared in the scaffold before the model run. Counts below are post-run descriptive audit only; no retrieval gain or promotion decision is inferred from them.',
 'GENOS existing reference links are preferred by implementation and synthetic test. GENOS data and deployment have not been accessed.']
result={'status':'complete','development_checks_passed':all(checks.values()),'checks':checks,'tests_passed':34,
 'model_calls':run['model_calls'],'seconds':run['elapsed_seconds'],'rows':body.get('report',{}).get('rows',[]),
 'original_span_mismatches':sum(not x['exact_original_match'] for x in a['evidence_span_checks']),
 'children':{s:{'status':v['status'],'returned_evidence':len(v.get('evidence_ids',[])),'investigation_return':v.get('investigation_return')} for s,v in children.items()},
 'remaining_before_promotion':['native journal terminal bookkeeping'], 'quality_certified':False,'main_changed':False,'genos_deployed':False,'limitations':limits}
put(O/'result.json',result);put(D/'verification-binding-final.json',read(D/'verification-binding.json'))
# Descriptive counts: original read, returned and final cited coordinates (no relevance/gold judgment).
counts={'read':len({json.dumps(e['canonical'],sort_keys=True) for v in a['children'].values() for e in v['all_read_evidence'] if e.get('canonical')}),
 'returned':len({json.dumps(e,sort_keys=True) for v in a['children'].values() for e in v['canonical_adopted']}),
 'final_cited':len({json.dumps(e,sort_keys=True) for e in a['canonical_final']})}
put(O/'post-run-counts.json',{'prospectively_declared':False,'scope':'descriptive source receipt counts only','counts':counts,'golden_recall':None})
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','reason':'Prior MAIN80 result retained as descriptive context'},'sources':{'status':'complete','checks':checks}},comparisons=[],usage={'product_model_calls':run['model_calls'],'offline_evaluator_calls':0},latency={'seconds':run['elapsed_seconds']},error_taxonomy=[{'kind':'TERMINAL_BOOKKEEPING','detail':limits[2]}])
m['retrieval_accounting']['not_applicable_reason']='No valid prospective retrieval metric: stage plan was omitted before call. Post-run descriptive counts are in post-run-counts.json and cannot support a retrieval-effect claim.'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
q=m['questions'][0];p=A/'실험'/q['file'];heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
texts=['run-001 / sources / known in_sample question. No holdout claim.',read(D/'cases.json')[0]['question'],'Approved gold absent. No legal correctness score.', 'request.json / binding.json / health.json in ../artifacts/run-001/committee-duties-01', '../artifacts/run-001/committee-duties-01/raw/call-*/request.json and response.json; actual ExperimentClient receipts.', 'Actual native and parent journals plus audit.json retain prompts, failures, reads and decisions.', 'No evaluator LLM; exact original and status/duplicate checks only.',json.dumps(result,ensure_ascii=False,indent=2)]
p.write_text('# 지정 문서 전체 읽기와 원문 반환\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(p);put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. Four design changes implemented in an isolated344-file candidate; known live test and34contracts recorded. Native journal closure remains for a followup ADR.',
 'MAIN80 read partial named internal rules and required child legal judgment before returning sources.',criteria['hypothesis'],
 'Frozen known committee question once, Qwen3.8/Parasail FP8/reasoning none/no fallback. No product changes during the call.',
 'design/freeze.json binds candidate rev001 and data. Existing unrelated working changes and MAIN80 unchanged.',json.dumps(result,ensure_ascii=False,indent=2),
 'Return case status is SOURCES_RETURNED and no legal experience is accepted. Journal run status remains RUNNING: followup bookkeeping fix required. Native standalone20 regression and source12 contracts pass.',
 json.dumps({'calls':run['model_calls'],'seconds':run['elapsed_seconds'],'usage':run['usage'],'counts':counts},ensure_ascii=False),
 'Original availability and actual comparison can be observed; legal meaning remains reviewable LLM opinion.', '\n'.join(limits),
 'No MAIN promotion from this in-sample development ADR. Subsequent unchanged/limited-fixed code must pass prospectively frozen technical qualification and working/service integration.',
 'prepare.py; snapshot edits; run_tests.py; freeze.py; live.py committee-duties-01; audit.py; finish.py; stable validate --final; status completed; graph. Do not reuse completed call directories.']
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Proposed',meta)
(A/'README.md').write_text('---'+meta+'---\n\n# 지정 문서 읽기와 원문 반환\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'실험/README.md').write_text('# 알려진 질문의 실제 전체 대사\n\n위원회 질문1회. 실제 원문·모델 입출력과 저장·중복 소비자는 artifacts/run-001에 보존.\n')
(A/'RESULT.txt').write_text('대사 원문 반환 구현·개발 검증\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ('manifest.json','final-validation.txt','graph-final.txt') and not p.name.endswith(('-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen candidate and actual source-return development record','contains_raw_prompts_and_outputs':'raw' in p.parts} for p in paths]})
print(json.dumps({'checks':checks,'counts':counts,'calls':run['model_calls'],'seconds':run['elapsed_seconds']},ensure_ascii=False))
