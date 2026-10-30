from common import *
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1105/source_audit.py').read_text().replace("read(DES/'cases.json')","read(ART/'cases.json')")
Path(__file__).with_name('source_audit.py').write_text(s)
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1105/wire_audit.py').read_text().replace("f['arms'][arm]['code_root']","f['code_root']")
s=s.replace('for call in calls:', 'physical=0\nfor call in calls:')
s=s.replace(" native=next((P/'raw').glob(f\"call-{call['call']:03d}-*/request.json\"));actual=read(native)"," if call.get('new_model_call'):\n  physical+=1;native=next((P/'raw').glob(f'call-{physical:03d}-*/request.json'));actual=read(native)\n else:actual=wirebody")
needle=" rows.append(row)"
s=s.replace(needle,""" if call['phase'].startswith('memory-assess'):
  row['semantic_plans']=[]
  for card in view.get('ontology_bundles',[]):
   plan=card.get('payload',{}).get('semantic_plan')
   if not plan:continue
   used=[ref for n in plan['ordered_steps'] for ref in n.get('source_refs',[])]
   quotes=[b for n in plan['ordered_steps'] for b in n.get('basis',[])]
   def quoted(b):
    texts_for_refs=[option_text(options[r]) for r in b['source_refs'] if r in options]
    return b['quote'] in ''.join(x or '' for x in texts_for_refs)
   row['semantic_plans'].append({'steps':len(plan['ordered_steps']),'authority':plan['authority'],'unknown_refs':[r for r in used if r not in options],'quote_checks':len(quotes),'quote_failures':[b for b in quotes if not quoted(b)]})
 rows.append(row)""")
s=s.replace("put(P/'wire-audit.json',out)","out['semantic_unknown_refs']=sum(len(p['unknown_refs']) for r in rows for p in r.get('semantic_plans',[]));out['semantic_quote_failures']=sum(len(p['quote_failures']) for r in rows for p in r.get('semantic_plans',[]))\nput(P/'wire-audit.json',out)")
Path(__file__).with_name('wire_audit.py').write_text(s)
