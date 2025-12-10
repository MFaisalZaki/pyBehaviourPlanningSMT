import math
from collections import namedtuple
import z3
from unified_planning.model.metrics import Oversubscription
from unified_planning.engines.results import CompilerResult
from pypmt.encoders.utilities import varstr_repr

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.base import DimensionConstructorSMT

class UtilityDimension(DimensionConstructorSMT):
    def __init__(self, name, encoder, additional_information):
        # extract the goal predicates utilties.
        oversubscription_metrics = list(filter(lambda metric: isinstance(metric, Oversubscription), encoder.task.quality_metrics))
        assert len(oversubscription_metrics) == 1, 'The task should have oversubscription metric to use the utility dimension.'
        oversubscription_metrics = oversubscription_metrics.pop()
        assert len(oversubscription_metrics.goals) > 0, 'The oversubscription metric should have goals with utility value per goal.'
        
        # map up goal predicates to z3 variables.
        additional_information['goals-utilities'] = []
        u_fn = namedtuple('u_fn', 'name timestep_vars utility')
        for up_goal_predicate, utility in oversubscription_metrics.goals.items():
            up_goal_predicate_name   = str(up_goal_predicate)
            goal_predicate_vars_list = [encoder._expr_to_z3(up_goal_predicate, t, encoder.ctx) for t in range(1, len(encoder))]
            utility_var_value        = z3.IntVal(utility, encoder.ctx)
            additional_information['goals-utilities'].append(u_fn(up_goal_predicate_name, goal_predicate_vars_list, utility_var_value))

        assert len(additional_information['goals-utilities']) == len(oversubscription_metrics.goals), 'The number of goals in the oversubscription metric should be equal to the number of goal predicates.'
        super().__init__(name, encoder, additional_information)
            
    def __encode__(self, encoder):
        pass
        # cost_bound_value = self.additional_information.get('cost-bound-factor', None)
        # assert cost_bound_value is not None, 'Cost bound factor is not provided.'

        # # compute the cost bound value.
        # cost_bound_value = int(math.floor(cost_bound_value*len(encoder)))

        # # first limit the horizon var to this value.
        # self.encodings.append(encoder.horizon_var <= z3.IntVal(cost_bound_value, encoder.ctx))

        # # disable the actions after the cost bound value.
        # disabled_actions = []
        # for t in range(cost_bound_value+1, len(encoder)):
        #     disabled_actions += encoder.disable_actions_at_t(t)

        # if len(disabled_actions) > 0: self.encodings.append(z3.And(disabled_actions))