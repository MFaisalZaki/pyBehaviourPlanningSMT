# bpbench — benchmark harness for pyBehaviourPlanningSMT

Compares the FBI planner's diversity indicators against a naive FBI without
dimensions, ForbidIterative baselines, and a SymK baseline on the
oversubscription track — one job per (planner, task, k) — and turns the
results into a coverage-and-diversity report. The stages, experiment layout
and sandbox structure follow the
[aspbench harness of ASPPlanners](https://github.com/MFaisalZaki/ASPPlanners/tree/main/benchmarks).

The whole thing is one script away:

```bash
cd benchmarks
./setup_benchmark.sh          # asks for the limits, then does everything
```

That creates a virtualenv, installs the planner (and builds its C++ core), the
harness, [BehaviourDiversityCounter](https://github.com/MFaisalZaki/BehaviourDiversityCounter)
and [ForbidIterative](https://github.com/MFaisalZaki/forbiditerative), clones
and builds [SymK](https://github.com/speckdavid/symk), clones the benchmark
repositories, writes an experiment with the limits you gave, and generates
the slurm job arrays. Every prompt also has a flag, so a scripted
run is the same script:

```bash
./setup_benchmark.sh --time-limit 30m --memory-limit 8GB \
    --tracks "classical numeric oversubscription" \
    --instance-selection paper --k-plans "5" --partition compute --yes
```

## What is compared

Seven planner configurations ship by default; every `.json` in
`experiment/planners/` is benchmarked, so delete a file to leave one out or
drop in your own:

| configuration | tracks | what it does |
|---|---|---|
| `FBI-bdc` | all | this repository's planner, behaviour-diversity-count indicator |
| `FBI-bms` | all | the same planner, BehaviourMaxSum indicator |
| `FBI-naive` | all | the same planner with **no dimensions**: every plan shares the trivial behaviour, so the loop degenerates to forbid-plan-and-regenerate — the ablation showing what the behaviour space buys |
| `FI-bdc` | classical | ForbidIterative generates a pool of `pool-factor × k` plans (extended unordered top-quality), then `k` are extracted with the counter's `bdc` indicator |
| `FI-bms` | classical | the same pool, extracted with the counter's `bmaxsum` indicator |
| `SymK-bdc` | oversubscription | SymK generates the pool (see below), then `k` are extracted with the counter's `bdc` indicator |
| `SymK-bms` | oversubscription | the same pool, extracted with the counter's `bmaxsum` indicator |

**One judge for everyone.** Whatever produced the k plans, the returned set is
scored by BehaviourDiversityCounter — the plans are replayed against the task,
their behaviours inferred along the same dimensions the FBI planner used, and
the set's `bdc` (distinct behaviours) and `b_maxsum` (sum of pairwise
behaviour distances) recorded. For the FI configurations the counter also
performs the subset extraction from the pool; for FBI it is purely the judge,
so the numbers are comparable across engines by construction.

The dimensions per track mirror the paper experiments: `go` + `cb` for
classical tasks (plus `ru` where the resources data declares the instance),
`go` + `cb` + `fn` for numeric ones, and `cb` + `uv` for oversubscription —
the oversubscription track is the classical selection with priced goals
(utilities 2, 4, 6, … in goal order) instead of hard goals. ForbidIterative
needs hard goals, so it runs on the classical track only; `FBI-naive` plans
without dimensions but is judged along the same track dimensions as everyone
else.

**The SymK oversubscription baseline.** Mainline SymK dropped native
oversubscription support, so the harness compiles the priced-goals task to
classical planning with the soft-goals-can-be-compiled-away construction
(Keyder & Geffner): a `plan_mode` fluent gates the original actions (cost 1
each), and an `end` action starts a fixed chain in which each priced goal is
either *collected* (it holds; cost 0) or *forgone* (cost `1000 × utility`).
With the forgone-utility scale above any realistic plan length, SymK's
symbolic top-k search (`symk_bd` with the unordered plan selector) enumerates
plans by maximum utility first, then fewest actions — the FBI seed's own
oversubscription objective — and the fixed chain means no pool slot is wasted
on collect/forgo permutations of the same core plan. The bookkeeping actions
are stripped from the returned plans and the k-subset is extracted and judged
against the *original* priced-goals task. The setup script clones and builds
SymK at `benchmarks/symk`; a different location can be given per planner
configuration (`"symk-dir"`) or via `SYMK_HOME`.

## The stages

```
bpbench init      → an experiment directory (limits + planner configurations)
bpbench discover  → what tasks a benchmark repository holds
bpbench generate  → one run command per (planner, task, k), plus slurm arrays
bpbench solve     → run ONE triple under its limits, dump a JSON result   (slurm calls this)
bpbench analyze   → results.csv + a coverage-and-diversity report
```

Everything except `solve` is stdlib-only, so a sweep can be generated on a
laptop and only the compute nodes carry the planners.

Tasks are discovered from `api.py` domain directories
([AI-Planning/classical-domains](https://github.com/AI-Planning/classical-domains),
[pyPMT/numeric-domains](https://github.com/pyPMT/numeric-domains)) and from
plain `domain.pddl + problems` directories (the repository's own
`tutorials/pddls` works as a smoke fixture). A task's track is decided by
reading its domain file: it is numeric when the domain genuinely reasons over
numbers (a numeric comparison, or an effect updating a fluent other than
`total-cost`), so the IPC action-costs idiom — including static cost
functions like `road-length` — stays classical; temporal domains are skipped
with a note. Per-instance `(:resource ...)` declarations are read from a
`paper_experiments/data/classical-domains-ru-info` style directory.

**The paper's instance selection.** The experiment's `instance-selection`
setting (or `--instance-selection` on `discover`/`generate`) restricts the
classical track — and with it the derived oversubscription track — to a
fixed instance list, while the numeric track always runs every discovered
instance. `"paper"` uses the selection of
`paper_experiments/generate-benchmark-slurm-tasks.py`, shipped with the
harness as `bpbench/paper_selection.py` (1076 instances over 53 domains); a
path reads a file with one `"(year, domain, instance)"` key per line;
`null`/`"none"` runs everything. An instance's identity is its 1-based
position in the domain's `api.py` problem list sorted by problem path — the
paper script's numbering, which the ru-info resource files also key by.
Where one `(year, domain)` pair exists in several directories (the opt/sat
tracks of an IPC, strips/full variants), `adl` directories are skipped and
the strips variant is preferred, smallest path first, so the pick is
deterministic. `setup_benchmark.sh` defaults to the paper selection with no
per-domain cap: the classical and oversubscription tracks run exactly the
paper's 1076 instances and the numeric track runs all of
`numeric-domains`.

## Sandbox layout

```
sandbox/
├── tasks.json                  the resolved task list (what "attempted" means)
├── resources/<task-id>.txt     per-task (:resource ...) declarations
├── cmds/<planner>.txt          one bpbench-solve command per line
├── slurm/bpbench-<planner>.sbatch     job array, one index per line
├── slurm/submit_all.sh
├── run_local.sh                the same commands through xargs -P, no scheduler
├── results/<planner>/<task>__k<k>.json
├── errors/                     tracebacks of crashed runs
└── analysis/                   results.csv, summary.txt, summary.json
```

## What a run records

Each result JSON carries the task and planner identity, the limits, the
per-stage times (`prepare`/`plan`/`extract`/`score`/`total`), the returned
plans (PDDL text annotated with their behaviour), the judge's scores
(`bdc`, `bmaxsum`), the engine's own metrics (FBI: seed length, formula
length, indicator, internal distances; FI: pool size and how much of it
parsed), and a status:

| status | meaning |
|---|---|
| `SOLVED` | the full `k` plans came back, replayed and were scored |
| `PARTIAL` | some plans came back but fewer than `k`; they are scored, yet the run counts as unsolved in coverage and the means |
| `NO_PLANS` | the engine finished without a usable plan |
| `TIMEOUT` / `MEMOUT` | the run's own limit fired |
| `ERROR` | it crashed; the traceback is in `errors/` |
| `MISSING` | the run never produced a result at all |

Two disciplines inherited from aspbench: limits are enforced twice (the
runner arms its own alarm and address-space limit; slurm gets them plus
headroom), and `MISSING` is counted against `tasks.json` so coverage is never
computed over a quietly smaller denominator. One of this harness's own: a
plan the judge cannot replay against the task is excluded from every score
and reported in the run's logs, rather than silently inflating a diversity
number.

Every run also gets a private working directory under `sandbox/runs/` (the
prepared task files, the FI pool, the resources file), removed afterwards
unless `--keep-run-dir` is passed.

## Running and collecting

```bash
bash sandbox/slurm/submit_all.sh          # one job array per planner
bash sandbox/run_local.sh 8               # or locally, 8 at a time
bpbench analyze --sandbox-dir sandbox --per-domain
```

`analyze` prints (and writes to `analysis/`) coverage, mean `bdc`, mean
`bmaxsum` and mean runtime per planner and track, a status breakdown, and —
when more than one planner ran — a head-to-head over the runs *every* planner
solved, which is the comparison paper tables should be built from.

`generate --skip-existing` drops the runs that already have a result, so a
partial sweep (or a new planner configuration) resumes without redoing
finished work.

## Smoke test

The repository's own tutorial tasks make a sweep that finishes in minutes:

```bash
bpbench generate --exp-dir experiment --sandbox-dir /tmp/smoke \
    --tasks-dir smoke=../tutorials/pddls --venv-dir venv
bash /tmp/smoke/run_local.sh 2
bpbench analyze --sandbox-dir /tmp/smoke
```
