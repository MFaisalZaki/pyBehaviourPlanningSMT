from collections import defaultdict
import os
from lark import Lark, Transformer, v_args
import z3
import z3
from z3 import ModelRef
from unified_planning.plans import SequentialPlan

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.base import DimensionConstructorSMT

class FunctionsSMT(DimensionConstructorSMT):
    def __init__(self, encoder, additional_information):
        super().__init__('functions', encoder, parse_functions_file(additional_information))
            
    def __encode__(self, encoder):
        self.var_domain = defaultdict(dict)
        self.functions_vars = []
        for _, fn in self.additional_information.items():
            varname, minval, maxval, delta = fn['name'], fn['min'], fn['max'], fn['delta']
            if not varname in encoder.up_fluent_to_z3: continue
            # assert varname in encoder.up_fluent_to_z3, f'Function {varname} is not in the encoder.'
            # get the last element of the list
            z3var = encoder.up_fluent_to_z3[varname][-1]
            # create the values boxes.
            boxes = [z3.And(z3var >= z3.RealVal(i, ctx=encoder.ctx), z3var < z3.RealVal(i + delta, ctx=encoder.ctx)) for i in range(minval, maxval-delta, delta)]
            
            boxes.append(z3.And(z3var >= z3.RealVal(maxval-delta, ctx=encoder.ctx), z3var <= z3.RealVal(maxval, ctx=encoder.ctx)))
            function_dimension_var = z3.Int(f'{self.name}-box-{varname}', ctx=encoder.ctx)

            self.encodings.extend([box == (function_dimension_var == z3.IntVal(idx, ctx=encoder.ctx)) for idx, box in enumerate(boxes)])
            self.encodings.append(function_dimension_var >= z3.IntVal(minval, ctx=encoder.ctx))
            self.encodings.append(function_dimension_var <= z3.IntVal(maxval, ctx=encoder.ctx))
            
            self.functions_vars.append((varname, function_dimension_var))
            self.var_domain[varname] = set()
        
        assert len(self.functions_vars) > 0, 'Functions dimension has no functions vars found in the encoder.'

    def value(self, plan):
        ret_value = []
        if isinstance(plan, ModelRef):
            for name, predicate in self.functions_vars:
                predicate_value = plan.evaluate(predicate, model_completion = True)
                ret_value.append(predicate == predicate_value)
                self.var_domain[name].add(predicate_value.as_long())
        elif isinstance(plan, SequentialPlan):
            assert False, 'Value function is not implemented for this dimension for a plan.'
        else:
            raise TypeError(f"Unknown type for plan: {type(plan)}")
        return z3.And(ret_value)

    def discretize(self, value):
        return value
    
    def behaviour_expression(self, plan):
        return self.discretize(self.value(plan))

class ResourceTransformer(Transformer):
    def resource_line(self, token):
        return {
            'name':  token[0].value,
            'min':   int(token[1].value),
            'max':   int(token[2].value),
            'delta': int(token[3].value)
        }

def parse_functions_file(inputfile):
    def read_function_file(resource_input):
        def construct_parser():
            grammar = r'''
                start: resource_line+
                resource_line: "(:function" (NAME | NAME_WITH_PARENTHESIS) MIN MAX DELTA ")"
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
        assert os.path.exists(inputfile), f'The function file {inputfile} does not exist.'
        for resource in read_function_file(inputfile):
            addition_informaion[resource['name']] = resource
    return addition_informaion
