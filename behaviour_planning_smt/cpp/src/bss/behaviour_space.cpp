#include "behaviour_space.hpp"
#include "../util/logger.hpp"
#include "../util/scoped_timer.hpp"
#include "../util/stats.hpp"

#include <stdexcept>

namespace bp {

BehaviourSpace::BehaviourSpace(const Problem& problem, z3::context& ctx, const Config& config,
                               int optimal_plan_length,
                               std::vector<BoundedSeqEncoder::WeightedGoal> oversubscription_goals)
    : problem_(problem), ctx_(ctx), optimal_plan_length_(optimal_plan_length) {
    const int formula_length =
        static_cast<int>(optimal_plan_length * config.planner.quality_bound);

    encoder_ = std::make_unique<BoundedSeqEncoder>(problem, ctx, formula_length,
                                                   config.planner.horizon_planning_mode,
                                                   std::move(oversubscription_goals));

    // Build the requested dimensions, in the order given on the command line.
    for (const auto& spec : config.planner.dimensions) {
        if (spec.name == "go") {
            dimensions_.push_back(std::make_unique<GoalOrderingDimension>(*encoder_));
        } else if (spec.name == "cb") {
            dimensions_.push_back(std::make_unique<CostBoundDimension>(
                *encoder_, config.planner.quality_bound, optimal_plan_length_));
        } else if (spec.name == "ru") {
            dimensions_.push_back(std::make_unique<ResourceCountDimension>(
                *encoder_, parse_range_file(spec.arg, "resource")));
        } else if (spec.name == "uv") {
            dimensions_.push_back(std::make_unique<UtilityValueDimension>(*encoder_));
        } else if (spec.name == "fn") {
            dimensions_.push_back(std::make_unique<FunctionsDimension>(
                *encoder_, parse_range_file(spec.arg, "function")));
        } else {
            throw std::invalid_argument("Unknown dimension: " + spec.name);
        }
    }

    // Assemble the solver: planning formula plus dimension constraints.
    solver_ = std::make_unique<z3::solver>(ctx_);
    for (const auto& assertion : encoder_->assertions()) {
        solver_->add(assertion);
    }
    size_t dimension_constraints = 0;
    for (const auto& dimension : dimensions_) {
        for (const auto& constraint : dimension->formula()) {
            solver_->add(constraint);
        }
        dimension_constraints += dimension->formula().size();
    }

    z3::params solver_params(ctx_);
    solver_params.set("timeout", static_cast<unsigned>(config.planner.solver_timeout_ms));
    solver_params.set("max_memory", static_cast<unsigned>(config.planner.solver_memory_mb));
    solver_->set(solver_params);

    Logger::instance().component(VerbosityLevel::INFO, "BehaviourSpace", {
        {"formula_length", std::to_string(formula_length)},
        {"dimensions", std::to_string(dimensions_.size())},
        {"dimension_constraints", std::to_string(dimension_constraints)}
    });
}

std::optional<DiversePlan> BehaviourSpace::check(const std::vector<z3::expr>& assumptions) {
    ScopedTimer timer("behaviour_space.check_time_ms");
    Stats::instance().add("behaviour_space.checks");

    z3::expr_vector assumption_vector(ctx_);
    for (const auto& assumption : assumptions) {
        assumption_vector.push_back(assumption);
    }

    z3::check_result result;
    try {
        result = solver_->check(assumption_vector);
    } catch (const z3::exception& e) {
        Logger::instance().error("Solver error while checking the behaviour space: " +
                                 std::string(e.msg()));
        return std::nullopt;
    }
    if (result != z3::sat) {
        return std::nullopt;
    }

    z3::model model = solver_->get_model();
    BoundedSeqEncoder::ExtractedPlan extracted = encoder_->extract_plan(model);
    if (extracted.plan.is_empty()) {
        return std::nullopt;
    }

    DiversePlan diverse;
    diverse.plan = std::move(extracted.plan);
    diverse.action_literals = std::move(extracted.action_literals);
    diverse.horizon = extracted.horizon;

    std::vector<z3::expr> behaviour_parts;
    for (const auto& dimension : dimensions_) {
        Dimension::BehaviourValue value = dimension->evaluate(model);
        if (value.expr) {
            behaviour_parts.push_back(*value.expr);
        }
        diverse.attributes.emplace_back(dimension->name(), value.value);
    }
    if (!behaviour_parts.empty()) {
        z3::expr_vector parts(ctx_);
        for (const auto& part : behaviour_parts) parts.push_back(part);
        diverse.behaviour = z3::mk_and(parts);
        diverse.behaviour_expr_str = diverse.behaviour->to_string();
    }

    return diverse;
}

} // namespace bp
