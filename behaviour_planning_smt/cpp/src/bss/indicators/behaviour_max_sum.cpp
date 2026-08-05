#include "../diversity_indicator.hpp"
#include "../../util/logger.hpp"
#include "../../util/z3_utils.hpp"

#include <stdexcept>
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

// Behaviour distance between two plans: the sum over the dimensions of the
// per-dimension distance between their values.
double behaviour_distance(const BehaviourSpace& space, const DiversePlan& a,
                          const DiversePlan& b) {
    double total = 0.0;
    const auto& dimensions = space.dimensions();
    for (size_t d = 0; d < dimensions.size(); ++d) {
        total += dimensions[d]->distance(a.attributes[d].second, b.attributes[d].second);
    }
    return total;
}

/**
 * @brief BehaviourMaxSum ('bms').
 *
 * The indicator is the sum of pairwise behaviour distances over the plan set,
 * computed with the dimensions' distance functions. It is optimised as an
 * anytime generate-and-swap loop:
 *
 *  1. generate plans with pairwise-distinct behaviours (assuming the negation
 *     of every behaviour seen) until the set holds `requested_plans` plans;
 *  2. keep generating further new behaviours; each arrival replaces the set
 *     member whose replacement increases the total pairwise distance the
 *     most, and is discarded when no swap improves the sum. Every generated
 *     behaviour stays forbidden, so the loop terminates when the behaviour
 *     space is exhausted (or the round budget or time runs out) with a
 *     monotonically non-decreasing sum;
 *  3. when the space holds fewer behaviours than requested plans — the sum
 *     cannot grow, behaviour-identical plans are distance 0 apart — the
 *     remaining quota is simply filled with plans that reuse known behaviours
 *     but differ from every plan in the set.
 *
 * The optional argument bounds the number of behaviour-generation rounds
 * (default 5 * requested_plans), keeping runs on huge behaviour spaces
 * anytime rather than exhaustive.
 */
class BehaviourMaxSum : public DiversityIndicator {
public:
    explicit BehaviourMaxSum(int max_rounds) : max_rounds_(max_rounds) {}

    const std::string& name() const override { return name_; }

    Result generate(BehaviourSpace& space, size_t requested_plans,
                    const std::function<bool()>& out_of_time) override {
        Result result;
        z3::context& ctx = space.ctx();

        std::vector<z3::expr> behaviours;               // every behaviour generated
        std::unordered_set<std::string> behaviour_keys; // duplicate detection
        std::vector<DiversePlan> selected;              // the current set, |selected| <= k

        const int round_budget =
            max_rounds_ > 0 ? max_rounds_ : 5 * static_cast<int>(requested_plans);
        int rounds = 0;
        bool space_exhausted = false;

        // Pairwise distances of the current set; distances[i][j] == distances[j][i].
        std::vector<std::vector<double>> distances;

        auto add_to_set = [&](DiversePlan&& plan) {
            std::vector<double> to_members;
            for (size_t i = 0; i < selected.size(); ++i) {
                double distance = behaviour_distance(space, selected[i], plan);
                distances[i].push_back(distance);
                to_members.push_back(distance);
            }
            to_members.push_back(0.0);
            distances.push_back(std::move(to_members));
            selected.push_back(std::move(plan));
        };

        auto replace_in_set = [&](size_t member, DiversePlan&& plan,
                                  const std::vector<double>& to_members) {
            for (size_t i = 0; i < selected.size(); ++i) {
                distances[member][i] = i == member ? 0.0 : to_members[i];
                distances[i][member] = distances[member][i];
            }
            selected[member] = std::move(plan);
        };

        // --- Phases 1 and 2: generate new behaviours; grow the set, then swap
        // to increase the sum of pairwise distances.
        while (rounds < round_budget && !out_of_time()) {
            ++rounds;
            std::vector<z3::expr> assumptions;
            if (!behaviours.empty()) {
                assumptions.push_back(!mk_or_vec(ctx, behaviours));
            }
            std::optional<DiversePlan> found = space.check(assumptions);
            if (!found) {
                space_exhausted = true;
                break;
            }

            const bool has_new_behaviour =
                found->behaviour && !behaviour_keys.count(found->behaviour_expr_str);
            if (!has_new_behaviour) {
                // Degenerate dimensions (empty or repeated behaviour): treat
                // the behaviour space as exhausted, but keep the plan when the
                // set still has room.
                if (selected.size() < requested_plans) {
                    found->is_new_behaviour = true;
                    add_to_set(std::move(*found));
                }
                space_exhausted = true;
                break;
            }
            behaviours.push_back(*found->behaviour);
            behaviour_keys.insert(found->behaviour_expr_str);

            if (selected.size() < requested_plans) {
                found->is_new_behaviour = true;
                Logger::instance().info("[bms] Growing: plan " +
                                        std::to_string(selected.size() + 1) + " with " +
                                        std::to_string(found->plan.length()) + " actions");
                add_to_set(std::move(*found));
                continue;
            }
            if (requested_plans < 2) {
                // A single plan has no pairwise sum to improve.
                space_exhausted = false;
                break;
            }

            // Swap step: does replacing some member with the new plan increase
            // the total pairwise distance?
            std::vector<double> to_members;
            to_members.reserve(selected.size());
            for (const auto& member : selected) {
                to_members.push_back(behaviour_distance(space, member, *found));
            }
            double new_plan_total = 0.0;
            for (double distance : to_members) new_plan_total += distance;

            double best_gain = 0.0;
            size_t best_member = selected.size();
            for (size_t r = 0; r < selected.size(); ++r) {
                double member_total = 0.0;
                for (size_t i = 0; i < selected.size(); ++i) member_total += distances[r][i];
                const double gain = (new_plan_total - to_members[r]) - member_total;
                if (gain > best_gain) {
                    best_gain = gain;
                    best_member = r;
                }
            }

            if (best_member < selected.size()) {
                Logger::instance().info(
                    "[bms] Improving: swapped plan " + std::to_string(best_member + 1) +
                    " for a new behaviour (+" + std::to_string(best_gain) + " total distance)");
                found->is_new_behaviour = true;
                replace_in_set(best_member, std::move(*found), to_members);
            }
            // Otherwise the new behaviour is discarded; it stays forbidden, so
            // the loop keeps making progress towards exhaustion.
        }

        if (rounds >= round_budget && !space_exhausted) {
            Logger::instance().info("[bms] Round budget of " + std::to_string(round_budget) +
                                    " behaviour generations reached; further behaviours were "
                                    "not explored");
        }

        result.plans = std::move(selected);
        result.new_behaviour_count = static_cast<int>(result.plans.size());

        // --- Phase 3: more plans requested than the space has behaviours —
        // just return plans, reusing known behaviours.
        std::unordered_set<std::string> plan_keys;
        std::vector<z3::expr> plan_blocks;
        for (const auto& plan : result.plans) {
            plan_keys.insert(plan_key(plan));
            plan_blocks.push_back(mk_and_vec(ctx, plan.action_literals));
        }
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

            Logger::instance().info("[bms] Filling: plan " +
                                    std::to_string(result.plans.size() + 1) + " with " +
                                    std::to_string(found->plan.length()) + " actions");
            found->is_new_behaviour = false;
            plan_keys.insert(plan_key(*found));
            plan_blocks.push_back(mk_and_vec(ctx, found->action_literals));
            result.plans.push_back(std::move(*found));
        }

        return result;
    }

private:
    std::string name_ = "bms";
    int max_rounds_;
};

std::unique_ptr<DiversityIndicator> make_behaviour_max_sum(const std::string& argument) {
    int max_rounds = 0; // 0: default to 5 * requested_plans
    if (!argument.empty()) {
        try {
            max_rounds = std::stoi(argument);
        } catch (const std::exception&) {
            throw std::invalid_argument(
                "The 'bms' indicator expects a numeric round budget, got '" + argument + "'");
        }
        if (max_rounds <= 0) {
            throw std::invalid_argument("The 'bms' round budget must be positive");
        }
    }
    return std::make_unique<BehaviourMaxSum>(max_rounds);
}

} // namespace

static DiversityIndicatorPlugin _bms_plugin(
    "bms",
    make_behaviour_max_sum,
    "BehaviourMaxSum: maximises the sum of pairwise behaviour distances by "
    "generating new behaviours and swapping them into the plan set while the sum "
    "grows; with fewer behaviours than requested plans it just returns plans "
    "(ARG bounds the generation rounds, default 5 * num-plans)");

static DiversityIndicatorPlugin _behaviour_max_sum_alias(
    "BehaviourMaxSum",
    make_behaviour_max_sum,
    "alias of bms");

} // namespace bp
