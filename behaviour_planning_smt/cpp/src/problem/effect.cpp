// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "effect.hpp"

namespace bp {

Effect::Effect(const pb::Effect& pb_effect, const Problem* problem) 
    : effect_expr_(pb_effect.effect(), problem) {
}

} // namespace bp
