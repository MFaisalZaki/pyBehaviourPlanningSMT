#include "cli_parser.hpp"
#include "../bss/dimension.hpp"
#include "../bss/diversity_indicator.hpp"
#include "../encoders/encoder.hpp"
#include <iostream>
#include <stdexcept>

namespace bp {

void CLIParser::print_help(const char* program_name) {
    std::cout <<
        "Usage: " << program_name << " <input_problem.pb> <output_result.pb> [OPTIONS]\n"
        "\n"
        "Forbid-Behaviour-Iterative diverse planner over an SMT encoding.\n"
        "Reads a grounded unified-planning problem serialized as protobuf, generates\n"
        "up to --num-plans behaviourally diverse plans, and writes one\n"
        "PlanGenerationResult per plan: <output_result.pb> holds the overall result\n"
        "and <output_result.pb>.<i> the i-th plan (i starting at 0).\n"
        "\n"
        "Encoders, behaviour-space dimensions and diversity indicators are plugins:\n"
        "--list-encoders, --list-dimensions and --list-indicators show what this\n"
        "build registered. Each dimension decides for itself which encoders it\n"
        "supports, and the indicator is the optimisation metric the diversification\n"
        "maximises over the behaviour space.\n"
        "\n"
        "Options:\n"
        "  --num-plans K             number of diverse plans to generate (default 1)\n"
        "  --encoder NAME            encoder plugin to use (default seq)\n"
        "  --dim SPEC                dimension plugin, repeatable, in order.\n"
        "                            SPEC is NAME or NAME:ARG; see --list-dimensions.\n"
        "                            The built-in dimensions:\n"
        "                              go        goal predicate ordering\n"
        "                              cb:Q      makespan-optimal cost bound, Q = quality bound\n"
        "                              ru:FILE   resource usage count, FILE = resources file\n"
        "                              uv        utility value (oversubscription tasks)\n"
        "                              fn:FILE   numeric function values, FILE = functions file\n"
        "                              ac:NAME   action count (example plugin)\n"
        "  --indicator NAME[:ARG]    diversity-indicator plugin to optimise (default bdc,\n"
        "                            behaviour diversity count)\n"
        "  --list-dimensions         list the registered dimension plugins and exit\n"
        "  --list-encoders           list the registered encoder plugins and exit\n"
        "  --list-indicators         list the registered diversity-indicator plugins and exit\n"
        "  --horizon-length N        skip the seed search and use N as the optimal plan length\n"
        "  --horizon-planning-mode   pin the horizon to the formula's last step\n"
        "  --max-steps N             seed-search horizon cap (default 500)\n"
        "  --oversubscription-horizon N\n"
        "                            encoding bound for the oversubscription seed (default 30)\n"
        "  --solver-timeout MS       per-check solver timeout in milliseconds (default 300000)\n"
        "  --solver-memory MB        per-check solver memory limit in MB (default 16000)\n"
        "  --timeout S               overall wall-clock budget in seconds (default 3600)\n"
        "  --no-action-removal       disable RPG-based pruning of unreachable actions\n"
        "  --stats-file FILE         write solver statistics to FILE\n"
        "  --verbosity LEVEL         silent | info | verbose | debug (default info)\n"
        "  --silent | -v | -vv       shorthands for the verbosity levels\n"
        "  --help                    show this message and exit\n";
}

namespace {

void print_plugin_list(const std::string& title,
                       const std::vector<std::pair<std::string, std::string>>& plugins) {
    std::cout << title << ":\n";
    for (const auto& [name, documentation] : plugins) {
        std::cout << "  " << name << "\n      " << documentation << "\n";
    }
}

} // namespace

DimensionSpec CLIParser::parse_dimension(const std::string& value) const {
    DimensionSpec spec;
    auto colon = value.find(':');
    if (colon == std::string::npos) {
        spec.name = value;
    } else {
        spec.name = value.substr(0, colon);
        spec.arg = value.substr(colon + 1);
    }
    // The registry is the authority on which dimensions exist; its error
    // message lists everything this build registered.
    DimensionRegistry::instance().get(spec.name);
    return spec;
}

void CLIParser::parse(Config& config, int argc, char* argv[]) {
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            print_help(argv[0]);
            exit(0);
        }
        if (arg == "--list-dimensions") {
            print_plugin_list("Registered dimension plugins",
                              DimensionRegistry::instance().list());
            exit(0);
        }
        if (arg == "--list-encoders") {
            print_plugin_list("Registered encoder plugins",
                              EncoderRegistry::instance().list());
            exit(0);
        }
        if (arg == "--list-indicators") {
            print_plugin_list("Registered diversity-indicator plugins",
                              DiversityIndicatorRegistry::instance().list());
            exit(0);
        }
    }

    auto next_value = [&](int& i, const std::string& flag) -> std::string {
        if (i + 1 >= argc) {
            throw std::invalid_argument(flag + " requires a value");
        }
        return argv[++i];
    };

    for (int i = 3; i < argc; ++i) {
        std::string arg = argv[i];

        if (arg == "--num-plans") {
            config.planner.num_plans = std::stoi(next_value(i, arg));
        }
        else if (arg == "--encoder") {
            config.planner.encoder = next_value(i, arg);
            EncoderRegistry::instance().get(config.planner.encoder); // validate early
        }
        else if (arg == "--indicator") {
            std::string value = next_value(i, arg);
            auto colon = value.find(':');
            if (colon == std::string::npos) {
                config.planner.indicator = value;
                config.planner.indicator_arg.clear();
            } else {
                config.planner.indicator = value.substr(0, colon);
                config.planner.indicator_arg = value.substr(colon + 1);
            }
            DiversityIndicatorRegistry::instance().get(config.planner.indicator); // validate early
        }
        else if (arg == "--dim") {
            DimensionSpec spec = parse_dimension(next_value(i, arg));
            if (spec.name == "cb" && !spec.arg.empty()) {
                // The cb argument doubles as a planner parameter: the quality
                // bound scales the encoded formula length, so it is needed
                // before any dimension is built. This mirrors the Python
                // implementation, which also read it off the cb dimension.
                config.planner.quality_bound = std::stod(spec.arg);
            }
            config.planner.dimensions.push_back(spec);
        }
        else if (arg == "--horizon-length") {
            config.planner.horizon_length = std::stoi(next_value(i, arg));
        }
        else if (arg == "--horizon-planning-mode") {
            config.planner.horizon_planning_mode = true;
        }
        else if (arg == "--max-steps") {
            config.planner.max_steps = std::stoi(next_value(i, arg));
        }
        else if (arg == "--oversubscription-horizon") {
            config.planner.oversubscription_horizon = std::stoi(next_value(i, arg));
        }
        else if (arg == "--solver-timeout") {
            config.planner.solver_timeout_ms = std::stoi(next_value(i, arg));
        }
        else if (arg == "--solver-memory") {
            config.planner.solver_memory_mb = std::stoi(next_value(i, arg));
        }
        else if (arg == "--timeout") {
            config.global.timeout = std::stoi(next_value(i, arg));
        }
        else if (arg == "--no-action-removal") {
            config.global.enable_action_removal = false;
        }
        else if (arg == "--stats-file") {
            config.global.stats_file = next_value(i, arg);
        }
        else if (arg == "--verbosity") {
            config.global.verbosity = parse_verbosity(next_value(i, arg));
        }
        else if (arg == "-v") {
            config.global.verbosity = VerbosityLevel::VERBOSE;
        }
        else if (arg == "-vv") {
            config.global.verbosity = VerbosityLevel::DEBUG;
        }
        else if (arg == "--silent") {
            config.global.verbosity = VerbosityLevel::SILENT;
        }
        else if (arg == "--debug") {
            config.global.debug_mode = true;
            config.global.verbosity = VerbosityLevel::DEBUG;
        }
        else {
            throw std::invalid_argument("Unknown option: " + arg);
        }
    }
}

VerbosityLevel CLIParser::parse_verbosity(const std::string& value) const {
    if (value == "silent") return VerbosityLevel::SILENT;
    if (value == "info") return VerbosityLevel::INFO;
    if (value == "verbose") return VerbosityLevel::VERBOSE;
    if (value == "debug") return VerbosityLevel::DEBUG;

    throw std::invalid_argument("Invalid verbosity level: " + value +
                                ". Valid values are: silent, info, verbose, debug");
}

} // namespace bp
