# pyBehaviourPlanningSMT
Implementation for the `Behaviour Planning: A Toolbox for Diverse Planning` paper.

# Installation
Installation is easy; just run `python -m venv venv && source venv/bin/activate && pip install .` This is tested on python3.12

# How to use
```
import os
from unified_planning.io import PDDLReader, PDDLWriter
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

domainfile  = '/home/ma342/developer/tmp/pyBehaviourPlanningSMT/sandbox-benchmark/classical-domains/classical/rovers/domain.pddl'
problemfile = '/home/ma342/developer/tmp/pyBehaviourPlanningSMT/sandbox-benchmark/classical-domains/classical/rovers/p02.pddl'

task = PDDLReader().parse_problem(domainfile, problemfile)
k = 5 # set the number of required plans
q = 1.0 # set the quality bound 1.0 for optimal plans only.

# 1. Construct the planner's parameters:
# - define the behaviour space's dimensions 
dims  = []
dims += [['go', {}]] # add goal predicate ordering feature.
dims += [['cb', {"quality-bound": q}]] # add the cost bound feature

# SYNATX FOR THE RESOURCES FILE:
# (:resource NAME MINVALUE MAXVALUE STEPSIZE)
# Example for the rover domain
# (:resource rover0 0 100 5)
# (:resource rover1 0 100 5)
# (:resource rover2 0 100 5)
#dims += [['ru', 'PATH-TO-RESOURCES-FILE']]

# 2. Run the planner.
planner = ForbiddenBehaviorSMTPlanner(task, dims)
plans   = planner.plan(k)

# 3. Dump the plans.
plans_dir = os.path.join(os.path.dirname(__file__), "plans")
os.makedirs(plans_dir, exist_ok=True)
task_writer = PDDLWriter(task)
for i, plan_str in  enumerate([task_writer.get_plan(p) + f';{len(p.actions)} cost (unit)' + f'\n;behaviour: {p.behaviour_str.replace("\n","")}' for p in plans]):
    with open(os.path.join(plans_dir, f"plan_{i+1}.sas"), "w") as f:
        f.writelines(plan_str)
```

# Citation
```
@article{abdelwahed2024behaviour,
  title={Behaviour Planning: A Toolbox for Diverse Planning},
  author={Abdelwahed, Mustafa F and Espasa, Joan and Toniolo, Alice and Gent, Ian P},
  journal={arXiv preprint arXiv:2405.04300},
  year={2024}
}
```
