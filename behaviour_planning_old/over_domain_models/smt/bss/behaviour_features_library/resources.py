from collections import defaultdict
import os
from lark import Lark, Transformer, v_args
import z3

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.base import DimensionConstructorSMT

class Resources(DimensionConstructorSMT):
    def __init__(self, name, encoder, additional_information):

        # parse the additional information from the provided file.
        additional_information = parse_resource_file(additional_information)

        self.resources_list = defaultdict(dict)
        # For every resource list all of its action names.
        for r in [r['name'] for k, r in additional_information.items()]:
            self.resources_list[r] = encoder.actions_that_uses_resource(r)
            if len(self.resources_list[r]) == 0: del self.resources_list[r]
            
        super().__init__(name, encoder, additional_information)

    def value(self, plan):
        assert False, 'Not implemented'

    def discretize(self, value):
        return value

class ResourceTransformer(Transformer):
    def resource_line(self, token):
        return {
            'name': token[0].value,
            'min':  int(token[1].value),
            'max':  int(token[2].value),
            'delta': int(token[3].value)
        }

def parse_resource_file(inputfile):
    def read_resource_file(resource_input):
        def construct_parser():
            grammar = r'''
                start: resource_line+
                resource_line: "(:resource" (NAME | NAME_WITH_PARENTHESIS) MIN MAX DELTA ")"
                NAME: /[a-zA-Z_][\w-]*/
                NAME_WITH_PARENTHESIS: /[a-zA-Z_]\w*\([^)]*\)/
                MIN: /[0-9]+/
                MAX: /[0-9]+/
                DELTA: /[0-9]+/
                %ignore /\s+/
            '''
            parser = Lark(grammar, parser='lalr', transformer=v_args(inline=True))
            return parser
        # readlines in reource_input
        with open(resource_input, 'r') as f:
            resource_input = f.readlines()
        resource_input = ''.join(resource_input)
        parser = construct_parser()
        tree = parser.parse(resource_input)
        transformer = ResourceTransformer()
        resources = transformer.transform(tree)
        return resources.children

    addition_informaion = defaultdict(dict)
    if inputfile:
        assert os.path.exists(inputfile), f'The resources file {inputfile} does not exist.'
        for resource in read_resource_file(inputfile):
            addition_informaion[resource['name']] = resource
    return addition_informaion
