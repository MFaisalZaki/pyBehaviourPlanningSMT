
from copy import deepcopy, copy
from collections import defaultdict

import z3

from unified_planning.model.metrics import Oversubscription
from unified_planning.plans import SequentialPlan
from unified_planning.plans import ActionInstance
from unified_planning.engines.results import CompilerResult

from pypmt.encoders.basic import EncoderSequential, EncoderForall
from pypmt.encoders.utilities import str_repr

from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.common import actions_that_uses_resource, disable_actions_at_t, enabled_actions_vars, get_actions_vars, extend, convert, get_all_action_vars
from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.smt_sequential_plan import SMTSequentialPlan
from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.utilities import flattern_expression

# append some extra functions to the EncoderSequential.
def encode_n(self, **kwargs):
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
    formula_length = kwargs.get('formula_length', None)
    assert formula_length is not None, 'formula_length is required to encode the formula.'
    disable_after_goal_state_actions = kwargs.get('disable_after_goal_state_actions', False)
    horizon_planning = kwargs.get('horizon_planning', False)
    skip_actions = kwargs.get('skip_actions', False)

    self.task_is_oversubscription_planning = len(list(filter(lambda metric: isinstance(metric, Oversubscription), self.task.quality_metrics))) > 0

    self.goal_states = []
    self.assertions = []
    self.goal_predicates_vars = defaultdict(dict)

    flatten_args = lambda expr: [expr] if not (z3.is_and(expr) or z3.is_or(expr)) else [arg for child in expr.children() for arg in flatten_args(child)]
    for t in range(0, formula_length):
        formula = self.encode(t)
        nested_and = all([z3.is_and(p) for p in formula['goal'].children()])
        nested_or  = all([z3.is_or(p) for p in formula['goal'].children()])
        _fn = z3.And if nested_and else z3.Or
        # strip the extra And if available in formula['goal']
        # This is a bug we need to fix this. 
        # self.goal_states.append(_fn(flattern_expression(formula['goal'])) if (nested_and or nested_or) else formula['goal'])
        # self.goal_states.append(formula['goal'] if not 'And(' in str(formula['goal'].arg(0)) else formula['goal'].arg(0))
        self.goal_states.append(flattern_expression(formula['goal']))
        if t == 0: self.assertions.append(formula['initial'])
        del formula['goal']
        del formula['initial']
        del formula['sem']
        if 'objective' in formula: del formula['objective']
        for k, v in formula.items():
            if v is not None: self.assertions.append(v)
    
    # define the horizon variable.
    self.horizon_var = z3.Int('horizon', ctx=self.ctx)
    self.assertions.append(self.horizon_var >  z3.IntVal(0, ctx=self.ctx))
    self.assertions.append(self.horizon_var <= z3.IntVal(formula_length, ctx=self.ctx))
    
    # extract goal predicates.
    for goal_predicate in self.goal_states:
        for idx, predicate in enumerate(goal_predicate.children()):
            if not idx in self.goal_predicates_vars: self.goal_predicates_vars[idx] = []
            self.goal_predicates_vars[idx].append(predicate)
    
    # deny any empty steps.
    t_minus_1_actions_vars = self.get_actions_vars(0)
    for t in range(1, len(self)-1):
        t_actions_vars = self.get_actions_vars(t)
        self.assertions.append(z3.Implies(z3.Or(t_actions_vars), z3.PbEq([(a, 1) for a in t_minus_1_actions_vars], 1)))
        t_minus_1_actions_vars = copy(t_actions_vars)

    # add the extection sematics.
    if not skip_actions:
        for t in range(0, len(self)-1):
            actions = list(map(lambda x: x[t], self.up_actions_to_z3.values()))
            self.assertions.append(z3.PbLe([(var, 1) for var in actions], 1))

    # disable the actions in the last step of the formula.
    last_step_actions = list(map(lambda x: x[len(self)-1], self.up_actions_to_z3.values()))
    #self.assertions.append(z3.PbEq([(var, 1) for var in last_step_actions], 0, ctx=self.ctx))
    self.assertions.append(z3.Not(z3.Or(last_step_actions), ctx=self.ctx))

    # encode possible goal states.
    if horizon_planning:
        self.horizon_var = z3.IntVal(len(self)-1, ctx=self.ctx)
    else:
        # update the goal_states for oversubscription planning.
        _fn = z3.Or if self.task_is_oversubscription_planning else z3.And
        self.goal_states = list(map(lambda x: _fn(x.children()), self.goal_states))

        # encode possible goal states.
        self.assertions.append(z3.Or(self.goal_states))

        # locate the first goal state step.
        offset = 0 if self.task_is_oversubscription_planning else 1
        for idx, goal_state in enumerate(self.goal_states):
            pre_goal_states = [goal_state] if idx == 0 else [goal_state, z3.Not(z3.Or(self.goal_states[:idx]), ctx=self.ctx)]
            self.assertions.append(z3.And(pre_goal_states) == (self.horizon_var == z3.IntVal(idx+offset, ctx=self.ctx)))

    # we need to check this, since in the case of appending plans, 
    # we could get plans that undo goal states to add more actions.
    if not disable_after_goal_state_actions:
        # force no actions to be taken after the first goal state.
        for t, goal_state in enumerate(self.goal_states):
            after_goal_state_actions = []
            for t2 in range(t+1, len(self)):
                after_goal_state_actions.extend(self.get_actions_vars(t2))
            #self.assertions.append(goal_state == z3.PbEq([(var, 1) for var in after_goal_state_actions], 0, ctx=self.ctx))
            self.assertions.append(goal_state == z3.Not(z3.Or(after_goal_state_actions), ctx=self.ctx))

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
                break
    return SMTSequentialPlan(plan, self.task, selected_actions_vars)

def encode_execution_semantics(self):
    return z3.PbLe([(var, 1) for var in list(map(lambda x: x[0], self.up_actions_to_z3.values()))], 1)

# Update the encoder apis.
# Store all goal states.
setattr(EncoderSequential, 'goal_states', [])
setattr(EncoderSequential, 'goal_predicates_vars', defaultdict(dict))
# Store all assertions.
setattr(EncoderSequential, 'assertions', [])
setattr(EncoderSequential, 'encode_n', encode_n)
setattr(EncoderSequential, 'enabled_actions_vars', enabled_actions_vars)
setattr(EncoderSequential, 'get_actions_vars', get_actions_vars)
setattr(EncoderSequential, 'disable_actions_at_t', disable_actions_at_t)
setattr(EncoderSequential, 'extend', extend)
setattr(EncoderSequential, 'convert', convert)
setattr(EncoderSequential, 'extract_plan', extract_plan)
setattr(EncoderSequential, 'encode_execution_semantics', encode_execution_semantics)
setattr(EncoderSequential, 'get_all_action_vars', get_all_action_vars)
setattr(EncoderSequential, 'horizon_var', None)
setattr(EncoderSequential, 'actions_that_uses_resource', actions_that_uses_resource)
setattr(EncoderSequential, 'task_is_oversubscription_planning', False)


setattr(EncoderForall, 'goal_states', [])
setattr(EncoderForall, 'goal_predicates_vars', defaultdict(dict))
# Store all assertions.
setattr(EncoderForall, 'assertions', [])
setattr(EncoderForall, 'encode_n', encode_n)
setattr(EncoderForall, 'enabled_actions_vars', enabled_actions_vars)
setattr(EncoderForall, 'get_actions_vars', get_actions_vars)
setattr(EncoderForall, 'disable_actions_at_t', disable_actions_at_t)
setattr(EncoderForall, 'extend', extend)
setattr(EncoderForall, 'convert', convert)
setattr(EncoderForall, 'extract_plan', extract_plan)
setattr(EncoderForall, 'encode_execution_semantics', encode_execution_semantics)
setattr(EncoderForall, 'get_all_action_vars', get_all_action_vars)
setattr(EncoderForall, 'horizon_var', None)
setattr(EncoderForall, 'actions_that_uses_resource', actions_that_uses_resource)
setattr(EncoderForall, 'task_is_oversubscription_planning', False)
