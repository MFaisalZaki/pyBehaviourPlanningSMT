"""Run ONE (planner, task, k) triple under its limits and dump a JSON result.

This is the only module that imports unified_planning; the other stages stay
stdlib-only so a sweep can be generated on a laptop and only the compute
nodes carry the planners (the aspbench discipline).

Every returned plan set — FBI's and ForbidIterative's alike — is judged by the
same BehaviourDiversityCounter: the returned k plans are scored with its
``bdc`` and ``b_maxsum`` indicators, so the numbers in the results are
comparable across engines by construction. For the FI configurations the
counter additionally performs the subset extraction from the generated pool.
"""

from __future__ import annotations

import json
import os
import resource
import shutil
import signal
import time
import traceback
from typing import List, Optional, Tuple


class _TimeBudgetExceeded(Exception):
    pass


def _arm_limits(time_limit: int, memory_limit_mb: int) -> None:
    if time_limit and time_limit > 0:
        def _on_alarm(_signum, _frame):
            raise _TimeBudgetExceeded()
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(time_limit)
    if memory_limit_mb and memory_limit_mb > 0:
        limit_bytes = memory_limit_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
        except (ValueError, OSError):
            pass  # some systems refuse to lower/raise; the slurm limit remains


# ---------------------------------------------------------------------------
# Task preparation
# ---------------------------------------------------------------------------

def _prepare_task(domain_file: str, problem_file: str, track: str, workdir: str):
    """Parse, compile and rewrite the task once for the whole run.

    The compiled task is written out with PDDLWriter and re-parsed, so every
    consumer — FBI, ForbidIterative and the behaviour counter — sees exactly
    the same names. This sidesteps the '-'/'_' renaming mismatch between the
    original files and what planners echo back in their plans (the discipline
    the paper experiments used).

    Returns (task, renamed_domain_file, renamed_problem_file, osp_goals).
    """
    from unified_planning.io import PDDLReader, PDDLWriter
    from unified_planning.shortcuts import Compiler, CompilationKind

    original = PDDLReader().parse_problem(domain_file, problem_file)

    names, kinds = [], []
    if track != "numeric":
        names += ["up_quantifiers_remover", "up_disjunctive_conditions_remover"]
        kinds += [CompilationKind.QUANTIFIERS_REMOVING,
                  CompilationKind.DISJUNCTIVE_CONDITIONS_REMOVING]
    if names:
        with Compiler(names=names, compilation_kinds=kinds) as compiler:
            original = compiler.compile(original).problem

    writer = PDDLWriter(original)
    renamed_domain = os.path.join(workdir, "renamed-domain.pddl")
    renamed_problem = os.path.join(workdir, "renamed-problem.pddl")
    writer.write_domain(renamed_domain)
    writer.write_problem(renamed_problem)

    task = PDDLReader().parse_problem(renamed_domain, renamed_problem)

    osp_goals = {}
    if track == "oversubscription":
        import unified_planning as up
        from unified_planning.model.walkers.free_vars import FreeVarsExtractor
        predicates = next(map(lambda e: FreeVarsExtractor().get(e), task.goals), None)
        if predicates:
            # The paper experiments' pricing: 2, 4, 6, ... in goal order.
            osp_goals = {g: (i + 1) * 2 for i, g in enumerate(predicates)}
            task.add_quality_metric(
                up.model.metrics.Oversubscription(osp_goals, task.environment))
            task.goals.clear()

    return task, renamed_domain, renamed_problem, osp_goals


def _build_dimensions(track: str, quality_bound: float, resources_file: Optional[str],
                      osp_goals: dict) -> Tuple[list, list, list]:
    """The behaviour-space dimensions for the FBI planner and their
    translations for the BehaviourDiversityCounter judge.

    Two judge dimension lists come back, because not every counter dimension
    implements a distance: the *behaviour* list (the counter's 'rc' is the
    per-resource counts our 'ru' counts behaviours by; 'uv'/'fn' likewise)
    defines behaviour identity for bdc, and the *distance* list keeps only the
    counter's distance-capable dimensions ('go', 'cb', and the used-resources
    'ru' with its Jaccard distance) for the b_maxsum indicator.
    """
    if track == "oversubscription":
        planner_dims = [["cb", {"quality-bound": quality_bound}], ["uv", {}]]
        behaviour_dims = [("cb", {"q": quality_bound}),
                          ("uv", {"utility-goals": osp_goals})]
        distance_dims = [("cb", {"q": quality_bound})]
        return planner_dims, behaviour_dims, distance_dims

    planner_dims = [["go", {}], ["cb", {"quality-bound": quality_bound}]]
    behaviour_dims = [("go", None), ("cb", {"q": quality_bound})]
    distance_dims = [("go", None), ("cb", {"q": quality_bound})]
    if resources_file:
        if track == "numeric":
            planner_dims.append(["fn", resources_file])
            behaviour_dims.append(("fn", resources_file))
        else:
            planner_dims.append(["ru", resources_file])
            behaviour_dims.append(("rc", resources_file))
            distance_dims.append(("ru", resources_file))
    return planner_dims, behaviour_dims, distance_dims


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def solve(args) -> int:
    import unified_planning as up
    environment = up.environment.get_environment()
    environment.error_used_name = False
    environment.credits_stream = None

    with open(args.planner_cfg) as handle:
        planner_cfg = json.load(handle)
    engine = planner_cfg.get("engine", "fbi")
    params = planner_cfg.get("params", {})

    k = int(args.k)
    quality_bound = float(args.quality_bound)

    result = {
        "task": {
            "task-id": args.task_id, "suite": args.suite, "domain": args.domain_name,
            "instance": args.instance, "track": args.track,
            "domain-file": args.domain, "problem-file": args.problem,
            "k": k, "quality-bound": quality_bound,
        },
        "planner": {"tag": planner_cfg.get("planner-tag"), "engine": engine,
                    "params": params},
        "limits": {"time-seconds": args.time_limit, "memory-mb": args.memory_limit},
        "status": "ERROR",
        "times": {},
        "plans": {"requested-k": k, "returned": 0},
        "scores": {},
        "logs": [],
    }

    results_dir = os.path.abspath(args.results_dir)
    os.makedirs(results_dir, exist_ok=True)
    result_path = os.path.join(
        results_dir, f"{args.task_id}__k{k}.json")

    workdir = os.path.abspath(args.run_dir or os.path.join(
        results_dir, "..", "..", "runs",
        f"{planner_cfg.get('planner-tag')}__{args.task_id}__k{k}.{os.getpid()}"))
    os.makedirs(workdir, exist_ok=True)
    result["run"] = {"work-dir": workdir}

    started = time.time()
    _arm_limits(args.time_limit, args.memory_limit)

    try:
        _run(args, result, engine, params, k, quality_bound, workdir, started)
    except _TimeBudgetExceeded:
        result["status"] = "TIMEOUT"
    except MemoryError:
        result["status"] = "MEMOUT"
    except Exception as error:  # noqa: BLE001 - a run must always report
        result["status"] = "ERROR"
        result["logs"].append(str(error))
        if args.errors_dir:
            os.makedirs(args.errors_dir, exist_ok=True)
            with open(os.path.join(
                    args.errors_dir,
                    f"{planner_cfg.get('planner-tag')}__{args.task_id}__k{k}.log"),
                    "w") as handle:
                handle.write(traceback.format_exc())
    finally:
        signal.alarm(0)
        result["times"]["total"] = round(time.time() - started, 3)
        with open(result_path, "w") as handle:
            json.dump(result, handle, indent=2)
        print(f"[{result['status']}] {planner_cfg.get('planner-tag')} "
              f"{args.task_id} k={k} -> {result_path}")
        if not args.keep_run_dir:
            shutil.rmtree(workdir, ignore_errors=True)

    return 0


def _run(args, result, engine, params, k, quality_bound, workdir, started):
    from behaviour_diversity_counter import BehaviourDiversityCounter
    from .engines import run_fbi, run_fi

    def remaining() -> int:
        if not args.time_limit:
            return 10 ** 6
        return max(1, int(args.time_limit - (time.time() - started)))

    # --- Prepare: compile + rename, so every stage shares one task identity.
    prepare_started = time.time()
    task, renamed_domain, renamed_problem, osp_goals = _prepare_task(
        args.domain, args.problem, args.track, workdir)

    resources_file = None
    if args.resources and os.path.exists(args.resources):
        with open(args.resources) as handle:
            declaration = handle.read()
        # The prepared task uses '_' where the original files used '-'.
        resources_file = os.path.join(workdir, "resources.txt")
        with open(resources_file, "w") as handle:
            handle.write(declaration.replace("-", "_"))

    planner_dims, behaviour_dims, distance_dims = _build_dimensions(
        args.track, quality_bound, resources_file, osp_goals)
    result["dimensions"] = {
        "behaviour": [name for name, _info in behaviour_dims],
        "distance": [name for name, _info in distance_dims],
    }
    result["times"]["prepare"] = round(time.time() - prepare_started, 3)

    # --- Plan.
    plan_started = time.time()
    if engine == "fbi":
        plans, engine_metrics, logs = run_fbi(
            task, planner_dims, k, params, remaining(), args.memory_limit)
        pool = None
    elif engine == "fi":
        pool, engine_metrics, logs = run_fi(
            task, renamed_domain, renamed_problem, k, quality_bound, params,
            workdir, remaining())
        plans = None  # extracted below, under the counter's clock
    else:
        raise ValueError(f"unknown engine '{engine}' in {args.planner_cfg}")
    result["engine-metrics"] = engine_metrics
    result["logs"].extend(logs)
    result["times"]["plan"] = round(time.time() - plan_started, 3)

    # --- Judge: the behaviour counter defines behaviour identity (bdc), the
    # distance counter carries the distance-capable dimensions (b_maxsum).
    behaviour_counter = BehaviourDiversityCounter(task, behaviour_dims)
    distance_counter = BehaviourDiversityCounter(task, distance_dims)

    if engine == "fi":
        extract_started = time.time()
        indicator = params.get("extract-indicator", "bdc")
        usable_pool = _drop_inapplicable(pool, behaviour_counter, result)
        result["pool"] = {
            "size": len(usable_pool),
            "bdc": behaviour_counter.bdc(usable_pool) if usable_pool else 0,
        }
        extractor = distance_counter if indicator == "bmaxsum" else behaviour_counter
        plans = extractor.extract(usable_pool, k, indicator=indicator) if usable_pool else []
        result["times"]["extract"] = round(time.time() - extract_started, 3)

    score_started = time.time()
    plans = _drop_inapplicable(plans, behaviour_counter, result)
    result["plans"]["returned"] = len(plans)
    if plans:
        bdc_score = behaviour_counter.bdc(plans)
        # Snapshot the behaviour strings now: the distance counter's replay
        # below re-attaches plan.behaviour with its own (shorter) tokens.
        behaviours = [getattr(p, "behaviour", "") for p in plans]
        result["scores"] = {
            "bdc": bdc_score,
            "bmaxsum": round(distance_counter.b_maxsum(plans), 6),
        }
        result["plans"]["lengths"] = [len(p.actions) for p in plans]
        result["plans"]["behaviours"] = behaviours
        result["plans"]["pddl"] = _plans_to_pddl(task, plans, behaviours)
        result["status"] = "SOLVED"
    else:
        result["status"] = "NO_PLANS"
    result["times"]["score"] = round(time.time() - score_started, 3)


def _drop_inapplicable(plans, counter, result) -> list:
    """Filter out plans the judge cannot replay, reporting how many.

    An inapplicable plan is an engine bug (or a task-identity mismatch); it is
    excluded from every score rather than silently inflating them.
    """
    if not plans:
        return []
    from behaviour_diversity_counter import InapplicablePlanError

    usable = []
    dropped = 0
    for plan in plans:
        try:
            counter.behaviours([plan])
            usable.append(plan)
        except InapplicablePlanError:
            dropped += 1
    if dropped:
        result["logs"].append(
            f"{dropped} plans were not applicable to the prepared task and "
            "were excluded from the scores")
    return usable


def _plans_to_pddl(task, plans, behaviours) -> List[str]:
    from unified_planning.io import PDDLWriter
    writer = PDDLWriter(task)
    rendered = []
    for plan, behaviour in zip(plans, behaviours):
        text = writer.get_plan(plan)
        rendered.append(f"{text};{len(plan.actions)} cost (unit)"
                        f"\n;behaviour: {behaviour.replace(chr(10), ' ')}")
    return rendered
