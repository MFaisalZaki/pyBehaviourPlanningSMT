// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <string>
#include <vector>
#include <map>
#include <utility>
#include <memory>
#include "config/config.hpp"

namespace bp {

/**
 * @brief Centralized logging with consistent formatting and verbosity control
 *
 * Replaces scattered std::cout statements with structured, verbosity-aware output.
 * All output goes through this class, ensuring consistent formatting and respecting
 * the global verbosity settings.
 *
 * Usage:
 *   Logger::instance().info("Starting RPG construction");
 *   Logger::instance().component(VerbosityLevel::INFO, "RPG.Boolean", {
 *       {"time", "147ms"},
 *       {"layers", "15"},
 *       {"mem", "12MB"}
 *   });
 */
class Logger {
public:
    // Get the global logger instance
    static Logger& instance();

    // Initialize with config (must be called after Config is initialized)
    void set_config(const Config* config);

    // Simple message logging (respects verbosity)
    void info(const std::string& msg);
    void verbose(const std::string& msg);
    void debug(const std::string& msg);
    void error(const std::string& msg);  // Always shown

    // Structured component output with consistent formatting
    // Format: [ComponentName]  time: Xms  |  key1: value1  |  key2: value2  |  mem: XMB
    void component(
        VerbosityLevel min_level,
        const std::string& component_name,
        const std::vector<std::pair<std::string, std::string>>& metrics
    );

    // Timestep-specific output for search loop
    // Format: [Encoding T0]  time: Xms  |  constraints: N  |  mem: XMB
    // Format: [Solving T0]   time: Xms  |  result: SAT/UNSAT
    void timestep_encoding(
        VerbosityLevel min_level,
        int timestep,
        const std::vector<std::pair<std::string, std::string>>& metrics
    );

    void timestep_solving(
        VerbosityLevel min_level,
        int timestep,
        const std::vector<std::pair<std::string, std::string>>& metrics
    );

    // Summary box for final results
    // Format:
    // === Planning Summary ===
    // Total time:     1.234s
    // Plan found:     YES
    // ...
    // ========================
    void summary(const std::map<std::string, std::string>& data);

    // Enable/disable all output (for testing)
    void set_enabled(bool enabled);

private:
    Logger() = default;

    // Check if we should print at this level
    bool should_print(VerbosityLevel min_level) const;

    // Formatting helpers
    std::string format_component_line(
        const std::string& component_name,
        const std::vector<std::pair<std::string, std::string>>& metrics
    ) const;

    const Config* config_ = nullptr;
    bool enabled_ = true;

    static constexpr int COMPONENT_WIDTH = 16;  // Width for component name column

    static std::unique_ptr<Logger> instance_;
};

} // namespace bp
