"""Assemble the exact active ASSESS instructions without invoking a model."""
import ast
def assessment_prompt(root,ce,v8,narrative):
 tree=ast.parse((root/'02_BACKEND/semantic_runtime/legal_agent/completion_execution.py').read_text())
 policy=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='answer_policy' for t in n.targets))
 policy=ast.literal_eval(policy.body if isinstance(policy,ast.IfExp) else policy)
 return ce.MODERN_ASSESS_PROMPT+'\n'+v8.PROMPT+'\n'+narrative.ASSESS_GUIDANCE+'\n'+ce.CONDITION_GUIDANCE+policy
