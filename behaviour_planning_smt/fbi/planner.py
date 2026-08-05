"""Backwards-compatible entry point for the behaviour planner.

The planning logic lives in the C++ core (behaviour_planning_smt/cpp); this
module keeps the original ForbiddenBehaviorSMTPlanner API on top of the
unified-planning engine wrapper, so existing scripts and the tutorials keep
working:

    planner = ForbiddenBehaviorSMTPlanner(task, dims)
    plans   = planner.plan(k)

Every returned plan carries `behaviour_attr` (a value per dimension),
`behaviour_str` (a printable summary) and `behaviour_expr` (the SMT-LIB text of
the behaviour formula, previously a z3 expression).
"""

from typing import List, Optional

from behaviour_planning_smt.planner_wrapper import BehaviourPlanningSMTPlanner


class BehaviourSpaceInfo:
    """What the C++ core reports about the behaviour space of the last run."""

    def __init__(self):
        self.optimal_plan_length: Optional[int] = None
        self.formula_length: Optional[int] = None
        self.new_behaviour_count: Optional[int] = None
        self.seed_seconds: Optional[float] = None
        self.diversify_seconds: Optional[float] = None
        self.indicator: Optional[str] = None
        # Pairwise behaviour distances of the returned plan set, keyed by the
        # (i, j) plan indices; the sum over the dimensions of each dimension's
        # distance between the two plans' values.
        self.pairwise_behaviour_distances: dict = {}
        self.min_behaviour_distance: Optional[float] = None
        self.avg_behaviour_distance: Optional[float] = None

    def update_from_metrics(self, metrics: dict):
        def to_int(key):
            return int(metrics[key]) if key in metrics else None

        def to_float(key):
            return float(metrics[key]) if key in metrics else None

        self.optimal_plan_length = to_int("optimal_plan_length")
        self.formula_length = to_int("formula_length")
        self.new_behaviour_count = to_int("new_behaviour_count")
        self.seed_seconds = to_float("seed_seconds")
        self.diversify_seconds = to_float("diversify_seconds")
        self.indicator = metrics.get("indicator")
        self.min_behaviour_distance = to_float("behaviour_distance.min")
        self.avg_behaviour_distance = to_float("behaviour_distance.avg")
        self.pairwise_behaviour_distances = {}
        for key, value in metrics.items():
            if not key.startswith("behaviour_distance."):
                continue
            suffix = key[len("behaviour_distance."):]
            if suffix in ("min", "avg"):
                continue
            first, _, second = suffix.partition(".")
            try:
                self.pairwise_behaviour_distances[(int(first), int(second))] = float(value)
            except ValueError:
                pass


class ForbiddenBehaviorSMTPlanner:
    """Forbid-Behaviour-Iterative diverse planner (C++ core).

    Accepts the same constructor arguments as the original Python
    implementation: the task, the behaviour-space dimensions, and optional
    keyword arguments (`horizon_length`, `horizon_planning_mode`). The
    `use_pypmt` option is accepted for compatibility and ignored — plan length
    inference always runs on the C++ SMT core now.
    """

    def __init__(self, task, features, **args):
        self.task = task
        self.features = features
        self.args = dict(args)
        self.args.pop("use_pypmt", None)  # the C++ core always infers via SMT
        self.plan_set: List = []
        self.behaviour_space = BehaviourSpaceInfo()

        engine_options = {"dims": features}
        for option in (
            "encoder", "indicator", "horizon_length", "horizon_planning_mode",
            "max_steps", "oversubscription_horizon", "solver_timeout",
            "solver_memory", "no_action_removal", "verbosity", "stats_file",
            "executable_path",
        ):
            if option in self.args and self.args[option] is not None:
                engine_options[option] = self.args[option]
        self._engine_options = engine_options

    def plan(self, k, timeout=None):
        """Generate at most `k` behaviourally diverse plans.

        The planner first enumerates plans with pairwise-distinct behaviours
        and, once the behaviour space is exhausted, keeps returning plans that
        reuse the behaviours already found. Returns a list ordered as the plans
        were found.
        """
        engine = BehaviourPlanningSMTPlanner(num_plans=k, **self._engine_options)
        engine.skip_checks = True
        _overall, plan_results = engine.get_diverse_plans(self.task, timeout=timeout)
        self.behaviour_space.update_from_metrics(engine.last_metrics)
        self.plan_set = [result.plan for result in plan_results if result.plan is not None]
        return self.plan_set
