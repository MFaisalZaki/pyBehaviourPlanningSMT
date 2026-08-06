"""Command line entry point: ``bpbench <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import __version__
from .config import TRACKS


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args) or 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bpbench",
        description="Benchmark harness for pyBehaviourPlanningSMT: FBI's diversity "
                    "indicators vs ForbidIterative + subset extraction, judged by "
                    "BehaviourDiversityCounter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "typical flow:\n"
            "  bpbench init      --exp-dir experiment\n"
            "  bpbench discover  --tasks-dir classical-domains\n"
            "  bpbench generate  --exp-dir experiment --sandbox-dir sandbox "
            "--tasks-dir classical-domains --venv-dir venv\n"
            "  bash sandbox/slurm/submit_all.sh    # or: bash sandbox/run_local.sh 8\n"
            "  bpbench analyze   --sandbox-dir sandbox\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"bpbench {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # -- init ----------------------------------------------------------
    init = subparsers.add_parser("init", help="write a starter experiment directory")
    init.add_argument("--exp-dir", required=True)
    init.add_argument("--time-limit", help="e.g. 00:30:00 or 30m")
    init.add_argument("--memory-limit", help="e.g. 8GB")
    init.add_argument("--resources-dir",
                      help="classical-domains-ru-info style directory for the ru/fn dimensions")
    init.set_defaults(func=_init)

    # -- discover ------------------------------------------------------
    discover = subparsers.add_parser(
        "discover", help="list the tasks found in a benchmark repository")
    _add_task_arguments(discover)
    discover.add_argument("--json", dest="as_json", action="store_true",
                          help="dump the task list as JSON instead of a summary")
    discover.set_defaults(func=_discover)

    # -- generate ------------------------------------------------------
    generate = subparsers.add_parser(
        "generate", help="generate one run command per (planner, task, k) plus slurm arrays")
    generate.add_argument("--exp-dir", required=True,
                          help="experiment directory (exp-details.json + planners/)")
    generate.add_argument("--sandbox-dir", required=True,
                          help="where commands, results and logs are written")
    _add_task_arguments(generate)
    generate.add_argument("--venv-dir", help="virtualenv the commands should activate")
    generate.add_argument("--apptainer-image", default=None,
                          help="run every solve command through `apptainer exec` "
                               "on this image (benchmarks/Apptainer.def builds one); "
                               '"none" forces plain commands. Default: the '
                               "experiment's cfgs.apptainer-image setting")
    generate.add_argument("--skip-existing", action="store_true",
                          help="skip runs that already have a result (resume a sweep)")
    generate.add_argument("--local-jobs", type=int, default=4,
                          help="default parallelism baked into run_local.sh (default: 4)")
    generate.set_defaults(func=_generate)

    # -- solve ---------------------------------------------------------
    solve = subparsers.add_parser("solve", help="run ONE (planner, task, k) (called by slurm)")
    solve.add_argument("--planner-cfg", required=True)
    solve.add_argument("--domain", required=True)
    solve.add_argument("--problem", required=True)
    solve.add_argument("--results-dir", required=True)
    solve.add_argument("--task-id", required=True)
    solve.add_argument("--suite", default="")
    solve.add_argument("--domain-name", default="")
    solve.add_argument("--instance", default="")
    solve.add_argument("--track", default="classical", choices=list(TRACKS))
    solve.add_argument("--k", type=int, required=True)
    solve.add_argument("--quality-bound", type=float, default=1.0)
    solve.add_argument("--resources", default=None,
                       help="file with (:resource ...) declarations for this task")
    solve.add_argument("--errors-dir", default=None)
    solve.add_argument("--run-dir", default=None,
                       help="this run's private working directory")
    solve.add_argument("--keep-run-dir", action="store_true",
                       help="do not delete the working directory afterwards")
    solve.add_argument("--time-limit", type=int, default=1800,
                       help="seconds; 0 disables the runner-side limit")
    solve.add_argument("--memory-limit", type=int, default=8192,
                       help="MB; 0 disables the runner-side limit")
    solve.set_defaults(func=_solve)

    # -- analyze -------------------------------------------------------
    analyze = subparsers.add_parser("analyze", help="aggregate results into a CSV and a report")
    analyze.add_argument("--sandbox-dir", required=True)
    analyze.add_argument("--results-dir", default=None, help="default: <sandbox>/results")
    analyze.add_argument("--output-dir", default=None, help="default: <sandbox>/analysis")
    analyze.add_argument("--per-domain", action="store_true", help="add a per-domain table")
    analyze.set_defaults(func=_analyze)

    return parser


def _add_task_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tasks-dir", action="append", required=True, metavar="[LABEL=]PATH",
                        help="benchmark repository to scan; repeatable. "
                             "Prefix with LABEL= to name the suite.")
    parser.add_argument("--tracks", nargs="+", choices=list(TRACKS), default=None,
                        help="restrict to these tracks (default: the experiment setting)")
    parser.add_argument("--domains", nargs="+", default=None,
                        help="glob patterns of domains to include")
    parser.add_argument("--exclude-domains", nargs="+", default=None,
                        help="glob patterns of domains to drop")
    parser.add_argument("--max-instances-per-domain", type=int, default=None,
                        help="cap per domain (0 or negative: no cap)")
    parser.add_argument("--selection", choices=("even", "first"), default=None,
                        help='"even" spreads the cap across the instance range, '
                             '"first" takes the smallest')
    parser.add_argument("--instance-selection", default=None,
                        help='restrict the classical track (and the derived '
                             'oversubscription track) to a fixed instance list: '
                             '"paper" for the paper experiments\' selection, '
                             '"none" to disable, or a file with one '
                             '"(year, domain, instance)" key per line. Numeric '
                             'tasks always run in full. Default: the experiment '
                             'setting (discover: none)')


# ----------------------------------------------------------------------
# Dispatch (imports stay inside, so `solve` is the only path needing UP)
# ----------------------------------------------------------------------

def _init(args) -> int:
    from .config import write_default_experiment
    path = write_default_experiment(args.exp_dir, args.time_limit, args.memory_limit,
                                    args.resources_dir)
    print(f"Wrote {path} and starter planner configurations in {args.exp_dir}/planners")
    return 0


def _discover(args) -> int:
    from . import tasks as tasks_module

    found = tasks_module.discover(args.tasks_dir)
    selected = tasks_module.select(
        found, args.tracks or ["classical", "numeric"],
        args.domains or [], args.exclude_domains or [],
        args.max_instances_per_domain or 0, args.selection or "even",
        tasks_module.load_instance_selection(args.instance_selection))

    if args.as_json:
        json.dump([t.to_dict() for t in selected], sys.stdout, indent=2)
        print()
        return 0

    counts = tasks_module.summarize(selected)
    print(f"{len(selected)} tasks")
    for track, count in sorted(counts["instances_per_track"].items()):
        print(f"  {track:<10} {count:>6} instances, "
              f"{counts['domains_per_track'].get(track, 0)} domains")
    print()
    print(f"{'track':<12}{'suite':<22}{'domain':<36}{'instances':>10}")
    print("-" * 80)
    grouped = {}
    for task in selected:
        grouped.setdefault((task.track, task.suite, task.domain), 0)
        grouped[(task.track, task.suite, task.domain)] += 1
    for (track, suite, domain), count in sorted(grouped.items()):
        print(f"{track:<12}{suite[:21]:<22}{domain[:35]:<36}{count:>10}")
    return 0


def _generate(args) -> int:
    from .generator import generate
    return generate(args)


def _solve(args) -> int:
    from .runner import solve
    return solve(args)


def _analyze(args) -> int:
    from .analyzer import analyze
    return analyze(args)


if __name__ == "__main__":
    sys.exit(main())
