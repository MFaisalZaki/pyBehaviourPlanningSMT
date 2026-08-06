"""Task discovery: what a benchmark repository holds.

Two repository layouts are recognised, following aspbench (whose discovery
this is a lean adaptation of):

``api.py``   a domain directory with an ``api.py`` that defines a ``domains``
             list of ``{'name', 'ipc', 'problems': [(domain, problem), ...]}``
             dicts, with the paths relative to the *parent* of that directory.
             This is AI-Planning/classical-domains and pyPMT/numeric-domains.

``flat``     a directory with a single domain file (``domain*.pddl``) and its
             problems as siblings — the shape of tutorials/pddls and of most
             hand-made task sets.

The track a task belongs to is decided by *reading the domain file*, not by
which repository it came from: a ``(:functions ...)`` block makes it numeric,
anything else is classical. Durative-action (temporal) domains are outside
this planner's scope and are skipped with a note on stderr. The
oversubscription track is not discovered at all: it is derived from the
classical tasks at generation time by pricing their goals.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from fnmatch import fnmatch
from typing import Dict, List, Optional, Sequence

_PRUNED = {"__pycache__", "generator", "generators", "venv", "node_modules"}

_COMMENT_RE = re.compile(r";[^\n]*")
_IPC_YEAR_RE = re.compile(r"ipc[-_]?(\d{4})", re.IGNORECASE)
_TRAILING_NUM_RE = re.compile(r"(\d+)(?!.*\d)")
_NATURAL_RE = re.compile(r"(\d+)")
_NUMERIC_UPDATE_RE = re.compile(
    r"\(\s*(?:increase|decrease|assign|scale-up|scale-down)\s+\(\s*([a-z0-9_-]+)")
_NUMERIC_COMPARE_RE = re.compile(r"\(\s*(?:<=|>=|<|>)[\s(]")


@dataclass
class Task:
    task_id: str
    suite: str
    domain: str
    instance: str
    track: str
    domain_file: str
    problem_file: str
    ipc_year: Optional[str] = None
    instance_number: Optional[int] = None
    resources: Optional[str] = None  # (:resource ...) declaration string

    def to_dict(self) -> dict:
        return asdict(self)


def _natural_key(text: str):
    return [int(part) if part.isdigit() else part
            for part in _NATURAL_RE.split(text)]


def _sniff_track(domain_file: str) -> Optional[str]:
    """classical | numeric, or None for domains this planner cannot run."""
    try:
        with open(domain_file, errors="replace") as handle:
            text = _COMMENT_RE.sub("", handle.read().lower())
    except OSError:
        return None
    if ":durative-action" in text or "(:process" in text or "(:event" in text:
        return None  # temporal / PDDL+: out of scope
    if "(:functions" not in text:
        return "classical"
    updated = set(_NUMERIC_UPDATE_RE.findall(text))
    if updated - {"total-cost"} or _NUMERIC_COMPARE_RE.search(text):
        return "numeric"
    # Functions that only ever accumulate total-cost — the IPC action-costs
    # idiom, including static per-object cost functions like road-length —
    # do not make the planning numeric: the task is classical.
    return "classical"


def _instance_number(problem_file: str, position: int) -> int:
    """The instance number: the trailing number in the file name, or the
    1-based position in the domain's problem list when there is none."""
    stem = os.path.splitext(os.path.basename(problem_file))[0]
    match = _TRAILING_NUM_RE.search(stem)
    return int(match.group(1)) if match else position


def _from_api(dirpath: str, suite: str, root: str) -> List[Task]:
    """Load ``<dirpath>/api.py`` and read its ``domains`` list."""
    api = os.path.join(dirpath, "api.py")
    module_name = f"bpbench_api_{abs(hash(dirpath))}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, api)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as error:  # a broken api.py must not sink the sweep
        print(f"note: skipping {api} ({error})", file=sys.stderr)
        return []

    entries = getattr(module, "domains", None)
    if not isinstance(entries, list):
        return []

    parent = os.path.dirname(dirpath)
    tasks: List[Task] = []
    for entry in entries:
        if not isinstance(entry, dict) or "problems" not in entry:
            continue
        domain_name = str(entry.get("name") or os.path.basename(dirpath))
        year = entry.get("ipc")
        year = str(year) if year not in (None, "") else None
        pairs = []
        for pair in entry["problems"]:
            try:
                pairs.append((pair[0], pair[1]))
            except (TypeError, IndexError):
                continue
        # The paper experiments number an instance by its 1-based position in
        # the api.py problem list sorted by problem path (plain string order,
        # numbered before dropping missing files). The same numbering is
        # reproduced here, because it is what the paper's instance-selection
        # lists and the ru-info resource files key instances by.
        pairs.sort(key=lambda p: p[1])
        for number, (domain_rel, problem_rel) in enumerate(pairs, start=1):
            domain_file = os.path.join(parent, domain_rel)
            problem_file = os.path.join(parent, problem_rel)
            if not (os.path.exists(domain_file) and os.path.exists(problem_file)):
                continue
            track = _sniff_track(domain_file)
            if track is None:
                continue
            instance = os.path.splitext(os.path.basename(problem_file))[0]
            tasks.append(Task(
                task_id="", suite=suite, domain=domain_name, instance=instance,
                track=track, domain_file=os.path.abspath(domain_file),
                problem_file=os.path.abspath(problem_file), ipc_year=year,
                instance_number=number))
    if not tasks:
        print(f"note: no tasks from {dirpath} "
              f"(api.py lists no existing (domain, problem) pair)", file=sys.stderr)
    return tasks


def _from_flat(dirpath: str, filenames: Sequence[str], suite: str) -> List[Task]:
    """A directory holding one domain file and its problems as siblings."""
    pddls = sorted((f for f in filenames if f.endswith(".pddl")), key=_natural_key)
    domain_files = [f for f in pddls if "domain" in f.lower()]
    if len(domain_files) != 1:
        return []
    domain_file = os.path.join(dirpath, domain_files[0])
    track = _sniff_track(domain_file)
    if track is None:
        return []
    domain_name = os.path.basename(dirpath.rstrip(os.sep))
    tasks: List[Task] = []
    position = 0
    for name in pddls:
        if name == domain_files[0]:
            continue
        position += 1
        problem_file = os.path.join(dirpath, name)
        tasks.append(Task(
            task_id="", suite=suite, domain=domain_name,
            instance=os.path.splitext(name)[0], track=track,
            domain_file=os.path.abspath(domain_file),
            problem_file=os.path.abspath(problem_file),
            ipc_year=_ipc_year_from_path(dirpath),
            instance_number=_instance_number(problem_file, position)))
    return tasks


def _ipc_year_from_path(path: str) -> Optional[str]:
    match = _IPC_YEAR_RE.search(path)
    return match.group(1) if match else None


def discover(tasks_dirs: Sequence[str]) -> List[Task]:
    """Scan the given repositories; ``LABEL=PATH`` names the suite."""
    tasks: List[Task] = []
    for spec in tasks_dirs:
        label, _, path = spec.rpartition("=")
        path = os.path.abspath(path or spec)
        suite = label or os.path.basename(path.rstrip(os.sep))
        if not os.path.isdir(path):
            print(f"note: {path} is not a directory, skipped", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in _PRUNED and not d.startswith("."))
            if "api.py" in filenames:
                found = _from_api(dirpath, suite, path)
                if found:
                    tasks.extend(found)
                    dirnames[:] = []  # the api speaks for the whole directory
                    continue
            found = _from_flat(dirpath, filenames, suite)
            tasks.extend(found)

    # Stable ids after the full scan, so duplicates across suites stay apart.
    seen: Dict[str, int] = {}
    for task in tasks:
        base = f"{task.suite}__{task.domain}__{task.instance}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        task.task_id = base if count == 0 else f"{base}__{count}"
    return tasks


def paper_key(task: Task) -> str:
    """The instance's identity in the paper experiments' selection lists:
    ``"(ipc-year, domain, instance-number)"`` with ``None`` for non-IPC
    domains — the exact membership string the paper experiments' retired
    generate-benchmark-slurm-tasks.py tested."""
    year = task.ipc_year if task.ipc_year is not None else "None"
    return f"({year}, {task.domain}, {task.instance_number})"


def load_instance_selection(spec: Optional[str]) -> Optional[set]:
    """Resolve an instance-selection setting into a set of paper keys.

    ``None``/``"none"`` disables the filter, ``"paper"`` loads the selection
    shipped with the harness (the paper experiments' classical_instances
    list), and anything else is read as a file with one key per line
    (``#`` comments allowed).
    """
    if not spec or spec == "none":
        return None
    if spec == "paper":
        from .paper_selection import CLASSICAL_INSTANCES
        return set(CLASSICAL_INSTANCES)
    with open(spec) as handle:
        return {line.strip() for line in handle
                if line.strip() and not line.lstrip().startswith("#")}


def select(tasks: List[Task], tracks: Sequence[str], include: Sequence[str],
           exclude: Sequence[str], cap: int, selection: str,
           instance_selection: Optional[set] = None) -> List[Task]:
    """Filter by track and domain patterns, then cap instances per domain.

    ``instance_selection`` restricts the *classical* tasks to the given paper
    keys (one task per key); numeric tasks always pass, so a selection-driven
    sweep runs the listed classical instances — and, since oversubscription
    is derived from the classical selection, the listed instances there too —
    but every numeric instance.
    """
    chosen = [t for t in tasks if t.track in tracks]
    if instance_selection is not None:
        kept = [t for t in chosen if t.track != "classical"]
        candidates: Dict[str, List[Task]] = {}
        for task in chosen:
            if task.track != "classical":
                continue
            directory = os.path.basename(os.path.dirname(task.domain_file)).lower()
            if "adl" in directory:
                continue  # the paper's parser skips adl directories
            key = paper_key(task)
            if key in instance_selection:
                candidates.setdefault(key, []).append(task)
        for group in candidates.values():
            # The same (year, name) pair can exist in sibling directories
            # (opt/sat tracks of one IPC, strips/full variants). The paper's
            # stated intent is the strips variant; the smallest path breaks
            # the remaining ties deterministically.
            group.sort(key=lambda t: (
                0 if "strips" in os.path.basename(
                    os.path.dirname(t.domain_file)).lower() else 1,
                t.domain_file, t.problem_file))
            kept.append(group[0])
        chosen = kept
    if include:
        chosen = [t for t in chosen if any(fnmatch(t.domain, p) for p in include)]
    if exclude:
        chosen = [t for t in chosen if not any(fnmatch(t.domain, p) for p in exclude)]

    if cap and cap > 0:
        by_domain: Dict[tuple, List[Task]] = {}
        for task in chosen:
            by_domain.setdefault((task.suite, task.domain), []).append(task)
        capped: List[Task] = []
        for group in by_domain.values():
            group.sort(key=lambda t: _natural_key(t.instance))
            if len(group) <= cap:
                capped.extend(group)
            elif selection == "first":
                capped.extend(group[:cap])
            else:  # "even": spread the cap across the instance range
                step = (len(group) - 1) / (cap - 1) if cap > 1 else 0
                indices = sorted({round(i * step) for i in range(cap)})
                capped.extend(group[i] for i in indices)
        chosen = capped

    chosen.sort(key=lambda t: (t.track, t.suite, t.domain, _natural_key(t.instance)))
    return chosen


def attach_resources(tasks: List[Task], resources_dir: Optional[str]) -> None:
    """Attach per-instance (:resource ...) declarations from a
    classical-domains-ru-info style directory (JSON files declaring their
    domain/year in an ``info`` block, instances keyed by number), or from
    plain ``<domain>.txt`` files of declarations."""
    if not resources_dir or not os.path.isdir(resources_dir):
        return

    index: Dict[tuple, Dict[str, str]] = {}
    plain: Dict[str, str] = {}
    import json as _json
    for folder, _dirs, files in os.walk(resources_dir):
        for name in files:
            path = os.path.join(folder, name)
            if name.endswith(".json"):
                try:
                    with open(path) as handle:
                        declared = _json.load(handle)
                except (_json.JSONDecodeError, OSError):
                    continue
                info = declared.get("info") or {}
                key = (str(info.get("domain")), str(info.get("year")))
                index[key] = declared.get("instances") or {}
            elif name.endswith(".txt"):
                try:
                    with open(path) as handle:
                        plain[os.path.splitext(name)[0]] = handle.read()
                except OSError:
                    continue

    for task in tasks:
        # Strict (domain, year) matching only: both shipped datasets key their
        # files exactly (classical ru-info by IPC year, numeric fn-info by
        # 'None'), and a looser same-name fallback would cross-attach numeric
        # declarations to classical tasks of the same domain name.
        instances = index.get((task.domain, str(task.ipc_year)))
        if instances is not None:
            task.resources = instances.get(str(task.instance_number))
        if task.resources is None and task.domain in plain:
            task.resources = plain[task.domain]


def summarize(tasks: List[Task]) -> dict:
    instances_per_track: Dict[str, int] = {}
    domains_per_track: Dict[str, set] = {}
    for task in tasks:
        instances_per_track[task.track] = instances_per_track.get(task.track, 0) + 1
        domains_per_track.setdefault(task.track, set()).add(task.domain)
    return {
        "instances_per_track": instances_per_track,
        "domains_per_track": {k: len(v) for k, v in domains_per_track.items()},
    }
