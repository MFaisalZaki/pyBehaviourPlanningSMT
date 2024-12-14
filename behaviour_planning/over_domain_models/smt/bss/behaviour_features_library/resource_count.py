
import z3

from z3 import ModelRef
from unified_planning.plans import SequentialPlan

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.resources import Resources

class ResourceCountSMT(Resources):
    def __init__(self, encoder, additional_information):
        super().__init__('resources-count', encoder, additional_information)

    def __encode__(self, encoder):

        self.resoruces_count = z3.Int(self.name, ctx=encoder.ctx)
        self.var = self.resoruces_count
        
        resoruce_count_vars = []
        for resource, actions in self.resources_list.items():
            # Now create two real variables.
            # actions_count_z3_var = z3.Int(f'actions-count-for-object-{resource}', ctx=encoder.ctx)
            resource_used_z3_var = z3.Int(f'resource-{resource}-used', ctx=encoder.ctx) 
            # Add the constraints.
            # self.encodings.append(actions_count_z3_var == z3.Sum(actions))
            # self.encodings.append(resource_used_z3_var == z3.If(actions_count_z3_var > z3.IntVal(0, ctx=encoder.ctx), \
            #                                               z3.IntVal(1, ctx=encoder.ctx), z3.IntVal(0, ctx=encoder.ctx), \
            #                                               ctx=encoder.ctx))
            self.encodings.append(resource_used_z3_var == z3.If(z3.Or(actions), \
                                                          z3.IntVal(1, ctx=encoder.ctx), z3.IntVal(0, ctx=encoder.ctx), \
                                                          ctx=encoder.ctx))
            resoruce_count_vars.append(resource_used_z3_var)

        self.encodings.append(self.resoruces_count == z3.Sum(resoruce_count_vars))

    def value(self, plan):
        retvalue = None
        if isinstance(plan, ModelRef):
            retvalue = plan.evaluate(self.var, model_completion = True)
        elif isinstance(plan, SequentialPlan):
            assert False, 'Value function is not implemented for this dimension for a plan.'
        else:
            raise TypeError(f"Unknown type for plan: {type(plan)}")
        self.var_domain.add(str(retvalue))
        return retvalue

    def discretize(self, value):
        return value
