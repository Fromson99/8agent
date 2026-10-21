"""Parent-graph compiler shared with the document grammar. Instance editing removed."""
from .recipe_output import ResponseError, StructureDecisionError
import copy
from collections import defaultdict

ROOT = '$document'


def levels_from_parents(parents, catalog):
    if set(parents) != set(catalog):
        raise StructureDecisionError('Parent map must contain every catalog family exactly once')
    grouped = defaultdict(list)
    def depth(family, path=()):
        if family in path: raise StructureDecisionError('Parent cycle: '+str(path+(family,)))
        parent = parents[family]
        if not isinstance(parent,str) or (parent != ROOT and parent not in catalog):
            raise StructureDecisionError('Unknown parent family: '+str(parent))
        return 0 if parent == ROOT else 1 + depth(parent,path+(family,))
    for family in catalog: grouped[depth(family)].append(family)
    if len(grouped)>16: raise StructureDecisionError('Parent depth exceeds recipe contract')
    return [grouped[k] for k in sorted(grouped)]

