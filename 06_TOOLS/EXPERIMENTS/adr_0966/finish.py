"""Assemble qualification evidence; reservation completion is a separate operation."""
from common import *
import statistics, xml.etree.ElementTree as ET

m=read(ADR/'실험/manifest.json'); assert m['reservation']['status']=='in_progress'
a=read(ART/'analysis.json'); assert a['strict_success'] and all(a['checks'].values())
s=read(ART/'stage.json'); assert all(sha(ROOT/n)==h and sha(ROOT/s['roots']['candidate']/n)==h for n,h in s['files']['candidate'].items())
f=read(ART/'design-freeze.json')
for n,h in f['design']['script_bindings'].items(): assert sha(ROOT/n)==h,(n,'runner drift')
for n,h in f['design']['test_bindings'].items(): assert sha(ROOT/n)==h,(n,'test drift')
ref=m['design']['inherited_contracts'];assert sha(ROOT/ref['path'])==ref['sha256']
suites=ET.parse(ART/'contracts-002.xml').getroot().findall('testsuite')
assert suites and all(int(x.get('failures',0))==int(x.get('errors',0))==0 for x in suites)
count=sum(int(x.get('tests')) for x in suites);assert count==260
assert 'glossary compiler/cache binding mismatch' in (ART/'consumer-candidate.log').read_text()
counts={arm:sum(r['pass'] for r in ts) for arm,ts in a['by_arm'].items()}
def binding(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
usage={k:sum(u.get(k) or 0 for u in a['usage']) for k in ('input_tokens','output_tokens','thinking_tokens','cost_usd')}
usage['physical_model_calls']=a['physical_model_calls']
latency={arm:{'p50_seconds':statistics.median(r['seconds'] for r in ts),'p95_seconds':sorted(r['seconds'] for r in ts)[round((len(ts)-1)*.95)],'physical_calls':sum(r['model_calls'] for r in ts)} for arm,ts in a['by_arm'].items()}
checks={**a['checks'],'all_applicable_260_contracts':True,'candidate_native_service_consumer':False,'working_native_service_consumer':False,'all_418_working_candidate_files_match':True,'frozen_scripts_and_tests_unchanged':True}
result={'strict_success':False,'model_navigation_success':True,'integration_status':'BLOCKED_CACHE_COMPILER_HASH','checks':checks,'source_delivery_counts':counts,'recovery_cases_passed':sum(r['pass'] and r['successful_name_retry'] for r in a['by_arm']['candidate'][:4]),
 'physical_model_calls':a['physical_model_calls'],'usage':usage,'latency':latency,'contracts':count,'contracts_execution':'Inherited exact same product/test bytes from ADR0965; not rerun or counted twice.',
 'analysis':binding(ART/'analysis.json'),'contract_result':binding(ART/'contracts-002.xml'),'inherited_contracts':ref,
 'consumers':{'failed_candidate':binding(ART/'consumer-candidate.log'),'working':'Not repeated: same code and same data compiler mismatch'},
 'limits':['Eight developer-authored synthetic tasks; both arms 8/8, no accuracy uplift established. Baseline can recover through other navigation tools.',
 'Candidate uses requested retry path in four of four name variants. Candidate 21 calls versus baseline20; median latency is higher in this run, so no speed or cost improvement claimed.',
 'Model trial covers source investigation and verified-original delivery. Full response/reuse consumer behavior is covered separately by deterministic API contracts.',
 'Seven recorded failures reproduced before this feature remain excluded; they are not fixed by this release.',
 'ADR0965 malformed structural fixture (54 calls) and its final record-format errors remain immutable and excluded from promotion evidence.',
 'Working text-length removal is fixed in both arms and included in the integrated release; paired baseline is not byte-identical MAIN97.',
 'GENOS, internal models, Oracle querying and general legal-answer quality are not certified. Post-promotion actual service binding has a separate audit and rollback gate.']}
save(ART/'result.json',result)
m['decision_eligible']=False
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={arm:{'status':'complete','correct':counts[arm],'total':8,'strict_success':False,'model_navigation_success':True,'actual_name_retry_matches':sum(r['successful_name_retry'] for r in ts)} for arm,ts in a['by_arm'].items()},comparisons=[a['comparison']],judge_disagreements=0,usage=usage,latency=latency,error_taxonomy=['No source-delivery failures in this synthetic set; seven pre-existing contract failures excluded and preserved.'])
retr=m['retrieval_accounting']
for metric in ('presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):retr[metric]={arm:v[metric] for arm,v in a['retrieval'].items()}
retr['before_filter']={arm:32*8 for arm in counts};retr['after_filter']=retr['presented_total'];retr['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
ledger=read(ART/'retrieval-ledger.json')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
paragraphs=[
 '모델 경로 검증은 통과했으나 실제 데이터 연결의 compiler/cache hash 충돌로 이 통합안은 승격하지 않는다. MAIN97 유지. 결과를 바꾸지 않고 후속 ADR에서 호환성 범위를 정리한다.',
 '이름 표기가 다르면 구조 조회가 실패할 수 있었다. 새 경로는 제목·별칭만 대상으로 형태소 검색을 수행해 최대8개 후보를 제시한다. RETRY_LAW_STRUCTURE에서 모델이 선택하며 원래 조문 조건·권한은 시스템이 유지한다. 이름 후보 자체는 인용 근거가 아니다.',
 m['design']['success_criteria']+'\n\n실행 전 기준·예산·데이터·코드·스크립트를 design-freeze.json에 고정했다. 결과를 보고 기준을 완화하지 않았다.',
 m['design']['sampling']+'\n\n'+m['design']['preexisting_work']+'\n\nMAIN97 계보는 ADR0964/integrated다. 무효 입력이었던 ADR0965는 informed_by 관계로만 연결하며 품질 근거로 사용하지 않는다.',
 '새 합성8문서·32조문, 8질문×2arm. 저장 legal_coordinate/key를 갖춘32조문 전부 구조 조회 사전 검사 통과. Qwen3.8 qwen/qwen3.8-27b / OpenRouter Parasail FP8 / reasoning none / fallback 없음. 실험 공통 ExperimentClient를 사용했다. 제품 입력과 grading-only.json은 분리했다. 질문당 arm별1회, 재채점·다수결·LLM judge 없음.',
 f'기존 {counts["baseline"]}/8, 변경 {counts["candidate"]}/8. paired both_correct=8, candidate_only=0, baseline_only=0, both_wrong=0. 이름 변형4/4에서 변경 arm의 RETRY_LAW_STRUCTURE MATCH와 해당 조문 원문 전달을 확인했다. 정확 이름2/2, 미존재 조문·권한 밖 문서2/2 통과. 동일 코드260계약 통과 결과를 해시로 상속했고 후보 HEALTH는 통과했으나 원문 세션 준비 시 기존 용어집 cache compiler 해시 불일치로 실패했다. 작업 코드는 같은 바이트이므로 중복 실패 실행은 생략했다.',
 '이 합성 세트의 전달 오류는0/8이다. 기준 arm도 문서 목차 등 다른 경로로 정답 원문을 찾았다. 없는 제99조는 이름 후보를 선택해 재조회한 뒤 원문을 전달하지 않았고, 허용 범위 밖 문서도 전달하지 않았다. 기존7계약 실패는 이전 코드에서도 재현되어 허용 목록으로 동결했으며 수정 완료로 처리하지 않는다.',
 json.dumps({'usage':usage,'latency':latency,'retrieval':a['retrieval']},ensure_ascii=False,indent=2)+'\n\n총41모델 호출(기준20, 변경21). 초기 무효 ADR0965의54호출은 별도 실패 이력과 비용이다. 후보 기사 원장은 메타데이터 이름 후보와 분리하며 정수 source_unit ID 0..3을 제1..4조에 대응시킨다. [정확 원장](artifacts/retrieval-ledger.json)과 [질문별 원시 호출](실험/README.md)을 참조한다.',
 '확인된 것은 명시적 이름 복구 도구의 작동과 이 세트에서의 회귀 부재다. 정확도 향상은 관찰되지 않았고 후보 호출 수·중앙 지연도 감소하지 않았다. 작은 세트의 속도 수치를 일반화하지 않는다.',
 '\n\n'.join(result['limits']),
 '원문·권한·조문·상태·해시 위반과 활성 서비스 불일치는 승격 차단/복원 사유다. release-rebase.json으로418개 서빙 파일을 결속하며 데이터·모델 프로필·선택 색인을 유지한다. stable runner의 prepare 후 --confirm-main으로 적용하고 실제 service.service.application() 선택을 검사한다. MAIN97과 복원 receipt를 보존한다. GENOS 반입·배포, Git commit/push는 범위에 없다.',
 '재현 진입점: 06_TOOLS/EXPERIMENTS/adr_0966/{build_synthetic,run_trials,run_case,analyze,seal_release,consumer}.py. 완료된 모델 호출을 덮어쓰지 않는다. .venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0966-law-name-bound-holdout --final 및 graph를 사용한다. [산출물 해시](artifacts/manifest.json), [후보·통합](artifacts/integration.json), [불변 코드418개](artifacts/stage.json).'
]
front=(ADR/'README.md').read_text().split('---',2)[1].replace('decision_eligible: true','decision_eligible: false')
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0966: 법령명 복구 도구·원문 전달과 로컬 MAIN 통합 검증\n\n'+''.join(f'## {i}. {h}\n\n{p}\n\n' for i,(h,p) in enumerate(zip(heads,paragraphs),1)))
cases={x['id']:x for x in read(ART/'cases.json')};gold={x['case_id']:x for x in read(ART/'grading-only.json')}
index=['# ADR-0966 실험 질문 인덱스','신규 합성8사례, 기준8/8·변경8/8, 이름 재조회4/4. Qwen3.8 실제41호출. 채점은 선택 완료 후 원문/좌표 동일성으로 수행했다. 법률 답변 품질 평가가 아니다.','| 사례 | 기준 | 변경 | 이름 재조회 MATCH | 원시 기록 |','|---|---|---|---|---|']
for q in m['questions']:
    cid=q['case_id'];chunks=[f'# 질문 {q["number"]:03d} — {cid}','## 1. 실행 메타','ADR-0966 / run-001 / baseline,candidate / temperature0 / reasoning none / Parasail FP8 / no fallback / 각1회.','## 2. 사용자 질문 원문',cases[cid]['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',json.dumps(gold[cid],ensure_ascii=False),'## 4. 제품 입력을 구성한 원값','[동결 질문·권한 범위](../artifacts/cases.json), [합성 문서](../artifacts/documents.json), [32저장좌표 사전 검사](../artifacts/fixture-preflight.json). 모델에 기대 조문 ID나 채점 데이터는 주지 않았다.','### 회수·탈락 단계 원장 — run·arm별','[정확 identity·추가·탈락 사유와 hash](../artifacts/retrieval-ledger.json). 정수 node0..3은 해당 합성 문서의 제1..4조다. 이름 후보는 기사 원장·인용에서 제외한다.','| arm | stage | before→after | added/discarded | gold before→after |','|---|---|---:|---:|---:|']
    for armrec in ledger['runs'][0]['arms']:
        rec=next(x for x in armrec['cases'] if x['case_id']==cid)
        for st in rec['stages']:chunks.append(f'| {armrec["arm_id"]} | {st["stage_id"]} | {st["before_count"]}→{st["after_count"]} | {st["added_count"]}/{st["discarded_count"]} | {st["gold_before"]}→{st["gold_after"]} |')
    chunks.append('## 5. 제품 모델 호출 — run·arm별 실제 원문')
    for arm in ('baseline','candidate'):
        folder=ART/'trials'/cid/arm;chunks.append(f'### run-001 / {arm}\n\n[전체 입력·관찰·상태·결과](../artifacts/trials/{cid}/{arm}/result.json)')
        for call in sorted((folder/'model').glob('call-*')):
            chunks.append(' '.join(f'[{call.name}/{p.name}](../artifacts/trials/{cid}/{arm}/model/{call.name}/{p.name})' for p in sorted(call.glob('*.json'))))
        item=next(r for r in a['by_arm'][arm] if r['case_id']==cid);chunks.append(json.dumps(item,ensure_ascii=False))
    chunks+=['## 6. 중간 LLM 호출 — router/compiler/verifier/repair','구조 탐색·선택·수정 요청을 포함한 실제 호출은 위 원시 JSON에 전부 보존했다. 별도 숨은 모델/평가 호출은 없다.','## 7. 채점 호출과 반복 판정','LLM judge 없음. 동결된 기대 source coordinate와 검증된 selected_originals를 결정적으로 비교했다. legacy read_scopes는 v8 전달 근거가 아니므로 사용하지 않았다. 동일 결과를 재생성하거나 재채점하지 않았다.','## 8. 사례 최종 판정','기준·변경 모두 통과. 이름 재조회 수행 여부·원문 일치·권한·조문 보존·호출수는 [analysis.json](../artifacts/analysis.json)에 연결된다.']
    path=ADR/'실험'/q['file'];path.write_text('\n\n'.join(chunks)+'\n');q['sha256']=sha(path)
    cr=next(x for x in a['by_arm']['candidate'] if x['case_id']==cid);index.append(f'| {cid} | PASS | PASS | {cr["successful_name_retry"]} | [{q["file"]}]({q["file"]}) |')
(ADR/'실험/README.md').write_text('\n\n'.join(index[:2])+'\n\n'+'\n'.join(index[2:])+'\n\n계보·동결 기준·단계별 집계·판정은 [manifest.json](manifest.json), [정확 원장](../artifacts/retrieval-ledger.json)에 보존했다. 원시 모델 입력/출력은 질문별 링크에서 확인한다.\n')
save(ADR/'실험/manifest.json',m)
files=[]
for p in sorted(ART.rglob('*')):
    if not p.is_file() or p==ART/'manifest.json' or any(x.startswith('runtime-') or x=='runtime' for x in p.relative_to(ART).parts):continue
    files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen paired source-navigation qualification or exact integration evidence','contains_raw_prompts_and_outputs':'model' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':files})
print('Model outcomes preserved; integration blocked;  validate before completing reservation',counts,usage)
