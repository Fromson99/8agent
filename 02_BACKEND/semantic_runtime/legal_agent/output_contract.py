"""Model proposals: typed failures, strict JSON, and durable correction ownership.

This layer never invents evidence or changes a legal decision. Existing role
validators still own semantics, ACLs, source receipts, and commit revisions.
"""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
import json
import math
from jsonschema import Draft202012Validator, ValidationError
from ..contracts import digest
from .errors import ContractError, ProposalError, StaleProposal, InvestigationPending

VERSION = 'output-contract-v1'
MAX_ISSUES = 16


def pointer(parts):
    return '/' + '/'.join(str(x).replace('~', '~0').replace('/', '~1') for x in parts)


def issue(code, path='/', *, related=(), rule=None, expected=None, repairable=True):
    return {'code': code, 'path': path, 'related_paths': list(related),
            'rule_id': rule or code, 'repairable': repairable,
            'expected_constraint': expected}


class OutputContractError(ProposalError):
    def __init__(self, message, issues, *, category='OUTPUT_SHAPE_INVALID', repairable=True):
        super().__init__(message)
        self.category = category
        self.repairable = repairable
        self.issues = deepcopy(issues[:MAX_ISSUES])


class DecisionConflict(OutputContractError, ContractError):
    """Compatibility with older reference validators, explicitly repairable."""
    def __init__(self, message, issues=None):
        super().__init__(message, issues or [issue('REFERENCE_DECISION_CONFLICT')],
                         category='DECISION_CONFLICT')


class PartialOperationError(OutputContractError):
    """Known committed tool outcomes; correction starts from their exact revision."""
    def __init__(self,message,revision):
        super().__init__(message,[issue('PARTIAL_OPERATION_REJECTED')],category='TOOL_RESULT_REJECTED')
        self.committed_revision=revision


def repairable(exc):
    return (isinstance(exc, (ProposalError, ValidationError))
            and not isinstance(exc, StaleProposal)
            and getattr(exc, 'repairable', True))


def diagnostics(exc):
    """Typed facts survive wrapper exceptions; no classification by message text."""
    terminal = isinstance(exc, InvestigationPending)
    def result(value):
        value = deepcopy(value)
        if terminal:
            # The underlying proposal might have been repairable before the
            # owner exhausted its budget. The terminal wrapper must not offer
            # a new correction merely because it preserves that cause.
            value['repairable'] = False
            for row in value.get('issues', []):
                row['repairable'] = False
        return value
    seen = set(); cur = exc; cause = None
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if cur is not exc and not isinstance(cur, InvestigationPending):
            cause = cur
        if isinstance(cur, OutputContractError):
            return result({'contract_version': VERSION, 'category': cur.category,
                    'repairable': repairable(cur), 'issues': cur.issues,
                    'reference_space':getattr(cur,'reference_space','canonical')})
        if isinstance(cur, ValidationError):
            return result({'contract_version': VERSION, 'category': 'OUTPUT_SHAPE_INVALID',
                    'repairable': True, 'issues': getattr(cur,'response_contract_issues',None) or schema_issues([cur]),
                    'reference_space':'canonical'})
        detail=getattr(cur,'diagnostic',None)
        if isinstance(detail,dict):
            contract=detail.get('output_contract',detail)
            if isinstance(contract,dict) and contract.get('contract_version')==VERSION:
                return result(contract)
        cur = cur.__cause__
    if terminal and cause is None:
        # SELECT keeps its independent rejections in the investigation report,
        # whereas ASSESS normally uses an explicit exception cause above.
        details = [row.get('diagnostics') for row in exc.diagnostics.get('blockers', []) if isinstance(row, dict)]
        contracts = [d.get('output_contract') for d in details if isinstance(d, dict)]
        contracts = [c for c in contracts if isinstance(c, dict) and c.get('contract_version') == VERSION]
        categories = {c['category'] for c in contracts}
        problems = []; keys = set()
        for contract in contracts:
            for row in contract.get('issues', []):
                key = digest(row)
                if key not in keys:
                    keys.add(key); problems.append(row)
        return result({'contract_version': VERSION,
            'category': next(iter(categories)) if len(categories) == 1 else 'INVESTIGATION_INCOMPLETE',
            'repairable': False, 'issues': problems[:MAX_ISSUES] or
                [issue('SOURCE_INVESTIGATION_INCOMPLETE', repairable=False)]})
    failure = cause if terminal and cause is not None else exc
    return result({'contract_version': VERSION,
            'category': 'STATE_OR_BINDING_INVALID' if isinstance(failure, (ContractError, StaleProposal))
                        else 'DECISION_CONFLICT' if isinstance(failure, ProposalError)
                        else 'IMPLEMENTATION_FAILURE',
            'repairable': repairable(failure), 'issues': []})


def strict_json(content, *, max_chars=4194304, max_depth=128):
    """Reject duplicate keys before dict construction (including nested objects)."""
    class Pairs(list):
        pass
    if not isinstance(content, str):
        value = deepcopy(content)
    else:
        if len(content) > max_chars:
            raise OutputContractError('model JSON exceeds the decoding limit',
                [issue('JSON_SIZE_LIMIT', repairable=False)], repairable=False)
        try:
            value = json.loads(content, object_pairs_hook=Pairs)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise OutputContractError('invalid complete JSON object',
                [issue('JSON_SYNTAX_INVALID', expected='one complete JSON value')],
                category='OUTPUT_JSON_INVALID') from exc
    problems = []
    def walk(v, path=(), depth=0):
        if depth > max_depth:
            raise OutputContractError('model JSON nesting exceeds the decoding limit',
                [issue('JSON_DEPTH_LIMIT', pointer(path), repairable=False)], repairable=False)
        if isinstance(v, Pairs):
            out = {}
            for k, child in v:
                if k in out:
                    problems.append(issue('DUPLICATE_JSON_KEY', pointer((*path, k)),
                        expected='one occurrence of each object key'))
                out[k] = walk(child, (*path, k), depth+1)
            return out
        if isinstance(v, dict):
            return {k: walk(x, (*path, k), depth+1) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x, (*path, i), depth+1) for i, x in enumerate(v)]
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(issue('NONFINITE_JSON_NUMBER', pointer(path)))
        return v
    result = walk(value)
    if problems:
        raise OutputContractError('JSON contains duplicate keys or nonfinite numbers',
            problems, category='OUTPUT_JSON_INVALID')
    return result


def schema_issue(error):
    row = issue('SCHEMA_'+str(error.validator).upper(), pointer(error.absolute_path),
        rule='json-schema:'+pointer(error.absolute_schema_path),
        expected=deepcopy(error.validator_value))
    # A bounded diagnostic preview, not a source or a new executable proposal.
    value = error.instance
    row['received'] = (value[:300] if isinstance(value,str) else deepcopy(value)
                       if value is None or isinstance(value,(bool,int,float)) else
                       {'type':type(value).__name__})
    row['message'] = error.message[:500]
    return row


def schema_issues(errors):
    """Explain only the uniquely selected branch; acceptance still uses all rules."""
    rows = []
    def collect(error):
        if len(rows) >= MAX_ISSUES:return
        if error.validator in ('anyOf','oneOf') and error.context:
            selected = None
            if isinstance(error.instance,dict):
                for key in ('method_id','choice','next_action','operation','kind','status','disposition','id','target_id','issue_id'):
                    if key not in error.instance:continue
                    matches = [n for n,branch in enumerate(error.validator_value)
                        if isinstance(branch,dict) and
                        (branch.get('properties',{}).get(key,{}).get('const',object()) == error.instance[key] or
                         error.instance[key] in branch.get('properties',{}).get(key,{}).get('enum',[]))]
                    if len(matches)==1:
                        selected=matches[0];break
            if selected is not None:
                children=[child for child in error.context if list(child.schema_path)[:1]==[selected]]
                if children:
                    for child in children:collect(child)
                    return
            row=schema_issue(error)
            row['expected_constraint']='one complete permitted action alternative'
            row['message']='Choose one permitted action and supply its required fields.'
            if isinstance(error.instance,dict):
                choices=list(dict.fromkeys(b.get('properties',{}).get('choice',{}).get('const')
                    for b in error.validator_value if isinstance(b,dict)))
                choices=[x for x in choices if x is not None]
                if choices and error.instance.get('choice') not in choices:
                    row.update(path=pointer((*error.absolute_path,'choice')),
                        expected_constraint={'enum':choices},received=error.instance.get('choice'))
            rows.append(row);return
        if error.validator=='required' and isinstance(error.instance,dict):
            for name in error.validator_value:
                if name not in error.instance and len(rows)<MAX_ISSUES:
                    row=schema_issue(error);rule=error.schema.get('properties',{}).get(name,{})
                    row.update(path=pointer((*error.absolute_path,name)),received={'missing':True},
                        expected_constraint={k:deepcopy(v) for k,v in rule.items() if k in ('type','enum','const','minItems','maxItems')},
                        message='Required field is missing.')
                    if row not in rows:rows.append(row)
            return
        row=schema_issue(error)
        if error.validator=='enum' and list(error.absolute_path)[-1:]==['coordinate_scope']:
            row['message']='coordinate_scope selects a structural branch (body/addendum/annex/form/repeated/appendix); 조/항/호/목 are levels.'
        if row not in rows:rows.append(row)
    for error in errors:collect(error)
    return rows[:MAX_ISSUES]


def validate_shape(value, schema, *, reference_space='canonical'):
    errors = schema_issues(Draft202012Validator(schema).iter_errors(value))
    if errors:
        exc=OutputContractError('model output does not match the original schema', errors)
        exc.reference_space=reference_space
        raise exc
    return value


def decision_issues(value):
    """Collect independent duplicate and blank-reason errors only on safe shapes."""
    if not isinstance(value, dict):
        return []
    errors = []
    for field, ident in (('law_decisions', 'law_id'), ('branch_decisions', 'branch_id'),
                         ('gap_resolutions', 'gap_id'), ('decisions', 'id')):
        rows = value.get(field)
        if not isinstance(rows, list):
            continue
        seen = {}
        for n, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            base = pointer((field, n))
            key = row.get(ident)
            if isinstance(key, str):
                if key in seen:
                    old = seen[key]
                    code = 'DUPLICATE_'+field.upper() if row == rows[old] else 'CONFLICTING_'+field.upper()
                    errors.append(issue(code, base, related=[pointer((field, old))],
                        expected='one decision per offered identity'))
                else:
                    seen[key] = n
            for name in ('reason', 'applicability_reason'):
                if isinstance(row.get(name), str) and not row[name].strip():
                    errors.append(issue('BLANK_DECISION_REASON', base+'/'+name,
                        expected='a nonblank reason chosen by the model'))
    if isinstance(value.get('reason'), str) and not value['reason'].strip():
        errors.append(issue('BLANK_DECISION_REASON', '/reason'))
    return errors[:MAX_ISSUES]


def validate_decisions(value):
    errors = decision_issues(value)
    if errors:
        raise OutputContractError('decision identities or reasons conflict', errors,
                                  category='DECISION_CONFLICT')


def owner_for(phase):
    if phase == 'memory-guided-answer':return 'guided-answer'
    if phase in ('memory-reason-decision-review','source-reason-decision-review','memory-final-reason-review'):
        return 'reason-decision-review'
    if phase in ('source-request-route', 'source-request-route-repair'):
        return 'request-routing'
    if phase in ('request-entry', 'request-entry-repair'):
        return 'request-entry'
    if phase in ('memory-resolve', 'memory-resolve-repair', 'memory-resolve-fields', 'memory-resolve-repair-fields', 'memory-command-check',
                 'memory-resolve-related', 'memory-resolve-related-repair'):
        return 'command-resolver'
    if phase in ('memory-intent', 'memory-intent-repair'):
        return 'request-intent'
    if phase.startswith('source-law-navigation-'):
        return 'law-navigation'
    if phase.startswith('source-unit-'):
        return 'unit-selection'
    if phase.startswith('source-reference-'):
        return 'reference-navigation'
    if phase == 'memory-ontology-supervisor':
        return 'ontology-assessment-review'
    if phase in ('memory-assess', 'memory-assess-repair'):
        return 'assessment'
    if phase in ('memory-compose', 'memory-compose-repair'):
        return 'composition'
    return 'gateway'


@dataclass(frozen=True)
class ContractSpec:
    role: str
    schema_hash: str
    owner: str
    version: str = VERSION

    @classmethod
    def from_schema(cls, role, schema):
        return cls(role, digest(schema), owner_for(role))

    def receipt(self, view, binding):
        return {'version': self.version, 'role': self.role, 'schema_hash': self.schema_hash,
                'repair_owner': self.owner, 'view_hash': digest(view),
                'binding_hash': digest(binding)}


class DecisionJournal:
    """Append-only ownership inside the existing journal, no new database.

    Reserve before invoke. An interrupted reservation without an accepted result
    is unknown and cannot be replayed. Domain callers revalidate accepted values
    against current receipts before use. SQL ownership/commit checks remain.
    """
    EVENT = 'OUTPUT_DECISION_STATE'

    def __init__(self, repo, owner, identity, schema):
        self.repo = repo
        self.binding = {'version': VERSION, 'owner': owner,
            'identity_hash': digest(identity), 'schema_hash': digest(schema),
            'runtime_binding': deepcopy(getattr(repo, 'binding', {}))}
        self.key = digest(self.binding)
        self.local = None

    def state(self):
        if hasattr(self.repo, 'output_decision_state'):
            value = self.repo.output_decision_state(self.key)
            if value is not None and value['binding'] != self.binding:
                raise ContractError('output decision journal binding mismatch')
            return value
        if hasattr(self.repo, 'db'):
            from .journal_storage import register
            register(self.repo.db)
            row = self.repo.db.execute("SELECT payload_json,payload_hash FROM event WHERE kind=? AND json_extract(journal_text(payload_json),'$.decision_key')=? ORDER BY seq DESC LIMIT 1",
                                      (self.EVENT, self.key)).fetchone()
            if row is None:
                return None
            value = json.loads(row[0])
            if digest(value) != row[1] or value['binding'] != self.binding:
                raise ContractError('output decision journal binding/hash mismatch')
            return value
        # Non-persistent test/session adapters do not claim restart durability.
        return self.local

    def _put(self, status, attempt, **fields):
        row = {'decision_key': self.key, 'binding': self.binding,
               'status': status, 'attempt': attempt, **deepcopy(fields)}
        if hasattr(self.repo, 'output_decision_event'):
            self.repo.output_decision_event(row)
        else:
            self.repo.event(self.EVENT, row)
        self.local = row
        return row

    def transaction(self):
        return self.repo.transaction() if hasattr(self.repo, 'transaction') else nullcontext()

    def reserve(self, attempt, *, max_repairs=1, correction_budget=None):
        with self.transaction():
            prior = self.state()
            if prior and prior['status'] == 'ACCEPTED':
                return deepcopy(prior)
            if prior and prior['status'] == 'RESERVED':
                raise ContractError('previous model decision outcome is unknown; no automatic replay')
            expected = 0 if prior is None else prior['attempt'] + 1
            if (attempt != expected or attempt > max_repairs or
                    prior and (prior['status'] != 'REJECTED' or not prior.get('repairable'))):
                raise OutputContractError('decision correction budget exhausted',
                    [issue('CORRECTION_BUDGET_EXHAUSTED', repairable=False)], repairable=False)
            if correction_budget is not None:
                correction_budget.reserve_in_transaction(self.key,attempt)
            self._put('RESERVED', attempt, **({'previous_failure_signature': prior['failure_signature']}
                if prior and prior.get('failure_signature') else {}))
        return None

    def reject(self, attempt, error, value=None, *, can_retry=None, correction_budget=None):
        with self.transaction():
            if correction_budget is not None:
                correction_budget.finish_in_transaction(self.key,attempt,error=error,value=value,can_retry=can_retry)
            prior = self.state()
            failure = diagnostics(error)
            signature = digest({'binding': self.binding, 'category': failure.get('category'),
                'issues': sorted(({'code': row.get('code'), 'path': row.get('path'),
                    'expected_constraint': row.get('expected_constraint')} for row in failure.get('issues', [])),
                    key=lambda row: digest(row))})
            self._put('REJECTED', attempt, repairable=repairable(error) and can_retry is not False,
                      failure=failure, proposal=deepcopy(value),
                      failure_signature=signature,
                      repeated_failure=bool(prior and prior.get('previous_failure_signature', prior.get('failure_signature')) == signature),
                      proposal_hash=digest(value), error=str(error))

    def accept(self, attempt, value, *, correction_budget=None):
        with self.transaction():
            if correction_budget is not None:
                correction_budget.finish_in_transaction(self.key,attempt,value=value)
            return self._put('ACCEPTED', attempt, value=value, value_hash=digest(value))


class CorrectionBudget(DecisionJournal):
    """Shared correction ownership across changing presentations, not new retries.

    The caller supplies canonical task/evidence/revision identity; dynamic menus
    and schema aliases must not reset it. Each reservation/finish shares the
    existing decision transaction. Unknown outcomes fail closed on restart.
    """
    EVENT = 'OUTPUT_CORRECTION_SCOPE'

    def __init__(self,repo,owner,identity):
        super().__init__(repo,owner+'-correction-scope',identity,{})

    def reserve_in_transaction(self,decision_key,attempt):
        prior=self.state() or {}
        if prior.get('status')=='RESERVED':
            raise ContractError('previous correction-scope outcome is unknown; no automatic replay')
        failures=deepcopy(prior.get('failures',[]))
        if len(failures)>=2 or failures and (not failures[-1]['failure']['repairable'] or failures[-1]['can_retry'] is False):
            raise OutputContractError('same-evidence decision correction budget exhausted',
                [issue('CORRECTION_SCOPE_EXHAUSTED',repairable=False)],repairable=False)
        self._put('RESERVED',attempt,decision=decision_key,failures=failures)

    def finish_in_transaction(self,decision_key,attempt,*,error=None,value=None,can_retry=None):
        prior=self.state()
        if not prior or prior['status']!='RESERVED' or prior['decision']!=decision_key or prior['attempt']!=attempt:
            raise ContractError('correction-scope reservation changed before commit')
        failures=deepcopy(prior['failures'])
        if error is not None:
            failures.append({'decision':decision_key,'attempt':attempt,
                'failure':diagnostics(error),'error':str(error),'proposal_hash':digest(value),'can_retry':can_retry})
        self._put('REJECTED' if error is not None else 'ACCEPTED',attempt,
            decision=decision_key,failures=failures)


def bounded_decision(repo, owner, data, schema, invoke, validate, *, identity=None, can_repair=None,
                     correction_scope=None, recover=None):
    """One full correction with the same data/schema and durable budget.

    invoke(payload, attempt) is the existing stage call; no alternate transport.
    validate must be read-only; tool execution remains after this function.
    """
    journal = DecisionJournal(repo, owner, identity or data, schema)
    shared = CorrectionBudget(repo,owner,correction_scope) if correction_scope is not None else None
    prior = journal.state()
    if prior and prior['status'] in ('ACCEPTED','ACTION_RECOVERED'):
        value = deepcopy(prior['value'])
        validate(value)
        return value
    start = prior['attempt'] + 1 if prior and prior['status'] == 'REJECTED' else 0
    if start > 1 or prior and prior['status'] == 'REJECTED' and not prior.get('repairable'):
        raise OutputContractError('decision correction budget exhausted',
            [issue('CORRECTION_BUDGET_EXHAUSTED', repairable=False)], repairable=False)
    for attempt in range(start, 2):
        cached = journal.reserve(attempt,correction_budget=shared)
        if cached:
            value = deepcopy(cached['value']); validate(value); return value
        payload = deepcopy(data)
        if prior:
            payload.update(rejected_decision=prior.get('proposal'),
                contract_error=prior.get('error'),
                repair_contract={'response_mode':'FULL_DECISION', 'max_attempts':1,
                    'validation':prior['failure'], 'same_evidence_scope':True})
        value = None
        try:
            value = invoke(payload, attempt)
            validate(value)
        except (ProposalError, ValidationError) as exc:
            value=deepcopy(getattr(exc,'proposal',value))
            retry=not attempt and repairable(exc) and (can_repair is None or can_repair())
            journal.reject(attempt, exc, value,can_retry=retry,correction_budget=shared)
            if not retry:
                if recover is not None and value is not None:
                    with journal.transaction():
                        recovered=recover(value,exc)
                        if recovered is not None:
                            candidate,receipt=recovered
                            validate(candidate)
                            repo.event('INDEPENDENT_READ_RECOVERY',{**receipt,'owner':owner,'decision_key':journal.key,
                                'rejected_proposal':deepcopy(value),'rejected_diagnostics':diagnostics(exc),
                                'action_value_hash':digest(candidate),'judgments_adopted':False})
                            journal._put('ACTION_RECOVERED',attempt,value=candidate,value_hash=digest(candidate),
                                rejected_proposal=deepcopy(value),failure=diagnostics(exc),recovery=receipt)
                            return candidate
                raise
            prior = journal.state()
            continue
        journal.accept(attempt, value,correction_budget=shared)
        return value
