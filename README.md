# pyBehaviourPlanningSMT
Implementation for the `Behaviour Planning: A Toolbox for Diverse Planning` paper.

The planner core is C++ on top of Z3; the Python package is a thin
[unified-planning](https://github.com/aiplan4eu/unified-planning) frontend that
ships the task to the core as a protobuf message and reads the diverse plans
back. The architecture — protobuf interchange, problem model and build system —
follows [RantanPlan](https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT),
whose scaffolding this repository adapts.

```
Python frontend                    C++ core (bp_planner)
┌──────────────────────┐          ┌─────────────────────────────┐
│ unified-planning     │          │ seed search (optimal length)│
│ • PDDL parsing       │ protobuf │ bounded SMT encoding        │
│ • compile + ground   │ ───────▶ │ behaviour-space dimensions  │
│ • plan mapping back  │ ◀─────── │ forbid-behaviour iteration  │
└──────────────────────┘          │          Z3 solver          │
                                  └─────────────────────────────┘
```

# Installation
Requires python `>=3.10`, CMake, a C++20 compiler and the protobuf development
libraries (`apt-get install protobuf-compiler libprotobuf-dev` on Debian/Ubuntu,
`brew install protobuf` on macOS). Z3 comes from the `z3-solver` Python package.

```
python -m venv venv && source venv/bin/activate
pip install .
python build.py        # builds the bp_planner C++ core
```

# How to use
Runnable tutorials live in [tutorials/](tutorials/), starting with
[01_getting_started.py](tutorials/01_getting_started.py). They plan a bundled
task, so the two install steps above are the only setup needed. The short
version:

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
for i, plan_str in  enumerate([task_writer.get_plan(p) + f';{len(p.actions)} cost (unit)' + f'\n;behaviour: {p.behaviour_str}' for p in plans]):
    with open(os.path.join(plans_dir, f"plan_{i+1}.sas"), "w") as f:
        f.writelines(plan_str)
```

`plan(k)` returns a list of at most `k` plans. The planner first enumerates
plans with distinct behaviours, and once the behaviour space is exhausted it
keeps returning additional plans that reuse the behaviours already found. Every
returned plan carries four extra attributes: `behaviour_attr` (a per-dimension
value map), `behaviour_str` (a printable summary like `go=011 cb=10`),
`behaviour_expr` (the SMT-LIB text of the behaviour formula) and
`is_new_behaviour` (whether the plan came from the behaviour phase).

The planner is also registered as the unified-planning engine
`BehaviourPlanningSMT`, usable both oneshot and anytime:

```python
from unified_planning.shortcuts import AnytimePlanner
import behaviour_planning_smt  # registers the engine

with AnytimePlanner(name='BehaviourPlanningSMT',
                    params={'dims': dims, 'num_plans': k}) as planner:
    for result in planner.get_solutions(task):
        print(result.plan.behaviour_str)
```

The `bp_planner` executable can equally be driven directly — run
`behaviour_planning_smt/bin/bp_planner --help` for its options; it consumes a
grounded problem serialized with unified-planning's protobuf writer.

## Behaviour space dimensions
Each dimension is a `[name, additional-info]` pair. The built-in dimensions are:

| Name | Feature | Additional info |
| ---- | ------- | --------------- |
| `go` | Goal predicate ordering | ignored, pass `{}` |
| `cb` | Makespan-optimal cost bound | `{"quality-bound": <float>}` |
| `ru` | Resource usage count | path to a resources file |
| `uv` | Utility value | `{}`, requires an oversubscription task |
| `fn` | Numeric function values | path to a functions file |
| `ac` | Action count (example plugin) | an action-name fragment, e.g. `'navigate'` |

Dimensions, encoders and diversity indicators are plugins, in the style of
Fast Downward's plugin system: each lives in its own file, registers itself
under a name during static initialization, and is requested by that name.
`bp_planner --list-dimensions`, `--list-encoders` and `--list-indicators`
show what a build registered, and unknown names fail with the registered
list. The Python wrapper passes dimension names through untouched, so a new
C++ dimension is usable from Python without editing the wrapper — a string
additional-info becomes the dimension's argument (that is how
`['ac', 'navigate']` works).

Every dimension also defines a **distance function** between two of its
values: the discrete metric by default, overridden with a semantic distance
by the built-ins — absolute difference for the count-valued dimensions
(`cb`, `ru`, `uv`, `ac`), Hamming distance over the ordering vector for
`go`, and per-fluent box differences for `fn`. After a run the planner
scores the returned plan set with them: the overall result's metrics carry
`behaviour_distance.<i>.<j>` for every plan pair (the sum of the
per-dimension distances) plus `behaviour_distance.min`/`.avg`, and the
Python API exposes them as `planner.behaviour_space.pairwise_behaviour_distances`,
`.min_behaviour_distance` and `.avg_behaviour_distance`.

## Diversity indicators
The diversification strategy itself is a plugin category: a **diversity
indicator** is the optimisation metric the planner maximises over the
behaviour space, selected with `--indicator NAME[:ARG]` (or
`indicator='name'` in Python). Two ship with the planner:

| Name | Indicator | Strategy |
| ---- | --------- | -------- |
| `bdc` (default) | Behaviour diversity count | Maximises the number of distinct behaviours: forbid every behaviour found, generate another one; once the space is exhausted, fill the quota with plans that reuse known behaviours but differ from every known plan. |
| `bms` (alias `BehaviourMaxSum`) | Behaviour max-sum | Maximises the sum of pairwise behaviour distances (computed with the dimensions' distance functions): grow the set like `bdc`, then keep generating further new behaviours and swap one into the set whenever the swap strictly increases the total; with fewer behaviours than requested plans it just returns plans. `ARG` bounds the generation rounds (default `5 * num-plans`). |

Further indicators implement the interface in
`cpp/src/bss/diversity_indicator.hpp`, use the dimensions' distance
functions via `space.dimensions()`, and register with a
`DiversityIndicatorPlugin` in a file under `cpp/src/bss/indicators/`.

## Writing your own dimension, encoder or indicator
A dimension is a small C++ class implementing the contract in
`behaviour_planning_smt/cpp/src/bss/dimension.hpp` — constraints in the
constructor, behaviour evaluation from a model, and optionally a `distance`
override (the default is the discrete metric) — plus a `DimensionPlugin`
registrar. Drop the file into `cpp/src/bss/dimensions/`, add it to
`cpp/CMakeLists.txt`, rebuild: nothing else needs editing. The bundled
[`action_count.cpp`](behaviour_planning_smt/cpp/src/bss/dimensions/action_count.cpp)
is the template, and
[tutorials/06_custom_dimension.py](tutorials/06_custom_dimension.py) walks
through it. Diversity indicators extend the same way under
`cpp/src/bss/indicators/`, with
[`behaviour_diversity_count.cpp`](behaviour_planning_smt/cpp/src/bss/indicators/behaviour_diversity_count.cpp)
as the template.

Encoders follow the same pattern with `EncoderPlugin` against the interface in
`cpp/src/encoders/encoder.hpp`; the bounded sequential encoding ships as the
`seq` plugin, selected with `--encoder` (or the `encoder` option in Python).
A dimension is responsible for knowing which encoders it supports: it reads
the active encoder's name and places its encodings accordingly, rejecting
encoders it was never taught (see `Dimension::require_encoder` and the
per-encoder branch in the `cb` dimension).

The `cb` dimension is special: its `quality-bound` also scales the encoded
formula length, which is `optimal-plan-length * quality-bound`. When `cb` is
not among the dimensions, the quality bound defaults to `1.0`, i.e. optimal
plans only.

On an oversubscription task `cb` inverts: rather than requiring plans to be at
least optimal length, it caps them at `quality-bound * optimal-plan-length`,
which becomes the budget a plan may spend collecting utility.

The `uv` dimension requires the task to define an oversubscription quality
metric with a utility value per goal, otherwise the planner reports an
unsupported-problem error.
[tutorials/04_oversubscription_utility.py](tutorials/04_oversubscription_utility.py)
shows how to attach one to a classical task.

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
`ForbiddenBehaviorSMTPlanner` forwards any extra keyword arguments to the C++
core:

| Option | Default | Meaning |
| ------ | ------- | ------- |
| `encoder` | `seq` | Encoder plugin to use (`bp_planner --list-encoders`). |
| `indicator` | `bdc` | Diversity-indicator plugin, the optimisation metric of the diversification (`bp_planner --list-indicators`). |
| `horizon_length` | `None` | Skip the seed search and use this value as the optimal plan length. It is still scaled by `cb`'s quality bound to give the formula length. |
| `horizon_planning_mode` | `False` | Pin the horizon to the formula's last step instead of binding it to the first step at which the goal holds, so plans are read from the whole formula rather than truncated at the goal. |
| `max_steps` | `500` | Horizon cap for the seed search. |
| `oversubscription_horizon` | `30` | Encoding bound for the oversubscription seed (see below). |
| `solver_timeout` | `300000` | Per-check solver timeout in milliseconds. |
| `solver_memory` | `16000` | Per-check solver memory limit in MB. |
| `no_action_removal` | `False` | Disable the relaxed-planning-graph action pruning. |
| `verbosity` | `info` | One of `silent`, `info`, `verbose`, `debug`. |

```python
# skip the plan-length inference step and encode a fixed horizon of 20 steps.
planner = ForbiddenBehaviorSMTPlanner(task, dims, horizon_length=20, horizon_planning_mode=True)
```

The old `use_pypmt` option is accepted and ignored: plan-length inference
always runs on the C++ SMT core now. For classical and numeric tasks the seed
is an iterative-deepening search for the makespan-optimal length; for
oversubscription tasks the core instead maximizes the collected utility over a
bounded encoding (`oversubscription_horizon` steps) and, at maximum utility,
minimizes the plan length — this replaces the external oversubscription seed
planner the Python implementation used.

# Benchmarks
[benchmarks/](benchmarks/) holds `bpbench`, a benchmark harness in the style
of [ASPPlanners' aspbench](https://github.com/MFaisalZaki/ASPPlanners/tree/main/benchmarks):
it sweeps the FBI planner's diversity indicators against
[ForbidIterative](https://github.com/MFaisalZaki/forbiditerative) baselines
that generate a plan pool and extract a k-subset, with every returned plan set
judged by
[BehaviourDiversityCounter](https://github.com/MFaisalZaki/BehaviourDiversityCounter)
(behaviour diversity count and behaviour max-sum). One script sets everything
up — see [benchmarks/README.md](benchmarks/README.md):

```bash
cd benchmarks && ./setup_benchmark.sh
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
