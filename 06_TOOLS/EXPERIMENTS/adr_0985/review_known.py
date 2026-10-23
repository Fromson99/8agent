"""Audit the known diagnostic separately from fresh-model accuracy."""
from common import *
q=read(ART/'known-query/response.json');r=read(ART/'known-query/result.json')
b=q.get('body',{});assembly=b.get('assembly',{});agent=assembly.get('term_agent',{})
answer=b.get('answer',{});source_id='article:816aee85d53f84a3b2f322dd'
source=next((x for x in assembly.get('context',[]) if x['id']==source_id),None)
text=answer.get('text','').replace(' ','')
ratios=(('3분의2' in text or '2/3' in text) and ('3분의1' in text or '1/3' in text))
outcome=agent.get('accepted_outcome',{})
checks={'service_200':q['status']==200,'434_source_acquired':source is not None,
 'both_ratios_in_delivered_answer':ratios,'supported_claims_delivered':bool(answer.get('claims')),
 'explanatory_coverage':outcome.get('answer_coverage') in ('COVERED','PARTIAL'),
 'source_integrity':agent.get('citation_integrity')=='ORIGINAL_SPANS',
 'all_context_in_commercial_law':bool(assembly.get('context')) and all(x['document_id']=='7bbe815ff43b6635' for x in assembly['context'])}
review={'passed':all(checks.values()),'checks':checks,'service_status':q['status'],
 'source_id':source_id,'original_sha256':hashlib.sha256(source['text'].encode()).hexdigest() if source else None,
 'accepted_outcome':outcome,'explanatory_answer_claim_count':len(answer.get('claims',[])),
 'model_calls':r['model_calls'],'seconds':r['seconds'],
 'response_sha256':sha(ART/'known-query/response.json'),
 'limits':'Known question is an in-sample diagnostic. Passing original/claim/ratio delivery is not legal-quality or GENOS certification. Prior rejected results remain preserved.'}
save(ART/'known-query-review.json',review)
print(json.dumps(review,ensure_ascii=False))
