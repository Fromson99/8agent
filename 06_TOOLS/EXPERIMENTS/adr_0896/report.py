from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0896-cm-read-continuity-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-0895-committed-answer-consistency';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');C=R/f['code_root'];before=read(D/'working-before.json');m=read(A/'실험/manifest.json');prior=read(P/'artifacts/run-001/result.json');consumer=read(A/'artifacts/candidate-consumer.json');integration=read(D/'integration.json')
changes=[n for n,h in before.items() if sha(C/n)!=h]
products=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('completion_execution','completion_v6','completion_contracts','decision_projection','definition_entry','evidence_inventory','gateway','law_navigation','narrative_answer','relation_read_policy','request_entry','request_repair','unit_relations','unified_runtime')]
resources=[read(p) for p in sorted((P/'artifacts').glob('resource-cm-*.json'))]
allowed=lambda n:n in products or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') and n.endswith('.json')
checks={'frozen_code_inputs':all(sha(R/n)==h for n,h in f['files'].items()),
 'working_MAIN86_preserved':all(sha(R/n)==h for n,h in before.items()),
 'pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256'],
 'same_code605_regressions':'605 passed, 140 deselected' in (P/'artifacts/candidate-api.log').read_text() and read(P/'artifacts/design/freeze.json')['code_root']==f['code_root'],
 'new20_and44_retained':'64 passed' in (A/'artifacts/boundary-tests.log').read_text(),
 'candidate_actual_service10':consumer['status']=='PASS' and len(consumer['checks'])==10 and all(consumer['checks'].values()),
 'all8_actual_responses':prior['http200_cases']==8 and prior['model_calls']==152,
 'all2529_original_checks_exact':prior['original_evidence_checks']==2529 and prior['original_mismatches']==0,
 'all8_within_resource_limits':len(resources)==8 and all(x['returncode']==0 and x['stop_reason'] is None for x in resources),
 'technical_resource_limits':all(read(A/'artifacts'/n)['returncode']==0 and read(A/'artifacts'/n)['stop_reason'] is None for n in ('boundary-resource.json','candidate-consumer-resource.json')),
 'reviewed45_deltas_only':len(changes)==45 and all(allowed(n) for n in changes) and all(n in changes for n in products) and {n for n in changes}=={x['path'] for x in integration['changes']},
 'recent_MAIN_compression_workflow_preserved':all(sha(C/n)==before[n] for n in ('02_BACKEND/semantic_runtime/legal_agent/minimal_output.py','02_BACKEND/semantic_runtime/legal_agent/wire_schema.py','02_BACKEND/workflow/presentation.py','02_BACKEND/workflow/risk_team_compare_workflow/basis.py','02_BACKEND/workflow/risk_team_compare_workflow/compare.py','02_BACKEND/workflow/risk_team_compare_workflow/task_board.py','00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'))}
assert all(checks.values()),checks
remaining=['CM003 original26 and23(4)2 were acquired, but third-party allotment was overgeneralized as sufficient for3 without full timing/exception conditions; mandatory category exclusion softened. Core fail; not fixed by retrieval alone.',
 'Generic additional-source/fact or unverified-scope footers remain, including adequately answered questions. Some repeated search/review and excessive narrative persist.',
 'CM001/008/033/051/011/022/038 core pass in this known run only. Peripheral wording/inferences are recorded in manual review; not exhaustive legal correctness certification.',
 'CM022 andCM038 frozen gold IDs differ from selected structured original IDs. Selected metadata dates and exact text are audited separately; frozen ledger recall is not retroactively relabeled.',
 '140 legacy/incompatible contract cases deselected with preserved prior disposition;669pass is scoped verification, not all repository tests passing.',
 'Actual8model trials use service.py RAG_ASK. Comparison1.10.0/discovery1.0.0 wiring and authorization get technical checks, not8full parent comparison workflow model executions.',
 'Peak observed8caseRSS about3.13GiB under external research allocator controls; not a production/GENOS RAM guarantee.',
 'GENOS internal model/field deployment, Gitmain merge/push and resident local server restart not performed.']
result={'status':'complete','strict_success':True,'checks':checks,'changes':changes,'candidate':f['candidate'],'technical_tests':669,'same_code_regression_tests':605,'new_finite_tests':20,'retained_additional_tests':44,'deselected':140,'model_calls':0,'known_parent_model_calls':152,'known_parent_result':str((P/'artifacts/run-001/result.json').relative_to(R)),'legal_quality_certified':False,'core_pass':7,'http200':8,'original_checks':2529,'original_mismatches':0,'peak_known_case_rss_bytes':max(x['peak_group_rss_bytes'] for x in resources),'remaining':remaining}
put(A/'artifacts/run-001/result.json',result)
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={'qualified':{'status':'complete','strict_success':True,'checks':checks}},usage={'product_model_calls':0,'offline_evaluator_calls':0,'known_parent_calls':152},error_taxonomy=[{'kind':'known_semantic_limitations','details':remaining}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 p=A/'실험'/q['file'];parts=['run-001/qualified; unchanged0895candidate.','CM008search/completion andCM003/051insufficiency; preserve recentMAIN; sameCM5+extra3, seriallowRAM.','20finite software boundaries, not legal gold or unseen legal examples.','design/freeze.json andqualification-tests.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nFinite technical census has no model retrieval. Completed0895CM8ledger preserved unchanged.','No model calls in qualification. Parent0895preserves152actual calls and raw archive percase.','No new router/compiler/verifier/model calls; technical scripted failure cases only.','605samecode+20new+44retained=669pass,140deselected with disposition. Candidate actualservice10checks.',json.dumps(result,ensure_ascii=False)]
 p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
meta=(A/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=['Accepted finite technical qualification. CM003semantic error remains explicit; technical acceptance does not certify legal correctness.','Cross-window originals and partial article offers could be lost; bounded reference decisions raised instead of preserving unresolved originals; committed/public limitation lists diverged.',json.dumps(read(D/'criteria.json'),ensure_ascii=False),'20new finite boundaries+44retained technical cases;605samecodesuite inherited; no product edits or newmodelcalls.','Immutable711files/370servingfiles from0895; sharedMAIN86generation/profile. Actualparent8CM trials useQwen3.8ParasailFP8reasoningnone/no fallback.',json.dumps(result,ensure_ascii=False),json.dumps(read(P/'artifacts/run-001/manual-review.json'),ensure_ascii=False),'Qualification0modelcalls. Parent152calls,8HTTP200,7corepass;2529exactoriginalchecks; shared data and compressed raw histories.','Read continuity and reference recovery improve delivered evidence; source correctness remains separate from legal interpretation.','KnownCM8are in-sample. Technical finite census is not legal holdout. Workflow wiring checks are not actual parent comparison end-to-end trials.','Integrate45reviewed deltas only after validation; verifyworking andactive actualservice; stablehash-pinned MAIN87promotion; preserveMAIN86rollback.','prepare.py; resource_guard+0895run_tests64; resource_guard+consumer.py candidate; report.py; stablevalidatefinal; promote_main integrate/prepare; stableapply; activeconsumer andfinish.']
(A/'README.md').write_text('---'+meta+'---\n\n# CM 읽기 연속성과 응답 계약 독립 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n')
(A/'실험/README.md').write_text('# 검증\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Independent qualification evidence','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json' and not p.name.endswith(('-wal','-shm'))]})
print('Accepted finite qualification:669scopedtests,45deltas,knownCM8core7/8')
