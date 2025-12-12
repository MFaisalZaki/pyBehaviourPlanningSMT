import os
import json
from collections import Counter
from analyser import read_raw_results

fi_solved_instances = []

for f in os.listdir('/home/ma342/developer/pyBehaviourPlanningSMT/sandbox-benchmark-dev/fi-solved-instances'):
    with open(os.path.join('/home/ma342/developer/pyBehaviourPlanningSMT/sandbox-benchmark-dev/fi-solved-instances', f), 'r') as file:
        fi_solved_instances.append(json.load(file))



bc_counted = os.listdir('/home/ma342/developer/pyBehaviourPlanningSMT/sandbox-benchmark-dev/resultsdir')















results_dir = '/home/ma342/developer/pyBehaviourPlanningSMT/sandbox-benchmark-oversubscription/resultsdir'


raw_results = read_raw_results(results_dir)

symk  = list(filter(lambda x: x['q'] == 0.25 and x['k'] == 5  and x['planner'] == 'fbi-smt-naive', raw_results))

smt  = list(filter(lambda x: x['q'] == 0.25 and x['k'] == 5  and x['planner'] == 'fbi-smt', raw_results))
smtnaive = list(filter(lambda x: x['q'] == 0.25 and x['k'] == 5  and x['planner'] == 'fbi-smt-naive', raw_results))

smt_instances_unsolved = set((e['domain'], e['instance']) for e in filter(lambda e: len(e['plans']) > 0 and len(e['plans']) < e['k'], smt))

pass
