#pragma once

#include "config.hpp"

namespace bp {

class CLIParser {
public:
    void parse(Config& config, int argc, char* argv[]);
    static void print_help(const char* program_name);

private:
    VerbosityLevel parse_verbosity(const std::string& value) const;
    DimensionSpec parse_dimension(const std::string& value) const;
};

} // namespace bp
