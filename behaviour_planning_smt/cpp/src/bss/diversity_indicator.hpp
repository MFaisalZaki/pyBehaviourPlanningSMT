#pragma once

#include "../plugins/plugin.hpp"
#include "behaviour_space.hpp"

#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace bp {

/**
 * @brief A diversity indicator: the optimisation metric a diversification run
 * maximises over the behaviour space.
 *
 * An indicator owns the strategy that turns behaviour-space queries into a set
 * of diverse plans: it decides which assumptions to solve under, in which
 * order, and when the metric cannot improve any further. The first indicator,
 * behaviour diversity count ('bdc'), maximises the number of distinct
 * behaviours by forbidding every behaviour found and generating another one.
 *
 * Indicators are plugins (see plugins/plugin.hpp): each lives in its own file
 * under bss/indicators/, registers itself under a name, and is selected with
 * --indicator NAME[:ARG]. Further indicators — for instance ones that maximise
 * pairwise behaviour distance — use the per-dimension distance functions
 * exposed through space.dimensions().
 */
class DiversityIndicator {
public:
    struct Result {
        std::vector<DiversePlan> plans;
        int new_behaviour_count = 0; ///< plans found by improving the indicator
    };

    virtual ~DiversityIndicator() = default;

    /// The plugin name of this indicator ("bdc", ...).
    virtual const std::string& name() const = 0;

    /**
     * Generate up to `requested_plans` plans from the behaviour space,
     * optimising this indicator. `out_of_time` must be consulted between
     * solver queries; when it returns true the indicator returns what it has.
     */
    virtual Result generate(BehaviourSpace& space, size_t requested_plans,
                            const std::function<bool()>& out_of_time) = 0;
};

using DiversityIndicatorFactory =
    std::function<std::unique_ptr<DiversityIndicator>(const std::string& argument)>;
using DiversityIndicatorRegistry = PluginRegistry<DiversityIndicatorFactory>;
using DiversityIndicatorPlugin = Plugin<DiversityIndicatorFactory>;

} // namespace bp
