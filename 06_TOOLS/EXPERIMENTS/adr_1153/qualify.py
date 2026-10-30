from common import *
import subprocess,re
f=read(DES/'freeze.json');inherit=read(DES/'inherited-checks.json');assert f['files']==inherit['code_files']
assert sha(ROOT/inherit['path'])==inherit['sha256'] and inherit['passed']==216
q=read(ART/'check-ontology.json');assert q['status']==0 and q['passed']==10 and not q['import_leaks']
base=read(DES/'baseline.json');stage=read(DES/'staging.json');S=ROOT/stage['code_root']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
assert all(sha(S/n)==h for n,h in stage['files'].items()) and all(sha(ROOT/n)==h for n,h in f['scripts'].items())
# The preview invokes the official data-binding verifier; run only after the
# active full-corpus1151worker has completed or an authorized stop is verified.
coord=read(ROOT/'09_ARTIFACTS/AUDITS/20261028-ontology-selection-main110/execution-coordination.json')
assert coord['safe_to_prepare'] and coord['active_full_corpus_worker_stopped']
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(S),'--generation',base['manifest']['data_path'],'--release-id','ontology-selection-preview-20261028-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (DES/'preview.log').open('w') as log:subprocess.run(cmd,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
draft=read(DES/'official-preview.json');actual=dict(base['manifest']['files'])
for row in draft['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==stage['files'] and len(actual)==440 and len(draft['changes'])==32
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':draft['base_release_manifest_sha256'],'candidate':f['binding'],'staged_files':actual,'excluded_candidate_paths':{n:'Hash-bound test/build support, excluded from official runtime inventory' for n in sorted(set(f['files'])-set(actual))}})
for row in draft['changes']:row['reason']='Exact365char1150scenario-selection instruction; all other AST unchanged' if row['path'].endswith('.py') else 'Dependent code/engine hash only; no profile or data change'
draft.update(candidate=f['binding'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',draft)
result={'status':'complete','strict_success':True,'technical_conditions':226,'this_run_check_executions':10,'inherited_current_framework_conditions':216,'new_model_calls':0,'quality_certified':False,'files':440,'changed_files':32,'actual_product_changes':['ontology_scenarios.PROMPT'],'profile_unchanged':True,'ontology_default_off':True,'ontology_data_included':False,'same_data_generation':True,'preserved_main109_recovery':True,'selector_quality_reference':'ADR1150in-sample11/11preserved;notnewlegalqualitymeasurement','official_preview_exact':True,'concurrency_resolved':coord,'service_followup_required':True}
put(ART/'run-001/result.json',result)
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['design']['release_rebase']=bind(DES/'release-rebase.json');m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'MAIN109and1150historicalreference'},'integrated':{'status':'complete','technical_conditions':226,'quality_certified':False}},comparisons=[{'technical_integration_only':True,'same_parent_product':True,'new_legal_quality_evaluation':False}],usage={'new_model_calls':0},latency={'performance_claim':False},error_taxonomy=['1152testROOTpathfailurespreserved;productunchanged','1150pairedproviderincompletecallsandknown-sourcequalitylimitsremain'],main_wiring='promotion-candidate',quality_certified=False);put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
parts=[('결정 요약','MAIN109의복구기능·ON/OFF·기본OFF·데이터미포함을유지한365문자선택지침의기술승격후보.226조건(동일제품216상속+10재확인),440공식서빙파일·32변경일치. 법률품질인증아님.'),('문제와 변경 전 구조','1135는복수선택허용만으로PATH2누락이남았고1150은짧은일반요건·예외경로동시선택지침으로동일묶음11/11을관찰했다. 사용자는이선택개선만최신MAIN반영을명시했다.'),('가설과 사전 판정 기준','[1152에서동결한기술기준](artifacts/design/criteria.json). 신규8부분집합·지침전달·AST·프로필불변,기존216기술계약,공식440파일·데이터제외. 이전법률인샘플채점과분리.'),('실험 설계','1152의665제품파일과기준그대로. 기존pytestROOT주입과충돌한시험상수만REPO_ROOT로분리하고10검사재실행.216기존계약은동일제품·원결과해시로상속. 새모델0.'),('데이터·모델·재현성','선택전용PROMPT374→365자. 제품모듈1개·종속pin31개. 프로필/데이터/모델/출력상한없음/40·1024·1800예산불변. 연구package/recipe/원문사본은공식서빙제외.'),('결과','226조건통과. 실제선택지침전달·모델의0~3개선택그대로보존·중복요청재사용·본문hash보존·ON/OFF·빈데이터·재선택·SEARCH복귀·발행·고정참조결합을검사했다. 새선택코드의법률판단을추가채점하지않았다.'),('사례별 오류 분석','1152의224통과2파일경로실패기록보존. 수정후동일제품으로문제검사까지통과했다.1150전후비교미완료·같은묶음인샘플범위는변경하지않았다.'),('비용·지연·회수 규모','새외부모델0. 기술합성조건이며회수효과·전체서비스지연개선율없음. 실제데이터를쓰는공식prepare와선택서비스는다른무거운작업과겹치지않게진행.'),('해석','일반요건의성립과제외경로를함께선택하도록지침만교체한다. 경로2개를서버가강제하지않고데이터·선택스키마·복구소유자는유지한다.'),('한계와 일반화 가능 범위','기술적분리검증적격과법률품질인증을구분한다.1150은알려진원문8질문11반복. ON이어도온톨로지데이터가없으면일반RAG. GENOS현장/데이터게시미수행.'),('운영 결정·롤백 조건','사용자MAIN반영명시승인. 공식prepare/apply후동일코드작업통합·실제선택서비스OFF/ON-empty확인. 해시/원문/데이터/설정문제시이전109릴리스공식롤백. 진행1151작업은기록된사용자결정과종료확인후교체.'),('재현 명령','check.py ontology,design/inherited-checks.json,qualify.py,공식release-rebase. 완료실험덮어쓰기금지. 선택서비스확인은09_ARTIFACTS/AUDITS/20261028-ontology-selection-main110. [산출물](artifacts/manifest.json).')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 최신 MAIN 선택 지침 결합 기술검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(parts,1))+'\n');(ADR/'실험/README.md').write_text('# 기술검증226조건\n\n동일제품216기존조건상속+10추가조건재확인. 질문별법률평가없음. 새모델0.\n')
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note','Same665product/440servingbytes;216existingtechnicalconditionsinherited+10rerunpass;defaultOFF/no data preserved;user-authorizedpromotioncandidate.')]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],cwd=ROOT,capture_output=True,text=True);(ART/f'{args[0]}-final.txt').write_text(r.stdout+r.stderr);assert r.returncode==0
print('QUALIFIED226;440files32changes;model0')
