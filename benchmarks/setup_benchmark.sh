#!/bin/bash
# One-script benchmark setup, the aspbench way: creates a virtualenv, installs
# the planner, its C++ core, the harness, ForbidIterative,
# BehaviourDiversityCounter and SymK (the oversubscription baseline), clones
# the benchmark repositories, writes an experiment with the limits you give,
# and generates the slurm job arrays.
#
#   ./setup_benchmark.sh
#   ./setup_benchmark.sh --time-limit 30m --memory-limit 8GB \
#                        --tracks "classical numeric oversubscription" \
#                        --instance-selection paper --k-plans "5" \
#                        --partition compute --yes
#
# With --apptainer-image the toolchain lives in a container instead of the
# host: the image is built from Apptainer.def if it does not exist (planner,
# harness, judge, ForbidIterative and SymK, all against the image's pinned
# protobuf), and every generated solve command runs through `apptainer exec`,
# so the compute nodes need nothing but apptainer:
#
#   ./setup_benchmark.sh --apptainer-image bpbench.sif --yes
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$HERE")"

TIME_LIMIT="00:30:00"
MEMORY_LIMIT="8GB"
TRACKS="classical numeric oversubscription"
# The classical and oversubscription tracks run the paper experiments'
# instance selection; numeric runs every instance. Hence no per-domain cap
# by default — pass --max-instances (or answer the prompt) to trim a sweep.
INSTANCE_SELECTION="paper"
MAX_INSTANCES=0
K_PLANS="5"
QUALITY_BOUND="1.0"
PARTITION=""
APPTAINER_IMAGE=""
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --time-limit)         TIME_LIMIT="$2"; shift 2;;
        --memory-limit)       MEMORY_LIMIT="$2"; shift 2;;
        --tracks)             TRACKS="$2"; shift 2;;
        --instance-selection) INSTANCE_SELECTION="$2"; shift 2;;
        --max-instances)      MAX_INSTANCES="$2"; shift 2;;
        --k-plans)            K_PLANS="$2"; shift 2;;
        --quality-bound)      QUALITY_BOUND="$2"; shift 2;;
        --partition)          PARTITION="$2"; shift 2;;
        --apptainer-image)    APPTAINER_IMAGE="$2"; shift 2;;
        --yes|-y)             ASSUME_YES=1; shift;;
        *) echo "unknown option: $1" >&2; exit 1;;
    esac
done

if [[ $ASSUME_YES -eq 0 ]]; then
    read -r -p "time limit per run [$TIME_LIMIT]: " answer;   TIME_LIMIT="${answer:-$TIME_LIMIT}"
    read -r -p "memory limit per run [$MEMORY_LIMIT]: " answer; MEMORY_LIMIT="${answer:-$MEMORY_LIMIT}"
    read -r -p "tracks [$TRACKS]: " answer;                   TRACKS="${answer:-$TRACKS}"
    read -r -p "instance selection for classical/oversubscription (paper/none/file) [$INSTANCE_SELECTION]: " answer
    INSTANCE_SELECTION="${answer:-$INSTANCE_SELECTION}"
    read -r -p "max instances per domain (0 = no cap) [$MAX_INSTANCES]: " answer; MAX_INSTANCES="${answer:-$MAX_INSTANCES}"
    read -r -p "k values [$K_PLANS]: " answer;                K_PLANS="${answer:-$K_PLANS}"
fi

if [[ -n "$APPTAINER_IMAGE" ]]; then
    command -v apptainer >/dev/null 2>&1 || module load apptainer 2>/dev/null || true
    command -v apptainer >/dev/null 2>&1 || {
        echo "apptainer is not on PATH (and 'module load apptainer' did not provide it)" >&2
        exit 1
    }
    if [[ ! -f "$APPTAINER_IMAGE" ]]; then
        echo "== building the Apptainer image (planner, harness, judge, FI, SymK) =="
        apptainer build "$APPTAINER_IMAGE" "$HERE/Apptainer.def"
    fi
    APPTAINER_IMAGE="$(cd "$(dirname "$APPTAINER_IMAGE")" && pwd)/$(basename "$APPTAINER_IMAGE")"
    # Everything lives in the image; the host only holds the task data and
    # the sandbox. $HERE covers both in the default layout.
    BPBENCH="apptainer exec --cleanenv --bind $HERE $APPTAINER_IMAGE bpbench"
else
    BPBENCH="bpbench"

    echo "== virtualenv =="
    python3 -m venv "$HERE/venv"
    # shellcheck disable=SC1091
    source "$HERE/venv/bin/activate"
    pip install --upgrade pip >/dev/null

    echo "== installing the planner and its C++ core =="
    pip install -e "$REPO_ROOT"
    (cd "$REPO_ROOT" && python build.py)

    echo "== installing the harness, the judge and ForbidIterative =="
    pip install -e "$HERE"
    pip install "git+https://github.com/MFaisalZaki/BehaviourDiversityCounter.git"
    pip install "git+https://github.com/MFaisalZaki/forbiditerative.git"

    echo "== SymK (the oversubscription baseline) =="
    [[ -d "$HERE/symk" ]] || \
        git clone --depth 1 https://github.com/speckdavid/symk.git "$HERE/symk"
    [[ -x "$HERE/symk/builds/release/bin/downward" ]] || \
        (cd "$HERE/symk" && python3 build.py release)
fi

echo "== benchmark repositories =="
mkdir -p "$HERE/benchmark-tasks"
[[ -d "$HERE/benchmark-tasks/classical-domains" ]] || \
    git clone --depth 1 https://github.com/AI-Planning/classical-domains \
        "$HERE/benchmark-tasks/classical-domains"
[[ -d "$HERE/benchmark-tasks/numeric-domains" ]] || \
    git clone --depth 1 https://github.com/pyPMT/numeric-domains \
        "$HERE/benchmark-tasks/numeric-domains"

echo "== experiment =="
# benchmarks/data carries both resource datasets: classical-domains-ru-info
# for the ru dimension and functions-domains-info for the numeric fn one.
$BPBENCH init --exp-dir "$HERE/experiment" \
    --time-limit "$TIME_LIMIT" --memory-limit "$MEMORY_LIMIT" \
    --resources-dir "$HERE/data"

# stamp the requested tracks / selection / k values / cap / image into exp-details.json
python3 - "$HERE/experiment/exp-details.json" "$TRACKS" "$MAX_INSTANCES" "$K_PLANS" "$QUALITY_BOUND" "$PARTITION" "$INSTANCE_SELECTION" "$APPTAINER_IMAGE" <<'PYEOF'
import json, sys
path, tracks, cap, ks, quality_bound, partition, instance_selection, image = sys.argv[1:9]
with open(path) as handle:
    details = json.load(handle)
details["tasks"]["tracks"] = tracks.split()
details["tasks"]["max-instances-per-domain"] = int(cap)
details["tasks"]["k-plans"] = [int(k) for k in ks.split()]
details["tasks"]["quality-bound"] = float(quality_bound)
details["tasks"]["instance-selection"] = (
    None if instance_selection in ("", "none") else instance_selection)
if partition:
    details["cfgs"]["slurm"]["partition"] = partition
details["cfgs"]["apptainer-image"] = image or None
with open(path, "w") as handle:
    json.dump(details, handle, indent=4)
PYEOF

echo "== generating the sweep =="
if [[ -n "$APPTAINER_IMAGE" ]]; then
    $BPBENCH generate --exp-dir "$HERE/experiment" --sandbox-dir "$HERE/sandbox" \
        --tasks-dir "classical-domains=$HERE/benchmark-tasks/classical-domains" \
        --tasks-dir "numeric-domains=$HERE/benchmark-tasks/numeric-domains" \
        --apptainer-image "$APPTAINER_IMAGE"
else
    $BPBENCH generate --exp-dir "$HERE/experiment" --sandbox-dir "$HERE/sandbox" \
        --tasks-dir "classical-domains=$HERE/benchmark-tasks/classical-domains" \
        --tasks-dir "numeric-domains=$HERE/benchmark-tasks/numeric-domains" \
        --venv-dir "$HERE/venv"
fi

echo
echo "Done. Start the sweep with:"
echo "  bash $HERE/sandbox/slurm/submit_all.sh        # slurm"
echo "  bash $HERE/sandbox/run_local.sh 8             # or locally, 8 at a time"
echo "and collect the results with:"
echo "  $BPBENCH analyze --sandbox-dir $HERE/sandbox --per-domain"
