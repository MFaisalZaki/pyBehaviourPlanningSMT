import math 

import z3
from z3 import ModelRef
from unified_planning.plans import SequentialPlan


from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.utility_dimension import UtilityDimension

class UtilityValueSMT(UtilityDimension):
    def __init__(self, encoder, additional_information):
        super().__init__('utility-value', encoder, additional_information)
            
    def __encode__(self, encoder):
        
        # encode the common part of the utility dimension.
        super().__encode__(encoder)
        
        # create a utility variable to acculmate the utility values.
        self.utility_var = z3.Int('utility', encoder.ctx)
        self.var         = self.utility_var

        self.utility_vars = []
        for predicate_name, timestep_vars, utility_value in self.additional_information['goals-utilities']:
            utility_var = z3.Int(f'utility-({predicate_name})', encoder.ctx)
            self.utility_vars.append(utility_var)
            self.encodings.append(utility_var == z3.If(timestep_vars[-1], z3.IntVal(utility_value, encoder.ctx), z3.IntVal(0, encoder.ctx)))

        # set the utility variable to the sum of the utility values.
        self.encodings.append(self.utility_var == z3.Sum(self.utility_vars))
        self.encodings.append(self.utility_var >  z3.IntVal(0, encoder.ctx))
    
    def value(self, plan):
        retvalue = None
        if isinstance(plan, ModelRef):
            retvalue = plan.evaluate(self.var, model_completion = True)
        elif isinstance(plan, SequentialPlan):
            assert False, 'Value function is not implemented for this dimension for a plan.'
        else:
            raise TypeError(f"Unknown type for plan: {type(plan)}")
        # Update domain value.
        self.var_domain.add(str(retvalue))
        return retvalue

    def discretize(self, value):
        return value.as_long()