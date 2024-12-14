from copy import deepcopy, copy
from collections import defaultdict
from collections import OrderedDict

import z3

from unified_planning.model.metrics import Oversubscription
from unified_planning.plans import SequentialPlan
from unified_planning.plans import ActionInstance

from pypmt.encoders.R2E import EncoderRelaxed2Exists
from pypmt.encoders.utilities import str_repr, varstr_repr

from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.common import actions_that_uses_resource, disable_actions_at_t, enabled_actions_vars, get_actions_vars, extend, convert, get_all_action_vars
from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.smt_sequential_plan import SMTSequentialPlan

def encode_n(self, formula_length, disable_after_goal_state_actions):
    """!
    This method encodes a formula into a list of assertions.

    It iterates over the formula length, encoding each step into a formula and appending the 'goal' state to the goal_states list.
    If it's the first step, it also appends the 'initial' state to the assertions list.
    It then removes 'goal', 'initial', 'sem', and 'objective' (if present) from the formula.
    Any remaining items in the formula are appended to the assertions list if they are not None.

    After encoding the formula, it adds the execution semantics to the assertions list.
    It does this by mapping each action in up_actions_to_z3 to its corresponding value at time t.
    If it's the last step of the formula, the number of actions is set to 0, otherwise it's set to 1.
    It then creates a PbEq (pseudo-boolean equality) constraint with the actions and the number of actions, and appends it to the assertions list.

    Finally, it encodes the possible goal states into a PbGe (pseudo-boolean greater or equal) constraint and appends it to the assertions list.

    Parameters:
    formula_length (int): The length of the formula to encode.

    Returns:
    list: The list of assertions resulting from the encoding.
    """

    self.task_is_oversubscription_planning = len(list(filter(lambda metric: isinstance(metric, Oversubscription), self.task.quality_metrics))) > 0
    assert not self.task_is_oversubscription_planning, 'The relaxed to exists encoder does not support oversubscription planning.'

    self.goal_states = []
    self.assertions = []
    self.goal_predicates_vars = defaultdict(dict)
    for t in range(0, formula_length):
        formula = self.encode(t)
        # strip the extra And if available in formula['goal']
        self.goal_states.append(formula['goal'] if not 'And(' in str(formula['goal'].arg(0)) else formula['goal'].arg(0))
        if t == 0: self.assertions.append(formula['initial'])
        del formula['goal']
        del formula['initial']
        if 'objective' in formula: del formula['objective']
        for k, v in formula.items():
            if v is not None: self.assertions.append(v)

    # define the horizon variable.
    self.horizon_var = z3.Int('horizon', ctx=self.ctx)
    self.assertions.append(self.horizon_var >  z3.IntVal(0, ctx=self.ctx))
    self.assertions.append(self.horizon_var <= z3.IntVal(formula_length, ctx=self.ctx))
        
    # extract goal predicates.
    for t, goal_predicate in enumerate(self.goal_states):
        for idx, predicate in enumerate(goal_predicate.children()):
            if not idx in self.goal_predicates_vars: self.goal_predicates_vars[idx] = []
            # get predicate name.
            predicate_name = varstr_repr(predicate)
            # get the chain variables.
            predicate_chain_vars = list(OrderedDict.fromkeys(self.chain_lookup[predicate_name]))
            self.goal_predicates_vars[idx].extend([self.up_fluent_to_z3[n][t+1] for n in predicate_chain_vars])

    # deny any empty steps.
    t_minus_1_actions_vars = self.get_actions_vars(0)
    for t in range(1, len(self)):
        t_actions_vars = self.get_actions_vars(t)
        self.assertions.append(z3.Implies(z3.Or(t_actions_vars), z3.PbEq([(a, 1) for a in t_minus_1_actions_vars], 1)))
        t_minus_1_actions_vars = copy(t_actions_vars)

    # update the goal_states for oversubscription planning.
    _fn = z3.Or if self.task_is_oversubscription_planning else z3.And
    self.goal_states = list(map(lambda x: _fn(x.children()), self.goal_states))
    
    # encode possible goal states.
    self.assertions.append(z3.PbGe([(g,1) for g in self.goal_states], 1))

    # locate the first goal state step.
    offset = 0 if self.task_is_oversubscription_planning else 1
    for idx, goal_state in enumerate(self.goal_states):
        pre_goal_states = [goal_state] + [z3.Not(s, ctx=self.ctx) for s in self.goal_states[:idx]]
        self.assertions.append(z3.And(pre_goal_states) == (self.horizon_var == z3.IntVal(idx+offset, ctx=self.ctx)))

    # we need to check this, since in the case of appending plans, we could get plans that undo goal states to add more actions.
    if not disable_after_goal_state_actions:
        # Force no actions to be taken after the first goal state.
        for t, goal_state in enumerate(self.goal_states):
            after_goal_state_actions = []
            for t2 in range(t+1, len(self)):
                after_goal_state_actions.extend(self.get_actions_vars(t2))
            self.assertions.append(goal_state == z3.PbEq([(var, 1) for var in after_goal_state_actions], 0, ctx=self.ctx))

    return self.assertions

def extract_plan(self, model, horizon):
    plan = SequentialPlan([])
    selected_actions_vars = []
    if not model: return plan
    ## linearize partial-order plan
    for t in range(0, horizon+1):
        for action in self:
            if z3.is_true(model[self.up_actions_to_z3[action.name][t]]):
                plan.actions.append(ActionInstance(action))
                selected_actions_vars.append(self.up_actions_to_z3[action.name][t])

    for compilation_r in reversed(self.compilation_results):
        plan = plan.replace_action_instances(compilation_r.map_back_action_instance)

    return SMTSequentialPlan(plan, self.task, selected_actions_vars)


# Update the encoder apis.
# Store all goal states.
setattr(EncoderRelaxed2Exists, 'goal_states', [])
setattr(EncoderRelaxed2Exists, 'goal_predicates_vars', defaultdict(dict))
# Store all assertions.
setattr(EncoderRelaxed2Exists, 'assertions', [])
setattr(EncoderRelaxed2Exists, 'encode_n', encode_n)
setattr(EncoderRelaxed2Exists, 'extend', extend)
setattr(EncoderRelaxed2Exists, 'get_actions_vars', get_actions_vars)
setattr(EncoderRelaxed2Exists, 'enabled_actions_vars', enabled_actions_vars)
setattr(EncoderRelaxed2Exists, 'disable_actions_at_t', disable_actions_at_t)
setattr(EncoderRelaxed2Exists, 'extend', extend)
setattr(EncoderRelaxed2Exists, 'convert', convert)
setattr(EncoderRelaxed2Exists, 'extract_plan', extract_plan)
setattr(EncoderRelaxed2Exists, 'get_all_action_vars', get_all_action_vars)
setattr(EncoderRelaxed2Exists, 'horizon_var', None)
setattr(EncoderRelaxed2Exists, 'actions_that_uses_resource', actions_that_uses_resource)
setattr(EncoderRelaxed2Exists, 'task_is_oversubscription_planning', False)