#pragma once

#include "../config/config.hpp"
#include "../encoders/encoder.hpp"
#include "../problem/plan.hpp"
#include "dimension.hpp"
#include <z3++.h>

#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace bp {

/// A plan found in the behaviour space, with its behaviour along every dimension.
struct DiversePlan {
    Plan plan;
    std::vector<z3::expr> action_literals;      ///< the true action variables of the plan
    std::optional<z3::expr> behaviour;          ///< conjunction of the dimension values
    std::string behaviour_expr_str;             ///< printable form of `behaviour`
    std::vector<std::pair<std::string, std::string>> attributes; ///< dimension name -> value
    int horizon = 0;
    bool is_new_behaviour = true;               ///< found in the behaviour phase (vs. plan phase)
};

/**
 * @brief The behaviour space: bounded planning formula + dimension constraints.
 *
 * Builds the encoder and the dimensions requested in the configuration through
 * their plugin registries, owns the incremental solver, and answers
 * `check(assumptions)` queries with a plan and its behaviour — the C++
 * counterpart of the Python BehaviourSpaceSMT.
 */
class BehaviourSpace {
public:
    BehaviourSpace(const Problem& problem, z3::context& ctx, const Config& config,
                   int optimal_plan_length,
                   std::vector<Encoder::WeightedGoal> oversubscription_goals);

    /// Solve under `assumptions`; returns the found plan with its behaviour, or
    /// nullopt when unsatisfiable (or only the empty plan remains).
    std::optional<DiversePlan> check(const std::vector<z3::expr>& assumptions);

    const Encoder& encoder() const { return *encoder_; }
    int optimal_plan_length() const { return optimal_plan_length_; }
    int formula_length() const { return encoder_->formula_length(); }
    z3::context& ctx() const { return ctx_; }

private:
    const Problem& problem_;
    z3::context& ctx_;
    int optimal_plan_length_;
    std::unique_ptr<Encoder> encoder_;
    std::vector<std::unique_ptr<Dimension>> dimensions_;
    std::unique_ptr<z3::solver> solver_;
};

} // namespace bp
