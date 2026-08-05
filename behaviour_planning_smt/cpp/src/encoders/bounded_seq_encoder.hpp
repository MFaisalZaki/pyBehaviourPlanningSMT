#pragma once

#include "../problem/problem.hpp"
#include "../problem/plan.hpp"
#include "z3_variable_factory.hpp"
#include "grounded_encoding_visitor.hpp"
#include <z3++.h>

#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace bp {

/**
 * @brief Bounded sequential SMT encoding with a first-goal-state horizon variable.
 *
 * This is the C++ port of the behaviour-planning `seq` encoding built on top of
 * pypmt's EncoderSequential in the original Python implementation. Given a
 * grounded problem and a formula length N it encodes:
 *
 *  - the initial state at layer 0;
 *  - transitions for steps t in [0, N): action preconditions/effects and
 *    explanatory frame axioms between layers t and t+1;
 *  - at most one action per step, no action at layer N, and no empty step in
 *    the middle of a plan;
 *  - an integer `horizon` variable bound to the first state layer at which the
 *    goal holds (or pinned to N in horizon-planning mode), with no actions
 *    allowed at or after a goal layer.
 *
 * State layers range over [0, N] so, matching the Python code where
 * len(encoder) == formula_length + 1, size() returns N + 1.
 *
 * For oversubscription tasks the goal conjuncts come from the oversubscription
 * metric instead of the (empty) goal list, a state counts as final when any
 * weighted goal holds, and the horizon offset shifts by one, mirroring the
 * original encoding.
 */
class BoundedSeqEncoder {
public:
    /// One weighted goal of an oversubscription metric.
    struct WeightedGoal {
        Expression goal;
        Real weight;
    };

    /**
     * @param seed_mode when true, only the plain bounded transition system is
     *        encoded (initial state, transitions, sequential semantics): the
     *        horizon binding and the goal-freeze constraints are skipped. Used
     *        by the oversubscription seed, which optimizes utility over the
     *        raw transition system before the diverse space is built.
     */
    BoundedSeqEncoder(const Problem& problem, z3::context& ctx, int formula_length,
                      bool horizon_planning,
                      std::vector<WeightedGoal> oversubscription_goals = {},
                      bool seed_mode = false);

    // Encoded formula
    const std::vector<z3::expr>& assertions() const { return assertions_; }

    // Mirrors len(encoder) in the Python implementation: the number of state
    // layers, i.e. formula_length + 1.
    int size() const { return formula_length_ + 1; }
    int formula_length() const { return formula_length_; }
    bool is_oversubscription() const { return !oversubscription_goals_.empty(); }
    bool horizon_planning() const { return horizon_planning_; }

    z3::context& ctx() const { return ctx_; }
    const Problem& problem() const { return problem_; }

    // The horizon expression: an Int constant named "horizon", or the value N
    // when horizon-planning mode is active.
    const z3::expr& horizon_expr() const { return *horizon_expr_; }

    // Action variables of one step, ordered as problem.actions().
    std::vector<z3::expr> action_vars_at(int t) const;
    // Action variables at every layer [0, N] for actions whose grounded name
    // contains `substring` (used by the resource-usage dimension).
    std::vector<z3::expr> action_vars_matching(const std::string& substring) const;
    // Grounded name of an action: name and parameters joined by '_'.
    std::string grounded_action_name(const Action& action) const;

    // Goal conjunct i evaluated at states 1..N (used by the goal-ordering
    // dimension). Names are human-readable labels per conjunct.
    const std::vector<std::vector<z3::expr>>& goal_predicate_vars() const { return goal_predicate_vars_; }
    const std::vector<std::string>& goal_predicate_names() const { return goal_predicate_names_; }

    // Weighted oversubscription goals evaluated at the last state layer N
    // (used by the utility-value dimension).
    struct UtilityGoal {
        std::string name;
        z3::expr at_last_state;
        Real weight;
    };
    const std::vector<UtilityGoal>& utility_goals() const { return utility_goals_; }

    // The variable of a grounded fluent at the last state layer N, looked up by
    // its grounded name (name and parameters joined by '_'); nullopt when no
    // such grounded fluent exists (used by the functions dimension).
    std::optional<z3::expr> fluent_var_at_last_state(const std::string& grounded_name) const;

    /// A plan extracted from a model together with its selected action literals.
    struct ExtractedPlan {
        Plan plan;
        std::vector<z3::expr> action_literals;
        int horizon = 0;
    };

    // Extract the plan encoded by `model`, scanning steps [0, horizon].
    ExtractedPlan extract_plan(const z3::model& model) const;

    // Convert an expression at a state layer via the grounded visitor.
    std::optional<z3::expr> convert(const Expression& expr, int timestep) const;

private:
    const Problem& problem_;
    z3::context& ctx_;
    int formula_length_;
    bool horizon_planning_;
    std::vector<WeightedGoal> oversubscription_goals_;
    bool seed_mode_;

    mutable Z3VariableFactory variable_factory_;
    mutable GroundedEncodingVisitor grounded_visitor_;

    std::vector<z3::expr> assertions_;
    std::optional<z3::expr> horizon_expr_;

    // goal_conjuncts_[s-1] holds the goal conjuncts at state layer s in [1, N];
    // empty when the task has no goal conjuncts at all.
    std::vector<std::vector<z3::expr>> goal_conjuncts_;
    std::vector<std::vector<z3::expr>> goal_predicate_vars_;
    std::vector<std::string> goal_predicate_names_;
    std::vector<UtilityGoal> utility_goals_;

    // Map from grounded fluent name to its expression, for the functions dimension.
    std::unordered_map<std::string, const Expression*> grounded_fluent_by_name_;

    // Frame index: grounded fluent -> (action, effect) pairs that can change it.
    std::unordered_map<Expression, std::vector<std::pair<const Action*, const EffectExpression*>>> epc_index_;

    void build_epc_index();
    void build();
    std::optional<z3::expr> convert_effect(const EffectExpression& effect, int timestep) const;
    std::string grounded_fluent_name(const Expression& fluent_expr) const;
};

} // namespace bp
