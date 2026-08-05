"""The benchmarked engines: FBI (this repository) and ForbidIterative.

Both return plain lists of unified-planning SequentialPlans for the *prepared*
task (the compiled, renamed one every stage of a run shares), so the runner
can hand any engine's output to the same BehaviourDiversityCounter judge.
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
