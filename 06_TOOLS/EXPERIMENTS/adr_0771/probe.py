"""Run the frozen synthetic MAIN progress-to-card matrix in one code root."""
from pathlib import Path
import asyncio,itertools,json,os,sys,tempfile
R=Path(__file__).resolve().parents[3];code=Path(sys.argv[1]).resolve()
sys.dont_write_bytecode=True;sys.path[:0]=[str(code/'02_BACKEND'),str(code)]
from semantic_runtime.progress import ProgressCapture
from semantic_runtime.chat_adapter import views
w=views();assert Path(w.__file__).is_relative_to(code)
criteria=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0771-source-cards-main-wiring/artifacts/design/criteria.json').read_text())['matrix']
rows=[]
for count,boundary,mode in itertools.product(criteria['counts'],criteria['boundaries'],criteria['modes']):
 os.environ['GENOS_RAG_PROGRESS_UI']=mode
 events=[];c=ProgressCapture('display-matrix',tempfile.gettempdir(),events.append)
 names=[f'external > mock_team > law > 경계모의법 {i:02}' for i in range(count)]
 c.publish('phase','요청',basis={'kind':'OBS_EVENT','name':'request.started'})
 for at in range(0,count,8):c.publish('candidate','자료 검색 · 관련 법령을 찾았습니다',details=names[at:at+8],basis={'kind':'LAW_FULLTEXT_DIRECTORY','detail_mode':'activity'})
 for name in names:c.publish('reading','원문 확인 · 법령 본문을 읽기 시작합니다',details=[name+' · 제7조'],basis={'kind':'UNIT_READ_STARTED','detail_mode':'activity'})
 if boundary=='candidate':c.publish('candidate','자료 검색 · 다음 후보',details=['추가후보'],basis={'kind':'LAW_FULLTEXT_DIRECTORY','detail_mode':'activity'})
 elif boundary=='decision':c.publish('selected','근거 검토',basis={'kind':'CASE_JUDGMENT_ACCEPTED','state':'COMPLETED','stage':'SELECT','detail_mode':'judgment'})
 d=w._ChatProgress({'socketIOClientId':'synthetic-room'});sent=[]
 async def emit(kind,value,room=None):sent.append((kind,json.loads(json.dumps(value))))
 d.emit=emit
 async def render():
  for e in events:await d.progress(e)
  await d.answer_delta({'schema_version':'rag-answer-delta-v1','seq':1,'text':'원문에 근거한 모의 답변입니다.'})
  await d.finish('원문에 근거한 모의 답변입니다.')
 asyncio.run(render())
 texts=[json.loads(b['data']['output']['content'])['visible_rationale'] for b in d.blocks]
 reading=[t for t in texts if '확인 대상' in t]
 search=[t for t in texts if '관련 법령을 찾았습니다' in t]
 visible_names=all(any(w._ChatProgress._plain(n) in t for t in search) for n in names)
 read_names=(not reading if not count else len(reading)==1 and all(w._ChatProgress._plain(n+' · 제7조') in reading[0] for n in names))
 tokens=''.join(v for k,v in sent if k=='token')
 assert tokens==('원문에 근거한 모의 답변입니다.' if mode=='socketio' else '')
 rows.append({'count':count,'boundary':boundary,'mode':mode,'source_paths_visible':visible_names,'one_complete_read_card':bool(read_names),'answer_unchanged':True,'cards':len(texts),'reading_cards':len(reading)})
Path(sys.argv[2]).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(len(rows),'matrix rows',sum(r['source_paths_visible'] and r['one_complete_read_card'] for r in rows),'complete source displays')
