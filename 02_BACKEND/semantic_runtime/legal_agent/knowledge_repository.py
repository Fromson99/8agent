"""Shortcut and legal_wiki read the same current experience authority."""
import json
from .corrected_memory import MemoryError, digest


class KnowledgeRepository:
    def __init__(self,cases):self.cases=cases

    def get(self,experience_id,principal):
        k=self.cases.checked_knowledge(experience_id,principal)
        g=self.cases.db.execute('SELECT * FROM goal WHERE id=?',(k['bundle'],)).fetchone()
        if (not g or g['status']!='READY' or json.loads(g['state'])!=k['payload']['state'] or
                self.cases.parts(g['id'])['ASSESS']['id']!=k['payload']['nodes']['ASSESS']):
            raise MemoryError('experience no longer matches the current judgment')
        route=self.cases.route(g['id'])
        if not route or route['payload']['binding']!=self.cases.executor.binding:raise MemoryError('experience route is drifted')
        return k

    def questions(self,principal,query='',*,after='',limit=32,public_only=False):
        rows=[];limit=max(1,min(limit,100))
        for r in self.cases.db.execute('''SELECT g.*,s.owner,s.team,e.public_only FROM goal g
          JOIN session s ON s.id=g.session LEFT JOIN session_export e ON e.session_id=s.id
          WHERE s.owner=? AND s.team=? AND g.id>? ORDER BY g.id''',(principal['user_id'],principal['team_id'],after)):
            state=json.loads(r['state'])
            if not set(state['document_ids'])<=set(principal['document_ids']) or (public_only and not r['public_only']):continue
            if query and query.casefold() not in state['task'].casefold():continue
            rows.append({'question_id':r['id'],'session_id':r['session'],'ordinal':r['ordinal'],
                'revision':r['revision'],'status':r['status'],'task':state['task'],
                'confirmed':self.cases.db.execute("SELECT 1 FROM knowledge WHERE bundle=? AND status='ACTIVE'",(r['id'],)).fetchone() is not None})
            if len(rows)>limit:break
        return {'questions':rows[:limit],'next':rows[limit-1]['question_id'] if len(rows)>limit else None}

    def search(self,principal,query='',*,after='',limit=32):
        # A page limit is for display only. Exact ID lookup never uses this list.
        limit=max(1,min(limit,100));rows=[]
        for r in self.cases.db.execute("SELECT id FROM knowledge WHERE owner=? AND team=? AND status='ACTIVE' AND id>? ORDER BY id",
                (principal['user_id'],principal['team_id'],after)):
            try:k=self.get(r['id'],principal)
            except MemoryError:continue
            p=k['payload']
            if query and not any(query.casefold() in str(x).casefold() for x in [p['state']['task'],*p['concepts']]):continue
            rows.append(self.page(k))
            if len(rows)>limit:break
        return {'experiences':rows[:limit],'next':rows[limit-1]['experience_id'] if len(rows)>limit else None}

    def page(self,k):
        p=k['payload']
        return {'experience_id':k['id'],'experience_revision':k['revision'],'experience_hash':k['hash'],
            'question_id':k['bundle'],'conditions':p['state'],'binding':p['binding'],
            'judgment_refs':p['judgment_refs'],'concepts':p['concepts'],'approval':p['approval'],
            'judgment':p['parts']['ASSESS']['payload'],
            'read_source_ids':[s['source_id'] for s in p['parts']['READ']['payload']['originals']],
            'adopted_source_ids':p['parts']['SELECT']['payload']['final_ids'],
            'cited_source_ids':sorted({c['source_id'] for c in p['parts']['ASSESS']['payload']['claims']})}

    def wiki(self,kind,principal,**options):
        if kind!='legal_wiki':raise MemoryError('unknown wiki')
        data=self.search(principal,**options)
        pages=data.pop('experiences')
        return {'schema_version':'unified-experience-wiki-v1','kind':kind,'owner':principal['user_id'],
                'team':principal['team_id'],'pages':pages,**data}

    def rebuild(self,principal,directory):
        """Derived files can be deleted. Readers still check the live authority."""
        from pathlib import Path
        from .core_evidence_route import enabled
        if enabled(self.cases):
            from lawrag.pipeline.legal_wiki_compiler import rebuild
            return {'legal_wiki':rebuild(self.cases.shortcut,principal,Path(directory)/'legal_wiki')}
        from lawrag.pipeline.legal_llm_wiki import write
        directory=Path(directory)/digest([principal['user_id'],principal['team_id']])
        snapshots={}
        for kind in ('legal_wiki',):
            pages=[];after=''
            while True:
                projection=self.wiki(kind,principal,after=after,limit=100)
                pages.extend(projection['pages'])
                if projection['next'] is None:break
                after=projection['next']
            snapshot={**projection,'pages':pages,'next':None}
            write(directory/kind/'index.json',json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n')
            lines=['# '+kind,'','확정된 해결 경험. 현재 범위·상태·근거는 조회 시 정본에서 확인합니다.','']
            for p in pages:
                lines.extend(['## '+p['experience_id'],p['conditions']['task'],
                    'Experience revision: '+str(p['experience_revision']),
                    'Experience hash: '+p['experience_hash'],
                    json.dumps(p['judgment'],ensure_ascii=False),''])
            write(directory/kind/'index.md','\n'.join(lines)+'\n')
            snapshots[kind]=digest(snapshot)
        # Mark only committed experience events for this owner; unrelated users stay pending.
        with self.cases.transaction():
            for r in self.cases.db.execute("SELECT id,payload,hash FROM outbox WHERE kind='EXPERIENCE_CONFIRMED' AND status='PENDING'"):
                payload=json.loads(r['payload'])
                if digest(payload)!=r['hash']:raise MemoryError('outbox corrupt')
                if (payload['owner'],payload['team'])==(principal['user_id'],principal['team_id']):
                    self.cases.db.execute("UPDATE outbox SET status='PROJECTED' WHERE id=?",(r['id'],))
        return snapshots
