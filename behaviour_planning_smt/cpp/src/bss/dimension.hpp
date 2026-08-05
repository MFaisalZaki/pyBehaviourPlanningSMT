#pragma once

#include "../encoders/bounded_seq_encoder.hpp"
#include <z3++.h>

#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace bp {

/**
 * @brief One behaviour-space dimension.
 *
 * A dimension contributes constraints to the planning formula (its `formula()`)
 * and, given a model, evaluates to the behaviour of the found plan along this
 * dimension: a Z3 expression pinning the dimension's variables to their model
 * values plus a printable value. This is the C++ counterpart of the Python
 * DimensionConstructorSMT contract (__encode__ / expr).
 */
class Dimension {
public:
    struct BehaviourValue {
        std::optional<z3::expr> expr; ///< nullopt when the dimension has nothing to pin
        std::string value;            ///< printable form of the model value
    };

    explicit Dimension(std::string name) : name_(std::move(name)) {}
    virtual ~Dimension() = default;

    const std::string& name() const { return name_; }
    const std::vector<z3::expr>& formula() const { return formula_; }

    virtual BehaviourValue evaluate(const z3::model& model) const = 0;

protected:
    std::string name_;
    std::vector<z3::expr> formula_;
};

/**
 * @brief Goal predicate ordering ('go').
 *
 * Each goal conjunct gets an integer landmark variable holding the first state
 * layer at which the conjunct becomes true (-100 when it never does). Pairwise
 * orderings of those landmarks, reified through an uninterpreted function into
 * 0/1 integers, form the behaviour.
 */
class GoalOrderingDimension : public Dimension {
public:
    explicit GoalOrderingDimension(const BoundedSeqEncoder& encoder);
    BehaviourValue evaluate(const z3::model& model) const override;

private:
    std::vector<z3::expr> ordering_vars_;
};

/**
 * @brief Makespan-optimal cost bound ('cb').
 *
 * Counts the number of non-empty steps as the plan cost. For regular tasks the
 * cost is bounded below by the optimal plan length; for oversubscription tasks
 * it is instead capped by quality_bound * optimal_plan_length, which also caps
 * the horizon and disables all later steps.
 */
class CostBoundDimension : public Dimension {
public:
    CostBoundDimension(const BoundedSeqEncoder& encoder, double quality_bound,
                       int optimal_plan_length);
    BehaviourValue evaluate(const z3::model& model) const override;

private:
    std::optional<z3::expr> cost_var_;
};

/// One entry of a resources/functions file: (:resource NAME MIN MAX DELTA).
struct RangeEntry {
    std::string name;
    long min = 0;
    long max = 0;
    long delta = 0;
};

/**
 * @brief Resource usage count ('ru').
 *
 * A resource is used when any grounded action whose name contains the resource
 * name appears in the plan; the behaviour is the number of used resources.
 */
class ResourceCountDimension : public Dimension {
public:
    ResourceCountDimension(const BoundedSeqEncoder& encoder,
                           const std::vector<RangeEntry>& resources);
    BehaviourValue evaluate(const z3::model& model) const override;

private:
    std::optional<z3::expr> count_var_;
};

/**
 * @brief Utility value ('uv').
 *
 * Requires an oversubscription task: sums the weights of the metric goals that
 * hold in the final state and requires the total to be positive.
 */
class UtilityValueDimension : public Dimension {
public:
    explicit UtilityValueDimension(const BoundedSeqEncoder& encoder);
    BehaviourValue evaluate(const z3::model& model) const override;

private:
    std::optional<z3::expr> utility_var_;
};

/**
 * @brief Numeric function values ('fn').
 *
 * Slices the final-state value of each listed numeric fluent into boxes of
 * width delta; the box index a plan ends in is its behaviour along that fluent.
 */
class FunctionsDimension : public Dimension {
public:
    FunctionsDimension(const BoundedSeqEncoder& encoder,
                       const std::vector<RangeEntry>& functions);
    BehaviourValue evaluate(const z3::model& model) const override;

private:
    std::vector<std::pair<std::string, z3::expr>> function_vars_;
};

/**
 * @brief Parse a resources/functions file.
 *
 * Each entry has the form `(:KEYWORD NAME MIN MAX DELTA)` where KEYWORD is
 * `resource` or `function`. Later entries with an already-seen name overwrite
 * the earlier values but keep the original position.
 */
std::vector<RangeEntry> parse_range_file(const std::string& path, const std::string& keyword);

} // namespace bp
