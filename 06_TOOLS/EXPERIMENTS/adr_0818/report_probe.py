from pathlib import Path
import json,hashlib,gzip,tarfile,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0818-comparison-research-tasks';D=A/'artifacts/design';T=Path(__file__).parent;C=R/'02_BACKEND/lawrag/research/candidates/adr_0818/connected-r2'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
logs=A/'artifacts/development-logs';logs.mkdir(exist_ok=True)
for p in Path('/tmp').glob('tasks818-*.log'):
 if p.stat().st_size:(logs/(p.name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
# Preserve remaining development journals before pytest retention rotates them.
archive=A/'artifacts/development-journals.tar.gz'
if not archive.exists():
 with tarfile.open(archive,'w:gz') as tar:
  for folder in sorted(Path('/tmp/pytest-of-jin').glob('pytest-*')):
   if folder.is_symlink():continue
   for p in folder.rglob('*.sqlite'):
    if 'test_' in str(p):tar.add(p,arcname=str(p.relative_to('/tmp/pytest-of-jin')),recursive=False)
fixed=Path('/tmp/tasks818-last-boundaries.log').read_text();assert '2 passed' in fixed
r={'status':'complete','phase':'development implementation verification','code_root':str(code.relative_to(R)),
 'revision':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
 'observations':['rev005 API suite:22 passed','rev007 native requested operations with witnessed-reference fixture:6 passed',
 'rev007 additional contracts/core routes:36 passed;2 fixture failures corrected (field order and loaded module alias)',
 'rev008 corrected conflict and after-parent-save interruption:2 passed',
 'baseline source-span tests:19 passed and6 native reentry failures;candidate rev005 same6 in196 regression checks',
 'rev008 full API and shared regression logs are archived after completion and followed by independent qualification'],
 'limitations':['All model transcripts synthetic; external model calls0, no legal accuracy or cost reduction claim',
 'No MAIN pointer or GENOS deployment change','Known baseline native-reentry test failures retained'],
 'real_model_calls':0,'quality_certified':False,'baseline_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']}
put(A/'artifacts/run-001/result.json',r)
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=[{
 'candidate_id':'connected-r2','arm_id':'connected','experiment_id':m['experiment_id'],'run_ids':['run-001'],
 'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
 'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
 'runner_path':str((T/'run_tests.py').relative_to(R)),'runner_sha256':sha(T/'run_tests.py')}]
reason='Implementation probe with deterministic contracts and API failure injection; no retrieval effectiveness/golden recall comparison. Native source journals retained for audit; production retrieval data/index unchanged.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','known_regression_failures':6},'connected':{'status':'complete','implementation_complete':True,'decision_eligible':False}},usage={'product_model_calls':0,'offline_evaluator_calls':0},latency={'scope':'No model latency benchmark; raw pytest wall times in development logs'},error_taxonomy=[{'kind':'other','detail':'6 baseline native reentry test failures; candidate same cases; fixture repairs preserved'}]);put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. 구현과 개발 계약 검증 완료. MAIN 승격 결정 근거가 아닌 in-sample probe다.',
 '후속 RAG 실패가 기존 성공 근거를 지우고, 비교 대상 전체 source를 확장해 항목 비교를 막았다.',
 'artifacts/design/criteria.json의 성공·실패 기준을 구현 전 고정했다.',
 'MAIN76 기준으로 격리한 후보. 일반 결함 수정과 합성 API 계약 검증. 개발 관찰 후 변경 이력은 frozen revision으로 보존한다.',
 '선택 데이터·코드: baseline.json, verification-binding.json. 모델 호출0. 질문/정답/숫자를 제품에 고정하지 않았다.',json.dumps(r,ensure_ascii=False,indent=2),
 '참조 DB column, 후속 live revision 검사, 충돌 표시·완료 상태를 수정했다. import 충돌·참조가 없는 fixture·필드 순서·동적 모듈 monkeypatch 오류는 검사 도구 결함으로 구분했다.',
 '실제 모델 비용0. 개발 pytest 벽시계 시간은 로그에 기록. 검색 효과·절감률·법률 recall 미측정.',
 '고정 항목, 양측 원문 단서, 기존 RAG 정확 조회, 근거 유지, 부분 반환, 기존 경로 저장의 항목 결속을 구현했다.',
 '\n'.join(r['limitations']),
 '작업 코드/선택 릴리스에 아직 통합하지 않았다. 후속 분리 기술 검증을 통과한 정확한 파일만 통합한다. 과거 답변을 정답으로 재사용하지 않는다.',
 '.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0818/run_tests.py; consumer_check.py candidate; stable adr_structure validate/status/graph.']
meta=(A/'README.md').read_text().split('---',2)[1];(A/'README.md').write_text('---'+meta+'---\n\n# 대사 조사 과제 구현\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'실험/README.md').write_text('# 구현·기술 계약 검증\n\n법률 질문별 정답 채점은 수행하지 않아 questions는 비어 있다. 실제 합성 입출력·실패 이력은 artifacts/development-journals.tar.gz와 development-logs에, 선택 코드와 데이터는 artifacts/design에 보존했다.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock')) and 'runtime' not in str(p.relative_to(A))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Development code binding, exact observations or compressed original records','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in files]})
print('Probe record saved',rev['revision_id'])
