import sys
import json
import os

from unified_planning.io import PDDLReader

from behaviour_planning.over_domain_models.smt.fbi.planner.planner import ForbidBehaviourIterativeSMT
from .argparser import create_parser
from .utilities import process_args

def main(args=None):
    """
    Main planning routine
    """

    if args is None: args = sys.argv[1:]

    # Parse planner args
    parser = create_parser()
    args = parser.parse_args(args)
    bspace_cfg, planner_cfg = process_args(args)
    
    # Read the planning task.
    task = PDDLReader().parse_problem(args.domain, args.problem)

    fbi_planner = ForbidBehaviourIterativeSMT(task, bspace_cfg, planner_cfg)
    plans = fbi_planner.plan(args.k)

    if args.dump_dir:
        plans_dirs = os.path.join(args.dump_dir, 'plans')
        os.makedirs(plans_dirs, exist_ok=True)
        for i, plan in enumerate(plans):
            with open(os.path.join(plans_dirs, f'plan_{i}.sas'), 'w') as f:
                f.write(str(plan))
        
        logs_dir = os.path.join(args.dump_dir, 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        # Write to json file
        with open(os.path.join(logs_dir, 'logs.json'), 'w') as f:
            json.dump(fbi_planner.logs(), f)
    
if __name__ == '__main__':
    main(sys.argv[1:])
