#pragma once

#include "encoder.hpp"
#include "grounded_encoding_visitor.hpp"
#include "z3_variable_factory.hpp"

#include <optional>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace bp {

/**
 * @brief The "seq" encoder plugin: a bounded sequential SMT encoding with a
 * first-goal-state horizon variable.
 *
 * This is the C++ port of the behaviour-planning `seq` encoding built on top
 * of pypmt's EncoderSequential in the original Python implementation. Given a
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
 *
 * In seed mode only the plain bounded transition system is encoded (initial
 * state, transitions, sequential semantics): the horizon binding and the
 * goal-freeze constraints are skipped. The oversubscription seed optimizes
 * utility over that raw transition system before the diverse space is built.
 */
class SeqEncoder : public Encoder {
public:
    explicit SeqEncoder(const EncoderContext& context);

    const std::string& name() const override { return name_; }

    const Problem& problem() const override { return problem_; }
    z3::context& ctx() const override { return ctx_; }
    const std::vector<z3::expr>& assertions() const override { return assertions_; }

    int formula_length() const override { return formula_length_; }
    // Mirrors len(encoder) in the Python implementation: the number of state
    // layers, i.e. formula_length + 1.
    int size() const override { return formula_length_ + 1; }
    bool is_oversubscription() const override { return !oversubscription_goals_.empty(); }
    bool horizon_planning() const { return horizon_planning_; }

    // The horizon expression: an Int constant named "horizon", or the value N
    // when horizon-planning mode (or seed mode) is active.
    const z3::expr& horizon_expr() const override { return *horizon_expr_; }

    std::vector<z3::expr> action_vars_at(int t) const override;
    std::vector<z3::expr> action_vars_matching(const std::string& substring) const override;
    std::string grounded_action_name(const Action& action) const override;

    const std::vector<std::vector<z3::expr>>& goal_predicate_vars() const override { return goal_predicate_vars_; }
    const std::vector<std::string>& goal_predicate_names() const override { return goal_predicate_names_; }

    const std::vector<UtilityGoal>& utility_goals() const override { return utility_goals_; }

    std::optional<z3::expr> fluent_var_at_last_state(const std::string& grounded_name) const override;

    // Extract the plan encoded by `model`, scanning steps [0, horizon].
    ExtractedPlan extract_plan(const z3::model& model) const override;

    // Convert an expression at a state layer via the grounded visitor.
    std::optional<z3::expr> convert(const Expression& expr, int timestep) const;

private:
    std::string name_ = "seq";
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
