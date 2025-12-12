import argparse
import os
import sys
import json
import time

import unified_planning as up
import subprocess
import tempfile

import renamer

from itertools import chain
from subprocess import SubprocessError
from copy import deepcopy
from unified_planning.io import PDDLReader, PDDLWriter
from unified_planning.shortcuts import CompilationKind, Compiler
from unified_planning.shortcuts import OneshotPlanner, AnytimePlanner, OperatorKind
from unified_planning.engines import PlanGenerationResultStatus as ResultsStatus

from behaviour_planning.over_domain_models.smt.shortcuts import GoalPredicatesOrderingSMT, MakespanOptimalCostSMT, ResourceCountSMT, UtilityValueSMT, FunctionsSMT
from behaviour_planning.over_domain_models.smt.shortcuts import ForbidBehaviourIterativeSMT

from behaviour_planning.over_domain_models.smt.bss.behaviour_count.behaviour_counter_simulator import BehaviourCountSimulator
from behaviour_planning.over_domain_models.smt.bss.behaviour_count.behaviour_counter_simulator import GoalPredicatesOrderingSimulator, MakespanOptimalCostSimulator, ResourceCountSimulator, UtilityValueSimulator, FunctionsSimulator

from behaviour_planning.over_domain_models.smt.fbi.planner.planner import ForbidBehaviourIterativeSMT

def convert_smt_dims_to_simulator_dims(dims):
    sim_dims = []
    for dclass, addinfo in dims:
        sim_dims.append([eval(dclass.__name__.replace('SMT', 'Simulator')), addinfo])
    return sim_dims

def arg_parser():
    parser = argparse.ArgumentParser(description="Generate SLURM tasks for running experiments.")
    parser.add_argument('--taskfile', type=str, required=True, help='Path to the task file.')
    parser.add_argument('--outputdir', type=str, required=True, help='Directory to store output files.')
    return parser

def add_utility_values(task):
    from unified_planning.model.walkers.free_vars import FreeVarsExtractor
    vars = next(map(lambda expr: FreeVarsExtractor().get(expr), task.goals), None)
    if vars is None: return {}
    goals = {g: (i+1)*2 for i, g in enumerate(vars)}
    task.add_quality_metric(up.model.metrics.Oversubscription(goals, task.environment))
    return goals

def construct_task_details_info(taskdetails):
    return {
            'domain' : os.path.basename(os.path.dirname(taskdetails['domainfile-name'])) + '/' + os.path.basename(taskdetails['domainfile-name']),
            'problem': os.path.basename(taskdetails['problemfile-name']),
            'planner': taskdetails['planner'],
            'tag' : taskdetails['planner'],
            'planning-type': taskdetails['planning-type'],
            'k': taskdetails['k-plans'],
            'q': taskdetails['q']
        }


def construct_results_file(taskdetails, task, plans):
    task_writer = PDDLWriter(task)
    resultsfile = {
        'plans': [task_writer.get_plan(p) + f';{len(p.actions)} cost (unit)' + f'\n;behaviour: {p.behaviour.replace("\n","")}' for p in plans],
        'diversity-scores': {
            'behaviour-count': len(set(p.behaviour for p in plans))
        },
        'info' : construct_task_details_info(taskdetails),
    }
    return resultsfile

def select_plans_using_bspace_simulator(taskdetails, task, dims, planslist):
    from behaviour_planning.over_domain_models.smt.bss.behaviour_count.behaviour_counter_simulator import BehaviourCountSimulator
    bspace = BehaviourCountSimulator(task, planslist, dims)
    return bspace, bspace.selected_plans(taskdetails['k-plans'])


def select_plans_using_bspace_smt(taskdetails, dims, planlist, compilation_list, is_oversubscription_planning):
    from behaviour_planning.over_domain_models.smt.bss.behaviour_count.behaviour_count import BehaviourCountSMT
    bspace_cfg = {
        "encoder": "seq",
        # "encoder": "r2e",
        # "encoder": "forall",
        "solver-timeout-ms": 600000,
        "solver-memorylimit-mb": 16000,
        "dims": dims,
        "run-plan-validation": False,
        "disable-after-goal-state-actions": False,
        "select-k": taskdetails['k-plans']
    }
    bspace = BehaviourCountSMT(taskdetails['domainfile'], taskdetails['problemfile'], bspace_cfg, planlist, is_oversubscription_planning, compilation_list)
    return bspace, bspace.selected_plans(taskdetails['k-plans'])


def run_fbi(taskdetails, dims, compilation_list):
    task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])
    k = taskdetails['k-plans']
    q = taskdetails['q']

    base_planner_cfg = {}

    if taskdetails['planning-type'] == 'numerical':
        base_planner_cfg = {
            "planner-name": "SMTPlanner",
            "encoder": "EncoderForall", 
            "upper-bound": 100, 
            "search-strategy": "SMTSearch", 
            "configuration": "forall", 
            "run-validation": False,
            "compilationlist": list(map(lambda e: (e[0], str(e[1]).replace('CompilationKind.', '')), compilation_list))
        }
    else:
        base_planner_cfg = {
            "planner-name": "symk-opt",
            "symk_search_time_limit": "900s"
        }

    _params = {
        "fbi-planner-type": "ForbidBehaviourIterativeSMT",
        "base-planner-cfg": base_planner_cfg,
        "bspace-cfg": {
            "quality-bound-factor" : q,
            "encoder": "seq",
            "solver-timeout-ms": 600000,
            "solver-memorylimit-mb": 16000,
            "dims": [] if 'naive' in taskdetails['planner'] else dims,
            "compliation-list": compilation_list,
            "run-plan-validation": False,
            "disable-after-goal-state-actions": False
        }
    }

    # If the planning task is oversubscription, we add the utility dimension by default.
    _goals  = add_utility_values(task) if taskdetails['planning-type'] == 'oversubscription' else {}
    planner = ForbidBehaviourIterativeSMT(task, _params['bspace-cfg'], _params['base-planner-cfg'])
    plans   = planner.plan(k)
    dims = convert_smt_dims_to_simulator_dims(dims)
    # If the planning task is oversub update the addinfo
    if taskdetails['planning-type'] == 'oversubscription':
        for idx, (dclass, addinfo) in enumerate(dims):
            if dclass.__name__ == 'UtilityValueSimulator':
                dims[idx][1] |= {'goals-utilities': _goals}

    bspace, selected_plans = select_plans_using_bspace_simulator(taskdetails, task, dims, plans)
    results = construct_results_file(taskdetails, task, selected_plans)
    return results | {'logs': planner.log_msg} | {'oversubscription-goals': {str(g): u for g, u in _goals.items()}}

def run_fi(taskdetails, dims, compilation_list):
    tmpdir = os.path.join(taskdetails['sandbox-dir'], 'tmp', taskdetails['filename'].replace('.json',''))
    os.makedirs(tmpdir, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmpdir) as tmpdirname:
        cmd  = [sys.executable]
        cmd += ["-m"]
        cmd += ["forbiditerative.plan"]
        cmd += ["--planner"]
        cmd += ["extended_unordered_topq"]
        cmd += ["--domain"]
        cmd += [taskdetails['domainfile']]
        cmd += ["--problem"]
        cmd += [taskdetails['problemfile']]
        cmd += ["--number-of-plans"]
        cmd += [str(taskdetails['k-plans'])]
        cmd += ["--quality-bound"]
        cmd += [str(taskdetails['q'])]
        cmd += ["--symmetries"]
        cmd += ["--use-local-folder"]
        cmd += ["--clean-local-folder"]
        cmd += ["--suppress-planners-output"]
        cmd += ["--overall-time-limit"]
        cmd += ["1800"]

        fienv = os.environ.copy()
        fienv['FI_PLANNER_RUNS'] = tmpdir
        logs = []
        try:
            output = subprocess.check_output(cmd, env=fienv, cwd=tmpdir)
        except SubprocessError as e:
            logs.append(str(e))
        finally:    
            planlist = []
            found_plans = os.path.join(tmpdir, 'found_plans', 'done')
            if not os.path.exists(found_plans): return {}
            for plan in os.listdir(found_plans):
                with open(os.path.join(found_plans, plan), 'r') as f:
                    plan = f.read()
                    if not plan in planlist: planlist.append(plan)
            _planlist_str_cpy = planlist[:]
            task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])


            generated_results = os.path.join(taskdetails['sandbox-dir'], 'fi-solved-instances')
            os.makedirs(generated_results, exist_ok=True)
            _solved_task_details = construct_task_details_info(taskdetails) | {'found-plans': planlist}
            task_writer = PDDLWriter(task)
            _solved_task_details |= {'domain-str': task_writer.get_domain(), 'problem-str': task_writer.get_problem()}
            
            with open(os.path.join(generated_results, f"{taskdetails['filename'].replace('.json','')}_plans.json"), 'w') as f:
                json.dump(_solved_task_details, f, indent=4)
            
            planlist = list(map(lambda p: PDDLReader().parse_plan_string(task, p), list(set(planlist))[:1500])) # cap the plans to 1500 to have results to compare with FBI. 
            # For FI we are testing the goal predicate ordering
            dims = convert_smt_dims_to_simulator_dims(dims)
            bspace, selected_plans = select_plans_using_bspace_simulator(taskdetails, task, dims, planlist)
            results = construct_results_file(taskdetails, task, selected_plans)
            return results | {'logs': logs}

def run_symk(taskdetails, dims, compilation_list):
    tmpdir = os.path.join(taskdetails['sandbox-dir'], 'tmp', taskdetails['filename'].replace('.json',''))
    os.makedirs(tmpdir, exist_ok=True)
    task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])
    k = taskdetails['k-plans']
    q = taskdetails['q']

    planlist = []
    with tempfile.TemporaryDirectory(dir=tmpdir) as tmpdirname:        
        with OneshotPlanner(name="symk-opt") as planner:
            result = planner.solve(task)
            plan = result.plan
            assert plan is not None, "No plan found by symk"
            cost_bound = int(len(plan.actions) * q)

    _goals  = {}
    if taskdetails['planning-type'] == 'oversubscription':
        _goals  = add_utility_values(task) 
        task.goals.clear()
    
    for idx, (dclass, addinfo) in enumerate(dims):
        if dclass.__name__ in ['MakespanOptimalCostSMT', 'CostBoundSMT']:
            dims[idx][1] |= {'optimal-plan-length': len(plan.actions), 'is-oversubscription': taskdetails['planning-type'] == 'oversubscription'}
        elif dclass.__name__ == 'UtilityValueSMT':
            dims[idx][1] |= {'goals-utilities': _goals}

    # now remove the hard goals then generate k plans with different utilities.
    with tempfile.TemporaryDirectory(dir=tmpdir) as tmpdirname:        
        with AnytimePlanner(name='symk', params={"symk_search_time_limit": "1800",
                                                 "plan_cost_bound": 
                                                 cost_bound, "number_of_plans": k}) as planner:
            for i, result in enumerate(planner.get_solutions(task)):
                if result.status == ResultsStatus.INTERMEDIATE:
                    planlist.append(result.plan) if i < k else None
    
    planlist = list(filter(lambda p: len(p.actions) > 0, planlist))
    # I hate this but let's rewrtite the plans to work with 
    # planlist = list(map(lambda p: PDDLReader().parse_plan_string(task, PDDLWriter(task).get_plan(p)), planlist))
    dims = convert_smt_dims_to_simulator_dims(dims)
    bspace, selected_plans = select_plans_using_bspace_simulator(taskdetails, task, dims, planlist)
    results = construct_results_file(taskdetails, task, selected_plans)
    return results | {'oversubscription-goals': {str(g): u for g, u in _goals.items()}}

def solve(taskname, args):

    env = up.environment.get_environment()
    env.error_used_name = False
    env.credits_stream  = None

    with open(args.taskfile, 'r') as f:
        taskdetails = json.load(f)
    
    # TODO: Run a task renamer compilation to avoid the issue triggered by the mismatch between action names due 
    # the difference in - and _.
    tmpdir = os.path.join(taskdetails['sandbox-dir'], 'tmp', taskdetails['filename'].replace('.json',''))
    os.makedirs(tmpdir, exist_ok=True)
    # read the task, then rename it and then write it back.
    # 
    # renamed_task   = renamer.Renamer().compile(_original_task).problem
    compilation_list  = []
    if not taskdetails['planning-type'] == 'numerical':
        compilation_list += [["up_quantifiers_remover", CompilationKind.QUANTIFIERS_REMOVING]]
        compilation_list += [["up_disjunctive_conditions_remover", CompilationKind.DISJUNCTIVE_CONDITIONS_REMOVING]]
    # Apply these compilations and write the problem to a file to deal with with -,_ mistmatch.

    _original_task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])
    names = [name for name, _ in compilation_list]
    compilationkinds = [kind for _, kind in compilation_list]
    with Compiler(names=names, compilation_kinds=compilationkinds) as compiler:
        compiled_task = compiler.compile(_original_task)

    _task_writer   = PDDLWriter(compiled_task.problem)
    renamed_domainfile  = os.path.join(tmpdir, 'renamed-domain.pddl')
    renamed_problemfile = os.path.join(tmpdir, 'renamed-problem.pddl')
    _task_writer.write_domain(renamed_domainfile)
    _task_writer.write_problem(renamed_problemfile)

    taskdetails['domainfile-name']  = taskdetails['domainfile']
    taskdetails['problemfile-name'] = taskdetails['problemfile']

    taskdetails['domainfile']  = renamed_domainfile
    taskdetails['problemfile'] = renamed_problemfile

    compilation_list += [["up_grounder", CompilationKind.GROUNDING]] if 'numerical' in taskdetails['planning-type'] else [["fast-downward-reachability-grounder", CompilationKind.GROUNDING]]

    dims = []

    if taskdetails['planning-type'] == 'oversubscription':
        dims = [
            [MakespanOptimalCostSMT, {"cost-bound-factor": taskdetails['q']}],
            [UtilityValueSMT, {}]
        ]
    else:
        dims = [
            [GoalPredicatesOrderingSMT, {}],
            [MakespanOptimalCostSMT, {"cost-bound-factor": taskdetails['q']}]
        ]
        if taskdetails['resources'] is not None and os.path.exists(taskdetails['resources']):
            # I hate this but we have no saying in this.
            # make sure to rename the resouces details.
            with open(taskdetails['resources'], 'r') as f:
                resource_content = f.read()
            resource_content = resource_content.replace('-', '_')
            with open(taskdetails['resources'], 'w') as f:
                f.write(resource_content)

            if taskdetails['planning-type'] == 'numerical':
                dims += [[FunctionsSMT, taskdetails['resources']]]
            else:
                dims += [[ResourceCountSMT, taskdetails['resources']]]

    ret_details = {}
    start_time = time.time()
    match taskdetails['planner']:
        case 'fbi-smt-naive' | 'fbi-smt':
            ret_details = run_fbi(taskdetails,  dims, compilation_list)
        case 'fi-bc':
            ret_details = run_fi(taskdetails,   dims, compilation_list)
        case 'symk':
            ret_details = run_symk(taskdetails, dims, compilation_list)
        case _:
            assert False, f"Unknown planning type {taskdetails['planning-type']}"
    end_time = time.time()
    ret_details['total-time-seconds'] = end_time - start_time

    outputpath = os.path.join(args.outputdir, f'{taskname}-results.json')
    if len(ret_details) == 0: return
    with open(outputpath, 'w') as f:
        json.dump(ret_details, f, indent=4)
    
    # delete created files.
    if os.path.exists(taskdetails['domainfile']):
        # delete the dir 
        import shutil
        shutil.rmtree(os.path.dirname(taskdetails['domainfile']))

def main():
    args = arg_parser().parse_args()
    sandbox_dir = os.path.dirname(args.outputdir)
    taskname = os.path.basename(args.taskfile).replace('.json','')
    errorsdir = os.path.join(sandbox_dir, 'errors')
    os.makedirs(errorsdir, exist_ok=True)
    os.makedirs(args.outputdir, exist_ok=True)
    
    # # for dev only
    # solve(taskname, args)

    try:
        solve(taskname, args)
    except Exception as e:
        with open(os.path.join(errorsdir, f'{taskname}_error.log'), 'a') as f:
            f.write(str(e) + '\n')
    
    pass

if __name__ == "__main__":
    main()