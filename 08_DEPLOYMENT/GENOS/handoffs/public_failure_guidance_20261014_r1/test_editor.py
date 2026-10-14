import ast,asyncio,hashlib,types
from pathlib import Path
import pytest
O=Path(__file__).resolve().parent;R=O.parents[3]
@pytest.fixture
def editor(monkeypatch,tmp_path):
 monkeypatch.setenv('GENOS_SYSTEM_LOG_DIR',str(tmp_path/'logs'))
 monkeypatch.setenv('GENOS_LOG_SPOOL_DIR',str(tmp_path/'spool'))
 monkeypatch.setenv('GENOS_RAG_PROGRESS_UI','off')
 module=types.ModuleType('tested_editor');module.__file__=str(O/'GENOS_PUBLIC_FAILURE_GUIDANCE_20261014_R1_PASTE_ALL.txt')
 exec(compile(Path(module.__file__).read_bytes(),module.__file__,'exec'),module.__dict__)
 return module

def test_embedded_source_matches_selected_release():
 raw=(O/'GENOS_PUBLIC_FAILURE_GUIDANCE_20261014_R1_PASTE_ALL.txt').read_bytes();source=(R/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes()
 assert raw.endswith(source);ast.parse(raw,feature_version=(3,10))
@pytest.mark.parametrize('status',[401,403,409,413,422,429,500,502,503,504])
def test_editor_notice_status_preservation(editor,status):
 body=editor.public_failure('editor-1',status=status)
 assert body['answer_status']=='failed' and f'({status})' in editor.render(body)
 assert body['message'].startswith('현재 충분한 법률 검토를 하지 못했습니다.')
@pytest.mark.parametrize('phase',['preflight','request','render'])
def test_editor_failure_finishes_once(editor,monkeypatch,phase):
 finished=[];calls=[]
 def post(data):
  if phase=='preflight':return {'status':503,'body':{'error':'private'}}
  return {'status':200,'body':{'ad_handled':False}}
 async def stream(*args):
  calls.append(1)
  if phase=='request':raise TimeoutError('private')
  return {'answer':{'text':'ok'}}
 async def finish(self,text):finished.append(text)
 monkeypatch.setattr(editor,'_post_code_serving',post);monkeypatch.setattr(editor,'_stream_code_serving',stream);monkeypatch.setattr(editor._ChatProgress,'finish',finish)
 if phase=='render':monkeypatch.setattr(editor,'_judgment_flow',lambda *a: (_ for _ in ()).throw(ValueError('private')))
 result=asyncio.run(editor.run({'question':'모의 질문','request_id':'editor-1'}))
 assert result['answer_status']=='failed' and len(finished)==1 and 'private' not in result['text']
 assert len(calls)==(0 if phase=='preflight' else 1)
def test_editor_normal_and_limited_answers_preserved(editor):
 for coverage in ['FULL','PARTIAL','INSUFFICIENT']:
  b={'answer':{'text':'확인된 범위의 답변'},'assembly':{'term_agent':{'completion_contract':'v8','answer_coverage':coverage}}}
  assert editor.render(b).startswith('확인된 범위의 답변')
 assert '조금 더 구체적으로 질문해 주세요.' in editor.render({})
