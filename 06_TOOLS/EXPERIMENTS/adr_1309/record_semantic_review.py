"""Record Codex's post-run, claim-by-claim original comparison; no model calls."""
from common import *
rows=[]
for cell in read(DES/'criteria.json')['order']:
 case,arm=cell.split('/');p=ART/'live'/(case+'-'+arm);r=read(p/'result.json');d=read(p/'response.json.gz')['body'];term=d.get('assembly',{}).get('term_agent',{});answer=d.get('answer') or {};outcome=term.get('accepted_outcome') or {}
 row={'case_id':case,'arm':arm,'cell':p.name,'response_path':str((p/'response.json.gz').relative_to(ROOT)),'response_sha256':sha(p/'response.json.gz'),'answer_text_sha256':sha(p/'answer.txt'),'final_claim_count':r['claims'],'product_answer_coverage':outcome.get('answer_coverage'),'product_disposition':outcome.get('disposition'),'product_stop_reason':outcome.get('stop_reason'),'product_gaps':term.get('gaps'),'product_unresolved':answer.get('unresolved') if isinstance(answer,dict) else None,'manual_judge':'Codex: final claim text and actual cited source spans inspected after the run; external judge calls0','final_core_rules_total':3}
 if r['http_status']!=200:
  assert arm=='after' and case=='ontology-365' and r['http_status']==503
  assert read(p/'calls.json')[-1]['http_status']==429
  row.update(verdict='ERROR',error_taxonomy='provider_rate_limit',basis='Near AI shared-pool HTTP429 on physical call2 before final answer; API503, final claims0. This is not a wrong legal answer or successful fast response; no complete-answer latency ratio.',final_core_rules_matched=0,checks=[],unsupported_added_rules_found=None)
 else:
  assert r['claims']==3
  if case=='ontology-365':
   blocks=['1389','1390','1391'];rules=['정기총회 매년1회 일정한 시기','연2회 이상 결산기 회사는 매 결산기마다 총회','임시총회 필요한 경우 수시']
  else:
   blocks=['1421','1422','1423'];rules=['1주마다 의결권1개','회사가 가진 자기주식의 의결권 없음','회사/모회사및자회사/자회사의 타회사 발행주식총수10분의1 초과 보유; 그 다른 회사가 가진 회사 또는 모회사 주식의 의결권 없음']
  checks=[{'claim':'claim:'+str(i+1),'source_block':b,'rule':text,'matched':True} for i,(b,text) in enumerate(zip(blocks,rules))]
  if case=='ontology-369':checks[-1].update(threshold_strictness_preserved=True,holder_subjects_preserved=True,restricted_share_direction_preserved=True)
  additional=[]
  if arm=='after' and case=='ontology-369':additional=[{'claims':['claim:2','claim:3'],'source_block':'1426','rule':'제371조제1항: 제369조제2항/제3항 의결권 없는 주식을 발행주식총수에 산입하지 않음','matched':True,'source':'actually acquired and sent same-artifact original'}]
  row.update(verdict='PASS',basis='최종 주장3개에서 질문 핵심3규칙과 조건·수치·주체·대상 방향을 인용 원문에 대조해 일치 확인. '+('제371조제1항 추가설명2곳도 실제 확보·전달 원문1426과 일치. ' if additional else '')+'제품 내부PARTIAL과 내용 전달 성공은 구분한다.',final_core_rules_matched=3,checks=checks,additional_claim_checks=additional,unsupported_added_rules_found=False)
 rows.append(row)
put(ART/'semantic-review.json',{'rows':rows,'core_rules_matched':sum(r['final_core_rules_matched'] for r in rows),'core_rules_total':12,'source_scored_correct':sum(r['verdict']=='PASS' for r in rows),'provider_error':sum(r['verdict']=='ERROR' for r in rows),'frozen_reference_sha256':sha(DES/'scoring-only-originals.json'),'new_model_calls':0,'scope':'Two known questions, each version once; stored source only. Core content completion is distinct from internal coverage status.'})
print('Manual source review recorded: 3 complete-content answers, 1 provider429 failure, 0 model calls')
