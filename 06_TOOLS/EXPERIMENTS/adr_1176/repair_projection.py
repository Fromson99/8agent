from common import *
B=ROOT/read(DES/'candidate.json')['snapshot']/'02_BACKEND/semantic_runtime/legal_agent';p=B/'minimal_output.py';s=p.read_text();start=s.index('    def expand(self, raw):');end=s.index('\n    def project(self, value):',start)
s=s[:start]+'''    def expand(self, raw, path=()):
        from .output_contract import schema_issues, pointer
        def reject(message, rows):
            error=OutputContractError(message,rows)
            error.reference_space='wire'
            raise error
        def rows_for(value,schema):
            rows=schema_issues(Draft202012Validator(schema).iter_errors(value))
            for row in rows:
                row['path']=pointer(path).rstrip('/')+row['path']
            return rows
        if self.variants:
            if not isinstance(raw,dict) or self.discriminator not in raw:
                reject('minimal output missing discriminator: '+str(self.discriminator),
                    [issue('MINIMAL_OUTPUT_DISCRIMINATOR',pointer((*path,self.discriminator)),
                           expected={'enum':[label for label,_ in self.variants]})])
            matches, errors = {}, []
            for label, child in self.variants:
                if _key(label)!=_key(raw[self.discriminator]):continue
                try:
                    value=child.expand(raw,path)
                    Draft202012Validator(self.schema).validate(value)
                    matches[_key(value)]=value
                except (ValidationError,OutputContractError) as exc:errors.append(exc)
            if len(matches)!=1:
                if len(errors)==1 and isinstance(errors[0],OutputContractError):raise errors[0]
                problems=[]
                for error in errors:
                    problems.extend(error.issues if isinstance(error,OutputContractError) else rows_for(raw,self.schema))
                reject('minimal output has no unambiguous valid action',problems or
                    [issue('MINIMAL_OUTPUT_BRANCH',pointer((*path,self.discriminator)),
                           expected={'enum':list(dict.fromkeys(label for label,_ in self.variants))})])
            return next(iter(matches.values()))
        value=deepcopy(raw);problems=[];failed_paths=[]
        if isinstance(value,dict) and isinstance(self.schema,dict) and self.schema.get('type')=='object':
            for name,expected in self.fixed.items():
                if name in value and _key(value[name])!=_key(expected):
                    problems.append(issue('MINIMAL_OUTPUT_CONSTANT',pointer((*path,name)),expected={'const':expected}))
                    failed_paths.append(pointer((*path,name)));continue
                if name in value or name in self.schema.get('required',[]):value[name]=deepcopy(expected)
            for name,child in self.children.items():
                if name in value:
                    try:value[name]=child.expand(value[name],(*path,name))
                    except OutputContractError as exc:
                        problems.extend(exc.issues);failed_paths.append(pointer((*path,name)))
        elif isinstance(value,list) and self.item is not None:
            for n,v in enumerate(value):
                try:value[n]=self.item.expand(v,(*path,n))
                except OutputContractError as exc:
                    problems.extend(exc.issues);failed_paths.append(pointer((*path,n)))
        for row in rows_for(value,self.schema):
            if not any(row['path']==p or row['path'].startswith(p+'/') for p in failed_paths):problems.append(row)
        if problems:reject('minimal output fields do not match the expected action',problems)
        return value
''' +s[end:];p.write_text(s)
p=Path(__file__).parent/'check.py';s=p.read_text().replace('plugins=[r])','plugins=[r,conftest])');p.write_text(s)
print('projection preserves child paths and all independent errors; fixture registration corrected')
