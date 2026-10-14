"""Retain field transport and runtime differences; import qualified display methods."""
import ast

def function(source,name):
 for node in ast.walk(ast.parse(source)):
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==name:
   start=min([node.lineno,*[d.lineno for d in node.decorator_list]])-1
   return ''.join(source.splitlines(True)[start:node.end_lineno])
 raise ValueError(name)
def replace(s,old,new):
 assert s.count(old)==1,(old[:120],s.count(old));return s.replace(old,new,1)
def transform(raw,before,after,name):
 s=raw.decode();new=after.decode()
 if name=='main_workflow.py':
  if 'from genos_diagnostics import' not in s:
   new=replace(new,'from genos_diagnostics import install as install_system_logging\n\ninstall_system_logging("workflow-backend")\n','')
  return new.encode()
 if name.endswith('/workflow/genos_rag_chat.py'):
  # The repository copy must be identical to the separately deployed current
  # workflow editor; earlier editor source-card updates were shipped separately.
  return after
 if name.endswith('/chat_adapter.py'):
  # Transport/request/auth helpers remain those of the exact installed variant.
  return replace(s,function(s,'chat'),function(new,'chat')).encode()
 if name.endswith('/app.py') and not name.endswith('/stream_app.py'):
  if '\ndef legal_error_payload(' in s:s=replace(s,function(s,'legal_error_payload'),function(new,'legal_error_payload'))
  else:s=replace(s,'log = obs.get_logger("app")','log = obs.get_logger("app")\n\n\n'+function(new,'legal_error_payload').rstrip())
  start=s.index('    from .legal_agent.errors import LegalAgentError\n');end=s.index("    @app.get('/health')",start)
  ns=new.index('    from .legal_agent.errors import LegalAgentError\n');ne=new.index("    @app.get('/health')",ns)
  s=s[:start]+new[ns:ne]+s[end:]
  if '            return views().public_response(run)' not in s:
   s=replace(s,'            return run\n\n    def require_ad(body):','            from .chat_adapter import views\n            return views().public_response(run)\n\n    def require_ad(body):')
  # The optional local HTML page shares the safe final notice.
  oldline=next(l for l in s.splitlines(True) if "$('ask').onclick=" in l)
  newline=next(l for l in new.splitlines(True) if "$('ask').onclick=" in l)
  return replace(s,oldline,newline).encode()
 if name.endswith('/stream_app.py'):
  for fn in ('public_http_failure','install_http_diagnostics'):
   if '\ndef '+fn+'(' in s:s=replace(s,function(s,fn),function(new,fn))
   else:s=replace(s,'SSE_REVISION =',function(new,fn)+'\n\nSSE_REVISION =')
  if 'install_http_diagnostics(app)' not in s:s=replace(s,'SSE_REVISION =','install_http_diagnostics(app)\nSSE_REVISION =')
  for fn in ('json_endpoint',):
   s=replace(s,function(s,fn),function(new,fn))
  lines=s.splitlines(True)
  for i,line in enumerate(lines):
   if 'return JSONResponse(' in line and '400' in line:
    lines[i]='        return public_http_failure(400)\n'
  s=''.join(lines)
  # Insert exact duplicate/invalid-input handling, retaining existing queue and
  # heartbeat semantics of this installed cache/stream revision.
  oldstart=s.index('async def stream_response(');oldend=s.index('    async def events',oldstart)
  newstart=new.index('async def stream_response(');newend=new.index('    async def events',newstart)
  s=s[:oldstart]+new[newstart:newend]+s[oldend:]
  oldstart=s.index('            except Exception as exc:  # response details stay in code-serving logs');oldend=s.index('            if not detached.is_set():\n                await put_required(\'result\'',oldstart)
  newstart=new.index('            except Exception as exc:  # response details stay in code-serving logs');newend=new.index('            if not detached.is_set():\n                await put_required(\'result\'',newstart)
  s=s[:oldstart]+new[newstart:newend]+s[oldend:]
  if 'value = views().public_event(value)' not in s:
   s=replace(s,'        def sink(value):\n','        def sink(value):\n            from semantic_runtime.chat_adapter import views\n            value = views().public_event(value)\n            if value is None:return\n')
  return s.encode()
 raise ValueError(name)
