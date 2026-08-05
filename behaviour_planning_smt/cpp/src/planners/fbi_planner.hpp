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
 * quality_bound * optimal_length and hands it to the configured diversity
 * indicator (--indicator, default 'bdc'), which optimises its metric over the
 * space to produce the plan set. Afterwards the per-dimension distance
 * functions score every plan pair.
 *
 * This is the C++ port of the Python ForbiddenBehaviorSMTPlanner, with the
 * diversification strategy extracted into indicator plugins.
 */
class FBIPlanner {
public:
    /// Behaviour distance between two plans of the result set: the sum over
    /// the dimensions of the per-dimension distance between their values.
    struct PairwiseDistance {
        size_t first_plan = 0;
        size_t second_plan = 0;
        double distance = 0.0;
    };

    struct Result {
        std::vector<DiversePlan> plans;
        bool seed_found = false;
        int optimal_plan_length = 0;
        int formula_length = 0;
        int new_behaviour_count = 0;
        double seed_seconds = 0.0;
        double diversify_seconds = 0.0;
        std::string indicator;
        std::vector<PairwiseDistance> pairwise_distances;
        double min_behaviour_distance = -1.0; ///< -1 when fewer than two plans
        double avg_behaviour_distance = -1.0; ///< -1 when fewer than two plans
    };

    FBIPlanner(const Problem& problem, z3::context& ctx,
               std::vector<Encoder::WeightedGoal> oversubscription_goals);

    Result plan();

private:
    const Problem& problem_;
    z3::context& ctx_;
    std::vector<Encoder::WeightedGoal> oversubscription_goals_;

    // Seed searches for the optimal plan length. Return nullopt when no plan
    // is found within the configured bounds.
    std::optional<int> seed_plan_length();
    std::optional<int> seed_iterative_deepening();
    std::optional<int> seed_oversubscription();
};

} // namespace bp
