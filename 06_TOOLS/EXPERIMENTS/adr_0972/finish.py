"""Preserve the completed failed qualification without weakening frozen criteria."""
from common import *
import statistics
m=read(ADR/'실험/manifest.json');a=read(ART/'analysis.json');assert not a['strict_success']
f=read(ART/'design-freeze.json')
for kind in ('script_bindings','test_bindings'):
    for n,h in f['design'][kind].items():assert sha(ROOT/n)==h,n
counts={k:sum(x['pass'] for x in v) for k,v in a['by_arm'].items()}
usage={k:sum(u.get(k) or 0 for u in a['usage']) for k in ('input_tokens','output_tokens','thinking_tokens','cost_usd')};usage['physical_model_calls']=a['physical_model_calls']
latency={arm:{'p50_seconds':statistics.median(r['seconds'] for r in ts),'p95_seconds':sorted(r['seconds'] for r in ts)[round((len(ts)-1)*.95)]} for arm,ts in a['by_arm'].items()}
result={'strict_success':False,'checks':a['checks'],'status':'REJECTED_FOR_MAIN','correct':counts,'total_per_arm':32,'physical_model_calls':a['physical_model_calls'],'usage':usage,'latency':latency,
 'reason':'Frozen exact-scope criteria failed. In initial entry outputs, the optional search_scope_change field may be omitted; query strings do not preserve the requested structural set.',
 'contracts':'Not repeated after semantic scope gate failed. Prior deterministic feature tests are preserved separately and are not substituted for live LLM outcomes.',
 'main_changed':False,'genos_zip_created':False,'quality_certified':False,
 'limits':['32 developer-authored synthetic cases; one native planning decision plus repair and actual original READ, not full answering.', 'Direct original READ is exercised after the selected metadata set; model acknowledgement and answer correctness are not measured by this experiment.', 'External Qwen3.8 results do not certify GENOS internal models.']}
save(ART/'result.json',result);m['decision_eligible']=False;m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={arm:{'status':'complete','correct':counts[arm],'total':32,'strict_success':False} for arm in counts},comparisons=[a['comparison']],judge_disagreements=0,usage=usage,latency=latency,error_taxonomy=['MODEL_OPTIONAL_SCOPE_OMISSION','WRONG_OR_INCOMPLETE_STRUCTURAL_SET'])
ret=m['retrieval_accounting']
for metric in ('presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):ret[metric]={arm:r[metric] for arm,r in a['retrieval'].items()}
ret['before_filter']={arm:8*32 for arm in counts};ret['after_filter']=ret['presented_total'];ret['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
paragraphs=['Rejected. 현재 후보는 고정한 원문 범위 조건을 충족하지 못했다. MAIN98 유지, 이 후보의 GENOS 인계 ZIP 미생성. 후속 수정·재실험은 새 ADR로 분리한다.',
 '범위·열거·제외를 LLM 구조화 selection으로 표현하고 실제 저장 조항 집합을 읽는 구현을 기존 MAIN98과 비교했다. 초기 질문 판별의 search_scope_change 필드가 선택 사항이어서 모델이 검색어만 출력하는 문제가 실제 호출에서 나타났다. 정규표현식으로 범위를 추측해 보정하지 않는다.',
 m['design']['success_criteria'],m['design']['sampling']+'\n\n'+m['design']['preexisting_work'],
 '32 신규 합성 질문 ×2 arm, 문서2개·조8개·저장노드232개. 데이터와 기준답변은 물리적으로 분리했고 제품 실행기는 grading-only.json을 읽지 않는다. 저장 좌표232개 및 모의 연결4개 사전 검사 후 실제 호출했다. Qwen3.8 / Parasail FP8 / reasoning none / no fallback. 코드419개와 각 arm·스크립트·테스트를 첫 호출 전에 동결했다.',
 json.dumps({'correct':counts,'checks':a['checks'],'comparison':a['comparison']},ensure_ascii=False,indent=2),
 '각 사례의 기대/실제 원문 블록, 추가·누락, 모델 결정·원시 호출·오류를 [analysis.json](artifacts/analysis.json)과 질문별 문서에 보존했다. CASE 판별이 맞아도 범위 구조화 생략은 통과가 아니다. 모델 호출 실패를 원문 부재로 기록하지 않았다.',
 json.dumps({'usage':usage,'latency':latency,'retrieval':a['retrieval']},ensure_ascii=False,indent=2),
 '결정적 단위 검사에서 구조화 객체 실행이 맞더라도 실제 모델이 그 객체를 출력한다는 보장은 없었다. 구조화 판단 필드의 필수 출력과 구체적 출력 계약이 필요하다. 이 결과를 성공으로 재채점하거나 기존 기준을 완화하지 않는다.',
 '\n\n'.join(result['limits']),
 '이 ADR은 MAIN 승격하지 않는다. 선택 MAIN98과 GENOS 현장 상태는 변경하지 않았다. 후속 후보는 새 ADR 선점·코드 snapshot·기준 동결 뒤 별도 새 표현으로 검증한다. 인용·권한·해시·상태 오류와 제외 범위 재포함은 계속 차단 기준이다.',
 '06_TOOLS/EXPERIMENTS/adr_0972/{prepare,build_synthetic,freeze,run_case,run_trials,analyze,finish}.py. 완료 모델 호출은 재실행해 덮어쓰지 않는다. validate --final 및 graph는 stable runner로 수행한다. [실험 manifest](실험/manifest.json), [코드](artifacts/stage.json), [사전 기준](artifacts/design-freeze.json), [원장](artifacts/retrieval-ledger.json).']
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected').replace('decision_eligible: true','decision_eligible: false')
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0972 구조화 집합 선택 실제 모델 검증\n\n'+''.join(f'## {i}. {h}\n\n{p}\n\n' for i,(h,p) in enumerate(zip(heads,paragraphs),1)))
cases={r['id']:r for r in read(ART/'cases.json')};gold={r['case_id']:r for r in read(ART/'grading-only.json')};ledger=read(ART/'retrieval-ledger.json')
index=['# ADR-0972 질문과 원시 호출','기준/후보 32개씩; 고정된 기준을 충족하지 못해 MAIN 미반영.','| 질문 | 기준 | 후보 | 기록 |','|---|---:|---:|---|']
for q in m['questions']:
    cid=q['case_id'];sections=[f'# 질문 {q["number"]:03d} — {cid}','## 1. 실행 메타','run-001 / baseline,candidate / temperature0 / Parasail FP8 / reasoning none / 각1회; 수정은 기존 bounded owner의 최대1회만 허용.','## 2. 사용자 질문 원문',cases[cid]['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',json.dumps(gold[cid],ensure_ascii=False),'## 4. 제품 입력을 구성한 원값','[제품 질문](../artifacts/cases.json), [합성 원문](../artifacts/documents.json), [저장 좌표 검사](../artifacts/fixture-preflight.json).','### 회수·탈락 단계 원장 — run·arm별','[기사 root identity·추가·탈락·원문 READ 원장](../artifacts/retrieval-ledger.json). 조 안의 범위 정확성은 별도 block set metric으로 평가한다.','| arm | stage | before→after | added/discarded | gold before→after |','|---|---|---:|---:|---:|']
    for ar in ledger['runs'][0]['arms']:
        rec=next(x for x in ar['cases'] if x['case_id']==cid)
        for st in rec['stages']:sections.append(f'| {ar["arm_id"]} | {st["stage_id"]} | {st["before_count"]}→{st["after_count"]} | {st["added_count"]}/{st["discarded_count"]} | {st["gold_before"]}→{st["gold_after"]} |')
    sections.append('## 5. 제품 모델 호출 — run·arm별 실제 원문')
    verdicts=[]
    for arm in ('baseline','candidate'):
        folder=ART/'trials'/cid/arm;sections.append(f'### run-001 / {arm}\n\n[전체 모델 관찰·결정·원문 읽기](../artifacts/trials/{cid}/{arm}/result.json)')
        for call in sorted((folder/'model').glob('call-*')):
            sections.append(' '.join(f'[{call.name}/{p.name}](../artifacts/trials/{cid}/{arm}/model/{call.name}/{p.name})' for p in sorted(call.glob('*.json'))))
        v=next(x for x in a['by_arm'][arm] if x['case_id']==cid);verdicts.append(v['pass']);sections.append(json.dumps(v,ensure_ascii=False))
    sections+=['## 6. 중간 LLM 호출 — router/compiler/verifier/repair','초기 분류 또는 compact navigation과 해당 bounded repair의 모든 입력·응답을 위에 연결했다. 숨은 호출·평가 모델은 없다.','## 7. 채점 호출과 반복 판정','LLM judge 없음. 선택이 끝난 뒤 고정한 원문 블록 집합과 대조했다. 재생성·다수결·후보별 기준 완화 없음.','## 8. 사례 최종 판정',f'기준={verdicts[0]}, 후보={verdicts[1]}. 전체 승격 기준은 별도로 미충족이다.']
    p=ADR/'실험'/q['file'];p.write_text('\n\n'.join(sections)+'\n');q['sha256']=sha(p);index.append(f'| {cid} | {verdicts[0]} | {verdicts[1]} | [{q["file"]}]({q["file"]}) |')
(ADR/'실험/README.md').write_text('\n\n'.join(index[:2])+'\n\n'+'\n'.join(index[2:])+'\n');save(ADR/'실험/manifest.json',m)
files=[]
for p in sorted(ART.rglob('*')):
    if not p.is_file() or p==ART/'manifest.json' or 'runtime' in p.parts or 'preflight' in p.parts:continue
    files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen structural selection qualification evidence','contains_raw_prompts_and_outputs':'model' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':files})
print('Preserved rejected qualification',counts,usage)
