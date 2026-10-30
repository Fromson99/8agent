from common import *
import re,sqlite3,shutil
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-reference-bundle-purpose-review';O.mkdir(exist_ok=True)
f=read(DES/'freeze-rev-004.json');b=read(DES/'baseline.json');c=read(ART/'check-rev-004.json');w=read(ART/'check-working.json');reg=read(ART/'existing-contract-comparison.json');replay=read(ART/'saved009-rev-004.json');integration=read(ART/'working-integration.json')
assert c['returncode']==w['returncode']==0 and replay['passed'] and not reg['new_regressions']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for n,h in integration['product_files'].items():assert sha(ROOT/n)==h
for n,h in f['files'].items():assert sha(ROOT/f['code_root']/n)==h
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1201-final-original-coverage-review/artifacts/live/cm-009'
for row in replay['sources']:assert sha(ROOT/row['path'])==row['sha256']
for name in ('adr1202-native.log','adr1202-native2.log','adr1202-rev2.log','adr1202-rev3.log','adr1202-rev4.log','adr1202-working.log','adr1202-baseline.log','adr1202-saved.log','adr1202-saved3.log','adr1202-saved4.log'):
 p=Path('/tmp')/name
 if p.exists():
  dest=ART/'logs'/name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(p,dest)
failures={'rev001':'133 pass/3 API test fixture failures: empty origin refs omitted by compact input; subsequent fixture retry3 failures because singleton ref is a string; next retry1 pass/2 fixture assertions read source metadata instead of evidence_options. These did not prove delivery failures.',
 'saved_state_preparation':'Initial state006 predates retained original and fails current-original receipt check; replay uses final state013 and exact historical source receipts instead. No bypass of original verifier.',
 'saved_repeat':'Stored fragment exposed recursive activation of server-added goals on a second presentation. rev003 marks derived targets and only explicit model targets activate another group; one-hop test added.',
 'rev003':'140 pass/1 native gap recovery failure: extra top-level reconciliation receipt rejected at downstream schema. rev004 stores receipt inside existing requirement_review with its integrity hash.',
 'preservation':'Earlier candidate revisions, check JSONs, native runtime journals and available console logs retained. No old1201 failure reclassification.'}
put(ART/'preserved-failures.json',failures)
result={'status':'complete','candidate_revision':f['candidate_revision'],'serving_files':len(f['files']),'candidate_contracts':c['passed'],'working_contracts':w['passed'],'existing_contract_comparison':reg,'additional_unique_contracts':c['passed']-reg['baseline_passed'],
 'native_api':['Sibling source acquisition and final prompt delivery','Grounded change receipt, publication, persisted integrity and duplicate-request reuse','Missing change receipt corrected by existing one repair','Repeated missing change receipt rejected422 without answer or extra call','Material-gap metadata reconciliation retains claims/gaps and produces a limited answer when research budget is exhausted'],
 'saved009_fragment_replay':replay,'working_integration':integration,'main117_unchanged':True,'new_model_calls':0,'external_requests':0,'new_cm009_answer':False,'quality_certified':False,'genos_deployed':False,'prior_failures_preserved':failures}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json')
# Required article-root accounting intentionally cannot certify subclause coverage.
roots=[{'doc_id':'3521c3aaa5a735fd','node':349}]
rec=StageLedgerRecorder('cm-009','bound',identity_canonicalizer)
rec.record_stage('declared','source',roots)
rec.record_stage('bundled','expand',roots,parent_stage_ids=['declared'],after_occurrence_count=2)
rec.record_stage('offered','present',None,parent_stage_ids=['bundled'],executed=False,skip_reason='No new real009 read/model dispatch; fragment replay ends before fresh model input. The carried root is not a delivery receipt.')
ledger=build_experiment_artifact('ADR-1202',m['experiment_id'],[build_run_artifact('run-001',[grade_capture(rec.capture(),[])],{'bound':['declared','bundled','offered']})])
ledger['audit']={'scope':'Stored explicit-target fragment only; zero gold labels/legal scoring; root cardinality1 before/after does not describe exact coverage. Final present stage skipped, carried root is not new model delivery.',
 'declared_subclauses':replay['declared'],'expanded_subclauses':replay['expanded'],'stored_originals':replay['exact_coverage'],'new_model_input_dispatches':0}
ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
put(RUN/'retrieval-ledger.json',ledger)
data=ROOT/b['release']['data_path']
with sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 corpus=set()
 for (raw,) in db.execute('select json from source where document_id=?',('3521c3aaa5a735fd',)):
  s=json.loads(raw);a=s.get('article_coordinate') or {};node=a.get('node',s.get('unit_id'))
  if str(node).isdigit():corpus.add((a.get('doc_id',s['document_id']),int(node)))
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'bound':{'status':'complete','technical_contracts_passed':True,'candidate_contracts':c['passed'],'working_contracts':w['passed'],'quality_certified':False}},comparisons=[reg],judge_disagreements=[],usage={'physical_requests':0,'new_model_calls':0,'cost_usd':0},latency={'p50_seconds':None,'p95_seconds':None,'not_measured_reason':'Synthetic API and stored decision fragments; no provider latency or legal quality claim'},error_taxonomy=['other: fixture_compact_input_and_projection_errors','other: repeated_derived_reference_activation_fixed','other: downstream_receipt_schema_fixed'])
m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=1,after_filter=1,presented_total=1,presented_mean=1,presented_p50=1,presented_p95=1,golden_recall=None,selectivity=1/len(corpus),not_applicable_reason=None,metric_scope_note='Targeted single-document fragment, not full retrieval. Article root carried through skipped present stage is NOT a new model delivery or complete original receipt; exact ma/ba spans are audited separately.')
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
m['design']['code_isolation']['candidates'][0]['runner_sha256']=sha(Path(__file__).parent/'check.py')
sections=[
 ('결정 요약','참조 묶음과 목적별 판단 변경 검증을 작업 코드에 통합했다. 서버가 기존 원문에서 명시된 참조 목록의 선택 누락을 보완하며, 기존 긍정 판단을 최종 미사용으로 바꿀 때 원래 목적과 근거를 연결하게 한다. MAIN117 선택·GENOS는 유지한다.'),
 ('문제와 변경 전 구조','저장009는13조의 마목 또는 바목 중 마목만 목표로 선언했다. 서버는 선언한 마목을 정확히 읽었지만 바목을 추가 목표로 만들지 않았다. 마목을 SUPPORT로 인정한 모델은 최종에서 대형법인 정의가 아니라는 이유로 NOT_USED 처리했다. 별도로 핵심gap을 적고 요구검토를 SATISFIED로 유지해422로 끝났다. 조문ID 집계가 하위 범위 전체 확보를 증명하지 못한 점도 확인됐다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json). 일반 문법과 실제 저장 구조·현재 권한·원문 영수증을 사용한다. 특정31조·마목·바목이나 정답 문구는 제품에 넣지 않는다. 동일 도구·모델 예산과 기존 보완1회를 유지한다. 새 회귀·원문/권한/상태 검증 우회·미확인 삭제·무제한 재조사는 실패다.'),
 ('실험 설계','1200/1199 조사 복구를 부모로 한 격리 bound 후보468파일을 동결했다. 제품/설정9파일과pin31 변경. 새 원문 검토 AI1201은 채택하지 않는다. 저장009의 선택·최종판단 조각을 읽기 전용으로 재생하고 합성 원문을 실제 native HTTP/저장/재조회 경로로 검사했다. 기존104계약을 부모와 동일하게 비교했다.'),
 ('데이터·모델·재현성','저장1201의009 원문·응답·최종 조사 상태를 해시로 결속한다. 첫 시도의 과거 상태006에는 현재 retained source가 없어 검증이 거절되었으며 최종013 상태의 실제 과거 전달 영수증으로 다시 대조했다. 새 외부 요청·제품/채점 모델0. 합성 전송기는 네트워크를 사용하지 않으며 실제 법률 정답률을 평가하지 않는다.'),
 ('결과',f'최종 rev004 후보{c["passed"]}·작업{w["passed"]} 검사 통과. 기존104 동일 검사 통과·새 회귀0, 추가37조건. native API에서 선택하지 않은 형제 원문의 추가 확보·최종 입력, 정상 제외, 기존1회 보완, 반복 오류422, 핵심gap 보존 제한 답변, 저장 무결성·재조회 중복 호출 방지를 검증했다. 저장009는 마목→마목+바목 목표 확장, 바목410~414 실제 미확보 판정, 기존 NOT_USED 거절, 핵심gap 연결 복구를 확인했다. 새009 전체 실행/답변 통과는 아니다.'),
 ('사례별 오류 분석','[보존 실패](artifacts/preserved-failures.json). 최초 compact fixture 오류와 metadata/본문 혼동을 기록했다. 저장 재생에서 드러난 파생 목표의 다음 화면 재확장은 명시 목표만 새 묶음을 활성화하도록 고쳤다. rev003 native 제한 답변은 최상위 추가 필드가 저장 스키마에 거절되어 실패했고, rev004는 기존 requirement_review 영수증 안에 원제안·전후해시를 넣어 통과했다.'),
 ('비용·지연·회수 규모','새 모델0·외부 전송0·비용0. 속도 개선은 평가하지 않았다. 목표 수는 저장된 명시 참조 범위에서1→2이며 조문root는 둘 다31조여서1→1이다. [단계 원장](artifacts/run-001/retrieval-ledger.json)은 새 모델 제시 단계를 executed=false로 기록한다. root 수를 원문 완전성으로 해석하지 않으며 바목5블록 미확보를 별도 유지한다.'),
 ('해석','source_goal_control.record에서 현재 원문을 검증하고 reference_bundles.expand로 같은 문서의 명시 참조를 정확 목표에 연결한다. 기존 선집행기가 조회·읽기를 수행하고 subtree 원문 범위를 확보해야 ACQUIRED가 된다. ASSESS에서는 원래 조사 목적과 최신/과거 긍정 의견을 모두 보존하고, NOT_USED의 목적별 재해석·다른 주장에 반영·미해결을 검증한다. 필요한 하위 범위가 최종 원문에 없으면 다른 부분의 조문ID만으로 종료할 수 없다. 요구검토의 유일한 결함이 핵심gap 연결 누락일 때만 원래 주장·gap을 그대로 보존해 UNRESOLVED 행을 연결한다. 나머지 검증 오류는 기존 보완·독립 조사 또는 명시 실패를 따른다.'),
 ('한계와 일반화 가능 범위','현재 원문에 명시된 참조 가운데 모델/기존 서버가 특정한 목표가 있어야 묶음을 활성화한다. 목록과 현재 파서가 해석하는 범위를 대상으로 하며 외부 문서 한정·애매한 좌표·해석 불가 범위는 추측하지 않는다. 파생 목표는 연쇄 확장하지 않으며 전체16목표와 기존 시간·도구 예산을 유지한다. 구조 계약이 모든 법률 의미 오류를 판별하지는 않는다. 올바른 원문과 목적을 인용하고도 부적절한 재해석을 제시하는 문제는 별도 의미 평가가 필요하다. CORE/SUPPORT→NOT_USED를 검증하며 이전 의견을 정답으로 고정하지 않는다.'),
 ('운영 결정·롤백 조건','작업 제품/설정9+pin31을 반영했다. 다른428서빙파일과 completion_execution의 기존 저장 압축 읽기 hunk를 보존했고 작업141검사를 다시 통과했다. MAIN117 포인터/릴리스·GENOS·모델/40/1024/1800·개별180초·출력상한없음·온톨로지기본OFF 유지. 롤백은 artifacts/working-targeted.patch의 이번 hunk만 역적용하고 현재 파일로 엔진pin을 다시 계산한다. 새2모듈 삭제 전 이후 참조를 확인한다. 기존 파일 전체 덮어쓰기는 하지 않는다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_1202의 setup/freeze/check/baseline_check/replay_saved/integrate/document.py와 각 결과 JSON을 참조한다. 이미 실행한 저장 경로에는 덮어쓰지 않으며 새 결과 식별자를 사용한다. check.py는 후보, check.py working은 작업본, replay_saved.py는 저장 조각만 검사한다. 새 외부 모델 시험은 포함하지 않는다.')]
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','unchanged'),('in_sample','true'),('decision_eligible','false')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
(ADR/'README.md').write_text('---'+meta+'---\n\n# 참조 묶음 원문 확보와 목적별 판단 변경 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
question=read(P/'canonical/011.json.gz')['view']['current_request']
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
texts=['run-001 / bound / cm-009. 저장 응답 조각 재생·합성 native API; 실제009 새 실행0. source=exact for saved bytes, added goal/context is reconstructed and audited separately.',question,'법률 기준답변/채점 없음. 기술 기대값은 동결 기준과 실제 문서 구조·원문 범위를 사용한다. 합성 모델은 평가 모델이 아니다.', '[원문/응답 hash와 재생 결과](../artifacts/saved009-rev-004.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[단계 원장](../artifacts/run-001/retrieval-ledger.json). root1→1, 목표 하위 범위1→2; 새 제시 단계 미실행. 기존 마목3블록 확보·바목5블록 미확보를 별도 판정한다.', '새 제품 모델 호출0. 저장 원요청·응답은1201 canonical006/011/012 및 raw의 원본을 수정하지 않고 사용한다. [정확한 파일과 SHA-256](../artifacts/saved009-rev-004.json).', '새 중간/검토 AI0. 합성 API 전송기는 native_fixture.py의 고정 입력과 오류 주입만 사용한다.', '평가 모델0·법률 정답률 미인증·다수결 없음.',json.dumps({k:result[k] for k in ('candidate_contracts','working_contracts','new_model_calls','new_cm009_answer','quality_certified')},ensure_ascii=False)+'\n\n저장 조각 재생 통과는 새009 전체 답변 통과가 아니다.']
q=m['questions'][0];p=ADR/'실험'/q['file'];p.write_text('# cm-009 저장 조각 진단\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 기술 검증과 저장009 진단\n\n[결과](../artifacts/run-001/result.json) · [질문](질문-001-cm-009.md). 새 제품 모델0·법률 채점0.\n')
(O/'수정과_검증결과.txt').write_text('참조 묶음 확보·판단 변경·미해결 복구 수정\n\n'+'\n\n'.join(h+'\n'+v for h,v in sections)+'\n')
print('Documented candidate141 working141 baseline104; MAIN117 unchanged')
