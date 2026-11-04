from common import *
import subprocess,runpy
b=read(DES/'baseline.json');release=b['release'];w=b['workflow_source'];products=b['product_changes'];m=read(ADR/'실험/manifest.json')
can=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1336/integrated';C=can/'snapshot'
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
link=C/'01_DATA';assert not link.exists() and not link.is_symlink();link.symlink_to(ROOT/'01_DATA',target_is_directory=True)
try:
 with (ART/'rehash-r2.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','--root',str(C),'rehash-engines','--apply'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
finally:link.unlink()
old=runpy.run_path(str(ROOT/release['code_root']/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS'];new=runpy.run_path(str(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS']
def sql(p):return {k:{a:b for a,b in v.items() if a!='sources'} for k,v in p.items()}
assert sql(old)==sql(new) and len(new)==639
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in release['files']},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
assert all(sha(C/n)==w['files'][n] for n in products)
put(DES/'candidate-integrated.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path='06_TOOLS/EXPERIMENTS/adr_1336/run.py',runner_sha256=sha(Path(__file__).with_name('run.py')))])
put(ADR/'실험/manifest.json',m)
p=ROOT/'09_ARTIFACTS/AUDITS/20261104-workflow-review-main-coordination.txt'
with p.open('a') as out:out.write('\nADR1336 동결 후보 준비: '+str(C)+'\n해시목록: '+str(DES/'candidate-integrated.json')+'\n범위: 완료1326+메일워크플로우2수정,1332제외, MAIN141Gold 유지.\n워크플로우 담당은 이 경로에서 기존5suite73검사만 수행 후 별도 결과JSON/로그 경로를 이 파일에 추가해주세요. Gold37검사와 selection은 root가 수행하므로 중복하지 않습니다.\n')
print('Frozen merged528; workflow11 exact; Gold7 preserved; native639 same')
