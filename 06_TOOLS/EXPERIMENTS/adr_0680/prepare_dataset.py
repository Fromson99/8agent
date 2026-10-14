"""Prospective article-root holdout; no product run or gold leakage."""
from pathlib import Path
import hashlib,json,sqlite3,copy
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0680-investigation-main-consumer-integration';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not (D/'dataset.json').exists()
selection=[('ACTOR', 'article:022c1cb3940df1c21390193a', '금융소비자보호법상 금융교육협의회는 어디에 두며, 의장과 위원은 누구인가요? 위원 수와 자료 제출 요구 대상도 설명해 주세요.'), ('ACTOR', 'article:3dd7628df940398bd6f4afbd', '공공기관운영법상 공기업의 장과 감사는 각각 누구의 추천·심의·제청을 거쳐 누가 임명하나요? 소규모 공기업의 예외도 설명해 주세요.'), ('TIMING', 'article:ea5b69bc0021a8fae6f4df3f', '정보공개법상 비공개 또는 부분공개 결정이나 결정 지연에 대한 이의신청 기간과 기관의 결정 기간, 연장 및 통지 의무를 설명해 주세요.'), ('TIMING', 'article:20212aac0d2d447e31ea30cd', '국세기본법상 공시송달은 어떤 경우 가능하고 언제 송달된 것으로 보나요? 공고 방법과 국세정보통신망 사용 시 조건도 설명해 주세요.'), ('CLASSIFICATION', 'article:d04155a4b855256addb8d745', '금융소비자보호법 제25조의 금융상품판매대리·중개업자 금지행위를 구분하고, 법률에 명시된 예외와 추가 금품 수수 금지도 설명해 주세요.'), ('CLASSIFICATION', 'article:44b0def3b87f845b9f2a9ff3', '정보공개법상 심의위원의 제척·기피·회피를 구분하고, 기피 결정 참여 제한과 회피하지 않은 경우의 조치도 설명해 주세요.'), ('STRUCTURE', 'article:03ac47aa838e7b6ed074ba91', '정보공개법상 사전적으로 정기 공개해야 하는 정보의 유형과 미리 정할 사항, 공개 예외를 정리해 주세요.'), ('STRUCTURE', 'article:9e4f47ab1fbbf28cbdfdda2b', '공공기관운영법 제17조 제2항에 따라 기관장이 이사회에 보고해야 하는 사항을 모두 정리하고 단체협약 보고의 조건을 설명해 주세요.'), ('FORMULA', 'article:e4de710232e71d69a854715f', '국세기본법상 상속으로 인한 납세의무 승계에서 보험금을 상속재산으로 보는 두 경우와 각각의 금액 계산 방법을 설명해 주세요.'), ('FORMULA', 'article:44348ad402a447146bedfec0', '국세기본법상 법인의 제2차 납세의무 한도액은 어떻게 계산하나요? 계산식의 각 항목과 그 의무가 성립하는 경우를 설명해 주세요.'), ('AUTHORITY', 'article:5384e9ad4abb6705f9e74f1f', '금융소비자보호법상 금융상품판매업자등에 대한 검사 주체와 보고·자료·출석 요구 권한을 설명해 주세요. 외부감사인에게 자료를 요구할 때의 범위와 방식도 포함해 주세요.'), ('AUTHORITY', 'article:f3801a3fea0638038fc49c2e', '공공기관운영법상 통합공시 자료는 누가 누구에게 요구할 수 있나요? 공시 의무 불이행이나 허위 공시에 대한 시정 명령과 인사 조치 요청 권한도 설명해 주세요.'), ('DEFINITION', 'article:450aa3211f414ed898b9ea40', '국세기본법에서 납세의무자와 납세자는 어떻게 다른가요? 제2차 납세의무자와 보증인의 정의도 설명해 주세요.'), ('DEFINITION', 'article:1b1f294bf4a9d043c8207433', '공공기관운영법 제5조의 시장형·준시장형 공기업과 기금관리형·위탁집행형 준정부기관은 각각 무엇을 뜻하나요? 법률에 규정된 구분 기준을 설명해 주세요.'), ('SCOPE', 'article:7348749f83ecab4a24ae4f2d', '금융소비자보호법상 신의성실의무는 누구의 어떤 행위에 적용되나요? 업무 내용·절차의 공정성과 소비자 이익 침해 금지도 설명해 주세요.'), ('SCOPE', 'article:5098da13e7cba6cd40e56ed8', '국세기본법상 근거과세 원칙에서 장부와 다른 조사 결과로 결정할 수 있는 범위는 어디까지인가요? 결정서의 근거 기재와 납세자의 열람·복사 요구 절차도 설명해 주세요.')]
nav=R/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation/navigation/navigation.sqlite';db=sqlite3.connect(nav.resolve().as_uri()+'?mode=ro',uri=True)
sources={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,json FROM source')};excluded=set(read(D/'prior-excluded-source-ids.json'))
# Include every actually delivered source-bearing native input, even if not adopted.
from gzip import decompress
for n in range(674,680):
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
