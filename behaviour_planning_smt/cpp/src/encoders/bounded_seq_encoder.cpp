#include "bounded_seq_encoder.hpp"
#include "../util/logger.hpp"
#include "../util/stats.hpp"

#include <algorithm>
#include <functional>
#include <sstream>

namespace bp {

namespace {

// Turn an expression string like "at-robot(loc1, loc2)" into a symbol-friendly
// label like "at-robot_loc1_loc2".
std::string sanitize_label(const std::string& raw) {
    std::string label;
    label.reserve(raw.size());
    for (char c : raw) {
        if (c == '(' || c == ')' || c == ',' || c == ' ') {
            if (!label.empty() && label.back() != '_') label.push_back('_');
        } else {
            label.push_back(c);
        }
    }
    while (!label.empty() && label.back() == '_') label.pop_back();
    return label;
}

z3::expr mk_or_vec(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    if (exprs.empty()) return ctx.bool_val(false);
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::mk_or(vec);
}

z3::expr mk_and_vec(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    if (exprs.empty()) return ctx.bool_val(true);
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::mk_and(vec);
}

z3::expr exactly_one(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    std::vector<int> coeffs(exprs.size(), 1);
    return z3::pbeq(vec, coeffs.data(), 1);
}

z3::expr at_most_one(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::atmost(vec, 1);
}

} // namespace

BoundedSeqEncoder::BoundedSeqEncoder(const Problem& problem, z3::context& ctx,
                                     int formula_length, bool horizon_planning,
                                     std::vector<WeightedGoal> oversubscription_goals,
                                     bool seed_mode)
    : problem_(problem), ctx_(ctx), formula_length_(formula_length),
      horizon_planning_(horizon_planning),
      oversubscription_goals_(std::move(oversubscription_goals)), seed_mode_(seed_mode),
      variable_factory_(ctx), grounded_visitor_(ctx, &problem, &variable_factory_) {
    build_epc_index();
    for (const Expression& fluent : problem_.grounded_fluents()) {
        grounded_fluent_by_name_[grounded_fluent_name(fluent)] = &fluent;
    }
    build();
}

std::optional<z3::expr> BoundedSeqEncoder::convert(const Expression& expr, int timestep) const {
    grounded_visitor_.clear();
    if (timestep >= 0) {
        grounded_visitor_.set_timestep(timestep);
    } else {
        grounded_visitor_.clear_timestep();
    }
    accept_visitor(expr, grounded_visitor_);
    grounded_visitor_.clear_timestep();
    return grounded_visitor_.get_result();
}

std::optional<z3::expr> BoundedSeqEncoder::convert_effect(const EffectExpression& effect,
                                                          int timestep) const {
    auto fluent_curr = convert(effect.fluent(), timestep);
    auto fluent_next = convert(effect.fluent(), timestep + 1);
    auto value = convert(effect.value(), timestep);
    if (!fluent_curr || !fluent_next || !value) {
        Logger::instance().error("Failed to convert effect to Z3: " + effect.to_string());
        return std::nullopt;
    }

    z3::expr constraint = ctx_.bool_val(true);
    switch (effect.kind()) {
        case EffectExpression::Kind::ASSIGN:
            constraint = (*fluent_next == *value);
            break;
        case EffectExpression::Kind::INCREASE:
            constraint = (*fluent_next == *fluent_curr + *value);
            break;
        case EffectExpression::Kind::DECREASE:
            constraint = (*fluent_next == *fluent_curr - *value);
            break;
    }

    if (effect.is_conditional()) {
        auto condition = convert(effect.condition(), timestep);
        if (condition) {
            constraint = z3::implies(*condition, constraint);
        }
    }
    return constraint;
}

void BoundedSeqEncoder::build_epc_index() {
    epc_index_.clear();
    for (const Expression& fluent : problem_.grounded_fluents()) {
        epc_index_[fluent];
    }
    for (const auto& action : problem_.actions()) {
        for (const auto& effect : action.effects()) {
            const EffectExpression& eff_expr = effect.effect_expression();
            epc_index_[eff_expr.fluent()].emplace_back(&action, &eff_expr);
        }
    }
}

std::vector<z3::expr> BoundedSeqEncoder::action_vars_at(int t) const {
    std::vector<z3::expr> vars;
    vars.reserve(problem_.action_count());
    for (const Action& action : problem_.actions()) {
        vars.push_back(variable_factory_.get_action_variable(action, t));
    }
    return vars;
}

std::string BoundedSeqEncoder::grounded_action_name(const Action& action) const {
    return variable_factory_.get_action_var_name(action);
}

std::vector<z3::expr> BoundedSeqEncoder::action_vars_matching(const std::string& substring) const {
    std::vector<z3::expr> vars;
    for (const Action& action : problem_.actions()) {
        if (grounded_action_name(action).find(substring) == std::string::npos) continue;
        for (int t = 0; t <= formula_length_; ++t) {
            vars.push_back(variable_factory_.get_action_variable(action, t));
        }
    }
    return vars;
}

std::string BoundedSeqEncoder::grounded_fluent_name(const Expression& fluent_expr) const {
    // A grounded fluent expression is a state variable: fluent symbol followed
    // by constant arguments. Reproduce the variable factory's naming scheme
    // (name and parameters joined by '_', no timestep suffix).
    std::string name;
    if (fluent_expr.is_atom()) {
        name = fluent_expr.value().symbol();
    } else if (fluent_expr.is_list() && fluent_expr.list_size() > 0) {
        const Expression& head = fluent_expr.list_element(0);
        if (head.is_atom()) name = head.value().symbol();
        for (size_t i = 1; i < fluent_expr.list_size(); ++i) {
            const Expression& arg = fluent_expr.list_element(i);
            if (arg.is_atom()) name += "_" + arg.value().symbol();
        }
    }
    return name;
}

std::optional<z3::expr> BoundedSeqEncoder::fluent_var_at_last_state(
        const std::string& grounded_name) const {
    auto it = grounded_fluent_by_name_.find(grounded_name);
    if (it == grounded_fluent_by_name_.end()) return std::nullopt;
    return convert(*it->second, formula_length_);
}

void BoundedSeqEncoder::build() {
    auto& stats = Stats::instance();
    const int N = formula_length_;
    assertions_.clear();

    // --- 1. Initial state at layer 0.
    for (const auto& assignment : problem_.initial_state()) {
        auto fluent = convert(assignment.fluent(), 0);
        auto value = convert(assignment.value(), 0);
        if (fluent && value) {
            assertions_.push_back(*fluent == *value);
        }
    }

    // --- 2. Transitions for steps t in [0, N): actions and frame axioms.
    for (int t = 0; t < N; ++t) {
        // Action preconditions and effects: a@t -> pre@t, a@t -> eff(t -> t+1).
        for (const Action& action : problem_.actions()) {
            z3::expr action_var = variable_factory_.get_action_variable(action, t);
            if (action.effects().empty()) continue;

            if (action.has_precondition()) {
                auto precondition = convert(action.precondition(), t);
                if (precondition) {
                    assertions_.push_back(z3::implies(action_var, *precondition));
                }
            }

            std::vector<z3::expr> effects;
            for (const Effect& effect : action.effects()) {
                auto z3_effect = convert_effect(effect.effect_expression(), t);
                if (z3_effect) effects.push_back(*z3_effect);
            }
            assertions_.push_back(z3::implies(action_var, mk_and_vec(ctx_, effects)));
        }

        // Explanatory frame axioms: f@t != f@t+1 -> some modifying action fired.
        for (const auto& [fluent, action_effects] : epc_index_) {
            auto fluent_t = convert(fluent, t);
            auto fluent_t1 = convert(fluent, t + 1);
            if (!fluent_t || !fluent_t1) continue;

            std::vector<z3::expr> modifiers;
            for (const auto& [action, effect_expr] : action_effects) {
                z3::expr action_var = variable_factory_.get_action_variable(*action, t);
                if (effect_expr->is_conditional()) {
                    auto condition = convert(effect_expr->condition(), t);
                    modifiers.push_back(action_var && *condition);
                } else {
                    modifiers.push_back(action_var);
                }
            }
            assertions_.push_back(z3::implies(*fluent_t != *fluent_t1,
                                              mk_or_vec(ctx_, modifiers)));
        }
    }

    // --- 3. Goal conjuncts per state layer s in [1, N]. For oversubscription
    // tasks the conjuncts come from the metric's weighted goals instead.
    goal_conjuncts_.clear();
    goal_predicate_vars_.clear();
    goal_predicate_names_.clear();
    utility_goals_.clear();

    const bool osp = is_oversubscription();
    std::vector<const Expression*> conjunct_sources;
    if (osp) {
        for (const auto& weighted : oversubscription_goals_) {
            conjunct_sources.push_back(&weighted.goal);
        }
    } else {
        // Split conjunctive goals into their top-level conjuncts, mirroring the
        // Python implementation which unwrapped the goal's And structure. Each
        // conjunct becomes one goal predicate for the ordering dimension.
        std::function<void(const Expression*)> flatten = [&](const Expression* expr) {
            if (expr->is_and()) {
                for (size_t i = 1; i < expr->list_size(); ++i) {
                    flatten(&expr->list_element(i));
                }
            } else {
                conjunct_sources.push_back(expr);
            }
        };
        for (const auto& goal : problem_.goals()) {
            flatten(&goal.goal_expression());
        }
    }

    for (int s = 1; s <= N; ++s) {
        std::vector<z3::expr> conjuncts;
        conjuncts.reserve(conjunct_sources.size());
        for (const Expression* source : conjunct_sources) {
            auto converted = convert(*source, s);
            if (converted) conjuncts.push_back(*converted);
        }
        if (!conjuncts.empty()) {
            goal_conjuncts_.push_back(std::move(conjuncts));
        }
    }

    // Per-conjunct views across states, for the goal-ordering dimension.
    if (!goal_conjuncts_.empty()) {
        size_t conjunct_count = goal_conjuncts_.front().size();
        goal_predicate_vars_.assign(conjunct_count, {});
        for (const auto& state_conjuncts : goal_conjuncts_) {
            for (size_t i = 0; i < conjunct_count && i < state_conjuncts.size(); ++i) {
                goal_predicate_vars_[i].push_back(state_conjuncts[i]);
            }
        }
        for (size_t i = 0; i < conjunct_count; ++i) {
            goal_predicate_names_.push_back(sanitize_label(conjunct_sources[i]->to_string()));
        }
    }

    // Weighted goals at the final layer, for the utility-value dimension.
    if (osp && N >= 1) {
        for (const auto& weighted : oversubscription_goals_) {
            auto at_last = convert(weighted.goal, N);
            if (at_last) {
                utility_goals_.push_back(UtilityGoal{
                    sanitize_label(weighted.goal.to_string()), *at_last, weighted.weight});
            }
        }
    }

    // --- 4. The horizon variable: first goal layer, or pinned to N. In seed
    // mode there is no goal semantics, so the horizon is simply the last layer.
    if (horizon_planning_ || seed_mode_) {
        horizon_expr_ = ctx_.int_val(N);
    } else {
        horizon_expr_ = ctx_.int_const("horizon");
        assertions_.push_back(*horizon_expr_ > 0);
        assertions_.push_back(*horizon_expr_ <= N);
    }

    // --- 5. Deny empty steps in the middle of a plan: an action at step t
    // requires exactly one action at step t-1, for t in [1, N-1]. Kept in seed
    // mode as well — front-loading collapses the empty-step permutation
    // symmetry, which the seed's optimization queries depend on.
    if (problem_.action_count() > 0) {
        std::vector<z3::expr> previous_vars = action_vars_at(0);
        for (int t = 1; t <= N - 1; ++t) {
            std::vector<z3::expr> current_vars = action_vars_at(t);
            assertions_.push_back(z3::implies(mk_or_vec(ctx_, current_vars),
                                              exactly_one(ctx_, previous_vars)));
            previous_vars = std::move(current_vars);
        }
    }

    // --- 6. Sequential execution semantics: at most one action per step,
    // for t in [0, N-1], and no action at the final layer N.
    if (problem_.action_count() > 0) {
        for (int t = 0; t <= N - 1; ++t) {
            assertions_.push_back(at_most_one(ctx_, action_vars_at(t)));
        }
        assertions_.push_back(!mk_or_vec(ctx_, action_vars_at(N)));
    }

    // --- 7. Bind the horizon to the first goal layer (unless pinned).
    // A state layer s (stored at index idx = s-1 for classical tasks) is a
    // goal layer when all conjuncts hold; for oversubscription tasks when any
    // weighted goal holds, with the horizon offset shifted by one.
    std::vector<z3::expr> goal_layer_exprs;
    goal_layer_exprs.reserve(goal_conjuncts_.size());
    for (const auto& conjuncts : goal_conjuncts_) {
        if (horizon_planning_) {
            goal_layer_exprs.push_back(mk_and_vec(ctx_, conjuncts));
        } else {
            goal_layer_exprs.push_back(osp ? mk_or_vec(ctx_, conjuncts)
                                           : mk_and_vec(ctx_, conjuncts));
        }
    }

    if (!horizon_planning_ && !seed_mode_) {
        if (!goal_layer_exprs.empty()) {
            assertions_.push_back(mk_or_vec(ctx_, goal_layer_exprs));
        }
        const int offset = osp ? 0 : 1;
        for (size_t idx = 0; idx < goal_layer_exprs.size(); ++idx) {
            z3::expr first_goal_here = goal_layer_exprs[idx];
            if (idx > 0) {
                std::vector<z3::expr> earlier(goal_layer_exprs.begin(),
                                              goal_layer_exprs.begin() + idx);
                first_goal_here = first_goal_here && !mk_or_vec(ctx_, earlier);
            }
            assertions_.push_back(first_goal_here ==
                                  (*horizon_expr_ == ctx_.int_val(static_cast<int>(idx) + offset)));
        }
    }

    // --- 8. Freeze the plan at the goal: a layer is a goal layer iff no
    // action fires at or after it. This also forbids plans that pass through
    // an earlier goal state. Not part of the seed's plain transition system.
    for (size_t idx = 0; !seed_mode_ && idx < goal_layer_exprs.size(); ++idx) {
        std::vector<z3::expr> after_goal_actions;
        for (int t2 = static_cast<int>(idx) + 1; t2 <= N; ++t2) {
            auto vars = action_vars_at(t2);
            after_goal_actions.insert(after_goal_actions.end(), vars.begin(), vars.end());
        }
        assertions_.push_back(goal_layer_exprs[idx] == !mk_or_vec(ctx_, after_goal_actions));
    }

    stats.set("encoder.assertions", static_cast<double>(assertions_.size()));
    stats.set("encoder.formula_length", static_cast<double>(N));
    Logger::instance().component(VerbosityLevel::VERBOSE, "Encoder", {
        {"formula_length", std::to_string(N)},
        {"assertions", std::to_string(assertions_.size())},
        {"goal_conjuncts", std::to_string(goal_predicate_vars_.size())}
    });
}

BoundedSeqEncoder::ExtractedPlan BoundedSeqEncoder::extract_plan(const z3::model& model) const {
    ExtractedPlan extracted;
    z3::expr horizon_value = model.eval(*horizon_expr_, true);
    extracted.horizon = horizon_value.get_numeral_int();

    for (int t = 0; t <= extracted.horizon; ++t) {
        for (const Action& action : problem_.actions()) {
            z3::expr action_var = variable_factory_.get_action_variable(action, t);
            if (model.eval(action_var, true).is_true()) {
                extracted.plan.add_action(&action);
                extracted.action_literals.push_back(action_var);
                break; // at most one action per step
            }
        }
    }
    return extracted;
}

} // namespace bp
