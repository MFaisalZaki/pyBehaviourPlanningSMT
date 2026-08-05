// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <cstdint>
#include <string>
#include "protobuf_aliases.hpp"

namespace bp {

/**
 * @brief Simple rational number for data transport
 * 
 * Represents a rational number as numerator/denominator fraction.
 * Used only for data transport between protobuf and Z3 - all arithmetic 
 * operations are delegated to the Z3 SMT solver.
 */
class Real {
public:
    // Constructors
    Real() : numerator_(0), denominator_(1) {}
    Real(int64_t numerator, int64_t denominator = 1) : numerator_(numerator), denominator_(denominator) {}
    Real(double value);
    Real(const pb::Real& pb_real);
    
    // Accessors (needed for Z3 conversion)
    int64_t numerator() const { return numerator_; }
    int64_t denominator() const { return denominator_; }
    
    // Conversion utilities
    double to_double() const;
    std::string to_string() const;
    
    // Basic equality for debugging/testing
    bool operator==(const Real& other) const;
    bool operator!=(const Real& other) const { return !(*this == other); }

private:
    int64_t numerator_;
    int64_t denominator_;
};

} // namespace bp
