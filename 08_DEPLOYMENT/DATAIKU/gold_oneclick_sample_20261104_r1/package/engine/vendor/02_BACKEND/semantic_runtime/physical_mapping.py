"""Explicit physical identifiers for Oracle ingestion; payload keys never change."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType

import yaml

VERSION = 'legal-oracle-map-v1'
TABLE_KEYS = {'document','source_unit','block_payload','source_release','asset_part',
              'query_row','query_release','query_active','query_state'}
ROLES = {'gold_knowledge','gold_support','agent','transfer_archive'}
TYPES = {'VARCHAR2(64 BYTE)','VARCHAR2(128 BYTE)','VARCHAR2(512 BYTE)','CLOB',
         'NUMBER(1)','NUMBER(12)','NUMBER(18)','TIMESTAMP WITH TIME ZONE'}
CONTRACT_COLUMNS = {
    'document': 'DATASET_VERSION DOCUMENT_ID NAME SOURCE_ARTIFACT_SHA256 SOURCE_JSON',
    'source_unit': 'DATASET_VERSION DOCUMENT_ID UNIT_ID PARENT_ID SOURCE_JSON',
    'block_payload': 'DATASET_VERSION DOCUMENT_ID BLOCK_ID UNIT_ID TEXT SOURCE_ARTIFACT_SHA256 SOURCE_JSON JSON_TEXT_ELIDED',
    'asset_part': 'ASSET_SHA256 PART_NO RAW_BYTES PART_SHA256 DATA_B64',
    'source_release': 'RELEASE_ID DATASET_VERSION RELEASE_JSON CREATED_AT',
    'query_release': 'RELEASE_ID MANIFEST_JSON',
    'query_row': 'RELEASE_ID KIND ROW_ID DOCUMENT_ID LOOKUP_ID OWNER_ID TARGET_ID ROW_SHA256 VALUE_JSON',
    'query_active': 'CHANNEL RELEASE_ID REVISION',
    'query_state': 'SCOPE_HASH STATE_KEY REVISION VALUE_SHA256 VALUE_JSON',
}


class MappingError(ValueError):
    pass


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',value):
        raise MappingError('MAP_IDENTIFIER: uppercase identifier of at most 30 bytes required')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


class UniqueLoader(yaml.SafeLoader):
    pass


def unique(loader,node,deep=False):
    out={}
    for k,v in node.value:
        key=loader.construct_object(k,deep=deep)
        if not isinstance(key,str) or key in out:
            raise MappingError('MAP_KEYS: duplicate or non-string key')
        out[key]=loader.construct_object(v,deep=deep)
    return out


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,unique)


def exact(value,keys,where):
    if not isinstance(value,dict) or set(value)!=set(keys):
        raise MappingError('MAP_FIELDS: '+where)


@dataclass(frozen=True)
class Names:
    table: str
    columns: object = None

    def c(self,name):
        identifier(name)
        return name if self.columns is None else self.columns[name]

    def select(self,*columns):
        return ','.join(self.c(c) if self.c(c)==c else self.c(c)+' AS '+c for c in columns)


def names(sql,key,legacy):
    schema=getattr(getattr(sql,'client',sql),'schema_map',None)
    return schema.names(key) if schema else Names(legacy)


def _freeze(value):
    if isinstance(value,dict):return MappingProxyType({k:_freeze(v) for k,v in value.items()})
    if isinstance(value,list):return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class SchemaMap:
    tables: object
    owners: object
    profile: str
    execution_sha256: str
    target_sha256: str
    file_sha256: str

    @classmethod
    def load(cls,path,*,profile='dev_silver',expected_sha256=None):
        raw=Path(path).read_bytes()
        if len(raw)>1024*1024:raise MappingError('MAP_SIZE')
        sha=hashlib.sha256(raw).hexdigest()
        if expected_sha256 and sha!=expected_sha256:raise MappingError('MAP_FILE_HASH')
        value=yaml.load(raw,Loader=UniqueLoader)
        exact(value,{'schema_version','revision','profiles','tables'},'root')
        if value['schema_version']!=VERSION:raise MappingError('MAP_VERSION')
        if set(value['tables'])!=TABLE_KEYS:raise MappingError('MAP_TABLE_SET')
        if not isinstance(value['profiles'],dict) or profile not in value['profiles']:raise MappingError('MAP_PROFILE')
        p=value['profiles'][profile]
        exact(p,{'enabled','owner_by_role'},'profile')
        if p['enabled'] is not True:raise MappingError('MAP_PROFILE_DISABLED')
        exact(p['owner_by_role'],ROLES,'owners')
        owners={role:identifier(owner) for role,owner in p['owner_by_role'].items()}
        object_names=set();constraint_names=set();index_names=set()
        for key,t in value['tables'].items():
            exact(t,{'name','role','columns','pk','pk_name','indexes','checks','foreign_keys','description'},key)
            if t['role'] not in ROLES:raise MappingError('MAP_ROLE')
            qualified=(owners[t['role']],identifier(t['name']))
            if qualified in object_names:raise MappingError('MAP_TABLE_COLLISION')
            object_names.add(qualified)
            identifier(t['pk_name'])
            if not isinstance(t['columns'],dict) or set(t['columns'])!=set(CONTRACT_COLUMNS[key].split()):
                raise MappingError('MAP_LOGICAL_COLUMNS: '+key)
            cols=set()
            for old,c in t['columns'].items():
                identifier(old)
                exact(c,{'name','type','nullable','default','description'},key+'.'+old)
                new=identifier(c['name'])
                if new in cols:raise MappingError('MAP_COLUMN_COLLISION')
                cols.add(new)
                if c['type'] not in TYPES or type(c['nullable']) is not bool:raise MappingError('MAP_COLUMN_TYPE')
                if c['default'] not in (None,'SYSTIMESTAMP'):raise MappingError('MAP_DEFAULT')
            if not t['pk'] or len(set(t['pk']))!=len(t['pk']) or not set(t['pk'])<=t['columns'].keys():raise MappingError('MAP_PK')
            if any(t['columns'][c]['nullable'] for c in t['pk']):raise MappingError('MAP_PK_NULL')
            for i in t['indexes']:
                exact(i,{'name','columns'},'index');identifier(i['name'])
                if not i['columns'] or not set(i['columns'])<=t['columns'].keys():raise MappingError('MAP_INDEX')
            for c in t['checks']:
                exact(c,{'name','kind','columns'},'check');identifier(c['name'])
                if c['kind'] not in {'is_json','revision','part_bounds'} or not set(c['columns'])<=t['columns'].keys():raise MappingError('MAP_CHECK')
            for f in t['foreign_keys']:
                exact(f,{'name','columns','target','target_columns'},'fk');identifier(f['name'])
                if f['target'] not in value['tables'] or len(f['columns'])!=len(f['target_columns']):raise MappingError('MAP_FK')
                if not set(f['columns'])<=t['columns'].keys() or not set(f['target_columns'])<=value['tables'][f['target']]['columns'].keys():raise MappingError('MAP_FK_COLUMNS')
                if f['target_columns']!=value['tables'][f['target']]['pk']:raise MappingError('MAP_FK_TARGET_KEY')
            for name in [t['pk_name'],*[c['name'] for c in t['checks']],*[f['name'] for f in t['foreign_keys']]]:
                qualified=(owners[t['role']],name)
                if qualified in constraint_names:raise MappingError('MAP_CONSTRAINT_COLLISION')
                constraint_names.add(qualified)
            for name in [t['pk_name'],*[i['name'] for i in t['indexes']]]:
                qualified=(owners[t['role']],name)
                if qualified in index_names:raise MappingError('MAP_INDEX_COLLISION')
                index_names.add(qualified)
        # Description edits have a file hash, but do not change execution/target identities.
        execution=json.loads(json.dumps(value['tables']))
        for t in execution.values():
            t.pop('description')
            for c in t['columns'].values():c.pop('description')
        h=digest({'schema_version':VERSION,'tables':execution})
        result=cls(_freeze(value['tables']),_freeze(owners),profile,h,
                   digest({'map':h,'profile':profile,'owners':owners}),sha)
        for key,t in result.tables.items():
            for check in t['checks']:result.check_expression(key,check)
        return result

    def names(self,key):
        t=self.tables[key]
        return Names(self.owners[t['role']]+'.'+t['name'],
                     MappingProxyType({old:c['name'] for old,c in t['columns'].items()}))

    def binding(self,database_binding):
        return digest({'database_binding':database_binding,'physical_target':self.target_sha256})

    def check_expression(self,key,check):
        n=self.names(key);cs=[n.c(c) for c in check['columns']]
        if check['kind']=='is_json' and len(cs)==1:return cs[0]+' IS JSON'
        if check['kind']=='revision' and len(cs)==1:return cs[0]+'>=1'
        if check['kind']=='part_bounds' and len(cs)==2:return f'{cs[0]}>=0 AND {cs[1]}>0 AND {cs[1]}<=1048576'
        raise MappingError('MAP_CHECK_SHAPE')

    def ddl(self):
        result=[]
        order=['document','source_unit','block_payload','asset_part','source_release','query_release','query_row','query_active','query_state']
        for key in order:
            t=self.tables[key];n=self.names(key)
            fields=[n.c(old)+' '+c['type']+(' DEFAULT '+c['default'] if c['default'] else '')+(' NOT NULL' if not c['nullable'] else '') for old,c in t['columns'].items()]
            fields.append('CONSTRAINT '+t['pk_name']+' PRIMARY KEY ('+','.join(n.c(c) for c in t['pk'])+')')
            for c in t['checks']:fields.append('CONSTRAINT '+c['name']+' CHECK ('+self.check_expression(key,c)+')')
            for f in t['foreign_keys']:
                target=self.names(f['target'])
                fields.append('CONSTRAINT '+f['name']+' FOREIGN KEY ('+','.join(n.c(c) for c in f['columns'])+') REFERENCES '+target.table+' ('+','.join(target.c(c) for c in f['target_columns'])+')')
            result.append(('TABLE',key,t['name'],'CREATE TABLE '+n.table+' (\n    '+',\n    '.join(fields)+'\n)'))
        for key,t in self.tables.items():
            n=self.names(key)
            for i in t['indexes']:
                result.append(('INDEX',key,i['name'],'CREATE INDEX '+self.owners[t['role']]+'.'+i['name']+' ON '+n.table+' ('+','.join(n.c(c) for c in i['columns'])+')'))
        return result

    def preflight(self,sql,keys=None):
        """Read the actual physical schema; never relabel dictionary rows as legacy names."""
        selected=list(keys or self.tables)
        for key in selected:
            t=self.tables[key];n=self.names(key);owner=self.owners[t['role']]
            binds=[('o',owner,'VARCHAR2'),('t',t['name'],'VARCHAR2')]
            rows=sql.query('SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,DATA_PRECISION,DATA_SCALE,NULLABLE,DATA_DEFAULT FROM ALL_TAB_COLUMNS WHERE OWNER=:o AND TABLE_NAME=:t',binds,limit=100)
            found={r['COLUMN_NAME']:r for r in rows}
            if set(found)!={c['name'] for c in t['columns'].values()}:raise MappingError('TARGET_COLUMNS: '+n.table)
            for c in t['columns'].values():
                r=found[c['name']];typ=c['type'];ok=False
                if typ.startswith('VARCHAR2'):
                    size=int(re.search(r'\((\d+)',typ).group(1));ok=r['DATA_TYPE']=='VARCHAR2' and r['DATA_LENGTH']==size and r['CHAR_USED']=='B'
                elif typ.startswith('NUMBER'):
                    size=int(re.search(r'\((\d+)',typ).group(1));ok=r['DATA_TYPE']=='NUMBER' and r['DATA_PRECISION']==size and r['DATA_SCALE']==0
                elif typ=='CLOB':ok=r['DATA_TYPE']=='CLOB'
                else:ok=r['DATA_TYPE'] in {'TIMESTAMP(6) WITH TIME ZONE','TIMESTAMP WITH TIME ZONE'}
                default=(r.get('DATA_DEFAULT') or '').strip().upper()
                if not ok or r['NULLABLE']!=('Y' if c['nullable'] else 'N') or default!=(c['default'] or ''):raise MappingError('TARGET_TYPE: '+n.table+'.'+c['name'])
            constraints=sql.query('SELECT CONSTRAINT_NAME,CONSTRAINT_TYPE,STATUS,VALIDATED,R_OWNER,R_CONSTRAINT_NAME,SEARCH_CONDITION_VC FROM ALL_CONSTRAINTS WHERE OWNER=:o AND TABLE_NAME=:t',binds,limit=100)
            byname={r['CONSTRAINT_NAME']:r for r in constraints}
            def columns(name):
                return [r['COLUMN_NAME'] for r in sql.query('SELECT COLUMN_NAME FROM ALL_CONS_COLUMNS WHERE OWNER=:o AND CONSTRAINT_NAME=:c ORDER BY POSITION',[('o',owner,'VARCHAR2'),('c',name,'VARCHAR2')],limit=100)]
            def constraint(name,kind):
                r=byname.get(name)
                if not r or (r['CONSTRAINT_TYPE'],r['STATUS'],r['VALIDATED'])!=(kind,'ENABLED','VALIDATED'):raise MappingError('TARGET_CONSTRAINT: '+n.table+'.'+name)
                return r
            constraint(t['pk_name'],'P')
            if columns(t['pk_name'])!=[n.c(c) for c in t['pk']]:raise MappingError('TARGET_PK: '+n.table)
            normalize=lambda s:re.sub(r'[\s"()]','',s or '').upper()
            for c in t['checks']:
                r=constraint(c['name'],'C')
                if normalize(r['SEARCH_CONDITION_VC'])!=normalize(self.check_expression(key,c)):raise MappingError('TARGET_CHECK: '+c['name'])
            for f in t['foreign_keys']:
                r=constraint(f['name'],'R');target=self.tables[f['target']]
                if (r['R_OWNER'],r['R_CONSTRAINT_NAME'])!=(self.owners[target['role']],target['pk_name']) or columns(f['name'])!=[n.c(c) for c in f['columns']]:raise MappingError('TARGET_FK: '+f['name'])
            for i in t['indexes']:
                ib=[('o',owner,'VARCHAR2'),('i',i['name'],'VARCHAR2')]
                info=sql.query('SELECT TABLE_OWNER,TABLE_NAME,STATUS,UNIQUENESS FROM ALL_INDEXES WHERE OWNER=:o AND INDEX_NAME=:i',ib,limit=1)
                cols=sql.query('SELECT COLUMN_NAME FROM ALL_IND_COLUMNS WHERE INDEX_OWNER=:o AND INDEX_NAME=:i ORDER BY COLUMN_POSITION',ib,limit=100)
                if info!=[{'TABLE_OWNER':owner,'TABLE_NAME':t['name'],'STATUS':'VALID','UNIQUENESS':'NONUNIQUE'}] or [r['COLUMN_NAME'] for r in cols]!=[n.c(c) for c in i['columns']]:raise MappingError('TARGET_INDEX: '+i['name'])
        return {'status':'READY','tables':len(selected),'target_map_sha256':self.target_sha256}
