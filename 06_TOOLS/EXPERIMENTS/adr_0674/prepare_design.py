"""Select distinct source groups and freeze questions/gold before product calls."""
from pathlib import Path
import sqlite3,json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0674-investigation-control-integration';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0674/integrated';S=C/'snapshot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
g=R/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation'
c=sqlite3.connect('file:'+str(g/'store.sqlite')+'?mode=ro',uri=True);n=sqlite3.connect('file:'+str(g/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
entries=[
('ACTOR','상법','1374','주식회사의 주주총회 소집은 누가 결정하나요?'),
('ACTOR','상법','1464','주식회사의 이사는 누가 선임하고 회사와는 어떤 법률관계를 맺나요?'),
('ACTOR','주식회사 등의 외부감사에 관한 법률','41','외부감사 대상 회사의 재무제표 작성 책임은 누구에게 있고 제출은 어떻게 하나요?'),
('ACTOR','개인정보 보호법','433','개인정보 보호책임자는 누가 지정하고 어떤 업무를 맡기나요?'),
('TIMING','상법','1375','상법상 주주총회 소집 통지는 언제 어떤 방식으로 해야 하고 작은 회사의 예외는 무엇인가요?'),
('TIMING','상법','1897','상법상 이익배당은 언제까지 지급하며 달리 정할 수 있나요?'),
('TIMING','자본시장과 금융투자업에 관한 법률','1472','자본시장법상 반기보고서와 분기보고서는 언제까지 제출해야 하나요?'),
('TIMING','개인정보 보호법','708','개인정보 분쟁조정 사건은 언제까지 처리하고 기간을 연장할 수 있나요?'),
('CLASSIFICATION','상법','1014','주식회사 주주는 회사에 대해 어느 범위까지 책임을 지나요?'),
('CLASSIFICATION','자본시장과 금융투자업에 관한 법률','1320','자본시장법의 공개매수 규정은 어떤 증권 취득에 적용되나요?'),
('CLASSIFICATION','개인정보 보호법','374','가명정보 처리에서는 어떤 행위가 금지되나요?'),
('CLASSIFICATION','벤처기업육성에 관한 특별법','333','벤처기업 복수의결권주식은 어떤 결의에서 의결권이 제한되나요?'),
('STRUCTURE','상법','1512','상법상 이사회 결의의 정족수와 특별이해관계 이사의 처리는 어떻게 구성되나요?'),
('STRUCTURE','상법','1677','상법상 감사위원회의 구성과 사외이사 요건을 설명해 주세요.'),
('STRUCTURE','상법','1185','상법상 주주명부에는 무엇을 기재해야 하나요?'),
('STRUCTURE','개인정보 보호법','27','개인정보 보호법에서 정보주체에게 부여하는 권리들을 정리해 주세요.'),
('FORMULA','상법','1403','상법상 주주총회 보통결의 정족수와 대리인 의결권 행사는 어떻게 정하나요?'),
('FORMULA','상법','1772','상법상 정관변경 특별결의 정족수의 두 기준을 설명해 주세요.'),
('FORMULA','상법','1863','상법상 이익배당 가능액은 대차대조표 순자산액에서 무엇을 공제해 계산하나요?'),
('FORMULA','상법','1879','상법상 중간배당을 할 수 있는 요건과 배당 한도 계산을 설명해 주세요.'),
('AUTHORITY','개인정보 보호법','92','개인정보 보호위원회의 소관 사무는 무엇인가요?'),
('AUTHORITY','상법','1653','상법상 감사가 회사의 업무와 재산을 조사하고 보고를 요구할 수 있는 범위는?'),
('AUTHORITY','주식회사 등의 외부감사에 관한 법률','31','외부감사법상 회계처리기준은 누가 정하고 어떤 회사에 적용하나요?'),
('AUTHORITY','개인정보 보호법','166','개인정보 보호법상 자료제출 요구는 누가 누구에게 할 수 있나요?'),
('DEFINITION','벤처기업육성에 관한 특별법','2','벤처기업육성에 관한 특별법에서 벤처기업을 어떻게 정의하나요?'),
('DEFINITION','주식회사 등의 외부감사에 관한 법률','2','외부감사법에서 재무제표와 연결재무제표는 각각 무엇을 뜻하나요?'),
('DEFINITION','개인정보 보호법','2','개인정보 보호법상 개인정보와 가명처리의 정의를 구분해 주세요.'),
('DEFINITION','자본시장과 금융투자업에 관한 법률','136','자본시장법에서 전문투자자와 일반투자자는 어떻게 구분하나요?'),
('SCOPE','상법','1199','상법 제354조 주주명부 폐쇄와 기준일의 각 항 요건을 나누어 설명해 주세요.'),
('SCOPE','상법','1045','상법 제336조 주식의 양도방법의 각 항 내용을 나누어 설명해 주세요.'),
('SCOPE','개인정보 보호법','264','개인정보 보호법 제21조의 개인정보 파기 원칙과 보존 예외, 분리 보관을 나누어 설명해 주세요.'),
('SCOPE','주식회사 등의 외부감사에 관한 법률','134','외부감사법 제12조 감사인 선임 등의 보고 대상과 예외를 나누어 설명해 주세요.')]
cases=[];gold=[];grant=read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
for i,(kind,law,uid,q) in enumerate(entries,1):
 d=c.execute('SELECT document_id FROM document WHERE name=?',(law,)).fetchone()[0];assert d in grant['public_document_ids']
 nodes={str(u):json.loads(j) for u,j in c.execute('SELECT unit_id,json FROM source_unit WHERE document_id=?',(d,))};unit=nodes[uid];assert unit['family']=='kr_article' and unit.get('coordinate_scope')=='body'
 sid,payload=n.execute('SELECT id,json FROM source WHERE document_id=? AND json_extract(json,\'$.unit_id\')=?',(d,uid)).fetchone();src=json.loads(payload)
 text='\n'.join(c.execute('SELECT text FROM block_payload WHERE document_id=? AND block_id=?',(d,str(b['block_id']))).fetchone()[0] for b in src['blocks'])
 cases.append({'case_id':f'IC{i:02}','question':q,'kind':kind})
 gold.append({'case_id':f'IC{i:02}','kind':kind,'document_id':d,'document_name':law,'unit_id':uid,'source_id':sid,'canonical_coordinate':unit['coordinate_key'],
    'source_text':text,'source_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_artifact_sha256':c.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(d,)).fetchone()[0],
    'rubric':'Answer must fulfil every explicit part of the question with the correct subject and rules, keep numerical thresholds/conditions/exceptions faithful to supplied source. Partial/limited status does not compensate for a missing requested rule. Do not infer compliance from one prerequisite. Additional consistent sources are permitted.'})
assert len({r['source_id'] for r in gold})==32
put(D/'dataset.json',{'cases':cases,'selection':'32 independently chosen distinct canonical article groups, 8 requirement types, four each; no prior CM or observed question paraphrases; current selected source version only','source_generation':str(g.relative_to(R)),'product_gold':None,'max_calls_per_case':40,'max_output_tokens':6400})
put(D/'gold.json',{'cases':gold,'visibility':'Offline evaluator only, after immutable product output','version_scope':'Pinned repository source snapshots; no claim that these are latest law in force today'})
put(D/'rubric.json',{'semantic_correctness':'Every requested requirement, subject, scope, thresholds, exceptions and limitations grounded in exact original. Binary per case; no averaged hiding of a baseline-only correct case.','promotion':'All contracts, serving closure, hashes and quotations pass; 0 baseline-only correct cases; all candidate cases execute without new integrity/ACL/scope failures. Costs/latency reported; no improvement assertion required.','evaluator':'qwen/qwen3.8-27b; Parasail FP8; reasoning none; no fallback; one grade per answer; same frozen gold; may not alter product contexts or outputs.'})
config=read(S/'00_SYSTEM/PIPELINE.json')
for e in config['engines'].values():
 p=S/e['manifest'];m=read(p)
 if '/legal_agent/' in m['entrypoint']['path']:
  for module in ['investigation_chain.py','evidence_inventory.py','investigation_contracts.py']:
   m['files']['02_BACKEND/semantic_runtime/legal_agent/'+module]=sha(S/'02_BACKEND/semantic_runtime/legal_agent'/module)
 for f in m['files']:m['files'][f]=sha(S/f)
 put(p,m);e['sha256']=sha(p)
for e in config['contracts'].values():e['schema_sha256']=sha(S/e['schema_path'])
put(S/'00_SYSTEM/PIPELINE.json',config)
print(json.dumps({'questions':32,'distinct_source_groups':32,'gold_chars':sum(len(r['source_text']) for r in gold)},ensure_ascii=False))
