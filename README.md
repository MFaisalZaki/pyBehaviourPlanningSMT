# pyBehaviourPlanningSMT
Implementation for the `Behaviour Planning: A Toolbox for Diverse Planning` paper.

# Installation
Installation is easy; just run `python -m venv venv && source venv/bin/activate && pip install .`
Afterwards, install the UP wrapper:`pip install git+https://github.com/MFaisalZaki/up-behaviour-planning.git `

# How to use
```
import unified_planning as up
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

domainfile  = 'PATH-TO-DOMAIN.PDDL'
problemfile = 'PATH-TO-PROBLEM.PDDL'

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
