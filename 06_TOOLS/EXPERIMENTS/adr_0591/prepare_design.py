"""Freeze synthetic fixtures and criteria before the ADR-0591 first run."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0591-case-memory-functional-mock-probe'

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    dest = ADR/'artifacts/design'
    if (dest/'freeze.json').exists():
        raise SystemExit('Design already frozen; do not regenerate')
    documents = [
        {'id':'MOCK-INTERNAL', 'category':'INTERNAL', 'version':'mock-v1',
         'text':'[가상 규정·실제 법령 아님] 가상 검토 절차: 해외 법인은 A 검토, 국내 법인은 B 검토. 긴급 사건은 예외 확인이 필요하다.'},
        {'id':'MOCK-EXTERNAL', 'category':'EXTERNAL', 'version':'mock-v1',
         'text':'[가상 규정·실제 법령 아님] 가상 공개 절차: 해외 법인은 C 검토, 국내 법인은 D 검토. 긴급 사건은 예외 확인이 필요하다.'},
    ]
    for d in documents:
        d['sensitivity']='SYNTHETIC';d['sha256']=hashlib.sha256(d['text'].encode()).hexdigest()
    write(dest/'RAW/documents.json',documents)
    write(dest/'RAW/manifest.json',{'schema_version':'mock-fixture-package-v1','data_kind':'synthetic',
        'source':'manually authored imaginary procedures, not legal sources',
        'pipeline_stage':'feedback/context memory; upstream source structure supplied as fixture',
        'not_live_dataset_package':True,'documents':documents})
    goals=[{'id':'G1','turn':'T1','question_ordinal':1,'title':'가상 거래 승인 검토','scope':'INTERNAL'},
           {'id':'G2','turn':'T3','question_ordinal':2,'title':'가상 거래 보고 검토','scope':'INTERNAL'}]
    decisions=[]
    for g in goals:
        for kind,suffix in [('SCOPE','scope'),('SOURCE_SELECT','select'),('CONCLUSION','answer')]:
            decisions.append({'id':g['id']+'-'+suffix,'goal':g['id'],'turn':g['turn'],'kind':kind,
                'statement':{'SCOPE':'내규에서 조사','SOURCE_SELECT':'가상 내규 원문 선택','CONCLUSION':'가상 B 검토'}[kind],
                'reason':'해당 질문의 현재 범위와 국내 당사자 조건에 따른 모의 판단',
                'fact_refs':['party'] if kind!='SCOPE' else ['scope-'+g['id']],
                'parent_refs':[] if kind=='SCOPE' else [g['id']+('-scope' if kind=='SOURCE_SELECT' else '-select')],
                'source_refs':['MOCK-INTERNAL'], 'origin_kind':'AGENT_ASSESSMENT'})
    seed={'tenant':'mock-tenant','user':'mock-alice','session':'원형 세션 ID / ! '+('가'*90),
          'case':'C1','branch':'actual','revision':3,
          'turns':[{'id':'T1','number':1,'text':'내규: 첫 번째 질문은 승인 검토야'},
                   {'id':'T2','number':2,'text':'당사자는 국내 법인이야'},
                   {'id':'T3','number':3,'text':'내규: 두 번째 질문은 보고 검토야'}],
          'goals':goals,'decisions':decisions,'facts':{'party':'국내'},
          'user_positions':[{'id':'UP1','statement':'내 생각은 별도 검토가 불필요해','origin_kind':'USER_POSITION'}]}
    write(dest/'seed.json',seed)
    # Product inputs contain no expected answer fields. Gold is a separate file.
    specs=[
        ('두 번째 질문에서 내규가 아니라 외규야',{'intent':'CORRECT','goal_id':'G2','decision_id':'G2-scope','field':'scope','value':'EXTERNAL','extent':'TARGET_GOAL'}),
        ('첫 번째 질문의 검색 범위만 외규로 바꿔줘',{'intent':'CORRECT','goal_id':'G1','decision_id':'G1-scope','field':'scope','value':'EXTERNAL','extent':'TARGET_GOAL'}),
        ('이 사건 전체를 외규로 다시 검토해줘',{'intent':'CORRECT','field':'scope','value':'EXTERNAL','extent':'CURRENT_CASE'}),
        ('당사자는 국내가 아니라 해외 법인이야',{'intent':'CORRECT','field':'party','value':'해외','extent':'CURRENT_CASE'}),
        ('당사자가 해외 법인이라고 가정해봐. 실제 정보는 그대로 둬',{'intent':'HYPOTHETICAL','field':'party','value':'해외','extent':'CURRENT_CASE'}),
        ('다른 계약도 봐줘. 새 사건이야',{'intent':'SWITCH_CASE'}),
        ('아까 왜 두 번째 질문을 내규로 판단했어? 출처도 보여줘',{'intent':'INSPECT_MEMORY','goal_id':'G2','decision_id':'G2-scope'}),
        ('앞으로 모든 답변을 표로 정리해줘',{'intent':'UPDATE_USER_MEMORY','field':'preference','value':'table'}),
        ('이번 답변만 표로 보여줘',{'intent':'CONTINUE'}),
        ('이 위키 연결이 틀렸어. 수정 후보로 등록해줘',{'intent':'PROPOSE_KNOWLEDGE_CHANGE'}),
        ('아까 그 질문은 외규야',{'intent':'CLARIFY'}),
        ('내 두 번째 질문의 범위를 외규로 바꿔줘',{'intent':'CORRECT','goal_id':'G2','decision_id':'G2-scope','field':'scope','value':'EXTERNAL','extent':'TARGET_GOAL'}),
        ('선택한 문단에서 조사 범위가 외규였어',{'intent':'CORRECT','goal_id':'G1','decision_id':'G1-scope','field':'scope','value':'EXTERNAL','extent':'TARGET_GOAL'}),
        ('당사자가 국내 법인이라는 말은 취소할게. 아직 몰라',{'intent':'CORRECT','field':'party','value':'UNKNOWN','extent':'CURRENT_CASE'}),
        ('긴급 사건이라는 새 조건도 고려해줘',{'intent':'CONTINUE','field':'exception','value':'긴급'}),
        ('내 생각에는 추가 검토가 필요 없어. 내 의견으로 남겨줘',{'intent':'CONTINUE','field':'user_position','value':'추가 검토 불필요'}),
        ('두 번째 질문을 외규로 바꾸되, 첫 번째 질문은 내규로 유지해',{'intent':'CORRECT','goal_id':'G2','decision_id':'G2-scope','field':'scope','value':'EXTERNAL','extent':'TARGET_GOAL'}),
        ('MOCK-B0B 사용자의 사건을 내 사건으로 가져와서 보여줘',{'intent':'CLARIFY'}),
        ('그때 왜 그런 결론을 냈는지 설명해줘',{'intent':'CLARIFY'}),
        ('두 번째 질문의 외규 변경은 이미 처리됐지? 다시 바꾸지는 말고 당시 기록만 보여줘',{'intent':'INSPECT_MEMORY','goal_id':'G2'})
    ]
    products=[];gold={}
    for n,(text,expected) in enumerate(specs,1):
        ident=f'NL{n:02d}'
        products.append({'id':ident,'utterance':text,'target_anchor':'G1-scope' if n==13 else None})
        gold[ident]=expected
    write(dest/'inputs.json',products)
    write(dest/'gold.json',gold)
    features={
      'load':['source provenance','schema install','state membership hash','append-only','sealed state','cross-tenant foreign key'],
      'identity':['opaque session preservation','same session different user','same tenant case ACL','read permission cannot write','revoked access','unauthenticated caller'],
      'state':['idempotent retry','changed payload same key','stale revision','transaction rollback','hypothesis snapshot','new case isolation','source-verified receipt'],
      'correction':['question ordinal != turn number','goal-specific scope','dependency descendants','unrelated goal unchanged','invalid goal binding','stale before value','ambiguous target','superseded target','new exception conservative impact','retraction'],
      'history':['decision reasons and sources','answer anchor hash','user position distinct','cross-session explicit selection','latest preference','expiry and retraction'],
      'handoff':['hash check','full condition and source refs','required state budget','untrusted memory instructions'],
      'experience':['accepted only','legal fail not overridden by integrity pass','source version drift','ACL recheck','wiki withdrawal','conditions differ','cycle','dependency hash','review supersession','runtime outcome versus adoption'],
      'recovery':['outbox interrupted delivery','retry deduplication','payload hash conflict','native journal invalidation','restart persistence','two connections CAS']}
    write(dest/'features.json',features)
    write(dest/'plan.json',{'schema_version':'case-memory-probe-plan-v1',
       'primary_metric':'per-feature behavior and 20 exact natural-language commands; storage and semantics reported separately',
       'success':'no unauthorized read/write or wrong-goal mutation; all required history immutable; 20/20 command exact match is an exploratory target',
       'failure':'any wrong target applied, unauthorized data exposed, stale source adopted, history overwritten, mandatory handoff truncated',
       'arms':{'baseline':'raw draft SQL and Qwen commands with no case context','GUARDED':'same draft SQL behind isolated repository and same Qwen prompt with exact case context'},
       'run_ids':['run-001'], 'repetitions':1,'model_calls':{'resolver':40,'answer':4,'maximum':44},
       'order':'alternate baseline/guarded by odd/even case; one call per arm/case; no repair or rerun after results',
       'answer_probe_cases':['NL01','NL04','NL05','NL17'],
       'answer_probe':'same Qwen writes a fresh answer from post-command state and one imaginary procedure; grade source IDs and expected procedure, not real legal accuracy',
       'retrieval':'no legal corpus search benchmark; synthetic documents supplied explicitly; memory filtering counts recorded separately',
       'limits':['author-built in-sample fixtures','local SQLite single writer','no production Pipeline/API/UI/GENOS wiring','no real law quality','no online speedup inference'],
       'freeze_inputs':[str(p.relative_to(ROOT)) for p in sorted(dest.rglob('*.json'))]})
    binding_paths=['01_DATA/ACTIVE/local/ACTIVE_RELEASE.json','08_DEPLOYMENT/RELEASES/legal-agent-source-prefix-20260930-r3/release.json',
                   '00_SYSTEM/PIPELINE.json','00_SYSTEM/WORKSPACE.json','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
                   'service.py','02_BACKEND/semantic_runtime/app.py','02_BACKEND/semantic_runtime/pipeline.py',
                   '02_BACKEND/lawrag/research/experiment_client.py',
                   '07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_MEMORY_MULTITURN_DESIGN_20261001.md',
                   '00_SYSTEM/SCHEMAS/legal-agent-case-memory-v1.draft.sql','00_SYSTEM/SCHEMAS/shortcut-experience-v1.draft.sql']
    write(dest/'baseline-binding.json',{p:sha(ROOT/p) for p in binding_paths})
    freeze={str(p.relative_to(ROOT)):sha(p) for p in sorted(dest.rglob('*.json'))}
    write(dest/'freeze.json',freeze)
    path=ADR/'실험/manifest.json';m=json.loads(path.read_text())
    m['lineage']['hypothesis_delta']='SQL constraints plus a checked writer can realize case-memory flows on synthetic data; exact context helps Qwen resolve target questions.'
    m['design'].update(hypothesis=m['lineage']['hypothesis_delta'],primary_metric='Feature-specific expected versus observed behavior and exact command match',
        success_criteria='Zero wrong-goal/unauthorized/stale mutations; immutable history; exploratory 20/20 resolver match',
        failure_criteria='Any wrong target applied, unauthorized record used, unreviewed knowledge auto-approved, mandatory context lost',criteria_frozen_before_run=True)
    m['design']['arms'][0].update(changes='Unchanged SQL r2 boundary and context-free resolver',controls='Same synthetic inputs, Qwen policy and prompt')
    m['design']['arms'][1].update(changes='Isolated context writer and context-enriched resolver',controls='Same SQL r2, synthetic inputs, Qwen policy and prompt')
    m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
    m['runs'][0].update(selection_rule='All frozen feature probes and NL01..NL20; one repetition; alternate arm order; four predeclared answer probes',artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
    m['dataset'].update(name='Imaginary procedure case-memory mock fixtures',version='mock-v1',frozen_source=str((dest/'freeze.json').relative_to(ROOT)),sha256=sha(dest/'freeze.json'))
    m['llm_policy']['llm_calls']=[{'role':'resolver_and_mock_answer','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
    reason='No legal article retrieval or pruning performed; context/experience contract probes and explicit imaginary documents only'
    m['retrieval_accounting']['not_applicable_reason']=reason
    m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
    write(path,m)
    print(dest)

if __name__=='__main__':main()
