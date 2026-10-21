"""Explicit research transport; identity stays external and source flags unchanged."""
from pathlib import Path
import hashlib,json,sqlite3
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError,TransportError,ProposalError
from semantic_runtime.legal_agent.local_gemma import provider_request

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

class AuthorizedQwen:
    def __init__(self, root, grant_path, output):
        self.root=Path(root);self.grant_path=Path(grant_path);self.output=Path(output)
        self.grant_hash=sha(self.grant_path);self.grant=json.loads(self.grant_path.read_text())
        self.client=None;self.allowed_binding=None
        self.binding={'provider':'openrouter','model':'qwen/qwen3.8-27b','adapter_version':'adr0786-authorized-experiment-v1',
            'endpoint_identity':hashlib.sha256(b'https://openrouter.ai/api/v1').hexdigest(),'trust_zone':'external','max_input_bytes':2_000_000}

    def validate_model(self):
        return {'verified':True,'mode':'policy-bound; actual provider checked on every response','model':self.binding['model']}

    def check_grant(self):
        g=self.grant
        if (sha(self.grant_path)!=self.grant_hash or g.get('authorized') is not True or
            g.get('schema_version')!='research-workflow-export-v1' or g.get('adr_id')!='ADR-0786' or
            g.get('model')!=self.binding['model'] or g.get('provider')!='openrouter' or
            g.get('upstream_provider')!='Parasail' or g.get('endpoint')!='https://openrouter.ai/api/v1' or
            sha(self.root/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')!=g['policy_sha256']):
            raise ContractError('research export grant or model policy changed')
        return g

    def authorize_workflow(self, request, binding):
        g=self.check_grant()
        expected={'question':g['question'],'principal':g['principal'],'document_ids':g['document_ids'],
            'session_id':g['session_id'],'request_id':g['request_id'],'as_of':None,'use_llm':True,
            'workflow_id':'risk_team_compare_workflow','workflow_version':'1.0.0','return_to':None}
        if request!=expected:raise ContractError('request outside exact research authorization')
        for k in ('generation_id','store_sha256','generation_manifest_sha256','document_ids','principal'):
            if binding[k]!=g[k]:raise ContractError('research source/principal binding mismatch: '+k)
        if binding['export_allowed'] is not False:raise ContractError('immutable source flag changed')
        source=self.root/g['generation_path']
        if sha(source/'manifest.json')!=g['generation_manifest_sha256']:raise ContractError('generation drift')
        with sqlite3.connect('file:'+str(source/'store.sqlite')+'?mode=ro',uri=True) as db:
            rows={k:v for k,v in db.execute('SELECT document_id,source_artifact_sha256 FROM document')}
        if any(rows.get(k)!=v['source_sha256'] for k,v in g['documents'].items()):raise ContractError('authorized source artifact drift')
        if set(g['document_ids'])!=set(g['documents']):raise ContractError('grant document scope mismatch')
        self.allowed_binding=digest(binding)
        return True

    def validate_authorization(self, context):
        self.check_grant()
        if self.allowed_binding is None or digest(context.binding)!=self.allowed_binding:
            raise ContractError('external call lacks exact authorized workflow binding')
        if context.request['question']!=self.grant['question'] or sorted(context.query['scope']['document_version_ids'])!=self.grant['document_ids']:
            raise ContractError('external question/scope changed')

    def send_once(self, *, body, ticket):
        g=self.check_grant()
        if self.allowed_binding is None:raise ContractError('no workflow authorization')
        if body.get('model')!=self.binding['model'] or body.get('stream') is not False:
            raise ContractError('wrong outgoing model/stream')
        from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError,ExperimentTransportError
        if self.client is None:
            self.client=ExperimentClient(self.root,self.output,max_calls=g['max_model_calls'],max_output_tokens=6400,max_repairs=0)
        payload=provider_request(body)
        try:
            raw=self.client.chat_completions(payload,phase='workflow',timeout_seconds=min(180,ticket['remaining_seconds']))
        except ExperimentFormatError as exc:
            raw=exc.response
            if raw:
                from semantic_runtime.legal_agent.model_contract import structured_content
                from semantic_runtime.legal_agent.output_contract import OutputContractError
                try:structured_content(raw['body_json'],require_complete=True)
                except OutputContractError as error:
                    error.response=raw;raise
            error=ProposalError('Qwen returned incomplete workflow proposal');error.response=raw;raise error from exc
        except ExperimentProviderError as exc:
            raw=exc.response;status=(raw or {}).get('status_code',0)
            if raw:raw['acceptance']='KNOWN_REJECTED' if status==429 else 'UNKNOWN' if status>=500 else 'ACCEPTED'
            raise TransportError('Qwen provider failure',retryable=status==429,unknown=status>=500,response=raw) from exc
        except ExperimentTransportError as exc:
            raise TransportError('Qwen transport outcome unknown',retryable=False,unknown=True) from exc
        if raw['body_json'].get('model')!=self.binding['model'] or raw['body_json'].get('provider')!='Parasail':
            raise ContractError('actual Qwen model/provider mismatch')
        raw['acceptance']='ACCEPTED'
        return raw
