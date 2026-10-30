"""Persist research decisions, never answers; replay only identical live contracts.

The tools still execute on every request. A stored choice is admissible only when
the current question, authorization, source/configuration binding and complete
offered input agree. Changed contracts return to the original model checkpoint.
This is operational procedure memory, not legal approval or semantic equivalence.
"""
import json
from .corrected_memory import digest, encoded, MemoryError


class ProcedureMemory:
    VERSION = 'research-procedure-v1'

    def __init__(self, db, principal, binding, request, emit):
        self.db, self.request, self.emit = db, request, emit
        self.workspace=principal['team_id']
        self.scope = digest([principal['user_id'], principal['team_id'],
                             sorted(principal['document_ids'])])
        self.binding = {'contract': self.VERSION, **binding}
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS sw_procedure_step(
            id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL,
            phase TEXT NOT NULL, question TEXT NOT NULL, binding TEXT NOT NULL,
            input_hash TEXT NOT NULL, input_json TEXT NOT NULL, output_json TEXT NOT NULL,
            output_hash TEXT NOT NULL, request TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sw_procedure_activation(
            step INTEGER PRIMARY KEY REFERENCES sw_procedure_step(id), request TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sw_procedure_event(
            id INTEGER PRIMARY KEY AUTOINCREMENT, request TEXT NOT NULL,
            scope TEXT NOT NULL, phase TEXT NOT NULL, payload TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS sw_procedure_lookup
            ON sw_procedure_step(scope,phase,question,id);
        ''')

    def event(self, phase, payload):
        value={'phase':phase,'request':self.request,**payload}
        self.db.execute('INSERT INTO sw_procedure_event(request,scope,phase,payload) VALUES(?,?,?,?)',
                        (self.request,self.scope,phase,encoded(value)))
        self.emit('PROCEDURE_CHECKPOINT',value)
        return value

    def lookup(self, phase, question, data):
        # Exact question matching is intentional: no fuzzy semantic permission.
        from ..ad_store import features
        if not features(self.db,self.workspace)['shortcut']:
            return None,{'status':'DISABLED','reason':'SHORTCUT_OFF'}
        rows=self.db.execute('''SELECT s.* FROM sw_procedure_step s
          JOIN sw_procedure_activation a ON a.step=s.id
          WHERE s.scope=? AND s.phase=? AND s.question=? ORDER BY s.id DESC''',
          (self.scope,phase,question)).fetchall()
        actual=digest(data); binding=digest(self.binding)
        for row in rows:
            r=dict(row)
            from ..ad_store import excluded
            if excluded(self.db,'procedure',str(r['id'])):continue
            if digest(json.loads(r['input_json']))!=r['input_hash'] or digest(json.loads(r['output_json']))!=r['output_hash']:
                raise MemoryError('procedure record corrupt')
            if r['binding']==binding and r['input_hash']==actual:
                self.event(phase,{'status':'MATCH','step_id':r['id'],
                    'expected_input_hash':r['input_hash'],'actual_input_hash':actual,
                    'binding_hash':binding,'execution':'REPLAY_DECISION_WITH_CURRENT_TOOLS'})
                return json.loads(r['output_json']),None
        previous=dict(rows[0]) if rows else None
        # Historical matching must not disclose records outside the exact scope.
        reason=('SOURCE_OR_CONFIGURATION_CHANGED' if previous and previous['binding']!=binding
                else 'EXPECTED_INPUT_CHANGED' if previous else 'NO_VERIFIED_PROCEDURE')
        deviation=self.event(phase,{'status':'DEVIATION' if previous else 'DISCOVERY',
            'reason':reason,'step_id':previous['id'] if previous else None,
            'expected_input':json.loads(previous['input_json']) if previous else None,
            'actual_input':data,'expected_binding':previous['binding'] if previous else None,
            'actual_binding':binding,'expected_input_hash':previous['input_hash'] if previous else None,
            'actual_input_hash':actual})
        return None,deviation

    def save(self,phase,question,data,output,*,decision):
        row=self.db.execute('''INSERT INTO sw_procedure_step
          (scope,phase,question,binding,input_hash,input_json,output_json,output_hash,request)
          VALUES(?,?,?,?,?,?,?,?,?)''',(self.scope,phase,question,digest(self.binding),digest(data),
           encoded(data),encoded(output),digest(output),self.request))
        self.event(phase,{'status':'RECORDED','step_id':row.lastrowid,'decision':decision,
                         'output':output,'authority':'PROCEDURE_ONLY_NOT_LEGAL_APPROVAL'})

    def activate(self):
        # Only a successfully completed source-bound route enables later replay.
        self.db.execute('''INSERT OR IGNORE INTO sw_procedure_activation
          SELECT id,request FROM sw_procedure_step WHERE request=? AND scope=?''',
          (self.request,self.scope))

    def observe(self,phase,question,data):
        prior,deviation=self.lookup('observe:'+phase,question,data)
        self.save('observe:'+phase,question,data,{'checked':True},decision='CURRENT_TOOL_RESULT')
        return deviation if prior is None and deviation['status']=='DEVIATION' else None
