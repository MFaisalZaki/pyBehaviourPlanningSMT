"""Behaviour planning over domain models using SMT solvers.

The planner core is C++ (see behaviour_planning_smt/cpp); the Python package is
the unified-planning frontend. Two entry points are provided:

  - the unified-planning engine `BehaviourPlanningSMT` (oneshot + anytime),
    registered automatically with the environment;
  - the original `ForbiddenBehaviorSMTPlanner` API in
    behaviour_planning_smt.fbi.planner.
"""

from behaviour_planning_smt.planner_wrapper import BehaviourPlanningSMTPlanner

__all__ = ["BehaviourPlanningSMTPlanner"]


def _register_engine():
    try:
        from unified_planning.environment import get_environment

        environment = get_environment()
        environment.factory.add_engine(
            "BehaviourPlanningSMT",
            "behaviour_planning_smt.planner_wrapper",
            "BehaviourPlanningSMTPlanner",
        )
    except Exception:
        # Registration is best-effort here; the entry point in pyproject.toml
        # also registers the engine for installed environments.
        pass


_register_engine()
