// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "real.hpp"
#include <numeric>

namespace bp {

Real::Real(double value) {
    // Convert double to fraction (simple approach)
    const int64_t precision = 1000000; // 6 decimal places
    numerator_ = static_cast<int64_t>(value * precision);
    denominator_ = precision;
    
    // Basic normalization to avoid division by zero
    if (denominator_ == 0) {
        denominator_ = 1;
    }
    
    // Reduce to lowest terms for cleaner representation
    int64_t gcd_val = std::gcd(std::abs(numerator_), std::abs(denominator_));
    if (gcd_val > 1) {
        numerator_ /= gcd_val;
        denominator_ /= gcd_val;
    }
}

Real::Real(const pb::Real& pb_real) 
    : numerator_(pb_real.numerator()), denominator_(pb_real.denominator()) {
    // Ensure denominator is not zero
    if (denominator_ == 0) {
        denominator_ = 1;
    }
}

double Real::to_double() const {
    return static_cast<double>(numerator_) / static_cast<double>(denominator_);
}

std::string Real::to_string() const {
    if (denominator_ == 1) {
        return std::to_string(numerator_);
    }
    return std::to_string(numerator_) + "/" + std::to_string(denominator_);
}

bool Real::operator==(const Real& other) const {
    // Compare cross products to avoid floating point issues
    return numerator_ * other.denominator_ == other.numerator_ * denominator_;
}

} // namespace bp
