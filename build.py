"""Build the bp_planner C++ core.

Mirrors RantanPlan's build script: configures CMake against the Z3 that ships
with the z3-solver Python package, builds, and installs the executable into
behaviour_planning_smt/bin.

    python build.py                    # release build
    python build.py --clean            # clean rebuild
    python build.py --build-type debug # debug build
"""

import argparse
import os
import subprocess

import z3

build_parameters = {
    "CMAKE_BUILD_TYPE": "release",
    "OUTPUT_DIR": os.path.join(os.path.dirname(__file__), "behaviour_planning_smt", "bin"),
    # Z3 include and lib dirs from the z3-solver Python package.
    "Z3_INCLUDE_DIR": os.path.join(os.path.dirname(z3.__file__), "include"),
    "Z3_LIB_DIR": os.path.join(os.path.dirname(z3.__file__), "lib"),
}


def build_ext(make_clean=False):
    build_dir = os.path.join(
        os.path.dirname(__file__), "behaviour_planning_smt", "cpp", "build")

    if make_clean and os.path.exists(build_dir):
        import shutil
        shutil.rmtree(build_dir)

    os.makedirs(build_dir, exist_ok=True)

    cmake_args = ["-D{}={}".format(key, value) for key, value in build_parameters.items()]

    subprocess.run(["cmake", "-G", "Unix Makefiles", ".."] + cmake_args, cwd=build_dir, check=True)
    subprocess.run(["cmake", "--build", ".", "-j", "4"], cwd=build_dir, check=True)
    subprocess.run(["cmake", "--install", "."], cwd=build_dir, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the bp_planner C++ core.")
    parser.add_argument(
        "--build-type",
        choices=["release", "debug"],
        default="release",
        help="CMake build type (default: release).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clear the build directory before building.",
    )
    args = parser.parse_args()

    build_parameters["CMAKE_BUILD_TYPE"] = args.build_type
    build_ext(make_clean=args.clean)
