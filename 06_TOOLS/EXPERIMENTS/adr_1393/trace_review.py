"""Use the earlier route audit and count only JSON objects in an unfinished stream."""
from common import *
import base64,re,runpy
runpy.run_path(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1391/trace_review.py'),run_name='__main__')
trace=read(ART/'supervisor-trace.json')
for cell in trace['cells']:
    for part in cell['partial_streams']:
        payload=read(ADR/part['source'])
        fragments=[]
        for line in base64.b64decode(payload['body_base64']).splitlines():
            if not line.startswith(b'data:'):continue
            try:event=json.loads(line[5:])
            except ValueError:continue
            fragments.extend((c.get('delta',{}).get('content') or '') for c in event.get('choices',[]))
        text=''.join(fragments);tail=text.lstrip();objects=[]
        while tail.startswith('{'):
            try:value,end=json.JSONDecoder().raw_decode(tail)
            except ValueError:break
            objects.append(value)
            tail=re.sub(r'^(?:\s*```(?:json)?\s*)+','',tail[end:]).lstrip()
        part.update(complete_objects_in_prefix=len(objects),distinct_complete_objects=len({json.dumps(o,sort_keys=True) for o in objects}),
            unfinished_tail_chars=len(tail),trailing_brace_only_lines=sum(line.strip()=='}' for line in tail.splitlines()),
            tail_begins_with_action_field=tail.startswith('"action"'))
put(ART/'supervisor-trace.json',trace)
