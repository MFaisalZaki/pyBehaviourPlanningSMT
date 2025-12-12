import os
import json
from collections import Counter
from analyser import read_raw_results

from unified_planning.io import PDDLReader
from behaviour_planning.over_domain_models.smt.bss.behaviour_count.behaviour_counter_simulator import GoalPredicatesOrderingSimulator, MakespanOptimalCostSimulator, ResourceCountSimulator, UtilityValueSimulator, FunctionsSimulator

fi_solved_instances_dir = '/home/ma342/developer/pyBehaviourPlanningSMT/sandbox-benchmark-dev/fi-solved-instances'

fi_solved_instances = set(map(lambda f: f.replace('_plans.json','.json'), os.listdir(fi_solved_instances_dir)))
bc_counted = set(map(lambda f: f.replace('-results.json','.json'), os.listdir('/home/ma342/developer/pyBehaviourPlanningSMT/sandbox-benchmark-dev/resultsdir')))


rovers_4 = json.load(open(os.path.join(fi_solved_instances_dir, '2.0-100-classical-None-tsp-17-fi-bc_plans.json')))

task = PDDLReader().parse_problem_string(rovers_4['domain'], rovers_4['problem'])

plans = list(map(lambda p: PDDLReader().parse_plan_string(task, p), rovers_4['found-plans'])) # cap the plans to 1500 to have results to compare with FBI. 

from behaviour_planning.over_domain_models.smt.bss.behaviour_count.behaviour_counter_simulator import BehaviourCountSimulator

dims = [
    (GoalPredicatesOrderingSimulator, {}),
    (ResourceCountSimulator,'/home/ma342/developer/pyBehaviourPlanningSMT/sandbox-benchmark-classical/resource-usage-dumps/rovers_4_resources.txt')
]

bspace = BehaviourCountSimulator(task, plans, dims)
selected_plans = bspace.selected_plans(5)


pass















results_dir = '/home/ma342/developer/pyBehaviourPlanningSMT/sandbox-benchmark-oversubscription/resultsdir'


raw_results = read_raw_results(results_dir)

symk  = list(filter(lambda x: x['q'] == 0.25 and x['k'] == 5  and x['planner'] == 'fbi-smt-naive', raw_results))

smt  = list(filter(lambda x: x['q'] == 0.25 and x['k'] == 5  and x['planner'] == 'fbi-smt', raw_results))
smtnaive = list(filter(lambda x: x['q'] == 0.25 and x['k'] == 5  and x['planner'] == 'fbi-smt-naive', raw_results))

smt_instances_unsolved = set((e['domain'], e['instance']) for e in filter(lambda e: len(e['plans']) > 0 and len(e['plans']) < e['k'], smt))

pass
