"""Prospective article-root holdout; no product run or gold leakage."""
from pathlib import Path
import hashlib,json,sqlite3,copy
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not (D/'dataset.json').exists()
selection=[
('ACTOR','article:a914fdb78fcfba8889f5270f','정보공개법상 정보공개심의회의 설치 주체와 위원장 선임 주체는 누구이며, 외부 전문가 위촉 비율과 그 예외는 어떻게 정하나요?'),
('ACTOR','article:5df9f0d58128da9d0f01b1db','중소기업기본법상 중소기업 옴부즈만은 누구의 추천과 심의를 거쳐 누가 위촉하며, 활동 결과보고서는 누구에게 언제 보고하나요?'),
('TIMING','article:9e0d9248cff8de0662f64775','정보공개법상 공공기관은 공개 여부를 언제까지 결정해야 하고 기간을 연장할 수 있는 조건과 통지 의무는 무엇인가요?'),
('TIMING','article:10708f5990fa2c587103e6dc','국세기본법상 우편신고와 전자신고는 각각 언제 신고된 것으로 보나요? 전자신고 서류의 제출기한 연장도 설명해 주세요.'),
('CLASSIFICATION','article:0adc7da31c0aab258ee14c49','금융소비자보호법의 금융상품 유형을 구분하고 하나의 상품에 여러 유형의 속성이 있는 경우를 설명해 주세요.'),
('CLASSIFICATION','article:b0e45bddc7852ca5b252ed4e','정보공개법상 반복 청구 등을 종결 처리할 수 있는 경우를 구분하고 각각의 통지·안내 의무를 설명해 주세요.'),
('STRUCTURE','article:3726146e0c6be2dad264c729','금융소비자보호법에서 정한 금융소비자의 기본적 권리를 항목별로 정리해 주세요.'),
('STRUCTURE','article:2fd69a86391dd5a74a105fd7','정보공개법상 정보공개 청구서에 적어야 할 사항과 말로 청구할 때의 절차를 정리해 주세요.'),
('FORMULA','article:c91fbf357e27ac3dec328b7c','금융소비자보호법상 분쟁조정위원회 회의의 구성 인원과 개의 및 의결 정족수는 어떻게 정하나요?'),
('FORMULA','article:4461d3173e10ea02cec2a7e6','국세기본법상 출자자의 제2차 납세의무에서 과점주주와 과점조합원의 책임 한도 금액을 어떻게 계산하나요?'),
('AUTHORITY','article:70b6cb7e9ffb78947762e8d4','금융소비자보호법상 금융위원회는 금융상품판매업자에게 어떤 명령을 할 수 있고 계약 체결 권유 금지 명령은 어떤 경우 가능한가요?'),
('AUTHORITY','article:254a30d7e31243def6ed0777','중소기업기본법상 중소기업 확인자료는 누가 누구에게 요구하나요? 국세청장에게 과세정보를 요청할 때 명시할 사항과 요청받은 자의 의무도 설명해 주세요.'),
('DEFINITION','article:b97c7c81f5b5be2b13d2960b','정보공개법에서 정보와 공개는 각각 무엇을 뜻하나요?'),
('DEFINITION','article:b7beb95a1a6f8875cfd6fc79','금융소비자보호법상 금융상품직접판매업과 금융상품판매대리·중개업의 정의를 구분해 주세요.'),
('SCOPE','article:1f94b0329fb626bfb7c221b2','정보공개법 제6조가 정한 공공기관과 행정안전부장관의 의무를 각 항별로 구분해 주세요. 통합정보공개시스템을 통한 청구 처리의 예외 기관도 설명해 주세요.'),
('SCOPE','article:31acb4b1dd8adf892dce278b','국세기본법 제14조의 실질과세 원칙을 귀속, 과세표준 계산, 제3자를 통한 거래의 세 항목으로 나누어 설명해 주세요.'),
]
nav=R/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation/navigation/navigation.sqlite';db=sqlite3.connect(nav.resolve().as_uri()+'?mode=ro',uri=True)
sources={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,json FROM source')};excluded=set(read(D/'prior-excluded-source-ids.json'))
# Include every actually delivered source-bearing native input, even if not adopted.
from gzip import decompress
for n in range(674,679):
 for root in (R/'04_EXPERIMENTS/ADR').glob(f'ADR-{n:04d}-*'):
  for p in list(root.glob('artifacts/run-*/integrated/*/runtime/**/journal.sqlite'))+list(root.glob('artifacts/run-*/integrated/*/runtime/**/journal.sqlite.gz')):
   if p.suffix=='.gz':c=sqlite3.connect(':memory:');c.deserialize(decompress(p.read_bytes()))
   else:c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
   def visit(v):
    if isinstance(v,dict):
     if v.get('source_id') in sources and isinstance(v.get('text'),str) and v['text']:excluded.add(v['source_id'])
     for z in v.values():visit(z)
    elif isinstance(v,list):
     for z in v:visit(z)
   for row in c.execute("SELECT payload_json FROM event WHERE kind='MEMORY_MODEL_INPUT'"):visit(json.loads(row[0]))
   c.close()
put(D/'prior-excluded-source-ids.json',sorted(excluded))
allowed=set(read(R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
cases=[];gold=[]
for i,(kind,sid,q) in enumerate(selection,1):
 assert sid not in excluded,(sid,q)
 s=sources[sid];assert s['document_id'] in allowed
 cid=f'H{i:02d}';cases.append({'case_id':cid,'question':q,'kind':kind})
 gold.append({'case_id':cid,'kind':kind,'document_id':s['document_id'],'document_name':s['document_name'],'unit_id':s['unit_id'],'source_id':sid,'canonical_coordinate':'body:'+s['heading'].split()[0],'source_text':s['text'],'source_text_sha256':s['text_sha256'],'source_artifact_sha256':s['source_artifact_sha256'],'rubric':'Judge only requested rules and exceptions against this pinned article. All explicitly requested subparts matter; unrelated application facts are not required for rule explanations. Preserve uncertainty, distinguish substantive errors from harmless style. Do not invent requirements beyond question/source; semantic score is diagnostic, not an absolute promotion gate.'})
old=read(P/'artifacts/design/dataset.json');ids=['NG01','NG02','NG05','NG11','NG13','IC16','IC22','IC23','IC24','IC25','IC28','REG-cm-039'];by={c['case_id']:c for c in old['cases']+old['regression_cases']}
reg=[{**by[c],'case_id':c if c.startswith('REG-') else 'REG-'+c,'parent_case_id':c,'decision_eligible':False} for c in ids]
put(D/'dataset.json',{'cases':cases,'regression_cases':reg,'source_generation':old['source_generation'],'selection':read(D/'design.json')['evaluation_selection'],'product_gold':None,'max_calls_per_case':40,'max_output_tokens':6400})
put(D/'gold.json',{'cases':gold,'product_visible':False,'source_generation':old['source_generation'],'frozen_before_run':True})
put(D/'selection-audit.json',{'primary_count':16,'regression_count':12,'primary_article_roots': [s for _,s,_ in selection],'prior_excluded_count':len(excluded),'no_primary_overlap':True,'domain_limit':'Public legal rule questions across four laws, same source generation; not proof of internal GENOS or case-specific decision quality.','no_product_outputs_observed':True})
m=read(A/'실험/manifest.json');m['dataset']['sha256']=sha(D/'dataset.json');m['dataset']['legal_version_checked']=True;m['dataset']['reference_version_checked']=True;put(A/'실험/manifest.json',m)
print('Frozen 16 new roots and 12 observed regressions. Gold stays evaluator-only.')
print('\n\n'.join(f"{c['case_id']} {c['document_name']}\n{c['source_text']}" for c in gold))
