from pathlib import Path
S=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_1308/optimized/snapshot'
p=S/'02_BACKEND/semantic_runtime/oracle_query_db.py'
s=p.read_text().replace('\x08legal_normalized',r'\blegal_normalized')
old='        self._needs_literal = bool(re.search'
start=s.index(old)
s=s[:start]+'''        from .oracle_query_cache import for_request, key as result_key
        query_cache=for_request(self.request)
        query_key=result_key('relational',asset=self.asset,statement=statement,parameters=list(parameters),tables=self.tables)
        cache_hit,cached=query_cache.get(query_key)
        if cache_hit:return Cursor(cached[0],cached[1])
'''+s[start:]
start=s.index('                for predicate in conjuncts(where.this) if where is not None else ():')
end=s.index("            replacement.set('alias'",start)
s=s[:start]+'''                encoding=self.tables[node.name][1].get('lookup_encoding')
                if encoding not in (None,LOOKUP_ENCODING):
                    raise DPError('QUERY_LOOKUP_ENCODING: unsupported auxiliary key encoding')
                def indexed_value(value):
                    if not isinstance(value,(exp.Literal,exp.Placeholder)):return None
                    actual=(value.this if isinstance(value,exp.Literal) and value.is_string else
                            next((v for n,v,_ in binds if n==value.this),None) if isinstance(value,exp.Placeholder) else None)
                    # Oracle empty/NULL and implicit numeric conversions cannot
                    # narrow the maintained string key safely.
                    if not isinstance(actual,str) or not actual:return None
                    if encoding==LOOKUP_ENCODING and len(actual.encode())>512:
                        name='a8_index_key'+str(len(binds));binds.append((name,lookup_key(actual),'VARCHAR2'))
                        return exp.Placeholder(this=name)
                    return value.copy()
                def physical(column):
                    return (exp.column(columns[column.name],table='r') if isinstance(column,exp.Column)
                            and column.table==alias and column.name in columns else None)
                def push(predicate):
                    if isinstance(predicate,exp.Paren):return push(predicate.this)
                    if isinstance(predicate,(exp.And,exp.Or)):
                        left,right=push(predicate.this),push(predicate.expression)
                        if isinstance(predicate,exp.Or):
                            return exp.or_(left,right) if left is not None and right is not None else None
                        return exp.and_(left,right) if left is not None and right is not None else left if left is not None else right
                    if isinstance(predicate,exp.EQ):
                        column=physical(predicate.this);value=indexed_value(predicate.expression)
                        if column is None:
                            column=physical(predicate.expression);value=indexed_value(predicate.this)
                        return exp.EQ(this=column,expression=value) if column is not None and value is not None else None
                    if isinstance(predicate,exp.In):
                        column=physical(predicate.this)
                        if column is None:return None
                        values=predicate.expressions
                        if not values and predicate.args.get('query') is not None:
                            sub=predicate.args['query'];sub=sub.this if isinstance(sub,exp.Subquery) else sub
                            tables=list(sub.find_all(exp.Table));projections=list(sub.selects)
                            # Only the exact one-column JSON array relation; no
                            # joins, filters, distinct, limit or expressions.
                            if (len(tables)!=1 or len(projections)!=1 or not isinstance(projections[0],exp.Column)
                                or projections[0].name!='value' or any(sub.args.get(k) for k in ('where','joins','group','limit','offset','distinct'))):return None
                            fn=tables[0].this
                            if not isinstance(fn,exp.Anonymous) or fn.name.lower()!='json_each' or len(fn.expressions)!=1:return None
                            arg=fn.expressions[0]
                            raw=next((v for n,v,_ in binds if isinstance(arg,exp.Placeholder) and n==arg.this),None)
                            try:array=json.loads(raw) if isinstance(raw,str) else None
                            except ValueError:return None
                            if not isinstance(array,list) or not 1<=len(array)<=1000 or any(not isinstance(v,str) or not v for v in array):return None
                            values=[]
                            for actual in array:
                                name='a8_index_key'+str(len(binds))
                                binds.append((name,lookup_key(actual) if encoding==LOOKUP_ENCODING else actual,'VARCHAR2'))
                                values.append(exp.Placeholder(this=name))
                        if not values or len(values)>1000:return None
                        indexed=[indexed_value(v) for v in values]
                        if any(v is None for v in indexed):return None
                        return exp.In(this=column,expressions=indexed)
                    return None
                pushed=push(where.this) if where is not None else None
                if pushed is not None:
                    replacement.this.set('this',replacement.this.this+' AND ('+pushed.sql(dialect='oracle')+')')
'''+s[end:]
old='''        def decoded():
            for row in self._pages(packed,binds):
                for i,flag in zip(empty_indexes,row[len(outputs):]):
                    if flag==1: row[i]=''
                yield row[:len(outputs)]
        return Cursor(outputs,decoded())'''
new='''        def decoded():
            saved=[];size=0
            for row in self._pages(packed,binds):
                for i,flag in zip(empty_indexes,row[len(outputs):]):
                    if flag==1: row[i]=''
                value=row[:len(outputs)]
                if saved is not None:
                    size+=len(json.dumps(value,ensure_ascii=False).encode())
                    if size<=4*1024*1024:saved.append(value)
                    else:saved=None
                yield value
            if saved is not None:query_cache.put(query_key,[outputs,saved])
        return Cursor(outputs,decoded())'''
assert old in s;s=s.replace(old,new)
p.write_text(s)
# A changed manifest cannot make a prior successful cached read authoritative.
p=S/'02_BACKEND/semantic_runtime/oracle_query_cache.py';s=p.read_text().replace('frozenset(r.sources.allowed))','frozenset(r.sources.allowed), digest(getattr(getattr(r, \'records\', None), \'manifest\', None)))');p.write_text(s)
print('SQL cache and key predicates written')
