"""This module defines the delete-then-set remover class."""

import unified_planning as up
import unified_planning.engines as engines
from unified_planning.engines.mixins.compiler import CompilationKind, CompilerMixin
from unified_planning.engines.results import CompilerResult
from unified_planning.model.problem_kind_versioning import LATEST_PROBLEM_KIND_VERSION
from unified_planning.engines.compilers.utils import replace_action
from unified_planning.shortcuts import EffectKind, OperatorKind, InstantaneousAction
from unified_planning.model.object import Object
from unified_planning.shortcuts import UserType, Fluent, And, Or, Not
from collections import OrderedDict
from unified_planning.model.parameter import Parameter

from unified_planning.model import (
    Problem,
    ProblemKind,
    Action,
)

from typing import Optional, Dict
from functools import partial

# TODO: check if this can be better integrated via the 
# add_engine: https://github.com/aiplan4eu/unified-planning/blob/master/unified_planning/engines/factory.py
class Renamer(engines.engine.Engine, CompilerMixin):
    """
    This compiler just renames actions and fluents to avoid having - in their names.
    """

    def __init__(self):
        engines.engine.Engine.__init__(self)
        CompilerMixin.__init__(self, CompilationKind.GROUNDING)

    @property
    def name(self):
        return "renamer"

    @staticmethod
    def supported_kind() -> ProblemKind:
        supported_kind = ProblemKind(version=LATEST_PROBLEM_KIND_VERSION)
        supported_kind.set_problem_class("ACTION_BASED")
        supported_kind.set_typing("FLAT_TYPING")
        supported_kind.set_typing("HIERARCHICAL_TYPING")
        supported_kind.set_numbers("BOUNDED_TYPES")
        supported_kind.set_problem_type("SIMPLE_NUMERIC_PLANNING")
        supported_kind.set_problem_type("GENERAL_NUMERIC_PLANNING")
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
        supported_kind.set_effects_kind("STATIC_FLUENTS_IN_BOOLEAN_ASSIGNMENTS")
        supported_kind.set_effects_kind("STATIC_FLUENTS_IN_NUMERIC_ASSIGNMENTS")
        supported_kind.set_effects_kind("STATIC_FLUENTS_IN_OBJECT_ASSIGNMENTS")
        supported_kind.set_effects_kind("FLUENTS_IN_BOOLEAN_ASSIGNMENTS")
        supported_kind.set_effects_kind("FLUENTS_IN_NUMERIC_ASSIGNMENTS")
        supported_kind.set_effects_kind("FLUENTS_IN_OBJECT_ASSIGNMENTS")
        supported_kind.set_effects_kind("FORALL_EFFECTS")
        supported_kind.set_simulated_entities("SIMULATED_EFFECTS")
        supported_kind.set_constraints_kind("STATE_INVARIANTS")
        supported_kind.set_constraints_kind("TRAJECTORY_CONSTRAINTS")
        supported_kind.set_quality_metrics("ACTIONS_COST")
        supported_kind.set_actions_cost_kind("STATIC_FLUENTS_IN_ACTIONS_COST")
        supported_kind.set_actions_cost_kind("FLUENTS_IN_ACTIONS_COST")
        supported_kind.set_quality_metrics("PLAN_LENGTH")
        supported_kind.set_quality_metrics("OVERSUBSCRIPTION")
        supported_kind.set_quality_metrics("MAKESPAN")
        supported_kind.set_quality_metrics("FINAL_VALUE")
        supported_kind.set_actions_cost_kind("INT_NUMBERS_IN_ACTIONS_COST")
        supported_kind.set_actions_cost_kind("REAL_NUMBERS_IN_ACTIONS_COST")
        supported_kind.set_oversubscription_kind("INT_NUMBERS_IN_OVERSUBSCRIPTION")
        supported_kind.set_oversubscription_kind("REAL_NUMBERS_IN_OVERSUBSCRIPTION")
        return supported_kind

    @staticmethod
    def supports(problem_kind):
        return problem_kind <= Renamer.supported_kind()

    @staticmethod
    def supports_compilation(compilation_kind: CompilationKind) -> bool:
        return True #compilation_kind == CompilationKind.DELETE_THEN_SET_REMOVING # we do not support anything in particular, just cleaning up the problem

    @staticmethod
    def resulting_problem_kind(
        problem_kind: ProblemKind,
        compilation_kind: Optional[CompilationKind] = None
    ) -> ProblemKind:
        return problem_kind.clone() # we do not change the problem kind

    def _compile(
        self,
        problem: "up.model.AbstractProblem",
        compilation_kind: "up.engines.CompilationKind",
    ) -> CompilerResult:
        """
        Takes an instance of a :class:`~unified_planning.model.Problem` and the wanted :class:`~unified_planning.engines.CompilationKind`
        and returns a :class:`~unified_planning.engines.results.CompilerResult` where the :meth:`problem<unified_planning.engines.results.CompilerResult.problem>`
        field does not have state innvariants.

        :param problem: The instance of the
        :class:`~unified_planning.model.Problem` that must be returned without
        state innvariants.

        :param compilation_kind: The
        :class:`~unified_planning.engines.CompilationKind` that must be applied
        on the given problem; only
        :class:`~unified_planning.engines.CompilationKind.STATE_INVARIANTS_REMOVING`
        is supported by this compiler
        
        :return: The resulting :class:`~unified_planning.engines.results.CompilerResult` data structure.
        """
        assert isinstance(problem, Problem)
        self.env = problem.environment
        self.env.error_used_name = False

        self._em = self.env.expression_manager
        self._tm = self.env.type_manager

        _initial_defaults = {
            self._tm.BoolType(): self._em.FALSE(),
            self._tm.IntType(): self._em.Int(0),
        }

        new_problem = Problem(f"{self.name}_{problem.name}", environment=self.env, initial_defaults=_initial_defaults)

        # Mapping from old to new.
        self._types_map:   Dict[up.model.Type, up.model.Type]     = {_type: UserType(_type.name.replace('-', '_'), _type.father) for _type in problem.user_types}
        self._fluents_map: Dict[up.model.Fluent, up.model.Fluent] = {}
        self._objects_map: Dict[up.model.Object, up.model.Object] = {param.name: new_problem.add_object(param.name.replace('-','_'), self._types_map[param.type]) for param in problem.all_objects}
        self.new_to_old: Dict[Action, Optional[Action]] = {}

        self.__rename_fluents__(problem, new_problem)
        self.__rename_actions__(problem, new_problem)
        self.__rename_initial_values__(problem, new_problem)
        self.__rename_goals__(problem, new_problem)
        pass
        return CompilerResult(
            new_problem, partial(replace_action, map=self.new_to_old), self.name
        )
    
    def __rename_goals__(self, problem: Problem, new_problem: Problem) -> None:
        assert len(problem.goals) <= 1, "Renamer currently only supports problems with at most one goal."
        for goal in problem.goals:
            if goal.node_type == OperatorKind.AND:
                renamed_goal = [self.__rename_predicate__(f) for f in goal.args]
                new_problem.add_goal(And(renamed_goal))
            elif goal.node_type == OperatorKind.OR:
                renamed_goal = [self.__rename_predicate__(f) for f in goal.args]
                new_problem.add_goal(Or(renamed_goal))
            elif goal.node_type in [OperatorKind.FLUENT_EXP, OperatorKind.NOT]:
                new_problem.add_goal(self.__rename_predicate__(goal))
            else:
                raise NotImplementedError("Renamer currently only supports goals that are conjunctions, disjunctions, or single fluents.")
            
    def __rename_initial_values__(self, problem: Problem, new_problem: Problem) -> None:
        for fluent, value in problem.initial_values.items():
            # update the object map before using it.
            new_problem.set_initial_value(self.__rename_predicate__(fluent), value)

    def __rename_predicate__(self, fluent):
        _renamed_fluent = self.__rename_fluent__(fluent.args[0]._content.payload) if fluent.is_not() else self.__rename_fluent__(fluent._content.payload)
        _renamed_args   = [self._objects_map[str(a)] for a in fluent.args[0].args] if fluent.is_not() else [self._objects_map[str(a)] for a in fluent.args]
        return Not(_renamed_fluent(*_renamed_args)) if fluent.is_not() else _renamed_fluent(*_renamed_args)

    def __rename_fluents__(self, problem: Problem, new_problem: Problem) -> None:
        env = problem.environment
        for fluent in problem.fluents:
            new_fluent = self.__rename_fluent__(fluent)
            new_problem.add_fluent(new_fluent)
            self._fluents_map[fluent] = new_fluent
    
    def __rename_fluent__(self, fluent: up.model.Fluent) -> up.model.Fluent:
        renamed_signature = OrderedDict([(arg.name.replace('-','_'), self._types_map[arg.type]) for arg in fluent.signature])
        return Fluent(fluent.name.replace('-', '_'), fluent.type, renamed_signature, environment=fluent.environment)

    def __rename_expression__(self, expr):
        if expr.node_type == OperatorKind.PARAM_EXP:
            _em = expr.environment.expression_manager
            return _em.ParameterExp(Parameter(expr._content.payload.name.replace('-','_'), self._types_map[expr._content.payload.type]))
        elif expr.node_type == OperatorKind.NOT:
            _em = expr.environment.expression_manager
            return _em.Not(self.__rename_expression__(expr.args[0]))
        elif expr.node_type == OperatorKind.AND:
            _em = expr.environment.expression_manager
            return _em.And([self.__rename_expression__(arg) for arg in expr.args])
        elif expr.node_type == OperatorKind.OR:
            _em = expr.environment.expression_manager
            return _em.Or([self.__rename_expression__(arg) for arg in expr.args])
        elif expr.node_type == OperatorKind.BOOL_CONSTANT:
            return expr
        elif expr.node_type == OperatorKind.IMPLIES:
            _em = expr.environment.expression_manager
            return _em.Implies(self.__rename_expression__(expr.args[0]), self.__rename_expression__(expr.args[1]))
        elif expr.node_type == OperatorKind.EQUALS:
            _em = expr.environment.expression_manager
            return _em.Equals(self.__rename_expression__(expr.args[0]), self.__rename_expression__(expr.args[1]))
        elif expr.node_type == OperatorKind.OBJECT_EXP:
            return self._objects_map[expr._content.payload.name]
        elif expr.node_type == OperatorKind.LE:
            _em = expr.environment.expression_manager
            return _em.LE(self.__rename_expression__(expr.args[0]), self.__rename_expression__(expr.args[1]))
        elif expr.node_type == OperatorKind.LT:
            _em = expr.environment.expression_manager
            return _em.LT(self.__rename_expression__(expr.args[0]), self.__rename_expression__(expr.args[1]))
        elif expr.node_type == OperatorKind.IFF:
            _em = expr.environment.expression_manager
            return _em.Iff(self.__rename_expression__(expr.args[0]), self.__rename_expression__(expr.args[1]))
        elif expr.node_type == OperatorKind.PLUS:
            _em = expr.environment.expression_manager
            return _em.Plus(self.__rename_expression__(expr.args[0]), self.__rename_expression__(expr.args[1]))
        elif expr.node_type == OperatorKind.MINUS:
            _em = expr.environment.expression_manager
            return _em.Minus(self.__rename_expression__(expr.args[0]), self.__rename_expression__(expr.args[1]))
        elif expr.node_type == OperatorKind.TIMES:
            _em = expr.environment.expression_manager
            return _em.Times(self.__rename_expression__(expr.args[0]), self.__rename_expression__(expr.args[1]))
        elif expr.node_type == OperatorKind.DIV:
            _em = expr.environment.expression_manager
            return _em.Div(self.__rename_expression__(expr.args[0]), self.__rename_expression__(expr.args[1]))
        elif expr.node_type == OperatorKind.DOT:
            _em = expr.environment.expression_manager
            return _em.Dot(self.__rename_expression__(expr.args[0]), expr.args[1])
        elif expr.node_type in [OperatorKind.INT_CONSTANT, OperatorKind.REAL_CONSTANT]:
            return expr
        else:
            _renamed_fluent = self._fluents_map[expr._content.payload]
            _em = expr.environment.expression_manager
            _renamed_args = tuple(_em.ParameterExp(Parameter(a._content.payload.name.replace('-','_'), self._types_map[a._content.payload.type])) for a in expr.args)
            return _em.FluentExp(_renamed_fluent, _renamed_args)

    def __rename_actions__(self, problem: Problem, new_problem: Problem) -> None:
        env = problem.environment
        _em = env.expression_manager
        for action in problem.actions:
            # update the object map:
            # renamed_parameters = OrderedDict([Parameter(a.name.replace('-','_'), self._types_map[a.type]) for a in action.parameters])
            renamed_parameters = OrderedDict([(a.name.replace('-','_'), self._types_map[a.type]) for a in action.parameters])
            renamed_action = InstantaneousAction(_name=action.name.replace('-', '_'), **renamed_parameters, _env=env)
            # now let's rename the preconditions.
            assert (len(action.preconditions) <= 1), "Renamer currently only supports actions with at most one precondition."
            for cond in action.preconditions:
                if cond.node_type in [OperatorKind.FLUENT_EXP, OperatorKind.NOT, OperatorKind.EQUALS, OperatorKind.LE, OperatorKind.LT]:
                    renamed_action.add_precondition(self.__rename_expression__(cond))
                elif cond.node_type == OperatorKind.AND:
                    renamed_action.add_precondition(_em.And([self.__rename_expression__(a) for a in cond.args]))
                elif cond.node_type == OperatorKind.OR:
                    renamed_action.add_precondition(_em.Or([self.__rename_expression__(a) for a in cond.args]))
                else:
                    raise NotImplementedError("Renamer currently only supports action preconditions that are single fluents.")
                    # for arg in cond.args:
                    #     renamed_action.add_precondition(self.__rename_expression__(arg))
            
            # now let's deal with unconditional effects only.
            for eff in action.unconditional_effects:
                renamed_action.add_effect(self.__rename_expression__(eff.fluent), eff.value, eff.condition, eff.forall)
            
            for eff in action.conditional_effects:
                renamed_action.add_effect(self.__rename_expression__(eff.fluent), eff.value, self.__rename_expression__(eff.condition), eff.forall)

            new_problem.add_action(renamed_action)
            self.new_to_old[renamed_action] = action