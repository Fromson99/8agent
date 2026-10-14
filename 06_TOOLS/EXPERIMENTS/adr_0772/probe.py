"""Frozen complete synthetic provider-group matrix, no model calls."""
from pathlib import Path
import asyncio,itertools,json,os,sys,tempfile
R=Path(__file__).resolve().parents[3];code=Path(sys.argv[1]).resolve();sys.dont_write_bytecode=True;sys.path[:0]=[str(code/'02_BACKEND'),str(code)]
from semantic_runtime.progress import ProgressCapture
from semantic_runtime.chat_adapter import views
w=views();assert Path(w.__file__).is_relative_to(code)
criteria=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0772-source-provider-display/artifacts/design/criteria.json').read_text())['matrix'];results=[]
for count,boundary,mode in itertools.product(criteria['counts'],criteria['boundaries'],criteria['modes']):
 os.environ['GENOS_RAG_PROGRESS_UI']=mode;events=[];c=ProgressCapture('provider-matrix',tempfile.gettempdir(),events.append)
 names=[f'external > mock_team > '+['krx','law','kofia'][i%3]+f' > 경계모의법 {i:02}' for i in range(count)]
 titles=[f'경계모의법 {i:02}' for i in range(count)]
 c.publish('phase','요청',basis={'kind':'OBS_EVENT','name':'request.started'})
 for at in range(0,count,8):c.publish('candidate','자료 검색 · 관련 법령을 찾았습니다',details=names[at:at+8],basis={'kind':'LAW_FULLTEXT_DIRECTORY','detail_mode':'activity','journal_seq':11})
 for name in names:c.publish('reading','원문 확인',details=[name+' · 제7조'],basis={'kind':'UNIT_READ_STARTED','detail_mode':'activity'})
 if boundary=='candidate':c.publish('candidate','자료 검색 · 다음 후보',details=['추가후보'],basis={'kind':'LAW_FULLTEXT_DIRECTORY','detail_mode':'activity','journal_seq':12})
 elif boundary=='decision':c.publish('selected','근거 검토',basis={'kind':'CASE_JUDGMENT_ACCEPTED','state':'COMPLETED','stage':'SELECT','detail_mode':'judgment'})
 d=w._ChatProgress({'socketIOClientId':'synthetic-room'});sent=[]
 async def emit(kind,value,room=None):sent.append((kind,json.loads(json.dumps(value))))
 d.emit=emit
 async def render():
  for e in events:await d.progress(e)
  await d.answer_delta({'schema_version':'rag-answer-delta-v1','seq':1,'text':'모의 답변입니다.'})
  await d.finish('모의 답변입니다.')
 asyncio.run(render())
 texts=[json.loads(b['data']['output']['content'])['visible_rationale'] for b in d.blocks];reads=[t for t in texts if '확인 대상' in t];search=[t for t in texts if '관련 법령을 찾았습니다' in t]
 titles_ok=all(any(n in t for t in search) and any(n+' · 제7조' in t for t in reads) for n in titles)
 groups_ok=not count or (len(search)==len(reads)==1 and all('external' not in t and 'mock' not in t for t in search+reads) and all(any('외부법률 / '+label in t for t in search) for label in ['한국거래소','법제처','한국금융투자협회'][:min(count,3)]))
 tokens=''.join(v for k,v in sent if k=='token');assert tokens==('모의 답변입니다.' if mode=='socketio' else '')
 results.append({'count':count,'boundary':boundary,'mode':mode,'all_titles_visible':titles_ok,'korean_provider_groups':bool(groups_ok),'answer_unchanged':True,'search_cards':len(search),'read_cards':len(reads)})
Path(sys.argv[2]).write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print(len(results),'matrix rows',sum(x['all_titles_visible'] and x['korean_provider_groups'] for x in results),'complete grouped displays')
