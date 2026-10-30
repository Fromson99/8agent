"""Public source-tool port for workflows, bound to this RAG code package.

Business stages live in workflow/. Native question calls use the existing Pipeline.run; source methods verify returned evidence.
"""
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timezone, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace

from .contracts import digest, sha
from .document_agent import ServingDocumentAgent
from .storage import Store
from .folder_navigation import normalized
from .legal_agent.context import RequestContext
from .legal_agent.repository import WorkRepository, encoded
from .legal_agent.source_tools import SourceSession
from .legal_agent.errors import ContractError, ProposalError, BudgetExhausted, DeadlineExceeded, TransportError, ToolExecutionError
from .legal_agent.bounded_source_session import _Gateway, _Protocol


def package():
    root = Path(__file__).resolve().parents[1]/'workflow'
    name = '_workflow_'+hashlib.sha256(str(root).encode()).hexdigest()[:16]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, root/'__init__.py', submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return name


def install(app, pipeline, runtime, release, identity):
    import importlib
    api = importlib.import_module(package()+'.api')
    return api.install(app, Services(pipeline, runtime, release), identity)


class Services:
    ProposalError = ProposalError
    BudgetExhausted = BudgetExhausted
    DeadlineExceeded = DeadlineExceeded
    TransportError = TransportError
    ContractError = ContractError
    ToolExecutionError = ToolExecutionError

    def __init__(self, pipeline, runtime, release):
        self.pipeline, self.runtime = pipeline, Path(runtime)
        # Process identifiers are diagnostics, not code/data/policy identity.
        # All other release fields remain part of the immutable execution binding.
        self.release = {key:value for key,value in (release or {}).items()
                        if key not in ('process_id', 'process_instance_id')}
        self.profile = dict(pipeline.term_agent.profile)

    def binding(self, request, manifest):
        store = self.pipeline.store
        store.check_unchanged()
        root = self.pipeline.contracts.root
        from .stage_runner import StageRunner
        StageRunner(self.pipeline).verify_profile()
        declarations=self.pipeline.contracts.pipeline['workflows']['registered']
        selected=next((d for d in declarations if d['id']==request['workflow_id'] and d['version']==request['workflow_version']),None)
        if selected is None or sha(root/selected['manifest'])!=selected['sha256']:
            raise ContractError('workflow manifest is not bound by PIPELINE')
        binding = {'workflow':digest(manifest), 'request':digest(request),
                'generation_id':store.manifest['generation_id'], 'store_sha256':store.manifest['store_sha256'],
                'generation_manifest_sha256':sha(store.path/'manifest.json'),
                'search_selection_sha256':getattr(getattr(store,'selection',None),'fingerprint',None),
                'pipeline_sha256':sha(root/'00_SYSTEM/PIPELINE.json'),
                'profile_sha256':digest(self.profile), 'release':self.release,
                'export_allowed':store.manifest['export_allowed'],
                'document_ids':request['document_ids'], 'principal':request['principal'],
                'model':self.profile.get('model_binding')}
        if manifest.get('execution_policy'):
            binding['execution_policy'] = dict(manifest['execution_policy'])
        if request['use_llm'] and (self.profile.get('model_binding') or {}).get('trust_zone') != 'internal':
            authorize = getattr(self.pipeline.term_agent.transport, 'authorize_workflow', None)
            if authorize is None:
                raise ContractError('workflow external scope is not authorized')
            binding['external_authorization'] = authorize(request, binding)
            if not isinstance(binding['external_authorization'], dict):
                raise ContractError('workflow authorization receipt required')
        return binding

    def principal(self,user,team):
        from .team_scope import select_documents
        return {'user_id':user,'team_id':team,'document_ids':sorted(select_documents(self.pipeline.store,team))}

    def deliver(self, result):
        # Called only after runtime verification and durable publication, also
        # for a verified reused result. No model call or artificial token delay.
        from .legal_agent.answer_stream import current_sink
        sink = current_sink()
        if (sink is None or result.get('workflow_id') != 'risk_team_compare_workflow'
                or result.get('status') not in {'completed', 'partial'}):
            return result
        if getattr(sink, 'started', False):
            raise ContractError('workflow answer channel was already used')
        from .chat_adapter import views
        text = views()._public_answer_text(result)
        for line in text.splitlines(keepends=True):
            sink(line)
        return result

    def constrain_principal(self,principal):
        from .team_scope import prepared_catalogue
        visible=prepared_catalogue(self.pipeline.store)['ids']
        return {**principal,'document_ids':sorted(set(principal['document_ids'])&visible)}

    def recover_response(self,raw,schema):
        from .legal_agent.model_contract import structured_content, validate_response_model
        from .legal_agent.output_contract import strict_json,validate_shape
        body=raw.get('body_json')
        validate_response_model(self.profile['model_binding'], body)
        value=strict_json(structured_content(body,require_complete=True))
        from .legal_agent.minimal_output import Projection
        value=Projection(schema).expand(value)
        validate_shape(value,schema)
        return value

    def context(self, request, binding, run_id, journal):
        deadline_at = None
        if journal.is_file():
            import sqlite3
            with sqlite3.connect('file:'+str(journal)+'?mode=ro', uri=True) as db:
                deadline_at = db.execute('SELECT deadline_at FROM run WHERE singleton=1').fetchone()[0]
        query = {'id':'workflow-query:'+run_id, 'question':request['question'] or '선택 내규 전체의 근거 외규 조사',
                 'generation_id':binding['generation_id'],
                 'scope':{'document_version_ids':request['document_ids']}}
        seconds=min(self.profile['wall_seconds'],binding.get('execution_policy',{}).get('wall_seconds',self.profile['wall_seconds']))
        result = RequestContext.create(query, request, binding, seconds, run_id)
        if deadline_at:
            remaining = (datetime.fromisoformat(deadline_at)-datetime.now(timezone.utc)).total_seconds()
            result = replace(result, deadline=time.monotonic()+remaining, deadline_at=deadline_at)
        return result

    def journal(self, path, context):
        profile=dict(self.profile);policy=context.binding.get('execution_policy',{})
        if policy:
            profile['max_model_attempts']=min(profile['max_model_attempts'],policy['max_model_attempts'])
            profile['finalization_reserve']=min(max(profile['finalization_reserve'],policy['finalization_reserve']),
                                               max(0,profile['max_model_attempts']-1))
        work=WorkRepository(path, context, profile)
        if policy and not work.db.execute("SELECT 1 FROM event WHERE kind='WORKFLOW_EXECUTION_POLICY' LIMIT 1").fetchone():
            work.event('WORKFLOW_EXECUTION_POLICY',{'policy':policy,
                'deadline_at':context.deadline_at,
                'investigation_deadline_at':self.phase_context(context).deadline_at,
                'final_model_deadline_at':self.phase_context(context,final=True).deadline_at,
                'effective_budget':work.budget()})
        return work

    def phase_context(self, context, *, final=False):
        """One original end time: investigation cannot consume publication time."""
        policy=context.binding.get('execution_policy')
        if not policy:return context
        reserve=policy['publication_seconds'] if final else policy['finalization_seconds']
        # Shorter operator deadlines reserve a proportional share, never renew it.
        total=min(self.profile['wall_seconds'],policy['wall_seconds'])
        reserve=min(reserve,total*(.05 if final else .2))
        return replace(context,deadline=context.deadline-reserve,
            deadline_at=(datetime.fromisoformat(context.deadline_at)-timedelta(seconds=reserve)).isoformat())

    @contextmanager
    def tools(self, work, context):
        # Dedicated read connection: request deadlines and SQL callbacks never leak.
        store = Store(self.pipeline.store.path, verify=True)
        try:
            if store.manifest != self.pipeline.store.manifest:
                raise ContractError('workflow source binding changed')
            proxy = SimpleNamespace(store=store, contracts=self.pipeline.contracts,
                                    term_agent=self.pipeline.term_agent)
            agent = ServingDocumentAgent(proxy, self.pipeline.term_agent.config)
            with agent.resources(context.query['scope']['document_version_ids']) as (_, tools, glossary, matcher):
                read_context=context
                if work.db.execute("SELECT result_json FROM workflow_state WHERE singleton=1").fetchone()[0] is not None:
                    # Publication verification gets a read-only deadline; persisted
                    # workflow deadline and usage remain unchanged.
                    read_context=replace(context,deadline=time.monotonic()+30)
                session = SourceSession(store, tools, glossary, matcher, work, read_context, self.profile)
                port = SourcePort(session)
                port.services = self
                yield port
        finally:
            store.close()

    def structured(self, work, context, stage, call_id, data, schema, system, validator):
        # Gateway alone owns wire/JSON correction. The business stage gets one
        # bounded semantic correction, using the same durable attempt budget.
        profile = {**self.profile, 'schema_version':'legal-agent-profile-v1',
                   'numbered_references_enabled':False, 'max_schema_repairs':0}
        gateway = _Gateway(work, context, profile, {}, self.pipeline.term_agent.transport,
            message_protocol=_Protocol(schema, validator), system=system, prompts={})
        phase = 'compose' if stage in ('BASIS','COMPARE','FINALIZE') else 'investigate'
        context=self.phase_context(context,final=phase=='compose')
        context.remaining()
        gateway.context=context
        if stage=='FINALIZE':
            # The workflow owns one schema correction. A timed-out final model
            # must leave time to publish saved opinions and originals.
            gateway.profile['max_transport_retries']=0
        if len(json.dumps(data,ensure_ascii=False)) > profile['max_context_chars']-2000:
            raise BudgetExhausted('workflow bounded view including repair exceeds context limit')
        view = work.save_view(phase, {**data, 'source_stage':'workflow-'+stage.lower(),
                                     'workflow_call_id':call_id}, [e['evidence_id'] for e in data.get('sources',[])])
        return gateway.generate(phase, view, 'WorkflowDecision', repair_owner='workflow')


class SourcePort:
    OPERATIONS = ('search_sources','list_documents','list_structure','locate_provision',
                  'search_structure','search_text','search_subtree','read_node','read_parent',
                  'follow_reference','lookup_definition','return_to')

    def __init__(self, session):
        self.session = session
        self._verification_deadline = None
        self.all_scope = list(session.scope)
        self.categories = {did:session.navigator.m.document_catalogue[did]['category'] for did in self.all_scope}

    @contextmanager
    def source_reads(self, context):
        """Bind SQL to the current phase and classify only proven deadline aborts.

        The workflow owns recovery; this scope never retries a read or renews
        the request. Unknown interruptions and all other DB errors stay fatal.
        """
        s=self.session;original=s.context
        current=replace(original,deadline=min(original.deadline,context.deadline),
            deadline_at=context.deadline_at if context.deadline<original.deadline else original.deadline_at)
        def bind(value):
            s.context=value
            s.store.db.set_progress_handler(lambda:int(time.monotonic()>=value.deadline),1000)
            s.tools.db.set_progress_handler(lambda:int(time.monotonic()>=value.deadline),1000)
            s.tools.request_deadline=value.deadline
        bind(current)
        try:
            current.remaining()
            yield
        except sqlite3.OperationalError as exc:
            if getattr(exc,'sqlite_errorcode',None)!=sqlite3.SQLITE_INTERRUPT or time.monotonic()<current.deadline:
                raise
            s.repo.event('WORKFLOW_SOURCE_DEADLINE',{'type':type(exc).__name__,
                'cause':str(exc),'sqlite_errorcode':exc.sqlite_errorcode,
                'deadline_at':current.deadline_at,'request_deadline_at':original.deadline_at,
                'recovery_owner':'workflow','retried':False})
            raise DeadlineExceeded('workflow source SQL interrupted at its deadline') from exc
        finally:
            bind(original)

    @contextmanager
    def publication_verification(self):
        """Verify saved originals after research stops, without renewing research.

        This window permits reads of existing evidence only. Its first end time
        is durable, so interrupted finalization cannot acquire another window.
        """
        s=self.session
        if self._verification_deadline is not None:
            raise ContractError('nested workflow publication verification')
        with s.repo.transaction():
            s.repo.db.execute('CREATE TABLE IF NOT EXISTS workflow_publication_window(singleton INTEGER PRIMARY KEY CHECK(singleton=1),deadline_at TEXT NOT NULL)')
            row=s.repo.db.execute('SELECT deadline_at FROM workflow_publication_window WHERE singleton=1').fetchone()
            if row is None:
                deadline_at=(datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat()
                s.repo.db.execute('INSERT INTO workflow_publication_window VALUES(1,?)',(deadline_at,))
                s.repo.event('WORKFLOW_PUBLICATION_VERIFY_STARTED',{'deadline_at':deadline_at,'max_seconds':30,
                    'research_deadline_at':s.context.deadline_at,'new_research_allowed':False})
            else:deadline_at=row[0]
        remaining=(datetime.fromisoformat(deadline_at)-datetime.now(timezone.utc)).total_seconds()
        if remaining<=0:raise DeadlineExceeded('workflow publication verification window exhausted')
        deadline=time.monotonic()+remaining
        original=s.context
        self._verification_deadline=deadline
        s.context=replace(original,deadline=deadline)
        s.store.db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
        s.tools.db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
        s.tools.request_deadline=deadline
        try:
            self._check_verification_time()
            yield
            self._check_verification_time()
        finally:
            s.context=original
            s.store.db.set_progress_handler(lambda:int(time.monotonic()>=original.deadline),1000)
            s.tools.db.set_progress_handler(lambda:int(time.monotonic()>=original.deadline),1000)
            s.tools.request_deadline=original.deadline
            self._verification_deadline=None

    def _check_verification_time(self):
        if self._verification_deadline is not None and time.monotonic()>=self._verification_deadline:
            raise DeadlineExceeded('workflow publication verification window exhausted')

    def evidence(self):
        from .legal_agent.source_recall import spans_complete
        values=self.session.repo.evidence()
        out=[]
        for e in values:
            self._check_verification_time()
            raw=self.session.store.db.execute('SELECT json FROM document WHERE document_id=?',(e['document_id'],)).fetchone()
            metadata=json.loads(raw[0])
            names=metadata.get('document_metadata') or {}
            citation_names=[names[k] for k in ('document_title','official_abbreviation')
                            if isinstance(names.get(k),str) and names[k].strip()]
            if not citation_names:
                citation_names=[e['metadata']['document_name']]
            temporal=metadata.get('workflow_version') or {}
            day=self.session.context.request.get('as_of')
            verified=False
            try:
                start=temporal.get('valid_from');end=temporal.get('valid_to')
                if temporal.get('verified') is True and isinstance(day,str) and isinstance(start,str):
                    dates=[day,start]+([end] if end is not None else [])
                    verified=(all(isinstance(d,str) and date.fromisoformat(d).isoformat()==d for d in dates)
                        and start<=day and (end is None or day<=end))
            except ValueError:
                pass  # Malformed source metadata never establishes applicability.
            out.append({**e,'side':self.categories[e['document_id']],
                'citation_names':citation_names,
                'version_verified':verified,
                'source_complete':spans_complete(self.session.tools.sources[e['source_id']],values),
                'text':'\n'.join(p['text'] for p in e['spans'])})
        return out

    def split_evidence(self,e,max_chars):
        from .legal_agent.source_tools import canonical_evidence
        from .legal_agent.repository import text_hash
        pieces=[]
        for span in e['spans']:
            if len(span['text'])>max_chars:
                from .legal_agent.errors import BudgetExhausted
                raise BudgetExhausted('complete original block exceeds model context; original and unfinished state preserved')
            item=canonical_evidence(e,[span])
            self.session.verify(item);pieces.append(item)
        self.session.repo.record_observation({'tool':'workflow_packet_ranges','args':{'origin':e['evidence_id'],'max_chars':max_chars}},
            {'status':'OK','evidence_ids':[p['evidence_id'] for p in pieces]},pieces,verify=self.session.verify)
        ids={p['evidence_id'] for p in pieces}
        return [p for p in self.evidence() if p['evidence_id'] in ids]

    def saved_context(self,ids,call_id):
        """Only already read blocks of explicitly requested active sources.

        This is a no-model lookup, never a new search. Missing ranges still need
        the existing scoped child continuation.
        """
        from .legal_agent.source_tools import canonical_evidence
        action={'tool':'workflow_saved_context','args':{'call_id':call_id,'evidence_ids':sorted(ids)}}
        key=digest({'action':action,'binding':self.session.repo.run()['binding_hash']})
        saved=self.session.repo.db.execute('SELECT result_json FROM observation WHERE request_key=? ORDER BY created_seq DESC LIMIT 1',(key,)).fetchone()
        if saved:return json.loads(saved[0])['evidence_ids']
        wanted={self.session.repo.evidence(i)['source_id'] for i in ids}
        db=self.session.repo.db;values={}
        for row in db.execute('SELECT journal FROM workflow_child_run'):
            path=Path(row['journal']).resolve()
            root=self.services.runtime/'workflows'/self.session.context.run_id/'children'
            if not path.is_relative_to(root.resolve()):raise ContractError('context journal outside workflow')
            from .legal_agent.unified_repository import UnifiedRepository
            child=UnifiedRepository(path)
            try:
                for item in child.evidence():
                    if item['source_id'] not in wanted:continue
                    for span in item['spans']:
                        value=canonical_evidence({**item,'metadata':{**item['metadata'],'read_location':item['metadata'].get('heading','')}},[span])
                        self.session.verify(value);values[value['evidence_id']]=value
            finally:child.close()
        self.session.context.remaining();self.session.repo.reserve_tool()
        self.session.repo.record_observation(action,
            {'status':'OK' if values else 'NOT_FOUND','evidence_ids':sorted(values)},list(values.values()),verify=self.session.verify)
        return sorted(values)

    def verify_all(self):
        from .workflow_rag import verify_returns
        self._check_verification_time()
        verify_returns(self)
        self.session.store.check_unchanged()
        for e in self.session.repo.evidence():
            self._check_verification_time()
            self.session.verify(e)
        self._check_verification_time()

    def validate(self, action):
        s=self.session
        if action['operation'] not in self.OPERATIONS or action['side'] not in ('internal','external','both'):
            raise ValueError('unknown operation or side')
        args=action['args']
        allowed=[d for d in self.all_scope if action['side']=='both' or self.categories[d]==action['side']]
        for key,kind in (('document','D'),('node','U')):
            if args.get(key):
                resolved=s.resolve(args[key],kind)
                did=resolved if kind=='D' else resolved['document_id']
                if did not in allowed:raise ValueError('handle outside selected side')
        if args.get('evidence_id'):
            e=s.repo.evidence(args['evidence_id'])
            if not e or e['document_id'] not in allowed:raise ValueError('reference evidence outside selected side')
        if args.get('cursor') and action['operation']!='read_parent':
            s.cursor_position({'tool':action['operation'],'args':args})
        return True

    def execute(self, action):
        s = self.session
        self.validate(action)
        operation, side, args = action['operation'], action['side'], dict(action['args'])
        if operation not in self.OPERATIONS or side not in ('internal','external','both'):
            raise ProposalError('unsupported workflow source operation/side')
        s.scope = [d for d in self.all_scope if side == 'both' or self.categories[d] == side]
        try:
            if not s.scope:
                s.context.remaining()
                s.repo.reserve_tool()
                result = {'status':'UNRESOLVED','registration_status':'NOT_REGISTERED','items':[],'evidence_ids':[],'next_cursor':None,
                          'coverage':{'document_ids':[],'complete':False},'error_code':'SOURCE_CATEGORY_EMPTY'}
                return s.repo.record_observation({'tool':operation,'args':args}, result, verify=s.verify)
            if operation in ('search_sources','search_structure','read_parent','return_to'):
                return self.extended(operation, args, action.get('reason','원문 조사'))
            return s.execute({'tool':operation,'args':args,'reason':action.get('reason','원문 조사')})
        finally:
            s.scope = list(self.all_scope)

    def extended(self, operation, args, reason):
        s = self.session
        s.context.remaining()
        if operation == 'read_parent':
            if set(args)-{'node','cursor'} or not args.get('node'):
                raise ProposalError('read_parent requires a stored node')
            node = s.resolve(args['node'],'U')
            unit = s.matcher.units.get((node['document_id'],str(node['unit_id'])))
            parent = unit.get('parent') if unit else None
            if parent is None: raise ProposalError('node has no stored parent')
            return s.execute({'tool':'read_node','args':{'node':s.node(node['document_id'],parent),
                            'cursor':args.get('cursor')},'reason':reason})
        if operation == 'return_to':
            if set(args) != {'node'}: raise ProposalError('return_to requires one known node')
            node = s.resolve(args['node'],'U')
            items = [{'node':args['node'],'document':s.handle('D',node['document_id']),
                      'content_read':False,'restored':True}]
            next_cursor = None
            s.repo.reserve_tool()
        else:
            if set(args)-{'query','document','cursor'} or not isinstance(args.get('query'),str) or not 0<len(args['query'])<=500:
                raise ProposalError('bounded query required')
            docs = [s.resolve(args['document'],'D')] if args.get('document') else list(s.scope)
            action = {'tool':operation,'args':args}
            key, offset = s.cursor_position(action)
            if type(offset) is not int: raise ProposalError('search cursor type mismatch')
            s.repo.reserve_tool()
            ids, nodes = [], []
            if operation == 'search_structure':
                q = normalized(args['query'])
                nodes = [(d,u) for (d,u),v in s.matcher.units.items()
                         if d in docs and q in normalized(v.get('title','')+' '+v.get('surface',''))]
            else:
                found = s.matcher.starts(args['query'],docs)
                for row in found['structures']:
                    nodes.append((row['document_id'],row['unit_id']))
                allowed = {sid for sid,source in s.tools.sources.items() if source['document_id'] in docs}
                from .fulltext import question_terms
                if s.matcher.fulltext is not None:
                    ids = s.matcher.fulltext.rank(s.matcher.fulltext_db, question_terms(args['query']), allowed)
                # Existing term occurrence index remains available without fulltext.
                for row in found['terms']:
                    for match in s.tools.db.execute('SELECT source_id FROM occurrence WHERE term_id=? ORDER BY source_id',(row['id'],)):
                        if match[0] in allowed: ids.append(match[0])
                for sid in dict.fromkeys(ids):
                    source = s.tools.sources[sid]
                    nodes.append((source['document_id'],source.get('unit_id')))
            nodes = list(dict.fromkeys(nodes))
            page = nodes[offset:offset+s.profile['page_size']]
            items = [{'node':s.node(d,u),'document':s.handle('D',d),
                      'document_name':s.matcher.documents[d], 'category':self.categories[d],
                      'heading':s.matcher.units.get((d,str(u)),{}).get('title',''),
                      'content_read':False} for d,u in page]
            next_cursor = s.cursor(key,offset+len(page)) if offset+len(page)<len(nodes) else None
        result = {'status':'OK' if items else 'NOT_FOUND','items':items,'evidence_ids':[],
                  'next_cursor':next_cursor,'error_code':None,
                  'coverage':{'document_ids':list(s.scope),'complete':next_cursor is None,
                              'meaning':'operation only, never proof of absence'}}
        s.context.remaining()
        return s.repo.record_observation({'tool':operation,'args':args},result,verify=s.verify)

    def basis_inventory(self,did):
        from .basis_links.contracts import require
        require(did in self.all_scope and self.categories[did]=='internal','BASIS_SCOPE','허용 내규를 선택해야 합니다.',403)
        self.session.context.remaining();self.session.repo.reserve_tool()
        groups={}
        for row in self.session.store.db.execute('SELECT block_id,unit_id,text FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)',(did,)):
            if not row['text']:continue
            uid=str(row['unit_id']) if row['unit_id'] is not None else None
            groups.setdefault(uid,[]).append({'block_id':str(row['block_id']),'start_cp':0,'end_cp':len(row['text'])})
        items=[]
        for uid,segments in groups.items():
            title=self.session.matcher.units.get((did,uid),{}).get('title') or uid or '구조 미분류 본문'
            # Each complete original block is an inventory unit. Shared owner
            # labels keep long articles composable without dropping annexes.
            parts=[]
            for segment in segments:
                width=max(256,min(4000,self.services.profile['max_context_chars']//8))
                parts.extend({**segment,'start_cp':a,'end_cp':min(a+width,segment['end_cp'])} for a in range(segment['start_cp'],segment['end_cp'],width))
            for segment in parts:
                node={'document_id':did,'unit_id':uid,'source_id':None,'read_segments':[segment],'read_label':title}
                items.append({'inventory_id':digest(node),'title':title,'node':node})
        return items

    def basis_existing(self,originals,targets,rag,key):
        ids=set();s=self.session
        nodes=[]
        for target in targets:
            end=target['endpoint']
            node={'document_id':end['document_id'],'unit_id':end['unit_id'],'source_id':None,
                  'read_segments':[{k:p[k] for k in ('block_id','start_cp','end_cp')} for p in end['spans']]}
            nodes.append(s.handle('U',node))
        for e in originals:
            cursor=None
            while True:
                result=rag.source_call({'operation':'follow_reference','side':'both','args':{'evidence_id':e['evidence_id'],'direction':'outgoing','cursor':cursor}},call_id='basis-ref:'+digest([key,e['evidence_id'],cursor]))
                for ref in result.get('items',[]):
                    for target in ref.get('targets',[]):
                        if self.categories.get(s.resolve(target['node'],'U')['document_id'])=='external':nodes.append(target['node'])
                cursor=result.get('next_cursor')
                if not cursor:break
        for node in dict.fromkeys(nodes):
            cursor=None
            while True:
                result=rag.source_call({'operation':'read_node','side':'external','args':{'node':node,'cursor':cursor}},call_id='basis-existing:'+digest([key,node,cursor]))
                ids.update(result.get('evidence_ids',[]));cursor=result.get('next_cursor')
                if not cursor:break
        return sorted(ids)

    def basis_packets(self,evidence):
        from .legal_agent.source_tools import canonical_evidence
        from .legal_agent.repository import text_hash
        width=max(128,min(2000,self.services.profile['max_context_chars']//16));pieces=[]
        for e in evidence:
            for span in e['spans']:
                for offset in range(0,len(span['text']),width):
                    text=span['text'][offset:offset+width]
                    value={**span,'start_cp':span['start_cp']+offset,'end_cp':span['start_cp']+offset+len(text),'text':text,'span_hash':text_hash(text)}
                    item=canonical_evidence(e,[value]);self.session.verify(item);pieces.append(item)
        self.session.repo.record_observation({'tool':'basis_packets','args':{'originals':[e['evidence_id'] for e in evidence],'width':width}},
            {'status':'OK','evidence_ids':[e['evidence_id'] for e in pieces]},pieces,verify=self.session.verify)
        selected={e['evidence_id'] for e in pieces}
        return [e for e in self.evidence() if e['evidence_id'] in selected]
