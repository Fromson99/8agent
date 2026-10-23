"""Reserve first; derive public source-curated experience without forging success."""
from common import *
import sys,shutil
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
assert not (DES/'freeze.json').exists()
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/p['manifest_path']);C=ROOT/release['code_root']
assert p['generation']==99 and all(sha(C/n)==h for n,h in release['files'].items())
put(DES/'selected.json',{'pointer':p,'release':release,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
pilot=ROOT/'04_EXPERIMENTS/ADR/ADR-0984-cm-knowledge-reuse-pilot/artifacts'
cases=[c for c in read(pilot/'design/questions.json') if c['id'] in ['cm-051','cm-008','cm-010','cm-007']]
put(DES/'cases.json',cases)
criteria=read(pilot/'offline/criteria.json');put(ART/'offline/criteria.json',{c['id']:criteria[c['id']] for c in cases})
packs=read(pilot/'gold_layer/knowledge.json')[:2]
source_ids={s for k in packs for s in k['evidence_sources']}
sources=[s for s in read(pilot/'gold_layer/sources.json') if s['id'] in source_ids]
put(DES/'curated-source-values.json',{'packs':packs,'sources':sources})
historical=ROOT/'04_EXPERIMENTS/ADR/ADR-0979-latest-main-cm-graph-demo/artifacts/run-001'
experiences=[]
for pack in packs:
    cid=pack['seed'];refs=[]
    for name in ['request.json','response.json','result.json','calls.json','generations.json']:
        path=historical/cid/name;refs.append({'path':str(path.relative_to(ROOT)),'sha256':sha(path)})
    experiences.append({'id':'assumed-success:'+cid,'origin':'COUNTERFACTUAL_SOURCE_CURATED_CORRECTION',
        'actual_log_refs':refs,'actual_success_claim':False,'assumption':'User asks to assume the agent found the correct sources. Historical output is unchanged; added evidence is an authored correction.',
        'correction_values':pack,'sources_added_or_reconfirmed':pack['evidence_sources'],
        'approved_legal_answer':False,'native_success_receipt_created':False})
put(ART/'agent_layer/corrected-experiences.json',experiences)
instructions={
 'joint_underwriter_holding':[
  '증권 인수업무 등에 관한 규정 제6조: 공동주관 기준 보유비율과 적용 범위를 확인한다.',
  '제6조제2항은 자본시장법 시행규칙 제14조제1항만 준용한다. 시행령이나 제2항의 공개매수 분모식을 혼동하지 않는다.',
  '주권·신주인수권·CB·BW 등 증권별 수를 확인한다. CB는 권면액/전환 발행가격이고 1 미만 단수를 제외한다.',
  '제6조제3항의 코스닥 상장규정 제13조제5항제1호 취득 주식과 지정자문인 계약 중 취득 코넥스 주식의 제외를 확인한다. 분모 자동 차감으로 확대하지 않는다.',
  '제6조제4항의 조합·기구 간접 보유는 출자·투자비율로 반영한다.',
  '제6조제5항부터의 확약 제외는 취득시점·확약 제출·5영업일·6개월·증명10영업일 요건을 확인한다.'
 ],
 'listing_sponsor_holding':[
  '코스닥 상장규정 제13조제5항: 일반 국내는 3%·10억원 상한·상장일부터3개월, 신속이전은5%·25억원·6개월이며 특정유형은1년이다.',
  '외국 혁신기술기업은5%·50억원·1년, 기타 외국기업은5%·25억원·1년이다. 상장6개월 후 월 최초수량5% 매각 규정을 확인한다.',
  '일반 국내3개월을6개월로 연장하려면 현재 혁신기술기업 AND 주선인의 세칙 제15조제5항 사유를 모두 확인한다.',
  '세칙 제15조제5항: 현재 예비심사신청일 기준 최근3년 내 주선한 기술성장기업이 그 상장 이후2년 내 환기·관리 지정 또는 형식적·실질심사 상장폐지 사유에 해당한다.',
  '세칙 제15조제4항: 사모취득, 예비심사 신청일부터 신규상장 신청일까지 취득, 미청약 잔여 인수수량 포함을 확인한다.',
  '규정 제13조제6항 거래소 재량 면제와 제외 유형을 구분한다. 현재 사건 조건이 없으면 일반 조건부 설명으로 답한다.'
 ]}
templates=[]
for pack in packs:
    refs=[]
    for check in pack['checks']:
        eb=check['evidence_binding'];s=next(x for x in sources if x['id']==eb['source_id'])
        for bid in eb['block_ids']:
            block=next(b for b in s['blocks'] if b['id']==bid)
            ref={'document_id':s['document_id'],'version':s['document_id'],'locator':bid,'content_hash':block['sha256']}
            if ref not in refs:refs.append(ref)
    # Bound model guidance; source route separately retains every checked block.
    essential={'underwriting':['111','112','113','118'],'counting':['129'],'listing':['194','195','197','198'],'listing_detail':['94','95','96','97']}
    refs=[r for r in refs if any(r['document_id']==s['document_id'] and r['locator'] in essential.get(s['id'],[]) for s in sources)]
    definition={'schema_version':'legal-knowledge-v1','kind':'METHOD','title':pack['title'],
      'description':'공개 CM 실제 로그에서 누락한 근거를 보완한 실험용 검토 방법. 원문을 다시 읽고 현재 질문의 관련성·예외를 판단한다. 법률 승인 아님.',
      'scope':{k:{'mode':'UNSPECIFIED','values':[]} for k in ('business','product','role','action','jurisdiction')},
      'source_refs':refs,'dependencies':[],'lookup_terms':pack['entry_terms'],'effective_from':None,'effective_to':None,
      'content':{'purpose':pack['title'],'requested_outputs':['질문에 필요한 근거·조건·미확인 사항'],'inputs':[],
        'evidence_needs':[next(s for s in sources if s['id']==sid)['title'] for sid in pack['evidence_sources']],
        'steps':[{'id':f'check-{i}','label':t,'capability':'READ_SOURCE','after':[]} for i,t in enumerate(instructions[pack['id']])],'policies':[]}}
    templates.append({'key':pack['id'],'definition':definition,'seed':pack['seed']})
put(DES/'method-templates.json',templates)
criteria={'hypothesis':'Source-curated experience persisted through existing wiki and knowledge authorities reduces discovery/calls and omissions on two seed and two related CM questions.',
 'success':['Persist corrected experience -> source-bound shortcut/wiki -> METHOD and typed APPLICATION -> published local research release',
 'Same native /v1/rag/ask path with baseline off vs knowledge consume; all original-source, permission and state validators retained',
 'Report each case speed, calls, source coverage and frozen required/forbidden criteria; a hit is not correctness'],
 'limits':{'max_requests':8,'max_model_calls_per_request':40,'wall_seconds_per_request':1800,'concurrency':1,'rss_gib':6,'minimum_available_gib':3},
 'order':[[c['id'],a] for i,c in enumerate(cases) for a in (['baseline','knowledge'] if i%2==0 else ['knowledge','baseline'])],
 'failure':'Stop new calls on code/source/ACL/state integrity failure or RAM floor. Normal bounded model/provider failures remain outcomes, no adaptive whole-case reruns.',
 'recovery_owner':'native gateway only; ExperimentClient max_repairs=0; started request is never replayed with fresh budget',
 'quality':'Offline author review of pre-frozen criteria; no automated legal certification. Both seed and related CM were previously exposed; not holdout.',
 'scope':'WSL research candidate using MAIN99 native app and immutable source generation; local SQLite is research storage, not GENOS/Oracle deployment.',
 'counterfactual':'Historical failed logs remain failed. Manual source correction substitutes only assumed successful learning input; new agent runs are actual.',
 'isolation':'Frozen selected MAIN99 code plus bounded export grant and source-route knowledge bridge. No selected MAIN pointer or production code modification.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Paired elapsed seconds/calls and frozen core criteria per4 cases; actual route and ontology consumption',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria)
m['design']['arms'][0].update(changes='MAIN99 native API with knowledge consumer off, fresh session per case',controls='Same native code, model, public scope, source generation and limits')
m['design']['arms'][1].update(changes='Existing knowledge publication and source-route bridge on; frozen corrected-log knowledge',controls='Same current source re-read/selection/assessment/composition, no cached answers')
m['design']['retrieval_stage_plan']={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{a:[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}] for a in ['baseline','knowledge']}}
m['dataset'].update(name='CM051/008 seeds; CM010/007 related reuse',version='cm 20261022',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'native_rag_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Two curated seeds and two previously exposed related CM; alternating arm order frozen before calls',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
candidate=ac.snapshot(ADR,'knowledge',[str((C/n).relative_to(ROOT)) for n in release['files']]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/pipeline/shortcut_package.py','02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py'],experiment_id=m['experiment_id'],arm_id='knowledge',run_ids=['run-001'])
S=candidate/'snapshot'/release['code_root']
# Previously tested exact public-definition grant. Preserve the rest of MAIN99.
bridge=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0958/integrated/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/knowledge_bridge.py'
if not bridge.exists():bridge=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0958/integrated/snapshot/02_BACKEND/semantic_runtime/legal_agent/knowledge_bridge.py'
code=bridge.read_text()
code=code.replace('    host.knowledge_plan = value\n    return value','''    host.knowledge_plan = value
    binder = getattr(transport, 'knowledge_source_route', None)
    if binder is not None and value['mode'] == 'consume' and plan['items']:
        path = binder(plan, scoped, question, source_binding)
        if path:
            host.model.ensure().sources.core_evidence_route = path
            work.event('KNOWLEDGE_SOURCE_ROUTE_BOUND', {'plan_hash': plan.get('plan_hash'),
                'targets': len(path['targets']), 'origins': path['origins'], 'legal_claim_reuse': False})
    return value''')
(S/'02_BACKEND/semantic_runtime/legal_agent/knowledge_bridge.py').write_text(code)
config=read(S/'00_SYSTEM/PIPELINE.json');config['legal_knowledge'].update(management_enabled=True,consumer_mode='consume');put(S/'00_SYSTEM/PIPELINE.json',config)
put(DES/'candidate.json',{'path':str(candidate.relative_to(ROOT)),'selected_code_relative':release['code_root']})
print('Prepared4cases,2corrected experiences,2METHOD templates; candidate not frozen; no model calls')
