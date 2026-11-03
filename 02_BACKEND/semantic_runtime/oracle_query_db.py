"""Maintained relational reads over a request-pinned Oracle projection.

SQL comes from repository consumers, never a model or HTTP request. The parser
resolves only declared logical tables to scoped JSON_TABLE projections. No
SQLite source/index file is opened and no corpus is materialized in serving.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import re

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify

from .oracle_dp_io import DPError, units
from .oracle_query_catalog import ROW, json_body, LOOKUP_ENCODING, lookup_key


class Row:
    def __init__(self,names,values):
        self.names,self.values=tuple(names),tuple(values)
    def __getitem__(self,key):
        return self.values[self.names.index(key)] if isinstance(key,str) else self.values[key]
    def __iter__(self):
        return iter(self.values)
    def __len__(self):
        return len(self.values)
    def keys(self):
        return self.names


class Cursor:
    def __init__(self,names,rows):
        self.description=[(name,None,None,None,None,None,None) for name in names]
        self.names,self.rows=names,iter(rows)
    def __iter__(self):
        return self
    def __next__(self):
        return Row(self.names,next(self.rows))
    def fetchone(self):
        return next(self,None)
    def fetchmany(self,size=100):
        if type(size) is not int or not 0<=size<=10000:
            raise DPError('QUERY_PAGE: invalid fetch size')
        rows=[]
        for _ in range(size):
            row=self.fetchone()
            if row is None: break
            rows.append(row)
        return rows
    def fetchall(self):
        return list(self)
    def close(self):
        close=getattr(self.rows,'close',None)
        if close: close()


def _identifier(value):
    if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',value):
        raise DPError('QUERY_SQL_IDENTIFIER: undeclared identifier syntax')
    return value


def _parameters(statement,values):
    if isinstance(values,Mapping):
        raise DPError('QUERY_SQL_BINDS: maintained port requires positional parameters')
    placeholders=[t for t in sqlglot.Dialect.get_or_raise('sqlite').tokenize(statement) if t.token_type.name=='PLACEHOLDER']
    if len(placeholders)!=len(values) or any(t.text!='?' for t in placeholders):
        raise DPError('QUERY_SQL_BINDS: parameter count or style differs')
    for i,token in reversed(list(enumerate(placeholders))):
        statement=statement[:token.start]+':a8_p'+str(i)+statement[token.end+1:]
    binds=[]
    for i,value in enumerate(values):
        if value is not None and not isinstance(value,(str,int,float)):
            raise DPError('QUERY_SQL_BINDS: unsupported scalar bind')
        typ='NUMBER' if isinstance(value,(int,float)) else 'CLOB' if isinstance(value,str) and len(value.encode())>4000 else 'VARCHAR2'
        binds.append(('a8_p'+str(i),value,typ))
    return statement,binds


class Connection:
    def __init__(self,request,asset):
        self.request,self.sql=request,request.sql
        self.asset=asset
        self.tables={v['table']:(kind,v) for kind,v in request.records.manifest['tables'].items()
                     if v.get('asset')==asset and 'columns' in v}
        if not self.tables:
            raise DPError('QUERY_SQL_SCHEMA: no projected relational schema for '+asset)
        self.row_factory=None
        self.closed=False

    def close(self):
        self.closed=True

    def set_progress_handler(self,callback,steps):
        # Oracle owns execution; check caller cancellation between bounded
        # requests in addition to the shared ORDS deadline/call budget.
        self.progress_handler=callback

    def _progress(self):
        callback=getattr(self,'progress_handler',None)
        if callback is not None and callback():
            raise DPError('QUERY_CANCELLED: caller deadline/cancellation reached')

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.close()

    def _view(self,name,number):
        kind,table=self.tables[name]
        definitions=[]
        for column,spec in table['columns'].items():
            _identifier(column)
            typ=('NUMBER' if spec['type'] in ('integer','real') else
                 'CLOB' if spec['max_bytes']>4000 else 'VARCHAR2(4000)')
            definitions.append('"'+column+'" '+typ+" PATH '$."+column+"' ERROR ON ERROR")
        suffix=str(number)
        binds=[('a8_release'+suffix,self.request.release_id,'VARCHAR2'),('a8_kind'+suffix,kind,'VARCHAR2'),
               ('a8_scope'+suffix,json_body(sorted(self.request.sources.allowed)),'CLOB')]
        text=('SELECT jt.*,r.ROW_ID AS "a8_row_id" FROM '+ROW+' r,JSON_TABLE(r.VALUE_JSON,\'$\' COLUMNS('+','.join(definitions)+')) jt '
              f'WHERE r.RELEASE_ID=:a8_release{suffix} AND r.KIND=:a8_kind{suffix} '
              '(AND_SCOPE)')
        text=text.replace('(AND_SCOPE)',f"AND (r.DOCUMENT_ID IS NULL OR r.DOCUMENT_ID IN (SELECT s.did FROM JSON_TABLE(:a8_scope{suffix},'$[*]' COLUMNS(did VARCHAR2(512) PATH '$')) s))")
        flags=["CASE WHEN JSON_EXISTS(r.VALUE_JSON,'$?(@."+c+" == \"\")') THEN 1 ELSE 0 END AS \"a8_empty_"+c+'"'
               for c,spec in table['columns'].items() if spec.get('has_empty')]
        if flags: text=text.replace('SELECT jt.*,','SELECT jt.*,'+','.join(flags)+',',1)
        # The maintained JSON_TABLE ERROR clauses are Oracle SQL; SQLGlot's
        # Oracle parser does not currently accept column-level ERROR ON ERROR.
        # Keep this generated, identifier-validated view as an opaque AST leaf.
        return exp.Subquery(this=exp.Var(this=text)),binds

    def _catalogue(self,statement,parameters):
        # sqlite_master/table_info are metadata requests. Interpret only the
        # small declared schema locally; no source/index rows enter SQLite.
        import sqlite3
        cache_key=(statement,tuple(parameters))
        cached=getattr(self,'_schema_results',{}).get(cache_key)
        if cached is not None:return Cursor(list(cached[0]),list(cached[1]))
        if not statement.lstrip().upper().startswith(('SELECT ','PRAGMA TABLE_INFO(')):
            raise DPError('QUERY_SQL_READ_ONLY: schema metadata is read-only')
        with sqlite3.connect(':memory:') as db:
            db.execute('PRAGMA temp_store=MEMORY')
            for name,(_,spec) in self.tables.items():
                columns=','.join('"'+_identifier(c)+'" '+('INTEGER' if v['type']=='integer' else 'REAL' if v['type']=='real' else 'TEXT')
                                 for c,v in spec['columns'].items())
                db.execute('CREATE TABLE "'+_identifier(name)+'"('+columns+')')
            cursor=db.execute(statement,parameters)
            names=[d[0] for d in cursor.description];rows=cursor.fetchall()
            if not hasattr(self,'_schema_results'):self._schema_results={}
            if len(self._schema_results)<64:self._schema_results[cache_key]=(tuple(names),tuple(rows))
            return Cursor(names,rows)

    def execute(self,statement,parameters=()):
        self._progress()
        if self.closed:
            raise DPError('QUERY_SQL_CLOSED: request connection is closed')
        if re.fullmatch(r'\s*PRAGMA\s+query_only\s*=\s*(ON|1)\s*',statement,re.I):
            return Cursor([],[])
        if re.fullmatch(r'\s*PRAGMA\s+table_info\(.+\)\s*',statement,re.I) or 'sqlite_master' in statement:
            return self._catalogue(statement,parameters)
        from .oracle_query_cache import for_request, key as result_key
        query_cache=for_request(self.request)
        query_key=result_key('relational',asset=self.asset,statement=statement,parameters=list(parameters),tables=self.tables)
        cache_hit,cached=query_cache.get(query_key)
        if cache_hit:return Cursor(cached[0],cached[1])
        self._needs_literal = bool(re.search(r'\blegal_normalized\s*\(', statement, re.I))
        statement,binds=_parameters(statement,list(parameters))
        trees=sqlglot.parse(statement,read='sqlite')
        if len(trees)!=1 or not isinstance(trees[0],(exp.Select,exp.Union)):
            raise DPError('QUERY_SQL_READ_ONLY: one maintained SELECT required')
        tree=trees[0]
        if tree.find(exp.Into) or tree.find(exp.Lock):
            raise DPError('QUERY_SQL_READ_ONLY: materialization/locking not allowed')
        # SQLite permits DISTINCT(json) ORDER BY id. Oracle disallows that,
        # and cannot DISTINCT a CLOB. These maintained identity-bearing rows
        # have unique IDs in their JSON; join fanout is an existence test.
        base=tree.args.get('from_')
        base=base.this if base is not None else None
        joins=tree.args.get('joins') or []
        if (isinstance(base,exp.Table) and base.name in ('reference','source','term','definition')
                and tree.args.get('distinct') and joins and len(joins)==1):
            expressions=[p.this if isinstance(p,exp.Alias) else p for p in tree.expressions]
            if (all(isinstance(p,exp.Column) and p.table==base.alias_or_name for p in expressions)
                    and any(p.name in ('id','json') for p in expressions) and not joins[0].args.get('side')):
                condition=joins[0].args.get('on')
                where=tree.args.get('where')
                if where is not None: condition=exp.and_(condition,where.this.copy()) if condition is not None else where.this.copy()
                exists=exp.select('1').from_(joins[0].this.copy())
                if condition is not None: exists=exists.where(condition.copy())
                tree.set('joins',[]);tree.set('distinct',None)
                tree.set('where',exp.Where(this=exp.Exists(this=exists)))
        # Resolve stars and preserve cursor column names before physical tables
        # are replaced. Unknown relations are rejected below, including schemas.
        schema={t:{c:'INT' if v['type']=='integer' else 'DOUBLE' if v['type']=='real' else 'TEXT'
                   for c,v in spec['columns'].items()} for t,(_,spec) in self.tables.items()}
        tree=qualify(tree,dialect='sqlite',schema=schema,quote_identifiers=False,validate_qualify_columns=False)
        outputs=[projection.output_name for projection in tree.selects]
        if any(not n for n in outputs) or len(outputs)!=len(set(outputs)):
            raise DPError('QUERY_SQL_COLUMNS: output names must be unambiguous')
        ctes={n.alias for n in tree.find_all(exp.CTE)}
        root_tables=[]
        column_schemas={node.alias_or_name:self.tables[node.name][1]['columns'] for node in tree.find_all(exp.Table) if node.name in self.tables}
        def empty_flag(column):
            if (self.asset!='oracle-source' and isinstance(column,exp.Column) and
                    column_schemas.get(column.table,{}).get(column.name,{}).get('has_empty')):
                return exp.column('a8_empty_'+column.name,table=column.table)
            return None
        output_flags=[]
        for projection in tree.selects:
            expression=projection.this if isinstance(projection,exp.Alias) else projection
            output_flags.append(empty_flag(expression))
        for node in list(tree.find_all(exp.Table)):
            if isinstance(node.this,exp.Anonymous) and node.this.name.lower()=='json_each':
                if len(node.this.expressions)!=1:
                    raise DPError('QUERY_SQL_JSON: only array iteration is supported')
                argument=node.this.expressions[0].sql(dialect='oracle')
                replacement=sqlglot.parse_one("SELECT value FROM JSON_TABLE("+argument+",'$[*]' COLUMNS(value VARCHAR2(4000) PATH '$'))",read='oracle').args['from_'].this
                replacement.set('alias',node.args.get('alias'))
                node.replace(replacement)
                continue
            if node.name in ctes:
                continue
            if node.db or node.catalog or node.name not in self.tables:
                raise DPError('QUERY_SQL_TABLE: undeclared relational table')
            alias=node.alias_or_name
            if node.parent and (isinstance(node.parent,exp.From) or isinstance(node.parent,exp.Join)) and node.find_ancestor(exp.Select) is tree:
                root_tables.append(alias)
            replacement,more=self._view(node.name,len(binds))
            # Push a maintained key predicate onto the physical B-tree column.
            # JSON_TABLE alone otherwise scans every row of a large glossary.
            if self.asset!='oracle-source':
                specs=self.tables[node.name][1]['columns']
                columns={}
                for physical,choices in [('LOOKUP_ID',('id','key','term_id','node_id')),
                                          ('OWNER_ID',('source_id','reference_id','definition_id')),
                                          ('TARGET_ID',('target_id','target','parent_id'))]:
                    logical=next((name for name in choices if name in specs),None)
                    spec=specs.get(logical,{})
                    if logical and spec.get('type')=='text' and not spec.get('has_null') and not spec.get('has_empty'):
                        columns[logical]=physical
                where=node.find_ancestor(exp.Select).args.get('where')
                def conjuncts(value):
                    if isinstance(value,exp.And):
                        yield from conjuncts(value.this);yield from conjuncts(value.expression)
                    else: yield value
                encoding=self.tables[node.name][1].get('lookup_encoding')
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
                            tables=list(sub.find_all(exp.Table));projections=[p.this if isinstance(p,exp.Alias) else p for p in sub.selects]
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
            replacement.set('alias',exp.TableAlias(this=exp.to_identifier(alias)))
            binds.extend(more)
            node.replace(replacement)
        for node in list(tree.find_all(exp.JSONExtractScalar)):
            path=node.expression.sql(dialect='oracle')
            column=node.this
            spec=column_schemas.get(column.table,{}).get(column.name,{}) if isinstance(column,exp.Column) else {}
            shape=spec.get('json_paths',{}).get(path.strip("'"))
            types=set(shape.get('types',[]))-{'null'} if shape else set()
            if types and types <= {'array','object'}:
                function,kind='JSON_QUERY','CLOB'
            elif types and types <= {'integer','real'}:
                function,kind='JSON_VALUE','NUMBER'
            else:
                function='JSON_VALUE'
                kind='CLOB' if (shape or {}).get('max_bytes',0)>4000 or path in ("'$.text'","'$.body'") else 'VARCHAR2(4000)'
            text=function+'('+node.this.sql(dialect='oracle',identify=True)+','+path+' RETURNING '+kind+' NULL ON EMPTY ERROR ON ERROR)'
            if types=={'boolean'}:
                text="CASE "+text+" WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END"
            node.replace(exp.Var(this=text))
        for node in list(tree.find_all(exp.Is)):
            flag=empty_flag(node.this)
            if flag is not None and isinstance(node.expression,exp.Null):
                node.replace(exp.Paren(this=exp.and_(node.copy(),exp.NEQ(this=flag,expression=exp.Literal.number(1)))))
        empty_parameters={name for name,value,_ in binds if value==''}
        def is_empty(expression):
            return ((isinstance(expression,exp.Literal) and expression.is_string and expression.this=='') or
                    isinstance(expression,exp.Placeholder) and expression.this in empty_parameters)
        for node in list(tree.find_all(exp.NEQ)):
            if is_empty(node.expression):
                node.replace(exp.Not(this=exp.Is(this=node.this.copy(),expression=exp.Null())))
        for node in list(tree.find_all(exp.EQ)):
            if is_empty(node.expression):
                flag=empty_flag(node.this)
                node.replace(exp.EQ(this=flag,expression=exp.Literal.number(1)) if flag is not None else exp.false())
            elif (isinstance(node.this,exp.Column) and
                  isinstance(node.expression,(exp.Placeholder,exp.Literal)) and
                  (column_schemas.get(node.this.table,{}).get(node.this.name,{}).get('max_bytes',0)>4000 or
                   isinstance(node.expression,exp.Placeholder) and
                   any(n==node.expression.this and t=='CLOB' for n,v,t in binds) or
                   isinstance(node.expression,exp.Literal) and node.expression.is_string and
                   len(node.expression.this.encode())>4000)):
                # Candidate hashes never replace exact logical equality. Oracle
                # requires LOB comparison when the original column is a CLOB.
                original = node.expression.copy()
                if isinstance(original,exp.Literal) and original.is_string:
                    name = 'a8_exact_lob'+str(len(binds))
                    binds.append((name,original.this,'CLOB'))
                    original = exp.Placeholder(this=name)
                node.replace(exp.EQ(this=exp.Anonymous(this='DBMS_LOB.COMPARE',
                    expressions=[node.this.copy(),original]),expression=exp.Literal.number(0)))
        for node in list(tree.find_all(exp.Anonymous)):
            if node.name.lower()=='legal_normalized':
                args=node.expressions
                if len(args)!=1 or not isinstance(args[0],exp.Column) or args[0].name!='text' or self.asset!='oracle-source':
                    raise DPError('QUERY_SQL_FUNCTION: unsupported normalization expression')
                node.replace(exp.column('a8_normalized_text',table=args[0].table))
        if isinstance(tree,exp.Select) and not tree.args.get('order') and not tree.args.get('group') and not any(n.find(exp.AggFunc) for n in tree.expressions):
            if tree.args.get('distinct'):
                tree=tree.order_by(*(p.this.copy() if isinstance(p,exp.Alias) else p.copy() for p in tree.expressions))
            elif root_tables:
                tree=tree.order_by(*(exp.column('a8_row_id',table=alias) for alias in root_tables))
        # Stable positional aliases avoid Oracle changing expression-column
        # names. JSON_ARRAY retains strings, numeric types and JSON text values.
        for i,projection in enumerate(list(tree.selects)):
            expression=projection.this.copy() if isinstance(projection,exp.Alias) else projection.copy()
            projection.replace(exp.alias_(expression,'a8_c'+str(i)))
        for i,flag in enumerate(output_flags):
            if flag is not None:
                tree.select(exp.alias_(flag.copy(),'a8_e'+str(i)),append=True,copy=False)
                if tree.args.get('group') is not None: tree.args['group'].append('expressions',flag.copy())
        order=tree.args.get('order')
        if order:
            for column in order.find_all(exp.Column):
                if not column.table and column.name in outputs:
                    column.set('this',exp.to_identifier('a8_c'+str(outputs.index(column.name))))
        compiled=tree.sql(dialect='oracle',identify=True,unsupported_level=sqlglot.ErrorLevel.RAISE)
        # Empty-string predicates can eliminate a placeholder entirely.
        used={m.group(1) for m in re.finditer(r':(a8_[A-Za-z0-9_]+)',compiled)}
        binds=[b for b in binds if b[0] in used]
        fields=','.join('x."a8_c'+str(i)+'"' for i in range(len(outputs)))
        empty_indexes=[i for i,flag in enumerate(output_flags) if flag is not None]
        fields+=''.join(',x."a8_e'+str(i)+'"' for i in empty_indexes)
        packed='SELECT TO_CLOB(JSON_ARRAY('+fields+' NULL ON NULL RETURNING CLOB)) AS body FROM ('+compiled+') x'
        def decoded():
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
        return Cursor(outputs,decoded())

    def _pages(self,packed,binds):
        offset,total_bytes=0,0
        while True:
            self._progress()
            page=packed+f' OFFSET {offset} ROWS FETCH NEXT 100 ROWS ONLY'
            rows=self.sql.query('SELECT p.body,DBMS_LOB.GETLENGTH(p.body) AS n FROM ('+page+') p',binds,limit=100)
            for index,row in enumerate(rows):
                body=row['BODY']
                if not isinstance(body,str) or units(body)!=row['N']:
                    body='';at=1
                    while units(body)<row['N']:
                        single=packed+f' OFFSET {offset+index} ROWS FETCH NEXT 1 ROWS ONLY'
                        part=self.sql.query('SELECT DBMS_LOB.SUBSTR(p.body,1000,:a8_lob_pos) AS piece,DBMS_LOB.GETLENGTH(p.body) AS n FROM ('+single+') p',
                            [*binds,('a8_lob_pos',at,'NUMBER')],limit=1)
                        if len(part)!=1 or part[0]['N']!=row['N'] or not part[0]['PIECE']:
                            raise DPError('QUERY_SQL_CLOB: result changed/truncated during read')
                        body+=part[0]['PIECE'];at=units(body)+1
                    if units(body)!=row['N']:
                        raise DPError('QUERY_SQL_CLOB: inconsistent result length')
                total_bytes+=len(body.encode())
                if total_bytes>64*1024*1024 or offset+index>=10000:
                    raise DPError('QUERY_SQL_RESULT_BUDGET: use bounded consumer pages')
                yield json.loads(body)
            if len(rows)<100:
                return
            offset+=len(rows)
