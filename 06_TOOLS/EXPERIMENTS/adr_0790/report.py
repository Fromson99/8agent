"""Record technical qualification separately from real Qwen answer quality."""
from pathlib import Path
import hashlib,json,sqlite3

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0790-risk-rag-publication-deadline';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');C=R/f['code_root'];technical=read(A/'artifacts/run-001/technical.json')
unchanged=all(sha(R/n)==h for n,h in f['files'].items())
live=[]
for folder in sorted((A/'artifacts/live').iterdir()):
    if not (folder/'result.json').is_file():continue
    observation=read(folder/'result.json');response=read(folder/'response.json').get('body',{})
    errors=[];models=set();providers=set()
    for p in sorted((folder/'raw').glob('*/response.json')):
        v=read(p)
        if v.get('error'):errors.append({'call':p.parent.name,'error':v['error']})
        if v.get('model'):models.add(v['model'])
        if v.get('provider'):providers.add(v['provider'])
    journals=list((folder/'runtime/workflows').glob('*/journal.sqlite'))
    db=sqlite3.connect(journals[0]);db.row_factory=sqlite3.Row
    evidence=[dict(v) for v in db.execute('SELECT evidence_id,source_id,document_id FROM evidence_unit')]
    entry={'case':observation['case'],'status':observation.get('status'),'http_status':observation.get('http_status'),
        'sides':{k:v['status'] for k,v in observation.get('sides',{}).items()},
        'model_calls':observation['model_calls'],'usage':observation.get('model_usage'),
        'elapsed_seconds':observation['elapsed_seconds'],'models':sorted(models),'providers':sorted(providers),
        'errors':errors,'response_path':str((folder/'response.json').relative_to(R)),
        'response_sha256':sha(folder/'response.json'),
        'target_liquidity_article_read':any(e['source_id']=='article:c3af79efc692a91026430460' for e in evidence),
        'corrected_committee_document_read':any(e['document_id']=='11478916f48b00e5' for e in evidence),
        'in_sample':True,'quality_certified':False}
    db.close();live.append(entry)
checks={'frozen_code_data_and_test_inputs_unchanged':unchanged,
    'baseline_required_contracts_pass':technical['baseline']['passed']==technical['baseline']['total'] and technical['baseline']['exit_code']==0,
    'candidate_required_contracts_pass':technical['orchestration']['passed']==technical['orchestration']['total'] and technical['orchestration']['exit_code']==0,
    'live_observations_recorded_separately':len(live)==1,
    'no_unhandled_publication_failure':all(v['http_status']==200 for v in live),
    'observed_qwen_provider_no_fallback':all(v['models']==['qwen/qwen3.8-27b'] and v['providers']==['Parasail'] for v in live)}
limitations=[
    'Technical orchestration qualification only. Known liquidity/committee observations are in-sample; no legal quality or unseen-question certification.',
    'The live harness uses native risk_team selection. It is one known in-sample question and does not certify retrieval quality.',
    'Prior ADR0789 liquidity observation did not recover the target article 3-24-4 paragraph 2. Parasail rejected an existing RAG navigation schema as too large; workflow basis validation also exhausted its correction allowance.',
    'Corrected internal source is 위험관리위원회운영준칙 (2016-08-23), not 위험관리기준시행세칙 6-4. No liquidity numeric rule or current applicability is invented.',
    'Prior ADR0789 concurrent jobs caused host OOM; this ADR executes heavy audits/live questions serially and caps process virtual memory. Original evidence and interruption records are retained.',
    'GENOS field deployment and internal-model verification not performed.',
]
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'by_arm':technical,
    'contracts_passed':technical['orchestration']['passed'],'live':live,'limitations':limitations,
    'usage':{'product_model_calls':sum(x['model_calls'] for x in live),'offline_evaluator_calls':0},
    'qualification_scope':'Prospectively enumerated technical orchestration contracts, not legal retrieval quality',
    'actual_service_selection':'Verified separately after qualified apply using the same serving file hashes'}
put(A/'artifacts/run-001/result.json',result)
assert result['strict_success'],checks
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm=technical,comparisons=[],judge_disagreements=None,usage=result['usage'],
    latency={'live_seconds':{v['case']['id']:v['elapsed_seconds'] for v in live}},
    error_taxonomy=['HOST_OOM_INTERRUPTION','PROVIDER_SCHEMA_TOO_LARGE','WORKFLOW_BASIS_REPAIR_EXHAUSTED'])
put(A/'실험/manifest.json',m)
parts=[
 ('결정 요약','Accepted promotion-candidate. ADR-0789에서 드러난 만료 후 출처 검증 500 오류를 별도 읽기 한도로 복구했다. 대사가 기존 RAG 전체 실행에 내규·외규 질문을 각각 전달하고 답변·검증 원문·조사 기록을 받아 판단하도록 변경한다. 기술 연결 검증과 실제 질문의 의미 품질은 분리한다.'),
 ('문제와 변경 전 구조','기존 대사는 RAG의 검색·원문 도구를 재사용했지만 별도 조사 루프를 실행했다. 사용자가 요청한 기존 RAG 질문→답변·기록→대사 형태와 달랐다.'),
 ('가설과 사전 판정 기준','두 범위의 Pipeline.run, 정확한 원문 검증, 같은 사건의 추가 조사, 부모 총 예산, 중단·중복·권한·변조 차단, 필수 회귀 검사를 사전에 지정했다. 무결성·권한·상태·예산 문제는 승격 차단이며 법률 의미 정확도는 별도 관찰한다.'),
 ('실험 설계','MAIN67/ADR-0788 recovery와 ADR-0789 동결 후보의 실제 차이를 확인하고 전체 서빙 코드를 새로 동결했다. 변경하지 않은 RAG 조사·검색 정책도 기준에 결속했다. 기준과 후보는 별도 프로세스와 실제 API에서 검사한다. 모의 모델 응답으로 지정 기술 경계를 검증하고 실제 Qwen 위원회 질문 한 건은 보조 관찰로만 남긴다.'),
 ('데이터·모델·재현성','기존 추가 문서 세대에 명시적 명명 정의 635건과 참조 링크 635건만 추가한 SQLite 세대다. 원문 재파싱·전체 재색인은 없다. 사용자 외부 전송 허용을 문서·팀·세대·해시에 결속했으며 내부 원문을 공개 자료로 표시하지 않는다. Qwen3.8/Parasail FP8/reasoning none/no fallback 공통 ExperimentClient를 사용했다.'),
 ('결과',f"기준 {technical['baseline']['passed']}/{technical['baseline']['total']}, 후보 {technical['orchestration']['passed']}/{technical['orchestration']['total']} 통과. 실제 질문 결과: "+json.dumps([{k:v[k] for k in ('case','status','sides','model_calls','target_liquidity_article_read','corrected_committee_document_read')} for v in live],ensure_ascii=False)),
 ('사례별 오류 분석','이전 ADR-0789 유동성 질문에서 정답 제3-24조의4 제2항은 회수되지 않았다. 외규 RAG 제공자가 schema too large를 반환했고 근거 관계 출력도 보정 한도에서 실패했다. 확인된 원문과 실패 원인을 유지한 partial 응답으로 끝냈으며 규정 부재나 부합으로 바꾸지 않았다. 위원회 질문의 상세 결과는 result.json과 원시 기록을 따른다.'),
 ('비용·지연·회수 규모','부모 workflow가 자식의 물리 모델 시도와 도구 예약을 실행 전에 기록한다. 조사 종료 후 발행 검증은 최초 시점부터30초인 별도 읽기 창을 저장하고 재개로 초기화하지 않는다. 모델·검색·추가 조사 예산은 늘리지 않는다. 추가 조사·재개 시 예산과 최초 deadline을 초기화하지 않는다. 이전 ADR-0789의 병렬 검증은 호스트 OOM으로 중단됐다. 이번 ADR은 무거운 작업을 순차 실행한다. 이전 전체 권한 범위 초기화는 프로세스당 약 8GB를 사용했다. 통상 risk_team 선택 범위의 메모리·성능 인증은 별도다.'),
 ('해석','기존 RAG를 호출하는 구조가 확인됐다는 뜻이며 원하는 법률 답을 모두 찾았다는 뜻은 아니다. 두 답변은 rag_results로 반환하고 근거는 원문의 정확한 span으로 검증한다. 판단 대상의 관계와 내용 상충은 별개다. 실패한 자식 실행을 원문 부재로 간주하지 않는다.'),
 ('한계와 일반화 가능 범위','\n'.join('- '+v for v in limitations)),
 ('운영 결정·롤백 조건','사용자의 MAIN 반영 요청에 따라 완료 ADR의 동일 동결 코드·추가 데이터 세대로 prepare/apply --confirm-main한다. 다른 작업 변경을 보존하는 제한 병합 계획을 별도 저장했다. 활성 포인터·파일 해시·실제 로컬 service.service 진입점은 적용 후 receipt로 검증한다. 기준 MAIN67을 롤백 대상으로 보존한다. Git main 병합과 GENOS 현장 반입·배포는 수행하지 않는다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_0790의 freeze/audit_pinned/live_bootstrap/report/prepare_promotion 스크립트와 design의 해시를 따른다. 완료된 결과는 덮어쓰지 않고 새 실험 ADR로 분리한다. stable adr_structure validate --final 및 graph, rag_main_promotion prepare/apply로 확인한다.'),
]
meta=f"---\nadr_id: ADR-0790\ntitle: 대사 워크플로우에서 기존 RAG 전체 실행 호출\nstatus: Accepted\ndecision_date: 2026-10-15\nphase: full\nin_sample: false\ndecision_eligible: true\nmain_wiring: promotion-candidate\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 기존 RAG 호출 대사 검증\n\n지정 기술 계약 검사와 별도 Qwen 실질문 한 건. ../artifacts/run-001/result.json 참조.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0790',
    'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),
    'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen orchestration qualification and separate live observation',
    'contains_raw_prompts_and_outputs':'raw' in p.parts} for p in (A/'artifacts').rglob('*')
    if p.is_file() and p.name!='manifest.json']})
print(json.dumps({'strict_success':result['strict_success'],'contracts':technical,'live_cases':len(live)},ensure_ascii=False))
