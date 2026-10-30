from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1130-ontology-precompiled-scenario-selection';ART=ADR/'artifacts';D=Path(__file__).parent
read=lambda p:json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1124-ontology-explicit-exception-contract';f=read(old/'artifacts/freeze.json');source=ROOT/f['code_root']
criteria={'hypothesis':'Source-bound deterministic precompilation can deliver self-contained business scenarios, so runtime LLM selects IDs/relevance/missing facts without generating legal structures or final legal prose.',
'primary':['Package compiled before questions; runtime compiler/model legal construction calls0','Exact selected scenario body preserved in final rendering','CM023 selects normal and threshold-exclusion paths; refund selects refund; exclusion selects exclusion; unrelated question returns NO_MATCH','No invented source/permission/reference; pending readings not silently marked reviewed'],
'success':'All integrity and native HTTP tests pass; four fixed selector probes select their predeclared route expectations with no legal-text rewrite. Failures preserved; no general legal-quality certification.',
'authoring':'Codex-authored explicit recipe from saved exact originals, using known1124 failure analysis as in-sample design. No gold/reference answer in product or recipe. No claim of automatic ontology creation or human approval.',
'run':'Compile package once before tests/calls, then four fixed questions sequentially on same package through actual product selector/materializer. Native HTTP through synthetic transport separately. No live full navigation, historical1124 is provenance only, not paired baseline.',
'controls':['MAIN107-based1124 code ancestry','same28 original fragments and model policy','Qwen3.8 Parasail FP8 reasoning none fallback none output cap none','no active release mutation; no model rerun after results'],
'limits':{'calls_per_case':2,'total_calls':8,'max_output_tokens':None,'max_rss_gib':4,'heavy_processes':1,'min_available_gib':3,'min_disk_gib':20},
'failure_contract':{'schema':'Existing output.bounded_decision owns at most1 repair; exact menu immutable.','integrity':'Changed package/current original/hash/ACL or unknown source rejects; never fix by regenerating hashes.','missing':'Unavailable originals withhold corresponding paths. No match/unknown remains limited; no path invented. Existing ordinary source mode stays available when no package is configured.','facts':'Selector marks CONDITIONAL and missing facts; general request does not require personal facts; route selection is relevance not case fact verification.','publication':'Existing claim span checks and deterministic compose; source-backed authored text preserved exactly. Prior agent judgments remain pending, not auto-adopted.'}}
put(ART/'criteria.json',criteria)
for n in ('baseline.json','composition.json','build-input.json'):shutil.copyfile(old/'artifacts'/n,ART/n)
put(ART/'cases.json',[{'id':'cm-023','question':read(old/'artifacts/cases.json')[0]['question']},{'id':'scenario-refund','question':'상장 주식의 정산기준일 가액이 당초 증여세 과세가액보다 낮아진 경우의 환급 요건과 연결된 계산 기준을 설명해 주세요. 일반 규정 설명입니다.'},{'id':'scenario-exclusion','question':'상장차익 증여의제에서 계산된 이익이 기준금액보다 작은 경우의 처리와 기준금액 산식을 알려 주세요. 일반 규정 설명입니다.'},{'id':'scenario-unknown','question':'부동산 담보대출의 연체이자는 어떤 금리로 계산하나요?'}])
put(ART/'rubric.json',{'authored_before_calls':True,'quality_certified':False,'cases':{'cm-023':{'required_paths':['S1','S2'],'forbidden_paths':[]},'scenario-refund':{'required_paths':['S3'],'forbidden_paths':['S1','S2','S4','S5','S6','S7','S8']},'scenario-exclusion':{'required_paths':['S2'],'forbidden_paths':['S1','S3','S4','S5','S6','S7','S8']},'scenario-unknown':{'required_paths':[],'outcome':'NO_MATCH'}}})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary'],success_criteria=criteria['success'],failure_criteria='Any integrity failure, route mismatch or final scenario drift',criteria_frozen_before_run=True)
for a in m['design']['arms']:a.update(changes='historical parent, not executed' if a['id']=='baseline' else 'Precompiled scenario package + closed-choice selector + deterministic final rendering',controls='Same original28 and parent MAIN107 code; noncomparative implementation probe')
m['runs'][0].update(arms=['scenario'],selection_rule=criteria['run'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (ROOT/n).is_file()];C=ac.snapshot(ADR,'scenario-r1',present,experiment_id=m['experiment_id'],arm_id='scenario',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(source/n)==h,n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
put(ART/'parent.json',{'freeze_path':str((old/'artifacts/freeze.json').relative_to(ROOT)),'freeze_sha256':sha(old/'artifacts/freeze.json'),'pointer_sha256':f['pointer_sha256'],'snapshot_path':f['snapshot_path'],'snapshot_digest':f['snapshot_digest']})
(D/'common.py').write_text("from pathlib import Path\nimport json,hashlib\nROOT=Path(__file__).resolve().parents[3]\nADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1130-ontology-precompiled-scenario-selection'\nART=ADR/'artifacts'\nCAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1130/scenario-r1'\ndef read(p):return json.loads(Path(p).read_text())\ndef sha(p):\n with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()\ndef put(p,v):\n p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\\n')\n")
print(S)
