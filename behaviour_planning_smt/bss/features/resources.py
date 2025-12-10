import os
import z3

from collections import defaultdict
from lark import Lark, Transformer, v_args
from behaviour_planning_smt.bss.features.base import DimensionConstructorSMT
from behaviour_planning_smt.bss.features.base import DimensionConstructorSimulator

class Resources(DimensionConstructorSMT):
    def __init__(self, name, task, additional_information):
        # parse the additional information from the provided file.
        additional_information = parse_resource_file(additional_information)
        self.resources_list = defaultdict(dict)
        # For every resource list all of its action names.
        for r in [r['name'] for k, r in additional_information.items()]:
            self.resources_list[r] = task.encoder.actions_that_uses_resource(r)
            if len(self.resources_list[r]) == 0: del self.resources_list[r]

        super().__init__(name, task, additional_information)

class ResourceCountSMT(Resources):
    def __init__(self, task, additional_information):
        super().__init__('ru', task, additional_information)

    def __encode__(self, encoder):

        self.resoruces_count = z3.Int(self.name, ctx=encoder.ctx)
        self.var = self.resoruces_count
        
        resoruce_count_vars = []
        for resource, actions in self.resources_list.items():
            # Now create two real variables.
            resource_used_z3_var = z3.Int(f'ru-{resource}', ctx=encoder.ctx) 
            # Add the constraints.
            self.formula.append(resource_used_z3_var == z3.If(z3.Or(actions), \
                                                        z3.IntVal(1, ctx=encoder.ctx), z3.IntVal(0, ctx=encoder.ctx), \
                                                        ctx=encoder.ctx))
            resoruce_count_vars.append(resource_used_z3_var)

        self.formula.append(self.resoruces_count == z3.Sum(resoruce_count_vars))

    def expr(self, model):
        retvalue = None
        retvalue = model.evaluate(self.var, model_completion = True)
        self.var_domain.add(str(retvalue))
        return self.var == retvalue

class ResourceCountSimulator(DimensionConstructorSimulator):
    def __init__(self, task, addinfo):
        super().__init__(task, 'ru', {'resources_list': parse_resource_file(addinfo)})
        self.addinfo['objects'] = set(map(str,filter(lambda e: e.name in set(map(lambda e: e['name'], self.addinfo['resources_list'].values())), self.task.all_objects)))
    
    def plan_behaviour(self, plan):
        resource_usage = {o: 0 for o in self.addinfo['objects']}
        for action in plan.actions:
            for used_resource in set.intersection(set(map(str, action.actual_parameters)), set(self.addinfo['objects'])):
                resource_usage[used_resource] += 1
        return f'{self.name}:' + str(len(list(filter(lambda e: e[1] > 0, resource_usage.items()))))




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
