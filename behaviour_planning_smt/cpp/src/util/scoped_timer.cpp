// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "scoped_timer.hpp"
#include "stats.hpp"

namespace bp {

ScopedTimer::ScopedTimer(const std::string& stats_key)
    : stats_key_(stats_key)
    , start_(std::chrono::high_resolution_clock::now()) {
}

ScopedTimer::~ScopedTimer() {
    // Record elapsed time to Stats singleton
    Stats::instance().set(stats_key_, elapsed_ms());
}

double ScopedTimer::elapsed_ms() const {
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration<double, std::milli>(end - start_);
    return duration.count();
}

double ScopedTimer::elapsed_s() const {
    return elapsed_ms() / 1000.0;
}

} // namespace bp
