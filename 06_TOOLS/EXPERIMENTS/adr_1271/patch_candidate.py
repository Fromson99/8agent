p=S/'02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py'
s=p.read_text()
helper="""def target_coordinate(row, *, path='/source_targets/coordinate'):
    \"\"\"Parse one exact locator; a matching display scope adds no new meaning.\"\"\"
    from .output_contract import OutputContractError,issue
    text=row['coordinate'].strip()
    if ':' in text:
        prefix,coordinate=text.split(':',1)
        if prefix not in COORDINATE_SCOPES or prefix!=row['coordinate_scope']:
            item=issue('SOURCE_TARGET_SCOPE_CONFLICT',path,
                related=[path.rsplit('/',1)[0]+'/coordinate_scope'],
                expected={'matching_scope':row['coordinate_scope']})
            item.update(received=text,message='Coordinate prefix must equal coordinate_scope; choose the intended scope explicitly.')
            raise OutputContractError('source target coordinate prefix conflicts with coordinate_scope',[item])
        text=coordinate.strip()
    occurrences=find_coordinates(text)
    if len(occurrences)!=1 or occurrences[0].start!=0 or occurrences[0].end!=len(text):
        item=issue('SOURCE_TARGET_COORDINATE_INVALID',path,
            expected='one complete legal coordinate; matching scope prefix optional; ranges use structure selection')
        item.update(received=row['coordinate'],message='Use one exact coordinate such as 제1조, with coordinate_scope in its separate field.')
        raise OutputContractError('source_targets.coordinate requires one complete legal coordinate; ranges need ordinary structure selection',[item])
    return occurrences[0].coordinate.canonical_surface()


"""
s=s.replace("PROMPT='''",helper+"PROMPT='''",1)
old="""        occurrences=find_coordinates(row['coordinate'].strip())
        if len(occurrences)!=1 or occurrences[0].start!=0 or occurrences[0].end!=len(row['coordinate'].strip()):
            raise ProposalError('source_targets.coordinate requires one complete legal coordinate; ranges need ordinary structure selection')"""
assert old in s;s=s.replace(old,"        target_coordinate(row,path='/source_targets/'+str(index)+'/coordinate')")
s=s.replace("coordinate=find_coordinates(row['coordinate'].strip())[0].coordinate.canonical_surface()","coordinate=target_coordinate(row)")
p.write_text(s)
mapping={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text());before=sha(p);changed=False
 for n,h in v.get('files',{}).items():
  actual=sha(S/n)
  if actual!=h:v['files'][n]=actual;changed=True
 if changed:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');mapping[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';s=p.read_text()
for old,new in mapping.items():s=s.replace(old,new)
p.write_text(s)
