
import os
import z3

from collections import defaultdict
from lark import Lark, Transformer, v_args
from behaviour_planning_smt.bss.features.base import DimensionConstructorSMT
from behaviour_planning_smt.bss.features.base import DimensionConstructorSimulator

class FunctionsSMT(DimensionConstructorSMT):
    def __init__(self, task, additional_information):
        super().__init__('functions', task, parse_functions_file(additional_information))
            
    def __encode__(self, encoder):
        self.var_domain = defaultdict(dict)
        self.functions_vars = []
        for _, fn in self.addinfo.items():
            varname, minval, maxval, delta = fn['name'], fn['min'], fn['max'], fn['delta']
            if not varname in encoder.up_fluent_to_z3: continue
            # assert varname in encoder.up_fluent_to_z3, f'Function {varname} is not in the encoder.'
            # get the last element of the list
            z3var = encoder.up_fluent_to_z3[varname][-1]
            # create the values boxes.
            boxes = [z3.And(z3var >= z3.RealVal(i, ctx=encoder.ctx), z3var < z3.RealVal(i + delta, ctx=encoder.ctx)) for i in range(minval, maxval-delta, delta)]
            
            boxes.append(z3.And(z3var >= z3.RealVal(maxval-delta, ctx=encoder.ctx), z3var <= z3.RealVal(maxval, ctx=encoder.ctx)))
            function_dimension_var = z3.Int(f'{self.name}-box-{varname}', ctx=encoder.ctx)

            self.formula.extend([box == (function_dimension_var == z3.IntVal(idx, ctx=encoder.ctx)) for idx, box in enumerate(boxes)])
            self.formula.append(function_dimension_var >= z3.IntVal(minval, ctx=encoder.ctx))
            self.formula.append(function_dimension_var <= z3.IntVal(maxval, ctx=encoder.ctx))
            
            self.functions_vars.append((varname, function_dimension_var))
            self.var_domain[varname] = set()
        
        # assert len(self.functions_vars) > 0, 'Functions dimension has no functions vars found in the encoder.'

    def expr(self, model):
        ret_value = []
        for name, predicate in self.functions_vars:
            predicate_value = model.evaluate(predicate, model_completion = True)
            ret_value.append(predicate == predicate_value)
            self.var_domain[name].add(predicate_value.as_long())
        return z3.And(ret_value)

class FunctionsSimulator(DimensionConstructorSimulator):
    def __init__(self, task, addinfo):
        super().__init__(task, 'function_value', parse_functions_file(addinfo))
    
    def plan_behaviour(self, plan):
        
        vars_values_over_time = defaultdict(list)
        for t, state in enumerate(plan.states):
            var_map = {str(e).replace('(','_').replace(')','').replace(' ','_').replace(',','') : e for e in state._values}
            for func_name, func_info in self.addinfo.items():
                if not func_info['name'] in var_map: continue
                vars_values_over_time[func_info['name']].append(state.get_value(var_map[func_info['name']]))
        
        # map the values.
        for _, fn in self.addinfo.items():
            varname, minval, maxval, delta = fn['name'], fn['min'], fn['max'], fn['delta']
            boxes = [(idx, i, i+delta) for idx, i in enumerate(range(minval, maxval-delta, delta))]
            current_value = vars_values_over_time[varname][-1].constant_value()
            vars_values_over_time[varname] = next(filter(lambda e: current_value >= e[1] and current_value < e[2], boxes), boxes[-1])[0]
        
        val = ','.join([f'{k}:{str(v)}' for k,v in vars_values_over_time.items()])
        self.domain.add(val)
        return ','.join(val)

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
