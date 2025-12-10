import z3

def flattern_list(list_of_lists):
    return sum((flattern_list(sub) if isinstance(sub, list) else [sub] for sub in list_of_lists), [])

def get_actions_vars(self, step):
    return list(map(lambda x: x[step], self.up_actions_to_z3.values()))

def extend(self, asserstions_list):
    self.assertions.extend(asserstions_list)

def convert(self, plan):
    actions_vars = [z3.And([self.up_actions_to_z3[a][t] for t, a in enumerate(map(lambda x: str(x), plan.actions))])]
    for _t in range(len(plan.actions), len(self)):
        actions_vars.extend(self.disable_actions_at_t(_t))
    return actions_vars

def get_all_action_vars(self, name):
    """!
    Function used to recover the plan: given the var name, 
    return all the z3 vars
    """
    return self.up_actions_to_z3[name]

def enabled_actions_vars(self):
    all_actions = []
    for t in range(0, len(self)):
        all_actions += [z3.If(a, z3.IntVal(1, ctx=self.ctx), z3.IntVal(0, ctx=self.ctx)) for a in self.get_actions_vars(t)]
    return all_actions

def disable_actions_at_t(self, t):
    return [z3.Not(z3.Or(self.get_actions_vars(t)), ctx=self.ctx)]

def actions_that_uses_resource(self, resource_name):
    # Get grounded actions that has the resource_name in it.
    actions_names = list(filter(lambda action: resource_name in action, self.up_actions_to_z3.keys()))
    # For every action get all its vars across the time steps.
    actions_vars = [self.get_all_action_vars(action) for action in actions_names]
    # Flattern this list of lists.
    actions_vars = flattern_list(actions_vars)
    return actions_vars
