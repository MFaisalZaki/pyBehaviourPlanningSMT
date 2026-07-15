# pyBehaviourPlanningSMT
Implementation for the `Behaviour Planning: A Toolbox for Diverse Planning` paper.

# Installation
Installation is easy; just run `python -m venv venv && source venv/bin/activate && pip install .` The package requires python `>=3.10` and is tested on python3.12.

# How to use
Runnable tutorials live in [tutorials/](tutorials/), starting with
[01_getting_started.py](tutorials/01_getting_started.py). They plan a bundled task, so
`pip install .` is the only setup needed. The short version:

```python
import os
from unified_planning.io import PDDLReader, PDDLWriter
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

domainfile  = 'PATH-TO-DOMAIN-FILE'
problemfile = 'PATH-TO-PROBLEM-FILE'

task = PDDLReader().parse_problem(domainfile, problemfile)
k = 5 # set the number of required plans
q = 1.0 # set the quality bound 1.0 for optimal plans only.

# 1. Construct the planner's parameters:
# - define the behaviour space's dimensions
dims  = []
dims += [['go', {}]] # add goal predicate ordering feature.
dims += [['cb', {"quality-bound": q}]] # add the cost bound feature

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

`plan(k)` returns a set of at most `k` plans. The planner first enumerates plans with distinct behaviours, and once the behaviour space is exhausted it keeps returning additional plans that reuse the behaviours already found. Every returned plan carries three extra attributes: `behaviour_expr` (the z3 expression), `behaviour_attr` (a per-dimension map) and `behaviour_str` (a printable form).

## Behaviour space dimensions
Each dimension is a `[name, additional-info]` pair. The supported names are:

| Name | Feature | Additional info |
| ---- | ------- | --------------- |
| `go` | Goal predicate ordering | ignored, pass `{}` |
| `cb` | Makespan-optimal cost bound | `{"quality-bound": <float>}` |
| `ru` | Resource usage count | path to a resources file |
| `uv` | Utility value | `{}`, requires an oversubscription task |
| `fn` | Numeric function values | path to a functions file |

The list is open. A dimension is a `DimensionConstructorSMT` subclass implementing `__encode__` and `expr`, registered by assigning it into `behaviour_planning_smt.bss.behaviour_space.features_map` under a short name of your choice; the library itself needs no edit. [tutorials/06_custom_dimension.py](tutorials/06_custom_dimension.py) walks through one.

The `cb` dimension is special: its `quality-bound` also scales the encoded formula length, which is `optimal-plan-length * quality-bound`. When `cb` is not among the dimensions, the quality bound defaults to `1.0`, i.e. optimal plans only.

On an oversubscription task `cb` inverts: rather than requiring plans to be at least optimal length, it caps them at `quality-bound * optimal-plan-length`, which becomes the budget a plan may spend collecting utility.

The `uv` dimension requires the task to define an oversubscription quality metric with a utility value per goal, otherwise the planner raises an assertion error. [tutorials/04_oversubscription_utility.py](tutorials/04_oversubscription_utility.py) shows how to attach one to a classical task.

## Resources and functions files
The `ru` dimension reads a resources file, one entry per line with the syntax `(:resource NAME MINVALUE MAXVALUE STEPSIZE)`. For the rover domain:
```
(:resource rover0 0 100 5)
(:resource rover1 0 100 5)
(:resource rover2 0 100 5)
```
`NAME` is matched as a substring against the grounded action names, and entries matching no action are dropped. `ru` reads nothing but the name: the three numbers are required by the parser and then ignored, which is why the resource data under `paper_experiments/data/classical-domains-ru-info` gives them in a different order and still works.

The `fn` dimension reads a functions file, which uses the `:function` keyword and names a numeric fluent of the task: `(:function NAME MINVALUE MAXVALUE STEPSIZE)`. For the numeric rover domain:
```
(:function energy_rover0 0 100 5)
(:function recharges 0 100 2)
```
`MINVALUE`, `MAXVALUE` and `STEPSIZE` slice the fluent's range into boxes, and the box a plan ends in becomes its behaviour along that dimension. A working example ships in [tutorials/pddls/numeric-rovers/](tutorials/pddls/numeric-rovers/).

Both parsers accept only these entries; neither file format supports comments.

## Planner options
`ForbiddenBehaviorSMTPlanner` forwards any extra keyword arguments to the underlying behaviour space:

| Option | Default | Meaning |
| ------ | ------- | ------- |
| `horizon_length` | `None` | Skip the plan-length inference step and use this value as the optimal plan length. It is still scaled by `cb`'s quality bound to give the formula length. |
| `horizon_planning_mode` | `False` | Pin the horizon to the formula's last step instead of binding it to the first step at which the goal holds, so plans are read from the whole formula rather than truncated at the goal. |
| `use_pypmt` | `None` | Force the SMT planner when inferring the plan length. Numeric and oversubscription tasks use it regardless. |

```python
# skip the plan-length inference step and encode a fixed horizon of 20 steps.
planner = ForbiddenBehaviorSMTPlanner(task, dims, horizon_length=20, horizon_planning_mode=True)
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
