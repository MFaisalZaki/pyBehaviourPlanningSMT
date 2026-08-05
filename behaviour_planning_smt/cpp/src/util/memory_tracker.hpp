// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

namespace bp {

/**
 * @brief Simple memory tracking utility for monitoring RSS memory usage
 * 
 * Provides lightweight tracking of current memory usage during
 * planning operations. Platform-specific implementations for Linux and macOS.
 */
class MemoryTracker {
public:

    /**
     * @brief Get the singleton instance
     */
    static MemoryTracker& instance();
    
    
    /**
     * @brief Get current memory usage
     * @return Current RSS memory in MB, or 0.0 if unable to read
     */
    double get_current_memory_mb();

private:
    
    MemoryTracker() = default;
    ~MemoryTracker() = default;
    MemoryTracker(const MemoryTracker&) = delete;
    MemoryTracker& operator=(const MemoryTracker&) = delete;
    
    /**
     * @brief Platform-specific memory reading implementation
     * @return RSS memory in MB, or 0.0 if unable to read
     */
    double read_rss_memory_mb();
};


} // namespace bp