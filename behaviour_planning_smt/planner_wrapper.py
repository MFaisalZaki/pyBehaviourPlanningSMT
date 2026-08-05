"""Unified-planning interface to the C++ behaviour planning core.

The Python side is a thin frontend, following the architecture of RantanPlan
(https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT): it prepares the task
with unified-planning compilers, ships it to the `bp_planner` C++ executable as
a protobuf message, and converts the returned protobuf results back into
unified-planning plans. All the planning work — seed search, SMT encoding,
behaviour-space dimensions and the forbid-behaviour-iterative loop — happens in
C++.
"""

from typing import IO, Iterator, List, Optional, Tuple

import unified_planning as up
from unified_planning.engines import CompilationKind, Engine, PlanGenerationResultStatus
from unified_planning.engines.compilers import DisjunctiveConditionsRemover, Grounder, QuantifiersRemover
from unified_planning.engines.mixins import AnytimePlannerMixin, OneshotPlannerMixin
from unified_planning.engines.results import LogLevel, LogMessage, PlanGenerationResult
from unified_planning.exceptions import UPException
from unified_planning.grpc.proto_reader import ProtobufReader
from unified_planning.grpc.proto_writer import ProtobufWriter
from unified_planning.model import Problem, ProblemKind
from unified_planning.model.fluent import get_all_fluent_exp
from unified_planning.plans import ActionInstance, SequentialPlan
from unified_planning.shortcuts import Fraction, get_environment
import unified_planning.grpc.generated.unified_planning_pb2 as up_pb2

import os
import subprocess
import sys
import tempfile
import threading


class BehaviourPlanningSMTPlanner(Engine, AnytimePlannerMixin, OneshotPlannerMixin):
    """Diverse planner engine backed by the `bp_planner` C++ executable.

    Options:
        dims: behaviour-space dimensions as ``[name, additional-info]`` pairs,
            using the same format as the original Python implementation:
            ``['go', {}]``, ``['cb', {'quality-bound': 1.0}]``,
            ``['ru', 'resources-file']``, ``['uv', {}]``, ``['fn', 'functions-file']``.
            Dimensions are plugins on the C++ side (`bp_planner
            --list-dimensions`), so names beyond the built-ins pass through:
            a string additional-info becomes the dimension's argument, e.g.
            ``['ac', 'navigate']`` for the example action-count plugin.
        num_plans: how many diverse plans to request (default 1).
        encoder: encoder plugin name (default ``seq``; see
            `bp_planner --list-encoders`).
        horizon_length: skip the seed search and use this optimal plan length.
        horizon_planning_mode: pin the horizon to the formula's last step.
        max_steps: seed-search horizon cap.
        oversubscription_horizon: encoding bound for the oversubscription seed.
        solver_timeout: per-check solver timeout in milliseconds.
        solver_memory: per-check solver memory limit in MB.
        no_action_removal: disable RPG-based action pruning.
        verbosity: silent | info | verbose | debug.
        executable_path: explicit path to the bp_planner executable.
    """

    def __init__(self, **options):
        Engine.__init__(self)
        AnytimePlannerMixin.__init__(self)
        OneshotPlannerMixin.__init__(self)

        self._writer = ProtobufWriter()
        self._reader = ProtobufReader()
        self.executable_path = self._find_executable(options.get("executable_path"))

        self._dims = options.get("dims", [])
        self._num_plans = int(options.get("num_plans", 1))
        self._encoder = options.get("encoder")  # None → C++ default ("seq")
        self._horizon_length = options.get("horizon_length")
        self._horizon_planning_mode = options.get("horizon_planning_mode", False)
        self._max_steps = options.get("max_steps")
        self._oversubscription_horizon = options.get("oversubscription_horizon")
        self._solver_timeout = options.get("solver_timeout")
        self._solver_memory = options.get("solver_memory")
        self._no_action_removal = options.get("no_action_removal", False)
        self._verbosity = options.get("verbosity")
        self._stats_file = options.get("stats_file")

        # Filled by the last run, so callers can inspect the planner's work.
        self.last_overall_result: Optional[PlanGenerationResult] = None
        self.last_metrics: dict = {}

    # ------------------------------------------------------------------
    # Engine identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "BehaviourPlanningSMT"

    @staticmethod
    def supported_kind():
        supported_kind = ProblemKind()
        supported_kind.set_problem_class("ACTION_BASED")
        supported_kind.set_problem_type("GENERAL_NUMERIC_PLANNING")
        supported_kind.set_problem_type("SIMPLE_NUMERIC_PLANNING")
        supported_kind.set_typing("FLAT_TYPING")
        supported_kind.set_typing("HIERARCHICAL_TYPING")
        supported_kind.set_numbers("CONTINUOUS_NUMBERS")
        supported_kind.set_numbers("DISCRETE_NUMBERS")
        supported_kind.set_numbers("BOUNDED_TYPES")
        supported_kind.set_fluents_type("NUMERIC_FLUENTS")
        supported_kind.set_fluents_type("INT_FLUENTS")
        supported_kind.set_fluents_type("REAL_FLUENTS")
        supported_kind.set_fluents_type("OBJECT_FLUENTS")
        supported_kind.set_conditions_kind("NEGATIVE_CONDITIONS")
        supported_kind.set_conditions_kind("DISJUNCTIVE_CONDITIONS")
        supported_kind.set_conditions_kind("EQUALITIES")
        supported_kind.set_conditions_kind("EXISTENTIAL_CONDITIONS")
        supported_kind.set_conditions_kind("UNIVERSAL_CONDITIONS")
        supported_kind.set_effects_kind("CONDITIONAL_EFFECTS")
        supported_kind.set_effects_kind("INCREASE_EFFECTS")
        supported_kind.set_effects_kind("DECREASE_EFFECTS")
        supported_kind.set_effects_kind("FLUENTS_IN_NUMERIC_ASSIGNMENTS")
        supported_kind.set_quality_metrics("OVERSUBSCRIPTION")
        supported_kind.set_quality_metrics("PLAN_LENGTH")
        supported_kind.set_quality_metrics("ACTIONS_COST")
        return supported_kind

    @staticmethod
    def supports(problem_kind):
        return problem_kind <= BehaviourPlanningSMTPlanner.supported_kind()

    # ------------------------------------------------------------------
    # Executable discovery
    # ------------------------------------------------------------------

    def _find_executable(self, provided_path):
        """Find the bp_planner executable, trying various locations."""
        if provided_path:
            return provided_path

        package_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(package_dir, "bin", "bp_planner"),
            os.path.join(package_dir, "cpp", "build", "bp_planner"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path

        raise UPException(
            f"bp_planner executable not found. Tried: {', '.join(candidates)}. "
            "Build it with `python build.py` and/or provide options={'executable_path': ...}."
        )

    # ------------------------------------------------------------------
    # Problem preparation
    # ------------------------------------------------------------------

    def _initialize_fluents(self, task: Problem):
        """Give every uninitialized fluent an explicit initial value (False/0),
        so the C++ side never sees partial initial states."""
        _env = get_environment()
        _tm = _env.type_manager
        _em = _env.expression_manager
        task.initial_defaults.update({_tm.RealType(): _em.Real(Fraction(0))})
        task.initial_defaults.update({_tm.IntType(): _em.Int(0)})
        task.initial_defaults.update({_tm.BoolType(): _em.Bool(False)})

        all_fluent_expressions = []
        for fluent in task.fluents:
            all_fluent_expressions.extend(get_all_fluent_exp(task, fluent))

        initialized_fluents = set(task.explicit_initial_values.keys())
        for fluent_expression in all_fluent_expressions:
            if fluent_expression not in initialized_fluents:
                task.set_initial_value(
                    fluent_expression, task.initial_defaults[fluent_expression.type]
                )

    def _compile_problem(self, problem: Problem):
        """Quantifier removal, disjunctive-conditions removal and grounding,
        keeping the compilation maps to translate plans back."""
        current_problem = problem
        compilation_maps = []

        quantifier_remover = QuantifiersRemover()
        if quantifier_remover.supports(current_problem.kind):
            result = quantifier_remover.compile(
                current_problem, CompilationKind.QUANTIFIERS_REMOVING
            )
            current_problem = result.problem
            compilation_maps.append(result)

        disjunction_remover = DisjunctiveConditionsRemover()
        if disjunction_remover.supports(current_problem.kind):
            result = disjunction_remover.compile(
                current_problem, CompilationKind.DISJUNCTIVE_CONDITIONS_REMOVING
            )
            current_problem = result.problem
            compilation_maps.append(result)

        grounder = Grounder()
        result = grounder.compile(current_problem, CompilationKind.GROUNDING)
        current_problem = result.problem
        compilation_maps.append(result)

        class CombinedCompilationResult:
            def __init__(self, problem, compilation_maps):
                self.problem = problem
                self.compilation_maps = compilation_maps

            def map_back_action_instance(self, action_instance):
                current = action_instance
                for compilation_result in reversed(self.compilation_maps):
                    if current is None:
                        return None
                    map_back = compilation_result.map_back_action_instance
                    if map_back is not None:
                        current = map_back(current)
                return current

        return current_problem, CombinedCompilationResult(current_problem, compilation_maps)

    def _dimension_arguments(self) -> List[str]:
        """Translate the dims option into --dim command line arguments.

        Dimensions are plugins on the C++ side, so any registered name is
        accepted here and validated by the planner itself (see
        `bp_planner --list-dimensions`). The additional information becomes the
        dimension's argument: a plain string is passed as-is, and for the
        original dict formats the known keys (`quality-bound` for cb, `file`
        for ru/fn, or a generic `arg`) are unwrapped.
        """
        arguments: List[str] = []
        for dimension in self._dims:
            name, info = dimension[0], dimension[1] if len(dimension) > 1 else {}
            argument = ""
            if isinstance(info, str):
                argument = info
            elif isinstance(info, dict) and info:
                if name == "cb":
                    argument = str(info.get("quality-bound", 1.0))
                else:
                    value = info.get("file", info.get("arg"))
                    if value is not None:
                        argument = str(value)
            arguments += ["--dim", f"{name}:{argument}" if argument else name]
        return arguments

    # ------------------------------------------------------------------
    # Running the C++ planner
    # ------------------------------------------------------------------

    def _stream_output(self, pipe, output_stream: Optional[IO[str]], prefix=""):
        if not pipe:
            return
        try:
            for line in iter(pipe.readline, b""):
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if not text:
                    continue
                if output_stream is not None:
                    output_stream.write(f"{prefix}{text}\n")
                else:
                    print(f"{prefix}{text}")
                    sys.stdout.flush()
        except Exception:
            pass
        finally:
            if pipe:
                pipe.close()

    def _run_planner(
        self,
        problem: Problem,
        num_plans: int,
        timeout: Optional[float] = None,
        output_stream: Optional[IO[str]] = None,
    ) -> Tuple[PlanGenerationResult, List[PlanGenerationResult]]:
        """Run the C++ planner and return (overall_result, per_plan_results),
        with every plan mapped back to the original problem and annotated with
        its behaviour."""
        self._initialize_fluents(problem)
        compiled_problem, compilation_result = self._compile_problem(problem)
        pb_problem_msg = self._writer.convert(compiled_problem)

        problem_file = tempfile.NamedTemporaryFile(suffix=".pb", delete=False)
        solution_file = tempfile.NamedTemporaryFile(suffix=".pb", delete=False)
        problem_filepath = problem_file.name
        solution_filepath = solution_file.name
        problem_file.close()
        solution_file.close()
        produced_files = [problem_filepath, solution_filepath]

        try:
            with open(problem_filepath, "wb") as f:
                f.write(pb_problem_msg.SerializeToString())

            command = [
                self.executable_path, problem_filepath, solution_filepath,
                "--num-plans", str(num_plans),
            ]
            command += self._dimension_arguments()
            if self._encoder is not None:
                command += ["--encoder", self._encoder]
            if self._horizon_length is not None:
                command += ["--horizon-length", str(self._horizon_length)]
            if self._horizon_planning_mode:
                command += ["--horizon-planning-mode"]
            if self._max_steps is not None:
                command += ["--max-steps", str(self._max_steps)]
            if self._oversubscription_horizon is not None:
                command += ["--oversubscription-horizon", str(self._oversubscription_horizon)]
            if self._solver_timeout is not None:
                command += ["--solver-timeout", str(self._solver_timeout)]
            if self._solver_memory is not None:
                command += ["--solver-memory", str(self._solver_memory)]
            if self._no_action_removal:
                command += ["--no-action-removal"]
            if self._stats_file is not None:
                command += ["--stats-file", self._stats_file]
            if self._verbosity is not None:
                command += ["--verbosity", self._verbosity]
            if timeout is not None:
                command += ["--timeout", str(int(timeout))]

            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=False,
            )
            stdout_thread = threading.Thread(
                target=self._stream_output, args=(process.stdout, output_stream, ""))
            stderr_thread = threading.Thread(
                target=self._stream_output, args=(process.stderr, output_stream, "ERROR: "))
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            try:
                # Leave the C++ side some slack to write its results before the
                # hard kill: it enforces the --timeout budget itself.
                subprocess_timeout = timeout * 1.1 + 30 if timeout is not None else None
                return_code = process.wait(timeout=subprocess_timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                timeout_result = PlanGenerationResult(
                    PlanGenerationResultStatus.TIMEOUT, None, self.name,
                    log_messages=[LogMessage(level=LogLevel.INFO, message="Planner timed out.")],
                )
                return timeout_result, []

            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)

            if return_code != 0:
                error_msg = f"The planner failed with return code {return_code}."
                return PlanGenerationResult(
                    PlanGenerationResultStatus.INTERNAL_ERROR, None, self.name,
                    log_messages=[LogMessage(level=LogLevel.ERROR, message=error_msg)],
                ), []

            overall_result = self._read_result_file(
                solution_filepath, compiled_problem, compilation_result, problem)
            self.last_overall_result = overall_result
            self.last_metrics = dict(overall_result.metrics or {})

            plan_results: List[PlanGenerationResult] = []
            index = 0
            while True:
                plan_filepath = f"{solution_filepath}.{index}"
                if not os.path.exists(plan_filepath):
                    break
                produced_files.append(plan_filepath)
                plan_results.append(self._read_result_file(
                    plan_filepath, compiled_problem, compilation_result, problem))
                index += 1

            return overall_result, plan_results
        finally:
            for filepath in produced_files:
                if os.path.exists(filepath):
                    os.remove(filepath)

    def _read_result_file(
        self, filepath: str, compiled_problem: Problem, compilation_result, original_problem: Problem
    ) -> PlanGenerationResult:
        """Parse one PlanGenerationResult protobuf file, map its plan back to
        the original problem, and attach the behaviour attributes."""
        with open(filepath, "rb") as f:
            pb_result = up_pb2.PlanGenerationResult()  # type: ignore
            pb_result.ParseFromString(f.read())

        result = self._reader.convert(pb_result, compiled_problem)
        metrics = dict(result.metrics or {})

        final_plan = None
        if result.plan is not None:
            new_actions: List[ActionInstance] = []
            plan_actions = getattr(result.plan, "actions", [])
            for action_instance in plan_actions:
                mapped = compilation_result.map_back_action_instance(action_instance)
                assert mapped is not None
                new_actions.append(mapped)
            final_plan = SequentialPlan(new_actions)

            behaviour_attributes = {
                key[len("behaviour."):]: value
                for key, value in metrics.items()
                if key.startswith("behaviour.")
            }
            setattr(final_plan, "behaviour_attr", behaviour_attributes or None)
            setattr(final_plan, "behaviour_str", metrics.get("behaviour", ""))
            setattr(final_plan, "behaviour_expr", metrics.get("behaviour_expr") or None)
            setattr(final_plan, "is_new_behaviour",
                    metrics.get("is_new_behaviour", "true") == "true")
            setattr(final_plan, "task", original_problem)

        return PlanGenerationResult(
            result.status, final_plan, self.name,
            log_messages=result.log_messages, metrics=metrics,
        )

    # ------------------------------------------------------------------
    # unified-planning entry points
    # ------------------------------------------------------------------

    def _solve(
        self,
        problem: Problem,
        heuristic=None,
        timeout: Optional[float] = None,
        output_stream: Optional[IO[str]] = None,
    ) -> PlanGenerationResult:
        overall_result, plan_results = self._run_planner(
            problem, self._num_plans, timeout, output_stream)
        if plan_results:
            first = plan_results[0]
            return PlanGenerationResult(
                overall_result.status, first.plan, self.name,
                log_messages=overall_result.log_messages, metrics=overall_result.metrics,
            )
        return overall_result

    def _get_solutions(
        self,
        problem: Problem,
        timeout: Optional[float] = None,
        output_stream: Optional[IO[str]] = None,
    ) -> Iterator[PlanGenerationResult]:
        overall_result, plan_results = self._run_planner(
            problem, self._num_plans, timeout, output_stream)
        if not plan_results:
            yield overall_result
            return
        for plan_result in plan_results:
            yield plan_result

    def get_diverse_plans(
        self,
        problem: Problem,
        num_plans: Optional[int] = None,
        timeout: Optional[float] = None,
        output_stream: Optional[IO[str]] = None,
    ) -> Tuple[PlanGenerationResult, List[PlanGenerationResult]]:
        """Convenience entry point: run once, return the overall result and one
        result per diverse plan."""
        return self._run_planner(
            problem, num_plans if num_plans is not None else self._num_plans,
            timeout, output_stream)

    def destroy(self):
        pass
