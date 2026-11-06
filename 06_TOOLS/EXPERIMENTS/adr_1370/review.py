from common import *
rows=[]
for d in sorted((ART/'public-live').glob('*')):
 if not (d/'result.json').exists():continue
 r=read(d/'result.json');turns=r.get('turns',[])
 rows.append({'cell':d.name,'semantic_pass':False,'review_state':'MANUAL_REVIEW_REQUIRED','claims':sum(t['claims'] for t in turns),'unknown':r.get('unknown',0)})
put(ART/'semantic-review.json',{'rows':rows,'all_passed':False,'judging_model_calls':0,'product_response_rewritten':False,'conclusion':'Actual source and schema checks are separate from pending semantic and UI/internal review.'})
