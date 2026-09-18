from pathlib import Path
R=Path.cwd();P=R/'02_BACKEND/lawrag/research/candidates/adr_0456/stateful/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime';B=R/'02_BACKEND/lawrag/research/candidates/adr_0457/portable/snapshot/02_BACKEND/semantic_runtime';B.mkdir(parents=True,exist_ok=True)
for f in ['compact_handles.py','navigation_work_state.py','stateful_navigation.py','work_navigation.py','expression_probe_binding.py']:
 s=(P/f).read_text()
 if f=='expression_probe_binding.py':s=s.replace("arm=='stateful'","arm=='portable'")
 if f=='work_navigation.py':
  needle='class WorkSession(previous.TypedSession):'
  code='''def portable_schema(value):
    """Project provider grammar bounds only; callers validate the original contract."""
    if isinstance(value,list):return [portable_schema(v) for v in value]
    if not isinstance(value,dict):return deepcopy(value)
    out={k:portable_schema(v) for k,v in value.items() if k not in ('minItems','maxItems')}
    if value.get('type')=='array' and any(k in value for k in ('minItems','maxItems')):
        bounds=', '.join(f'{k}={value[k]}' for k in ('minItems','maxItems') if k in value)
        out['description']=(out.get('description','')+' Required array bounds, checked locally: '+bounds+'.').strip()
    return out

'''
  s=s.replace(needle,code+needle)
  old='self.calls+=1;out,receipt=provider.call(role,system,data,schema);self.receipts.append(receipt);Draft202012Validator(schema).validate(out);return out'
  new='''self.calls+=1
        wire_schema=portable_schema(schema) if role in ('navigation_synthesis','navigation_verify') else schema
        out,receipt=provider.call(role,system,data,wire_schema)
        self.receipts.append({**receipt,'local_validation_schema':deepcopy(schema),'schema_projection':{'version':'array-bounds-local-v1','applied':wire_schema!=schema,'wire_sha256':hashlib.sha256(json.dumps(wire_schema,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}})
        Draft202012Validator(schema).validate(out)
        return out'''
  assert old in s;s=s.replace(old,new)
 (B/('portable_navigation.py' if f=='stateful_navigation.py' else f)).write_text(s)
