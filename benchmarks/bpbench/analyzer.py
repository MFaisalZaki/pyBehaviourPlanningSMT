"""Aggregate the result JSONs into results.csv and a summary report.

Beyond coverage and runtime, the summary carries the two diversity scores the
runs were judged by — behaviour diversity count (bdc) and behaviour max-sum
(bmaxsum), both computed by BehaviourDiversityCounter over the returned
k-set — as means over solved runs, and again head-to-head over the runs that
*every* planner solved, which is the comparison the paper tables are built
from. MISSING is counted against tasks.json, so coverage is never computed
over a quietly smaller denominator.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
from typing import Dict, List


def _load_results(results_dir: str) -> List[dict]:
    rows = []
    if not os.path.isdir(results_dir):
        return rows
    for tag in sorted(os.listdir(results_dir)):
        planner_dir = os.path.join(results_dir, tag)
        if not os.path.isdir(planner_dir):
            continue
        for name in sorted(os.listdir(planner_dir)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(planner_dir, name)) as handle:
                    rows.append(json.load(handle))
            except (json.JSONDecodeError, OSError):
                continue
    return rows


def _expected_runs(sandbox: str) -> List[dict]:
    """Every (planner, task, k) the sweep was supposed to run."""
    path = os.path.join(sandbox, "tasks.json")
    if not os.path.exists(path):
        return []
    with open(path) as handle:
        manifest = json.load(handle)
    expected = []
    for planner in manifest.get("planners", []):
        for task in manifest.get("tasks", []):
            if task["track"] not in planner.get("tracks", []):
                continue
            for k in manifest.get("k-plans", []):
                expected.append({
                    "planner": planner["tag"], "task-id": task["task_id"],
                    "track": task["track"], "domain": task["domain"], "k": k,
                })
    return expected


def analyze(args) -> int:
    sandbox = os.path.abspath(args.sandbox_dir)
    results_dir = args.results_dir or os.path.join(sandbox, "results")
    output_dir = args.output_dir or os.path.join(sandbox, "analysis")
    os.makedirs(output_dir, exist_ok=True)

    results = _load_results(results_dir)
    expected = _expected_runs(sandbox)

    # --- results.csv -----------------------------------------------------
    columns = ["planner", "engine", "track", "suite", "domain", "instance",
               "task-id", "k", "quality-bound", "status", "returned-plans",
               "bdc", "bmaxsum", "total-seconds", "plan-seconds",
               "extract-seconds", "pool-size", "pool-bdc"]
    seen = {}
    csv_rows = []
    for row in results:
        task = row.get("task", {})
        planner = row.get("planner", {})
        record = {
            "planner": planner.get("tag"), "engine": planner.get("engine"),
            "track": task.get("track"), "suite": task.get("suite"),
            "domain": task.get("domain"), "instance": task.get("instance"),
            "task-id": task.get("task-id"), "k": task.get("k"),
            "quality-bound": task.get("quality-bound"),
            "status": row.get("status"),
            "returned-plans": row.get("plans", {}).get("returned", 0),
            "bdc": row.get("scores", {}).get("bdc"),
            "bmaxsum": row.get("scores", {}).get("bmaxsum"),
            "total-seconds": row.get("times", {}).get("total"),
            "plan-seconds": row.get("times", {}).get("plan"),
            "extract-seconds": row.get("times", {}).get("extract"),
            "pool-size": row.get("pool", {}).get("size"),
            "pool-bdc": row.get("pool", {}).get("bdc"),
        }
        csv_rows.append(record)
        seen[(record["planner"], record["task-id"], record["k"])] = record

    for run in expected:
        key = (run["planner"], run["task-id"], run["k"])
        if key not in seen:
            csv_rows.append({**{c: None for c in columns},
                             "planner": run["planner"], "track": run["track"],
                             "domain": run["domain"], "task-id": run["task-id"],
                             "k": run["k"], "status": "MISSING",
                             "returned-plans": 0})

    csv_path = os.path.join(output_dir, "results.csv")
    with open(csv_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(csv_rows)

    # --- summary ---------------------------------------------------------
    summary = {"planners": {}, "head-to-head": {}}
    lines: List[str] = []

    def fmt(value, digits=2):
        return "-" if value is None else f"{value:.{digits}f}"

    by_planner_track: Dict[tuple, List[dict]] = {}
    for record in csv_rows:
        by_planner_track.setdefault((record["planner"], record["track"]), []).append(record)

    lines.append(f"{'planner':<12}{'track':<18}{'att':>5}{'solved':>7}{'cov%':>7}"
                 f"{'mean-bdc':>10}{'mean-bmaxsum':>14}{'mean-time':>11}")
    lines.append("-" * 84)
    for (planner, track), records in sorted(by_planner_track.items()):
        solved = [r for r in records if r["status"] == "SOLVED"]
        bdc_values = [r["bdc"] for r in solved if r["bdc"] is not None]
        bmaxsum_values = [r["bmaxsum"] for r in solved if r["bmaxsum"] is not None]
        times = [r["total-seconds"] for r in solved if r["total-seconds"] is not None]
        entry = {
            "attempted": len(records), "solved": len(solved),
            "coverage": round(100.0 * len(solved) / len(records), 1) if records else 0.0,
            "mean-bdc": round(statistics.mean(bdc_values), 3) if bdc_values else None,
            "mean-bmaxsum": round(statistics.mean(bmaxsum_values), 3) if bmaxsum_values else None,
            "mean-time": round(statistics.mean(times), 2) if times else None,
            "statuses": {},
        }
        for record in records:
            entry["statuses"][record["status"]] = entry["statuses"].get(record["status"], 0) + 1
        summary["planners"].setdefault(planner, {})[track] = entry
        lines.append(f"{planner:<12}{track:<18}{entry['attempted']:>5}{entry['solved']:>7}"
                     f"{entry['coverage']:>7.1f}{fmt(entry['mean-bdc']):>10}"
                     f"{fmt(entry['mean-bmaxsum']):>14}{fmt(entry['mean-time']):>11}")

    # Head-to-head on the (task, k) pairs every planner of a track solved.
    planners = sorted({r["planner"] for r in csv_rows if r["planner"]})
    tracks = sorted({r["track"] for r in csv_rows if r["track"]})
    if len(planners) > 1:
        lines.append("")
        lines.append("head-to-head over the runs every planner solved:")
        for track in tracks:
            per_planner: Dict[str, Dict[tuple, dict]] = {}
            for record in csv_rows:
                if record["track"] != track:
                    continue
                per_planner.setdefault(record["planner"], {})[
                    (record["task-id"], record["k"])] = record
            active = {p: runs for p, runs in per_planner.items() if runs}
            if len(active) < 2:
                continue
            common = set.intersection(*(
                {key for key, r in runs.items() if r["status"] == "SOLVED"}
                for runs in active.values()))
            lines.append(f"  {track}: {len(common)} common runs")
            summary["head-to-head"][track] = {"common-runs": len(common), "planners": {}}
            if not common:
                continue
            for planner in sorted(active):
                records = [active[planner][key] for key in common]
                bdc_values = [r["bdc"] for r in records if r["bdc"] is not None]
                bmaxsum_values = [r["bmaxsum"] for r in records if r["bmaxsum"] is not None]
                times = [r["total-seconds"] for r in records if r["total-seconds"] is not None]
                entry = {
                    "mean-bdc": round(statistics.mean(bdc_values), 3) if bdc_values else None,
                    "mean-bmaxsum": round(statistics.mean(bmaxsum_values), 3) if bmaxsum_values else None,
                    "mean-time": round(statistics.mean(times), 2) if times else None,
                }
                summary["head-to-head"][track]["planners"][planner] = entry
                lines.append(f"    {planner:<12} mean-bdc {fmt(entry['mean-bdc'])}"
                             f"  mean-bmaxsum {fmt(entry['mean-bmaxsum'])}"
                             f"  mean-time {fmt(entry['mean-time'])}s")

    if getattr(args, "per_domain", False):
        lines.append("")
        lines.append(f"{'planner':<12}{'track':<18}{'domain':<28}{'solved':>7}{'att':>5}"
                     f"{'mean-bdc':>10}{'mean-bmaxsum':>14}")
        lines.append("-" * 94)
        by_domain: Dict[tuple, List[dict]] = {}
        for record in csv_rows:
            by_domain.setdefault((record["planner"], record["track"],
                                  record["domain"]), []).append(record)
        for (planner, track, domain), records in sorted(by_domain.items(),
                                                        key=lambda kv: tuple(map(str, kv[0]))):
            solved = [r for r in records if r["status"] == "SOLVED"]
            bdc_values = [r["bdc"] for r in solved if r["bdc"] is not None]
            bmaxsum_values = [r["bmaxsum"] for r in solved if r["bmaxsum"] is not None]
            lines.append(
                f"{str(planner):<12}{str(track):<18}{str(domain)[:27]:<28}{len(solved):>7}"
                f"{len(records):>5}"
                f"{fmt(statistics.mean(bdc_values) if bdc_values else None):>10}"
                f"{fmt(statistics.mean(bmaxsum_values) if bmaxsum_values else None):>14}")

    report = "\n".join(lines) + "\n"
    print(report)
    with open(os.path.join(output_dir, "summary.txt"), "w") as handle:
        handle.write(report)
    with open(os.path.join(output_dir, "summary.json"), "w") as handle:
        json.dump(summary, handle, indent=2)
    print(f"wrote {csv_path}, summary.txt and summary.json in {output_dir}")
    return 0
