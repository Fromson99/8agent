from common import *
import shutil
from copy import deepcopy
DES.mkdir(parents=True,exist_ok=True)
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1274-final-review-multiturn-recovery/artifacts/design/freeze.json'
f=read(parent);C=ROOT/f['code_root'];assert all(sha(C/n)==h for n,h in f['files'].items())
source=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1271-source-goal-coordinate-recovery/artifacts/design/source.json');put(DES/'source.json',source)
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/p['manifest_path'])
assert p['generation']==131
put(DES/'baseline.json',{'pointer':p,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'selected_release':r,'release':dict(r,data_path=source['data_path']),'experimental_data_override':True,'parent_freeze':{'path':str(parent.relative_to(ROOT)),'sha256':sha(parent)}})
criteria={'hypothesis':'An exhausted review can return verified sources without rejected conclusions, then actual Qwen can use an explicit follow-up fact in the same case and revalidate a supported answer.',
 'success':['Two actual first-turn ASSESS envelopes have need reviews removed and originals retained','First API200 is explicitly REVIEW_INCOMPLETE, zero claims, source-only; no extra COMPOSE','Second fixed fact update preserves goal/investigation and produces validated claims from the same originals','Both identical reposts cause zero physical transmissions','All original/hash/ACL and model request checks pass in a fresh process'],
 'failure':'Transport UNKNOWN or exhausted 429 stops the experiment with no new question/replay. A missing injection or initial recovery failure prevents follow-up. Source-only second turn is not successful answer recovery. No synthetic alteration of second-turn model response.',
 'authorization_change':'ADR1275 first turn recovered but experiment grant rejected core-derived task+facts before second ASSESS. Register only validated host-state derivations of the two fixed approved API requests. Unapproved body/task/document still rejected; product518 unchanged.',
 'limits':{'physical_model_calls_total':40,'per_turn_product_budget':40,'per_turn_wall_seconds':1800,'per_model_seconds':180,'rss_GiB':4,'minimum_available_GiB':3,'max_swap_growth_MiB':128},
 'quality':'One fixed two-turn in-sample fault injection on three synthetic original clauses. No population failure-rate, legal-quality or production latency inference.'}
put(DES/'criteria.json',criteria)
question='복구검증규정 제1조와 제2조를 조문 구조로 찾아 원문을 읽고, 각 조문의 승인·보고 기준을 알려주세요.'
follow='같은 사건입니다. 긴급 복구가 아닌 일반 작업이고, 서면 승인을 받은 뒤 시작했습니다. 작업이 끝난 지 12시간이 지났고 아직 보고하지 않았습니다. 이 사실을 추가해서 보고 기한을 판단해 주세요.'
body={'question':question,'document_ids':source['document_ids'],'use_llm':True,'public_question':True,'team_id':'risk_team','session_id':'adr1277-review-followup','request_id':'incomplete-review'}
cases=[{'id':'review-followup','request':{'API_TYPE':'RAG_ASK','json':body},'followup':{'API_TYPE':'RAG_ASK','json':dict(body,question=follow,request_id='explicit-facts')}}]
put(DES/'cases.json',cases)
put(DES/'authorization.json',{'user_instruction':'전체다 수정했냐? qwen으로 실험하고 (데이터 보내도 됨 외부로) 확인해봐; 나머지 남은 문제 해결해봐 그리고 사용자가 어떻게 422문제를 멀티턴으로 해결할수 잇냐',
 'external_transmission_allowed':True,'synthetic_originals':True,'document_ids':source['document_ids'],'questions':[question,follow],
 'source_manifest_sha256':sha(ROOT/source['data_path']/'manifest.json'),'model':'qwen/qwen3.8-27b','maximum_fixed_turns':2,'new_session_redispatch':False})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']+' Correct only experiment grant for host-derived context; preserve failed ADR1275.'
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual two-turn source-only then supported answer recovery with duplicate calls zero',success_criteria=criteria['success'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Historical MAIN131 failure only; no new baseline model',controls='No stochastic causal comparison')
m['design']['arms'][1].update(changes='Exact frozen ADR1274 recovery code',controls='Same full product profile, Qwen policy, source corpus, request limits and validators')
m['runs'][0].update(arm_ids=['verified'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='One fixed two-turn conversation; first two ASSESS needs cleared; second turn unaltered')
m['dataset'].update(name='Three-clause synthetic recovery policy and fixed explicit fact follow-up',version='20261102-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='Failure recovery audit, no retrieval effect benchmark';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
candidate=ac.snapshot(ADR,'verified',sorted(f['files']),experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001']);S=candidate/'snapshot'
for n in f['files']:
 if sha(S/n)!=f['files'][n]:shutil.copyfile(C/n,S/n)
assert all(sha(S/n)==h for n,h in f['files'].items())
put(DES/'candidate-path.json',{'snapshot':str(S.relative_to(ROOT))})
print('Prepared exact upstream candidate',len(f['files']))
