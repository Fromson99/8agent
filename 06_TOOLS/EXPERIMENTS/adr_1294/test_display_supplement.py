"""Semantic DOM verification for parent test's obsolete literal <details> check."""
from copy import deepcopy
from types import SimpleNamespace as S
from html.parser import HTMLParser
from markdown_it import MarkdownIt
from test_internal_concept_comparison import source,concept,concept_report
class DOM(HTMLParser):
 def __init__(self):super().__init__();self.tags=[];self.text=[]
 def handle_starttag(self,tag,attrs):self.tags.append(tag)
 def handle_data(self,data):self.text.append(data)
def test_comparison_source_details_dom_preserves_literals_and_locations():
 s=source();c=concept(s);c.pop('existing_id');c['id']='concept-1'
 state={'concept_plan':{'concepts':[c]},'question_scope':{'issues':[{'id':'question-1'}]}}
 body={'comparison_items':{'items':[]},'assembly':{'term_agent':{'source_bundle':{'sources':[]}}},'report':{},'answer':{},'evidence_refs':[],'evidence_summary':{},'unresolved':['외규 미확보']}
 before=deepcopy(state);result=concept_report.apply(S(request={'question':'승인 기준 대사','as_of':None}),state,body,{'in':s})
 html=MarkdownIt('commonmark',{'html':True}).enable('table').render(result['answer']['text']);d=DOM();d.feed(html);text=''.join(d.text)
 assert d.tags.count('th')==3 and d.tags.count('td')==3
 assert 'details' in d.tags and 'summary' in d.tags
 assert all(t in text for t in ('모의내규 A','제2장 제3조 제1항','<원문>','단서는 보존한다.','해당 규정이 없다는 뜻은 아닙니다'))
 assert result['comparison_table']['rows'][0]['internal'][0]['quote']==s['text'] and state==before
