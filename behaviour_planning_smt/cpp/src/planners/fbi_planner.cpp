#include "fbi_planner.hpp"
#include "../bss/diversity_indicator.hpp"
#include "../encoders/grounded_encoding_visitor.hpp"
#include "../encoders/z3_variable_factory.hpp"
#include "../util/logger.hpp"
#include "../util/stats.hpp"
#include "../util/z3_utils.hpp"

#include <algorithm>
#include <chrono>
#include <unordered_map>

namespace bp {

namespace {

double seconds_since(const std::chrono::high_resolution_clock::time_point& start) {
    return std::chrono::duration<double>(
        std::chrono::high_resolution_clock::now() - start).count();
}

} // namespace

FBIPlanner::FBIPlanner(const Problem& problem, z3::context& ctx,
                       std::vector<Encoder::WeightedGoal> oversubscription_goals)
    : problem_(problem), ctx_(ctx),
      oversubscription_goals_(std::move(oversubscription_goals)) {}

/**
 * Iterative-deepening seed search for regular (non-oversubscription) tasks.
 *
 * Encodes transitions incrementally with at most one action per step and asks,
 * for each horizon h, whether the goal can hold at layer h. Since empty steps
 * are allowed, the formula at horizon h is satisfiable iff a plan with at most
 * h actions exists, so the first satisfiable horizon is the optimal
 * (makespan-minimal) plan length.
 */
std::optional<int> FBIPlanner::seed_iterative_deepening() {
    auto& config = Config::instance();
    auto start_time = std::chrono::high_resolution_clock::now();

    z3::solver solver(ctx_);
    z3::params solver_params(ctx_);
    solver_params.set("timeout", static_cast<unsigned>(config.planner.solver_timeout_ms));
    solver_params.set("max_memory", static_cast<unsigned>(config.planner.solver_memory_mb));
    solver.set(solver_params);

    Z3VariableFactory factory(ctx_);
    GroundedEncodingVisitor visitor(ctx_, &problem_, &factory);

    auto convert = [&](const Expression& expr, int timestep) -> std::optional<z3::expr> {
        visitor.clear();
        visitor.set_timestep(timestep);
        accept_visitor(expr, visitor);
        visitor.clear_timestep();
        return visitor.get_result();
    };

    // Frame index: fluent -> modifying (action, effect) pairs.
    std::unordered_map<Expression, std::vector<std::pair<const Action*, const EffectExpression*>>> epc_index;
    for (const Expression& fluent : problem_.grounded_fluents()) {
        epc_index[fluent];
    }
    for (const auto& action : problem_.actions()) {
        for (const auto& effect : action.effects()) {
            const EffectExpression& eff_expr = effect.effect_expression();
            epc_index[eff_expr.fluent()].emplace_back(&action, &eff_expr);
        }
    }

    auto convert_effect = [&](const EffectExpression& effect, int t) -> std::optional<z3::expr> {
        auto fluent_curr = convert(effect.fluent(), t);
        auto fluent_next = convert(effect.fluent(), t + 1);
        auto value = convert(effect.value(), t);
        if (!fluent_curr || !fluent_next || !value) return std::nullopt;
        z3::expr constraint = ctx_.bool_val(true);
        switch (effect.kind()) {
            case EffectExpression::Kind::ASSIGN:
                constraint = (*fluent_next == *value); break;
            case EffectExpression::Kind::INCREASE:
                constraint = (*fluent_next == *fluent_curr + *value); break;
            case EffectExpression::Kind::DECREASE:
                constraint = (*fluent_next == *fluent_curr - *value); break;
        }
        if (effect.is_conditional()) {
            auto condition = convert(effect.condition(), t);
            if (condition) constraint = z3::implies(*condition, constraint);
        }
        return constraint;
    };

    auto add_transition = [&](int t) {
        std::vector<z3::expr> action_vars;
        for (const Action& action : problem_.actions()) {
            z3::expr action_var = factory.get_action_variable(action, t);
            action_vars.push_back(action_var);
            if (action.effects().empty()) continue;
            if (action.has_precondition()) {
                auto precondition = convert(action.precondition(), t);
                if (precondition) solver.add(z3::implies(action_var, *precondition));
            }
            std::vector<z3::expr> effects;
            for (const Effect& effect : action.effects()) {
                auto z3_effect = convert_effect(effect.effect_expression(), t);
                if (z3_effect) effects.push_back(*z3_effect);
            }
            solver.add(z3::implies(action_var, mk_and_vec(ctx_, effects)));
        }
        for (const auto& [fluent, action_effects] : epc_index) {
            auto fluent_t = convert(fluent, t);
            auto fluent_t1 = convert(fluent, t + 1);
            if (!fluent_t || !fluent_t1) continue;
            std::vector<z3::expr> modifiers;
            for (const auto& [action, effect_expr] : action_effects) {
                z3::expr action_var = factory.get_action_variable(*action, t);
                if (effect_expr->is_conditional()) {
                    auto condition = convert(effect_expr->condition(), t);
                    modifiers.push_back(action_var && *condition);
                } else {
                    modifiers.push_back(action_var);
                }
            }
            solver.add(z3::implies(*fluent_t != *fluent_t1, mk_or_vec(ctx_, modifiers)));
        }
        if (!action_vars.empty()) {
            z3::expr_vector vec(ctx_);
            for (const auto& v : action_vars) vec.push_back(v);
            solver.add(z3::atmost(vec, 1));
        }
    };

    // Initial state at layer 0.
    for (const auto& assignment : problem_.initial_state()) {
        auto fluent = convert(assignment.fluent(), 0);
        auto value = convert(assignment.value(), 0);
        if (fluent && value) solver.add(*fluent == *value);
    }

    const int start_h = std::max(0, config.planner.start_timestep);
    int filled_up_to = 0;

    for (int h = start_h; h <= config.planner.max_steps; ++h) {
        if (seconds_since(start_time) >= config.global.timeout) {
            Logger::instance().info("[Seed] Timeout reached at horizon " + std::to_string(h));
            return std::nullopt;
        }

        for (int t = filled_up_to; t < h; ++t) {
            add_transition(t);
        }
        filled_up_to = std::max(filled_up_to, h);

        std::vector<z3::expr> goal_conjuncts;
        for (const auto& goal : problem_.goals()) {
            auto converted = convert(goal.goal_expression(), h);
            if (converted) goal_conjuncts.push_back(*converted);
        }
        z3::expr goal_literal =
            ctx_.bool_const(("seed_goal_at_" + std::to_string(h)).c_str());
        solver.add(z3::implies(goal_literal, mk_and_vec(ctx_, goal_conjuncts)));

        z3::expr_vector assumptions(ctx_);
        assumptions.push_back(goal_literal);
        z3::check_result result = solver.check(assumptions);

        Logger::instance().timestep_solving(VerbosityLevel::VERBOSE, h, {
            {"result", result == z3::sat ? "SAT" : (result == z3::unsat ? "UNSAT" : "UNKNOWN")}
        });

        if (result == z3::sat) {
            Logger::instance().info("[Seed] Optimal plan length: " + std::to_string(h));
            return h;
        }
        if (result == z3::unknown) {
            Logger::instance().info("[Seed] Solver returned unknown at horizon " +
                                    std::to_string(h) + ", aborting seed search");
            return std::nullopt;
        }
    }

    Logger::instance().info("[Seed] No plan found within " +
                            std::to_string(config.planner.max_steps) + " steps");
    return std::nullopt;
}

/**
 * Oversubscription seed: over a bounded encoding of the plain transition
 * system, maximize the collected utility and then minimize the number of
 * actions, both by incremental strengthening of a plain solver. The length of
 * the resulting plan seeds the behaviour space, mirroring the role the
 * oversubscription seed planner played in the Python implementation.
 */
std::optional<int> FBIPlanner::seed_oversubscription() {
    auto& config = Config::instance();
    const int bound = std::max(1, config.planner.oversubscription_horizon);

    Logger::instance().info("[Seed] Oversubscription seed over " + std::to_string(bound) +
                            " steps (utility max, then plan length min)");

    const auto& encoder_entry = EncoderRegistry::instance().get(config.planner.encoder);
    std::unique_ptr<Encoder> seed_encoder = encoder_entry.factory(EncoderContext{
        problem_, ctx_, bound, /*horizon_planning=*/false,
        oversubscription_goals_, /*seed_mode=*/true});

    z3::solver solver(ctx_);
    z3::params solver_params(ctx_);
    solver_params.set("timeout", static_cast<unsigned>(config.planner.solver_timeout_ms));
    solver_params.set("max_memory", static_cast<unsigned>(config.planner.solver_memory_mb));
    solver.set(solver_params);

    for (const auto& assertion : seed_encoder->assertions()) {
        solver.add(assertion);
    }

    // total utility collected in the final state
    std::vector<z3::expr> utility_terms;
    for (const auto& goal : seed_encoder->utility_goals()) {
        z3::expr weight = goal.weight.denominator() == 1
                              ? ctx_.int_val(static_cast<int64_t>(goal.weight.numerator()))
                              : ctx_.real_val(static_cast<int64_t>(goal.weight.numerator()),
                                              static_cast<int64_t>(goal.weight.denominator()));
        utility_terms.push_back(z3::ite(goal.at_last_state, weight, ctx_.int_val(0)));
    }
    z3::expr_vector utility_vec(ctx_);
    for (const auto& term : utility_terms) utility_vec.push_back(term);
    z3::expr total_utility = ctx_.int_const("seed_utility");
    solver.add(total_utility == z3::sum(utility_vec));

    // number of non-empty steps (front-loaded, so this is the plan length)
    std::vector<z3::expr> step_costs;
    for (int t = 0; t < seed_encoder->size(); ++t) {
        step_costs.push_back(z3::ite(mk_or_vec(ctx_, seed_encoder->action_vars_at(t)),
                                     ctx_.int_val(1), ctx_.int_val(0)));
    }
    z3::expr_vector cost_vec(ctx_);
    for (const auto& term : step_costs) cost_vec.push_back(term);
    z3::expr total_cost = ctx_.int_const("seed_cost");
    solver.add(total_cost == z3::sum(cost_vec));

    // Maximize the utility by incremental strengthening.
    if (solver.check() != z3::sat) {
        Logger::instance().info("[Seed] Oversubscription transition system is unsatisfiable");
        return std::nullopt;
    }
    z3::model model = solver.get_model();
    z3::expr best_utility = model.eval(total_utility, true);
    while (true) {
        solver.push();
        solver.add(total_utility > best_utility);
        z3::check_result improved = solver.check();
        if (improved != z3::sat) {
            solver.pop();
            break;
        }
        model = solver.get_model();
        best_utility = model.eval(total_utility, true);
        solver.pop();
    }
    Logger::instance().info("[Seed] Maximum utility within the bound: " +
                            best_utility.to_string());
    solver.add(total_utility == best_utility);

    // A plan must collect something for the seed to be meaningful.
    if (model.eval(total_utility > 0, true).is_false()) {
        Logger::instance().info("[Seed] No profitable oversubscription plan within the bound");
        return std::nullopt;
    }

    // Minimize the plan length at maximum utility, again incrementally.
    if (solver.check() != z3::sat) return std::nullopt;
    model = solver.get_model();
    z3::expr best_cost = model.eval(total_cost, true);
    while (true) {
        solver.push();
        solver.add(total_cost < best_cost);
        z3::check_result improved = solver.check();
        if (improved != z3::sat) {
            solver.pop();
            break;
        }
        model = solver.get_model();
        best_cost = model.eval(total_cost, true);
        solver.pop();
    }

    int length = best_cost.get_numeral_int();
    Logger::instance().info("[Seed] Oversubscription seed plan length: " + std::to_string(length));
    if (length == 0) return std::nullopt;
    return length;
}

std::optional<int> FBIPlanner::seed_plan_length() {
    auto& config = Config::instance();
    if (config.planner.horizon_length >= 0) {
        Logger::instance().info("[Seed] Using the provided horizon length: " +
                                std::to_string(config.planner.horizon_length));
        return config.planner.horizon_length;
    }
    if (!oversubscription_goals_.empty()) {
        return seed_oversubscription();
    }
    return seed_iterative_deepening();
}

FBIPlanner::Result FBIPlanner::plan() {
    auto& config = Config::instance();
    auto& stats = Stats::instance();
    Result result;

    auto overall_start = std::chrono::high_resolution_clock::now();

    // --- Phase 0: infer the optimal plan length.
    auto seed_start = std::chrono::high_resolution_clock::now();
    std::optional<int> optimal_length = seed_plan_length();
    result.seed_seconds = seconds_since(seed_start);
    if (!optimal_length) {
        return result;
    }
    result.seed_found = true;
    result.optimal_plan_length = *optimal_length;

    const int formula_length =
        static_cast<int>(*optimal_length * config.planner.quality_bound);
    result.formula_length = formula_length;
    if (formula_length <= 0) {
        Logger::instance().info("Formula length is 0; there is no room for any plan.");
        return result;
    }

    // --- Build the behaviour space and hand it to the diversity indicator.
    auto diversify_start = std::chrono::high_resolution_clock::now();
    BehaviourSpace space(problem_, ctx_, config, *optimal_length, oversubscription_goals_);

    const auto& indicator_entry =
        DiversityIndicatorRegistry::instance().get(config.planner.indicator);
    std::unique_ptr<DiversityIndicator> indicator =
        indicator_entry.factory(config.planner.indicator_arg);
    result.indicator = indicator->name();
    Logger::instance().info("Diversifying with indicator: " + indicator->name());

    const size_t requested_plans = static_cast<size_t>(std::max(0, config.planner.num_plans));
    auto out_of_time = [&]() {
        if (seconds_since(overall_start) < config.global.timeout) return false;
        Logger::instance().info("*** TIMEOUT reached while diversifying ***");
        return true;
    };

    DiversityIndicator::Result diversified =
        indicator->generate(space, requested_plans, out_of_time);
    result.plans = std::move(diversified.plans);
    result.new_behaviour_count = diversified.new_behaviour_count;
    result.diversify_seconds = seconds_since(diversify_start);

    // --- Score the plan set: pairwise behaviour distance, summed over the
    // per-dimension distance functions.
    if (result.plans.size() >= 2) {
        double total = 0.0;
        double minimum = -1.0;
        for (size_t i = 0; i < result.plans.size(); ++i) {
            for (size_t j = i + 1; j < result.plans.size(); ++j) {
                double pair_distance = 0.0;
                for (size_t d = 0; d < space.dimensions().size(); ++d) {
                    const auto& dimension = space.dimensions()[d];
                    const std::string& value_i = result.plans[i].attributes[d].second;
                    const std::string& value_j = result.plans[j].attributes[d].second;
                    pair_distance += dimension->distance(value_i, value_j);
                }
                result.pairwise_distances.push_back({i, j, pair_distance});
                total += pair_distance;
                minimum = minimum < 0 ? pair_distance : std::min(minimum, pair_distance);
            }
        }
        result.min_behaviour_distance = minimum;
        result.avg_behaviour_distance = total / result.pairwise_distances.size();
    }

    stats.set("planner.plans_found", static_cast<double>(result.plans.size()));
    stats.set("planner.new_behaviours", static_cast<double>(result.new_behaviour_count));
    stats.set("planner.optimal_plan_length", static_cast<double>(result.optimal_plan_length));
    stats.set("planner.formula_length", static_cast<double>(result.formula_length));
    stats.set("planner.seed_seconds", result.seed_seconds);
    stats.set("planner.diversify_seconds", result.diversify_seconds);

    return result;
}

} // namespace bp
