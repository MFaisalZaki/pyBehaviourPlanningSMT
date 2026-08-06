# Tutorials

Runnable introductions to the planner. Each script stands alone and plans a
bundled task, so no benchmark checkout is needed.

Install the package and build the C++ core first, then run them from the
repository root:

```
python -m venv venv && source venv/bin/activate && pip install .
python build.py
python tutorials/01_getting_started.py
```

Each script takes a few seconds to a minute: `plan(k)` runs the C++ core once,
which solves the task to find the optimal plan length before anything is
encoded, and reports its progress on stdout.

| Tutorial | Covers |
| -------- | ------ |
| [01_getting_started.py](01_getting_started.py) | Parse a task, pick dimensions, generate diverse plans, read their behaviours, and dump them to disk. |
| [02_behaviour_space_dimensions.py](02_behaviour_space_dimensions.py) | How the choice of dimensions changes which plans come back, covering `go` and `fn`. |
| [03_resource_usage.py](03_resource_usage.py) | The `ru` dimension and the resources file. |
| [04_oversubscription_utility.py](04_oversubscription_utility.py) | The `uv` dimension, and turning a classical task into an oversubscription one. |
| [05_planner_options.py](05_planner_options.py) | Controlling the horizon: `horizon_length`, `horizon_planning_mode` and the solver budgets. |
| [06_custom_dimension.py](06_custom_dimension.py) | The plugin system: dissecting the bundled `ac` example plugin and writing a dimension of your own. |

## The bundled tasks

[pddls/numeric-rovers/](pddls/numeric-rovers/) is the rovers domain with numeric
fluents, one rover, four waypoints and three goal predicates. It minimises
`(recharges)`, and its `resources.txt` tracks the `energy_rover0` and
`recharges` fluents for the `fn` dimension. Tutorials 1, 2 and 5 use it.

[pddls/classical-rovers/](pddls/classical-rovers/) is the IPC-2006 rovers domain
with instance 3, which has two rovers, so a plan has a real choice about how
much of the fleet to use. Its `resources.txt` lists both rovers for the `ru`
dimension, matching the instance 3 entry in
`benchmarks/data/classical-domains-ru-info/rovers/rovers-2006.json`.
Tutorials 3, 4 and 6 use it.

See the [main README](../README.md) for the full list of dimensions and options.
