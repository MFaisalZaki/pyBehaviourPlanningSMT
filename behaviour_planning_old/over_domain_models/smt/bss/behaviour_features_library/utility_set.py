import math 

import z3
from z3 import ModelRef
from unified_planning.plans import SequentialPlan


from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.utility_dimension import UtilityDimension

class UtilitySetSMT(UtilityDimension):
    def __init__(self, encoder, additional_information):
        super().__init__('utility-set', encoder, additional_information)
            
    def __encode__(self, encoder):

        # encode the common part of the utility dimension.
        super().__encode__(encoder)
        
        # create a utility variable to acculmate the utility values.
        self.utility_var = z3.Int('utility', encoder.ctx)
        self.var         = self.utility_var

        self.utility_vars = []
        for predicate_name, timestep_vars, _ in self.additional_information['goals-utilities']:
            utility_var = z3.Bool(f'utility-set({predicate_name})', encoder.ctx)
            self.utility_vars.append(utility_var)
            self.encodings.append(timestep_vars[-1] == utility_var)
        
        self.encodings.append(z3.PbGe([(self.utility_vars[i], 1) for i in range(len(self.utility_vars))], 1))
        
    def value(self, plan):
        ret_value = []
        ret_value_str = []
        if isinstance(plan, ModelRef):
            for predicate in self.utility_vars:
                predicate_value = plan.evaluate(predicate, model_completion = True)
                ret_value.append(predicate == predicate_value)
                ret_value_str.append(str(ret_value[-1]).replace('\n', ''))
        elif isinstance(plan, SequentialPlan):
            assert False, 'Value function is not implemented for this dimension for a plan.'
        else:
            raise TypeError(f"Unknown type for plan: {type(plan)}")
        self.var_domain.add(', '.join(ret_value_str))
        return z3.And(ret_value)

    def discretize(self, value):
        """!
        This function should return the discretized value of the dimension.
        """
        return value
    
    def behaviour_expression(self, plan):
        return self.discretize(self.value(plan))
