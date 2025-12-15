
import z3

from collections import defaultdict, namedtuple

from unified_planning.model.metrics import Oversubscription
from behaviour_planning_smt.bss.features.base import DimensionConstructorSMT
from behaviour_planning_smt.bss.features.base import DimensionConstructorSimulator

class UtilityValueSMT(DimensionConstructorSMT):
    def __init__(self, task, additional_information):
        # extract the goal predicates utilties.
        oversubscription_metrics = list(filter(lambda metric: isinstance(metric, Oversubscription), task.encoder.task.quality_metrics))
        assert len(oversubscription_metrics) == 1, 'The task should have oversubscription metric to use the utility dimension.'
        oversubscription_metrics = oversubscription_metrics.pop()
        assert len(oversubscription_metrics.goals) > 0, 'The oversubscription metric should have goals with utility value per goal.'
        
        # map up goal predicates to z3 variables.
        additional_information['goals-utilities-map'] = []
        u_fn = namedtuple('u_fn', 'name timestep_vars utility')
        for up_goal_predicate, utility in oversubscription_metrics.goals.items():
            up_goal_predicate_name   = str(up_goal_predicate)
            goal_predicate_vars_list = [task.encoder._expr_to_z3(up_goal_predicate, t, task.encoder.ctx) for t in range(1, len(task.encoder))]
            utility_var_value        = z3.IntVal(utility, task.encoder.ctx)
            additional_information['goals-utilities-map'].append(u_fn(up_goal_predicate_name, goal_predicate_vars_list, utility_var_value))
        assert len(additional_information['goals-utilities-map']) == len(oversubscription_metrics.goals), 'The number of goals in the oversubscription metric should be equal to the number of goal predicates.'

        super().__init__('uv', task, additional_information)
            
    def __encode__(self, encoder):
        # create a utility variable to acculmate the utility values.
        self.utility_var  = z3.Int('utility', encoder.ctx)
        self.var          = self.utility_var
        self.utility_vars = []
        for predicate_name, timestep_vars, utility_value in self.addinfo['goals-utilities-map']:
            utility_var = z3.Int(f'utility-({predicate_name})', encoder.ctx)
            self.utility_vars.append(utility_var)
            self.formula.append(utility_var == z3.If(timestep_vars[-1], z3.IntVal(utility_value, encoder.ctx), z3.IntVal(0, encoder.ctx)))

        # set the utility variable to the sum of the utility values.
        self.formula.append(self.utility_var == z3.Sum(self.utility_vars))
        self.formula.append(self.utility_var >  z3.IntVal(0, encoder.ctx))
    
    def expr(self, model):
        retvalue = model.evaluate(self.var, model_completion = True)
        # Update domain value.
        self.var_domain.add(str(retvalue))
        return self.var == retvalue


class UtilityValueSimulator(DimensionConstructorSimulator):
    def __init__(self, task, addinfo):
        super().__init__(task, 'utility_value', addinfo)
        from unified_planning.model.walkers.free_vars import FreeVarsExtractor
        vars = list(map(lambda expr: FreeVarsExtractor().get(expr), self.task.goals))
        self.vars = [(str(elem), elem) for s in vars for elem in s]
    
    def plan_behaviour(self, plan):
        achieved_utilities = defaultdict(list)
        _acheived_utilities = defaultdict(list)
        for state in plan.states:
            for var, util in self.addinfo['goals-utilities'].items():
                _acheived_utilities[var].append(state.get_value(var).is_true())

        for var, utils in _acheived_utilities.items():
            achieved_utilities[str(var)] = self.addinfo['goals-utilities'][var] if any(utils) else 0
        return f'{self.name}:' + str(sum(achieved_utilities.values())) + ' -- ' + ','.join(f'{k}={str(v)}' for k,v in achieved_utilities.items())
