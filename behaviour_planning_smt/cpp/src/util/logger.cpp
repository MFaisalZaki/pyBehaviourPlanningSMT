// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "logger.hpp"
#include <iostream>
#include <iomanip>
#include <sstream>

namespace bp {

std::unique_ptr<Logger> Logger::instance_;

Logger& Logger::instance() {
    if (!instance_) {
        instance_ = std::unique_ptr<Logger>(new Logger());
    }
    return *instance_;
}

void Logger::set_config(const Config* config) {
    config_ = config;
}

bool Logger::should_print(VerbosityLevel min_level) const {
    if (!enabled_) {
        return false;
    }

    // Error messages always print
    if (min_level == VerbosityLevel::SILENT) {
        return true;
    }

    // If no config yet, default to INFO level
    if (!config_) {
        return min_level <= VerbosityLevel::INFO;
    }

    // Check against configured verbosity
    return config_->global.verbosity >= min_level;
}

void Logger::info(const std::string& msg) {
    if (should_print(VerbosityLevel::INFO)) {
        std::cout << msg << std::endl;
    }
}

void Logger::verbose(const std::string& msg) {
    if (should_print(VerbosityLevel::VERBOSE)) {
        std::cout << msg << std::endl;
    }
}

void Logger::debug(const std::string& msg) {
    if (should_print(VerbosityLevel::DEBUG)) {
        std::cout << msg << std::endl;
    }
}

void Logger::error(const std::string& msg) {
    // Errors always print to stderr
    std::cerr << "Error: " << msg << std::endl;
}

std::string Logger::format_component_line(
    const std::string& component_name,
    const std::vector<std::pair<std::string, std::string>>& metrics
) const {
    std::ostringstream oss;

    // Component name in brackets, left-aligned in fixed width
    oss << "[" << std::left << std::setw(COMPONENT_WIDTH - 2) << component_name << "]";

    // Metrics separated by " | "
    bool first = true;
    for (const auto& metric : metrics) {
        if (!first) {
            oss << "  |  ";
        } else {
            oss << "  ";
            first = false;
        }
        oss << metric.first << ": " << metric.second;
    }

    return oss.str();
}

void Logger::component(
    VerbosityLevel min_level,
    const std::string& component_name,
    const std::vector<std::pair<std::string, std::string>>& metrics
) {
    if (should_print(min_level)) {
        std::cout << format_component_line(component_name, metrics) << std::endl;
    }
}

void Logger::timestep_encoding(
    VerbosityLevel min_level,
    int timestep,
    const std::vector<std::pair<std::string, std::string>>& metrics
) {
    if (should_print(min_level)) {
        std::ostringstream component_name;
        component_name << "Encoding T" << timestep;
        std::cout << format_component_line(component_name.str(), metrics) << std::endl;
    }
}

void Logger::timestep_solving(
    VerbosityLevel min_level,
    int timestep,
    const std::vector<std::pair<std::string, std::string>>& metrics
) {
    if (should_print(min_level)) {
        std::ostringstream component_name;
        component_name << "Solving T" << timestep;
        std::cout << format_component_line(component_name.str(), metrics) << std::endl;
    }
}

void Logger::summary(const std::map<std::string, std::string>& data) {
    if (!should_print(VerbosityLevel::INFO)) {
        return;
    }

    std::cout << "\n=== Planning Summary ===" << std::endl;

    // Find the longest key for alignment
    size_t max_key_length = 0;
    for (const auto& pair : data) {
        max_key_length = std::max(max_key_length, pair.first.length());
    }

    // Print each key-value pair, aligned
    for (const auto& pair : data) {
        std::cout << std::left << std::setw(max_key_length + 1) << (pair.first + ":")
                  << " " << pair.second << std::endl;
    }

    std::cout << "========================" << std::endl;
}

void Logger::set_enabled(bool enabled) {
    enabled_ = enabled;
}

} // namespace bp
