from common import *
import shutil,sqlite3
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(exist_ok=True);assert not (DES/'freeze-live.json').exists()
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==157
rel=read(ROOT/ptr['manifest_path']);C=ROOT/rel['code_root'];files=rel['files']
assert len(files)==532 and all(sha(C/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
public=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
criteria={'authorization':'지금 우리 메인에서 정관을 변경할때 주주총회 결의요건을 묻는데 여기 떡하니 적혀잇는데 왜 못들고오나? 이유를 확인해봐 내부에서 qwen으로 실험해봐',
 'scope':'MAIN157 actual local root service, default ontology OFF, public commercial-law question diagnostic. Screenshot exact original question and prior session unavailable; three newly frozen formulations. GENOS inaccessible; external Qwen via approved local adapter.',
 'hypothesis':'The source exists, but initial article selection or early ASK_USER/ANSWER handoff can end retrieval before the resolution-requirements article is read. Direct article control distinguishes access failure from navigation choice.',
 'required':['532 serving bytes and source unchanged','Trace actual prompt, actions, source acquisition/delivery and final answer','Answer both numerical conditions from acquired original; missing source or invitation to research is incomplete','No source/ACL/wire mismatch; physical attempts equal budget; duplicate adds zero calls'],
 'limits':{'physical_total':120,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':2,'ram_start_gib':5,'ram_floor_gib':3,'swap_growth_mib':128,'workers':1},
 'stop':'UNKNOWN/resource/source/ACL/code failure stops all later cases; no same-question retry. Every planned question once in declared order.',
 'order':['charter-natural','charter-433','charter-434'],'quality_certified':False,'in_sample':True}
questions=[('charter-natural','정관을 변경할 때 주주총회 결의요건은 무엇인가요?'),
 ('charter-433','상법 제433조에 따라 정관을 변경할 때 필요한 주주총회 결의요건을 알려줘.'),
 ('charter-434','상법 제434조에 따른 정관 변경의 주주총회 결의요건을 알려줘.')]
cases=[{'id':cid,'arms':['selected'],'document_ids':public,'steps':[{'number':1,'question':q,'mode':'외규'}]} for cid,q in questions]
put(DES/'criteria.json',criteria);put(DES/'live-cases.json',cases)
put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'request':criteria['authorization'],'documents':public,'scope':'User-directed public Commercial Act diagnostic, three question strings; intersect current financial team. No screenshot transmission, internal documents or grading answers.'})
photo=Path('/tmp/codex-remote-attachments/01a1ab9e-11a5-7920-b022-18630467818b/F36C8580-7F80-456C-9FA6-E63F2F4C75DE/1-사진-1.jpg')
put(DES/'photo-observation.json',{'path':str(photo),'sha256':sha(photo),'observed':'Photo answer cites433 only; says434/368/435 not read and offers further inquiry. Original question/prior turns and actual serving revision unknown.','exported':False})
db=sqlite3.connect((ROOT/rel['data_path']/'store.sqlite').as_uri()+'?mode=ro',uri=True)
docs=db.execute("SELECT document_id,name FROM document WHERE name LIKE '%> 상법'").fetchall();assert docs
originals=[]
for did,name in docs:
 for uid,parent,raw in db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,)):
  v=json.loads(raw)
  if v.get('family')=='kr_article' and any('제'+num+'조' in json.dumps(v,ensure_ascii=False) for num in ('433','434','435','368')):
   originals.append({'document_id':did,'name':name,'unit_id':uid,'parent_id':parent,'unit':v})
put(DES/'grading-source-locations.json',originals);db.close()
put(ART/'preparation-issues.json',[{'phase':'read-only source inspection','error':'Queried document.title, but current schema column is name','correction':'Inspected schema and used name. Then exact name 상법 matched no row because stored name includes hierarchy; used suffix > 상법. No source mutation or model call.'},{'phase':'setup before freeze','error':'MAIN drift156 to157 caught before baseline save or model calls','correction':'Rebind current157. Changes only Oracle Agent mapping and dependent pins; retrieval and dialogue code identical. ADR slug retains initial reservation name.'}])
transport=ART/'transport';transport.mkdir()
origin=ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json'
pins=read(origin)
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Original acquisition and correct source-grounded quorum answer versus early handoff',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'No completed source-grounded quorum answer'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['retrieval_stage_plan']['stages_by_arm']={'selected':[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]}
for arm in m['design']['arms']:arm.update(changes='Unchanged selected MAIN157; baseline is configuration reference, not an extra execution',controls='Same532 files/default profile/source generation; independent fresh sessions')
m['dataset'].update(name='User photo charter quorum diagnostic, natural/433/434 formulations',version='frozen-v1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['selected'],selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for row,case in zip(m['questions'],cases):
 p=ADR/'실험'/row['file']
 p.write_text(f"# {case['id']}\n\n## 1. 실행 메타\n\nMAIN157 unchanged532; run-001/selected; actual root service; Qwen3.8 Parasail/none; no output cap.\n\n## 2. 사용자 질문 원문\n\n{case['steps'][0]['question']}\n\n사진의 원 질문은 보이지 않아 현재 요청 취지를 재구성한 진단 질문.\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n현재 등록 상법 원문과 두 결의수치 조건을 직접 대조. grading-source-locations.json은 제품 입력 비공개.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz와 source-wire-audit.json 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{case['id']}-selected/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n해당 셀 generations.json 및 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n채점 모델0; 원문/행동/실제 전송/답변 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
 row['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'selected',list(files),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
for n,h in files.items():
 if sha(can/'snapshot'/n)!=h:shutil.copyfile(C/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
desc={'code_root':str((can/'revisions'/rev['revision_id']/'snapshot').relative_to(ROOT)),'selected_files':files,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),DES/'criteria.json',DES/'live-cases.json',DES/'authorization.json',DES/'provider-policy.json',DES/'candidate-selected.json']
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('FROZEN MAIN157/532; three questions; model0; source locations',len(originals))
