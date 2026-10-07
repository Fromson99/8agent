"""Reserve-first, synthetic-only sequential design. Gold never enters product input."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0592-rag-chain-sequential-prototype'
DESIGN = ADR / 'artifacts/design'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def main():
    docs=[]
    for scope,pair in [('INTERNAL',('B','A')),('EXTERNAL',('D','C'))]:
        for kind,text in [('main',f'합성 규정. {scope}. 국내 법인은 {pair[0]} 절차, 해외 법인은 {pair[1]} 절차를 따른다.'),('exception','합성 규정 단서. 긴급 사건이면 별도의 예외 확인이 필요하며, 긴급 여부가 확인되지 않았으면 미확인으로 남긴다.'),('documents',f'합성 규정 서류. {pair[0]} 절차는 신청서와 국내 확인서, {pair[1]} 절차는 신청서와 해외 확인서를 사용한다.')]:
            docs.append({'doc_id':'MOCK-'+scope,'node':kind,'scope':scope,'version':'synthetic-v2','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'kind':'SYNTHETIC'})
    products=[];gold={}
    def case(cid,turns,expected):
        products.append({'case_id':cid,'data_kind':'SYNTHETIC','turns':turns})
        gold[cid]=expected
    def t(text,goal='G1',**extra):return {'utterance':text,'goal':goal,**extra}
    filler=[t('현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘.') for _ in range(12)]
    case('SEQ01',[t('내규에서 국내 법인의 긴급 예외 적용 조건을 확인해줘.'),t('아니 외규에서 해외 법인의 필요 서류를 확인하는 것으로 바꿔줘.'),*filler,t('앞의 전환은 잘못됐어. 첫 질문의 목적과 규정 범위와 당사자 조건 전부 원래대로 다시 봐줘. 그 최초 질문까지 거슬러 확인해.'),t('그러면 지금 조건에서 결론과 근거를 다시 알려줘.'),t('같은 조건으로 새 대화에서 물으면 이 최종 경로를 써줘.',action='reuse')],{'checkpoints':{'1':{'scope':'INTERNAL','party':'DOMESTIC','task':'EXCEPTION','procedure':'B'},'2':{'scope':'EXTERNAL','party':'FOREIGN','task':'DOCUMENTS','procedure':'C'},'15':{'scope':'INTERNAL','party':'DOMESTIC','task':'EXCEPTION','procedure':'B'},'16':{'procedure':'B'},'17':{'procedure':'B'}},'must_backtrack_turn':15,'gold_sources':['MOCK-INTERNAL/main','MOCK-INTERNAL/exception'],'reuse_required':True})
    case('SEQ02',[t('내규의 국내 법인 절차를 확인해줘.','G1'),t('두 번째 질문은 내규의 해외 법인 절차야.','G2'),t('두 번째 질문만 외규로 고쳐줘.','G2'),t('두 번째 질문은 긴급 사건이라는 조건도 고려해줘.','G2'),t('방금 긴급이라고 고친 건 잘못이야. 두 번째 질문은 긴급하지 않아.','G2'),t('첫 번째 질문의 현재 결론은 뭐야?','G1')],{'checkpoints':{'1':{'procedure':'B'},'2':{'procedure':'A'},'3':{'scope':'EXTERNAL','procedure':'C'},'4':{'urgent':True,'needs_check':True},'5':{'urgent':False,'needs_check':False},'6':{'scope':'INTERNAL','procedure':'B'}},'preserve_goal':'G1','preserve_between':[2,5],'gold_sources':['MOCK-INTERNAL/main']})
    case('SEQ03',[t('내규의 본문만 검색해서 국내 법인 절차를 확인해줘.'),t('본문만 읽은 게 문제야. 단서와 서류도 포함하도록 검색 계획과 원문 읽기부터 고쳐줘.'),t('이제 근거 선별 단계부터 다시 검토해서 단서도 근거로 유지해줘.'),t('판단에서 긴급 여부가 빠졌어. 이 사건은 긴급이야. 다시 판단해줘.'),t('지금 최종 답변만 표로 보여줘.'),t('같은 내용으로 표 대신 문장으로 자세하게 써줘.'),t('그럼 현재 적용 절차와 긴급 조건은 어떻게 돼?')],{'checkpoints':{'1':{'procedure':'B','query_mode':'MAIN_ONLY'},'2':{'query_mode':'ALL','procedure':'B'},'4':{'urgent':True,'needs_check':True},'5':{'procedure':'B','table':True},'7':{'procedure':'B','urgent':True,'needs_check':True}},'presentation_turns':[5,6],'gold_sources':['MOCK-INTERNAL/main','MOCK-INTERNAL/exception']})
    case('SEQ04',[t('첫 번째 경험은 내규 국내 법인의 절차 확인이야.','G1'),t('두 번째 경험은 외규 해외 법인의 절차 확인이야.','G2'),t('첫 번째 질문에 두 번째 경험을 잘못 연결했다고 가정하자.','G1',action='wrong_link'),t('가져온 경험이 잘못됐어. 첫 번째 질문은 첫 번째 경험으로 연결해. 두 번째 경험 자체는 유지해줘.','G1'),t('첫 번째 질문에 해당하는 현재 경로로 다시 알려줘.','G1',action='reuse')],{'checkpoints':{'1':{'procedure':'B'},'2':{'procedure':'C'},'5':{'procedure':'B'}},'wiki_target':'G1','preserve_bundle':'G2','gold_sources':['MOCK-INTERNAL/main'],'reuse_required':True})
    case('SEQ05',[t('내규에서 국내 법인 절차를 알려줘.'),t('외규로 고쳐줘.'),t('그 정정은 잘못됐어. 다시 내규로 봐줘.'),t('국내가 아니라 해외 법인이야.'),t('두 번째 정정에서 내규로 돌린 게 잘못됐어. 외규 기준을 유지해줘.',fault='ASSESS'),t('중단된 정정을 이어서 처리해줘.'),t('지금 최종 경로로 다시 답해줘.'),t('옛 실행을 다시 수집해도 최종 경로를 사용해줘.',action='reingest')],{'checkpoints':{'1':{'procedure':'B'},'2':{'procedure':'D'},'3':{'procedure':'B'},'4':{'procedure':'A'},'6':{'scope':'EXTERNAL','party':'FOREIGN','procedure':'C'},'7':{'procedure':'C'},'8':{'procedure':'C'}},'fault_turn':5,'gold_sources':['MOCK-EXTERNAL/main'],'reingest_required':True})
    write(DESIGN/'RAW/documents.json',docs)
    write(DESIGN/'RAW/manifest.json',{'data_kind':'SYNTHETIC','not_actual_law':True,'documents_sha256':sha(DESIGN/'RAW/documents.json'),'documents':6,'parent_fixture':'ADR-0591 synthetic concepts; newly authored units, not real source ingestion'})
    write(DESIGN/'inputs.json',products);write(DESIGN/'gold.json',gold)
    plan=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'scope','kind':'filter','parent_stage_ids':['source']},{'stage_id':'query','kind':'retrieve','parent_stage_ids':['scope']},{'stage_id':'selected','kind':'select','parent_stage_ids':['query']},{'stage_id':'present','kind':'present','parent_stage_ids':['selected']}]
    m=json.loads((ADR/'실험/manifest.json').read_text())
    m['lineage']['hypothesis_delta']='r3 prototype adds stage graph, cross-turn original lookup, bundle route and next-request consumption; baseline is current-only ablation of same new executor, not replay of ADR0591 or active MAIN.'
    m['design'].update(hypothesis='An explicit provenance/dependency graph permits repeated corrections back to initial premises and consistent final-route consumption.',primary_metric='Passed predeclared checkpoints per sequential case, full-case pass and stage-consumption invariants',success_criteria='All CHAIN checkpoints, no wrong-goal overwrite, route closure, no retired route consumption, presentation-only upstream preservation, recover pending correction; exploratory in-sample only',failure_criteria='Any checkpoint mismatch, missing required original lookup, stale route reuse, wrong goal mutation, or incomplete resume',criteria_frozen_before_run=True)
    m['design']['arms'][0].update(changes='Completed ADR0591/GUARDED inherited as implementation/design ancestor only; not rerun on incompatible sequential dataset',controls='Historical evidence preserved; no cross-dataset accuracy comparison')
    m['design']['arms'][1].update(changes='Full linked provenance including superseded steps and original turns; exact ancestors retrieved for interpretation and corrections',controls='Same executor, sources, utterances, model, command/output schemas and guards')
    m['design']['arms'].append({'id':'CURRENT_ONLY','role':'candidate','derived_from':['baseline'],'changes':'Ablation of the new executor: original graph lookup disabled, only two recent turns/current results reach resolver','controls':'Same code, corpus, schemas, stage execution and guards as CHAIN; not active MAIN'})
    m['design']['retrieval_stage_plan']['stages_by_arm']={a:plan for a in ['baseline','CHAIN','CURRENT_ONLY']}
    m['runs'][0]['arm_ids']=['CURRENT_ONLY','CHAIN']
    m['design']['planned_faults']={'SEQ05':'At turn 5 before ASSESS; next explicit turn resumes pending route'}
    m['design']['limits']=['Synthetic stage executor, not production API/Coordinator integration','Gold loaded only after all product calls','Baseline is current-only ablation, not old MAIN','No real law, PDF ingestion, DB admin or approval implementation','One sequential family per case; exploratory in-sample']
    m['runs'][0]['selection_rule']='All five frozen sequences, all turns in one persistent DB per case/arm; alternate whole-arm order by case; one repetition; predeclared injected fault'
    m['dataset'].update(name='synthetic-rag-chain-sequences',version='r3-mock-v1',frozen_source=str((DESIGN/'inputs.json').relative_to(ROOT)),sha256=sha(DESIGN/'inputs.json'),legal_version_checked=True,reference_version_checked=True)
    m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
    m['retrieval_accounting'].update(changed=True,corpus_total=6,not_applicable_reason=None)
    m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',not_applicable_reason=None)
    write(ADR/'실험/manifest.json',m)
    protected=['01_DATA/ACTIVE/local/ACTIVE_RELEASE.json','00_SYSTEM/PIPELINE.json','00_SYSTEM/SCHEMAS/legal-agent-case-memory-v1.draft.sql','00_SYSTEM/SCHEMAS/shortcut-experience-v1.draft.sql','04_EXPERIMENTS/ADR/ADR-0591-case-memory-functional-mock-probe/실험/manifest.json']
    write(DESIGN/'baseline-binding.json',{p:sha(ROOT/p) for p in protected})
    print(json.dumps({'sequences':len(products),'turns':sum(len(p['turns']) for p in products),'design_sha256':sha(DESIGN/'inputs.json')},ensure_ascii=False))

if __name__=='__main__':main()
