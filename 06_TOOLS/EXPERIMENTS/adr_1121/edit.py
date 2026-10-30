from common import *
import sys,gzip,copy
S=CAND/'snapshot';P=S/'02_BACKEND/semantic_runtime/legal_agent'
p=P/'ontology_context.py';s=p.read_text();s=s.replace("if set(value) != {'mode', 'snapshot', 'snapshot_sha256'}:","if set(value) not in ({'mode', 'snapshot', 'snapshot_sha256'}, {'mode', 'snapshot', 'snapshot_sha256', 'semantic_binding'}):")
s=s.replace("    identities = set()\n", "    if 'semantic_binding' in value:\n        from . import ontology_semantics\n        binding=value['semantic_binding']\n        ontology_semantics.validate(binding['proposal'],binding['originals'],binding['judgments'])\n        for key in ('proposal','originals','judgments'):\n            if digest(binding[key])!=binding[key+'_sha256']:raise ContractError('semantic snapshot changed')\n    identities = set()\n",1);p.write_text(s)
p=P/'ontology_assessment.py';s=p.read_text();needle="        payload = deepcopy(compiled['payload'])";assert s.count(needle)==1
s=s.replace(needle,needle+"\n        if settings.get('semantic_binding'):\n            from .ontology_semantics import compile_plan\n            semantic=compile_plan(settings['semantic_binding'],fragments)\n            payload['semantic_plan']=semantic")
s=s.replace("원문과 개념·관계를 함께 보고 이번 응답에서", "semantic_plan이 있으면 측정 대상·산정 입력/방식·범위·조건·효과·예외 대상의 의존 순서를 원문과 함께 검토한다. EX​PERIMENT_PROPOSAL_NOT_APPROVED는 과거 에이전트 판단에서 제안된 연구 지식이며 원문보다 우선하지 않는다. UNKNOWN은 미확보이며 거짓이나 0이 아니다. 서로 다른 효과와 그 조건·예외를 합치지 않고 현재 사안의 적용은 직접 판단한다. 원문과 개념·관계를 함께 보고 이번 응답에서".replace('\u200b',''))
p.write_text(s)
# Construct the build input solely from the previously delivered originals and
# actual agent claims. Exact anchors and judgment provenance are host-owned.
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1105-main106-ontology-cm023/artifacts/run-001/ontology/cm-023/canonical'
v=json.loads(gzip.decompress((old/'003.json.gz').read_bytes()))['view'];claims=json.loads(gzip.decompress((old/'003-output.json.gz').read_bytes()))['claims']
f=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1105-main106-ontology-cm023/artifacts/freeze.json')
bundle=next(b for b in read(ROOT/f['snapshot_path'])['bundles'] if b['bundle_id']=='cb-764ad7c91f3f')
options={o['id']:o for o in v['evidence_options']};cards=v['ontology_bundles'][0]['payload']['provisions'];originals=[];mapping={}
for i,(provision,card) in enumerate(zip(bundle['provisions'],cards),1):
 assert provision['anchor']['label']==card['anchor']['label']
 rows=[options[x] for x in card['source_refs']];text=''.join(x['text'] for x in sorted(rows,key=lambda x:x['start_cp']))
 assert hashlib.sha256(text.encode()).hexdigest()==provision['anchor']['content_sha256']
 sid='P'+str(i);originals.append({'id':sid,'anchor':provision['anchor'],'text':text})
 for x in card['source_refs']:mapping[x]=sid
judgments=[]
for c in claims:
 def remap(x):
  if isinstance(x,list):return [remap(v) for v in x]
  if isinstance(x,dict):return {k:remap(v) for k,v in x.items()}
  return mapping.get(x,x) if isinstance(x,str) else x
 judgments.append({'id':c['claim_id'],'provenance':{'path':str((old/'003-output.json.gz').relative_to(ROOT)),'sha256':sha(old/'003-output.json.gz'),'claim_id':c['claim_id']},'judgment':remap(c['rule'])})
put(ART/'build-input.json',{'originals':originals,'judgments':judgments,'concept':bundle['concept'],'authority':'UNREVIEWED_HISTORICAL_AGENT_OPINIONS'})
put(ART/'cases.json',read(ROOT/'04_EXPERIMENTS/ADR/ADR-1105-main106-ontology-cm023/artifacts/cases.json'))
# Freeze the exact legacy landing responses with hashes; no product gold.
put(ART/'prefix.json',{'calls':[{'phase':phase,'path':str(next((old.parent/'raw').glob(f'call-{i:03d}-*/response.json')).relative_to(ROOT)),'sha256':sha(next((old.parent/'raw').glob(f'call-{i:03d}-*/response.json'))),'request_path':str(next((old.parent/'raw').glob(f'call-{i:03d}-*/request.json')).relative_to(ROOT))} for i,phase in [(1,'request-entry'),(2,'candidate-navigation')]]})
# Explicit candidate registration; no production file modifications.
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.register_file(CAND,'02_BACKEND/semantic_runtime/legal_agent/ontology_semantics.py',upstream_state='absent')
print('prepared',len(originals),'originals',len(judgments),'judgments')
