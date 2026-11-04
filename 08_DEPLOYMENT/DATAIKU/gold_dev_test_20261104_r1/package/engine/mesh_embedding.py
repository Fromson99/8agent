"""Dataiku Mesh adapter; deployment values are supplied only through environment."""
import math
import os
from structure_segments import POLICY


def resolve_settings(environment, project_variables):
    values = dict(environment)
    for name in ('LEGAL_EMBED_LLM_ID', 'LEGAL_EMBED_DIMENSIONS'):
        if not str(values.get(name, '')).strip() and name in project_variables:
            values[name] = str(project_variables[name])
    return settings(values)


def settings(env=None):
    env = os.environ if env is None else env
    model = env.get('LEGAL_EMBED_LLM_ID', '').strip()
    if not model:
        raise ValueError('LEGAL_EMBED_LLM_ID_REQUIRED')
    dimensions = int(env.get('LEGAL_EMBED_DIMENSIONS', ''))
    if not 1 <= dimensions <= 4096:
        raise ValueError('LEGAL_EMBED_DIMENSIONS_INVALID')
    return {'model': model, 'revision': model, 'dimensions': dimensions,
            'metric': 'COSINE', 'normalization': 'l2', 'transport': 'dataiku-llm-mesh'}


def encode(project, config, texts):
    if not 1 <= len(texts) <= 16 or any(not isinstance(t, str) or not t.strip() or len(t) > POLICY['max_input_chars'] for t in texts):
        raise ValueError('EMBED_INPUT_INVALID')
    request = project.get_llm(config['model']).new_embeddings(text_overflow_mode='FAIL')
    for text in texts:
        request.add_text(text)
    response = request.execute()  # One SDK attempt; caller records intent before entering.
    rows = [list(row) for row in response.get_embeddings()]
    if len(rows) != len(texts):
        raise ValueError('EMBED_COUNT_INVALID')
    result = []
    for row in rows:
        if len(row) != config['dimensions'] or any(type(x) not in (int, float) or not math.isfinite(x) for x in row):
            raise ValueError('EMBED_VALUES_INVALID')
        norm = math.sqrt(sum(x*x for x in row))
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError('EMBED_NORM_INVALID')
        result.append([x/norm for x in row])
    return result
