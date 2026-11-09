"""ADR-1456: the same 8 branch scenarios as ADR-1454/1455, candidate r14 run twice (variance check before MAIN).
baseline = selected MAIN176 (cells already run in ADR-1454, reused); candidate = stage 20261108-multiturn-followups-r14 (MAIN176 + ten files).
User rule 2026-11-08: anything connected to an earlier question continues it (S1 T4, S6 T3 are continue), an explicit new-question wording starts a new one."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(parents=True,exist_ok=True);assert not (DES/'freeze-live.json').exists()
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==176
rel=read(ROOT/ptr['manifest_path']);S=ROOT/rel['code_root'];files=rel['files']
assert all(sha(S/n)==h for n,h in files.items())
STAGED=ROOT/'09_ARTIFACTS/AUDITS/20261108-multiturn-followups-r14/staged'
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
public=read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
def st(n,q,expect,mode=None,article=None):return {'number':n,'question':q,'mode':mode,'expect':expect,'article':article}
R1='위험관리위원회는 어떤 사항을 심의·의결해?';INT='내부회계관리제도 구축의무와 그 면제 기준은 무엇인가요'
SR='자본시장법상 단기매매차익 반환 대상은 누구야?';GM='상법상 주주총회 보통결의 요건은?'
cases=[
 {'id':'s1-same-law-other-article','steps':[st(1,R1,'new','외규','지배구조법 제21조'),st(2,'준법감시인은 어떻게 임면해?','new',None,'지배구조법 제25조'),
   st(3,'그 사람 임기는 몇 년이야?','continue:2',None,'지배구조법 제25조'),st(4,'위험관리위원회 구성은 어떻게 해야 해?','continue:1',None,'지배구조법 제16조')]},
 {'id':'s2-other-law-field','steps':[st(1,R1,'new','외규','지배구조법 제21조'),st(2,INT,'new',None,'외감법 제8조'),
   st(3,SR,'new',None,'자본시장법 제172조'),st(4,'아까 면제 기준에서 자산총액은 얼마 미만이었지?','continue:2',None,'외감법 제8조')]},
 {'id':'s3-article-number-only','steps':[st(1,GM,'new','외규','상법 제368조'),st(2,'상법 제391조는 뭐야?','new',None,'상법 제391조'),
   st(3,'금융지주회사법 제45조도 알려줘','new',None,'금융지주회사법 제45조'),st(4,'제368조에서 정관으로 다르게 정할 수 있어?','continue:1',None,'상법 제368조')]},
 {'id':'s4-continue-controls','steps':[st(1,SR,'new','외규','자본시장법 제172조'),st(2,'반환 청구는 누가 할 수 있어?','continue:1',None,'자본시장법 제172조'),
   st(3,'6개월 기간은 언제부터 세?','continue:1',None,'자본시장법 제172조'),st(4,'그럼 미공개중요정보 이용은 어떻게 금지돼?','new',None,'자본시장법 제174조')]},
 {'id':'s5-compare','steps':[st(1,GM,'new','외규','상법 제368조'),st(2,'이사회 결의는?','new',None,'상법 제391조'),
   st(3,'두 결의 요건의 차이를 정리해줘','background:1,2',None,'상법 제368조·제391조')]},
 {'id':'s6-mentioned-article','steps':[st(1,R1,'new','외규','지배구조법 제21조'),st(2,'제27조 위험관리기준에는 뭘 정해야 해?','continue:1',None,'지배구조법 제27조'),
   st(3,'자산총액 2조원 이상이면 위험관리위원회를 꼭 둬야 해?','continue:1',None,'지배구조법 제16조')]},
 {'id':'s7-guidance-unanswered','steps':[st(1,'리스크 한도를 넘는 거래는 누가 승인해?','new','외규',None),
   st(2,'금융회사 지배구조법 제21조를 보면 될 거야','continue:1',None,'지배구조법 제21조')]},
 {'id':'s8-ask-when-unclear','steps':[st(1,R1,'new','외규','지배구조법 제21조'),st(2,INT,'new',None,'외감법 제8조'),
   st(3,'제24조는?','ask',None,None),st(4,'1번째 질문 법 기준으로 봐줘','continue:1',None,'지배구조법 제24조')]}]
for c in cases:c['document_ids']=public
criteria={'authorization':'이거 구현해봐 … 4번은 조금이라도 이어져있으면 연결된 질문이라고 판단하고 그리고 사용자가 직접적으로 뭐 새롭게 찾아줘 이러한 내용을 … 나리면 Llm이 감지해서 새질문으로 가게하는거야 (2026-11-08) / 앞선 기준: 다른 법조항을 이야기하면 새 질문, 의도를 모르겠으면 n번째 질문에 대한 것인지 묻기, 못 찾은 질문의 가이드는 이어가기',
 'scope':'Actual local root service, isolated runtime, SQLite source, public allowlist ∩ financial_team, default profile (guided). Candidate r14 run twice (run-1, run-2), one cell at a time; the MAIN176 baseline is the ADR-1454 baseline arm (same scenarios, same release).',
 'expect_rules':{'new':'CASE_START (a new goal, no earlier goal targeted)','continue:n':'executes the goal created by turn n (any same-goal method)','background:n,m':'CASE_START whose related selection includes turns n and m','ask':'CLARIFY naming an earlier question ("n번째 질문" or the listed form "n번째 “…”")'},
 'primary_metric':'Turns whose branch matches the frozen expectation (turn 1 excluded); per arm.',
 'secondary':['Answer cites the expected article (recorded, not graded)','Physical calls, seconds, UNKNOWN','Source/ACL/wire mismatch 0; duplicate request adds 0 calls'],
 'limits':{'physical_total':600,'per_cell_client_calls':80,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':3,'ram_start_gib':6,'ram_floor_gib':3,'worker_rss_gib':5,'worker_swap_growth_mib':128,'workers':1,'runs':2},
 'stop':'An UNKNOWN outcome stops its cell and every later cell; no same-question retry.','quality_certified':False,'in_sample':True,
 'note':'S7 turn 1 may answer or ask back; turn 2 must continue it either way. S8 turn 4 is graded only if turn 3 asked. Two independent runs of the same 8 chats; a turn passes a run only if its branch matches; stability = turns correct in both runs.','recorded_not_graded':['S1 T3 / S2 T4 / S3 T4 answer text shorter than the earlier full answer (part re-show)','S8 T3 clarification names the question in the user words (no law the user did not say)','no HTTP 500']}
put(DES/'criteria.json',criteria);put(DES/'live-cases.json',cases)
put(DES/'provider-policy.json',read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
put(DES/'authorization.json',{'request':criteria['authorization'],'documents':public,'scope':'Public-law scenarios; intersect current financial team. No internal documents or grading answers are sent.'})
put(DES/'grading-reference.json',{'expect':{c['id']:[(s['number'],s['expect'],s['article']) for s in c['steps']] for c in cases},'product_input':False})
transport=ART/'transport';transport.mkdir(exist_ok=True)
pins=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
put(DES/'arm-baseline.json',{'code_root':rel['code_root'],'selected_files':files,'note':'selected MAIN176 release code'})
m=read(ADR/'실험/manifest.json')
m['runs']=[{**m['runs'][0],'id':'run-001','purpose':'primary'},{**m['runs'][0],'id':'run-002','purpose':'repeat','parent_run_id':'run-001'}]
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'candidate',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001','run-002'])
snap=can/'snapshot';inventory={n:sha(STAGED/n) for n in files}
for n in files:shutil.copyfile(STAGED/n,snap/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==h for n,h in inventory.items())
changed=sorted(n for n in files if inventory[n]!=files[n])
put(DES/'arm-candidate.json',{'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main176':changed,'tested_copy':str(STAGED.relative_to(ROOT)),
 'contract_regression':'09_ARTIFACTS/AUDITS/20261108-multiturn-followups-r14/regression-compare.json','oracle_guard':'09_ARTIFACTS/AUDITS/20261108-multiturn-followups-r14/oracle-guard/보고서.txt',
 'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
m['lineage']['hypothesis_delta']='r14: a part of an earlier answer asked again shows that part (one claim choice, no search); the clarification names the question in the user words; anything connected to an earlier question continues it unless the user asks for a new question; unverifiable persisted read grants are dropped instead of HTTP 500; an unresolved investigation decision still answers from acquired originals. Two runs measure run-to-run variance.'
m['design'].update(hypothesis=m['lineage']['hypothesis_delta'],primary_metric=criteria['primary_metric'],success_criteria=[criteria['primary_metric'],*criteria['secondary']],
    failure_criteria=[criteria['stop']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['dataset'].update(name='User branch scenarios r2 (8 chats, 28 turns, public documents)',version='frozen-v1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':2}]
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*(DES/n for n in ('criteria.json','live-cases.json','authorization.json','provider-policy.json','arm-baseline.json','arm-candidate.json','grading-reference.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('FROZEN 8 scenarios x 2 runs; candidate',len(changed),'files changed; model0')
