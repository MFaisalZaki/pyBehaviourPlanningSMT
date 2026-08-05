// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "unified_planning.pb.h"

/**
 * @brief Protobuf type aliases using pb:: namespace for clean separation
 * 
 * This file creates aliases for all protobuf types in the pb:: namespace,
 * allowing our custom classes to use clean, natural names.
 * This approach works regardless of whether the protobuf file has a package
 * declaration or not, and survives protobuf regeneration.
 */

namespace pb {
    // Core protobuf types
    using Action = ::Action;
    using ActionInstance = ::ActionInstance;
    using Effect = ::Effect;
    using EffectExpression = ::EffectExpression;
    using Expression = ::Expression;
    using Condition = ::Condition;
    using Parameter = ::Parameter;
    using Fluent = ::Fluent;
    using Goal = ::Goal;
    using Assignment = ::Assignment;
    using Problem = ::Problem;
    using Plan = ::Plan;
    using ObjectDeclaration = ::ObjectDeclaration;
    using TypeDeclaration = ::TypeDeclaration;
    
    // Basic types
    using Atom = ::Atom;
    using Real = ::Real;
    
    // Enums
    using ExpressionKind = ::ExpressionKind;
    using EffectExpression_EffectKind = ::EffectExpression_EffectKind;

    // Repeated field aliases for cleaner signatures
    using RepeatedTypeDeclaration = ::google::protobuf::RepeatedPtrField<TypeDeclaration>;
    using RepeatedObjectDeclaration = ::google::protobuf::RepeatedPtrField<ObjectDeclaration>;
    using RepeatedFluent = ::google::protobuf::RepeatedPtrField<Fluent>;
    using RepeatedAction = ::google::protobuf::RepeatedPtrField<Action>;
}
