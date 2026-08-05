// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <string>
#include <chrono>

namespace bp {

/**
 * @brief RAII timer that automatically records elapsed time to Stats singleton
 *
 * Usage:
 *   {
 *       ScopedTimer timer("rpg.build_time_ms");
 *       // ... do work ...
 *   }  // Automatically records timing to Stats on destruction
 *
 * You can also query elapsed time before destruction:
 *   ScopedTimer timer("key");
 *   // ... do some work ...
 *   double elapsed = timer.elapsed_ms();
 */
class ScopedTimer {
public:
    /**
     * @brief Construct timer and start measuring
     * @param stats_key Key to use when recording to Stats singleton
     */
    explicit ScopedTimer(const std::string& stats_key);

    /**
     * @brief Destructor - records elapsed time to Stats
     */
    ~ScopedTimer();

    /**
     * @brief Get elapsed time in milliseconds (without destroying timer)
     */
    double elapsed_ms() const;

    /**
     * @brief Get elapsed time in seconds (without destroying timer)
     */
    double elapsed_s() const;

    // Disable copy and move
    ScopedTimer(const ScopedTimer&) = delete;
    ScopedTimer& operator=(const ScopedTimer&) = delete;
    ScopedTimer(ScopedTimer&&) = delete;
    ScopedTimer& operator=(ScopedTimer&&) = delete;

private:
    std::string stats_key_;
    std::chrono::high_resolution_clock::time_point start_;
};

} // namespace bp
