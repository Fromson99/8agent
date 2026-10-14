from pathlib import Path
import hashlib,json,shutil,statistics
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0766-rich-grounded-answer-stream';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for n in ['contracts-r1','native-r2','native-detail','native-captured','contracts-r3','consumers-r3','consumers-baseline']:
    p=Path('/tmp/adr0766-'+n+'.log')
    if p.exists():shutil.copy2(p,A/'artifacts'/('tests-'+n+'.log'))
results=[read(O/c/'result.json') for c in 'ABC'];assert all(r['status']=='completed' for r in results)
review={'method':'Offline Codex review of exact archived originals and both rendered answers; no judge model and no product changes',
    'metric':'No additional unsupported legal effect in the writing stage, distinct from full legal correctness',
    'cases':{'A':{'baseline':True,'narrative':True,'note':'Delegation, notification and contribution permission/obligation retained.'},
    'B':{'baseline':True,'narrative':False,'note':'New writing says inspector cannot arbitrarily delay reporting, although paragraph2 states no reporting deadline. Preserve as unsupported strengthening; do not rewrite recorded output.'},
    'C':{'baseline':True,'narrative':True,'note':'Mandatory cancellation reasons1/5 and discretionary alternatives/one-year bound retained.'}}}
put(O/'semantic-review.json',review)
usage={k:sum(u.get(k,0) or 0 for r in results for u in r['usage']) for k in ['input_tokens','output_tokens','cost_usd']}
lat=[r['seconds'] for r in results]
result={'status':'complete','structural_contracts':{'critical_pass':63,'critical_fail':0,'broader_pass':36,'broader_fail':26,'baseline_same_failures':26,'new_regressions':[],'broader_limit':'8 test files assert their physical root;18 existing workflow fixtures have stale display expectations. Same baseline failures; do not claim full suite pass.'},
    'cases':results,'semantic_review':review,'by_arm':{'baseline':{'status':'complete','cases':3,'additional_unsupported_effect_free':3},'narrative':{'status':'complete','cases':3,'structurally_valid':3,'additional_unsupported_effect_free':2}},
    'comparisons':[{'arms':['baseline','narrative'],'metric':'additional unsupported effect free','both_correct':2,'baseline_only_correct':1,'candidate_only_correct':0,'both_incorrect':0,'paired_delta':-1}],
    'usage':{'model_calls':3,**usage},'latency':{'phase':'composition only','p50':statistics.median(lat),'p95':max(lat),'min':min(lat),'max':max(lat),'small_sample':True},'main_wiring':'unchanged','genos_field_verified':False}
put(O/'result.json',result)
m=read(A/'실험/manifest.json');m['results'].update(status='complete',by_arm=result['by_arm'],comparisons=result['comparisons'],judge_disagreements=0,usage=result['usage'],latency=result['latency'],error_taxonomy=[{'type':'unsupported_inference','count':1,'denominator':3,'case':'B'}])
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['questions']=[]
headings=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
dataset=read(D/'public-probes.json')
for i,c in enumerate(dataset['cases'],1):
    cid=c['case_id'];p=A/'실험'/f'질문-{i:03}-{cid}.md'
    body=['ADR0766/run-001; Qwen3.8 Parasail FP8 none; one composition call, deterministic baseline.',c['question'],'No product gold. Offline review checks immutable selected originals; source versions pinned in design/public-probes.json.',
        'artifacts/design/public-probes.json retains exact accepted assessments and selected original sources with archived event provenance.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nNo retrieval invocation; presentation-only replay.',
        f'artifacts/run-001/{cid}/provider contains exact request, response, binding and usage. baseline.txt/answer.txt are canonical displays.',
        'No new investigation or assessment model calls. Existing assessment reused by hash; only final composition invoked.',
        'Offline Codex review, no independent judge model, no repeated votes. See run-001/semantic-review.json.',review['cases'][cid]['note']]
    p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {j}. {h}\n\n{v}' for j,(h,v) in enumerate(zip(headings,body),1))+'\n')
    m['questions'].append({'number':i,'case_id':cid,'file':p.name,'sha256':sha(p)})
put(A/'실험/manifest.json',m)
sections=[('결정 요약','구현/연결 검사는 통과했으나 추가 의미 단정 1/3을 발견하여 Proposed로 보존한다. MAIN53과 GENOS 배포는 변경하지 않는다. 후속 수정은 새 ADR에서 시행한다.'),
 ('문제와 변경 전 구조','v8는 규칙 구조를 고정 표제로 나열하고 생성 중 최종 본문을 송신하지 않았다. 워크플로우는 완료 후 160자씩 전송했다.'),
 ('가설과 사전 판정 기준','artifacts/design/criteria.json과 probe-freeze.json에서 성공 조건, 정확한3개 공개 평가 입력, 호출수1·180초 한도, 무재실행을 동결했다.'),
 ('실험 설계','MAIN53 동일 working code를 snapshot으로 격리. 판단/근거는 보존하고 별도 최종 작성1회, 문단별 참조 검증 후 기존 채널 송신. 개발 계약 수정 rev1~3는 합성 단위 검사이고 공개 효과 실험은 rev3만 실행했다.'),
 ('데이터·모델·재현성','공개65문서 허용 범위의 기존 검증 원문/판단3건. 내부 사진 질문은 반출하지 않았다. Qwen3.8 Parasail FP8 none; fallback없음. 모델 입력·출력은 provider 폴더와 해시 인덱스에 보존한다.'),
 ('결과','핵심63검사 통과. 넓은62검사는36통과/26실패이며 MAIN53 동일 실패26개, 새 회귀0. 공개3건 구조3/3, 신규 과도한 법률 단정 없음2/3. baseline-only1, both2, candidate-only0, both-fail0.'),
 ('사례별 오류 분석','A는 위임/통보/출연, C는 의무취소/재량조치 구분 유지. B는 원문에 없는 검사인 보고 지연 불가를 추가했다. 표현2곳 및 구형 UI fixture의 알려진 기대 불일치를 보존한다.'),
 ('비용·지연·회수 규모',f'추가 작성3콜, 입력{usage["input_tokens"]}·출력{usage["output_tokens"]}토큰, 비용${usage["cost_usd"]:.6f}. 작성 지연{min(lat):.2f}~{max(lat):.2f}초. 전체 검색/판단 시간 측정이 아니다. 새 retrieval은 없으며 완성된 판단을 재사용했다.'),
 ('해석','인용·원문·판단의 바이트 보존과 자연어 설명의 의미 정확성은 다르다. 문단 검사는 근거 ID·출력 연속성을 검증하며 법률 함의까지 인증하지 않는다.'),
 ('한계와 일반화 가능 범위','인샘플3건 단회, 독립 전문가 없음. 실제 GENOS 모델/화면 미확인. 스트리밍은 내부 전송 모의에서 실제 native API와 기존 workflow/SSE 계약을 확인했다. 외부 실험 전송은 buffered다.'),
 ('운영 결정·롤백 조건','작업 코드/선택 MAIN/GENOS 미변경. 후보는 격리·비활성이다. 원문보다 강한 단정과 문서형 표현을 후속 ADR에서 개선한다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_0766/{bootstrap,implement,freeze,run_tests,freeze_probes,run_probe,finish}.py. 완료된 run-001은 덮어쓰지 않는다. 새 호출은 후속 ADR에서 동결한다.')]
front=(A/'README.md').read_text().split('---',2)[1]
(A/'README.md').write_text('---'+front+'---\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 최종 서술·스트리밍 공개3건\n\n'+ '\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n\n구조3/3, 추가 미근거 단정 없음2/3. 인샘플·MAIN 불변.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen inputs, exact provider records, test failures and outcomes','contains_raw_prompts_and_outputs':p.name in ('request.json','response.json')} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']})
print('Development probe complete;63 contracts passed; additional unsupported statement1/3 retained; MAIN unchanged.')
