"""The existing bounded glossary API over Oracle tables and FTS positions."""
import hashlib
import json
import re

from .full_glossary import Glossary as Base, encoded, norm, sha
from .full_glossary_connections import ConnectionReader
from .oracle_dp_io import DPError, digest
from .oracle_query_catalog import ROW
from .oracle_query_db import Connection
from .oracle_query_fulltext import query_phrases


class Glossary(Base):
    def __init__(self,request,config):
        self.request=request
        binding=request.snapshot.manifest.get('glossary') or config.get('glossary') or {}
        metadata=request.records.manifest.get('metadata',{})
        def descriptor(path,expected=None):
            item=metadata.get(path)
            if not item or (expected is not None and item['sha256']!=expected):
                raise DPError('QUERY_GLOSSARY_BINDING: missing/mismatched metadata '+path)
            return item['value']
        bundle=binding['bundle']
        manifest=descriptor(bundle+'/manifest.json',binding['manifest_sha256'])
        receipt=descriptor(binding['cache']+'/'+binding['cache_receipt'],binding['cache_receipt_sha256'])
        self.binding=receipt['binding']
        from . import full_glossary
        expected={'manifest_sha256':binding['manifest_sha256'],'dictionary_sha256':manifest['dictionary_sha256'],
                  'compiler_sha256':sha(full_glossary.__file__)}
        if self.binding!=expected:
            raise DPError('QUERY_GLOSSARY_BINDING: source/compiler cache binding differs')
        cache_key=hashlib.sha256(encoded(self.binding).encode()).hexdigest()
        lookup=binding['cache']+'/'+cache_key+'.sqlite'
        graph='nodes.sqlite' if manifest['schema_version']=='glossary-serving-v2' else 'graph.sqlite'
        assets={'graph':bundle+'/'+graph,'translations':bundle+'/translations.sqlite',
                'identity':bundle+'/identity.sqlite','dictionary':binding['dictionary'],'lookup':lookup}
        pins={row['path']:row['sha256'] for row in manifest['files']}
        for name,path in assets.items():
            expected_sha=(receipt['sha256'] if name=='lookup' else manifest['dictionary_sha256'] if name=='dictionary'
                          else pins[path[len(bundle)+1:]])
            if request.records.manifest['assets'].get(path)!=expected_sha:
                raise DPError('QUERY_GLOSSARY_BINDING: projected asset differs '+name)
        self.dbs={name:Connection(request,path) for name,path in assets.items()}
        self.known={}
        self.connections=ConnectionReader(self.dbs,self.card)
        self.span_reader=None
        self._lookup_prefix='asset_'+digest(lookup)[:12]+'.'

    def check_unchanged(self):
        if digest(self.request.records.manifest)!=self.request.release_id:
            raise DPError('QUERY_RELEASE_BINDING: glossary query manifest changed')

    def lookup(self,label,*,limit=8,offset=0):
        self.check_unchanged();self.page(limit,offset)
        if not isinstance(label,str) or not 2<=len(label.strip())<=120:
            raise ValueError('label length must be 2..120')
        db=self.dbs['lookup'];key=norm(label)
        total=db.execute('SELECT COUNT(*) FROM (SELECT DISTINCT source,node_id FROM label WHERE key=?)',(key,)).fetchone()[0]
        if total:
            # Parent implements exact ordering and card contracts unchanged.
            return super().lookup(label,limit=limit,offset=offset)
        words=re.findall(r'\w+',label)[:8]
        tokens=list(dict.fromkeys(t for phrase in query_phrases(words) for t in phrase))
        if not tokens:
            return {'label':label,'concepts':[],'total':0,'next_offset':None}
        kinds=self.request.records.manifest['tables']
        posting,content=self._lookup_prefix+'words_posting',self._lookup_prefix+'words_content'
        if posting not in kinds or content not in kinds:
            raise DPError('QUERY_GLOSSARY_FTS: publish glossary token positions and row identities')
        binds=[('g_release',self.request.release_id,'VARCHAR2'),('g_posting',posting,'VARCHAR2'),('g_content',content,'VARCHAR2')]
        binds += [('g_token'+str(i),v,'VARCHAR2') for i,v in enumerate(tokens)]
        matches=(f'SELECT OWNER_ID FROM {ROW} WHERE RELEASE_ID=:g_release AND KIND=:g_posting AND LOOKUP_ID IN ('+
                 ','.join(':g_token'+str(i) for i in range(len(tokens)))+') GROUP BY OWNER_ID HAVING COUNT(DISTINCT LOOKUP_ID)='+str(len(tokens)))
        pairs=(f"SELECT DISTINCT j.src,j.node FROM {ROW} r,JSON_TABLE(r.VALUE_JSON,'$' COLUMNS(src VARCHAR2(512) PATH '$.source',node VARCHAR2(512) PATH '$.node_id')) j "
               'WHERE r.RELEASE_ID=:g_release AND r.KIND=:g_content AND r.LOOKUP_ID IN ('+matches+')')
        ranked='SELECT src,node,ROW_NUMBER() OVER(PARTITION BY src ORDER BY node) AS n,COUNT(*) OVER() AS total FROM ('+pairs+')'
        rows=self.request.sql.query('SELECT * FROM ('+ranked+') ORDER BY n,src,node OFFSET '+str(offset)+' ROWS FETCH NEXT '+str(limit)+' ROWS ONLY',binds,limit=limit)
        if rows:
            total=rows[0]['TOTAL']
        elif offset:
            total=self.request.sql.query('SELECT COUNT(*) AS n FROM ('+pairs+')',binds,limit=1)[0]['N']
        else:
            total=0
        return {'label':label,'concepts':[self.card(r['SRC'],r['NODE'],match='LABEL_TOKEN_CANDIDATE') for r in rows],
                'total':total,'next_offset':offset+len(rows) if offset+len(rows)<total else None}
