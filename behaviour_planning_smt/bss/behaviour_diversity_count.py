from collections import defaultdict
from unified_planning.shortcuts import SequentialSimulator


from behaviour_planning_smt.bss.features.goal_predicate_ordering import GoalPredicatesOrderingSimulator
from behaviour_planning_smt.bss.features.cost_bound_makespan_optimal import MakespanOptimalCostSimulator
from behaviour_planning_smt.bss.features.resources import ResourceCountSimulator
from behaviour_planning_smt.bss.features.utility_value import UtilityValueSimulator

features_map = {
    'go': GoalPredicatesOrderingSimulator,
    'cb': MakespanOptimalCostSimulator,
    'ru': ResourceCountSimulator,
    'uv': UtilityValueSimulator,
}


class BehaviourDiversityCount:
    def __init__(self, task, planlist, f):
        self.task      = task
        self.planslist = list(planlist)
        self.features  = {feat_name: features_map[feat_name](task, addinfo) for feat_name, addinfo in f}
        self.colleted_behaviours = set()

    def _simulate_(self, plan):
        states = []
        with SequentialSimulator(problem=self.task) as simulator:
            initial_state = simulator.get_initial_state()
            current_state = initial_state
            states += [current_state]
            for action_instance in plan.actions:
                current_state = simulator.apply(current_state, action_instance)
                if current_state is None: return []
                states.append(current_state)
        return states
    
    def _extract_behaviour_(self, plan, states):
        setattr(plan, 'states', states)
        return ' $$ '.join([dim.plan_behaviour(plan) for name, dim in self.features.items()])

    def count(self):
        if len(self.colleted_behaviours) == 0: self.optimise(k=len(self.planslist))
        return len(self.colleted_behaviours)
    
    def optimise(self, k):
        _behaviours = defaultdict(list)
        _ret_plans = []
        for idx, p in enumerate(self.planslist):
            states    = self._simulate_(p)
            behaviour = self._extract_behaviour_(p, states)
            self.colleted_behaviours.add(behaviour)
            setattr(self.planslist[idx], 'behaviour', behaviour)
            _behaviours[behaviour].append(self.planslist[idx])
        
        while not all([len(v) == 0 for v in _behaviours.values()]):
            for key in _behaviours.keys():
                if len(_ret_plans) >= k: break
                if len(_behaviours[key]) == 0: continue
                _ret_plans.append(_behaviours[key].pop())
        return _ret_plans