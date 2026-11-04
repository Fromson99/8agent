from pathlib import Path
import sys,json,hashlib,shutil
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1319-multiturn-command-assessment-repair';ART=ADR/'artifacts';DES=ART/'design'
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary

def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():
  if read(p)==v:return
  assert p.name=='manifest.json'
  p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 else:write_summary(p,v)
DES.mkdir(exist_ok=True)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path']);C=ROOT/release['code_root']
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
assert all(sha(C/n)==h for n,h in release['files'].items())
put(DES/'baseline.json',{'pointer':pointer,'release':release})
files=sorted(release['files']);put(DES/'working-before.json',{n:sha(ROOT/n) for n in files})
criteria={
 'hypothesis':'Method-specific command schemas prevent the observed RESEARCH_REENTER+AUTHORIZED contradiction. Bounded repairs retain the exact failed proposal and action identity for a mechanical field error. Final review repairs identify the conflicting adoption fields, preserving model choice and all source/security checks. Existing known-failure resume and unknown-stop paths remain intact.',
 'success':['Recorded command009 is rejected at the method-specific schema with /document_scope_mode=KEEP; the same goal with KEEP is executable.','A field-only repair cannot silently change method or target. A separately checked semantic intention failure can change them.','Repeat, followup, scope switch, topic change and failure/resume contracts pass with actual journal/API consumers; no extra duplicate dispatch, no stale scope/evidence reuse.','Final assessment retains original claims, requirements, gaps, source/hash/ACL checks; gives explicit competing repair paths without host-inferred legal conclusions.','Public live followups keep intended goal and receive cited substantive answers; report provider, semantic and UI/private limitations separately.'],
 'failure':['Do not certify question quality from mocks, schema acceptance or nonempty original-only text.','Unknown external result stops all further live dispatch; known429 follows the frozen current provider policy, never automatic resend of UNKNOWN.','Three consecutive technical failures stop the public campaign; no repeated failed live cell under this ADR.','No source/ACL/hash drift; no MAIN promotion, GENOS deployment or email under this task.'],
 'limits':{'sequential_heavy_workers':1,'max_physical_per_request':40,'max_physical_total':160,'model_seconds':180,'request_seconds':1800,'rss_GiB':5,'minimum_free_GiB':3,'start_free_GiB':5,'swap_growth_MiB':128},
 'sequence':['Implement isolated candidate','Freeze before before/after effect tests','Five-pattern contract/API verification plus original-response diagnosis','Public multi-turn live once if contracts pass; internal scope and provider failure via synthetic API','Inventory all R3 rows; expand public questions only if core live checks pass and call budget allows','Selective working-code integration with pins; preserve selected MAIN138'],
 'baseline':'Exact MAIN138 selected release; prior1318 MAIN137 records are regression inputs, not new MAIN138 live outcomes.',
 'provider_policy_path':'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json','provider_policy_sha256':sha(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'),
 'user_authorization':'질문날리는것들 확인해줘 특히 멀티턴...수정이나 실험해봐 내부에서; 어떻게 수정해야할까?; 진행해봐',
 'scope_note':'Private ordinary RAG cannot be falsely marked public. Live private/GENOS UI coverage remains unverified where no authorized local transport supports it.'}
cases=[{'id':'repeat','question':'상법상 정기주주총회는 언제 소집해야 하나요?','followups':['상법상 정기주주총회는 언제 소집해야 하나요?','그럼 임시총회는 언제 소집하나요?'],'mode':'외규'},
 {'id':'followup','question':'상법상 정기주주총회는 언제 소집해야 하나요?','followups':['그럼 임시총회는 언제 소집하나요?'],'mode':'외규','covered_in':'repeat'},
 {'id':'scope-switch','question':'위험관리위원회 회의는 정기적으로 언제 개최하나요?','modes':['내규','외규'],'live':'internal transport unavailable; synthetic API'},
 {'id':'topic-change','question':'상법상 정기주주총회는 언제 소집해야 하나요?','followups':['상법 제369조의 의결권 원칙을 알려줘.'],'mode':'외규','live_sequence':'after repeat group in same session'},
 {'id':'failure-resume','faults':['known429','UNKNOWN','accepted-then-interrupted','duplicate-request'],'live':'fault injection only; never create extra provider failures'}]
put(DES/'criteria.json',criteria);put(DES/'cases.json',cases)
shutil.copyfile(ROOT/criteria['provider_policy_path'],DES/'provider-policy.json')
book=ROOT/'09_ARTIFACTS/REPORTS/DOCUMENTS/20261104-integration-template-r3/작성데이터.json';put(DES/'workbook-r3.json',read(book))
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Action/goal continuity, original-proof final answer availability, exact failure/resume and duplicate dispatch counts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')});m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Unchanged selected MAIN138',controls='Exact selected525 files; same recorded regression inputs; no new baseline model calls')
m['design']['arms'][1].update(changes=criteria['hypothesis'],controls='Same selected source/generation, validation and model; public live is candidate-only, no causal quality or speed claim')
m['dataset'].update(name='Five multi-turn patterns plus60 R3 test rows',version='20261104-r3-repair',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['runs'][0].update(selection_rule='Declared five patterns; offline baseline/candidate; single candidate public sequence; public expansion conditional on core pass',artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[]
m['llm_policy']['provider_override']={'path':str((DES/'provider-policy.json').relative_to(ROOT)),'sha256':sha(DES/'provider-policy.json')}
for arm in ('baseline','repaired'):m['design']['retrieval_stage_plan']['stages_by_arm'][arm]=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'repaired',files,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n in files:shutil.copyfile(C/n,can/'snapshot'/n)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files})
print('Isolated MAIN',pointer['generation'],len(files),'files; frozen criteria, no product mutation')
