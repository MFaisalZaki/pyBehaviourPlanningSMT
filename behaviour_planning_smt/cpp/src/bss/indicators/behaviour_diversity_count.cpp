#include "../diversity_indicator.hpp"
#include "../../util/logger.hpp"
#include "../../util/z3_utils.hpp"

#include <unordered_set>

namespace bp {

namespace {

// A stable key for a plan: the names of its selected action literals.
std::string plan_key(const DiversePlan& plan) {
    std::string key;
    for (const auto& literal : plan.action_literals) {
        key += literal.decl().name().str();
        key += '|';
    }
    return key;
}

/**
 * @brief Behaviour diversity count ('bdc').
 *
 * The indicator is the number of distinct behaviours in the plan set, and it
 * is optimised greedily by forbidding and regenerating: each round assumes
 * the negation of every behaviour found so far and asks the behaviour space
 * for a plan, so any solution strictly increases the count. When no new
 * behaviour exists the space is exhausted; the remaining quota is filled with
 * plans that reuse known behaviours but differ from every known plan, which
 * keeps the count at its maximum while still returning `requested_plans`
 * plans when possible.
 *
 * This is the diversification loop of the original Python
 * ForbiddenBehaviorSMTPlanner, packaged as the first indicator plugin.
 */
class BehaviourDiversityCount : public DiversityIndicator {
public:
    const std::string& name() const override { return name_; }

    Result generate(BehaviourSpace& space, size_t requested_plans,
                    const std::function<bool()>& out_of_time) override {
        Result result;
        z3::context& ctx = space.ctx();

        std::vector<z3::expr> behaviours;               // behaviour of every found plan
        std::unordered_set<std::string> behaviour_keys; // duplicate detection
        std::vector<z3::expr> plan_blocks;              // And(action literals) per plan
        std::unordered_set<std::string> plan_keys;

        auto record_plan = [&](DiversePlan&& plan, bool is_new_behaviour) {
            plan.is_new_behaviour = is_new_behaviour;
            plan_keys.insert(plan_key(plan));
            plan_blocks.push_back(mk_and_vec(ctx, plan.action_literals));
            result.plans.push_back(std::move(plan));
        };

        // --- Behaviour phase: maximise the indicator. Every plan found under
        // the assumption "no known behaviour" carries a new behaviour.
        while (result.plans.size() < requested_plans && !out_of_time()) {
            std::vector<z3::expr> assumptions;
            if (!behaviours.empty()) {
                assumptions.push_back(!mk_or_vec(ctx, behaviours));
            }
            std::optional<DiversePlan> found = space.check(assumptions);
            if (!found) break;

            if (plan_keys.count(plan_key(*found))) {
                // The solver returned a plan we already hold: the space cannot
                // make progress (only happens with degenerate dimensions).
                break;
            }

            const bool has_new_behaviour =
                found->behaviour && !behaviour_keys.count(found->behaviour_expr_str);
            if (found->behaviour && has_new_behaviour) {
                behaviours.push_back(*found->behaviour);
                behaviour_keys.insert(found->behaviour_expr_str);
            }

            Logger::instance().info("[bdc] Behaviour phase: plan " +
                                    std::to_string(result.plans.size() + 1) + " with " +
                                    std::to_string(found->plan.length()) + " actions");
            record_plan(std::move(*found), true);
            result.new_behaviour_count++;

            if (!has_new_behaviour) {
                // Degenerate behaviour (empty or repeated): the behaviour
                // space is exhausted, continue with the plan phase.
                break;
            }
        }

        // --- Plan phase: the indicator cannot grow further; fill the quota
        // with plans that reuse known behaviours but differ from known plans.
        while (result.plans.size() < requested_plans && !out_of_time()) {
            std::vector<z3::expr> assumptions;
            if (!behaviours.empty()) {
                assumptions.push_back(mk_or_vec(ctx, behaviours));
            }
            if (!plan_blocks.empty()) {
                assumptions.push_back(!mk_or_vec(ctx, plan_blocks));
            }
            std::optional<DiversePlan> found = space.check(assumptions);
            if (!found) break;
            if (plan_keys.count(plan_key(*found))) break;

            Logger::instance().info("[bdc] Plan phase: plan " +
                                    std::to_string(result.plans.size() + 1) + " with " +
                                    std::to_string(found->plan.length()) + " actions");
            record_plan(std::move(*found), false);
        }

        return result;
    }

private:
    std::string name_ = "bdc";
};

} // namespace

static DiversityIndicatorPlugin _bdc_plugin(
    "bdc",
    [](const std::string&) -> std::unique_ptr<DiversityIndicator> {
        return std::make_unique<BehaviourDiversityCount>();
    },
    "behaviour diversity count: maximises the number of distinct behaviours by "
    "forbidding every behaviour found and generating another one");

} // namespace bp
