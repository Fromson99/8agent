"""Manifest-addressable adapters retaining the existing external stage contracts."""


def retrieve(inputs, parameters, context):
    session = context['legal_session']
    return {'retrieved': {'request': inputs['request'], 'query': session.context.query,
                          'retrieval': session.investigate()}}


def select(inputs, parameters, context):
    session = context['legal_session']
    value = inputs['retrieved']
    return {'selected': {**value, 'selection': session.select(value)}}


def assemble(inputs, parameters, context):
    return {'assembled': {**inputs['selected'], 'assembly': context['legal_session'].assemble()}}


def answer(inputs, parameters, context):
    result, control = context['legal_session'].answer_and_review(inputs['assembled'])
    return {'result': result, 'control': control}
