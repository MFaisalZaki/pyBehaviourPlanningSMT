// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <string>
#include <map>
#include <memory>
#include <iostream>
#include <mutex>

namespace bp {

/**
 * @brief Thread-safe statistics collection - global key-value store
 *
 * Think of it like a global dictionary/map that you can set and get values from anywhere.
 * Only supports numbers (as doubles). Thread-safe for future parallelization.
 */
class Stats {
public:
    // Get the global stats instance
    static Stats& instance();

    // Set a statistic (number only - keeps it simple!)
    void set(const std::string& key, double value);

    // Get a statistic (returns 0 if key doesn't exist)
    double get(const std::string& key) const;

    // Add to an existing statistic (creates it if it doesn't exist)
    void add(const std::string& key, double value = 1.0);

    // Bulk operations
    void set_multiple(const std::map<std::string, double>& values);

    // Prefix helper for namespacing
    void set_prefixed(const std::string& prefix, const std::string& key, double value);

    // Clear all statistics
    void clear();

    // Print all statistics (simple format)
    void print_all() const;

    // Write all statistics to file
    void write_to_file(const std::string& filename) const;

    // Get number of statistics stored
    size_t size() const;

private:
    Stats() = default;

    // Just a simple map ...
    std::map<std::string, double> stats_;

    // Mutex for thread safety
    mutable std::mutex mutex_;

    static std::unique_ptr<Stats> instance_;
};

} // namespace bp