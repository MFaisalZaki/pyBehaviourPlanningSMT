from collections import defaultdict
from unified_planning.shortcuts import SequentialSimulator
from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.qfuf_encoder import EncoderSequentialQFUF
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.resources import parse_resource_file
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.functions import parse_functions_file

# I hate this shit but I have no time to refactor everything properly.
# what dimensions we want to have a simulator version for it.
# GPO, Reosurce Count, Cost Bound, Utility value, Function value.

class DimSimulator:
    def __init__(self, task, name, addinfo):
        self.task = task
        self.name = name
        self.addinfo = addinfo

class GoalPredicatesOrderingSimulator(DimSimulator):
    def __init__(self, task, addinfo=None):
        super().__init__(task, 'goal_predicate_ordering', addinfo)
        from unified_planning.model.walkers.free_vars import FreeVarsExtractor
        vars = list(map(lambda expr: FreeVarsExtractor().get(expr), self.task.goals))
        self.vars = [elem for s in vars for elem in s]
    
    def plan_behaviour(self, plan):
        _time_step_history = defaultdict(list)
        for t, state in enumerate(plan.states):
            for g in self.vars:
                _time_step_history[g].append(state.get_value(g).is_true())
        return 'gpo:' + '->'.join(map(lambda e: str(e[0]), sorted([(g, next((i for i, x in enumerate(_time_step_history[g]) if x), -1)) for g in self.vars], key=lambda e:e[1])))

class MakespanOptimalCostSimulator(DimSimulator):
    def __init__(self, task, addinfo):
        super().__init__(task, 'makespan_optimal', addinfo)
    
    def plan_behaviour(self, plan):
        return 'cb:' + str(len(plan.actions))

class ResourceCountSimulator(DimSimulator):
    def __init__(self, task, addinfo):
        super().__init__(task, 'resource_count', {'resources_list': parse_resource_file(addinfo)})
        self.addinfo['objects'] = set(map(str,filter(lambda e: e.name in set(map(lambda e: e['name'], self.addinfo['resources_list'].values())), self.task.all_objects)))
    
    def plan_behaviour(self, plan):
        resource_usage = {o: 0 for o in self.addinfo['objects']}
        for action in plan.actions:
            for used_resource in set.intersection(set(map(str, action.actual_parameters)), set(self.addinfo['objects'])):
                resource_usage[used_resource] += 1
        return 'rc:' + str(len(list(filter(lambda e: e[1] > 0, resource_usage.items()))))

class UtilityValueSimulator(DimSimulator):
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
        return 'uv:' + str(sum(achieved_utilities.values())) + ' -- ' + ','.join(f'{k}={str(v)}' for k,v in achieved_utilities.items())

class FunctionsSimulator(DimSimulator):
    def __init__(self, task, addinfo):
        super().__init__(task, 'function_value', {'functions_list': parse_functions_file(addinfo)})
    
    def plan_behaviour(self, plan):
        
        vars_values_over_time = defaultdict(list)
        for t, state in enumerate(plan.states):
            var_map = {str(e).replace('(','_').replace(')','').replace(' ','_').replace(',','') : e for e in state._values}
            for func_name, func_info in self.addinfo['functions_list'].items():
                if not func_info['name'] in var_map: continue
                vars_values_over_time[func_info['name']].append(state.get_value(var_map[func_info['name']]))
        return ','.join([f'{k}:{str(v[-1])}' for k,v in vars_values_over_time.items()])

class BehaviourCountSimulator:
    def __init__(self, task, planlist, dims):
        self.task      = task
        self.dims      = dims
        self.planslist = planlist
        self.colleted_behaviours = set()
        self.bspace = [d(task, addinfo) for (d, addinfo) in dims]

    def _simulate_(self, plan):
        states = []
        with SequentialSimulator(problem=self.task) as simulator:
            initial_state = simulator.get_initial_state()
            current_state = initial_state
            states += [current_state]
            for action_instance in plan.actions:
                current_state = simulator.apply(current_state, action_instance)
                if current_state is None:
                    assert False, "No cost available since the plan is invalid."
                states.append(current_state)
            pass
        return states
    
    def _extract_behaviour_(self, plan, states):
        setattr(plan, 'states', states)
        return ' $$ '.join([dim.plan_behaviour(plan) for dim in self.bspace])

    def count(self):
        if len(self.colleted_behaviours) == 0: self.selected_plans(k=len(self.planslist))
        return len(self.colleted_behaviours)
    
    def selected_plans(self, k):
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