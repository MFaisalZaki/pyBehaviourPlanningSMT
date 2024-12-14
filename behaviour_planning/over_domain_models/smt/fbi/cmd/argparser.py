import os
import sys
import argparse

def _is_valid_file(arg):
    """
    Checks whether input PDDL files exist and are valid
    """
    if not os.path.exists(arg):
        raise argparse.ArgumentTypeError('{} not found!'.format(arg))
    elif not os.path.splitext(arg)[1] == ".pddl":
        raise argparse.ArgumentTypeError('{} is not a valid PDDL file!'.format(arg))
    else:
        return arg


def create_parser():

    parser = argparse.ArgumentParser(description = "Behaviour Planning for Diverse Planning CLI",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('plannercfg', help='Path to the behaviour space configuration file')
    parser.add_argument('domain', help='Path to PDDL domain file', type=_is_valid_file)
    parser.add_argument('problem', metavar='problem.pddl', help='Path to PDDL problem file', type=_is_valid_file)
    
    # How we want to run bplanning
    parser.add_argument('-k', type=int, help='Number of plans to generate')
    parser.add_argument('-q', type=float, help='Quality bound factor')
    
    parser.add_argument('--add-goal-ordering', action='store_true', help='Add goal ordering to the plan')
    
    parser.add_argument('--add-resource-count', action='store_true', help='Add resource count to the plan')
    parser.add_argument('--resource-file', help='Resource file to use')

    parser.add_argument('--add-makespan', action='store_true', help='Add makespan to the plan')

    parser.add_argument('--dump-dir', help='Directory to dump plans to')

    return parser
