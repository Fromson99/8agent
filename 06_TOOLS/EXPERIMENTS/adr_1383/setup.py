from common import *
import shutil,ast
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(exist_ok=False)
def evidence(number):return next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{number}-*/artifacts'))
src,ordinary,legacy=evidence(1374),evidence(1373),evidence(1354)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert ptr==read(evidence(1377)/'main-r2/activation.json')['active'] and ptr['generation']==145
r=read(ROOT/ptr['manifest_path']);assert sha(ROOT/ptr['manifest_path'])==ptr['release_manifest_sha256']
C=ROOT/r['code_root'];put(DES/'baseline.json',dict(pointer=ptr,release=r))
for name in ('provider-policy','source-scope','runtime-ontology'):put(DES/(name+'.json'),read(src/'design'/(name+'.json')))
put(DES/'legacy365-context.json',read(legacy/'design/ontology-365-r1-context.json'))
assert read(DES/'legacy365-context.json')==read(legacy/'design/ontology-365-r2-context.json')
put(ART/'publication-verified.json',read(src/'publication-verified.json'))
shutil.copytree(src/'transport',ART/'transport')
shutil.copytree(src/'sandbox-repository',ART/'sandbox-repository')
for p in (src/'sandbox-repository').rglob('*'):
    if p.is_file():assert sha(p)==sha(ART/'sandbox-repository'/p.relative_to(src/'sandbox-repository'))
cs=read(ordinary/'design/live-cases.json')+read(src/'design/live-cases.json')
s365=read(legacy/'design/live-cases.json')[0]
cs.extend([{**s365,'id':'legacy365-'+label,'arms':[arm]} for label,arm in [('on1','ontology-on'),('off','baseline'),('on2','ontology-on')]])
assert cs[0]['steps']==cs[1]['steps'] and cs[3]['steps']==cs[4]['steps']==cs[5]['steps']
put(DES/'live-cases.json',cs)
put(DES/'authorization.json',{'user_request':'일단 메인에 반영하고 온톨로지는 이후에 추가 남은거 돌려봐봐','prior_explicit_model':'qwen','public_document_ids':read(DES/'source-scope.json')['public'],'scope':'Only frozen public Commercial Act question and derived search; separate isolated source-authorized requests; no export of internal documents or gold answers','production_publication':False})
criteria=dict(hypothesis='Does ordinary Qwen use the charter pathway and does correct source-grounded completion improve when the ontology is available on MAIN145?',
success=['Correct ratios and distinct denominators in verified final claims on charter; all three sourced timing rules on 365','Distinguish actual transmitted catalog from confirmed source-linked use; only qualify a charter adoption when final path,node,claim,source and package checks pass.','Report pairwise calls, tokens, latency, answer quality. No aggregate speed or quality certification on two known questions.'],
failure=['Global stop on uncertain physical outcome; preserve reply, no resend','Source-only, unsupported or rejected responses never count as complete.','Do not change release, prompts, package or questions during comparison.'],
limits={'max_external_total':120,'per_case':40,'concurrency':1,'network':'Qwen FP8, Parasail primary, authorized 429 fallback only'},order=[q['id'] for q in cs])
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Complete original-grounded answers and confirmed final claim use with paired latency and call counts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for a in m['design']['arms']:a.update(changes='Completed1377 release reference' if a['id']=='baseline' else 'Execute frozen ON/OFF cases with identical MAIN145 bytes',controls='Same code, source, review, model and independent fresh sessions')
stages=read(src.parent/'실험/manifest.json')['design']['retrieval_stage_plan']
m['design']['retrieval_stage_plan']={**stages,'stages_by_arm':{a:stages['stages_by_arm']['baseline'] for a in ('baseline','paired')}}
m['dataset'].update(name='Two public charter/meeting questions and an explicit charter control',version='main145-frozen-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['runs'][0].update(arm_ids=['paired'],selection_rule='Six independent cells in frozen order; global halt on unknown',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
can=ac.snapshot(ADR,'paired',list(r['files']),experiment_id=m['experiment_id'],arm_id='paired',run_ids=['run-001'])
for n,h in r['files'].items():
    assert sha(C/n)==h
    shutil.copyfile(C/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can)
rev=read(can/'candidate.json')['revisions'][-1]
assert all(sha(can/'revisions'/rev['revision_id']/'snapshot'/n)==h for n,h in r['files'].items())
pin={'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
runner=Path(__file__).with_name('live_public.py')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='paired',experiment_id=m['experiment_id'],arm_id='paired',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(DES/'consumer.json',{'code_root':r['code_root'],'selected_files':r['files'],'pin':pin})
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*DES.glob('*.json'),ART/'publication-verified.json',*(p for p in (ART/'transport').rglob('*') if p.is_file()),*(p for p in (ART/'sandbox-repository').rglob('*') if p.is_file())]
for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text())
put(DES/'freeze.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'release_manifest_sha256':ptr['release_manifest_sha256'],'case_count':len(cs)})
print('Frozen MAIN145 and six public cases.')
