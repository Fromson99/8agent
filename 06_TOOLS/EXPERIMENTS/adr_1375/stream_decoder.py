"""Strict assembly of one completed OpenRouter chat SSE; no schema repair."""
import json


def decode_stream(body):
    text=body.decode('utf-8').replace('\r\n','\n').replace('\r','\n')
    if not text.endswith('\n\n'):raise ValueError('incomplete SSE frame')
    identity={};content=[];reasoning=[];finish=None;usage=None;done=False;error=None
    for frame in text.split('\n\n'):
        lines=[line[5:].removeprefix(' ') for line in frame.split('\n') if line.startswith('data:')]
        if not lines:continue
        data='\n'.join(lines)
        if done:raise ValueError('data after DONE')
        if data=='[DONE]':done=True;continue
        row=json.loads(data)
        if not isinstance(row,dict):raise ValueError('SSE data is not object')
        for field in ('id','model','provider'):
            value=row.get(field)
            if value is not None:
                if not isinstance(value,str) or not value:raise ValueError('invalid stream identity')
                if field in identity and identity[field]!=value:raise ValueError('stream identity changed: '+field)
                identity[field]=value
        if row.get('error'):error=row['error']
        if row.get('usage') is not None:
            if not isinstance(row['usage'],dict):raise ValueError('invalid stream usage')
            usage=row['usage']
        choices=row.get('choices',[])
        if not isinstance(choices,list) or len(choices)>1:raise ValueError('unexpected stream choices')
        for choice in choices:
            if choice.get('index')!=0:raise ValueError('unexpected stream choice index')
            delta=choice.get('delta',{})
            if not isinstance(delta,dict):raise ValueError('invalid stream delta')
            if delta.get('tool_calls') or delta.get('function_call'):raise ValueError('unexpected tool output')
            if delta.get('role') not in (None,'assistant'):raise ValueError('unexpected role')
            for key,target in [('content',content),('reasoning',reasoning),('reasoning_content',reasoning)]:
                value=delta.get(key)
                if value is not None:
                    if not isinstance(value,str):raise ValueError('invalid '+key+' delta')
                    if finish is not None and value:raise ValueError('content after terminal frame')
                    target.append(value)
            terminal=choice.get('finish_reason')
            if terminal is not None:
                if finish is not None and finish!=terminal:raise ValueError('terminal reason changed')
                finish=terminal
    if not done or finish is None:raise ValueError('stream did not complete')
    if error:
        return {**identity,'error':error,'choices':[{'index':0,'finish_reason':finish,'message':{'role':'assistant','content':''.join(content)}}], 'usage':usage}
    if set(identity)!={'id','model','provider'}:raise ValueError('missing stream identity')
    if usage is None:raise ValueError('missing final stream usage')
    return {**identity,'object':'chat.completion','choices':[{'index':0,'finish_reason':finish,
        'message':{'role':'assistant','content':''.join(content),**({'reasoning':''.join(reasoning)} if reasoning else {})}}], 'usage':usage}
