"""
Tutorial 1: Getting started.

Generates a set of diverse plans for the numeric rovers task and prints the
behaviour that makes each of them different.

Run with: python tutorials/01_getting_started.py
"""

import os
from unified_planning.io import PDDLReader, PDDLWriter
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

pddls_dir   = os.path.join(os.path.dirname(__file__), 'pddls', 'numeric-rovers')
domainfile  = os.path.join(pddls_dir, 'domain.pddl')
problemfile = os.path.join(pddls_dir, 'pfile1.pddl')

task = PDDLReader().parse_problem(domainfile, problemfile)

k = 4   # the number of required plans.
q = 1.0 # the quality bound, 1.0 asks for optimal plans only.

# 1. Define the behaviour space's dimensions. Two plans have the same behaviour
#    when they agree on every dimension, and the planner only returns one plan
#    per behaviour until the space runs out.
dims  = []
dims += [['go', {}]]                   # the order in which goal predicates are achieved.
dims += [['cb', {"quality-bound": q}]] # the plan cost, bounded by q * optimal cost.

# 2. Run the planner. Everything happens inside the C++ core in one go: it
#    first solves the task to find the optimal plan length (the seed search),
#    then iterates the behaviour space for diverse plans.
#
# plan(k) returns *at most* k plans. It stops early when neither a new behaviour
# nor a new plan can be found, so always check what you actually got back.
planner = ForbiddenBehaviorSMTPlanner(task, dims)
plans   = planner.plan(k)
print(f'Optimal plan length: {planner.behaviour_space.optimal_plan_length}')
print(f'Asked for {k} plans, got {len(plans)}.')

# 3. Inspect the behaviours. Every returned plan carries three extra attributes:
#    behaviour_attr (a value per dimension, as strings), behaviour_str (a
#    printable summary like 'go=011 cb=10') and behaviour_expr (the SMT-LIB text
#    of the behaviour formula the C++ core used).
for i, plan in enumerate(plans):
    print(f'\nPlan {i+1}: {len(plan.actions)} actions')
    print(f'  dimensions: {list(plan.behaviour_attr.keys())}')
    print(f'  behaviour:  {plan.behaviour_str}')

# 4. Dump the plans to disk, annotated with their cost and behaviour.
plans_dir = os.path.join(os.path.dirname(__file__), 'plans')
os.makedirs(plans_dir, exist_ok=True)
task_writer = PDDLWriter(task)
for i, plan in enumerate(plans):
    plan_str  = task_writer.get_plan(plan)
    plan_str += f';{len(plan.actions)} cost (unit)'
    plan_str += f'\n;behaviour: {plan.behaviour_str}'
    with open(os.path.join(plans_dir, f'plan_{i+1}.sas'), 'w') as f:
        f.writelines(plan_str)
print(f'\nWrote {len(plans)} plans to {plans_dir}')
