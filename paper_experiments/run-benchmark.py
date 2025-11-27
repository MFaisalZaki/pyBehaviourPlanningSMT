import argparse
import os
import json

import unified_planning as up
from copy import deepcopy
from unified_planning.io import PDDLReader, PDDLWriter
from unified_planning.shortcuts import CompilationKind
from unified_planning.shortcuts import OneshotPlanner

from behaviour_planning.over_domain_models.smt.shortcuts import GoalPredicatesOrderingSMT, MakespanOptimalCostSMT, ResourceCountSMT
from behaviour_planning.over_domain_models.smt.shortcuts import ForbidBehaviourIterativeSMT
from up_behaviour_planning.FBIPlannerUp import FBIPlanner

from behaviour_planning.over_domain_models.smt.fbi.planner.planner import ForbidBehaviourIterativeSMT
            

env = up.environment.get_environment()
env.factory.add_engine('FBIPlanner', __name__, 'FBIPlanner')

def arg_parser():
    parser = argparse.ArgumentParser(description="Generate SLURM tasks for running experiments.")
    parser.add_argument('--taskfile', type=str, required=True, help='Path to the task file.')
    parser.add_argument('--outputdir', type=str, required=True, help='Directory to store output files.')
    return parser

def dump_results_file(taskdetails, planner, plans, outputpath):
    task_writer = PDDLWriter(planner.basic_task)
    resultsfile = {
        'plans': [task_writer.get_plan(p) + f';{len(p.actions)} cost (unit)' + f';{p.behaviour}' for p in plans],
        'diversity-scores': {
            'behaviour-count': len(set(p.behaviour for p in plans)),
            'distribution': planner.bspace._behaviour_frequency
        },
        'info' : {
            'domain' : os.path.basename(os.path.dirname(taskdetails['domainfile'])) + '/' + os.path.basename(taskdetails['domainfile']),
            'problem': os.path.basename(taskdetails['problemfile']),
            'planner': 'fbi-seq',
            'tag' : 'fbi-seq-fd-incremental',
            'k': taskdetails['k-plans'],
            'q': 1.0
        },
        'logs': planner.log_msg
    }
    with open(outputpath, 'w') as f:
        json.dump(resultsfile, f, indent=4)

def solve(taskname, args):

    with open(args.taskfile, 'r') as f:
        taskdetails = json.load(f)
    
    task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])
    
    
    dims = [
        [GoalPredicatesOrderingSMT, {}],
        [MakespanOptimalCostSMT, {"cost-bound-factor": 1.0}]
    ]
    
    if taskdetails['resources'] is not None and os.path.exists(taskdetails['resources']): 
        dims += [[ResourceCountSMT, taskdetails['resources']]]
    
    _params = {
        "fbi-planner-type": "ForbidBehaviourIterativeSMT",
        "base-planner-cfg": {
            "planner-name": "symk-opt",
            "symk_search_time_limit": "900s"
          },
          "bspace-cfg": {
            "encoder": "seq",
            "solver-timeout-ms": 600000,
            "solver-memorylimit-mb": 16000,
            "dims": dims,
            "compliation-list": [
              ["up_quantifiers_remover", CompilationKind.QUANTIFIERS_REMOVING],
              ["fast-downward-reachability-grounder", CompilationKind.GROUNDING]
            ],
            "run-plan-validation": False,
            "disable-after-goal-state-actions": False
          }
    }

    planner = ForbidBehaviourIterativeSMT(task, _params['bspace-cfg'], _params['base-planner-cfg'])
    plans = planner.plan(taskdetails['k-plans'])
    if len(plans) == 0: return
    dump_results_file(taskdetails, planner, plans, os.path.join(args.outputdir, f'{taskname}-1.0-{taskdetails["k-plans"]}-incremental-fbi-seq-fd-{taskdetails["k-plans"]}-scores.json'))

def main():
    args = arg_parser().parse_args()
    sandbox_dir = os.path.dirname(args.outputdir)
    taskname = os.path.basename(args.taskfile).replace('.json','')
    errorsdir = os.path.join(sandbox_dir, 'errors')
    os.makedirs(errorsdir, exist_ok=True)
    
    # # for dev only
    solve(taskname, args)

    try:
        solve(taskname, args)
    except Exception as e:
        with open(os.path.join(errorsdir, f'{taskname}_error.log'), 'a') as f:
            f.write(str(e) + '\n')

if __name__ == "__main__":
    main()