#pragma once

#include "../bss/behaviour_space.hpp"
#include "../config/config.hpp"
#include "../problem/problem.hpp"
#include <z3++.h>

#include <optional>
#include <vector>

namespace bp {

/**
 * @brief Forbid-Behaviour-Iterative diverse planner.
 *
 * First infers the optimal (makespan) plan length with a seed search, then
 * builds the behaviour space over a formula of length
 * quality_bound * optimal_length and iterates:
 *
 *  - behaviour phase: repeatedly ask for a plan whose behaviour differs from
 *    every behaviour found so far (assumption: not any known behaviour);
 *  - plan phase: once the behaviour space is exhausted, ask for further plans
 *    that reuse known behaviours but differ from every known plan.
 *
 * This is the C++ port of the Python ForbiddenBehaviorSMTPlanner.
 */
class FBIPlanner {
public:
    struct Result {
        std::vector<DiversePlan> plans;
        bool seed_found = false;
        int optimal_plan_length = 0;
        int formula_length = 0;
        int new_behaviour_count = 0;
        double seed_seconds = 0.0;
        double diversify_seconds = 0.0;
    };

    FBIPlanner(const Problem& problem, z3::context& ctx,
               std::vector<BoundedSeqEncoder::WeightedGoal> oversubscription_goals);

    Result plan();

private:
    const Problem& problem_;
    z3::context& ctx_;
    std::vector<BoundedSeqEncoder::WeightedGoal> oversubscription_goals_;

    // Seed searches for the optimal plan length. Return nullopt when no plan
    // is found within the configured bounds.
    std::optional<int> seed_plan_length();
    std::optional<int> seed_iterative_deepening();
    std::optional<int> seed_oversubscription();
};

} // namespace bp
