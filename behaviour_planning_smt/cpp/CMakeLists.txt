cmake_minimum_required(VERSION 3.10)

# ==============================================================================
# PROJECT CONFIGURATION
# ==============================================================================
# The C++ core of behaviour_planning_smt. The build system, protobuf
# interchange and problem model follow RantanPlan
# (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
project(bp_planner)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Set default output directory
if(NOT DEFINED OUTPUT_DIR)
    set(OUTPUT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../bin" CACHE STRING "Output directory for executable")
endif()

# ==============================================================================
# PROTOBUF SETUP
# ==============================================================================
# https://github.com/protocolbuffers/protobuf/issues/12637
if(APPLE)
    find_package(Protobuf REQUIRED CONFIG)
else()
    find_package(Protobuf REQUIRED)
endif()

# ==============================================================================
# Z3 SOLVER SETUP
# ==============================================================================
find_package(Z3 QUIET)

if(Z3_FOUND)
    message(STATUS "Found Z3 using CMake package config")
    set(Z3_LINK_LIBRARY z3::libz3)
else()
    # Manual Z3 setup: paths are passed by build.py from the z3-solver
    # Python package installation.
    message(STATUS "Using manual Z3 setup")

    set(Z3_INCLUDE_DIR ${Z3_INCLUDE_DIR} CACHE STRING "Z3 include directory")
    set(Z3_LIB_DIR ${Z3_LIB_DIR} CACHE STRING "Z3 library directory")

    find_library(Z3_LIBRARY
        NAMES z3 libz3
        PATHS ${Z3_LIB_DIR}
        NO_DEFAULT_PATH
    )

    if(NOT Z3_LIBRARY)
        message(FATAL_ERROR "Z3 library not found in ${Z3_LIB_DIR}")
    endif()

    message(STATUS "Found Z3 library: ${Z3_LIBRARY}")
    set(Z3_LINK_LIBRARY ${Z3_LIBRARY})
endif()

# ==============================================================================
# TARGET DEFINITION
# ==============================================================================
add_executable(bp_planner
    src/main.cpp
    src/config/config.cpp
    src/config/cli_parser.cpp
    src/util/memory_tracker.cpp
    src/util/stats.cpp
    src/util/scoped_timer.cpp
    src/util/logger.cpp
    src/problem/real.cpp
    src/problem/atom.cpp
    src/problem/parameter.cpp
    src/problem/expression.cpp
    src/problem/effect_expression.cpp
    src/problem/effect.cpp
    src/problem/object.cpp
    src/problem/fluent.cpp
    src/problem/goal.cpp
    src/problem/assignment.cpp
    src/problem/action.cpp
    src/problem/plan.cpp
    src/problem/problem.cpp
    src/problem/problem_normalizer.cpp
    src/problem/type.cpp
    src/problem/visitors/expression_visitor.cpp
    src/analysis/relaxed_planning_graph.cpp
    src/encoders/z3_variable_factory.cpp
    src/encoders/grounded_encoding_visitor.cpp
    src/bss/dimension.cpp
    src/bss/behaviour_space.cpp
    src/planners/fbi_planner.cpp
    # --- Plugins: each file self-registers via a static Plugin object.
    # Adding a new encoder or dimension = one new file + one line here.
    src/encoders/seq_encoder.cpp
    src/bss/dimensions/go.cpp
    src/bss/dimensions/cb.cpp
    src/bss/dimensions/ru.cpp
    src/bss/dimensions/uv.cpp
    src/bss/dimensions/fn.cpp
    src/bss/dimensions/action_count.cpp
    src/bss/indicators/behaviour_diversity_count.cpp
)

# Define proto files and generate C++ sources
set(PROTO_FILES ${CMAKE_CURRENT_SOURCE_DIR}/proto/unified_planning.proto)
protobuf_generate(TARGET bp_planner
    PROTOS ${PROTO_FILES}
    LANGUAGE cpp
)

# ==============================================================================
# TARGET CONFIGURATION
# ==============================================================================
target_include_directories(bp_planner PRIVATE
    ${CMAKE_CURRENT_BINARY_DIR}                      # generated protobuf sources
    ${CMAKE_CURRENT_BINARY_DIR}/proto                # generated protobuf headers
    ${CMAKE_CURRENT_SOURCE_DIR}/src                  # our source headers
    ${CMAKE_CURRENT_SOURCE_DIR}/src/config
    ${CMAKE_CURRENT_SOURCE_DIR}/src/util
    ${CMAKE_CURRENT_SOURCE_DIR}/src/problem
    ${CMAKE_CURRENT_SOURCE_DIR}/src/problem/visitors
    ${CMAKE_CURRENT_SOURCE_DIR}/src/analysis
    ${CMAKE_CURRENT_SOURCE_DIR}/src/encoders
    ${CMAKE_CURRENT_SOURCE_DIR}/src/bss
    ${CMAKE_CURRENT_SOURCE_DIR}/src/planners
    ${CMAKE_CURRENT_SOURCE_DIR}/src/plugins
    ${Protobuf_INCLUDE_DIRS}
    ${Z3_INCLUDE_DIR}
)

target_link_libraries(bp_planner PRIVATE
    protobuf::libprotobuf
    ${Z3_LINK_LIBRARY}
)

# ==============================================================================
# PLATFORM-SPECIFIC FIXES
# ==============================================================================
# Fix Z3 library reference on macOS
if(APPLE AND NOT Z3_FOUND)
    message(STATUS "macOS manual Z3: Using install_name_tool to set absolute path for libz3.dylib in 'bp_planner'")
    add_custom_command(TARGET bp_planner POST_BUILD
        COMMAND ${CMAKE_INSTALL_NAME_TOOL} -change libz3.dylib ${Z3_LIBRARY} $<TARGET_FILE:bp_planner>
        COMMENT "Fixing Z3 dylib reference in bp_planner executable to absolute path"
        VERBATIM
    )
endif()

# ==============================================================================
# INSTALLATION
# ==============================================================================
install(TARGETS bp_planner DESTINATION ${OUTPUT_DIR})

# ==============================================================================
# Set RPATH for Z3 if found manually
# ==============================================================================
if(NOT Z3_FOUND AND Z3_LIB_DIR)
    set_target_properties(bp_planner PROPERTIES
        BUILD_WITH_INSTALL_RPATH TRUE
        INSTALL_RPATH "${Z3_LIB_DIR}"
        SKIP_BUILD_RPATH FALSE
        SKIP_INSTALL_RPATH FALSE
    )
endif()
