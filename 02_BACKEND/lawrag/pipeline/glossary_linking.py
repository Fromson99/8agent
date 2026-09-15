"""Connect a versioned glossary to newly structured documents.

No source recollection, model calls, canonical merging, or runtime activation.
The structure cache stays immutable; linked source inputs are derived copies.
"""
from contextlib import closing, nullcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from . import glossary_assembly as assembly,glossary_definitions as definitions,glossary_v1 as v1
from .glossary_alignment import Matcher
from .collect_moleg_knowledge import _atomic_json

VERSION='glossary-structure-links-v2'


def configured(root, data):
    config=Path(root)/'00_SYSTEM/GLOSSARY_PIPELINE.json'
    settings=json.loads(config.read_text());data=Path(data).resolve()
    def data_location(value):
        if value['root_id']!='data':raise ValueError('Glossary config must use data root')
        relative=Path(value['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid glossary relative path')
        path=(data/relative).resolve()
        if not path.is_relative_to(data):raise ValueError('Glossary path escapes data root')
        return path
    base=data_location(settings['current_draft'])
    selection=settings.get('llm_review',{}).get('current_review_state')
    if not selection:return base
    state=data_location(selection);receipt_path=state/'completion.json'
    if not receipt_path.exists():return base
    receipt=json.loads(receipt_path.read_text())
    if receipt.get('schema_version')!='glossary-review-completion-v1' or receipt.get('completed') is not True:
        raise ValueError('Invalid glossary completion receipt')
    relative=Path(receipt['output_relative_to_state'])
    if relative.is_absolute():raise ValueError('Completion output must be relocatable')
    output=(state/relative).resolve()
    if not output.is_relative_to(data):raise ValueError('Reviewed glossary escapes data root')
    if assembly.inspect(base)['dictionary_sha256']!=receipt['source_glossary_sha256']:
        raise ValueError('Completed review belongs to another base glossary')
    report=assembly.inspect(output)
    if (report['dictionary_sha256']!=receipt['dictionary_sha256']
            or report.get('llm_review',{}).get('source_glossary_sha256')!=receipt['source_glossary_sha256']
            or report.get('llm_review',{}).get('state_sha256')!=receipt['state_sha256']):
        raise ValueError('Completed glossary/receipt binding mismatch')
    return output


def binding(directory):
    directory=Path(directory).resolve()
    report=assembly.inspect(directory)
    if report['schema_version']!=assembly.VERSION:raise ValueError('Use the current glossary assembly format')
    from . import glossary_knowledge
    knowledge=glossary_knowledge.selected_for(directory)
    knowledge_binding=glossary_knowledge.binding(knowledge) if knowledge else None
    if knowledge_binding and report['dictionary_sha256']!=knowledge_binding['dictionary_sha256'] and report.get('llm_review',{}).get('source_glossary_sha256')!=knowledge_binding['dictionary_sha256']:
        raise ValueError('Knowledge bundle belongs to another base glossary')
    return {'directory':str(directory),'dictionary_sha256':report['dictionary_sha256'],
            'schema_version':VERSION,'code_sha256':v1.sha(__file__),
            'definition_code_sha256':v1.sha(definitions.__file__),
            'matcher_sha256':v1.sha(Path(__file__).with_name('glossary_alignment.py')),
            'sense_review':report.get('sense_review'),
            'review_contract':report.get('schema_extensions',{}).get('glossary_review'),
            'knowledge':knowledge_binding}


def _candidates(glossary, linked, key, did):
    # A definition from another corpus document is not this document's definition.
    result=[]
    for row in glossary.execute("SELECT DISTINCT e.* FROM surface s JOIN entry e ON e.id=s.entry_id WHERE s.key=? AND e.source!='corpus_definition' ORDER BY e.id",(key,)):
        result.append({'entry_id':row['id'],'label':row['label'],'source':row['source'],
                       'definition':row['definition'][:1200],
                       'definition_truncated':len(row['definition'])>1200,
                       'match_kind':'LABEL_CANDIDATE','sense_applicability':'UNREVIEWED'})
    for row in linked.execute('SELECT e.*,d.scope_status,d.scope_hint,d.location,d.definition_status FROM entry e JOIN corpus_definition d ON d.id=e.id WHERE d.key=? AND d.document_id=? ORDER BY e.id',(key,did)):
        result.insert(0,{'entry_id':row['id'],'label':row['label'],'source':row['source'],
                         'definition':row['definition'][:1200],
                         'definition_truncated':len(row['definition'])>1200,
                         'definition_status':row['definition_status'],'document_id':did,
                         'scope_status':row['scope_status'],'scope_hints':json.loads(row['scope_hint']),
                         'location':json.loads(row['location']),'match_kind':'DOCUMENT_DEFINITION_CANDIDATE',
                         'sense_applicability':'UNREVIEWED'})
    total=len(result);selected=result[:6]
    for item in selected:
        if item['source']=='moleg':
            rows=glossary.execute('''SELECT d.id,d.text,d.payload,c.match_kind FROM definition_candidate c
                JOIN definition_record d ON d.id=c.definition_id WHERE c.entry_id=?
                AND d.content_type='EXPLANATION' ORDER BY d.id''',(item['entry_id'],)).fetchall()
            item['source_definitions']=[{'id':r['id'],'text':r['text'][:1200],
                'truncated':len(r['text'])>1200,'match_kind':r['match_kind'],
                'source_fields':json.loads(r['payload']).get('fields',{})} for r in rows[:4]]
            item['source_definitions_total']=len(rows)
    return {'candidates':selected,'total':total,'truncated':total>len(selected),'canonical_approval':False}


def project(source, directory, output):
    source,directory,output=map(lambda p:Path(p).resolve(),(source,directory,output))
    identity={'source_sha256':v1.sha(source),'glossary':binding(directory)}
    if output.exists():
        report=json.loads((output/'report.json').read_text())
        if report['identity']!=identity:raise ValueError('Glossary/source changed; use a new link output')
        if any(v1.sha(output/name)!=value for name,value in report['files'].items()):
            raise ValueError('Glossary linkage output hash mismatch')
        return output/'source.sqlite',report
    output.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    shutil.copyfile(source,temp/'source.sqlite')
    from . import glossary_knowledge
    knowledge_path=glossary_knowledge.selected_for(directory)
    with (closing(glossary_knowledge.Knowledge(knowledge_path)) if knowledge_path else nullcontext(None)) as knowledge, closing(v1.read_db(directory/'dictionary.sqlite')) as glossary,closing(v1.read_db(source)) as original,closing(sqlite3.connect(temp/'links.sqlite')) as links,closing(sqlite3.connect(temp/'source.sqlite')) as target:
        links.row_factory=sqlite3.Row
        v1.create_tables(links);definitions.tables(links)
        links.execute('CREATE INDEX occurrence_block ON occurrence(document_id,block_id)')
        definitions.add(links,original,identity['source_sha256'])
        keys={r[0] for r in glossary.execute('SELECT DISTINCT key FROM surface')}
        if knowledge: keys.update(knowledge.surfaces())
        keys.update(r[0] for r in links.execute('SELECT DISTINCT key FROM surface'))
        matcher=Matcher([(key,key) for key in sorted(keys)])
        for did,bid,uid,text in original.execute('SELECT document_id,block_id,unit_id,text FROM source_block ORDER BY document_id,block_id'):
            hits=list(matcher.find(text))
            links.executemany('INSERT OR IGNORE INTO occurrence VALUES (?,?,?,?,?,?)',
                [(key,did,str(bid),uid,lo,hi) for key,lo,hi,_ in hits
                 if not any(a<=lo and hi<=b and (a<lo or hi<b) for _,a,b,_ in hits)])
        # The catalogue reference and per-surface candidate IDs permit complete lookup
        # even when the LLM's bounded hints omit entries. Never erase raw occurrences.
        links.executescript('''CREATE TABLE catalogue_link(key TEXT,entry_id TEXT,
            PRIMARY KEY(key,entry_id));
            CREATE TABLE knowledge_catalogue_link(key TEXT,source TEXT,node_id TEXT,label TEXT,kind TEXT,
            PRIMARY KEY(key,source,node_id,label,kind));''')
        for key, in links.execute('SELECT DISTINCT key FROM occurrence').fetchall():
            links.executemany('INSERT OR IGNORE INTO catalogue_link VALUES (?,?)',
                [(key,r[0]) for r in glossary.execute('SELECT DISTINCT entry_id FROM surface WHERE key=?',(key,))])
            if knowledge:
                links.executemany('INSERT OR IGNORE INTO knowledge_catalogue_link VALUES (?,?,?,?,?)',
                    [(key,r['source'],r['node_id'],r['label'],r['kind']) for r in knowledge.matches(key)])
        target.commit();links.commit()
        report={'identity':identity,'occurrences':links.execute('SELECT count(*) FROM occurrence').fetchone()[0],
                'matched_surfaces':links.execute('SELECT count(DISTINCT key) FROM occurrence').fetchone()[0],
                'local_definitions':definitions.counts(links),
                'llm_calls':0,'canonical_approval':False,'runtime_promoted':False,
                'knowledge_matches':links.execute('SELECT count(*) FROM knowledge_catalogue_link').fetchone()[0]}
        for db in (links,target):
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Glossary linkage integrity failure')
    if v1.sha(source)!=identity['source_sha256'] or binding(directory)!=identity['glossary']:
        raise ValueError('Source/glossary changed while linking')
    report['files']={name:v1.sha(temp/name) for name in ('links.sqlite','source.sqlite')}
    _atomic_json(temp/'report.json',report)
    if output.exists():raise ValueError('Link output appeared during build')
    os.rename(temp,output)
    return output/'source.sqlite',report
