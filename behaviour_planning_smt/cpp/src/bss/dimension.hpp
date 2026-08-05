#pragma once

#include "../encoders/encoder.hpp"
#include "../plugins/plugin.hpp"
#include <z3++.h>

#include <functional>
#include <initializer_list>
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
 * values plus a printable value.
 *
 * Dimensions are plugins (see plugins/plugin.hpp): each implementation lives
 * in its own file under bss/dimensions/, registers itself under a short name,
 * and is requested from the command line with --dim NAME[:ARG].
 *
 * A dimension is handed the active encoder and is responsible for knowing
 * which encoders it can encode itself for: query encoder.name() and place the
 * encodings accordingly, and reject unsupported encoders with
 * require_encoder() so the user gets a clear error instead of silently wrong
 * constraints.
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

    /**
     * @brief Distance between two behaviour values of THIS dimension.
     *
     * `a` and `b` are printable values as produced by evaluate().value for two
     * plans. The default is the discrete metric — 0 when equal, 1 otherwise —
     * which every dimension satisfies; override it with a semantically
     * meaningful distance (the built-ins do: absolute difference for counts,
     * Hamming distance for the goal-ordering vector, per-function box
     * differences for 'fn'). Diversity indicators aggregate these to score
     * how far apart two plans are.
     *
     * Requirements: non-negative, symmetric, and 0 for equal values.
     */
    virtual double distance(const std::string& a, const std::string& b) const;

protected:
    /// |a - b| when both values parse as numbers; discrete metric otherwise.
    static double numeric_distance(const std::string& a, const std::string& b);

    /**
     * Guard for encoder support: throws std::invalid_argument when the active
     * encoder is not among `supported`, naming both sides. Call it first in a
     * dimension constructor — or branch on encoder.name() directly when the
     * dimension places different encodings for different encoders.
     */
    static void require_encoder(const Encoder& encoder, const std::string& dimension_name,
                                std::initializer_list<const char*> supported);

    std::string name_;
    std::vector<z3::expr> formula_;
};

/**
 * @brief Planner-level values a dimension may need besides the encoder.
 */
struct DimensionContext {
    int optimal_plan_length = 0;
    double quality_bound = 1.0;
};

using DimensionFactory = std::function<std::unique_ptr<Dimension>(
    const Encoder& encoder, const std::string& argument, const DimensionContext& context)>;
using DimensionRegistry = PluginRegistry<DimensionFactory>;
using DimensionPlugin = Plugin<DimensionFactory>;

/// One entry of a resources/functions file: (:resource NAME MIN MAX DELTA).
struct RangeEntry {
    std::string name;
    long min = 0;
    long max = 0;
    long delta = 0;
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
