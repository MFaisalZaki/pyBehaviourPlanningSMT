"""The benchmarked engines: FBI (this repository), ForbidIterative and SymK.

All of them return plain lists of unified-planning SequentialPlans for the
*prepared* task (the compiled, renamed one every stage of a run shares), so
the runner can hand any engine's output to the same BehaviourDiversityCounter
judge.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional, Tuple


def run_fbi(task, dims, k: int, params: dict, time_budget: int,
            memory_limit_mb: int) -> Tuple[list, dict, List[str]]:
    """Run the FBI planner with one of its diversity indicators.

    Returns (plans, engine_metrics, logs).
    """
    from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

    options = {
        "verbosity": "silent",
        # The per-check solver budget must fit inside the run's budget.
        "solver_timeout": min(300000, max(1, time_budget) * 1000),
        "solver_memory": min(16000, memory_limit_mb) if memory_limit_mb else 16000,
    }
    for key in ("indicator", "encoder", "horizon_length", "horizon_planning_mode",
                "max_steps", "oversubscription_horizon"):
        if key in params:
            options[key] = params[key]

    planner = ForbiddenBehaviorSMTPlanner(task, dims, **options)
    plans = planner.plan(k, timeout=time_budget)

    info = planner.behaviour_space
    metrics = {
        "indicator": info.indicator,
        "optimal-plan-length": info.optimal_plan_length,
        "formula-length": info.formula_length,
        "new-behaviour-count": info.new_behaviour_count,
        "seed-seconds": info.seed_seconds,
        "diversify-seconds": info.diversify_seconds,
        "internal-min-distance": info.min_behaviour_distance,
        "internal-avg-distance": info.avg_behaviour_distance,
    }
    return list(plans), metrics, []


def run_fi(task, domain_file: str, problem_file: str, k: int, quality_bound: float,
           params: dict, workdir: str, time_budget: int) -> Tuple[list, dict, List[str]]:
    """Run ForbidIterative to generate a plan pool.

    FI itself knows nothing about behaviours: it produces
    ``pool-factor * k`` plans (extended unordered top-quality, the
    configuration the behaviour-planning paper benchmarked against), and the
    runner afterwards extracts the k-subset with BehaviourDiversityCounter.

    Returns (pool_plans, pool_metrics, logs).
    """
    from unified_planning.io import PDDLReader

    pool_factor = int(params.get("pool-factor", 5))
    pool_size = max(k, pool_factor * k)

    fi_dir = os.path.join(workdir, "fi")
    os.makedirs(fi_dir, exist_ok=True)

    command = [
        sys.executable, "-m", "forbiditerative.plan",
        "--planner", str(params.get("fi-planner", "extended_unordered_topq")),
        "--domain", domain_file,
        "--problem", problem_file,
        "--number-of-plans", str(pool_size),
        "--quality-bound", str(quality_bound),
        "--symmetries",
        "--use-local-folder",
        "--clean-local-folder",
        "--suppress-planners-output",
        "--overall-time-limit", str(max(1, time_budget)),
    ]

    environment = os.environ.copy()
    environment["FI_PLANNER_RUNS"] = fi_dir

    logs: List[str] = []
    try:
        completed = subprocess.run(
            command, env=environment, cwd=fi_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=max(1, time_budget) + 60)
        if completed.returncode != 0:
            logs.append(f"forbiditerative exited with {completed.returncode}")
            tail = completed.stdout.decode("utf-8", errors="replace").splitlines()[-15:]
            logs.extend(tail)
    except subprocess.TimeoutExpired:
        logs.append("forbiditerative hit the subprocess timeout backstop")
    except FileNotFoundError as error:
        raise RuntimeError(
            "forbiditerative is not installed in this environment "
            "(pip install git+https://github.com/MFaisalZaki/forbiditerative.git)"
        ) from error

    # Whatever happened, collect the plans FI managed to produce.
    plan_texts: List[str] = []
    done_dir = os.path.join(fi_dir, "found_plans", "done")
    if os.path.isdir(done_dir):
        for name in sorted(os.listdir(done_dir)):
            try:
                with open(os.path.join(done_dir, name)) as handle:
                    text = handle.read()
            except OSError:
                continue
            if text not in plan_texts:
                plan_texts.append(text)

    reader = PDDLReader()
    pool = []
    unparsed = 0
    for text in plan_texts:
        try:
            pool.append(reader.parse_plan_string(task, text))
        except Exception:
            unparsed += 1
    if unparsed:
        logs.append(f"{unparsed}/{len(plan_texts)} pool plans did not parse "
                    "against the prepared task")

    metrics = {
        "pool-requested": pool_size,
        "pool-plan-files": len(plan_texts),
        "pool-parsed": len(pool),
        "extract-indicator": params.get("extract-indicator", "bdc"),
    }
    return pool, metrics, logs


# ---------------------------------------------------------------------------
# SymK: the oversubscription baseline
# ---------------------------------------------------------------------------

_OSP_PREFIX = "bpbosp_"


def compile_oversubscription_task(task, osp_goals: dict, scale: int = 1000):
    """Compile a priced-goals task to classical planning for SymK.

    The soft-goals-can-be-compiled-away construction (Keyder & Geffner): a
    `plan_mode` fluent gates the original actions; an `end` action leaves plan
    mode and starts a fixed evaluation chain in which every priced goal is
    either collected (it holds in the final core state; cost 0) or forgone
    (it does not; cost ``scale * utility``). Original actions cost 1, so with
    ``scale`` above any realistic plan length SymK's cost order is
    lexicographic — maximum utility first, then fewest actions — which is the
    FBI seed's oversubscription objective. The chain makes the completion of a
    core plan deterministic, so pool slots are never wasted on collect/forgo
    permutations of the same core plan.
    """
    import unified_planning as up
    from unified_planning.model import Fluent, InstantaneousAction

    for action in task.actions:
        if action.name.lower().startswith(_OSP_PREFIX):
            raise RuntimeError(
                f"action '{action.name}' collides with the '{_OSP_PREFIX}' "
                "bookkeeping prefix of the oversubscription compilation")

    expressions = task.environment.expression_manager
    types = task.environment.type_manager

    compiled = task.clone()
    compiled.clear_quality_metrics()
    compiled.clear_goals()

    plan_mode = Fluent(f"{_OSP_PREFIX}plan_mode", types.BoolType())
    compiled.add_fluent(plan_mode, default_initial_value=True)
    stages = []
    for index in range(len(osp_goals) + 1):
        stage = Fluent(f"{_OSP_PREFIX}stage_{index}", types.BoolType())
        compiled.add_fluent(stage, default_initial_value=False)
        stages.append(stage)

    # Gate fresh clones rather than the cloned problem's own actions, so no
    # action object shared with the judge's task is ever mutated.
    gated = []
    for action in list(compiled.actions):
        fresh = action.clone()
        fresh.add_precondition(plan_mode)
        gated.append(fresh)
    compiled.clear_actions()
    for action in gated:
        compiled.add_action(action)
    costs = {action: expressions.Int(1) for action in gated}

    end = InstantaneousAction(f"{_OSP_PREFIX}end")
    end.add_precondition(plan_mode)
    end.add_effect(plan_mode, False)
    end.add_effect(stages[0], True)
    compiled.add_action(end)
    costs[end] = expressions.Int(0)

    for index, (goal, utility) in enumerate(osp_goals.items()):
        collect = InstantaneousAction(f"{_OSP_PREFIX}collect_{index}")
        collect.add_precondition(stages[index])
        collect.add_precondition(goal)
        collect.add_effect(stages[index], False)
        collect.add_effect(stages[index + 1], True)
        compiled.add_action(collect)
        costs[collect] = expressions.Int(0)

        forgo = InstantaneousAction(f"{_OSP_PREFIX}forgo_{index}")
        forgo.add_precondition(stages[index])
        forgo.add_precondition(expressions.Not(goal))
        forgo.add_effect(stages[index], False)
        forgo.add_effect(stages[index + 1], True)
        compiled.add_action(forgo)
        costs[forgo] = expressions.Int(int(round(float(utility))) * scale)

    compiled.add_goal(stages[-1])
    compiled.add_quality_metric(up.model.metrics.MinimizeActionCosts(costs))
    return compiled


def _find_symk(params: dict) -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for candidate in (params.get("symk-dir"), os.environ.get("SYMK_HOME"),
                      os.path.join(here, "symk")):
        if candidate and os.path.isfile(os.path.join(candidate, "fast-downward.py")):
            return os.path.abspath(candidate)
    raise RuntimeError(
        "SymK not found: set 'symk-dir' in the planner configuration, export "
        "SYMK_HOME, or clone and build it at benchmarks/symk "
        "(setup_benchmark.sh does both)")


def run_symk(task, osp_goals: dict, k: int, params: dict, workdir: str,
             time_budget: int, memory_limit_mb: int) -> Tuple[list, dict, List[str]]:
    """Run SymK to generate a plan pool for an oversubscription task.

    Mainline SymK dropped native oversubscription support, so the priced-goals
    task is compiled to classical planning (`compile_oversubscription_task`)
    and SymK's symbolic top-k search with the unordered plan selector produces
    the ``pool-factor * k`` best compiled plans — maximum utility first, then
    fewest actions. The bookkeeping actions are stripped from the plans, and
    the runner afterwards extracts the k-subset with
    BehaviourDiversityCounter, exactly as for the ForbidIterative pool.

    Returns (pool_plans, pool_metrics, logs).
    """
    from unified_planning.io import PDDLReader, PDDLWriter

    if not osp_goals:
        raise RuntimeError("the symk engine needs priced goals, and this task has none")

    pool_factor = int(params.get("pool-factor", 5))
    pool_size = max(k, pool_factor * k)
    symk_dir = _find_symk(params)

    run_dir = os.path.join(workdir, "symk")
    os.makedirs(run_dir, exist_ok=True)

    compiled = compile_oversubscription_task(task, osp_goals)
    writer = PDDLWriter(compiled)
    compiled_domain = os.path.join(run_dir, "compiled-domain.pddl")
    compiled_problem = os.path.join(run_dir, "compiled-problem.pddl")
    writer.write_domain(compiled_domain)
    writer.write_problem(compiled_problem)

    search = str(params.get(
        "symk-search", "symk_bd(plan_selection=unordered(num_plans={num_plans}))"))
    search = search.replace("{num_plans}", str(pool_size))

    plan_prefix = os.path.join(run_dir, "sas_plan")
    command = [
        sys.executable, os.path.join(symk_dir, "fast-downward.py"),
        "--plan-file", plan_prefix,
        "--overall-time-limit", f"{max(1, time_budget)}s",
    ]
    if memory_limit_mb:
        command += ["--overall-memory-limit", f"{memory_limit_mb}M"]
    command += [compiled_domain, compiled_problem, "--search", search]

    logs: List[str] = []
    try:
        completed = subprocess.run(
            command, cwd=run_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=max(1, time_budget) + 60)
        if completed.returncode != 0:
            logs.append(f"symk exited with {completed.returncode}")
            tail = completed.stdout.decode("utf-8", errors="replace").splitlines()[-15:]
            logs.extend(tail)
    except subprocess.TimeoutExpired:
        logs.append("symk hit the subprocess timeout backstop")

    # Whatever happened, collect the plans SymK managed to write.
    plan_files = sorted(
        (name for name in os.listdir(run_dir)
         if name.startswith("sas_plan.") and name.rsplit(".", 1)[-1].isdigit()),
        key=lambda name: int(name.rsplit(".", 1)[-1]))

    reader = PDDLReader()
    pool, seen = [], set()
    empty_cores = 0
    unparsed = 0
    for name in plan_files:
        try:
            with open(os.path.join(run_dir, name)) as handle:
                lines = handle.read().splitlines()
        except OSError:
            continue
        core = []
        for line in lines:
            line = line.strip()
            if not line.startswith("("):
                continue
            tokens = line.strip("()").split()
            if not tokens:
                continue
            if tokens[0].lower().replace("-", "_").startswith(_OSP_PREFIX):
                continue
            core.append(line)
        if not core:
            empty_cores += 1
            continue
        text = "\n".join(core)
        if text in seen:
            continue
        seen.add(text)
        try:
            pool.append(reader.parse_plan_string(task, text))
        except Exception:
            unparsed += 1
    if empty_cores:
        logs.append(f"{empty_cores} pool plans were empty after stripping the "
                    "bookkeeping actions (every goal forgone)")
    if unparsed:
        logs.append(f"{unparsed} pool plans did not parse against the prepared task")

    metrics = {
        "pool-requested": pool_size,
        "pool-plan-files": len(plan_files),
        "pool-parsed": len(pool),
        "extract-indicator": params.get("extract-indicator", "bdc"),
        "compiled-priced-goals": len(osp_goals),
        "symk-search": search,
    }
    return pool, metrics, logs
