"""Record the fixed technical checks and separate the known live observation."""
from pathlib import Path
import json,hashlib,subprocess,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0800-workflow-literal-request-quotes';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');live=read(A/'artifacts/live/result.json');response=read(A/'artifacts/live/response.json')['body']
restart=read(A/'artifacts/live/restart-check.json');base=read(A/'artifacts/replay/baseline.json');candidate=read(A/'artifacts/replay/connected.json')
rows=response['report']['rows'];tests=(A/'artifacts/tests-final.txt').read_text()
views=[]
for p in sorted((A/'artifacts/live/raw').glob('*/request.json')):
    for message in read(p).get('messages',[]):
        try:v=json.loads(message.get('content','')).get('view',{})
        except (ValueError,AttributeError):continue
        if v.get('source_stage') in ('workflow-basis','workflow-compare'):
            views.append({'call':p.parent.name,'stage':v['source_stage'],'chars':len(json.dumps(v,ensure_ascii=False)),
                          'source_count':len(v.get('sources',[]))})
checks={'all_278_contracts_pass':'278 passed' in tests,'four_source_ui_checks':read(A/'artifacts/ui-check.json')['status']=='PASS',
    'frozen_files_unchanged':all(sha(R/n)==h for n,h in f['files'].items()),
    'same_recorded_claim_dependencies_preserved':candidate['selected']==read(R/'04_EXPERIMENTS/ADR/ADR-0799-workflow-handoff-task-context/artifacts/replay/connected.json')['selected'] and len(candidate['selected'])==11,
    'recorded_handoff_reduced_within_limit':base['evidence_count']==94 and candidate['evidence_count']==16 and candidate['view_chars']<100000,
    'actual_service_both_children_returned':all(response['rag_results'][s]['status'] in ('completed','partial') and response['rag_results'][s]['evidence_ids'] for s in ('internal','external')),
    'actual_comparison_rows':bool(rows),
    'actual_model_views_bounded':bool(views) and all(v['chars']<=100000 for v in views),
    'status_duplicate_no_model_recall':all(live['checks'].values()),
    'fresh_process_same_result_budget_sources':all(restart['checks'].values()),
    'source_generation_unchanged':sha(R/read(D/'data-binding.json')['path']/'manifest.json')==read(D/'data-binding.json')['manifest_sha256']}
limits=['Finite technical boundary qualification, not legal answer accuracy certification. Known liquidity question and recorded ADR0795 results are explicitly in-sample observations.',
    'Native RAG may still select irrelevant material or miss the required liquidity rules. Committed claim evidence is not certified legal truth.',
    'Missing verified applicability/version or complete conditions keeps comparison DEFERRED. No invented effective date or inferred source absence.',
    'Exact request quote choices bind whole original question when short; long questions use literal coordinate partitions under the existing 2000-character quote limit. This does not determine issue semantics.',
    'GENOS is inaccessible and not deployed; local MAIN and field deployment are separate.',
    'Earlier ADR0797/0798/0799 failures are preserved. The older direct-request test failed equally on MAIN73 and candidate because per-request metrics differ; the corrected contract verifies stable answer and zero repeated model calls.']
by={'baseline':{'status':'complete','handoff':base},'connected':{'status':'complete','handoff':candidate,'contract_passed':278,
    'actual_compare_rows':len(rows),'reported_source_count':len(response['evidence_refs']),'technical_integrity_qualified':all(checks.values())}}
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'by_arm':by,
    'qualification_scope':'Prospectively frozen finite technical handoff/source/state/consumer audit; known live observation separately reported',
    'known_case_in_sample':True,'live_status':response['status'],'live_view_sizes':views,'live_verdicts':[r['verdict'] for r in rows],
    'usage':{'product_model_calls':live['model_calls'],'offline_evaluator_calls':0,'cost_usd':sum(u.get('cost_usd',0) for u in live['usage'])},'limitations':limits}
put(A/'artifacts/run-001/result.json',result)
if not result['strict_success']:raise RuntimeError('Unqualified result: '+json.dumps(checks))
subprocess.run(['.venv/bin/python','06_TOOLS/EXPERIMENTS/adr_0800/ledger.py'],check=True,stdout=subprocess.DEVNULL)
p=A/'실험/질문-001-K01.md';s=p.read_text()
s=s.replace('별도 실제 Qwen 호출6건 원문은',f"별도 실제 Qwen 호출{live['model_calls']}건 원문은")
s=s.replace('INTAKE1, 자식 진입/수정4, BASIS1. 실제 새 질문의 인용 오류로 자식 조사 실패.', '원래 사용자 질문과 조사 범위를 분리하고 인용 선택지를 정확 원문에 결속했다. 실제 호출별 단계는 live/raw, 사용량은 live/result.json에 보존한다.')
s=s.replace('실제 실행은 자식 질문 인용 실패로 비교0행이므로 후보를 기각한다.',f"실제 실행은 {response['status']}, 비교 {len(rows)}행, 표시 근거 {len(response['evidence_refs'])}개다. 판정 내용·정답 정확도는 인증하지 않는다.")
p.write_text(s)
m=read(A/'실험/manifest.json');m['questions'][0]['sha256']=sha(p);m['decision_eligible']=True
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm=by,usage=result['usage'],latency={'known_observation_seconds':live['elapsed_seconds']},
    error_taxonomy=['SOURCE_SCOPE_HASH_STATE_REFUSED','NONLITERAL_QUOTE_REFUSED','INCOMPLETE_PAIR_DEFERRED','UNKNOWN_DELIVERY_NOT_RETRIED','UNVERIFIED_APPLICABILITY_PRESERVED'])
put(A/'실험/manifest.json',m)
parts=[('결정 요약','Accepted promotion-candidate. 채택된 원문 span만 전달하고 현재 revision의 비교·표시에 연결한다. 실제 소비자 검사까지 통과한 기술 경계 감사이며 법률 정답률 인증은 아니다.'),
    ('문제와 변경 전 구조','MAIN73은 자식 조사에서 읽은 모든 원문을 부모 비교로 복사했다. 동일 기록에서94근거·128976자가 전달되어 입력 한도를 넘었다. 후속 후보의 외규 진입에서는 모델이 사용자 인용에 조사 지시를 덧붙였다.'),
    ('가설과 사전 판정 기준','design/criteria.json은 후보 수정 전에 동결했다. 채택 원문·조건 의존성·해시·권한·최신 상태·입력 한도·복구·재시작·최종 표시·실제 비교 소비자를 검사한다.'),
    ('실험 설계','기준 MAIN73과 완료된 ADR0799/connected 위의 rev001. 합성 기술278계약, UI4검사, 같은 기록 재생, 실제 알려진 질문1회 및 새 프로세스 재사용. 일반화된 의미 품질 평가는 수행하지 않았다.'),
    ('데이터·모델·재현성','원문/색인/최신 선택/정의 최초 검색을 유지했다. Qwen3.8/Parasail FP8/reasoning none/fallback 없음. 공통 ExperimentClient, 총40회·1800초 및 기존 복구 한도를 유지한다.'),
    ('결과',json.dumps({k:v for k,v in result.items() if k not in ('by_arm','limitations')},ensure_ascii=False)),
    ('사례별 오류 분석','이전 실패 인용을 자동으로 잘라 채택하지 않는다. 새 후보는 원문 선택지로 생성 계약을 제한하고 기존 원문 검사를 그대로 수행한다. ASSESS가 채택한 span의 새 정규 ID를 만들며 조사 원장은 별도 보존한다. 최종 비교에서도 전달된 원문 완전성과 판본을 재검사한다.'),
    ('비용·지연·회수 규모',f"같은 기록 재생:94→16근거,45088→1132원문자,128976→26301입력자. 채택 의존 조문11개 전부 보존. 실제 모델{live['model_calls']}회/{live['elapsed_seconds']:.2f}초. 실제 결과는{len(rows)}행·표시{len(response['evidence_refs'])}근거. 비용·속도의 일반화 수치가 아니다."),
    ('해석','검색 범위는 넓게 유지하고 확정된 판단의 채택 근거를 전달한다. 조건·예외·명시 참조가 부족하면 이미 읽은 원문 문맥을 우선 재사용한다. 전달량 감소만으로 정확도 향상을 주장하지 않는다.'),
    ('한계와 일반화 가능 범위','\n\n'.join(limits)),
    ('운영 결정·롤백 조건','해시 고정 후보를 로컬 MAIN73 위에 승격하고 변경한 작업 파일만 통합한다. 선택 릴리스와 같은 파일·프로필·데이터·검색 정책으로 실제 로컬 진입점을 확인한다. 이전 포인터와 적용 영수증을 원복에 사용한다. GENOS 반입은 별도다.'),
    ('재현 명령','06_TOOLS/EXPERIMENTS/adr_0800의 run_tests/replay/live/restart_check/ui_check. 완료 원시 기록은 덮어쓰지 않는다. stable adr_structure validate --final/graph, rag_main_promotion prepare/apply --confirm-main.')]
meta=f"---\nadr_id: ADR-0800\ntitle: 대사 채택 근거 전달과 원문 인용 선택\nstatus: Accepted\ndecision_date: 2026-10-15\nphase: audit\nin_sample: false\ndecision_eligible: true\nmain_wiring: promotion-candidate\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 대사 전달 경계 기술 감사\n\n278개 계약, UI4검사, 실제 서비스·재시작. [K01 알려진 사례](질문-001-K01.md)는 의미 품질 holdout이 아니다.\n')
subprocess.run(['.venv/bin/python','06_TOOLS/run_tool.py','adr_structure.py','status','--path',str(A),'--status','completed','--note','Finite handoff integrity and actual comparison consumer qualified; semantic limitations explicitly retained'],check=True,stdout=subprocess.DEVNULL)
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and 'runtime' not in p.parts]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0800','created_at':m['reservation']['created_at'],
    'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Technical boundary and known live observation','contains_raw_prompts_and_outputs':'raw' in p.parts} for p in files]})
print('PASS',len(checks),'checks; actual rows',len(rows))
