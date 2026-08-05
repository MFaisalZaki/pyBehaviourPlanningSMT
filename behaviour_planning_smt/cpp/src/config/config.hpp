#pragma once

#include <string>
#include <vector>
#include <mutex>
#include <memory>

namespace bp {

enum class VerbosityLevel {
    SILENT = 0,
    INFO = 1,
    VERBOSE = 2,
    DEBUG = 3
};

/**
 * @brief One behaviour-space dimension requested on the command line.
 *
 * `name` is the short dimension code ('go', 'cb', 'ru', 'uv', 'fn') and `arg`
 * carries the dimension-specific argument: the quality bound for 'cb' and the
 * resources/functions file path for 'ru'/'fn'. Empty for 'go' and 'uv'.
 */
struct DimensionSpec {
    std::string name;
    std::string arg;
};

class Config {
public:
    static Config& instance();

    struct Global {
        VerbosityLevel verbosity = VerbosityLevel::INFO;
        bool debug_mode = false;
        int timeout = 3600;                 // overall wall-clock budget in seconds
        std::string stats_file = "";        // empty means no file output
        bool enable_action_removal = true;  // RPG-based pruning of unreachable actions
    } global;

    struct Planner {
        int num_plans = 1;                       // how many diverse plans to generate
        std::vector<DimensionSpec> dimensions;   // behaviour-space dimensions, in order
        double quality_bound = 1.0;              // derived from the 'cb' dimension argument
        int horizon_length = -1;                 // -1: infer the optimal length with a seed search
        bool horizon_planning_mode = false;      // pin the horizon to the formula's last step
        int max_steps = 500;                     // seed-search horizon cap
        int oversubscription_horizon = 30;       // encoding bound for the oversubscription seed
        int start_timestep = 0;                  // seed-search start (set from the RPG lower bound)
        int solver_timeout_ms = 300000;          // per solver check() call
        int solver_memory_mb = 16000;            // per solver check() call
    } planner;

    void initialize(int argc, char* argv[]);

    bool is_silent() const { return global.verbosity == VerbosityLevel::SILENT; }
    bool is_info() const { return global.verbosity >= VerbosityLevel::INFO; }
    bool is_verbose() const { return global.verbosity >= VerbosityLevel::VERBOSE; }
    bool is_debug() const { return global.verbosity >= VerbosityLevel::DEBUG; }

private:
    Config() = default;
    Config(const Config&) = delete;
    Config& operator=(const Config&) = delete;

    static std::once_flag initialized_flag_;
    static std::unique_ptr<Config> instance_;

    friend std::default_delete<Config>;
};

} // namespace bp
