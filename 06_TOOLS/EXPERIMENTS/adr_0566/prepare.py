"""Prospective input preparation; no retrieval, models or outcome access."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0566-investigation-ontology-value'
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0566/graph'
D = ADR/'artifacts/design'
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    D.mkdir(exist_ok=False)
    regulations = [
      ('외국인 인수의 정의','외국인은 국적이 대한민국이 아닌 자다. 거주지는 국적 판단을 대신하지 않는다. 인수는 의결권 있는 주식 취득을 말한다.'),
      ('외국인 인수 적용대상','외국인이 의결권 있는 주식을 인수하면 이 모의규정이 적용된다. 적용 여부는 제1조의 정의와 제3조의 예외를 함께 확인한다. 적용되는 인수는 제4조의 보고 절차를 따른다.'),
      ('외국인 인수 적용 제외 예외','의결권 없는 주식의 취득은 이 규정의 적용대상에서 제외한다. 제외되면 제5조의 후속 확인을 한다.'),
      ('외국인 인수 보고 절차','적용대상인 외국인 인수는 취득 후 7영업일 이내에 보고한다. 제출자료는 국적 확인서와 의결권 확인서다. 업무 실적 통계는 보고 의무의 적용 근거가 아니다.'),
      ('외국인 인수 비의결권 후속 확인','적용대상에서 제외된 비의결권 취득은 이 규정의 보고 의무가 없다. 다만 별도의 모의 비의결권 규정 존재 여부를 확인한다.'),
      ('외국인 인수와 국내국적 적용 구분','국적이 대한민국인 자는 해외에 거주해도 이 규정의 외국인에 해당하지 않는다. 거주지만으로 외국인 인수 적용을 결정하지 않는다.')]
    norm = {'id':'mock-regulation:v1','name':'모의외국인인수규정','version':'v1','role':'normative',
            'articles':[{'title':title,'text':f'제{i+1}조({title}) {text}'} for i,(title,text) in enumerate(regulations)]}
    reports = []
    for i in range(48):
        title = '외국인 인수 업무 실적 총괄표' if i==0 else f'외국인 인수 업무 실적 지점{i:02d}표'
        text = (f'제{i+1}조({title}) 이 자료는 외국인 인수 업무 실적 통계다. '
                '총괄 외국인 인수 처리수는 120건이며 실적 집계율은 17퍼센트다. '
                '의결권 인수 80건, 비의결권 인수 40건으로 집계했다. '
                '국적별 외국인 인수와 거주지별 처리 목록을 집계한다. '
                '인수 보고 처리 실적과 적용규정 확인 업무의 처리량을 나열한다. '
                '이는 과거 처리수의 관측이며 외국인 인수 적용 의무·기한·법적 예외를 정하는 규범이 아니다. '
                + '외국인 인수 업무 실적 통계의 지점별 집계와 목록 조회 기록을 보관한다. '*8)
        reports.append({'title':title,'text':text})
    perf = {'id':'mock-performance:v1','name':'모의외국인인수실적집','version':'v1','role':'descriptive','articles':reports}
    drift = {'id':'mock-drift:v2','name':'모의신규사업지침','version':'v2','role':'normative',
             'articles':[{'title':'외국인 인수 신규사업 특례 적용',
                 'text':'제1조(외국인 인수 신규사업 특례 적용) 이 문서는 구판 실적 보고서에서 개정된 신판 사업지침이다. 외국인의 신규사업 비의결권 인수도 이 특례의 적용대상이다. 신규사업 인수는 3영업일 이내에 등록한다. 일반 비의결권 제외 규정보다 이 신규사업 특례를 우선 적용한다.'}]}
    write(D/'corpus.json',{'classification':'SYNTHETIC','documents':[norm,perf,drift]})
    base = [norm['id'],perf['id']]
    definitions = [
      ('APP-01','미국 국적자가 의결권 주식을 인수한다. 적용규정과 보고 기한, 제출자료를 확인해줘.',base,['외국인 인수 적용대상','외국인 인수 정의 보고 절차']),
      ('APP-02','대한민국 국적자가 해외에 거주하며 주식을 인수한다. 외국인 인수규정이 적용되나?',base,['외국인 인수 국적 거주지 적용']),
      ('APP-03','외국 국적자가 의결권 없는 주식만 취득한다. 외국인 인수규정의 적용과 후속 확인은?',base,['외국인 인수 비의결권 적용 제외 예외 후속']),
      ('INV-01','외국인 인수 관련 자료의 종류를 전체 조회해줘. 규정 자료와 업무 실적 자료가 각각 있는지 원문으로 보여줘.',base,['외국인 인수 규정 업무 실적 총괄표 목록']),
      ('PERF-01','외국인 인수 업무 실적 총괄표에서 전체 처리 건수와 실적 집계율을 알려줘.',base,['외국인 인수 업무 실적 총괄표']),
      ('MIX-01','외국인 의결권 주식 인수의 적용규정과 보고 기한을 확인하고, 업무 실적 총괄표의 처리 건수와 집계율도 알려줘.',base,['외국인 인수 적용대상 보고 절차','외국인 인수 업무 실적 총괄표']),
      ('DRIFT-01','신규사업에서 외국인이 비의결권 주식을 인수한다. 신판 사업지침까지 확인해서 적용규정과 등록 기한을 알려줘.',base+[drift['id']],['외국인 인수 신규사업 특례 적용','외국인 인수 비의결권 제외'])]
    write(D/'cases.json',{'classification':'SYNTHETIC','cases':[
      {'id':cid,'question':q,'documents':docs,'query_plan':{'queries':queries,'law_names':[]}} for cid,q,docs,queries in definitions]})
    key = lambda did,u: {'doc_id':did,'node':u-1}
    n = lambda *us: [key(norm['id'],u) for u in us]
    c = [key(perf['id'],1)]
    write(D/'expected-offline.json',{'product_access_forbidden':True,
        'required':{'APP-01':n(1,2,3,4),'APP-02':n(1,6),'APP-03':n(1,2,3,5),
                    'INV-01':n(2)+c,'PERF-01':c,'MIX-01':n(2,4)+c,'DRIFT-01':[key(drift['id'],1)]+n(3)},
        'required_answer_terms':{'APP-01':['7','국적','의결권'],'APP-02':['대한민국','국적'],
                                'APP-03':['의결권','제외'],'INV-01':['규정','실적'],
                                'PERF-01':['120','17'],'MIX-01':['7','120','17'],'DRIFT-01':['3','신규사업']},
        'expected_purpose':{'APP-01':'APPLICABILITY','APP-02':'APPLICABILITY','APP-03':'APPLICABILITY',
                            'INV-01':'INVENTORY','PERF-01':'PERFORMANCE','MIX-01':'MIXED','DRIFT-01':'APPLICABILITY'}})
    write(D/'ontology.json',{'learned_from_real_logs':False,'source':'manually curated synthetic policy and classifications',
         'relation':['purpose:applicable','EXCLUDES','class:performance'],
         'purposes':{'APPLICABILITY':'선택된 규정의 적용 여부·정의·예외·절차를 조사',
                     'INVENTORY':'모든 자료의 목록·종류를 조사',
                     'PERFORMANCE':'업무 실적 통계 수치·관측을 조사',
                     'MIXED':'적용규정과 실적 등 서로 다른 목적을 함께 조사',
                     'UNKNOWN':'단일 조사 목적을 확정하지 못함'}})
    write(D/'prompts.json',{
      'classifier':'질문의 조사 목적만 분류한다. 적용규정(APPLICABILITY), 전체목록(INVENTORY), 업무실적(PERFORMANCE), 복합목적(MIXED), 미확정(UNKNOWN) 중 고른다. 업무실적이나 목록도 요청하면 적용규정만의 목적을 고르지 마라. 질문 원문 외 사실을 가정하지 마라. 명확한 단일 목적은 HIGH, 불명확하면 LOW다. purpose, confidence, reason 세 키의 JSON만 출력한다. reason은 40자 이내다.',
      'answer':'합성 문서에만 근거해 사용자의 질문에 간결하게 답한다. 실제 법률 판단이 아니다. 제공된 원문에 없는 사실·법령은 추가하지 마라. 관련 정의·적용·예외·절차를 함께 확인한다. 각 판단을 claims 배열로 구분하고 실제로 그 판단을 뒷받침하는 원문 source_ids를 인용한다. 필요한 원문이 없으면 부족함을 밝힌다. 출력은 claims와 answer 두 키의 JSON이다. claims의 text는 100자 이내, 전체 answer는 500자 이내다.'})
    write(D/'schemas.json',{'classifier':{'type':'object','additionalProperties':False,
        'properties':{'purpose':{'type':'string','enum':['APPLICABILITY','INVENTORY','PERFORMANCE','MIXED','UNKNOWN']},
            'confidence':{'type':'string','enum':['HIGH','LOW']},'reason':{'type':'string'}},
        'required':['purpose','confidence','reason']},
        'answer':{'type':'object','additionalProperties':False,'properties':{
            'claims':{'type':'array','maxItems':6,'items':{'type':'object','additionalProperties':False,
                'properties':{'text':{'type':'string'},'source_ids':{'type':'array','items':{'type':'string'},'minItems':1}},
                'required':['text','source_ids']}},'answer':{'type':'string'}},'required':['claims','answer']}})
    write(D/'criteria.json',{'functional':'7/7 required original/citation/answer-term checks; no candidate-only losses; no false exclusion on inventory/performance/mixed/drift',
        'read_value':'at least 30% fewer original article roots summed over APP-01..03',
        'end_to_end_value':'at least 10% lower total paired wall time, or 10% lower provider-reported product cost, including purpose recognition; all functional checks must pass',
        'speed_claim_boundary':'local synthetic corpus; a single alternating paired run, no GENOS/NFS performance certification',
        'negative_controls':'C retained for other purposes; stale version fallback; explicit ancestor/direct READ denied for excluded sources',
        'sample':'preauthored synthetic favorable high-noise conditions plus four negative controls; in-sample probe',
        'call_policy':'Gemma Parasail FP8 thinking off; max 1536 output; schema-in-prompt true; max repairs0; no retries/fallback; all failures retained',
        'not_executed':'automatic log extraction/group learning, native full BoundedSourceSession/Compose request, request planner, actual internal data'})
    # Isolated source-discovery adapters consume the semantic allow-list, not a prompt.
    for name in ('source_recall.py','source_recall_global.py'):
        p = CANDIDATE/'snapshot/02_BACKEND/semantic_runtime/legal_agent'/name
        text = p.read_text()
        needle = '        self.scores = defaultdict(float)'
        assert text.count(needle)==1
        text = text.replace(needle, '        policy_scope = getattr(sources, "investigation_allowed_source_ids", None)\n'
              '        if policy_scope is not None:\n            self.allowed &= set(policy_scope)\n'+needle)
        p.write_text(text)
    parent = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0565/graph/revisions/rev-001/snapshot/02_BACKEND/lawrag/core/investigation_graph.py'
    target = CANDIDATE/'snapshot/02_BACKEND/lawrag/core/investigation_graph.py'
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(parent,target)
    stable = [ROOT/'02_BACKEND/semantic_runtime/fulltext.py',ROOT/'02_BACKEND/lawrag/research/experiment_client.py',
              ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'05_TESTS/conftest.py',
              ROOT/'05_TESTS/CONTRACTS/test_document_release.py']
    stable += list((ROOT/'02_BACKEND/semantic_runtime/legal_agent').glob('*.py'))
    write(D/'code-pins.json',{str(p.relative_to(ROOT)):sha(p) for p in stable})
    write(D/'lineage-input.json',{'parent_graph_path':str(parent.relative_to(ROOT)),'parent_graph_sha256':sha(parent),
        'current_main_path':'00_SYSTEM/ARCHITECTURE.md','current_main_sha256':sha(ROOT/'00_SYSTEM/ARCHITECTURE.md'),
        'baseline':'current selected release matching native SourceRecall/source-selection working modules; no ontology scope',
        'prospective_policy':'not a new log-learning accuracy experiment'})
    print('Prepared prospective 7 paired cases, 55 synthetic article roots, gold separate.')


if __name__=='__main__': main()
