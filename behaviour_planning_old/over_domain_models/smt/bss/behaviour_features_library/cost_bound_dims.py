from collections import defaultdict
from copy import deepcopy

import z3

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.base import DimensionConstructorSMT

class CostBoundSMT(DimensionConstructorSMT):
    def __init__(self, name, encoder, action_cost_fn, additional_information):
        self.action_cost_fn       = action_cost_fn
        self.cost_bound_factor    = additional_information.get('cost-bound-factor', None)
        self.optimal_plan_length  = additional_information.get('optimal-plan-length', None)
        self.is_oversubscription  = additional_information.get('is-oversubscription', False)

        assert self.cost_bound_factor is not None, f"Cost bound factor is not provided for the dimension {name}."
        assert self.optimal_plan_length is not None, f"Optimal plan length is not provided for the dimension {name}."

        super().__init__(name, encoder, additional_information)
        
    def __encode__(self, encoder):
        # TODO: We need to get this information from the encoder itself.
        assert False, "For now we consider makespan optimal"

    def discretize(self, value):
        return value.as_long()
    