#pragma once

#include "../plugins/plugin.hpp"
#include "../problem/plan.hpp"
#include "../problem/problem.hpp"
#include <z3++.h>

#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace bp {

/**
 * @brief Abstract bounded encoder: the contract dimensions program against.
 *
 * An encoder turns the grounded problem into a bounded SMT formula whose
 * models are plans, and exposes the handles dimensions need to attach their
 * own constraints: the per-step action variables, the goal conjuncts per
 * state layer, the horizon expression, and the final-state fluent variables.
 *
 * Encoders are plugins (see plugins/plugin.hpp): each implementation
 * registers itself under a name ("seq", ...) and is selected with --encoder.
 * Dimensions are told which encoder is active via name() — it is the
 * dimension's responsibility to know the encoders it supports and to place
 * its encodings accordingly (see Dimension::require_encoder).
 *
 * Not every encoder can meaningfully provide every handle; an encoder that
 * has no notion of, say, per-conjunct goal layers returns empty collections,
 * and dimensions that need them must reject that encoder.
 */
class Encoder {
public:
    /// One weighted goal of an oversubscription metric.
    struct WeightedGoal {
        Expression goal;
        Real weight;
    };

    /// A weighted goal evaluated at the last state layer.
    struct UtilityGoal {
        std::string name;
        z3::expr at_last_state;
        Real weight;
    };

    /// A plan extracted from a model together with its selected action literals.
    struct ExtractedPlan {
        Plan plan;
        std::vector<z3::expr> action_literals;
        int horizon = 0;
    };

    virtual ~Encoder() = default;

    /// The plugin name of this encoder ("seq", ...): what dimensions branch on.
    virtual const std::string& name() const = 0;

    virtual const Problem& problem() const = 0;
    virtual z3::context& ctx() const = 0;

    /// The encoded planning formula.
    virtual const std::vector<z3::expr>& assertions() const = 0;

    /// Number of transition steps encoded (N).
    virtual int formula_length() const = 0;
    /// Number of state layers: formula_length() + 1 for bounded state encodings.
    virtual int size() const = 0;
    virtual bool is_oversubscription() const = 0;

    /// The horizon expression: where the found plan ends.
    virtual const z3::expr& horizon_expr() const = 0;

    /// Action variables of one step, ordered as problem().actions().
    virtual std::vector<z3::expr> action_vars_at(int t) const = 0;
    /// Action variables at every layer for actions whose grounded name
    /// contains `substring`.
    virtual std::vector<z3::expr> action_vars_matching(const std::string& substring) const = 0;
    /// Grounded name of an action: name and parameters joined by '_'.
    virtual std::string grounded_action_name(const Action& action) const = 0;

    /// Goal conjunct i evaluated at states 1..N, with printable labels.
    virtual const std::vector<std::vector<z3::expr>>& goal_predicate_vars() const = 0;
    virtual const std::vector<std::string>& goal_predicate_names() const = 0;

    /// Weighted oversubscription goals evaluated at the last state layer.
    virtual const std::vector<UtilityGoal>& utility_goals() const = 0;

    /// The variable of a grounded fluent at the last state layer, looked up by
    /// its grounded name; nullopt when no such grounded fluent exists.
    virtual std::optional<z3::expr> fluent_var_at_last_state(const std::string& grounded_name) const = 0;

    /// Extract the plan encoded by `model`.
    virtual ExtractedPlan extract_plan(const z3::model& model) const = 0;
};

/**
 * @brief Everything an encoder needs to build itself.
 *
 * `seed_mode` asks for the plain bounded transition system only (no goal
 * binding, no horizon machinery); the oversubscription seed optimizes over it.
 */
struct EncoderContext {
    const Problem& problem;
    z3::context& ctx;
    int formula_length;
    bool horizon_planning;
    std::vector<Encoder::WeightedGoal> oversubscription_goals;
    bool seed_mode = false;
};

using EncoderFactory = std::function<std::unique_ptr<Encoder>(const EncoderContext&)>;
using EncoderRegistry = PluginRegistry<EncoderFactory>;
using EncoderPlugin = Plugin<EncoderFactory>;

} // namespace bp
