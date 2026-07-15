"""
Tutorial 2: Choosing the behaviour space's dimensions.

The dimensions decide what "different" means, so they decide which plans the
planner considers worth returning. This tutorial plans the same task twice with
different dimensions and compares the behaviours that come back.

Run with: python tutorials/02_behaviour_space_dimensions.py
"""

import os
from unified_planning.io import PDDLReader
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

pddls_dir     = os.path.join(os.path.dirname(__file__), 'pddls', 'numeric-rovers')
domainfile    = os.path.join(pddls_dir, 'domain.pddl')
problemfile   = os.path.join(pddls_dir, 'pfile1.pddl')
functionsfile = os.path.join(pddls_dir, 'resources.txt')

task = PDDLReader().parse_problem(domainfile, problemfile)
k = 3

def show(title, dims):
    planner = ForbiddenBehaviorSMTPlanner(task, dims)
    plans   = planner.plan(k)
    print(f'\n=== {title} ===')
    print(f'optimal plan length: {planner.behaviour_space.optimal_plan_length}, plans: {len(plans)}')
    for i, plan in enumerate(plans):
        print(f'  plan {i+1}: {len(plan.actions)} actions | {plan.behaviour_str[:80]}')

# 'go' distinguishes plans by the order in which the goal predicates are
# achieved. It takes no additional information.
show('go: goal predicate ordering', [['go', {}]])

# 'fn' distinguishes plans by where the task's numeric fluents end up. It reads
# a functions file, whose entries slice each fluent's range into boxes:
#
#   (:function energy_rover0 0 100 5)
#
# means: track the fluent energy_rover0 over 0..100 in steps of 5. The box a
# plan finishes in becomes its behaviour along that dimension. Names must match
# the task's grounded fluents; entries that match nothing are ignored.
#
# 'cb' is paired with it here to allow plans of up to 2x the optimal cost,
# which gives the fluents room to land in different boxes.
show('fn + cb: numeric function values', [['fn', functionsfile], ['cb', {"quality-bound": 2.0}]])

# The remaining two dimensions need a task this fixture cannot provide, so each
# gets its own tutorial against the classical rovers instance instead:
#
# 'ru'  counts how many distinct resources a plan uses, and needs a task with
#       several of them to choose between. This one has a single rover, so every
#       plan would score the same. See 03_resource_usage.py.
#
# 'uv'  scores the utility a plan collects, and needs the task to carry an
#       oversubscription metric. This one minimises (recharges) instead, so 'uv'
#       would raise an assertion error. See 04_oversubscription_utility.py.
print('\nSee 03_resource_usage.py and 04_oversubscription_utility.py for ru and uv.')
