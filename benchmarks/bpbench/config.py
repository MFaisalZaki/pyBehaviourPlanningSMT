"""Experiment configuration: exp-details.json + planners/*.json.

An experiment is a directory, the same shape aspbench (and pyPMTEvalToolkit)
uses:

    experiment/
    ├── exp-details.json        limits + task selection + diverse-planning knobs
    └── planners/
        ├── fbi-bdc.json
        ├── fbi-bms.json
        ├── fbi-naive.json
        ├── fi-bdc.json
        ├── fi-bms.json
        ├── symk-bdc.json
        └── symk-bms.json

Every ``.json`` in ``planners/`` is benchmarked; to leave a planner out,
delete its file.
"""

from __future__ import annotations

import json
import os
import re
from typing import List, Optional


TRACKS = ("classical", "numeric", "oversubscription")

DEFAULT_EXP_DETAILS = {
    "cfgs": {
        "timelimit": "00:30:00",
        "memorylimit": "8GB",
        # Path to an Apptainer image (benchmarks/Apptainer.def builds one);
        # when set, every generated solve command runs through
        # `apptainer exec`, so the compute nodes need nothing installed.
        "apptainer-image": None,
        "slurm-time-headroom": "00:05:00",
        "slurm-memory-headroom": "1GB",
        "slurm": {
            "cpus-per-task": 1,
            "partition": None,
            "account": None,
            "max-parallel-jobs": 50,
            # Runs beyond this are split into several job arrays; set it to
            # your cluster's MaxArraySize (scontrol show config | grep -i
            # maxarraysize), or submission fails with "Invalid job array
            # specification".
            "max-array-size": 1000,
            "extra-directives": [],
        },
    },
    "tasks": {
        # oversubscription is derived from the classical tasks by pricing the
        # goals (the tutorials' add_utility_values recipe), not discovered.
        "tracks": ["classical", "numeric", "oversubscription"],
        "k-plans": [5],
        "quality-bound": 1.0,
        "max-instances-per-domain": 10,
        "selection": "even",
        "include-domains": [],
        "exclude-domains": [],
        # Restrict the classical track (and the oversubscription track derived
        # from it) to a fixed instance list: null runs everything, "paper"
        # uses the paper experiments' selection shipped with the harness
        # (bpbench/paper_selection.py), and a path reads one
        # "(year, domain, instance)" key per line. Numeric tasks always run
        # in full, whatever this is set to.
        "instance-selection": None,
        # Directory with per-instance (:resource ...) declarations in the
        # classical-domains-ru-info JSON layout; null disables the ru/fn
        # dimensions. benchmarks/data holds both paper datasets (classical ru
        # and numeric fn declarations).
        "resources-dir": None,
    },
}

# Planner configuration templates. `engine` picks the implementation in
# engines.py; everything under `params` goes to it verbatim.
DEFAULT_PLANNERS = {
    "fbi-bdc.json": {
        "planner-tag": "FBI-bdc",
        "engine": "fbi",
        "params": {"indicator": "bdc"},
        "tracks": ["classical", "numeric", "oversubscription"],
    },
    "fbi-bms.json": {
        "planner-tag": "FBI-bms",
        "engine": "fbi",
        "params": {"indicator": "bms"},
        "tracks": ["classical", "numeric", "oversubscription"],
    },
    # The naive FBI: no behaviour-space dimensions, so the loop degenerates to
    # forbid-plan-and-regenerate. What diversity that buys is measured by the
    # same judge dimensions as everyone else's plans.
    "fbi-naive.json": {
        "planner-tag": "FBI-naive",
        "engine": "fbi",
        "params": {"indicator": "bdc", "naive": True},
        "tracks": ["classical", "numeric", "oversubscription"],
    },
    # ForbidIterative generates a pool of pool-factor * k plans, then the
    # subset of k is extracted with BehaviourDiversityCounter.
    "fi-bdc.json": {
        "planner-tag": "FI-bdc",
        "engine": "fi",
        "params": {"pool-factor": 5, "extract-indicator": "bdc"},
        "tracks": ["classical"],
    },
    "fi-bms.json": {
        "planner-tag": "FI-bms",
        "engine": "fi",
        "params": {"pool-factor": 5, "extract-indicator": "bmaxsum"},
        "tracks": ["classical"],
    },
    # SymK is the oversubscription baseline (ForbidIterative needs hard
    # goals): the priced-goals task is compiled to classical planning with
    # collect/forgo bookkeeping actions whose costs rank plans by forgone
    # utility and then by length, SymK's symbolic top-k search generates the
    # pool, and the subset of k is extracted with BehaviourDiversityCounter.
    "symk-bdc.json": {
        "planner-tag": "SymK-bdc",
        "engine": "symk",
        "params": {"pool-factor": 5, "extract-indicator": "bdc"},
        "tracks": ["oversubscription"],
    },
    "symk-bms.json": {
        "planner-tag": "SymK-bms",
        "engine": "symk",
        "params": {"pool-factor": 5, "extract-indicator": "bmaxsum"},
        "tracks": ["oversubscription"],
    },
}


def parse_time_limit(value) -> int:
    """Accepts 1800, "1800", "30m", "00:30:00" -> seconds."""
    if value is None:
        return 1800
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if re.fullmatch(r"\d+", text):
        return int(text)
    match = re.fullmatch(r"(\d+)\s*([smh])", text)
    if match:
        return int(match.group(1)) * {"s": 1, "m": 60, "h": 3600}[match.group(2)]
    match = re.fullmatch(r"(\d+):(\d+):(\d+)", text)
    if match:
        hours, minutes, seconds = (int(g) for g in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError(f"cannot parse time limit: {value!r}")


def parse_memory_limit(value) -> int:
    """Accepts 8192, "8192", "8GB", "8 gb", "512MB" -> MB."""
    if value is None:
        return 8192
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().replace(" ", "")
    if re.fullmatch(r"\d+", text):
        return int(text)
    match = re.fullmatch(r"(\d+)(gb|g|mb|m)", text)
    if match:
        amount = int(match.group(1))
        return amount * 1024 if match.group(2) in ("gb", "g") else amount
    raise ValueError(f"cannot parse memory limit: {value!r}")


def seconds_to_slurm(seconds: int) -> str:
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class Experiment:
    """The parsed experiment directory."""

    def __init__(self, exp_dir: str):
        self.exp_dir = os.path.abspath(exp_dir)
        details_path = os.path.join(self.exp_dir, "exp-details.json")
        with open(details_path) as handle:
            self.details = json.load(handle)

        cfgs = self.details.get("cfgs", {})
        self.time_limit = parse_time_limit(cfgs.get("timelimit"))
        self.memory_limit = parse_memory_limit(cfgs.get("memorylimit"))
        self.slurm_time_headroom = parse_time_limit(cfgs.get("slurm-time-headroom", "00:05:00"))
        self.slurm_memory_headroom = parse_memory_limit(cfgs.get("slurm-memory-headroom", "1GB"))
        self.apptainer_image = cfgs.get("apptainer-image")
        self.slurm = {**DEFAULT_EXP_DETAILS["cfgs"]["slurm"], **cfgs.get("slurm", {})}

        tasks = {**DEFAULT_EXP_DETAILS["tasks"], **self.details.get("tasks", {})}
        self.tracks = [t for t in tasks.get("tracks", []) if t in TRACKS]
        self.k_plans = [int(k) for k in tasks.get("k-plans", [5])]
        self.quality_bound = float(tasks.get("quality-bound", 1.0))
        self.max_instances_per_domain = int(tasks.get("max-instances-per-domain") or 0)
        self.selection = tasks.get("selection", "even")
        self.include_domains = tasks.get("include-domains") or []
        self.exclude_domains = tasks.get("exclude-domains") or []
        self.instance_selection = tasks.get("instance-selection")
        self.resources_dir = tasks.get("resources-dir")

        self.planners = self._load_planners()

    def _load_planners(self) -> List[dict]:
        planners_dir = os.path.join(self.exp_dir, "planners")
        configurations = []
        if not os.path.isdir(planners_dir):
            return configurations
        for name in sorted(os.listdir(planners_dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(planners_dir, name)
            with open(path) as handle:
                configuration = json.load(handle)
            configuration.setdefault("planner-tag", os.path.splitext(name)[0])
            configuration.setdefault("engine", "fbi")
            configuration.setdefault("params", {})
            configuration.setdefault("tracks", list(TRACKS))
            configuration["path"] = path
            configurations.append(configuration)
        return configurations


def write_default_experiment(exp_dir: str, time_limit: Optional[str] = None,
                             memory_limit: Optional[str] = None,
                             resources_dir: Optional[str] = None) -> str:
    """Write exp-details.json and the starter planner configurations.

    Existing files are never overwritten, so local edits survive a re-run.
    """
    os.makedirs(os.path.join(exp_dir, "planners"), exist_ok=True)

    details = json.loads(json.dumps(DEFAULT_EXP_DETAILS))  # deep copy
    if time_limit:
        details["cfgs"]["timelimit"] = time_limit
        parse_time_limit(time_limit)  # validate now, not at generate time
    if memory_limit:
        details["cfgs"]["memorylimit"] = memory_limit
        parse_memory_limit(memory_limit)
    if resources_dir:
        details["tasks"]["resources-dir"] = os.path.abspath(resources_dir)

    details_path = os.path.join(exp_dir, "exp-details.json")
    if not os.path.exists(details_path):
        with open(details_path, "w") as handle:
            json.dump(details, handle, indent=4)

    for name, configuration in DEFAULT_PLANNERS.items():
        path = os.path.join(exp_dir, "planners", name)
        if not os.path.exists(path):
            with open(path, "w") as handle:
                json.dump(configuration, handle, indent=4)

    return details_path
