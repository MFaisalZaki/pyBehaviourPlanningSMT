"""Generate one run command per (planner, task, k), plus slurm job arrays.

Sandbox layout (the aspbench shape):

    sandbox/
    ├── tasks.json                  the resolved task list (what "attempted" means)
    ├── resources/<task-id>.txt     per-task (:resource ...) declarations
    ├── cmds/<planner>.txt          one `bpbench solve` command per line
    ├── slurm/bpbench-<planner>.sbatch
    ├── slurm/submit_all.sh
    ├── run_local.sh                the same commands through xargs -P
    ├── results/<planner>/<task>__k<k>.json
    ├── errors/
    └── analysis/
"""

from __future__ import annotations

import json
import os
import shlex
import stat
from typing import List

from .config import Experiment, seconds_to_slurm
from . import tasks as tasks_module


def collect_tasks(args, experiment: Experiment):
    found = tasks_module.discover(args.tasks_dir)
    tracks = args.tracks or [t for t in experiment.tracks if t != "oversubscription"]
    # oversubscription is not discovered; it reuses the classical selection.
    tracks = [t for t in dict.fromkeys(tracks) if t != "oversubscription"]
    instance_selection = tasks_module.load_instance_selection(
        args.instance_selection if args.instance_selection is not None
        else experiment.instance_selection)
    selected = tasks_module.select(
        found, tracks,
        args.domains if args.domains is not None else experiment.include_domains,
        args.exclude_domains if args.exclude_domains is not None else experiment.exclude_domains,
        args.max_instances_per_domain if args.max_instances_per_domain is not None
        else experiment.max_instances_per_domain,
        args.selection or experiment.selection,
        instance_selection)
    tasks_module.attach_resources(selected, experiment.resources_dir)
    return selected


def _expand_tracks(selected, experiment: Experiment):
    """Duplicate classical tasks into the oversubscription track when asked."""
    expanded = list(selected)
    if "oversubscription" in experiment.tracks:
        for task in selected:
            if task.track != "classical":
                continue
            clone = tasks_module.Task(**{**task.to_dict(),
                                         "track": "oversubscription",
                                         "task_id": task.task_id + "__osp"})
            expanded.append(clone)
    return expanded


def generate(args) -> int:
    experiment = Experiment(args.exp_dir)
    sandbox = os.path.abspath(args.sandbox_dir)
    for sub in ("cmds", "slurm", "results", "errors", "runs", "resources"):
        os.makedirs(os.path.join(sandbox, sub), exist_ok=True)

    selected = collect_tasks(args, experiment)
    if not selected:
        print("no tasks found — check --tasks-dir")
        return 1
    expanded = _expand_tracks(selected, experiment)

    with open(os.path.join(sandbox, "tasks.json"), "w") as handle:
        json.dump({
            "tasks": [t.to_dict() for t in expanded],
            "k-plans": experiment.k_plans,
            "quality-bound": experiment.quality_bound,
            "planners": [{"tag": p["planner-tag"], "engine": p["engine"],
                          "tracks": p["tracks"]} for p in experiment.planners],
        }, handle, indent=2)

    # Per-task resource declarations become files the solve command can point at.
    resource_files = {}
    for task in expanded:
        if task.resources:
            path = os.path.join(sandbox, "resources", f"{task.task_id}.txt")
            if task.task_id not in resource_files:
                with open(path, "w") as handle:
                    handle.write(task.resources)
                resource_files[task.task_id] = path

    # Solve commands run either through an Apptainer image (the compute node
    # needs nothing but apptainer), inside a virtualenv, or bare.
    image = args.apptainer_image if args.apptainer_image is not None \
        else experiment.apptainer_image
    if image == "none":
        image = None
    activate = ""
    if image:
        binds = {sandbox, os.path.abspath(args.exp_dir)}
        for spec in args.tasks_dir:
            _label, _, path = spec.rpartition("=")
            binds.add(os.path.abspath(path or spec))
        activate = (f"apptainer exec --cleanenv "
                    f"--bind {shlex.quote(','.join(sorted(binds)))} "
                    f"{shlex.quote(os.path.abspath(image))} ")
    elif args.venv_dir:
        activate = f". {shlex.quote(os.path.abspath(args.venv_dir))}/bin/activate && "

    total_commands = 0
    command_files: List[str] = []
    for planner in experiment.planners:
        lines: List[str] = []
        for task in expanded:
            if task.track not in planner["tracks"]:
                continue
            for k in experiment.k_plans:
                result = os.path.join(sandbox, "results", planner["planner-tag"],
                                      f"{task.task_id}__k{k}.json")
                if args.skip_existing and os.path.exists(result):
                    continue
                command = (
                    f"{activate}bpbench solve"
                    f" --planner-cfg {shlex.quote(planner['path'])}"
                    f" --domain {shlex.quote(task.domain_file)}"
                    f" --problem {shlex.quote(task.problem_file)}"
                    f" --task-id {shlex.quote(task.task_id)}"
                    f" --suite {shlex.quote(task.suite)}"
                    f" --domain-name {shlex.quote(task.domain)}"
                    f" --instance {shlex.quote(task.instance)}"
                    f" --track {task.track}"
                    f" --k {k}"
                    f" --quality-bound {experiment.quality_bound}"
                    f" --results-dir {shlex.quote(os.path.join(sandbox, 'results', planner['planner-tag']))}"
                    f" --errors-dir {shlex.quote(os.path.join(sandbox, 'errors'))}"
                    f" --run-dir {shlex.quote(os.path.join(sandbox, 'runs', planner['planner-tag'] + '__' + task.task_id + '__k' + str(k)))}"
                    f" --time-limit {experiment.time_limit}"
                    f" --memory-limit {experiment.memory_limit}"
                )
                if task.task_id in resource_files:
                    command += f" --resources {shlex.quote(resource_files[task.task_id])}"
                lines.append(command)
        if not lines:
            continue
        path = os.path.join(sandbox, "cmds", f"{planner['planner-tag']}.txt")
        with open(path, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        command_files.append(path)
        total_commands += len(lines)
        _write_sbatch(sandbox, experiment, planner["planner-tag"], len(lines),
                      uses_apptainer=bool(image))

    _write_submit_all(sandbox)
    _write_run_local(sandbox, args.local_jobs)

    print(f"{len(expanded)} tasks × {len(experiment.k_plans)} k values → "
          f"{total_commands} runs across {len(command_files)} planners")
    print(f"  sbatch:  bash {os.path.join(sandbox, 'slurm', 'submit_all.sh')}")
    print(f"  locally: bash {os.path.join(sandbox, 'run_local.sh')} "
          f"[jobs, default {args.local_jobs}]")
    return 0


def _write_sbatch(sandbox: str, experiment: Experiment, tag: str, count: int,
                  uses_apptainer: bool = False) -> None:
    """Write the job array(s) for one planner's command file.

    Slurm rejects arrays whose highest index reaches the cluster's
    MaxArraySize (`sbatch: error: ... Invalid job array specification`), so
    runs beyond `cfgs.slurm.max-array-size` are split into several scripts,
    each a 0-based array over a slice of the command file. Set the knob to
    your cluster's limit (`scontrol show config | grep MaxArraySize`).
    """
    slurm = experiment.slurm
    time_limit = seconds_to_slurm(experiment.time_limit + experiment.slurm_time_headroom)
    memory = experiment.memory_limit + experiment.slurm_memory_headroom
    max_parallel = slurm.get("max-parallel-jobs") or 50
    max_array = int(slurm.get("max-array-size") or 1000)
    if max_array <= 0:
        max_array = count

    chunks = [(offset, min(max_array, count - offset))
              for offset in range(0, count, max_array)]
    for index, (offset, size) in enumerate(chunks):
        suffix = "" if len(chunks) == 1 else f"-part{index:02d}"
        lines = [
            "#!/bin/bash",
            f"#SBATCH --job-name=bpbench-{tag}{suffix}",
            f"#SBATCH --time={time_limit}",
            f"#SBATCH --mem={memory}M",
            f"#SBATCH --cpus-per-task={slurm.get('cpus-per-task', 1)}",
            f"#SBATCH --array=0-{size - 1}%{max_parallel}",
            f"#SBATCH --output={sandbox}/slurm/logs/{tag}{suffix}-%A_%a.out",
        ]
        if slurm.get("partition"):
            lines.append(f"#SBATCH --partition={slurm['partition']}")
        if slurm.get("account"):
            lines.append(f"#SBATCH --account={slurm['account']}")
        lines.extend(slurm.get("extra-directives") or [])
        lines.append("")
        if uses_apptainer:
            # Clusters commonly ship apptainer as a module; loading it is a
            # no-op where it is already on PATH.
            lines.append("module load apptainer 2>/dev/null || true")
        lines += [
            f"mkdir -p {sandbox}/slurm/logs",
            f"LINE=$(( SLURM_ARRAY_TASK_ID + {offset + 1} ))",
            f'CMD=$(sed -n "${{LINE}}p" {sandbox}/cmds/{tag}.txt)',
            'eval "$CMD"',
            "",
        ]
        with open(os.path.join(sandbox, "slurm", f"bpbench-{tag}{suffix}.sbatch"),
                  "w") as handle:
            handle.write("\n".join(lines))
    if len(chunks) > 1:
        print(f"  {tag}: {count} runs split into {len(chunks)} job arrays "
              f"of at most {max_array} tasks")


def _write_submit_all(sandbox: str) -> None:
    path = os.path.join(sandbox, "slurm", "submit_all.sh")
    with open(path, "w") as handle:
        handle.write(
            "#!/bin/bash\n"
            f"mkdir -p {sandbox}/slurm/logs\n"
            f"for f in {sandbox}/slurm/bpbench-*.sbatch; do\n"
            "    echo \"sbatch $f\"\n"
            "    sbatch \"$f\"\n"
            "done\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


def _write_run_local(sandbox: str, default_jobs: int) -> None:
    path = os.path.join(sandbox, "run_local.sh")
    with open(path, "w") as handle:
        handle.write(
            "#!/bin/bash\n"
            "# Run the whole sweep locally: run_local.sh [parallel-jobs]\n"
            f"JOBS=${{1:-{default_jobs}}}\n"
            f"cat {sandbox}/cmds/*.txt | xargs -P \"$JOBS\" -I CMD bash -c CMD\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
