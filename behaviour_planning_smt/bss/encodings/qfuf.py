from collections import defaultdict

import z3

from unified_planning.model.metrics import Oversubscription
from unified_planning.plans import SequentialPlan
from unified_planning.plans import ActionInstance
from unified_planning.model import InstantaneousAction

from pypmt.encoders.SequentialQFUF import EncoderSequentialQFUF

from behaviour_planning_smt.bss.encodings.common import extend
from behaviour_planning_smt.bss.encodings.utilities import flattern_expression

def get_actions_vars(self, step):
    # This function is used now by the makespan optimla dimension to compute the cost.
    # It should return all possible actions at step t. For now it is used by the makespan optimal dimension.
    # We can add an expression that checks if this action is not a no-op action. and return this expression.
    nop_action = list(filter(lambda a: a.name == 'nop', self.task.actions))[0]
    return [self.z3_action_variable(step) != self.z3_actions_mapping[nop_action]]

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

    self.task_is_oversubscription_planning = len(list(filter(lambda metric: isinstance(metric, Oversubscription), self.task.quality_metrics))) > 0

    self.goal_states = []
    self.assertions = []
    self.goal_predicates_vars = defaultdict(dict)
 
    # First creat a noop action and append it to the task.
    nop_action = InstantaneousAction('nop')
    self.task.actions.append(nop_action)
    flatten_args = lambda expr: [expr] if not (z3.is_and(expr) or z3.is_or(expr)) else [arg for child in expr.children() for arg in flatten_args(child)]
    for t in range(0, formula_length):
        formula = self.encode(t)
        nested_and = all([z3.is_and(p) for p in formula['goal'].children()])
        nested_or  = all([z3.is_or(p) for p in formula['goal'].children()])
        _fn = z3.And if nested_and else z3.Or
        # strip the extra And if available in formula['goal']
        # self.goal_states.append(_fn(flatten_args(formula['goal'])) if (nested_and or nested_or) else formula['goal'])
        # self.goal_states.append(formula['goal'] if not 'And(' in str(formula['goal'].arg(0)) else formula['goal'].arg(0))
        self.goal_states.append(flattern_expression(formula['goal']))
        if t == 0: self.assertions.extend([formula['initial'], formula['typing']])
        del formula['goal']
        del formula['initial']
        del formula['typing']
        if 'objective' in formula: del formula['objective']
        for k, v in formula.items():
            if v is not None: self.assertions.append(v)
    
    # # append up_fluent_to_z3 to the encoder.
    # self.up_fluent_to_z3 = defaultdict(list)
    # grounded_up_fluents = [f for f, _ in self.ground_problem.initial_values.items()]
    # for grounded_fluent in grounded_up_fluents:
    #     fluent_name = str(grounded_fluent).replace('(', '_').replace(', ', '_').replace(')', '')
    #     z3_fluent   = self.z3_fluents[grounded_fluent.fluent().name]
    #     # convert the UP parameters of the grounded fluent to a list of Z3 objects
    #     fluent_vars = list(map(lambda x: self.up_objects_to_z3[x.constant_value()], grounded_fluent.args))
    #     for t in range(0, formula_length):
    #         self.up_fluent_to_z3[fluent_name].append(z3_fluent(fluent_vars + [z3.IntVal(t, ctx=self.ctx)]))

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
    nop_action_var = self.z3_actions_mapping[nop_action]
    for t in range(0, len(self)-1):
        prevent_gaps = z3.Implies(self.z3_action_variable(z3.IntVal(t, ctx=self.ctx))   == nop_action_var, 
                                  self.z3_action_variable(z3.IntVal(t+1, ctx=self.ctx)) == nop_action_var, ctx=self.ctx)
        self.assertions.append(prevent_gaps)
    
    # disable actions for the last step.
    self.assertions.append(self.z3_action_variable(z3.IntVal(formula_length, ctx=self.ctx)) == nop_action_var)

    if horizon_planning:
        self.horizon_var = z3.IntVal(len(self)-1, ctx=self.ctx)
    else:
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

    # make sure that once a goal state is reached we don't get any more actions.
    if not disable_after_goal_state_actions:
        for tstep, goal_state in enumerate(self.goal_states):
            after_goal_state_actions = []
            for t2 in range(tstep+1, len(self)):
                after_goal_state_actions.append(self.z3_action_variable(z3.IntVal(t2, ctx=self.ctx)) == nop_action_var)
            self.assertions.append(goal_state == z3.And(after_goal_state_actions))

    return self.assertions

def extract_plan(self, model, horizon):
    """!
    Extracts plan from model of the formula.
    Plan returned is linearized.

    @param model: Z3 model of the planning formula.
    @param encoder: encoder object, contains maps variable/variable names.

    @return  plan: dictionary containing plan. Keys are steps, values are actions.
    """
    plan = SequentialPlan([])
    selected_actions_vars = []
    if not model: return plan
    ## linearize partial-order plan
    for step in range(0, horizon+1):
        # which action is in step "step?"
        action_selected = model.evaluate(self.z3_action_variable(step))
        up_action = self.up_actions_mapping[action_selected]

        action_parameters = []
        action_parameters_vars = []
        for i in range(0, len(up_action.parameters)):
            z3_object = model.evaluate(self.z3_action_parameters[i](step))
            up_object = self.z3_objects_to_up[z3_object]
            action_parameters.append(up_object)
            # collect the function parameters. 
            action_parameters_vars.append(self.z3_action_parameters[i](step) == z3_object)

        action_inst = ActionInstance(up_action, action_parameters)
        plan.actions.append(action_inst)
        # append to the list of selected actions.
        selected_actions_vars.append(z3.And([self.z3_action_variable(step) == action_selected] + action_parameters_vars))
    
    setattr(plan, 'task', self.task)
    setattr(plan, 'z3_actions_vars', selected_actions_vars)
    return plan

def enabled_actions_vars(self):
    nop_action = self.z3_actions_mapping[InstantaneousAction('nop')]
    all_actions = [
        z3.If(self.z3_action_variable(z3.IntVal(t, ctx=self.ctx)) != nop_action, z3.IntVal(1, ctx=self.ctx), z3.IntVal(0, ctx=self.ctx))
        for t in range(0, len(self))
    ]
    return all_actions

def disable_actions_at_t(self, t):
    return [self.z3_action_variable(z3.IntVal(t, ctx=self.ctx)) == self.z3_actions_mapping[InstantaneousAction('nop')]]

def actions_that_uses_resource(self, resource_name):
    
    actions_using_resource = []
    
    # First get the typing function based on the resource name.
    typing_fn_resource_var = list(map(lambda x: (self.z3_typing_functions[self.z3_objects_to_up[self.up_objects_to_z3[x]].type.name], self.up_objects_to_z3[x]), filter(lambda x: str(x) == resource_name, self.up_objects_to_z3.keys())))
    nop_action_var = self.z3_actions_mapping[InstantaneousAction('nop')]
    for typing_fn, resource_var in typing_fn_resource_var:
        for tstep in range(0, len(self)):
            t = z3.IntVal(tstep, ctx=self.ctx)
            is_not_nop = self.z3_action_variable(t) != nop_action_var
            is_resource = z3.Or([param(t) == resource_var for param in self.z3_action_parameters])
            actions_using_resource.append(z3.And(is_not_nop, is_resource))
            # action_uses_resource_at_t = z3.And(is_not_nop, is_resource)
            # actions_using_resource.append(z3.If(action_uses_resource_at_t, z3.IntVal(1, ctx=self.ctx), z3.IntVal(0, ctx=self.ctx)))
    return actions_using_resource

def convert(self, plan):
    # We need to translate the SequentialPlan to a list of z3 variables.
    actions_var = []
    for t, action in enumerate(plan.actions):
        up_action = action.action
        tvar = z3.IntVal(t, ctx=self.ctx)
        action_t = [self.z3_action_variable(tvar) == self.z3_actions_mapping[up_action]]
        for i in range(0, len(up_action.parameters)):
            parameter_t = self.z3_action_parameters[i](tvar) == self.up_objects_to_z3[action._params[i]._content.payload] 
            action_t.append(parameter_t)
        actions_var.append(z3.And(action_t))
    return actions_var

# Update the encoder apis.
# Store all goal states.
setattr(EncoderSequentialQFUF, 'goal_states', [])
setattr(EncoderSequentialQFUF, 'goal_predicates_vars', defaultdict(dict))
# Store all assertions.
setattr(EncoderSequentialQFUF, 'assertions', [])
setattr(EncoderSequentialQFUF, 'encode_n', encode_n)
setattr(EncoderSequentialQFUF, 'disable_actions_at_t', disable_actions_at_t)
setattr(EncoderSequentialQFUF, 'enabled_actions_vars', enabled_actions_vars)
setattr(EncoderSequentialQFUF, 'extend', extend)
setattr(EncoderSequentialQFUF, 'convert', convert)
setattr(EncoderSequentialQFUF, 'extract_plan', extract_plan)
setattr(EncoderSequentialQFUF, 'horizon_var', None)
setattr(EncoderSequentialQFUF, 'actions_that_uses_resource', actions_that_uses_resource)
setattr(EncoderSequentialQFUF, 'task_is_oversubscription_planning', False)
setattr(EncoderSequentialQFUF, 'get_actions_vars', get_actions_vars)