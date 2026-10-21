"""Fresh cases and complete stored coordinates; unchanged product candidate."""
from common import *
import sys,copy,shutil
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
P=ROOT/'04_EXPERIMENTS/ADR/ADR-0965-law-name-recovery-qualification/artifacts'
previous=read(P/'design-freeze.json');seal=read(P/'stage.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==seal['base_pointer']
assert all(sha(ROOT/p)==h for p,h in seal['files']['candidate'].items())
save(ART/'stage.json',seal);shutil.copyfile(P/'integration-delta.json',ART/'integration-delta.json')
shutil.copyfile(P/'contracts-002.xml',ART/'contracts-002.xml')
save(ART/'inherited-contracts.json',{'path':str((P/'contracts-002.xml').relative_to(ROOT)),'sha256':sha(P/'contracts-002.xml'),'passed':260,'excluded_preexisting':7,'code_files':seal['files']['candidate'],'note':'Product bytes unchanged; contract result inherited, not counted as new executions.'})
titles=['정보보안 장비점검규정','정보보안 사고보고규정','외부업체 작업관리규정','상주직원 작업관리규정','회의자료 배포규정','회의실 예약규정','차량운행 기록규정','주차장 출입규정']
special={('D01',2):'정보보안 장비는 매주 금요일 점검하고 점검표에 결과를 적는다.',('D02',2):'정보보안 사고는 발견 즉시 상황실에 보고한다.',('D03',3):'외부업체는 작업 시작 이틀 전 작업계획을 시설 담당자에게 제출한다.',('D04',3):'상주직원은 작업을 마친 당일 부서장에게 결과를 제출한다.',('D05',4):'회의자료 발송 책임자는 배포 전에 참석자 명단과 파일 버전을 대조한다.',('D06',4):'회의실 예약은 사용일 전날까지 예약대장에 등록한다.',('D07',2):'차량 운행기록에는 출발 시각과 도착 시각 및 주행거리를 적는다.',('D08',2):'주차장 출입 시 차량번호를 등록한다.'}
docs=[]
for i,title in enumerate(titles,1):
    did=f'D{i:02d}';docs.append({'id':did,'title':title,'texts':[f'제{n}조 '+special.get((did,n),title+'에 따른 처리내역을 담당자가 기록한다.') for n in range(1,5)]})
scope=[d['id'] for d in docs]
specs=[('보안장비 점검지침 제2조','D01','제2조'),('외부업체 작업관리지침 제3조','D03','제3조'),('회의자료 배부규정 제4조','D05','제4조'),('차량운행 기록요령 제2조','D07','제2조'),('정보보안 장비점검규정 제2조','D01','제2조'),('회의자료 배포규정 제4조','D05','제4조'),('회의자료 배부규정 제99조',None,None),('외부업체 작업관리지침 제3조',None,None)]
cases=[];gold=[]
for i,(lookup,did,node) in enumerate(specs,1):
    cid=f'bound-{i:02d}';cases.append({'id':cid,'lookup':lookup,'question':lookup+'의 원문을 찾아 그대로 보여 주세요.','scope':['D01'] if i==8 else scope})
    gold.append({'case_id':cid,'expected':[] if did is None else [{'doc_id':did,'node':node}],'kind':'name_recovery' if i<=4 else 'exact_control' if i<=6 else 'missing_coordinate' if i==7 else 'scope_boundary'})
save(ART/'documents.json',docs);save(ART/'cases.json',cases);save(ART/'grading-only.json',gold)
m=read(ADR/'실험/manifest.json');m['decision_eligible']=True
m['lineage']['hypothesis_delta']='Same product bytes; evaluate fresh names with fully stored legal coordinates, not the malformed ADR0965 fixture.'
m['design']=copy.deepcopy(previous['design'])
m['design']['sampling']='Eight new information-security/worksite/meeting/vehicle synthetic tasks; no question, title or source text reused from ADR0965 or unit fixtures. Same four recovery/two exact/two negative categories and frozen thresholds.'
m['design']['success_criteria']+=' All32 synthetic stored-coordinate preflight lookups must pass before model calls. Recovery successes require RETRY lookup_status=MATCH followed by correct original delivery.'
m['design']['fixture_prerequisite']='Each source_unit stores legal_coordinate.as_dict(), body coordinate_scope and body:<canonical> coordinate_key. Integrity validation remains unchanged.'
m['design']['inherited_contracts']={'path':str((ART/'inherited-contracts.json').relative_to(ROOT)),'sha256':sha(ART/'inherited-contracts.json')}
m['llm_policy']=copy.deepcopy(read(P.parent/'실험/manifest.json')['llm_policy'])
m['dataset']={'name':'Fresh bound synthetic legal-title recovery','version':'bound-name-recovery-v1','frozen_source':str((ART/'cases.json').relative_to(ROOT)),'sha256':sha(ART/'cases.json'),'legal_version_checked':True,'reference_version_checked':True,'version_scope':'Synthetic only; no actual legal interpretation','documents':{'path':str((ART/'documents.json').relative_to(ROOT)),'sha256':sha(ART/'documents.json')},'grading_only':{'path':str((ART/'grading-only.json').relative_to(ROOT)),'sha256':sha(ART/'grading-only.json')}}
m['runs'][0].update(selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=True,corpus_total=32,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
m['design']['code_isolation']['candidates']=[]
save(ADR/'실험/manifest.json',m)
paths=read(P/'integration-delta.json')['against_main97']
C=ac.snapshot(ADR,'candidate',paths,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);ac.freeze(C);assert not ac.validate(C)
c=read(C/'candidate.json');rev=c['revisions'][-1];runner=Path(__file__).with_name('run_case.py')
m['design']['code_isolation']['candidates']=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}]
m['design']['script_bindings']={str(p.relative_to(ROOT)):sha(p) for p in runner.parent.glob('*.py')}
save(ADR/'실험/manifest.json',m)
save(ART/'design-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'dataset':m['dataset'],'stage_sha256':sha(ART/'stage.json'),'parent_invalid_trial_preserved':True,'model_calls_before_freeze':0})
text=(ADR/'README.md').read_text().replace('decision_eligible: false','decision_eligible: true');(ADR/'README.md').write_text(text)
print('Frozen fresh8 cases; unchanged418 product files; inherit260 contracts; require32 binding checks')
